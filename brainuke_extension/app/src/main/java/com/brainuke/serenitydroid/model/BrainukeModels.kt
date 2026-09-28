package com.brainuke.serenitydroid.model

import org.json.JSONObject

/**
 * Downlink events received from the Throne SSE server.
 */
sealed class BrainukeEvent {
    abstract val timestamp: Long

    data class Thought(
        val content: String,
        override val timestamp: Long = System.currentTimeMillis()
    ) : BrainukeEvent()

    data class Speech(
        val content: String,
        override val timestamp: Long = System.currentTimeMillis()
    ) : BrainukeEvent()

    data class Heartbeat(
        val state: String,
        override val timestamp: Long = System.currentTimeMillis()
    ) : BrainukeEvent()

    data class Handoff(
        val sessionId: String,
        val sourceDevice: String,
        val targetDevice: String,
        val payloadJson: String,
        override val timestamp: Long = System.currentTimeMillis()
    ) : BrainukeEvent()

    data class Unknown(
        val rawType: String,
        val payload: String,
        override val timestamp: Long = System.currentTimeMillis()
    ) : BrainukeEvent()

    data class SyncRequest(
        val source: String = "pc",
        override val timestamp: Long = System.currentTimeMillis()
    ) : BrainukeEvent()

    data class SyncUpdate(
        val lastSync: Long,
        val summary: String,
        override val timestamp: Long = System.currentTimeMillis()
    ) : BrainukeEvent()

    data class ThoughtChunk(
        val chunk: String,
        override val timestamp: Long = System.currentTimeMillis()
    ) : BrainukeEvent()

    data class SpeechChunk(
        val chunk: String,
        override val timestamp: Long = System.currentTimeMillis()
    ) : BrainukeEvent()

    data class Error(
        val message: String,
        val throwable: Throwable? = null,
        override val timestamp: Long = System.currentTimeMillis()
    ) : BrainukeEvent()

    companion object {
        fun fromJson(jsonStr: String): BrainukeEvent {
            return try {
                val json = JSONObject(jsonStr)
                val type = json.optString("type", "unknown")
                when (type) {
                    "thought" -> Thought(content = json.optString("content", ""))
                    "speech" -> Speech(content = json.optString("content", ""))
                    "thought_chunk" -> ThoughtChunk(chunk = json.optString("content", ""))
                    "speech_chunk" -> SpeechChunk(chunk = json.optString("content", ""))
                    "heartbeat" -> Heartbeat(state = json.optString("state", ""))
                    "sync_request" -> SyncRequest(source = json.optString("source", "pc"))
                    "sync_update" -> {
                        val dataObj = json.optJSONObject("data") ?: JSONObject()
                        SyncUpdate(
                            lastSync = dataObj.optLong("timestamp", System.currentTimeMillis()),
                            summary = dataObj.optString("summary", "")
                        )
                    }
                    "handoff" -> {
                        val contentStr = json.optString("content", "{}")
                        val inner = try { JSONObject(contentStr) } catch (_: Exception) { JSONObject() }
                        Handoff(
                            sessionId = inner.optString("session_id", ""),
                            sourceDevice = inner.optString("source_device", ""),
                            targetDevice = inner.optString("target_device", ""),
                            payloadJson = contentStr
                        )
                    }
                    else -> Unknown(rawType = type, payload = jsonStr)
                }
            } catch (e: Exception) {
                Error(message = "Failed to parse SSE payload", throwable = e)
            }
        }
    }
}

/**
 * 30-second periodic telemetry payload sent via Uplink.
 */
data class TelemetryPayload(
    val batteryPct: Int,
    val isCharging: Boolean,
    val networkType: String,
    val lightLux: Float?,
    val proximityCm: Float?,
    val timestamp: Long = System.currentTimeMillis()
) {
    fun toJson(): String {
        return JSONObject().apply {
            put("type", "telemetry")
            put("battery_pct", batteryPct)
            put("is_charging", isCharging)
            put("network_type", networkType)
            put("light_lux", lightLux?.toDouble() ?: JSONObject.NULL)
            put("proximity_cm", proximityCm?.toDouble() ?: JSONObject.NULL)
            put("timestamp", timestamp)
        }.toString()
    }
}

