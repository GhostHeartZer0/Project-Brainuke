package com.brainuke.serenitydroid.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.util.Base64
import android.util.Log
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.brainuke.serenitydroid.inference.LocalInferenceEngine
import com.brainuke.serenitydroid.model.AudioChunkPayload
import com.brainuke.serenitydroid.model.BrainukeEvent
import com.brainuke.serenitydroid.model.InferenceConfig
import com.brainuke.serenitydroid.model.ModelLoadState
import com.brainuke.serenitydroid.model.ModelType
import com.brainuke.serenitydroid.model.TelemetryPayload
import com.brainuke.serenitydroid.model.VisionPayload
import com.brainuke.serenitydroid.network.ThroneClient
import com.brainuke.serenitydroid.util.ThoughtIsolator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import kotlin.math.sqrt

/**
 * Foreground Service managing Android sensory ingest (Telemetry, Audio/VAD, Vision)
 * and SSE downlink collection for Project Brainuke.
 */
class SensoryService : Service(), SensorEventListener {

    private val binder = LocalBinder()
    private val serviceJob = SupervisorJob()
    private val serviceScope = CoroutineScope(serviceJob + Dispatchers.Default)

    private var throneClient: ThroneClient? = null

    // Downlink event bus for Jetpack Compose UI
    private val _downlinkEvents = MutableSharedFlow<BrainukeEvent>(replay = 50)
    val downlinkEvents: SharedFlow<BrainukeEvent> = _downlinkEvents.asSharedFlow()

    enum class InferenceMode {
        THRONE_OFFLOAD,
        LOCAL_REFLEX
    }

    @Volatile
    private var currentInferenceMode = InferenceMode.THRONE_OFFLOAD

    fun getInferenceMode(): InferenceMode = currentInferenceMode

    fun setInferenceMode(mode: InferenceMode) {
        currentInferenceMode = mode
    }


    suspend fun evaluateInferenceOffload(): InferenceMode = withContext(Dispatchers.IO) {
        val client = throneClient
        if (client == null) {
            currentInferenceMode = InferenceMode.LOCAL_REFLEX
            return@withContext currentInferenceMode
        }
        val statusRes = client.checkCognitiveStatus()
        currentInferenceMode = if (statusRes.isSuccess) {
            val json = org.json.JSONObject(statusRes.getOrThrow())
            val latency = json.optLong("latency_ms", 999L)
            val isOnline = json.optString("status") == "online"
            if (isOnline && latency < 250) InferenceMode.THRONE_OFFLOAD else InferenceMode.LOCAL_REFLEX
        } else {
            InferenceMode.LOCAL_REFLEX
        }
        currentInferenceMode
    }

    @Volatile
    private var activeStoragePath: String = "/storage/emulated/0/SerenityDroid/E2B"

    fun getActiveStoragePath(): String = activeStoragePath

    fun setActiveStoragePath(path: String) {
        if (path.isNotEmpty()) {
            activeStoragePath = path
        }
    }

    private val localInferenceEngine = LocalInferenceEngine(this)

    fun getLocalInferenceEngine(): LocalInferenceEngine = localInferenceEngine

    fun getModelLoadState(): StateFlow<ModelLoadState> =
        localInferenceEngine.loadState

    fun getInferenceConfig(): InferenceConfig =
        localInferenceEngine.getConfig()

    fun updateInferenceConfig(config: InferenceConfig) {
        localInferenceEngine.updateConfig(config)
    }

    suspend fun loadModel(
        targetType: ModelType? = null,
        storagePath: String? = null
    ): ModelLoadState {
        val path = storagePath ?: activeStoragePath
        setActiveStoragePath(path)
        return localInferenceEngine.loadModel(targetType, path)
    }

    fun unloadModel(): ModelLoadState =
        localInferenceEngine.unloadModel()

