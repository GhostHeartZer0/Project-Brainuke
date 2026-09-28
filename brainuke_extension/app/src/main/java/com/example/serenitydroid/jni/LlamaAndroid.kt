package com.example.serenitydroid.jni

import android.util.Log

object LlamaAndroid {
    private const val TAG = "LlamaAndroid"
    var isLibraryLoaded: Boolean = false
        private set

    init {
        try {
            System.loadLibrary("c++_shared")
        } catch (e: Throwable) {
            Log.w(TAG, "libc++_shared load note: ${e.message}")
        }
        try {
            System.loadLibrary("omp")
        } catch (e: Throwable) {
            Log.w(TAG, "libomp load note: ${e.message}")
        }
        try {
            System.loadLibrary("serenity_llama")
            isLibraryLoaded = true
            Log.i(TAG, "Successfully loaded libserenity_llama.so in Project Brainuke")
        } catch (e: Throwable) {
            isLibraryLoaded = false
            Log.e(TAG, "Failed to load libserenity_llama.so: ${e.message}")
        }
    }

    external fun loadModel(
        modelPath: String, 
        nGpuLayers: Int, 
        nContext: Int, 
        nThreads: Int, 
        mmprojPath: String? = null,
        kvQuantK: Int = 1,
        kvQuantV: Int = 1,
        flashAttn: Int = 0,
        backendHint: String? = null
    ): Int

    external fun unloadModel()
    external fun deinitBackend()
    external fun isModelLoaded(): Boolean
    external fun getModelContextLength(): Int
    external fun getBackendName(): String
    external fun completion_init(
        prompt: String,
        temp: Float = 0.7f,
        topK: Int = 40,
        topP: Float = 0.9f,
        minP: Float = 0.05f,
        penaltyRepeat: Float = 1.1f,
        penaltyFreq: Float = 0.0f,
        penaltyPresent: Float = 0.0f
    )
    external fun completion_loop(): String
    external fun autoSelectLevelForPrompt(prompt: String): Int
    external fun initWakeWord()
    external fun processAudioForWakeWord(audioData: ShortArray): Boolean
    external fun setThreadAffinity()
}
