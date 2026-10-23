package com.brainuke.serenitydroid.service

import kotlinx.coroutines.*
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

/**
 * Manages incremental idle timer intervals for Cecilia's volition and sensory interest checks.
 * Progression: 1st=5m, 2nd=10m, 3rd=15m, 4th=30m, 5th=45m, 6th+=60m (hourly).
 */
class IdleVolitionScheduler(
    private val scope: CoroutineScope,
    private val onIdleTick: suspend (step: Int, intervalMs: Long) -> Unit
) {
    companion object {
        val IDLE_INTERVALS_MS = listOf(
            5 * 60 * 1000L,   // 1st: 5 min
            10 * 60 * 1000L,  // 2nd: 10 min
            15 * 60 * 1000L,  // 3rd: 15 min
            30 * 60 * 1000L,  // 4th: 30 min
            45 * 60 * 1000L,  // 5th: 45 min
            60 * 60 * 1000L   // 6th+: 60 min (hourly)
        )
    }

    private val currentStep = AtomicInteger(0)
    private val lastActivityTime = AtomicLong(System.currentTimeMillis())
    private var timerJob: Job? = null

    fun recordActivity() {
        lastActivityTime.set(System.currentTimeMillis())
        currentStep.set(0)
        restartTimer()
    }

    fun start() {
        restartTimer()
    }

    fun stop() {
        timerJob?.cancel()
        timerJob = null
    }

    private fun restartTimer() {
        timerJob?.cancel()
        timerJob = scope.launch(Dispatchers.Default) {
            while (isActive) {
                val step = currentStep.get()
                val intervalMs = IDLE_INTERVALS_MS.getOrElse(step) { IDLE_INTERVALS_MS.last() }
                delay(intervalMs)

                val stepExecuted = currentStep.getAndIncrement()
                onIdleTick(stepExecuted + 1, intervalMs)
            }
        }
    }

    fun getCurrentIntervalMs(): Long {
        val step = currentStep.get()
        return IDLE_INTERVALS_MS.getOrElse(step) { IDLE_INTERVALS_MS.last() }
    }

    fun getCurrentStep(): Int = currentStep.get()

    fun getLastActivityTime(): Long = lastActivityTime.get()
}