    /**
     * Processes user interactions, dynamically routing between Throne cloud/desktop offload
     * and on-device local reflex runner with strict thought/response isolation.
     */
    suspend fun processInteraction(userInput: String): ThoughtIsolator.IsolatedResult = withContext(Dispatchers.IO) {
        val client = throneClient
        val mode = if (currentInferenceMode == InferenceMode.THRONE_OFFLOAD) evaluateInferenceOffload() else currentInferenceMode

        if (mode == InferenceMode.THRONE_OFFLOAD && client != null) {
            val throneRes = client.sendInteraction(userInput)
            if (throneRes.isSuccess) {
                try {
                    val json = org.json.JSONObject(throneRes.getOrThrow())
                    val rawThought = json.optString("thought", "")
                    val rawResponse = json.optString("response", "...")

                    val isolated = ThoughtIsolator.isolate(rawThought, rawResponse)

                    syncRepository.queueConversationTurn(
                        userInput = userInput,
                        thoughtStream = isolated.thought,
                        finalResponse = isolated.speech
                    )

                    return@withContext isolated
                } catch (e: Exception) {
                    Log.w(TAG, "Failed to parse Throne response, falling back to local reflex: ${e.message}")
                }
            } else {
                Log.w(TAG, "Throne offload failed: ${throneRes.exceptionOrNull()?.message}. Falling back to local reflex.")
            }
        }

        // Offline / Local Reflex Mode Fallback
        val telemetry = gatherTelemetry()
        val reflex = localInferenceEngine.executeReflex(userInput, telemetry)
        val isolated = ThoughtIsolator.isolate(reflex.thought, reflex.speech)

        syncRepository.queueConversationTurn(
            userInput = userInput,
            thoughtStream = isolated.thought,
            finalResponse = isolated.speech
        )

        isolated
    }

    // Sensors
    private lateinit var sensorManager: SensorManager
    private var lightSensor: Sensor? = null
    private var proximitySensor: Sensor? = null
    private var latestLightLux: Float? = null
    private var latestProximityCm: Float? = null

    // Audio & VAD configuration
    private val sampleRate = 16000
    private val channelConfig = AudioFormat.CHANNEL_IN_MONO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private var audioJob: Job? = null

    // CameraX ImageCapture instance
    private var imageCapture: ImageCapture? = null

    // Room Database Repository
    private lateinit var syncRepository: com.brainuke.serenitydroid.data.SyncRepository

    inner class LocalBinder : Binder() {
        fun getService(): SensoryService = this@SensoryService
    }

    override fun onBind(intent: Intent?): IBinder = binder

    fun getSyncRepository(): com.brainuke.serenitydroid.data.SyncRepository = syncRepository

    override fun onCreate() {
        super.onCreate()
        val database = com.brainuke.serenitydroid.data.BrainukeDatabase.getDatabase(this)
        syncRepository = com.brainuke.serenitydroid.data.SyncRepository(database)
        startForegroundServiceNotification()
        initializeSensors()
    }

    /**
     * Initializes Throne connection and starts sensory pipelines.
     */
    fun attachThroneClient(client: ThroneClient) {
        this.throneClient = client

        startDownlinkListener()
        startPeriodicTelemetry()
        startAudioStream()
    }

    // --- 1. FOREGROUND NOTIFICATION ---

