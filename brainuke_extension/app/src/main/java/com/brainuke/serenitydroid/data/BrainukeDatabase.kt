package com.brainuke.serenitydroid.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [TelemetryEntity::class, MemoryNodeEntity::class, ConversationEntity::class],
    version = 2,
    exportSchema = false
)
abstract class BrainukeDatabase : RoomDatabase() {

    abstract fun telemetryDao(): TelemetryDao
    abstract fun memoryNodeDao(): MemoryNodeDao
    abstract fun conversationDao(): ConversationDao

    companion object {
        @Volatile
        private var INSTANCE: BrainukeDatabase? = null

        fun getDatabase(context: Context): BrainukeDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    BrainukeDatabase::class.java,
                    "serenity_droid_master.db"
                ).fallbackToDestructiveMigration().build()
                INSTANCE = instance
                instance
            }
        }
    }
}
