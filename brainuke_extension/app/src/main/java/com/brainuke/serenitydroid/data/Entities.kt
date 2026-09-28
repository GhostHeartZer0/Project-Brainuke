package com.brainuke.serenitydroid.data

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import org.json.JSONObject

@Entity(
    tableName = "telemetry_logs",
    indices = [Index(value = ["isSynced"]), Index(value = ["timestamp"])]
)
data class TelemetryEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val timestamp: Long,
    val batteryPct: Int,
    val isCharging: Boolean,
    val networkType: String,
    val lightLux: Float?,
    val proximityCm: Float?,
    val isSynced: Boolean = false
) {
    fun toPayloadJson(): JSONObject {
        return JSONObject().apply {
            put("type", "telemetry")
            put("local_id", id)
            put("timestamp", timestamp)
            put("battery_pct", batteryPct)
            put("is_charging", isCharging)
            put("network_type", networkType)
            put("light_lux", lightLux?.toDouble() ?: JSONObject.NULL)
            put("proximity_cm", proximityCm?.toDouble() ?: JSONObject.NULL)
        }
    }
}

@Entity(
    tableName = "memory_nodes",
    indices = [Index(value = ["serverInsightId"], unique = true), Index(value = ["timestamp"])]
)
data class MemoryNodeEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val serverInsightId: Long,
    val insight: String,
    val emotionalShiftJson: String,
    val worldDeltaJson: String,
    val timestamp: Long
)

@Entity(
    tableName = "conversation_turns",
    indices = [Index(value = ["isSynced"]), Index(value = ["timestamp"])]
)
data class ConversationEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val serverTurnId: Long? = null,
    val userInput: String,
    val thoughtStream: String = "",
    val finalResponse: String,
    val sourceDevice: String = "android",
    val affectStateJson: String = "{}",
    val timestamp: Long = System.currentTimeMillis(),
    val isSynced: Boolean = false
) {
    fun toPayloadJson(): JSONObject {
        return JSONObject().apply {
            put("local_id", id)
            put("user_input", userInput)
            put("thought_stream", thoughtStream)
            put("final_response", finalResponse)
            put("source_device", sourceDevice)
            put("affect_state", try { JSONObject(affectStateJson) } catch (_: Exception) { JSONObject() })
            put("timestamp", timestamp)
        }
    }
}