    private fun startForegroundServiceNotification() {
        val channelId = "serenity_sensory_pipeline"
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Serenity Ingest Pipeline",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Streaming sensory context to Project Brainuke Throne"
            }
            notificationManager.createNotificationChannel(channel)
        }

        val notification: Notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle("Project Brainuke Active")
            .setContentText("Sensory extension linked to Throne")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .build()

        startForeground(1001, notification)
    }

    // --- 2. THE DOWNLINK (SSE LISTENER) ---

    private fun startDownlinkListener() {
        val client = throneClient ?: return
        serviceScope.launch(Dispatchers.IO) {
            client.listenToDownlink().collect { rawEvent ->
                val processedEvent = when (rawEvent) {
                    is BrainukeEvent.Speech -> {
                        val isolated = ThoughtIsolator.isolate(null, rawEvent.content)
                        if (isolated.thought.isNotEmpty()) {
                            _downlinkEvents.emit(BrainukeEvent.Thought(isolated.thought))
                        }
                        BrainukeEvent.Speech(isolated.speech)
                    }
                    else -> rawEvent
                }
                _downlinkEvents.emit(processedEvent)
                when (processedEvent) {
                    is BrainukeEvent.Thought -> Log.d(TAG, "[Internal Thought]: ${processedEvent.content}")
                    is BrainukeEvent.Speech -> Log.i(TAG, "[Spoken Voice]: ${processedEvent.content}")
                    is BrainukeEvent.ThoughtChunk -> Log.d(TAG, "[Thought Chunk]: ${processedEvent.chunk}")
                    is BrainukeEvent.SpeechChunk -> Log.d(TAG, "[Speech Chunk]: ${processedEvent.chunk}")
                    is BrainukeEvent.Heartbeat -> Log.v(TAG, "[Heartbeat]: ${processedEvent.state}")
                    is BrainukeEvent.SyncRequest -> {
                        Log.i(TAG, "[Sync Request]: PC Throne requested bidirectional sync. Executing...")
                        serviceScope.launch(Dispatchers.IO) {
                            try {
                                syncRepository.executeSync(client)
                            } catch (e: Exception) {
                                Log.w(TAG, "Downlink-triggered sync failed: ${e.message}")
                            }
                        }
                    }
                    is BrainukeEvent.SyncUpdate -> Log.i(TAG, "[Sync Update]: ${processedEvent.summary}")
                    is BrainukeEvent.Error -> Log.e(TAG, "[Downlink Error]: ${processedEvent.message}")
                    is BrainukeEvent.Unknown -> Log.w(TAG, "[Unknown Event]: ${processedEvent.rawType}")
                    else -> {}
                }
            }
        }
    }

    // --- 3. THE UPLINK: PERIODIC TELEMETRY ---

    private fun initializeSensors() {
        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        lightSensor = sensorManager.getDefaultSensor(Sensor.TYPE_LIGHT)
        proximitySensor = sensorManager.getDefaultSensor(Sensor.TYPE_PROXIMITY)

        lightSensor?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL) }
        proximitySensor?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL) }
    }

    override fun onSensorChanged(event: SensorEvent?) {
        event ?: return
        when (event.sensor.type) {
            Sensor.TYPE_LIGHT -> latestLightLux = event.values[0]
            Sensor.TYPE_PROXIMITY -> latestProximityCm = event.values[0]
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    private fun startPeriodicTelemetry() {
        serviceScope.launch(Dispatchers.IO) {
            while (isActive) {
                try {
                    val payload = gatherTelemetry()
                    syncRepository.queueTelemetry(payload)

                    val client = throneClient
                    if (client != null) {
                        val result = client.sendTelemetry(payload)
                        if (result.isFailure) {
                            Log.w(TAG, "Telemetry upload failed: ${result.exceptionOrNull()?.message}")
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Error generating telemetry", e)
                }
                delay(30_000L) // 30-second interval
            }
        }
    }

    private fun gatherTelemetry(): TelemetryPayload {
        // Battery info
        val batteryIntent = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = batteryIntent?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = batteryIntent?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val batteryPct = if (level != -1 && scale != -1) ((level / scale.toFloat()) * 100).toInt() else -1

        val status = batteryIntent?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val isCharging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                status == BatteryManager.BATTERY_STATUS_FULL

        // Network info
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val activeNetwork = cm.activeNetwork
        val caps = cm.getNetworkCapabilities(activeNetwork)
        val networkType = when {
            caps == null -> "NONE"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "WIFI"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "CELLULAR"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ETHERNET"
            else -> "OTHER"
        }

        return TelemetryPayload(
            batteryPct = batteryPct,
            isCharging = isCharging,
            networkType = networkType,
            lightLux = latestLightLux,
            proximityCm = latestProximityCm
        )
    }

    // --- 4. THE UPLINK: AUDIO STREAM & LOCAL VAD ---

    private fun startAudioStream() {
        val minBufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)
        val bufferSize = minBufferSize.coerceAtLeast(sampleRate * 2) // ~1 second chunk capacity

        try {
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                sampleRate,
                channelConfig,
                audioFormat,
                bufferSize
            )

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "AudioRecord initialization failed")
                return
            }

            audioRecord?.startRecording()
            isRecording = true

            audioJob = serviceScope.launch(Dispatchers.IO) {
                val audioBuffer = ShortArray(4000) // 250ms frames at 16kHz to prevent OkHttp dispatcher congestion
                val byteBuffer = ByteBuffer.allocate(audioBuffer.size * 2)

                while (isActive && isRecording) {
                    val readSamples = audioRecord?.read(audioBuffer, 0, audioBuffer.size) ?: 0
                    if (readSamples > 0) {
                        val rms = calculateRms(audioBuffer, readSamples)
                        val isSpeech = evaluateVad(rms)

                        if (isSpeech) {
                            byteBuffer.clear()
                            for (i in 0 until readSamples) {
                                byteBuffer.putShort(audioBuffer[i])
                            }
                            val pcmBytes = byteBuffer.array().copyOf(readSamples * 2)
                            val base64Pcm = Base64.encodeToString(pcmBytes, Base64.NO_WRAP)

                            val payload = AudioChunkPayload(
                                pcmBase64 = base64Pcm,
                                sampleRate = sampleRate,
                                channels = 1,
                                bitDepth = 16,
                                rmsEnergy = rms
                            )

                            throneClient?.sendAudioChunk(payload)
                        }
                    }
                }
            }
        } catch (e: SecurityException) {
            Log.e(TAG, "RECORD_AUDIO permission missing", e)
        }
    }

    /**
     * Root Mean Square (RMS) calculation across audio chunk.
     */
    private fun calculateRms(buffer: ShortArray, length: Int): Double {
        var sumSquares = 0.0
        for (i in 0 until length) {
            val sample = buffer[i].toDouble()
            sumSquares += sample * sample
        }
        return sqrt(sumSquares / length)
    }

    /**
     * Local Voice Activity Detection (VAD) threshold placeholder.
     * In production, this can be swapped with Silero VAD or LiteRT ONNX model.
     */
    private fun evaluateVad(rms: Double): Boolean {
        val vadEnergyThreshold = 350.0 // Noise floor threshold
        return rms > vadEnergyThreshold
    }

    // --- 5. THE UPLINK: VISION (CAMERAX LOW-RES CAPTURE) ---

    fun bindCameraProvider(cameraProvider: ProcessCameraProvider, lifecycleOwner: androidx.lifecycle.LifecycleOwner) {
        val previewSize = Size(640, 480) // Low resolution for real-time sensory pipeline
        val resolutionSelector = ResolutionSelector.Builder()
            .setResolutionStrategy(
                ResolutionStrategy(
                    previewSize,
                    ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER
                )
            )
            .build()

        imageCapture = ImageCapture.Builder()
            .setResolutionSelector(resolutionSelector)
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
            .build()

        val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

        try {
            cameraProvider.unbindAll()
            cameraProvider.bindToLifecycle(lifecycleOwner, cameraSelector, imageCapture)
            Log.i(TAG, "CameraX bound successfully for Project Brainuke")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to bind CameraX lifecycle", e)
        }
    }

    /**
     * Captures a snapshot, encodes as low-res JPEG, and posts to Throne.
     */
    suspend fun captureAndSendVisionFrame(): Result<Unit> = withContext(Dispatchers.IO) {
        val capture = imageCapture ?: return@withContext Result.failure(IllegalStateException("Camera not bound"))
        val client = throneClient ?: return@withContext Result.failure(IllegalStateException("ThroneClient not attached"))

        val deferredResult = kotlinx.coroutines.CompletableDeferred<Result<Unit>>()

        capture.takePicture(
            ContextCompat.getMainExecutor(this@SensoryService),
            object : ImageCapture.OnImageCapturedCallback() {
                override fun onCaptureSuccess(image: ImageProxy) {
                    serviceScope.launch(Dispatchers.Default) {
                        try {
                            val bitmap = imageProxyToBitmap(image)
                            image.close()

                            val stream = ByteArrayOutputStream()
                            bitmap.compress(Bitmap.CompressFormat.JPEG, 70, stream)
                            val jpegBytes = stream.toByteArray()
                            val base64Jpeg = Base64.encodeToString(jpegBytes, Base64.NO_WRAP)

                            val payload = VisionPayload(
                                jpegBase64 = base64Jpeg,
                                width = bitmap.width,
                                height = bitmap.height
                            )

                            val sendResult = client.sendVisionFrame(payload)
                            deferredResult.complete(sendResult)
                        } catch (e: Exception) {
                            deferredResult.complete(Result.failure(e))
                        }
                    }
                }

                override fun onError(exception: ImageCaptureException) {
                    deferredResult.complete(Result.failure(exception))
                }
            }
        )

        deferredResult.await()
    }

    private fun imageProxyToBitmap(image: ImageProxy): Bitmap {
        val plane = image.planes[0]
        val buffer = plane.buffer
        val bytes = ByteArray(buffer.remaining())
        buffer.get(bytes)
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }

    override fun onDestroy() {
        super.onDestroy()
        isRecording = false
        audioJob?.cancel()
        audioRecord?.apply {
            stop()
            release()
        }
        sensorManager.unregisterListener(this)
        serviceScope.cancel()
    }

    companion object {
        private const val TAG = "SensoryService"
    }
}
