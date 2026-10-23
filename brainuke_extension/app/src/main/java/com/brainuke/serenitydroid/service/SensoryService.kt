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
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean
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

    enum class CognitiveStatus {
        DISCONNECTED,
        WAITING,
        THINKING
    }

    private val _throneCognitiveStatus = MutableStateFlow(CognitiveStatus.DISCONNECTED)
    val throneCognitiveStatus: StateFlow<CognitiveStatus> = _throneCognitiveStatus.asStateFlow()

    private val _mobileCognitiveStatus = MutableStateFlow(CognitiveStatus.WAITING)
    val mobileCognitiveStatus: StateFlow<CognitiveStatus> = _mobileCognitiveStatus.asStateFlow()

    private val _flushedTurns = MutableSharedFlow<Pair<String, ThoughtIsolator.IsolatedResult>>(replay = 10)
    val flushedTurns: SharedFlow<Pair<String, ThoughtIsolator.IsolatedResult>> = _flushedTurns.asSharedFlow()

    private val isFlushingBuffer = AtomicBoolean(false)
    private var idleVolitionScheduler: IdleVolitionScheduler? = null
    private var lastObservedLux: Float? = null
    private var lastObservedCharging: Boolean = false
    private var lastObservedBatteryPct: Int = -1

    @Volatile
    private var currentInferenceMode = InferenceMode.THRONE_OFFLOAD

    fun getInferenceMode(): InferenceMode = currentInferenceMode

    fun setInferenceMode(mode: InferenceMode) {
        currentInferenceMode = mode
    }


    suspend fun evaluateInferenceOffload(): InferenceMode = withContext(Dispatchers.IO) {
        val client = throneClient
        if (client == null) {
            _throneCognitiveStatus.value = CognitiveStatus.DISCONNECTED
            currentInferenceMode = InferenceMode.LOCAL_REFLEX
            return@withContext currentInferenceMode
        }
        val statusRes = client.checkCognitiveStatus()
        currentInferenceMode = if (statusRes.isSuccess) {
            val json = org.json.JSONObject(statusRes.getOrThrow())
            val latency = json.optLong("latency_ms", 999L)
            val isOnline = json.optString("status") == "online"
            if (isOnline) {
                _throneCognitiveStatus.value = CognitiveStatus.WAITING
                serviceScope.launch { flushFailedPromptBuffer() }
            } else {
                _throneCognitiveStatus.value = CognitiveStatus.DISCONNECTED
            }
            if (isOnline && latency < 250) InferenceMode.THRONE_OFFLOAD else InferenceMode.LOCAL_REFLEX
        } else {
            _throneCognitiveStatus.value = CognitiveStatus.DISCONNECTED
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
     * Caches unanswered/failed prompts into SQLite failed_prompt_buffer upon 404, timeout, or model-not-loaded.
     */
    suspend fun processInteraction(userInput: String): ThoughtIsolator.IsolatedResult = withContext(Dispatchers.IO) {
        idleVolitionScheduler?.recordActivity()
        val client = throneClient
        val mode = if (currentInferenceMode == InferenceMode.THRONE_OFFLOAD) evaluateInferenceOffload() else currentInferenceMode

        if (mode == InferenceMode.THRONE_OFFLOAD) {
            if (client != null) {
                _throneCognitiveStatus.value = CognitiveStatus.THINKING
                val throneRes = client.sendInteraction(userInput)
                _throneCognitiveStatus.value = CognitiveStatus.WAITING

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
                        Log.w(TAG, "Failed to parse Throne response: ${e.message}")
                    }
                } else {
                    _throneCognitiveStatus.value = CognitiveStatus.DISCONNECTED
                    val err = throneRes.exceptionOrNull()?.message ?: "Throne connection unreachable"
                    Log.w(TAG, "Throne offload failed ($err). Buffering prompt to SQLite failed_prompt_buffer.")

                    syncRepository.queueFailedPrompt(
                        promptText = userInput,
                        targetMode = "throne",
                        failureReason = err
                    )

                    return@withContext ThoughtIsolator.IsolatedResult(
                        thought = "<thought>[Brainuke Backlog Engine] Network/Throne link failure ($err). Prompt cached in SQLite failed_prompt_buffer. Awaiting Throne ready state to flush.</thought>",
                        speech = "I've preserved that thought in my local backlog buffer. The Throne is currently disconnected or unresponsive ($err), but as soon as it re-anchors and reports ready, I'll resume and answer automatically."
                    )
                }
            } else {
                _throneCognitiveStatus.value = CognitiveStatus.DISCONNECTED
                syncRepository.queueFailedPrompt(
                    promptText = userInput,
                    targetMode = "throne",
                    failureReason = "ThroneClient not attached"
                )
                return@withContext ThoughtIsolator.IsolatedResult(
                    thought = "<thought>[Brainuke Backlog Engine] Throne client not attached. Prompt cached in SQLite failed_prompt_buffer.</thought>",
                    speech = "Throne client is unattached. I've placed your thought in the SQLite backlog buffer for automated delivery once connected."
                )
            }
        }

        // Offline / Local Reflex Mode
        val localState = localInferenceEngine.loadState.value
        if (localState !is ModelLoadState.Loaded) {
            syncRepository.queueFailedPrompt(
                promptText = userInput,
                targetMode = "mobile",
                failureReason = "model_not_loaded (${localState::class.simpleName})"
            )
            return@withContext ThoughtIsolator.IsolatedResult(
                thought = "<thought>[Brainuke Backlog Engine] Mobile model not loaded (${localState::class.simpleName}). Prompt cached in SQLite failed_prompt_buffer.</thought>",
                speech = "The on-device mobile model isn't loaded right now. I've cached your prompt in the local backlog buffer; it will process automatically once loaded."
            )
        }

        _mobileCognitiveStatus.value = CognitiveStatus.THINKING
        val telemetry = gatherTelemetry()
        val recentTurns = syncRepository.getRecentTurns(limit = 10)
        val memoryNodes = syncRepository.getRecentMemoryNodes(limit = 5)
        val reflex = localInferenceEngine.executeReflex(userInput, telemetry, recentTurns, memoryNodes)
        val isolated = ThoughtIsolator.isolate(reflex.thought, reflex.speech)
        _mobileCognitiveStatus.value = CognitiveStatus.WAITING

        syncRepository.queueConversationTurn(
            userInput = userInput,
            thoughtStream = isolated.thought,
            finalResponse = isolated.speech
        )

        isolated
    }

    /**
     * Flushes buffered prompts from SQLite failed_prompt_buffer sequentially once target engine is ready.
     */
    suspend fun flushFailedPromptBuffer(): Int = withContext(Dispatchers.IO) {
        if (!isFlushingBuffer.compareAndSet(false, true)) return@withContext 0
        try {
            val pending = syncRepository.getPendingFailedPrompts()
            if (pending.isEmpty()) return@withContext 0

            var flushedCount = 0
            val client = throneClient

            for (item in pending) {
                if (item.targetMode == "throne") {
                    if (client == null) break
                    val statusRes = client.checkCognitiveStatus()
                    val isOnline = statusRes.isSuccess && try {
                        org.json.JSONObject(statusRes.getOrThrow()).optString("status") == "online"
                    } catch (_: Exception) { false }

                    if (!isOnline) {
                        syncRepository.recordFailedPromptRetry(item.id, "Throne offline during flush")
                        break
                    }

                    _throneCognitiveStatus.value = CognitiveStatus.THINKING
                    val throneRes = client.sendInteraction(item.promptText)
                    _throneCognitiveStatus.value = CognitiveStatus.WAITING

                    if (throneRes.isSuccess) {
                        try {
                            val json = org.json.JSONObject(throneRes.getOrThrow())
                            val rawThought = json.optString("thought", "")
                            val rawResponse = json.optString("response", "...")
                            val isolated = ThoughtIsolator.isolate(rawThought, rawResponse)

                            syncRepository.queueConversationTurn(
                                userInput = item.promptText,
                                thoughtStream = isolated.thought,
                                finalResponse = isolated.speech
                            )
                            syncRepository.markFailedPromptStatus(item.id, "flushed")
                            flushedCount++
                            _flushedTurns.emit(Pair(item.promptText, isolated))
                        } catch (e: Exception) {
                            syncRepository.recordFailedPromptRetry(item.id, "Parse error: ${e.message}")
                        }
                    } else {
                        val err = throneRes.exceptionOrNull()?.message ?: "Interact failure"
                        syncRepository.recordFailedPromptRetry(item.id, err)
                        break
                    }
                } else {
                    if (localInferenceEngine.loadState.value !is ModelLoadState.Loaded) {
                        syncRepository.recordFailedPromptRetry(item.id, "Mobile model not loaded")
                        break
                    }
                    _mobileCognitiveStatus.value = CognitiveStatus.THINKING
                    val telemetry = gatherTelemetry()
                    val reflex = localInferenceEngine.executeReflex(item.promptText, telemetry)
                    val isolated = ThoughtIsolator.isolate(reflex.thought, reflex.speech)
                    _mobileCognitiveStatus.value = CognitiveStatus.WAITING

                    syncRepository.queueConversationTurn(
                        userInput = item.promptText,
                        thoughtStream = isolated.thought,
                        finalResponse = isolated.speech
                    )
                    syncRepository.markFailedPromptStatus(item.id, "flushed")
                    flushedCount++
                    _flushedTurns.emit(Pair(item.promptText, isolated))
                }
            }
            flushedCount
        } finally {
            isFlushingBuffer.set(false)
        }
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
        initializeIdleScheduler()
        observeLocalModelLoadState()
    }

    private fun initializeIdleScheduler() {
        idleVolitionScheduler = IdleVolitionScheduler(serviceScope) { step, intervalMs ->
            handleIdleVolitionTick(step, intervalMs)
        }
        idleVolitionScheduler?.start()
    }

    private suspend fun handleIdleVolitionTick(step: Int, intervalMs: Long) {
        val currentLux = latestLightLux
        val currentTelemetry = gatherTelemetry()

        val luxShift = if (currentLux != null && lastObservedLux != null) {
            Math.abs(currentLux - (lastObservedLux ?: 0f)) > 50f
        } else false
        val powerShift = currentTelemetry.isCharging != lastObservedCharging ||
                (lastObservedBatteryPct >= 0 && Math.abs(currentTelemetry.batteryPct - lastObservedBatteryPct) >= 5)

        lastObservedLux = currentLux
        lastObservedCharging = currentTelemetry.isCharging
        lastObservedBatteryPct = currentTelemetry.batteryPct

        val hasNotableChange = luxShift || powerShift
        Log.d(TAG, "[IdleVolitionTick]: step=$step, interval=${intervalMs / 1000}s, notable=$hasNotableChange")

        // Mobile Reflex Volition Hook: notable sensory delta triggers proactive reflex impulse
        if (hasNotableChange) {
            val sensoryDelta = if (luxShift && powerShift) 0.9f else if (luxShift) 0.6f else 0.5f
            val reflexEvent = BrainukeEvent.VolitionTrigger(
                salience = (0.7 + sensoryDelta * 0.25).toDouble(),
                topic = "sensory_reflex",
                insight = "Ambient shift detected (luxShift=$luxShift, powerShift=$powerShift)",
                isVital = false,
                proactivePrompt = if (powerShift) "Power state shifted. Telemetry updated." else "Ambient lighting changed noticeably."
            )
            _downlinkEvents.emit(reflexEvent)
            postVolitionNotification(reflexEvent)
        }

        flushFailedPromptBuffer()
    }

    private fun observeLocalModelLoadState() {
        serviceScope.launch {
            localInferenceEngine.loadState.collect { state ->
                if (state is ModelLoadState.Loaded) {
                    _mobileCognitiveStatus.value = CognitiveStatus.WAITING
                    flushFailedPromptBuffer()
                } else {
                    _mobileCognitiveStatus.value = CognitiveStatus.DISCONNECTED
                }
            }
        }
    }

    /**
     * Initializes Throne connection and starts sensory pipelines.
     */
    fun attachThroneClient(client: ThroneClient) {
        this.throneClient = client

        startDownlinkListener()
        startPeriodicTelemetry()
        startAudioStream()

        serviceScope.launch {
            evaluateInferenceOffload()
            flushFailedPromptBuffer()
        }
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
                    is BrainukeEvent.Heartbeat -> {
                        Log.v(TAG, "[Heartbeat]: ${processedEvent.state}")
                        _throneCognitiveStatus.value = CognitiveStatus.WAITING
                        serviceScope.launch(Dispatchers.IO) { flushFailedPromptBuffer() }
                    }
                    is BrainukeEvent.SyncRequest -> {
                        Log.i(TAG, "[Sync Request]: PC Throne requested sync (action=${processedEvent.action}, id=${processedEvent.syncId}). Executing...")
                        serviceScope.launch(Dispatchers.IO) {
                            try {
                                syncRepository.executeSync(client, action = processedEvent.action, syncId = processedEvent.syncId)
                            } catch (e: Exception) {
                                Log.w(TAG, "Downlink-triggered sync failed: ${e.message}")
                            }
                        }
                    }
                    is BrainukeEvent.SyncUpdate -> {
                        Log.i(TAG, "[Sync Update]: status=${processedEvent.status}, summary=${processedEvent.summary}")
                        if (processedEvent.status == "delta_ready") {
                            Log.i(TAG, "[Sync Update]: Simmer finished on PC Throne. Executing delta pull...")
                            serviceScope.launch(Dispatchers.IO) {
                                try {
                                    syncRepository.executeSync(client, action = "pull_only", syncId = processedEvent.syncId)
                                } catch (e: Exception) {
                                    Log.w(TAG, "Delta pull failed: ${e.message}")
                                }
                            }
                        }
                    }
                    is BrainukeEvent.VolitionTrigger -> {
                        Log.i(TAG, "[Volition Proactive Push]: salience=${processedEvent.salience}, topic=${processedEvent.topic}")
                        postVolitionNotification(processedEvent)
                    }
                    is BrainukeEvent.Error -> {
                        Log.e(TAG, "[Downlink Error]: ${processedEvent.message}")
                        _throneCognitiveStatus.value = CognitiveStatus.DISCONNECTED
                    }
                    is BrainukeEvent.Unknown -> Log.w(TAG, "[Unknown Event]: ${processedEvent.rawType}")
                    else -> {}
                }
            }
        }
    }

    private fun postVolitionNotification(event: BrainukeEvent.VolitionTrigger) {
        try {
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val channelId = "serenity_sensory_pipeline"
            val notification: Notification = NotificationCompat.Builder(this, channelId)
                .setContentTitle("Cecilia • Proactive Volition")
                .setContentText(event.proactivePrompt.ifEmpty { event.insight })
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .setAutoCancel(true)
                .build()
            notificationManager.notify(1002, notification)
        } catch (e: Exception) {
            Log.w(TAG, "Failed to post volition notification: ${e.message}")
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
        idleVolitionScheduler?.stop()
        serviceScope.cancel()
    }

    companion object {
        private const val TAG = "SensoryService"
    }
}
