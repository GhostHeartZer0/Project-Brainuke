package com.brainuke.serenitydroid.network

import com.brainuke.serenitydroid.model.AudioChunkPayload
import com.brainuke.serenitydroid.model.BrainukeEvent
import com.brainuke.serenitydroid.model.TelemetryPayload
import com.brainuke.serenitydroid.model.VisionPayload
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.BufferedReader
import java.io.IOException
import java.io.InputStream
import java.security.KeyStore
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509TrustManager

/**
 * High-performance network and security manager for connecting Project Brainuke to the PC-based Throne.
 */
class ThroneClient(
    private val throneHost: String,
    private val thronePort: Int = 8443,
    private val authToken: String,
    rootCaStream: InputStream
) {
    private val baseUrl = "https://$throneHost:$thronePort"
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    private val okHttpClient: OkHttpClient

    init {
        val (sslContext, trustManager) = configureTls(rootCaStream)

        val authInterceptor = Interceptor { chain ->
            val authenticatedRequest = chain.request().newBuilder()
                .header("Authorization", "Bearer $authToken")
                .header("User-Agent", "ProjectBrainuke/1.0")
                .build()
            chain.proceed(authenticatedRequest)
        }

        val connectionPool = okhttp3.ConnectionPool(
            maxIdleConnections = 8,
            keepAliveDuration = 2,
            TimeUnit.MINUTES
        )

        okHttpClient = OkHttpClient.Builder()
            .connectionPool(connectionPool)
            .sslSocketFactory(sslContext.socketFactory, trustManager)
            .hostnameVerifier { hostname, _ ->
                // Allow direct connection to Throne LAN IP or localhost
                hostname == throneHost || hostname == "localhost" || hostname == "127.0.0.1"
            }
            .addInterceptor(authInterceptor)
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.MILLISECONDS) // Indefinite for SSE streaming
            .writeTimeout(30, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }

    /**
     * Initializes custom X509TrustManager pinning the manual rootCA.pem trust anchor.
     */
    private fun configureTls(caInputStream: InputStream): Pair<SSLContext, X509TrustManager> {
        val certFactory = CertificateFactory.getInstance("X.509")
        val caCert = caInputStream.use { certFactory.generateCertificate(it) as X509Certificate }

        val keyStore = KeyStore.getInstance(KeyStore.getDefaultType()).apply {
            load(null, null)
            setCertificateEntry("brainuke_root_ca", caCert)
        }

        val tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()).apply {
            init(keyStore)
        }

        val trustManagers = tmf.trustManagers
        val x509TrustManager = trustManagers.filterIsInstance<X509TrustManager>().firstOrNull()
            ?: throw IllegalStateException("No X509TrustManager found")

        val sslContext = SSLContext.getInstance("TLS").apply {
            init(null, arrayOf(x509TrustManager), null)
        }

        return Pair(sslContext, x509TrustManager)
    }

    /**
     * Downlink SSE stream listener with coroutine flow and automatic backoff reconnection.
     */
    fun listenToDownlink(): Flow<BrainukeEvent> = flow {
        var backoffMs = 1000L
        val maxBackoffMs = 15000L

        while (currentCoroutineContext().isActive) {
            val request = Request.Builder()
                .url("$baseUrl/subscriptions/listen")
                .header("Accept", "text/event-stream")
                .header("Cache-Control", "no-cache")
                .build()

            var call: Call? = null
            var response: Response? = null

            try {
                call = okHttpClient.newCall(request)
                response = call.execute()

                if (!response.isSuccessful) {
                    emit(BrainukeEvent.Error("SSE connection failed with HTTP ${response.code}"))
                    delay(backoffMs)
                    backoffMs = (backoffMs * 2).coerceAtMost(maxBackoffMs)
                    continue
                }

                // Reset backoff on successful connect
                backoffMs = 1000L

                val body = response.body ?: throw IOException("Empty SSE response body")
                val reader = BufferedReader(body.charStream())

                val dataBuffer = StringBuilder()
                var line: String? = null

                while (currentCoroutineContext().isActive && reader.readLine().also { line = it } != null) {
                    val currentLine = line ?: break

                    when {
                        currentLine.startsWith("data:") -> {
                            val dataContent = currentLine.removePrefix("data:").trim()
                            dataBuffer.append(dataContent)
                        }
                        currentLine.isEmpty() -> {
                            // Blank line signals end of current SSE event frame
                            if (dataBuffer.isNotEmpty()) {
                                val eventJson = dataBuffer.toString()
                                dataBuffer.clear()
                                emit(BrainukeEvent.fromJson(eventJson))
                            }
                        }
                        currentLine.startsWith(":") -> {
                            // SSE comment / keep-alive heartbeat, ignore
                        }
                    }
                }
            } catch (e: Exception) {
                if (currentCoroutineContext().isActive) {
                    emit(BrainukeEvent.Error("SSE stream interrupted: ${e.message}", e))
                    delay(backoffMs)
                    backoffMs = (backoffMs * 2).coerceAtMost(maxBackoffMs)
                }
            } finally {
                response?.close()
                call?.cancel()
            }
        }
    }.flowOn(Dispatchers.IO)

    /**
     * Uplink: Sends periodic telemetry metrics.
     */
    suspend fun sendTelemetry(payload: TelemetryPayload): Result<Unit> = withContext(Dispatchers.IO) {
        postJson("/api/v1/sensory/stream", payload.toJson())
    }

    /**
     * Uplink: Streams Base64 PCM voice chunks detected by local VAD.
     */
    suspend fun sendAudioChunk(payload: AudioChunkPayload): Result<Unit> = withContext(Dispatchers.IO) {
        postJson("/api/v1/sensory/stream", payload.toJson())
    }

    /**
     * Uplink: Sends CameraX low-resolution JPEG frame.
     */
    suspend fun sendVisionFrame(payload: VisionPayload): Result<Unit> = withContext(Dispatchers.IO) {
        postJson("/api/v1/sensory/stream", payload.toJson())
    }

    /**
     * DataSync: Pushes queued local SQLite telemetry batch to Throne pool host.
     */
    suspend fun pushSyncBatch(json: String): Result<String> = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/sync/push")
            .post(json.toRequestBody(jsonMediaType))
            .build()

        try {
            okHttpClient.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    Result.success(response.body?.string() ?: "{}")
                } else {
                    Result.failure(IOException("Sync push failed with HTTP ${response.code}"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * DataSync: Pulls consolidated memory delta pack from Throne DMN.
     */
    suspend fun pullSyncDelta(sinceEpochMs: Long = 0): Result<String> = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/sync/pull?since=$sinceEpochMs")
            .get()
            .build()

        try {
            okHttpClient.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    Result.success(response.body?.string() ?: "{}")
                } else {
                    Result.failure(IOException("Sync pull failed with HTTP ${response.code}"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Executes pairing handshake with Throne, retrieving dynamic auth token.
     */
    suspend fun pairWithThrone(deviceId: String, deviceType: String = "android"): Result<String> = withContext(Dispatchers.IO) {
        val json = org.json.JSONObject().apply {
            put("device_id", deviceId)
            put("device_type", deviceType)
        }.toString()

        val request = Request.Builder()
            .url("$baseUrl/api/v1/pairing/handshake")
            .post(json.toRequestBody(jsonMediaType))
            .build()

        try {
            okHttpClient.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    Result.success(response.body?.string() ?: "{}")
                } else {
                    Result.failure(IOException("Pairing failed with HTTP ${response.code}"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Sends session handoff request to Throne.
     */
    suspend fun requestHandoff(targetDevice: String, sourceDevice: String = "android"): Result<String> = withContext(Dispatchers.IO) {
        val json = org.json.JSONObject().apply {
            put("target_device", targetDevice)
            put("source_device", sourceDevice)
        }.toString()

        val request = Request.Builder()
            .url("$baseUrl/api/v1/session/handoff")
            .post(json.toRequestBody(jsonMediaType))
            .build()

        try {
            okHttpClient.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    Result.success(response.body?.string() ?: "{}")
                } else {
                    Result.failure(IOException("Session handoff failed with HTTP ${response.code}"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Checks Throne cognitive inference availability and latency.
     */
    suspend fun checkCognitiveStatus(): Result<String> = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/cognitive/status")
            .get()
            .build()

        try {
            val startMs = System.currentTimeMillis()
            okHttpClient.newCall(request).execute().use { response ->
                val elapsed = System.currentTimeMillis() - startMs
                if (response.isSuccessful) {
                    val body = response.body?.string() ?: "{}"
                    val json = org.json.JSONObject(body).apply {
                        put("latency_ms", elapsed)
                    }
                    Result.success(json.toString())
                } else {
                    Result.failure(IOException("Cognitive status check failed with HTTP ${response.code}"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Fetches active conversation session snapshot from Throne.
     */
    suspend fun fetchActiveSession(): Result<String> = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/session/active")
            .get()
            .build()

        try {
            okHttpClient.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    Result.success(response.body?.string() ?: "{}")
                } else {
                    Result.failure(IOException("Fetch active session failed with HTTP ${response.code}"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Sends user dialogue turn to Throne Cognitive Orchestrator.
     */
    suspend fun sendInteraction(text: String): Result<String> = withContext(Dispatchers.IO) {
        val payload = org.json.JSONObject().apply {
            put("text", text)
            put("context", org.json.JSONArray())
        }
        val request = Request.Builder()
            .url("$baseUrl/api/v1/cognitive/interact")
            .post(payload.toString().toRequestBody(jsonMediaType))
            .build()

        try {
            okHttpClient.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    Result.success(response.body?.string() ?: "{}")
                } else {
                    Result.failure(IOException("Cognitive interact failed HTTP ${response.code}"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private fun postJson(endpoint: String, json: String): Result<Unit> {
        val request = Request.Builder()
            .url("$baseUrl$endpoint")
            .post(json.toRequestBody(jsonMediaType))
            .build()

        return try {
            okHttpClient.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    Result.success(Unit)
                } else {
                    Result.failure(IOException("Server returned HTTP ${response.code}: ${response.message}"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
