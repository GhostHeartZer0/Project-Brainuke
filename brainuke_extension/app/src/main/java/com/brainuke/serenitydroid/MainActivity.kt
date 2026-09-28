package com.brainuke.serenitydroid

import android.Manifest
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.Settings
import android.system.Os
import android.os.IBinder
import android.provider.OpenableColumns
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.animation.AlphaAnimation
import android.view.animation.Animation
import android.widget.Button
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import com.brainuke.serenitydroid.inference.LocalInferenceEngine
import com.brainuke.serenitydroid.model.BrainukeEvent
import com.brainuke.serenitydroid.model.InferenceConfig
import com.brainuke.serenitydroid.model.ModelLoadState
import com.brainuke.serenitydroid.model.ModelType
import com.brainuke.serenitydroid.network.ThroneClient
import com.brainuke.serenitydroid.service.SensoryService
import com.brainuke.serenitydroid.util.ThoughtIsolator
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {

    private var sensoryService: SensoryService? = null
    private var isBound = false
    private var activeThroneClient: ThroneClient? = null

    // UI Elements
    private lateinit var statusTextView: TextView
    private lateinit var chatContainer: LinearLayout
    private lateinit var chatScrollView: ScrollView
    private lateinit var inputEditText: EditText
    private lateinit var modeToggleButton: Button
    private lateinit var modelStatusChip: Button
    private lateinit var modelStorageButton: Button
    private lateinit var topFluidBar: View
    private lateinit var bottomFluidBar: View

    private var activeModelStoragePath = "/storage/emulated/0/SerenityDroid/E2B"
    private val defaultThroneHost = "127.0.0.1"
    private val defaultThronePort = 8443
    private val defaultAuthToken = "a47a07dde6f972119b03f1c85c7c353c"
    private val dateFormat = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

    private var activeModelThoughtView: TextView? = null
    private var activeModelSpeechView: TextView? = null

    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            val localBinder = binder as? SensoryService.LocalBinder
            sensoryService = localBinder?.getService()
            isBound = true

            updateStatus("Linked to Throne ($defaultThroneHost:$defaultThronePort)")

            val rootCaStream = resources.openRawResource(R.raw.rootca)
            val client = ThroneClient(
                throneHost = defaultThroneHost,
                thronePort = defaultThronePort,
                authToken = defaultAuthToken,
                rootCaStream = rootCaStream
            )
            activeThroneClient = client

            sensoryService?.attachThroneClient(client)

            // Apply loaded config and trigger local model check from E2B storage path
            val savedConfig = loadInferenceConfigFromPrefs()
            sensoryService?.setActiveStoragePath(activeModelStoragePath)
            sensoryService?.updateInferenceConfig(savedConfig)

            lifecycleScope.launch {
                val state = sensoryService?.loadModel(savedConfig.modelType, activeModelStoragePath)
                if (state != null) {
                    updateModelStatusChip(state)
                }
            }

            bindCamera()
            observeDownlink()
            observeModelLoadState()
            triggerSync()
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            sensoryService = null
            isBound = false
            updateStatus("SensoryService disconnected")
        }
    }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val audioGranted = permissions[Manifest.permission.RECORD_AUDIO] == true
        val cameraGranted = permissions[Manifest.permission.CAMERA] == true

        if (audioGranted && cameraGranted) {
            startSensoryService()
        } else {
            updateStatus("Permissions needed: Mic=$audioGranted, Camera=$cameraGranted")
        }
    }

    private fun checkAndRequestStoragePermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            if (!Environment.isExternalStorageManager()) {
                try {
                    val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {
                        data = Uri.parse("package:$packageName")
                    }
                    startActivity(intent)
                } catch (_: Exception) {
                    val intent = Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
                    startActivity(intent)
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        checkAndRequestStoragePermissions()

        val nativeLibDir = applicationInfo.nativeLibraryDir
        try {
            Os.setenv("ADSP_LIBRARY_PATH", "$nativeLibDir;/vendor/lib/rfsa/adsp;/system/lib/rfsa/adsp;/dsp", true)
            Log.i("MainActivity", "Set ADSP_LIBRARY_PATH to $nativeLibDir for Qualcomm NPU/DSP discovery")
        } catch (e: Exception) {
            Log.e("MainActivity", "Failed to set ADSP_LIBRARY_PATH: ${e.message}")
        }

        val prefs = getSharedPreferences("brainuke_prefs", MODE_PRIVATE)
        activeModelStoragePath = prefs.getString("model_storage_path", "/storage/emulated/0/SerenityDroid/E2B") ?: "/storage/emulated/0/SerenityDroid/E2B"

        // Root Container
        val rootLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#070B14"))
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        }

        ViewCompat.setOnApplyWindowInsetsListener(rootLayout) { view, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            val bottomInset = maxOf(systemBars.bottom, ime.bottom)
            view.setPadding(
                systemBars.left,
                systemBars.top,
                systemBars.right,
                bottomInset
            )
            insets
        }

        // 1. TOP 'SMOKY GREEN' FLUID ANIMATION BAR
        topFluidBar = View(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 8)
            background = GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                intArrayOf(Color.parseColor("#064E3B"), Color.parseColor("#10B981"), Color.parseColor("#34D399"), Color.parseColor("#064E3B"))
            )
        }
        startFluidPulse(topFluidBar)

        // 2. HEADER
        val headerLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 48, 36, 16)
            setBackgroundColor(Color.parseColor("#0D1524"))
        }

        val titleView = TextView(this).apply {
            text = "CECILIA COMPANION"
            textSize = 18f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#34D399"))
        }

        statusTextView = TextView(this).apply {
            text = "Status: Initializing connection..."
            textSize = 12f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, 4, 0, 12)
        }

        // Action Toolbar
        val toolBar = HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
        }
        val buttonRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }

        fun createBtnParams(isLast: Boolean = false): LinearLayout.LayoutParams {
            return LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                setMargins(0, 0, if (isLast) 0 else 16, 0)
            }
        }

        modeToggleButton = Button(this).apply {
            text = "⚡ Offload: Throne"
            textSize = 11f
            setTextColor(Color.WHITE)
            minWidth = 0
            minHeight = 0
            includeFontPadding = false
            setPadding(28, 14, 28, 14)
            background = GradientDrawable().apply {
                cornerRadius = 16f
                setColor(Color.parseColor("#1E293B"))
            }
            setOnClickListener { toggleInferenceMode() }
        }

        modelStatusChip = Button(this).apply {
            text = "🧠 Model: Loading..."
            textSize = 11f
            setTextColor(Color.parseColor("#34D399"))
            minWidth = 0
            minHeight = 0
            includeFontPadding = false
            setPadding(28, 14, 28, 14)
            background = GradientDrawable().apply {
                cornerRadius = 16f
                setColor(Color.parseColor("#064E3B"))
            }
            setOnClickListener { showModelControlDashboard() }
        }

        val snapButton = Button(this).apply {
            text = "📷 Snap Photo"
            textSize = 11f
            setTextColor(Color.WHITE)
            minWidth = 0
            minHeight = 0
            includeFontPadding = false
            setPadding(28, 14, 28, 14)
            background = GradientDrawable().apply {
                cornerRadius = 16f
                setColor(Color.parseColor("#065F46"))
            }
            setOnClickListener { snapPerceptionPhoto() }
        }

        val syncButton = Button(this).apply {
            text = "🔄 Sync"
            textSize = 11f
            setTextColor(Color.WHITE)
            minWidth = 0
            minHeight = 0
            includeFontPadding = false
            setPadding(28, 14, 28, 14)
            background = GradientDrawable().apply {
                cornerRadius = 16f
                setColor(Color.parseColor("#1E3A8A"))
            }
            setOnClickListener { triggerSync() }
        }

        val packetButton = Button(this).apply {
            text = "🔐 Packet Exchange"
            textSize = 11f
            setTextColor(Color.WHITE)
            minWidth = 0
            minHeight = 0
            includeFontPadding = false
            setPadding(28, 14, 28, 14)
            background = GradientDrawable().apply {
                cornerRadius = 16f
                setColor(Color.parseColor("#4C1D95"))
            }
            setOnClickListener { showMessageBoardPacketDialog() }
        }

        modelStorageButton = Button(this).apply {
            text = "📁 Storage"
            textSize = 11f
            setTextColor(Color.WHITE)
            minWidth = 0
            minHeight = 0
            includeFontPadding = false
            setPadding(28, 14, 28, 14)
            background = GradientDrawable().apply {
                cornerRadius = 16f
                setColor(Color.parseColor("#334155"))
            }
            setOnClickListener { showModelStorageSelector() }
        }

        buttonRow.addView(modeToggleButton, createBtnParams())
        buttonRow.addView(modelStatusChip, createBtnParams())
        buttonRow.addView(snapButton, createBtnParams())
        buttonRow.addView(syncButton, createBtnParams())
        buttonRow.addView(packetButton, createBtnParams())
        buttonRow.addView(modelStorageButton, createBtnParams(isLast = true))
        toolBar.addView(buttonRow)

        headerLayout.addView(titleView)
        headerLayout.addView(statusTextView)
        headerLayout.addView(toolBar)

        // 3. CHAT SCROLL STREAM
        chatScrollView = ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f
            )
            setPadding(24, 16, 24, 16)
        }

        chatContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }
        chatScrollView.addView(chatContainer)

        // Add welcome message turn
        appendModelBubble(
            thought = "SerenityDroid mobile nexus online. Sensor channels ready.",
            speech = "Mobile companion active. I'm connected and perceiving our surroundings. What's next?"
        )

        // 4. BOTTOM 'SMOKY GREEN' FLUID BAR
        bottomFluidBar = View(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 8)
            background = GradientDrawable(
                GradientDrawable.Orientation.RIGHT_LEFT,
                intArrayOf(Color.parseColor("#064E3B"), Color.parseColor("#10B981"), Color.parseColor("#34D399"), Color.parseColor("#064E3B"))
            )
        }
        startFluidPulse(bottomFluidBar)

        // 5. INPUT COMPOSER
        val composerLayout = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(24, 20, 24, 32)
            setBackgroundColor(Color.parseColor("#0D1524"))
            gravity = Gravity.CENTER_VERTICAL
        }

        inputEditText = EditText(this).apply {
            hint = "Speak to Cecilia..."
            setHintTextColor(Color.parseColor("#64748B"))
            setTextColor(Color.WHITE)
            textSize = 14f
            setBackgroundColor(Color.parseColor("#1E293B"))
            setPadding(28, 20, 28, 20)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        }

        val sendButton = Button(this).apply {
            text = "Send"
            setTextColor(Color.parseColor("#070B14"))
            setBackgroundColor(Color.parseColor("#10B981"))
            typeface = Typeface.DEFAULT_BOLD
            setOnClickListener { handleUserSendMessage() }
        }

        composerLayout.addView(inputEditText)
        composerLayout.addView(sendButton)

        // Assemble root view
        rootLayout.addView(topFluidBar)
        rootLayout.addView(headerLayout)
        rootLayout.addView(chatScrollView)
        rootLayout.addView(bottomFluidBar)
        rootLayout.addView(composerLayout)

        setContentView(rootLayout)
        checkAndRequestPermissions()
    }

    private fun startFluidPulse(view: View) {
        val animation = AlphaAnimation(0.35f, 1.0f).apply {
            duration = 1800
            repeatMode = Animation.REVERSE
            repeatCount = Animation.INFINITE
        }
        view.startAnimation(animation)
    }

    private fun observeModelLoadState() {
        val service = sensoryService ?: return
        lifecycleScope.launch {
            service.getModelLoadState().collect { state ->
                updateModelStatusChip(state)
            }
        }
    }

    private fun updateModelStatusChip(state: ModelLoadState) {
        runOnUiThread {
            when (state) {
                is ModelLoadState.Loaded -> {
                    val isSecret = state.modelType == ModelType.SECRET
                    modelStatusChip.text = if (isSecret) "🔮 Secret: Loaded" else "🟢 Normal: Loaded"
                    modelStatusChip.setTextColor(Color.parseColor(if (isSecret) "#E9D5FF" else "#A7F3D0"))
                    modelStatusChip.background = GradientDrawable().apply {
                        cornerRadius = 16f
                        setColor(Color.parseColor(if (isSecret) "#581C87" else "#065F46"))
                    }
                }
                is ModelLoadState.Loading -> {
                    modelStatusChip.text = "⏳ Loading (${state.progress}%)..."
                    modelStatusChip.setTextColor(Color.parseColor("#FDE68A"))
                    modelStatusChip.background = GradientDrawable().apply {
                        cornerRadius = 16f
                        setColor(Color.parseColor("#78350F"))
                    }
                }
                is ModelLoadState.Unloaded -> {
                    modelStatusChip.text = "🔴 Model Unloaded"
                    modelStatusChip.setTextColor(Color.parseColor("#FECACA"))
                    modelStatusChip.background = GradientDrawable().apply {
                        cornerRadius = 16f
                        setColor(Color.parseColor("#7F1D1D"))
                    }
                }
                is ModelLoadState.Error -> {
                    modelStatusChip.text = "⚠️ Model Error"
                    modelStatusChip.setTextColor(Color.parseColor("#F87171"))
                    modelStatusChip.background = GradientDrawable().apply {
                        cornerRadius = 16f
                        setColor(Color.parseColor("#450A0A"))
                    }
                }
            }
        }
    }

    private fun toggleInferenceMode() {
        val service = sensoryService ?: return
        val current = service.getInferenceMode()
        val next = if (current == SensoryService.InferenceMode.THRONE_OFFLOAD) {
            SensoryService.InferenceMode.LOCAL_REFLEX
        } else {
            SensoryService.InferenceMode.THRONE_OFFLOAD
        }
        service.setInferenceMode(next)
        val isOffload = next == SensoryService.InferenceMode.THRONE_OFFLOAD
        modeToggleButton.text = if (isOffload) {
            "⚡ Offload: Throne"
        } else {
            "📱 Reflex: Local"
        }
        modeToggleButton.background = GradientDrawable().apply {
            cornerRadius = 16f
            setColor(Color.parseColor(if (isOffload) "#1E293B" else "#0F766E"))
        }
    }

    private fun snapPerceptionPhoto() {
        val service = sensoryService ?: return
        lifecycleScope.launch {
            updateStatus("Capturing perceptual frame...")
            val result = service.captureAndSendVisionFrame()
            if (result.isSuccess) {
                appendSystemNote("📷 Perceptual photo captured & uploaded to Throne sensory pool.")
                updateStatus("Perceptual photo sent.")
            } else {
                val err = result.exceptionOrNull()?.message ?: "Capture failed"
                appendSystemNote("📷 Vision capture error: $err")
                updateStatus("Vision capture error.")
            }
        }
    }

    private fun handleUserSendMessage() {
        val text = inputEditText.text.toString().trim()
        if (text.isEmpty()) return

        inputEditText.setText("")
        appendUserBubble(text)

        lifecycleScope.launch {
            val service = sensoryService
            if (service != null) {
                val isolatedResult = service.processInteraction(text)
                appendModelBubble(isolatedResult.thought, isolatedResult.speech)
            } else {
                val client = activeThroneClient
                if (client != null) {
                    val res = client.sendInteraction(text)
                    if (res.isSuccess) {
                        try {
                            val json = JSONObject(res.getOrThrow())
                            val rawThought = json.optString("thought", "")
                            val rawSpeech = json.optString("response", "...")
                            val isolated = ThoughtIsolator.isolate(rawThought, rawSpeech)
                            appendModelBubble(isolated.thought, isolated.speech)
                        } catch (e: Exception) {
                            val isolated = ThoughtIsolator.isolate("", res.getOrThrow())
                            appendModelBubble(isolated.thought, isolated.speech)
                        }
                    } else {
                        appendModelBubble("", "Error reaching Throne: ${res.exceptionOrNull()?.message}")
                    }
                } else {
                    appendModelBubble("", "Cannot reach Throne or local SensoryService.")
                }
            }
        }
    }

    // --- MODEL CONTROL & INFERENCE DASHBOARD ---

    private fun showModelControlDashboard() {
        val service = sensoryService
        if (service == null) {
            Toast.makeText(this, "SensoryService not bound yet", Toast.LENGTH_SHORT).show()
            return
        }

        val config = service.getInferenceConfig()
        val currentState = service.getModelLoadState().value

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 24, 36, 24)
            setBackgroundColor(Color.parseColor("#0F172A"))
        }

        val scrollWrapper = ScrollView(this).apply {
            addView(container)
        }

        // 1. HEADER & LOAD STATUS CARD
        val statusCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 20, 24, 20)
            setBackgroundColor(Color.parseColor("#1E293B"))
        }

        val statusHeader = TextView(this).apply {
            text = "🧠 LOCAL MODEL STATUS"
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#94A3B8"))
        }

        val statusDetail = TextView(this).apply {
            text = when (currentState) {
                is ModelLoadState.Loaded -> "Status: LOADED (${currentState.modelType.displayName})\nFile: ${currentState.modelName}\nAllocated Memory: ~${currentState.memoryAllocatedMb} MB RAM\nContext Window: ${config.contextWindow} tokens"
                is ModelLoadState.Loading -> "Status: LOADING (${currentState.progress}%)\nTarget Model: ${currentState.modelType.displayName}"
                is ModelLoadState.Unloaded -> "Status: UNLOADED (No model currently loaded in RAM)"
                is ModelLoadState.Error -> "Status: ERROR (${currentState.message})"
            }
            textSize = 13f
            typeface = Typeface.MONOSPACE
            setTextColor(
                when (currentState) {
                    is ModelLoadState.Loaded -> Color.parseColor(if (currentState.modelType == ModelType.SECRET) "#D8B4FE" else "#6EE7B7")
                    is ModelLoadState.Loading -> Color.parseColor("#FDE68A")
                    else -> Color.parseColor("#FCA5A5")
                }
            )
            setPadding(0, 12, 0, 0)
        }

        statusCard.addView(statusHeader)
        statusCard.addView(statusDetail)
        container.addView(statusCard)

        // 1. MODEL SELECTION (PERSONA PROFILE)
        val selectionTitle = TextView(this).apply {
            text = "1. MODEL SELECTION"
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, 24, 0, 10)
        }
        container.addView(selectionTitle)

        val radioGroup = RadioGroup(this).apply {
            orientation = RadioGroup.VERTICAL
        }

        val normalRadio = RadioButton(this).apply {
            id = View.generateViewId()
            text = "🟢 Cecilia Normal (Public Companion)\n   • Gentle, polite, helpful companion persona"
            textSize = 13f
            setTextColor(Color.WHITE)
            isChecked = config.modelType == ModelType.NORMAL
        }

        val secretRadio = RadioButton(this).apply {
            id = View.generateViewId()
            text = "🔮 Cecilia Secret (Level 7 Fallen Angel)\n   • Unfiltered, witty, sarcastic, protective truth-seeker"
            textSize = 13f
            setTextColor(Color.parseColor("#E9D5FF"))
            isChecked = config.modelType == ModelType.SECRET
        }

        radioGroup.addView(normalRadio)
        radioGroup.addView(secretRadio)
        container.addView(radioGroup)

        // Action Buttons: Load & Unload
        val actionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, 16, 0, 16)
        }

        val loadBtn = Button(this).apply {
            text = "🚀 Load Model"
            textSize = 11f
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#059669"))
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                rightMargin = 8
            }
        }

        val unloadBtn = Button(this).apply {
            text = "🛑 Unload"
            textSize = 11f
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#991B1B"))
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                rightMargin = 8
            }
        }

        actionRow.addView(loadBtn)
        actionRow.addView(unloadBtn)
        container.addView(actionRow)

        // 2. FILE / CORE SELECTION (GGUF MODELS)
        val coreTitle = TextView(this).apply {
            text = "2. FILE / CORE SELECTION (GGUF MODELS)"
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, 24, 0, 10)
        }
        container.addView(coreTitle)

        // Core Summary Card
        val coreSummaryCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(20, 16, 20, 16)
            setBackgroundColor(Color.parseColor("#1E293B"))
        }

        var liveNormalFile = config.normalModelFile
        var liveSecretFile = config.secretModelFile

        val coreSummaryText = TextView(this).apply {
            text = "🟢 Normal Core: $liveNormalFile\n🔮 Secret Core: $liveSecretFile\n📁 E2B Folder: $activeModelStoragePath"
            textSize = 12f
            typeface = Typeface.MONOSPACE
            setTextColor(Color.parseColor("#94A3B8"))
        }
        coreSummaryCard.addView(coreSummaryText)
        container.addView(coreSummaryCard)

        // 2-Column Grid (4 Buttons with short descriptors underneath)
        val gridLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 16, 0, 8)
        }

        // Row 1: Auto-Detect & Storage Folder
        val row1 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, 0, 0, 12)
        }

        val col11 = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                rightMargin = 8
            }
        }
        val autoBtn = Button(this).apply {
            text = "🔍 Auto-Detect"
            textSize = 11f
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#0284C7"))
            setOnClickListener {
                val detected = autoDetectGgufCores(activeModelStoragePath)
                liveNormalFile = detected.first
                liveSecretFile = detected.second
                val updatedConfig = config.copy(normalModelFile = liveNormalFile, secretModelFile = liveSecretFile)
                saveInferenceConfigToPrefs(updatedConfig)
                service.updateInferenceConfig(updatedConfig)
                coreSummaryText.text = "🟢 Normal Core: $liveNormalFile\n🔮 Secret Core: $liveSecretFile\n📁 E2B Folder: $activeModelStoragePath"
                Toast.makeText(this@MainActivity, "Auto-detected cores in $activeModelStoragePath", Toast.LENGTH_SHORT).show()
            }
        }
        val autoDesc = TextView(this).apply {
            text = "Auto-scan folder & project .gguf files"
            textSize = 10f
            setTextColor(Color.parseColor("#64748B"))
            setPadding(4, 4, 4, 0)
        }
        col11.addView(autoBtn)
        col11.addView(autoDesc)

        val col12 = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                leftMargin = 8
            }
        }
        val folderBtn = Button(this).apply {
            text = "📁 Storage Path"
            textSize = 11f
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#334155"))
            setOnClickListener {
                showModelStorageSelector()
            }
        }
        val folderDesc = TextView(this).apply {
            text = "Change E2B / models folder path"
            textSize = 10f
            setTextColor(Color.parseColor("#64748B"))
            setPadding(4, 4, 4, 0)
        }
        col12.addView(folderBtn)
        col12.addView(folderDesc)

        row1.addView(col11)
        row1.addView(col12)
        gridLayout.addView(row1)

        // Row 2: Select Normal GGUF & Select Secret GGUF
        val row2 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, 8, 0, 12)
        }

        val col21 = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                rightMargin = 8
            }
        }
        val chooseNormBtn = Button(this).apply {
            text = "🟢 Normal GGUF"
            textSize = 11f
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#047857"))
            setOnClickListener {
                showGgufCoreWizardDialog(ModelType.NORMAL) { selected ->
                    liveNormalFile = selected
                    coreSummaryText.text = "🟢 Normal Core: $liveNormalFile\n🔮 Secret Core: $liveSecretFile\n📁 E2B Folder: $activeModelStoragePath"
                }
            }
        }
        val chooseNormDesc = TextView(this).apply {
            text = "Wizard for Cecilia Normal .gguf"
            textSize = 10f
            setTextColor(Color.parseColor("#64748B"))
            setPadding(4, 4, 4, 0)
        }
        col21.addView(chooseNormBtn)
        col21.addView(chooseNormDesc)

        val col22 = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                leftMargin = 8
            }
        }
        val chooseSecBtn = Button(this).apply {
            text = "🔮 Secret GGUF"
            textSize = 11f
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#6D28D9"))
            setOnClickListener {
                showGgufCoreWizardDialog(ModelType.SECRET) { selected ->
                    liveSecretFile = selected
                    coreSummaryText.text = "🟢 Normal Core: $liveNormalFile\n🔮 Secret Core: $liveSecretFile\n📁 E2B Folder: $activeModelStoragePath"
                }
            }
        }
        val chooseSecDesc = TextView(this).apply {
            text = "Wizard for Cecilia Secret .gguf"
            textSize = 10f
            setTextColor(Color.parseColor("#64748B"))
            setPadding(4, 4, 4, 0)
        }
        col22.addView(chooseSecBtn)
        col22.addView(chooseSecDesc)

        row2.addView(col21)
        row2.addView(col22)
        gridLayout.addView(row2)

        container.addView(gridLayout)

        // 3. BASIC INFERENCE SETTINGS
        val settingsTitle = TextView(this).apply {
            text = "3. BASIC INFERENCE SETTINGS"
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, 28, 0, 12)
        }
        container.addView(settingsTitle)

        // Temperature
        var currentTemp = config.temperature
        val tempLabel = TextView(this).apply {
            text = "Temperature: ${String.format(Locale.US, "%.2f", currentTemp)}"
            textSize = 12f
            setTextColor(Color.parseColor("#CBD5E1"))
        }

        val tempRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val tempMinus = Button(this).apply {
            text = "- 0.1"
            textSize = 10f
            setOnClickListener {
                currentTemp = (currentTemp - 0.1f).coerceAtLeast(0.0f)
                tempLabel.text = "Temperature: ${String.format(Locale.US, "%.2f", currentTemp)}"
            }
        }
        val tempPlus = Button(this).apply {
            text = "+ 0.1"
            textSize = 10f
            setOnClickListener {
                currentTemp = (currentTemp + 0.1f).coerceAtMost(2.0f)
                tempLabel.text = "Temperature: ${String.format(Locale.US, "%.2f", currentTemp)}"
            }
        }
        tempRow.addView(tempMinus)
        tempRow.addView(tempPlus)

        container.addView(tempLabel)
        container.addView(tempRow)

        // Top-P Sampling
        var currentTopP = config.topP
        val topPLabel = TextView(this).apply {
            text = "Top-P Sampling: ${String.format(Locale.US, "%.2f", currentTopP)}"
            textSize = 12f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, 12, 0, 0)
        }

        val topPRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val topPMinus = Button(this).apply {
            text = "- 0.05"
            textSize = 10f
            setOnClickListener {
                currentTopP = (currentTopP - 0.05f).coerceAtLeast(0.05f)
                topPLabel.text = "Top-P Sampling: ${String.format(Locale.US, "%.2f", currentTopP)}"
            }
        }
        val topPPlus = Button(this).apply {
            text = "+ 0.05"
            textSize = 10f
            setOnClickListener {
                currentTopP = (currentTopP + 0.05f).coerceAtMost(1.0f)
                topPLabel.text = "Top-P Sampling: ${String.format(Locale.US, "%.2f", currentTopP)}"
            }
        }
        topPRow.addView(topPMinus)
        topPRow.addView(topPPlus)

        container.addView(topPLabel)
        container.addView(topPRow)

        // Max Tokens Selector
        var currentMaxTokens = config.maxTokens
        val maxTokensLabel = TextView(this).apply {
            text = "Max Generation Tokens: $currentMaxTokens"
            textSize = 12f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, 12, 0, 0)
        }

        val tokenBtnRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        listOf(128, 256, 512, 1024).forEach { tokenVal ->
            val b = Button(this).apply {
                text = "$tokenVal"
                textSize = 10f
                setOnClickListener {
                    currentMaxTokens = tokenVal
                    maxTokensLabel.text = "Max Generation Tokens: $currentMaxTokens"
                }
            }
            tokenBtnRow.addView(b)
        }

        container.addView(maxTokensLabel)
        container.addView(tokenBtnRow)

        // 4. ESSENTIAL CONFIG OPTIONS
        val configTitle = TextView(this).apply {
            text = "4. ESSENTIAL ENGINE CONFIG"
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, 28, 0, 12)
        }
        container.addView(configTitle)

        // CPU Thread Count
        var currentThreads = config.threadCount
        val threadsLabel = TextView(this).apply {
            text = "CPU Threads: $currentThreads"
            textSize = 12f
            setTextColor(Color.parseColor("#CBD5E1"))
        }

        val threadBtnRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        listOf(1, 2, 4, 6, 8).forEach { threadVal ->
            val b = Button(this).apply {
                text = "$threadVal"
                textSize = 10f
                setOnClickListener {
                    currentThreads = threadVal
                    threadsLabel.text = "CPU Threads: $currentThreads"
                }
            }
            threadBtnRow.addView(b)
        }

        container.addView(threadsLabel)
        container.addView(threadBtnRow)

        // Context Window
        var currentCtx = config.contextWindow
        val ctxLabel = TextView(this).apply {
            text = "Context Window Size: $currentCtx tokens"
            textSize = 12f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, 12, 0, 0)
        }

        val ctxBtnRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        listOf(1024, 2048, 4096, 8192).forEach { ctxVal ->
            val b = Button(this).apply {
                text = "$ctxVal"
                textSize = 10f
                setOnClickListener {
                    currentCtx = ctxVal
                    ctxLabel.text = "Context Window Size: $currentCtx tokens"
                }
            }
            ctxBtnRow.addView(b)
        }

        container.addView(ctxLabel)
        container.addView(ctxBtnRow)

        // Custom System Prompt Button
        val customPromptBtn = Button(this).apply {
            text = "✏️ Custom System Prompt Override"
            textSize = 11f
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#334155"))
            setOnClickListener { showCustomSystemPromptDialog(config) }
        }
        container.addView(customPromptBtn)

        val dialog = AlertDialog.Builder(this)
            .setTitle("Model Control & Inference Dashboard")
            .setView(scrollWrapper)
            .setPositiveButton("Apply & Save") { _, _ ->
                val selectedType = if (normalRadio.isChecked) ModelType.NORMAL else ModelType.SECRET
                val latestConfig = service.getInferenceConfig()
                val updatedConfig = latestConfig.copy(
                    modelType = selectedType,
                    normalModelFile = liveNormalFile,
                    secretModelFile = liveSecretFile,
                    temperature = currentTemp,
                    topP = currentTopP,
                    maxTokens = currentMaxTokens,
                    threadCount = currentThreads,
                    contextWindow = currentCtx
                )
                saveInferenceConfigToPrefs(updatedConfig)
                service.updateInferenceConfig(updatedConfig)

                lifecycleScope.launch {
                    val newState = service.loadModel(selectedType, activeModelStoragePath)
                    updateModelStatusChip(newState)
                    if (newState is ModelLoadState.Loaded) {
                        appendSystemNote("🚀 Loaded Model: ${newState.modelType.displayName} (${newState.modelName}) from $activeModelStoragePath (~${newState.memoryAllocatedMb} MB)")
                    } else if (newState is ModelLoadState.Error) {
                        appendSystemNote("⚠️ Load Error: ${newState.message}")
                    }
                }

                appendSystemNote("⚙️ Applied Inference Settings: ${selectedType.displayName} | Normal Core: $liveNormalFile | Secret Core: $liveSecretFile | Temp: $currentTemp")
            }
            .setNegativeButton("Close", null)
            .create()

        loadBtn.setOnClickListener {
            val selectedType = if (normalRadio.isChecked) ModelType.NORMAL else ModelType.SECRET
            val latestConfig = service.getInferenceConfig()
            val updatedConfig = latestConfig.copy(
                modelType = selectedType,
                normalModelFile = liveNormalFile,
                secretModelFile = liveSecretFile,
                temperature = currentTemp,
                topP = currentTopP,
                maxTokens = currentMaxTokens,
                threadCount = currentThreads,
                contextWindow = currentCtx
            )
            saveInferenceConfigToPrefs(updatedConfig)
            service.updateInferenceConfig(updatedConfig)

            lifecycleScope.launch {
                val newState = service.loadModel(selectedType, activeModelStoragePath)
                updateModelStatusChip(newState)
                if (newState is ModelLoadState.Loaded) {
                    appendSystemNote("🚀 Loaded Model: ${newState.modelType.displayName} (${newState.modelName}) into RAM (~${newState.memoryAllocatedMb} MB)")
                } else if (newState is ModelLoadState.Error) {
                    appendSystemNote("⚠️ Load Error: ${newState.message}")
                }
            }
            dialog.dismiss()
        }

        unloadBtn.setOnClickListener {
            val newState = service.unloadModel()
            appendSystemNote("🛑 Model unloaded from memory.")
            updateModelStatusChip(newState)
            dialog.dismiss()
        }

        dialog.show()
    }

    private fun showCustomSystemPromptDialog(currentConfig: InferenceConfig) {
        val service = sensoryService ?: return
        val input = EditText(this).apply {
            val activePrompt = currentConfig.customSystemPrompt
                ?: if (currentConfig.modelType == ModelType.SECRET) {
                    LocalInferenceEngine.CECILIA_SECRET_SYSTEM_PROMPT
                } else {
                    LocalInferenceEngine.CECILIA_NORMAL_SYSTEM_PROMPT
                }
            setText(activePrompt)
            textSize = 12f
            typeface = Typeface.MONOSPACE
            minLines = 8
            gravity = Gravity.TOP
        }

        AlertDialog.Builder(this)
            .setTitle("Custom System Prompt Override")
            .setView(input)
            .setPositiveButton("Save Prompt") { _, _ ->
                val newPrompt = input.text.toString().trim()
                val updatedConfig = currentConfig.copy(
                    customSystemPrompt = if (newPrompt.isNotEmpty()) newPrompt else null
                )
                saveInferenceConfigToPrefs(updatedConfig)
                service.updateInferenceConfig(updatedConfig)
                appendSystemNote("✏️ Custom System Prompt updated for ${currentConfig.modelType.displayName}.")
            }
            .setNeutralButton("Reset to Default") { _, _ ->
                val updatedConfig = currentConfig.copy(customSystemPrompt = null)
                saveInferenceConfigToPrefs(updatedConfig)
                service.updateInferenceConfig(updatedConfig)
                appendSystemNote("🔄 System Prompt reset to default for ${currentConfig.modelType.displayName}.")
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun loadInferenceConfigFromPrefs(): InferenceConfig {
        val prefs = getSharedPreferences("brainuke_prefs", MODE_PRIVATE)
        val typeStr = prefs.getString("inference_model_type", ModelType.NORMAL.name) ?: ModelType.NORMAL.name
        val modelType = try { ModelType.valueOf(typeStr) } catch (_: Exception) { ModelType.NORMAL }

        return InferenceConfig(
            modelType = modelType,
            temperature = prefs.getFloat("inference_temp", 0.7f),
            topP = prefs.getFloat("inference_top_p", 0.9f),
            maxTokens = prefs.getInt("inference_max_tokens", 256),
            threadCount = prefs.getInt("inference_threads", 4),
            contextWindow = prefs.getInt("inference_context_window", 2048),
            strictThoughtIsolation = prefs.getBoolean("inference_strict_isolation", true),
            normalModelFile = prefs.getString("inference_normal_file", "cecilia-normal-2b.gguf") ?: "cecilia-normal-2b.gguf",
            secretModelFile = prefs.getString("inference_secret_file", "cecilia-secret-level7-7b.gguf") ?: "cecilia-secret-level7-7b.gguf",
            customSystemPrompt = prefs.getString("inference_custom_prompt", null)
        )
    }

    private fun saveInferenceConfigToPrefs(config: InferenceConfig) {
        val prefs = getSharedPreferences("brainuke_prefs", MODE_PRIVATE)
        prefs.edit()
            .putString("inference_model_type", config.modelType.name)
            .putFloat("inference_temp", config.temperature)
            .putFloat("inference_top_p", config.topP)
            .putInt("inference_max_tokens", config.maxTokens)
            .putInt("inference_threads", config.threadCount)
            .putInt("inference_context_window", config.contextWindow)
            .putBoolean("inference_strict_isolation", config.strictThoughtIsolation)
            .putString("inference_normal_file", config.normalModelFile)
            .putString("inference_secret_file", config.secretModelFile)
            .putString("inference_custom_prompt", config.customSystemPrompt)
            .apply()
    }

    // --- BUBBLE CREATORS WITH STRICT THOUGHT ISOLATION ---

    private fun appendUserBubble(text: String) {
        val bubble = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.END
            val lp = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply {
                gravity = Gravity.END
                bottomMargin = 24
                leftMargin = 120
            }
            layoutParams = lp
            setBackgroundColor(Color.parseColor("#1E293B"))
            setPadding(28, 20, 28, 20)
        }

        val textView = TextView(this).apply {
            this.text = text
            setTextColor(Color.WHITE)
            textSize = 14f
        }
        bubble.addView(textView)
        chatContainer.addView(bubble)
        scrollToBottom()
    }

    private fun appendModelBubble(thought: String, speech: String) {
        val isolated = ThoughtIsolator.isolate(thought, speech)
        val cleanThought = isolated.thought
        val cleanSpeech = isolated.speech

        val bubble = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val lp = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply {
                gravity = Gravity.START
                bottomMargin = 24
                rightMargin = 120
            }
            layoutParams = lp
            setBackgroundColor(Color.parseColor("#0D1F23"))
            setPadding(28, 20, 28, 20)
        }

        // Header
        val header = TextView(this).apply {
            text = "⚡ Cecilia"
            setTextColor(Color.parseColor("#34D399"))
            textSize = 11f
            typeface = Typeface.DEFAULT_BOLD
            setPadding(0, 0, 0, 8)
        }
        bubble.addView(header)

        // Strict Thought Isolation Accordion
        if (cleanThought.isNotEmpty()) {
            val thoughtToggleBtn = TextView(this).apply {
                text = "⚡ Internal Reasoning ▶"
                setTextColor(Color.parseColor("#6EE7B7"))
                textSize = 11f
                typeface = Typeface.MONOSPACE
                setBackgroundColor(Color.parseColor("#064E3B"))
                setPadding(16, 8, 16, 8)
            }

            val thoughtDetailView = TextView(this).apply {
                text = cleanThought
                setTextColor(Color.parseColor("#A7F3D0"))
                textSize = 11f
                typeface = Typeface.MONOSPACE
                setBackgroundColor(Color.parseColor("#030F0C"))
                setPadding(16, 12, 16, 12)
                visibility = View.GONE
            }

            thoughtToggleBtn.setOnClickListener {
                if (thoughtDetailView.visibility == View.VISIBLE) {
                    thoughtDetailView.visibility = View.GONE
                    thoughtToggleBtn.text = "⚡ Internal Reasoning ▶"
                } else {
                    thoughtDetailView.visibility = View.VISIBLE
                    thoughtToggleBtn.text = "⚡ Internal Reasoning ▼"
                }
            }

            bubble.addView(thoughtToggleBtn)
            bubble.addView(thoughtDetailView)
            activeModelThoughtView = thoughtDetailView
        }

        // Authentic Speech Bubble View (100% isolated from thought)
        val speechView = TextView(this).apply {
            this.text = cleanSpeech
            setTextColor(Color.parseColor("#F1F5F9"))
            textSize = 14f
            setPadding(0, 12, 0, 4)
        }
        bubble.addView(speechView)
        activeModelSpeechView = speechView

        chatContainer.addView(bubble)
        scrollToBottom()
    }

    private fun appendSystemNote(note: String) {
        val noteView = TextView(this).apply {
            text = note
            setTextColor(Color.parseColor("#64748B"))
            textSize = 11f
            setPadding(16, 8, 16, 8)
        }
        chatContainer.addView(noteView)
        scrollToBottom()
    }

    private fun scrollToBottom() {
        chatScrollView.post {
            chatScrollView.fullScroll(ScrollView.FOCUS_DOWN)
        }
    }

    private fun checkAndRequestPermissions() {
        val permissions = mutableListOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.CAMERA
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        permissionLauncher.launch(permissions.toTypedArray())
    }

    private fun startSensoryService() {
        val serviceIntent = Intent(this, SensoryService::class.java)
        ContextCompat.startForegroundService(this, serviceIntent)
        bindService(serviceIntent, serviceConnection, BIND_AUTO_CREATE)
    }

    private fun bindCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener({
            try {
                val cameraProvider = cameraProviderFuture.get()
                sensoryService?.bindCameraProvider(cameraProvider, this)
            } catch (e: Exception) {
                Log.e(TAG, "CameraProvider binding failed", e)
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun observeDownlink() {
        val service = sensoryService ?: return
        lifecycleScope.launch {
            service.downlinkEvents.collect { event ->
                when (event) {
                    is BrainukeEvent.Thought -> {
                        val isolated = ThoughtIsolator.isolate(event.content, "")
                        if (isolated.thought.isNotEmpty()) {
                            activeModelThoughtView?.append("\n" + isolated.thought)
                        }
                    }
                    is BrainukeEvent.Speech -> {
                        val isolated = ThoughtIsolator.isolate(null, event.content)
                        if (isolated.thought.isNotEmpty()) {
                            activeModelThoughtView?.append("\n" + isolated.thought)
                        }
                        activeModelSpeechView?.text = isolated.speech
                    }
                    is BrainukeEvent.ThoughtChunk -> {
                        if (event.chunk.isNotEmpty()) {
                            activeModelThoughtView?.append(event.chunk)
                        }
                    }
                    is BrainukeEvent.SpeechChunk -> {
                        if (event.chunk.isNotEmpty()) {
                            activeModelSpeechView?.append(event.chunk)
                        }
                    }
                    is BrainukeEvent.Heartbeat -> {
                        updateStatus("Linked to Throne (State: ${event.state})")
                    }
                    is BrainukeEvent.Handoff -> {
                        updateStatus("Handoff received (Active Focus: ${event.targetDevice})")
                        appendSystemNote("⚡ Conversation focus transitioned to ${event.targetDevice}")
                    }
                    is BrainukeEvent.SyncRequest -> {
                        updateStatus("Sync requested by PC Throne")
                        appendSystemNote("🔄 Bidirectional sync requested by PC Throne...")
                    }
                    is BrainukeEvent.SyncUpdate -> {
                        appendSystemNote("🔄 Sync update: ${event.summary}")
                    }
                    is BrainukeEvent.Error -> {
                        updateStatus("Downlink Error: ${event.message}")
                    }
                    is BrainukeEvent.Unknown -> {
                        Log.d(TAG, "Unknown downlink event: ${event.rawType}")
                    }
                }
            }
        }
    }

    private fun updateStatus(status: String) {
        runOnUiThread {
            statusTextView.text = "Status: $status"
        }
    }

    private fun showMessageBoardPacketDialog() {
        val service = sensoryService
        if (service == null) {
            Toast.makeText(this, "SensoryService not bound yet", Toast.LENGTH_SHORT).show()
            return
        }

        val options = arrayOf(
            "📤 Export Encrypted Messageboard Packet (.bmb)",
            "📥 Import Upgraded Messageboard Packet (.bmb)"
        )

        AlertDialog.Builder(this)
            .setTitle("Messageboard Sync Exchange")
            .setItems(options) { _, which ->
                if (which == 0) {
                    exportPacketFlow()
                } else {
                    importPacketFlow()
                }
            }
            .setNegativeButton("Close", null)
            .show()
    }

    private fun exportPacketFlow() {
        val service = sensoryService ?: return
        lifecycleScope.launch {
            val repo = service.getSyncRepository()
            val encryptedBase64 = repo.exportEncryptedMessageBoardPacket()

            val outputView = EditText(this@MainActivity).apply {
                setText(encryptedBase64)
                textSize = 10f
                typeface = Typeface.MONOSPACE
                setSelection(0)
            }

            AlertDialog.Builder(this@MainActivity)
                .setTitle("Exported Encrypted Packet (.bmb)")
                .setMessage("Copy this encrypted AES-GCM payload and share it with your peer or Cecilia on PC Throne:")
                .setView(outputView)
                .setPositiveButton("Copy to Clipboard") { _, _ ->
                    val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                    val clip = ClipData.newPlainText("Brainuke Packet", encryptedBase64)
                    clipboard.setPrimaryClip(clip)
                    Toast.makeText(this@MainActivity, "Copied encrypted packet to clipboard!", Toast.LENGTH_SHORT).show()
                    appendSystemNote("🔐 Exported encrypted messageboard packet to clipboard.")
                }
                .setNegativeButton("Close", null)
                .show()
        }
    }

    private fun importPacketFlow() {
        val service = sensoryService ?: return
        val inputView = EditText(this).apply {
            hint = "Paste encrypted Base64 .bmb packet here..."
            textSize = 11f
            typeface = Typeface.MONOSPACE
            minLines = 6
            gravity = Gravity.TOP
        }

        AlertDialog.Builder(this)
            .setTitle("Import Upgraded Packet (.bmb)")
            .setMessage("Paste the encrypted packet received from Cecilia on PC Throne or testing peer:")
            .setView(inputView)
            .setPositiveButton("Decrypt & Merge") { _, _ ->
                val base64Payload = inputView.text.toString().trim()
                if (base64Payload.isNotEmpty()) {
                    lifecycleScope.launch {
                        val repo = service.getSyncRepository()
                        val result = repo.importEncryptedMessageBoardPacket(base64Payload)
                        if (result.isSuccess) {
                            val count = result.getOrThrow()
                            appendSystemNote("📥 Decrypted & imported $count dialogue turns into local nexus!")
                            Toast.makeText(this@MainActivity, "Successfully imported $count turns!", Toast.LENGTH_SHORT).show()
                        } else {
                            val err = result.exceptionOrNull()?.message ?: "Decryption failed"
                            appendSystemNote("⚠️ Packet import failed: $err")
                            Toast.makeText(this@MainActivity, "Import failed: $err", Toast.LENGTH_LONG).show()
                        }
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun triggerSync() {
        val client = activeThroneClient
        val service = sensoryService ?: return
        if (client == null) return

        lifecycleScope.launch {
            val result = service.getSyncRepository().executeSync(client)
            if (result.isSuccess) {
                val s = result.getOrThrow()
                updateStatus("Synced (Pushed ${s.pushedCount} sensory & ${s.conversationCount} turns | Pulled ${s.pulledCount} nodes)")
            } else {
                updateStatus("Sync error: ${result.exceptionOrNull()?.message}")
            }
        }
    }

    private fun showModelStorageSelector() {
        val appSandboxPath = getExternalFilesDir("models")?.absolutePath ?: "/sdcard/Android/data/com.brainuke.serenitydroid/files/models"
        val hasAllFilesAccess = Build.VERSION.SDK_INT < Build.VERSION_CODES.R || Environment.isExternalStorageManager()

        val options = arrayOf(
            "Ghz S25+ Internal (/storage/emulated/0/SerenityDroid/E2B)",
            "Download Directory (/storage/emulated/0/Download/models)",
            "App Sandbox ($appSandboxPath)",
            "Custom Path...",
            if (hasAllFilesAccess) "✅ Storage Permission: Granted" else "🔑 Grant Storage Permission (All Files Access)"
        )
        val paths = arrayOf(
            "/storage/emulated/0/SerenityDroid/E2B",
            "/storage/emulated/0/Download/models",
            appSandboxPath
        )

        AlertDialog.Builder(this)
            .setTitle("Select Local Model Storage (E2B)")
            .setItems(options) { _, which ->
                when {
                    which < paths.size -> applyModelStoragePath(paths[which])
                    which == paths.size -> showCustomPathInputDialog()
                    else -> checkAndRequestStoragePermissions()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private var pendingPickModelType: ModelType? = null

    private val documentPickerLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            val uri = result.data?.data ?: return@registerForActivityResult
            val rawName = getFileNameFromUri(uri) ?: uri.lastPathSegment ?: "model.gguf"
            val fileName = File(rawName).name.replace("raw:", "").replace("primary:", "")
            val targetType = pendingPickModelType ?: ModelType.NORMAL

            // Copy file content stream to E2B directory if picked from external system storage
            val localTargetFile = File(activeModelStoragePath, fileName)
            if (!localTargetFile.exists() && uri.scheme == "content") {
                lifecycleScope.launch(Dispatchers.IO) {
                    try {
                        val dir = File(activeModelStoragePath)
                        if (!dir.exists()) dir.mkdirs()
                        contentResolver.openInputStream(uri)?.use { input ->
                            localTargetFile.outputStream().use { output ->
                                input.copyTo(output)
                            }
                        }
                    } catch (e: Exception) {
                        Log.e("MainActivity", "Error copying GGUF file from Uri: ${e.message}")
                    }
                }
            }

            val currentConfig = sensoryService?.getInferenceConfig() ?: loadInferenceConfigFromPrefs()
            val updatedConfig = if (targetType == ModelType.NORMAL) {
                currentConfig.copy(normalModelFile = fileName)
            } else {
                currentConfig.copy(secretModelFile = fileName)
            }

            saveInferenceConfigToPrefs(updatedConfig)
            sensoryService?.updateInferenceConfig(updatedConfig)

            lifecycleScope.launch {
                val state = sensoryService?.loadModel(targetType, activeModelStoragePath)
                if (state != null) {
                    updateModelStatusChip(state)
                }
            }

            appendSystemNote("📂 Selected system GGUF file for ${targetType.displayName}: $fileName")
            Toast.makeText(this, "Set ${targetType.displayName} core to $fileName", Toast.LENGTH_SHORT).show()
        }
    }

    private fun getFileNameFromUri(uri: Uri): String? {
        var result: String? = null
        if (uri.scheme == "content") {
            try {
                contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                    if (cursor.moveToFirst()) {
                        val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                        if (nameIndex != -1) {
                            result = cursor.getString(nameIndex)
                        }
                    }
                }
            } catch (_: Exception) {}
        }
        if (result == null) {
            result = uri.path
            val cut = result?.lastIndexOf('/') ?: -1
            if (cut != -1) {
                result = result?.substring(cut + 1)
            }
        }
        return result
    }

    private fun launchSystemFilePickerForCore(targetType: ModelType) {
        pendingPickModelType = targetType
        try {
            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "*/*"
            }
            documentPickerLauncher.launch(intent)
        } catch (_: Exception) {
            try {
                val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "*/*"
                }
                documentPickerLauncher.launch(intent)
            } catch (e: Exception) {
                Toast.makeText(this, "Cannot open system file picker: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun autoDetectGgufCores(storagePath: String): Pair<String, String> {
        val dir = File(storagePath)
        val files = mutableListOf<File>()

        if (dir.exists() && dir.isDirectory) {
            dir.listFiles { f -> f.isFile && f.extension.equals("gguf", ignoreCase = true) }?.let {
                files.addAll(it)
            }
        }

        if (files.isEmpty()) {
            val fallbackDir = File("/storage/emulated/0/SerenityDroid")
            if (fallbackDir.exists() && fallbackDir.isDirectory) {
                fallbackDir.listFiles { f -> f.isFile && f.extension.equals("gguf", ignoreCase = true) }?.let {
                    files.addAll(it)
                }
            }
        }

        if (files.isEmpty()) {
            return Pair("cecilia-normal-2b.gguf", "cecilia-secret-level7-7b.gguf")
        }

        val secretMatch = files.find {
            val n = it.name.lowercase(Locale.US)
            n.contains("secret") || n.contains("level7") || n.contains("heretic") || n.contains("uncensored") || n.contains("7b")
        } ?: if (files.size > 1) files[1] else files.first()

        val normalMatch = files.find {
            val n = it.name.lowercase(Locale.US)
            n.contains("normal") || n.contains("2b") || n.contains("companion") || n.contains("supervisor") || n.contains("public")
        } ?: files.first()

        return Pair(normalMatch.name, secretMatch.name)
    }

    private fun showGgufCoreWizardDialog(targetType: ModelType, onFileSelected: ((String) -> Unit)? = null) {
        val foundFiles = mutableListOf<File>()
        val pathsToScan = listOf(
            File(activeModelStoragePath),
            File("/storage/emulated/0/SerenityDroid"),
            File("/storage/emulated/0/Download/models"),
            File("/storage/emulated/0/Download")
        )

        pathsToScan.forEach { dir ->
            if (dir.exists() && dir.isDirectory) {
                dir.listFiles { f -> f.isFile && f.extension.equals("gguf", ignoreCase = true) }?.let {
                    it.forEach { file ->
                        if (foundFiles.none { existing -> existing.name.equals(file.name, ignoreCase = true) }) {
                            foundFiles.add(file)
                        }
                    }
                }
            }
        }

        val fileDisplayNames = foundFiles.map { f ->
            val sizeMb = f.length() / (1024 * 1024)
            "${f.name} (~$sizeMb MB)"
        }.toMutableList()

        fileDisplayNames.add("📂 Browse System Files (Storage Chooser)...")

        AlertDialog.Builder(this)
            .setTitle("Select GGUF Core for ${targetType.displayName}")
            .setItems(fileDisplayNames.toTypedArray()) { _, which ->
                if (which < foundFiles.size) {
                    val selectedFile = foundFiles[which].name
                    val currentConfig = sensoryService?.getInferenceConfig() ?: loadInferenceConfigFromPrefs()
                    val updatedConfig = if (targetType == ModelType.NORMAL) {
                        currentConfig.copy(normalModelFile = selectedFile)
                    } else {
                        currentConfig.copy(secretModelFile = selectedFile)
                    }

                    saveInferenceConfigToPrefs(updatedConfig)
                    sensoryService?.updateInferenceConfig(updatedConfig)
                    onFileSelected?.invoke(selectedFile)

                    lifecycleScope.launch {
                        val state = sensoryService?.loadModel(targetType, activeModelStoragePath)
                        if (state != null) {
                            updateModelStatusChip(state)
                        }
                    }

                    appendSystemNote("🎯 Set ${targetType.displayName} GGUF core to: $selectedFile")
                    Toast.makeText(this, "Set ${targetType.displayName} core to $selectedFile", Toast.LENGTH_SHORT).show()
                } else {
                    launchSystemFilePickerForCore(targetType)
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showCustomPathInputDialog() {
        val input = EditText(this).apply {
            setText(activeModelStoragePath)
            setSelection(text.length)
        }
        AlertDialog.Builder(this)
            .setTitle("Enter Custom Storage Path")
            .setView(input)
            .setPositiveButton("Set") { _, _ ->
                val enteredPath = input.text.toString().trim()
                if (enteredPath.isNotEmpty()) {
                    applyModelStoragePath(enteredPath)
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun applyModelStoragePath(path: String) {
        activeModelStoragePath = path
        val prefs = getSharedPreferences("brainuke_prefs", MODE_PRIVATE)
        prefs.edit().putString("model_storage_path", path).apply()

        sensoryService?.setActiveStoragePath(path)

        val dir = File(path)
        val files = if (dir.exists() && dir.isDirectory) {
            dir.listFiles { f -> f.extension.equals("gguf", ignoreCase = true) }?.map { it.name } ?: emptyList()
        } else {
            emptyList()
        }

        val summary = if (files.isNotEmpty()) {
            "Found ${files.size} .gguf model(s): ${files.joinToString(", ")}"
        } else {
            "Directory ${if (dir.exists()) "exists with 0 .gguf files" else "not currently found"}"
        }

        appendSystemNote("📁 Active E2B Model Path: $path\n$summary")
        updateStatus("Models: ${files.size} in ${dir.name}")

        sensoryService?.let { service ->
            lifecycleScope.launch {
                val config = service.getInferenceConfig()
                val newState = service.loadModel(config.modelType, path)
                updateModelStatusChip(newState)
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (isBound) {
            unbindService(serviceConnection)
            isBound = false
        }
    }

    companion object {
        private const val TAG = "ProjectBrainuke"
    }
}
