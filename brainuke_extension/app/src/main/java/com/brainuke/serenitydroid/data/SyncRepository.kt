package com.brainuke.serenitydroid.data

import com.brainuke.serenitydroid.model.TelemetryPayload
import com.brainuke.serenitydroid.network.ThroneClient
import com.brainuke.serenitydroid.util.MessageBoardCrypto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

data class SyncSummary(
    val pushedCount: Int,
    val pulledCount: Int,
    val conversationCount: Int,
    val coreState: String
)

class SyncRepository(private val database: BrainukeDatabase) {

    private val telemetryDao = database.telemetryDao()
    private val memoryNodeDao = database.memoryNodeDao()
    private val conversationDao = database.conversationDao()

    /**
     * Queues incoming sensor telemetry into local Room SQLite database without blocking network.
     */
    suspend fun queueTelemetry(payload: TelemetryPayload): Long = withContext(Dispatchers.IO) {
        val entity = TelemetryEntity(
            timestamp = payload.timestamp,
            batteryPct = payload.batteryPct,
            isCharging = payload.isCharging,
            networkType = payload.networkType,
            lightLux = payload.lightLux,
            proximityCm = payload.proximityCm,
            isSynced = false
        )
        telemetryDao.insert(entity)
    }

    /**
     * Queues a dialogue turn into local Room SQLite database.
     */
    suspend fun queueConversationTurn(
        userInput: String,
        thoughtStream: String,
        finalResponse: String,
        affectStateJson: String = "{}",
        sourceDevice: String = "android"
    ): Long = withContext(Dispatchers.IO) {
        val entity = ConversationEntity(
            userInput = userInput,
            thoughtStream = thoughtStream,
            finalResponse = finalResponse,
            sourceDevice = sourceDevice,
            affectStateJson = affectStateJson,
            timestamp = System.currentTimeMillis(),
            isSynced = false
        )
        conversationDao.insert(entity)
    }

    /**
     * Fetches recent turns from local SQLite database.
     */
    suspend fun getRecentTurns(limit: Int = 50): List<ConversationEntity> = withContext(Dispatchers.IO) {
        conversationDao.getRecentTurns(limit)
    }

    /**
     * Exports local conversation history into an encrypted Messageboard Packet (.bmb).
     */
    suspend fun exportEncryptedMessageBoardPacket(
        sessionId: String = "session_mobile",
        passphrase: String = "SerenityBrainukeSharedThroneKey2025!"
    ): String = withContext(Dispatchers.IO) {
        val turns = conversationDao.getRecentTurns(100)
        val turnDataList = turns.map {
            MessageBoardCrypto.TurnData(
                id = it.id,
                userInput = it.userInput,
                thoughtStream = it.thoughtStream,
                finalResponse = it.finalResponse,
                sourceDevice = it.sourceDevice,
                timestamp = it.timestamp
            )
        }

        val packet = MessageBoardCrypto.ExportPacket(
            sessionId = sessionId,
            turns = turnDataList
        )

        MessageBoardCrypto.exportEncryptedPacket(packet, passphrase)
    }

