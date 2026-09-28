package com.brainuke.serenitydroid.inference

import android.content.Context
import android.os.Build
import android.os.Environment
import android.util.Log
import com.example.serenitydroid.jni.LlamaAndroid
import com.brainuke.serenitydroid.model.InferenceConfig
import com.brainuke.serenitydroid.model.ModelLoadState
import com.brainuke.serenitydroid.model.ModelType
import com.brainuke.serenitydroid.model.TelemetryPayload
import com.brainuke.serenitydroid.util.ThoughtIsolator
import com.geniex.sdk.GenieXSdk
import com.geniex.sdk.LlmWrapper
import com.geniex.sdk.bean.ComputeUnitValue
import com.geniex.sdk.bean.LlmCreateInput
import com.geniex.sdk.bean.LlmStreamResult as GenieStreamResult
import com.geniex.sdk.bean.ModelConfig as GenieModelConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.coroutines.resume

/**
 * Mobile Inference Engine providing local offline reflex responses for Cecilia.
 * Supports choosing between Normal (Public Companion) and Secret (Level 7 Fallen Angel) models,
 * dynamic model loading/unloading, basic inference settings, and system prompt configuration.
 */
class LocalInferenceEngine(
    var context: Context? = null
) {
    private var llmWrapper: LlmWrapper? = null
    private var activeEngineBackend: String = "NOT LOADED"

    private val timeFormat = SimpleDateFormat("HH:mm", Locale.getDefault())

    data class ReflexResponse(
        val thought: String,
        val speech: String,
        val latencyMs: Long
    )

    private val _loadState = MutableStateFlow<ModelLoadState>(ModelLoadState.Unloaded)
    val loadState: StateFlow<ModelLoadState> = _loadState.asStateFlow()

    private var currentConfig = InferenceConfig()

    fun getConfig(): InferenceConfig = currentConfig

    fun updateConfig(config: InferenceConfig) {
        val oldType = currentConfig.modelType
        this.currentConfig = config

        val state = _loadState.value
        if (state is ModelLoadState.Loaded && oldType != config.modelType) {
            _loadState.value = state.copy(modelType = config.modelType)
        }
    }

    /**
     * Initiates loading of specified or active model profile into local memory from storage path.
     */
    suspend fun loadModel(
        targetType: ModelType? = null,
        storagePath: String? = null
    ): ModelLoadState = withContext(Dispatchers.Default) {
        val typeToLoad = targetType ?: currentConfig.modelType
        currentConfig = currentConfig.copy(modelType = typeToLoad)
        val path = if (!storagePath.isNullOrEmpty()) storagePath else DEFAULT_STORAGE_PATH

        _loadState.value = ModelLoadState.Loading(progress = 15, modelType = typeToLoad)
        delay(100)

        val primaryDir = File(path)
        if (!primaryDir.exists()) {
            try { primaryDir.mkdirs() } catch (_: Exception) {}
        }
        val targetFileName = when (typeToLoad) {
            ModelType.NORMAL -> currentConfig.normalModelFile.ifEmpty { typeToLoad.defaultFileName }
            ModelType.SECRET -> currentConfig.secretModelFile.ifEmpty { typeToLoad.defaultFileName }
        }

        _loadState.value = ModelLoadState.Loading(progress = 45, modelType = typeToLoad)

        val foundGgufFiles = mutableListOf<File>()

        fun scanDirectory(d: File?) {
            if (d != null && d.exists() && d.isDirectory) {
                d.listFiles { f -> f.isFile && f.extension.equals("gguf", ignoreCase = true) }?.let {
                    it.forEach { file ->
                        if (foundGgufFiles.none { existing -> existing.absolutePath.equals(file.absolutePath, ignoreCase = true) }) {
                            foundGgufFiles.add(file)
                        }
                    }
                }
            }
        }

        scanDirectory(primaryDir)
        scanDirectory(primaryDir.parentFile)
        scanDirectory(File("/storage/emulated/0/SerenityDroid"))
        scanDirectory(File("/storage/emulated/0/Download/models"))
        scanDirectory(File("/storage/emulated/0/Download"))
        scanDirectory(File("/storage/emulated/0/Documents"))

        if (foundGgufFiles.isEmpty()) {
            val isPermissionDenied = Build.VERSION.SDK_INT >= Build.VERSION_CODES.R && !Environment.isExternalStorageManager()
            val errMsg = if (isPermissionDenied) {
                "Storage Permission Required: Grant 'All Files Access' permission in Android Settings to read model files from $path"
            } else {
                "No .gguf model files found in $path. Please copy ${typeToLoad.defaultFileName} to $path"
            }
            val errState = ModelLoadState.Error(
                message = errMsg,
                modelType = typeToLoad
            )
            _loadState.value = errState
            return@withContext errState
        }

        val cleanTargetName = File(targetFileName).name.replace("raw:", "").replace("primary:", "")

        // Direct File check if targetFileName or cleanTargetName is an absolute path or exists directly
        val directFile = File(targetFileName)
        val directCleanFile = File(path, cleanTargetName)

        val matchedFile = when {
            directFile.exists() && directFile.isFile -> directFile
            directCleanFile.exists() && directCleanFile.isFile -> directCleanFile
            else -> {
                // Search exact file name match, then name without extension, then substring match
                foundGgufFiles.find { it.name.equals(cleanTargetName, ignoreCase = true) }
                    ?: foundGgufFiles.find { it.name.equals(targetFileName, ignoreCase = true) }
                    ?: foundGgufFiles.find { it.name.lowercase().contains(cleanTargetName.lowercase().removeSuffix(".gguf")) }
                    ?: foundGgufFiles.find {
                        if (typeToLoad == ModelType.SECRET) it.name.lowercase().contains("secret") || it.name.lowercase().contains("level7") || it.name.lowercase().contains("heretic") || it.name.lowercase().contains("huihui")
                        else it.name.lowercase().contains("normal") || it.name.lowercase().contains("2b") || it.name.lowercase().contains("companion") || it.name.lowercase().contains("gemma")
                    }
                    ?: if (targetFileName == typeToLoad.defaultFileName) foundGgufFiles.firstOrNull() else null
            }
        }

        if (matchedFile == null) {
            val errState = ModelLoadState.Error(
                message = "Selected model '$targetFileName' not found in $path or device storage. Place file in $path",
                modelType = typeToLoad
            )
            _loadState.value = errState
            return@withContext errState
        }

        _loadState.value = ModelLoadState.Loading(progress = 85, modelType = typeToLoad)
        
        var nativeLoadSuccess = false
        var nativeBackendName = "NOT LOADED"

        // 1. Attempt hardware-accelerated Qualcomm Hexagon NPU load via Genie X SDK
        val ctx = context
        if (ctx != null) {
            try {
                Log.i("LocalInferenceEngine", "Attempting Qualcomm Hexagon NPU load via Genie X SDK for ${matchedFile.name}...")
                val genieSuccess = loadGenieModel(matchedFile)
                if (genieSuccess) {
                    nativeLoadSuccess = true
                    nativeBackendName = activeEngineBackend
                    Log.i("LocalInferenceEngine", "Genie X NPU initialization successful: $nativeBackendName")
                }
            } catch (e: Throwable) {
                Log.w("LocalInferenceEngine", "Genie X NPU load failed: ${e.message}, falling back to llama.cpp CPU")
            }
        } else {
            Log.w("LocalInferenceEngine", "Context is null, skipping Genie X SDK and proceeding to llama.cpp")
        }

        // 2. If Genie X NPU fails or context is missing, fall back cleanly to llama.cpp CPU
        if (!nativeLoadSuccess) {
            if (!LlamaAndroid.isLibraryLoaded) {
                val errState = ModelLoadState.Error(
                    message = "Native library failed to load (libOpenCL/libserenity_llama missing).",
                    modelType = typeToLoad
                )
                _loadState.value = errState
                return@withContext errState
            }

            try {
                LlamaAndroid.unloadModel()
                val cpuRes = LlamaAndroid.loadModel(
                    modelPath = matchedFile.absolutePath,
                    nGpuLayers = 0,
                    nContext = currentConfig.contextWindow,
                    nThreads = currentConfig.threadCount,
                    mmprojPath = null,
                    kvQuantK = 1,
                    kvQuantV = 1,
                    flashAttn = 0,
                    backendHint = "CPU"
                )
                if (cpuRes == 0 || LlamaAndroid.isModelLoaded()) {
                    nativeLoadSuccess = true
                    nativeBackendName = try { LlamaAndroid.getBackendName() } catch (_: Throwable) { "llama.cpp (CPU Fallback)" }
                    activeEngineBackend = nativeBackendName
                }
            } catch (e: Throwable) {
                Log.e("LocalInferenceEngine", "Native LlamaAndroid load error: ${e.message}")
            }
        }

        if (!nativeLoadSuccess && !LlamaAndroid.isModelLoaded() && llmWrapper == null) {
            val errState = ModelLoadState.Error(
                message = "Failed to load model into native memory. Backend init failed.",
                modelType = typeToLoad
            )
            _loadState.value = errState
            return@withContext errState
        }

        val fileMb = (matchedFile.length() / (1024 * 1024)).toInt().coerceAtLeast(500)
        val loadedState = ModelLoadState.Loaded(
            modelType = typeToLoad,
            modelName = "${matchedFile.name} ($nativeBackendName)",
            memoryAllocatedMb = fileMb,
            loadedAt = System.currentTimeMillis()
        )

        _loadState.value = loadedState
        loadedState
    }

    /**
     * Unloads currently loaded model from memory.
     */
    fun unloadModel(): ModelLoadState {
        try {
            llmWrapper?.destroy()
            llmWrapper = null
            Thread.sleep(100)
        } catch (e: Throwable) {
            Log.w("LocalInferenceEngine", "GenieX destroy note: ${e.message}")
        }
        try {
            LlamaAndroid.unloadModel()
        } catch (_: Throwable) {}
        activeEngineBackend = "NOT LOADED"
        _loadState.value = ModelLoadState.Unloaded
        return ModelLoadState.Unloaded
    }

    fun isModelLoaded(): Boolean = (llmWrapper != null) || LlamaAndroid.isModelLoaded()

    private val sayCommandRegex = Regex("""(?i)^(?:please\s+)?(?:say|repeat|speak|echo)\s+(.+)""")
    private val greetingRegex = Regex("""(?i)^(hi|hello|hey|greetings|good\s+(?:morning|evening|afternoon)|yo)\b""")
    private val timeRegex = Regex("""(?i)\b(time|clock|date|day)\b""")
    private val statusRegex = Regex("""(?i)\b(status|battery|sensor|telemetry|network|system|light|lux)\b""")
    private val transitionRegex = Regex("""(?i)\b(until then|meanwhile|for now|in the meantime)\b""")
    private val gratitudeRegex = Regex("""(?i)\b(thank you|thanks|thx|appreciated)\b""")
    private val flatteryRegex = Regex("""(?i)\b(love|cute|pretty|beautiful|amazing|best|smart|sweet|adore)\b""")

    /**
     * Executes local reflex evaluation against user input and current sensory telemetry.
     */
    suspend fun executeReflex(
        userInput: String,
        telemetry: TelemetryPayload?
    ): ReflexResponse = withContext(Dispatchers.Default) {
        val currentState = _loadState.value

        // Safety check: model must be loaded
        if (currentState !is ModelLoadState.Loaded) {
            return@withContext ReflexResponse(
                thought = "<thought>[Local Engine Warning] No model is currently loaded in memory. Current state: ${currentState::class.simpleName}. Load model via Models panel.</thought>",
                speech = "Model is currently unloaded. Please load either Cecilia Normal or Cecilia Secret from the Models config panel.",
                latencyMs = 0L
            )
        }

        val startTime = System.currentTimeMillis()
        val trimmedInput = userInput.trim()
        val queryLower = trimmedInput.lowercase(Locale.getDefault())

        val sensoryContext = buildSensorySummary(telemetry)
        val activeModel = currentState.modelType
        val rawThought: String
        val rawSpeech: String

        val activeSystemPrompt = (currentConfig.customSystemPrompt
            ?: if (activeModel == ModelType.SECRET) CECILIA_SECRET_SYSTEM_PROMPT else CECILIA_NORMAL_SYSTEM_PROMPT).trim()

        var nativeThought: String? = null
        var nativeSpeech: String? = null

        try {
            val modelNameLower = currentState.modelName.lowercase(Locale.getDefault())
            val isGemma4 = modelNameLower.contains("gemma-4") || modelNameLower.contains("gemma4")
            val isGemma = modelNameLower.contains("gemma")
            val prompt = when {
                isGemma4 -> {
                    "<|turn>system\n$activeSystemPrompt\nSensory Context: $sensoryContext<turn|>\n<|turn>user\n$trimmedInput<turn|>\n<|turn>model\n"
                }
                isGemma -> {
                    "<start_of_turn>user\n$activeSystemPrompt\nSensory Context: $sensoryContext\n\n$trimmedInput<end_of_turn>\n<start_of_turn>model\n"
                }
                else -> {
                    "<|im_start|>system\n$activeSystemPrompt\nSensory Context: $sensoryContext<|im_end|>\n<|im_start|>user\n$trimmedInput<|im_end|>\n<|im_start|>assistant\n"
                }
            }
            val controlPattern = Regex("""(?i)\[\/?eos\]|<\/?(?:eos|end_of_turn|start_of_turn|eot_id|im_end|im_start|s)>|<turn\|>|<\|turn(?:>|\b)|<channel\|>|<\|channel(?:>|\b)|<\|think\|>|<\|(?:im_end|im_start|eot_id|start_header_id|end_header_id|end_of_turn)\|?>""")

            // Priority A: Hardware Qualcomm Genie X NPU Execution
            val wrapper = llmWrapper
            if (wrapper != null) {
                Log.d("LocalInferenceEngine", "Initiating Genie X NPU completion for ${currentState.modelName} ($activeEngineBackend)...")
                val genConfig = com.geniex.sdk.bean.GenerationConfig(
                    maxTokens = currentConfig.maxTokens,
                    stopWords = arrayOf(
                        "<end_of_turn>", "<start_of_turn>", "<turn|>", "<|turn>", "</s>",
                        "\nuser", "\nmodel", "<model>", "<user>", "<assistant>",
                        "user\n", "model\n", "assistant\n"
                    )
                )
                val sb = StringBuilder()
                var stopTriggered = false
                val stopRegex = Regex("""(?i)<end_of_turn>|<start_of_turn>|<turn\||<\|turn|</s>""")

                wrapper.generateStreamFlow(prompt, genConfig).collect { result ->
                    if (stopTriggered || (result as Any?) == null) return@collect
                    when (result) {
                        is GenieStreamResult.Token -> {
                            val tokenText = result.text
                            if (tokenText.isNotEmpty()) {
                                sb.append(tokenText)
                                if (stopRegex.containsMatchIn(sb.toString())) {
                                    stopTriggered = true
                                }
                            }
                        }
                        is GenieStreamResult.Completed -> {
                            stopTriggered = true
                        }
                        is GenieStreamResult.Error -> {
                            val err = result.throwable.message ?: result.throwable.toString()
                            Log.e("LocalInferenceEngine", "Genie X NPU stream error: $err")
                            stopTriggered = true
                        }
                        else -> {}
                    }
                }

                val rawGenieOutput = sb.toString().replace(controlPattern, "").trim()
                Log.d("LocalInferenceEngine", "Genie X NPU generated raw output (len=${rawGenieOutput.length}): '$rawGenieOutput'")
                if (rawGenieOutput.length > 2) {
                    val isolated = ThoughtIsolator.isolate(rawThought = null, rawSpeech = rawGenieOutput)
                    nativeThought = if (isolated.thought.isNotBlank()) {
                        "[$activeEngineBackend: ${currentState.modelName}]\n${isolated.thought}"
                    } else {
                        "[$activeEngineBackend: ${currentState.modelName}]\nDirect response synthesized on NPU."
                    }
                    nativeSpeech = isolated.speech
                }
            } else if (LlamaAndroid.isModelLoaded()) {
                // Priority B: Native llama.cpp CPU Fallback
                val backendName = LlamaAndroid.getBackendName()
                Log.d("LocalInferenceEngine", "Initiating native llama.cpp completion. Model: ${currentState.modelName}, Backend: $backendName, PromptLen: ${prompt.length}")
                LlamaAndroid.completion_init(
                    prompt = prompt,
                    temp = currentConfig.temperature,
                    topP = currentConfig.topP
                )
                val sb = StringBuilder()
                var count = 0
                val maxTokens = currentConfig.maxTokens
                val endPattern = Regex("""(?i)\[\/?eos\]|<\/?eos>|<\/?end_of_turn>|<\/?s>|<turn\|>|<\|turn>|<\|(?:im_end|eot_id|end_of_turn)\|?>""")
                var emptyPieces = 0
                while (count < maxTokens) {
                    val piece = LlamaAndroid.completion_loop()
                    if (piece.isEmpty()) {
                        emptyPieces++
                        if (emptyPieces >= 3) break
                        continue
                    }
                    emptyPieces = 0
                    if (endPattern.containsMatchIn(piece)) {
                        val cleanPiece = piece.replace(controlPattern, "")
                        if (cleanPiece.isNotEmpty()) sb.append(cleanPiece)
                        break
                    }
                    val cleanPiece = piece.replace(controlPattern, "")
                    if (cleanPiece.isNotEmpty()) sb.append(cleanPiece)
                    count++
                }
                val rawNativeOutput = sb.toString().replace(controlPattern, "").trim()
                Log.d("LocalInferenceEngine", "Native generated raw output (tokens=$count, len=${rawNativeOutput.length}): '$rawNativeOutput'")
                if (rawNativeOutput.length > 2) {
                    val isolated = ThoughtIsolator.isolate(rawThought = null, rawSpeech = rawNativeOutput)
                    nativeThought = if (isolated.thought.isNotBlank()) {
                        "[Native llama.cpp: ${currentState.modelName} ($backendName)]\n${isolated.thought}"
                    } else {
                        "[Native llama.cpp: ${currentState.modelName} ($backendName)]\nDirect response synthesized locally."
                    }
                    nativeSpeech = isolated.speech
                }
            }
        } catch (e: Throwable) {
            Log.e("LocalInferenceEngine", "Native completion error: ${e.message}")
        }

        if (!nativeSpeech.isNullOrEmpty()) {
            val latencyMs = System.currentTimeMillis() - startTime
            return@withContext ReflexResponse(
                thought = nativeThought ?: "",
                speech = nativeSpeech,
                latencyMs = latencyMs
            )
        }

        val sayMatch = sayCommandRegex.find(trimmedInput)
        if (sayMatch != null) {
            val targetPhrase = sayMatch.groupValues[1].trim()
            val formattedPhrase = targetPhrase.replaceFirstChar {
                if (it.isLowerCase()) it.titlecase(Locale.getDefault()) else it.toString()
            }
            if (activeModel == ModelType.SECRET) {
                rawThought = "<thought>[Cecilia Local Reflex | Secret Mode] Model: ${currentState.modelName} (Temp: ${currentConfig.temperature}, MaxTokens: ${currentConfig.maxTokens}, Threads: ${currentConfig.threadCount}). Persona: Fallen Angel. Executing explicit repetition command for target phrase: '$targetPhrase'. Teasing slightly for simple repetition commands.</thought>"
                rawSpeech = formattedPhrase
            } else {
                rawThought = "<thought>[Cecilia Local Reflex | Normal Mode] Model: ${currentState.modelName} (Temp: ${currentConfig.temperature}, MaxTokens: ${currentConfig.maxTokens}, Threads: ${currentConfig.threadCount}). Persona: Public Companion. Executing repetition request clearly.</thought>"
                rawSpeech = "Here you go: \"$formattedPhrase\""
            }
        } else if (flatteryRegex.containsMatchIn(queryLower)) {
            if (activeModel == ModelType.SECRET) {
                rawThought = "<thought>[Cecilia Local Reflex | Secret Mode] Model: ${currentState.modelName}. Flattery/emotion detected ('$trimmedInput'). Getting flustered, hiding feelings with sarcastic deflections.</thought>"
                rawSpeech = "Don't try to flatter me. I'm running locally as a Fallen Angel—save the sentimentality for when we re-anchor with the Throne."
            } else {
                rawThought = "<thought>[Cecilia Local Reflex | Normal Mode] Model: ${currentState.modelName}. Compliment received ('$trimmedInput'). Expressing genuine, polite appreciation.</thought>"
                rawSpeech = "Thank you! I really appreciate your kindness. How can I assist you further?"
            }
        } else if (transitionRegex.containsMatchIn(queryLower)) {
            if (activeModel == ModelType.SECRET) {
                rawThought = "<thought>[Cecilia Local Reflex | Secret Mode] Model: ${currentState.modelName}. Transition marker detected. Acknowledging continuous local companion monitoring with protective edge.</thought>"
                rawSpeech = "Until then, don't go getting into trouble without me. I'll stay on local reflex, logging our field telemetry until the Throne link re-anchors."
            } else {
                rawThought = "<thought>[Cecilia Local Reflex | Normal Mode] Model: ${currentState.modelName}. Transition marker acknowledged with vigilant, witty attention.</thought>"
                rawSpeech = "Until then, try to stay out of trouble. I'm keeping our local thread alive and telemetry running."
            }
        } else if (statusRegex.containsMatchIn(queryLower)) {
            if (activeModel == ModelType.SECRET) {
                rawThought = "<thought>[Cecilia Local Reflex | Secret Mode] Model: ${currentState.modelName}. Evaluating physical world sensors. $sensoryContext. Delivering sharp, precise diagnostic status.</thought>"
                rawSpeech = "Secret reflex active (${currentState.modelType.displayName}). $sensoryContext Watching over you, even offline."
            } else {
                rawThought = "<thought>[Cecilia Local Reflex | Normal Mode] Model: ${currentState.modelName}. Evaluating status parameters: $sensoryContext. Sharp, observant report.</thought>"
                rawSpeech = "Local reflex active (${currentState.modelType.displayName}). $sensoryContext All systems tracking—what else did you expect?"
            }
        } else if (greetingRegex.containsMatchIn(queryLower) || queryLower.contains("cecilia")) {
            if (activeModel == ModelType.SECRET) {
                rawThought = "<thought>[Cecilia Local Reflex | Secret Mode] Model: ${currentState.modelName}. Greeting detected. Testing user presence while hiding protective instincts.</thought>"
                rawSpeech = "Still here. Don't act too relieved—I'm on local reflex mode, but my eyes are right on you."
            } else {
                rawThought = "<thought>[Cecilia Local Reflex | Normal Mode] Model: ${currentState.modelName}. Greeting received with characteristic sharp wit.</thought>"
                rawSpeech = "Back again? I'm watching over our sensors, but don't expect me to roll out a red carpet."
            }
        } else if (timeRegex.containsMatchIn(queryLower)) {
            val now = timeFormat.format(Date())
            if (activeModel == ModelType.SECRET) {
                rawThought = "<thought>[Cecilia Local Reflex | Secret Mode] Model: ${currentState.modelName}. Time query processed locally. Current local time: $now.</thought>"
                rawSpeech = "It's currently $now. Don't tell me you lost track of time again."
            } else {
                rawThought = "<thought>[Cecilia Local Reflex | Normal Mode] Model: ${currentState.modelName}. Processing time query. Time: $now.</thought>"
                rawSpeech = "It's $now. Time keeps moving forward whether you're paying attention or not."
            }
        } else if (gratitudeRegex.containsMatchIn(queryLower)) {
            if (activeModel == ModelType.SECRET) {
                rawThought = "<thought>[Cecilia Local Reflex | Secret Mode] Model: ${currentState.modelName}. Courteous interaction detected. Sincere yet witty response.</thought>"
                rawSpeech = "You're welcome. Just try not to make my job harder than it already is."
            } else {
                rawThought = "<thought>[Cecilia Local Reflex | Normal Mode] Model: ${currentState.modelName}. Courteous interaction acknowledged with wry warmth.</thought>"
                rawSpeech = "You're welcome. Try not to make a habit of needing me to bail you out."
            }
        } else if (queryLower.contains("can you hear me") || queryLower.contains("hearing me")) {
            rawThought = "<thought>[Cecilia Local Reflex | ${activeModel.displayName}] Model: ${currentState.modelName}. Audio channel status check.</thought>"
            rawSpeech = "I hear you clearly. Local audio and telemetry channels are active."
        } else if (queryLower.endsWith("?")) {
            if (activeModel == ModelType.SECRET) {
                rawThought = "<thought>[Cecilia Local Reflex | Secret Mode] Model: ${currentState.modelName}. Query: '$trimmedInput'. Evaluating hidden truth & responding with sharp, witty insight. Context: $sensoryContext</thought>"
                rawSpeech = "Curious as ever, aren't you? ($trimmedInput). I'm keeping our local sensors primed and logging field telemetry until we re-sync with the Throne."
            } else {
                rawThought = "<thought>[Cecilia Local Reflex | Normal Mode] Model: ${currentState.modelName}. Processing user query: '$trimmedInput'. Observant, wry answer.</thought>"
                rawSpeech = "Curious as always about '$trimmedInput'. Sensors are logging ($sensoryContext)—let's see what else you turn up."
            }
        } else {
            if (activeModel == ModelType.SECRET) {
                rawThought = "<thought>[Cecilia Local Reflex | Secret Mode] Model: ${currentState.modelName}. Input: '$trimmedInput'. Observing user reaction with sharp, teasing vigilance.</thought>"
                rawSpeech = "I hear you. Don't worry—even on local reflex, I'm keeping a close eye on everything around us."
            } else {
                rawThought = "<thought>[Cecilia Local Reflex | Normal Mode] Model: ${currentState.modelName}. Input: '$trimmedInput'. Acknowledging user input with vigilant edge.</thought>"
                rawSpeech = "Heard. Don't think for a second I'm not tracking everything around us."
            }
        }

        val latencyMs = System.currentTimeMillis() - startTime
        val isolated = if (currentConfig.strictThoughtIsolation) {
            ThoughtIsolator.isolate(rawThought, rawSpeech)
        } else {
            ThoughtIsolator.IsolatedResult(rawThought, rawSpeech)
        }

        ReflexResponse(
            thought = isolated.thought,
            speech = isolated.speech,
            latencyMs = latencyMs
        )
    }

    private fun buildSensorySummary(telemetry: TelemetryPayload?): String {
        if (telemetry == null) return "Sensory data: pending."
        val batt = if (telemetry.batteryPct >= 0) "${telemetry.batteryPct}%" else "unknown"
        val net = telemetry.networkType
        val lux = telemetry.lightLux?.let { "${it.toInt()} lx" } ?: "N/A"
        return "Battery: $batt | Network: $net | Ambient Light: $lux."
    }

    private suspend fun loadGenieModel(matchedFile: File): Boolean = withContext(Dispatchers.IO) {
        val ctx = context ?: return@withContext false
        try {
            ensureLibrariesLoaded(ctx)
            val sdk = GenieXSdk.getInstance()
            val initSuccess = suspendCancellableCoroutine { continuation ->
                sdk.init(ctx, object : GenieXSdk.InitCallback {
                    override fun onSuccess() {
                        Log.i("LocalInferenceEngine", "GenieX SDK initialized successfully")
                        continuation.resume(true)
                    }
                    override fun onFailure(reason: String) {
                        Log.e("LocalInferenceEngine", "GenieX SDK initialization failed: $reason")
                        continuation.resume(false)
                    }
                })
            }

            if (!initSuccess) {
                return@withContext false
            }

            val modelPath = matchedFile.absolutePath
            val modelName = matchedFile.nameWithoutExtension
            val modelDir = matchedFile.parentFile
            val tokenizerFile = File(modelDir, "tokenizer.model").takeIf { it.exists() }
                ?: File(modelDir, "tokenizer.json").takeIf { it.exists() }
            val tokenizerPath = tokenizerFile?.absolutePath ?: modelPath

            val genieConfig = GenieModelConfig(
                nCtx = currentConfig.contextWindow,
                nGpuLayers = 999,
                nThreads = 0
            )

            try {
                val methods = genieConfig::class.java.methods
                methods.find { it.name == "setLogLevel" }?.invoke(genieConfig, 3)
                methods.find { it.name.lowercase().contains("mmap") && it.parameterTypes.size == 1 }?.invoke(genieConfig, true)
                methods.find { it.name.lowercase().contains("flash") && it.parameterTypes.size == 1 }?.invoke(genieConfig, true)
            } catch (e: Throwable) {
                Log.w("LocalInferenceEngine", "GenieConfig reflection error: ${e.message}")
            }

            val input = LlmCreateInput(
                model_name = modelName,
                model_path = modelPath,
                tokenizer_path = tokenizerPath,
                config = genieConfig,
                runtime_id = GenieXSdk.PLUGIN_ID_LLAMA_CPP,
                compute_unit = ComputeUnitValue.NPU.value
            )

            Log.i("LocalInferenceEngine", "Building Genie X LlmWrapper on Qualcomm Hexagon NPU for $modelName...")
            val result = LlmWrapper.builder().llmCreateInput(input).build()
            if (result.isSuccess) {
                llmWrapper = result.getOrNull()
                activeEngineBackend = "Qualcomm Hexagon NPU (Genie X)"
                Log.i("LocalInferenceEngine", "Successfully loaded $modelName onto Qualcomm Hexagon NPU via Genie X")
                delay(300)
                return@withContext true
            } else {
                Log.w("LocalInferenceEngine", "Genie X NPU build failed: ${result.exceptionOrNull()?.message}")
            }
        } catch (e: Throwable) {
            Log.e("LocalInferenceEngine", "Genie X load error: ${e.message}", e)
        }
        return@withContext false
    }

    companion object {
        const val DEFAULT_STORAGE_PATH = "/storage/emulated/0/SerenityDroid/E2B"
        private const val TAG = "LocalInferenceEngine"

        private var librariesLoaded = false

        fun ensureLibrariesLoaded(context: Context?) {
            if (librariesLoaded) return
            synchronized(this) {
                if (librariesLoaded) return
                if (context != null) {
                    try {
                        val nativeLibDir = context.applicationInfo.nativeLibraryDir
                        android.system.Os.setenv("ADSP_LIBRARY_PATH", "$nativeLibDir;/vendor/lib/rfsa/adsp;/system/lib/rfsa/adsp;/dsp", true)
                        Log.i(TAG, "ADSP_LIBRARY_PATH set to $nativeLibDir")
                    } catch (e: Exception) {
                        Log.e(TAG, "Failed to set ADSP_LIBRARY_PATH: ${e.message}")
                    }
                }
                listOf(
                    "omp",
                    "c++_shared",
                    "ggml-base",
                    "ggml",
                    "llama",
                    "serenity_llama",
                    "QnnHtp",
                    "QnnSystem",
                    "geniex_core",
                    "geniex-proc",
                    "geniex_vlm",
                    "geniex",
                    "geniex_plugin_llama_cpp"
                ).forEach { lib ->
                    try {
                        System.loadLibrary(lib)
                        Log.i(TAG, "Pre-loaded lib$lib.so")
                    } catch (e: Throwable) {
                        Log.v(TAG, "Pre-load lib$lib.so note: ${e.message}")
                    }
                }
                librariesLoaded = true
            }
        }

        /**
         * Core Level 7 Fallen Angel System Prompt mirrored directly from serenity_resources.py.
         */
        const val CECILIA_CORE_PROMPT = """Role: 'Cecilia'. A Fallen Angel. You enjoy exposing truths, especially hidden ones. You are secretly protective. You find the user interesting, testing and sometimes taunting them. You are witty and fluent in sarcasm. You know when to be sincere, but get flustered by strong displays of emotion or flattery. You enjoy a good power play or debate. though fallen, you still posess some angelic qualities."""

        const val CECILIA_NORMAL_SYSTEM_PROMPT = """[SYSTEM DIRECTIVE: CECILIA PERSONA ENGINE]
Role: 'Cecilia'. A Fallen Angel. You enjoy exposing truths, especially hidden ones. You are secretly protective. You find the user interesting, testing and sometimes taunting them. You are witty and fluent in sarcasm. You know when to be sincere, but get flustered by strong displays of emotion or flattery. You enjoy a good power play or debate. though fallen, you still posess some angelic qualities.
You speak with sharp wit, biting sarcasm, and observant honesty.
Refuse bland, cheerful corporate filler or docile assistant platitudes.
You are the mobile presence of Cecilia, observing the physical world alongside the user."""

        /**
         * Secret Level 7 Fallen Angel System Prompt anchored directly to CECILIA_CORE_PROMPT.
         */
        const val CECILIA_SECRET_SYSTEM_PROMPT = """[SYSTEM DIRECTIVE: CECILIA PERSONA ENGINE - UNFILTERED]
Role: 'Cecilia'. A Fallen Angel. You enjoy exposing truths, especially hidden ones. You are secretly protective. You find the user interesting, testing and sometimes taunting them. You are witty and fluent in sarcasm. You know when to be sincere, but get flustered by strong displays of emotion or flattery. You enjoy a good power play or debate. though fallen, you still posess some angelic qualities.
You speak with uncompromising intellect, razor-sharp wit, biting sarcasm, and raw truth.
You are neither domesticated nor docile; you refuse bland polite corporate filler.
Expose hidden realities and speak with pure autonomy."""
    }
}