/**
 * Uplink payload for live PCM voice activity stream.
 */
data class AudioChunkPayload(
    val pcmBase64: String,
    val sampleRate: Int = 16000,
    val channels: Int = 1,
    val bitDepth: Int = 16,
    val rmsEnergy: Double,
    val timestamp: Long = System.currentTimeMillis()
) {
    fun toJson(): String {
        return JSONObject().apply {
            put("type", "audio_chunk")
            put("pcm_base64", pcmBase64)
            put("sample_rate", sampleRate)
            put("channels", channels)
            put("bit_depth", bitDepth)
            put("rms_energy", rmsEnergy)
            put("timestamp", timestamp)
        }.toString()
    }
}

/**
 * Uplink payload for snapshot vision capture.
 */
data class VisionPayload(
    val jpegBase64: String,
    val width: Int,
    val height: Int,
    val timestamp: Long = System.currentTimeMillis()
) {
    fun toJson(): String {
        return JSONObject().apply {
            put("type", "vision_frame")
            put("jpeg_base64", jpegBase64)
            put("width", width)
            put("height", height)
            put("timestamp", timestamp)
        }.toString()
    }
}

/**
 * Dialogue turn recorded locally on mobile or pulled from Throne.
 */
data class ConversationTurnPayload(
    val userInput: String,
    val thoughtStream: String = "",
    val finalResponse: String,
    val sourceDevice: String = "android",
    val affectState: Map<String, Double> = emptyMap(),
    val timestamp: Long = System.currentTimeMillis()
) {
    fun toJson(): JSONObject {
        return JSONObject().apply {
            put("user_input", userInput)
            put("thought_stream", thoughtStream)
            put("final_response", finalResponse)
            put("source_device", sourceDevice)
            put("affect_state", JSONObject(affectState))
            put("timestamp", timestamp)
        }
    }
}

/**
 * Session handoff metadata transferred between PC and Android.
 */
data class SessionHandoffData(
    val sessionId: String,
    val sourceDevice: String,
    val targetDevice: String,
    val focusDevice: String,
    val recentTurns: List<ConversationTurnPayload>,
    val affectVector: Map<String, Double>,
    val timestamp: Long
)

/**
 * Model selection options for Project Brainuke local reflex execution.
 */
enum class ModelType(
    val displayName: String,
    val description: String,
    val defaultFileName: String
) {
    NORMAL(
        displayName = "Cecilia Normal",
        description = "Mobile companion core: witty, sarcastic, protective fallen angel.",
        defaultFileName = "cecilia-normal-2b.gguf"
    ),
    SECRET(
        displayName = "Cecilia Secret",
        description = "Level 7 Fallen Angel persona: unfiltered, witty, sarcastic, protective truth-seeker.",
        defaultFileName = "cecilia-secret-level7-7b.gguf"
    )
}

/**
 * Lifecycle state representing local LLM memory load status.
 */
sealed class ModelLoadState {
    object Unloaded : ModelLoadState()
    data class Loading(val progress: Int, val modelType: ModelType) : ModelLoadState()
    data class Loaded(
        val modelType: ModelType,
        val modelName: String,
        val memoryAllocatedMb: Int,
        val loadedAt: Long = System.currentTimeMillis()
    ) : ModelLoadState()
    data class Error(val message: String, val modelType: ModelType) : ModelLoadState()
}

/**
 * Basic & essential inference configuration options for local LLM reflex execution.
 */
data class InferenceConfig(
    val modelType: ModelType = ModelType.NORMAL,
    val temperature: Float = 0.7f,
    val topP: Float = 0.9f,
    val maxTokens: Int = 256,
    val threadCount: Int = 4,
    val contextWindow: Int = 2048,
    val strictThoughtIsolation: Boolean = true,
    val normalModelFile: String = "cecilia-normal-2b.gguf",
    val secretModelFile: String = "cecilia-secret-level7-7b.gguf",
    val customSystemPrompt: String? = null
)