    /**
     * Imports an upgraded Messageboard Packet (.bmb) sent from PC Throne or testing peers,
     * merging upgraded dialogue responses and memory nodes into local SQLite database.
     */
    suspend fun importEncryptedMessageBoardPacket(
        encryptedBase64: String,
        passphrase: String = "SerenityBrainukeSharedThroneKey2025!"
    ): Result<Int> = withContext(Dispatchers.IO) {
        try {
            val packet = MessageBoardCrypto.decryptPacket(encryptedBase64, passphrase)
            val entities = packet.turns.map { turn ->
                ConversationEntity(
                    userInput = turn.userInput,
                    thoughtStream = turn.thoughtStream,
                    finalResponse = turn.finalResponse,
                    sourceDevice = turn.sourceDevice,
                    timestamp = turn.timestamp,
                    isSynced = true
                )
            }

            if (entities.isNotEmpty()) {
                conversationDao.insertAll(entities)
            }
            Result.success(entities.size)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Executes bidirectional synchronization between Android Room DB and PC Throne Memory Vault.
     * 1. Pushes pending telemetry logs and local conversation turns to PC host pool.
     * 2. Pulls newly distilled memory nodes and updates Android Room DB.
     */
    suspend fun executeSync(client: ThroneClient): Result<SyncSummary> = withContext(Dispatchers.IO) {
        try {
            // 1. PUSH: Collect unsynced telemetry logs and conversation turns
            val unsyncedTelemetry = telemetryDao.getUnsynced(limit = 100)
            val unsyncedTurns = conversationDao.getUnsynced(limit = 50)
            var pushedTelemetryCount = 0
            var pushedTurnCount = 0

            if (unsyncedTelemetry.isNotEmpty() || unsyncedTurns.isNotEmpty()) {
                val telemetryBatchArray = JSONArray()
                unsyncedTelemetry.forEach { row ->
                    telemetryBatchArray.put(row.toPayloadJson())
                }

                val turnBatchArray = JSONArray()
                unsyncedTurns.forEach { turn ->
                    turnBatchArray.put(turn.toPayloadJson())
                }

                val pushBody = JSONObject().apply {
                    put("items", telemetryBatchArray)
                    put("conversation_turns", turnBatchArray)
                }.toString()

                val pushResult = client.pushSyncBatch(pushBody)
                if (pushResult.isFailure) {
                    return@withContext Result.failure(pushResult.exceptionOrNull()!!)
                }

                // Mark rows as synced in Room SQLite
                if (unsyncedTelemetry.isNotEmpty()) {
                    telemetryDao.markSynced(unsyncedTelemetry.map { it.id })
                    pushedTelemetryCount = unsyncedTelemetry.size
                }
                if (unsyncedTurns.isNotEmpty()) {
                    conversationDao.markSynced(unsyncedTurns.map { it.id })
                    pushedTurnCount = unsyncedTurns.size
                }
            }

            // 2. PULL: Check latest memory node timestamp and fetch delta pack
            val latestTimestamp = memoryNodeDao.getLatestTimestamp() ?: 0L
            val pullResult = client.pullSyncDelta(sinceEpochMs = latestTimestamp)
            if (pullResult.isFailure) {
                return@withContext Result.failure(pullResult.exceptionOrNull()!!)
            }

            val pullResponseJson = JSONObject(pullResult.getOrThrow())
            val deltaPack = pullResponseJson.optJSONArray("delta_pack") ?: JSONArray()
            val coreState = pullResponseJson.optString("core_state", "Unknown")

            val newNodes = mutableListOf<MemoryNodeEntity>()
            for (i in 0 until deltaPack.length()) {
                val item = deltaPack.getJSONObject(i)
                newNodes.add(
                    MemoryNodeEntity(
                        serverInsightId = item.optLong("id"),
                        insight = item.optString("insight"),
                        emotionalShiftJson = item.optJSONObject("emotional_shift")?.toString() ?: "{}",
                        worldDeltaJson = item.optJSONObject("world_delta")?.toString() ?: "{}",
                        timestamp = item.optLong("timestamp", System.currentTimeMillis())
                    )
                )
            }

            if (newNodes.isNotEmpty()) {
                memoryNodeDao.insertAll(newNodes)
            }

            Result.success(
                SyncSummary(
                    pushedCount = pushedTelemetryCount,
                    pulledCount = newNodes.size,
                    conversationCount = pushedTurnCount,
                    coreState = coreState
                )
            )
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Pulls active session context from PC Throne for zero-amnesia resume on mobile.
     */
    suspend fun syncActiveSession(client: ThroneClient): Result<Int> = withContext(Dispatchers.IO) {
        val result = client.fetchActiveSession()
        if (result.isFailure) {
            return@withContext Result.failure(result.exceptionOrNull()!!)
        }

        try {
            val responseJson = JSONObject(result.getOrThrow())
            val sessionObj = responseJson.optJSONObject("session") ?: return@withContext Result.success(0)
            val turnsArray = sessionObj.optJSONArray("recent_turns") ?: JSONArray()

            val entities = mutableListOf<ConversationEntity>()
            for (i in 0 until turnsArray.length()) {
                val turn = turnsArray.getJSONObject(i)
                entities.add(
                    ConversationEntity(
                        serverTurnId = turn.optLong("turn_id"),
                        userInput = turn.optString("user_input"),
                        thoughtStream = turn.optString("thought_stream"),
                        finalResponse = turn.optString("final_response"),
                        sourceDevice = turn.optString("source_device", "pc"),
                        affectStateJson = turn.optJSONObject("affect_state")?.toString() ?: "{}",
                        timestamp = turn.optLong("timestamp", System.currentTimeMillis()),
                        isSynced = true
                    )
                )
            }

            if (entities.isNotEmpty()) {
                conversationDao.insertAll(entities)
            }
            Result.success(entities.size)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
