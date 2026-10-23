package com.brainuke.serenitydroid.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface TelemetryDao {
    @Insert
    suspend fun insert(item: TelemetryEntity): Long

    @Query("SELECT * FROM telemetry_logs WHERE isSynced = 0 ORDER BY timestamp ASC LIMIT :limit")
    suspend fun getUnsynced(limit: Int = 100): List<TelemetryEntity>

    @Query("UPDATE telemetry_logs SET isSynced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<Long>)

    @Query("DELETE FROM telemetry_logs WHERE isSynced = 1 AND timestamp < :olderThanEpochMs")
    suspend fun pruneOld(olderThanEpochMs: Long)

    @Query("SELECT COUNT(*) FROM telemetry_logs WHERE isSynced = 0")
    fun observePendingCount(): Flow<Int>
}

@Dao
interface MemoryNodeDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(items: List<MemoryNodeEntity>)

    @Query("SELECT * FROM memory_nodes ORDER BY timestamp DESC")
    fun observeAll(): Flow<List<MemoryNodeEntity>>

    @Query("SELECT MAX(timestamp) FROM memory_nodes")
    suspend fun getLatestTimestamp(): Long?

    @Query("SELECT MAX(serverInsightId) FROM memory_nodes")
    suspend fun getLatestServerInsightId(): Long?

    @Query("SELECT * FROM memory_nodes ORDER BY timestamp DESC LIMIT :limit")
    suspend fun getRecentNodes(limit: Int = 10): List<MemoryNodeEntity>
}

@Dao
interface ConversationDao {
    @Insert
    suspend fun insert(turn: ConversationEntity): Long

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(turns: List<ConversationEntity>)

    @Query("SELECT * FROM conversation_turns WHERE isSynced = 0 ORDER BY timestamp ASC LIMIT :limit")
    suspend fun getUnsynced(limit: Int = 50): List<ConversationEntity>

    @Query("UPDATE conversation_turns SET isSynced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<Long>)

    @Query("SELECT * FROM conversation_turns ORDER BY timestamp DESC LIMIT :limit")
    fun observeRecentTurns(limit: Int = 20): Flow<List<ConversationEntity>>

    @Query("SELECT * FROM conversation_turns ORDER BY timestamp DESC LIMIT :limit")
    suspend fun getRecentTurns(limit: Int = 20): List<ConversationEntity>

    @Query("SELECT MAX(serverTurnId) FROM conversation_turns WHERE sourceDevice = 'pc'")
    suspend fun getLatestServerTurnId(): Long?
}

@Dao
interface FailedPromptDao {
    @Insert
    suspend fun insert(prompt: FailedPromptEntity): Long

    @Query("SELECT * FROM failed_prompt_buffer WHERE status = 'pending' ORDER BY timestamp ASC")
    suspend fun getPendingPrompts(): List<FailedPromptEntity>

    @Query("UPDATE failed_prompt_buffer SET status = :status WHERE id = :id")
    suspend fun updateStatus(id: Long, status: String)

    @Query("UPDATE failed_prompt_buffer SET retryCount = retryCount + 1, failureReason = :reason WHERE id = :id")
    suspend fun recordRetry(id: Long, reason: String)

    @Query("DELETE FROM failed_prompt_buffer WHERE status = 'flushed' AND timestamp < :olderThanEpochMs")
    suspend fun pruneFlushed(olderThanEpochMs: Long)

    @Query("SELECT COUNT(*) FROM failed_prompt_buffer WHERE status = 'pending'")
    fun observePendingCount(): Flow<Int>

    @Query("SELECT COUNT(*) FROM failed_prompt_buffer WHERE status = 'pending'")
    suspend fun getPendingCount(): Int
}
