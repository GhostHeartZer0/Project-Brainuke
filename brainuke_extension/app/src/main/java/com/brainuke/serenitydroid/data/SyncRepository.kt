package com.brainuke.serenitydroid.data

import com.brainuke.serenitydroid.model.TelemetryPayload
import com.brainuke.serenitydroid.network.ThroneClient
import com.brainuke.serenitydroid.util.MessageBoardCrypto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.sync.Mutex
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
    private val failedPromptDao = database.failedPromptDao()
    private val syncMutex = Mutex()

    /**
     * Caches an unanswered prompt into the failed_prompt_buffer SQLite queue.
     */
    suspend fun queueFailedPrompt(
        promptText: String,
        targetMode: String = "throne",
        failureReason: String = ""
    ): Long = withContext(Dispatchers.IO) {
        val entity = FailedPromptEntity(
            promptText = promptText,
            targetMode = targetMode,
            failureReason = failureReason,
            timestamp = System.currentTimeMillis(),
            status = "pending"
        )
        failedPromptDao.insert(entity)
    }

    suspend fun getPendingFailedPrompts(): List<FailedPromptEntity> = withContext(Dispatchers.IO) {
        failedPromptDao.getPendingPrompts()
    }

    suspend fun markFailedPromptStatus(id: Long, status: String) = withContext(Dispatchers.IO) {
        failedPromptDao.updateStatus(id, status)
    }

    suspend fun recordFailedPromptRetry(id: Long, reason: String) = withContext(Dispatchers.IO) {
        failedPromptDao.recordRetry(id, reason)
    }

    fun observePendingFailedPromptCount(): Flow<Int> =
        failedPromptDao.observePendingCount()

    suspend fun getPendingFailedPromptCount(): Int = withContext(Dispatchers.IO) {
        failedPromptDao.getPendingCount()
    }

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
     * Fetches recent distilled memory nodes (simmered insights) from local SQLite database.
     */
    suspend fun getRecentMemoryNodes(limit: Int = 10): List<MemoryNodeEntity> = withContext(Dispatchers.IO) {
        memoryNodeDao.getRecentNodes(limit)
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
     * Guaranteed single-flight via Mutex to prevent concurrency storms.
     * Supports action = "full", "push_only", or "pull_only".
     */
    suspend fun executeSync(
        client: ThroneClient,
        action: String = "full",
        syncId: String? = null
    ): Result<SyncSummary> = withContext(Dispatchers.IO) {
        if (!syncMutex.tryLock()) {
            return@withContext Result.success(
                SyncSummary(
                    pushedCount = 0,
                    pulledCount = 0,
                    conversationCount = 0,
                    coreState = "Sync in progress (locked)"
                )
            )
        }

        try {
            var pushedTelemetryCount = 0
            var pushedTurnCount = 0
            var pulledNodesCount = 0
            var pulledTurnsCount = 0
            var coreState = "Idle"

            // 1. PUSH: Collect unsynced telemetry logs and conversation turns
            if (action == "full" || action == "push_only") {
                val unsyncedTelemetry = telemetryDao.getUnsynced(limit = 100)
                val unsyncedTurns = conversationDao.getUnsynced(limit = 50)

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
                        if (syncId != null) {
                            put("sync_id", syncId)
                        }
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
            }

            // 2. PULL: Check latest sequence IDs and fetch delta pack
            if (action == "full" || action == "pull_only") {
                val latestTimestamp = memoryNodeDao.getLatestTimestamp() ?: 0L
                val latestInsightId = memoryNodeDao.getLatestServerInsightId() ?: 0L
                val latestTurnId = conversationDao.getLatestServerTurnId() ?: 0L

                val pullResult = client.pullSyncDelta(
                    sinceEpochMs = latestTimestamp,
                    sinceInsightId = latestInsightId,
                    sinceTurnId = latestTurnId
                )
                if (pullResult.isFailure) {
                    return@withContext Result.failure(pullResult.exceptionOrNull()!!)
                }

                val pullResponseJson = JSONObject(pullResult.getOrThrow())
                val deltaPack = pullResponseJson.optJSONArray("delta_pack")
                    ?: pullResponseJson.optJSONArray("insights")
                    ?: JSONArray()
                coreState = pullResponseJson.optString("core_state", "Idle")

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
                    pulledNodesCount = newNodes.size
                }

                // Symmetrical Dialogue Pull: Ingest PC conversation turns
                val pcTurns = pullResponseJson.optJSONArray("pc_turns") ?: JSONArray()
                val newTurns = mutableListOf<ConversationEntity>()
                for (i in 0 until pcTurns.length()) {
                    val item = pcTurns.getJSONObject(i)
                    newTurns.add(
                        ConversationEntity(
                            serverTurnId = item.optLong("id"),
                            turnUuid = item.optString("turn_uuid", "turn_pc_${item.optLong("id")}"),
                            userInput = item.optString("user_input"),
                            thoughtStream = item.optString("thought_stream", ""),
                            finalResponse = item.optString("final_response", ""),
                            sourceDevice = item.optString("source_device", "pc"),
                            affectStateJson = item.optJSONObject("affect_state")?.toString() ?: "{}",
                            timestamp = item.optLong("timestamp", System.currentTimeMillis()),
                            isSynced = true
                        )
                    )
                }

                if (newTurns.isNotEmpty()) {
                    conversationDao.insertAll(newTurns)
                    pulledTurnsCount = newTurns.size
                }
            }

            Result.success(
                SyncSummary(
                    pushedCount = pushedTelemetryCount,
                    pulledCount = pulledNodesCount,
                    conversationCount = if (action == "pull_only") pulledTurnsCount else pushedTurnCount,
                    coreState = coreState
                )
            )
        } catch (e: Exception) {
            Result.failure(e)
        } finally {
            syncMutex.unlock()
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
