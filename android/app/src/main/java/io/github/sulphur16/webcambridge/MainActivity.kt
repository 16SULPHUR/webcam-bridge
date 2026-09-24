package io.github.sulphur16.webcambridge

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.SurfaceTexture
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.os.Bundle
import android.view.TextureView
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * MainActivity — Full-screen camera preview UI.
 *
 * Streaming auto-starts when the Activity resumes (no manual button required).
 * Shows live camera preview via TextureView while simultaneously encoding
 * and sending H.264 over TCP to the Windows bridge.
 */
class MainActivity : AppCompatActivity() {

    companion object {
        private const val CAMERA_PERMISSION_REQUEST = 100
        // Set by the desktop bridge (`am start --ez stream true`) to skip the mode picker.
        const val EXTRA_STREAM = "stream"
    }

    private lateinit var cameraPreview: TextureView
    private lateinit var tvStatus: TextView
    private lateinit var tvRecBadge: TextView
    private lateinit var btnToggle: Button   // hidden, kept for compat
    private lateinit var btnSwitchCamera: Button
    private lateinit var btnSwitchMode: Button
    private lateinit var streamer: CameraStreamer

    private var isStreaming = false
    private var isStreamerModeSelected = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val prefs = getSharedPreferences("WebcamPrefs", Context.MODE_PRIVATE)
        val rememberedRole = prefs.getString("remembered_role", null)
        val launchedByBridge = intent.getBooleanExtra(EXTRA_STREAM, false)

        if (rememberedRole == "controller" && !launchedByBridge) {
            val intent = android.content.Intent(this, ControlActivity::class.java)
            startActivity(intent)
            finish()
            return
        } else if (rememberedRole == "streamer" || launchedByBridge) {
            isStreamerModeSelected = true
        }

        // Make the activity full-screen and keep screen on while streaming
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        setContentView(R.layout.activity_main)

        cameraPreview = findViewById(R.id.cameraPreview)
        tvStatus      = findViewById(R.id.tvStatus)
        tvRecBadge    = findViewById(R.id.tvRecBadge)
        btnToggle     = findViewById(R.id.btnToggle)
        btnSwitchCamera = findViewById(R.id.btnSwitchCamera)
        btnSwitchMode = findViewById(R.id.btnSwitchMode)

        btnSwitchCamera.setOnClickListener {
            showCameraSelectionDialog()
        }

        val overlay = findViewById<View>(R.id.modeSelectionOverlay)
        val cardStreamer = findViewById<View>(R.id.cardStreamerMode)
        val cardController = findViewById<View>(R.id.cardControllerMode)
        val cbRememberChoice = findViewById<android.widget.CheckBox>(R.id.cbRememberChoice)

        btnSwitchMode.setOnClickListener {
            // Clear remembered role
            prefs.edit().remove("remembered_role").apply()
            isStreamerModeSelected = false
            stopStreaming()
            overlay.visibility = View.VISIBLE
        }

        cardStreamer.setOnClickListener {
            if (cbRememberChoice.isChecked) {
                prefs.edit().putString("remembered_role", "streamer").apply()
            }
            isStreamerModeSelected = true
            overlay.visibility = View.GONE
            if (cameraPreview.isAvailable) {
                streamer.setPreviewTextureView(cameraPreview)
                startStreaming()
            }
        }

        cardController.setOnClickListener {
            if (cbRememberChoice.isChecked) {
                prefs.edit().putString("remembered_role", "controller").apply()
            }
            val intent = android.content.Intent(this, ControlActivity::class.java)
            startActivity(intent)
            if (cbRememberChoice.isChecked) {
                finish()
            }
        }

        streamer = CameraStreamer(this) { status ->
            runOnUiThread {
                tvStatus.text = status
                // Show LIVE badge when connected to PC
                val isConnected = status.contains("streaming", ignoreCase = true) ||
                                  status.contains("connected", ignoreCase = true)
                tvRecBadge.visibility = if (isConnected) View.VISIBLE else View.GONE
            }
        }

        // Wire up TextureView listener so we start streaming once the surface is ready
        cameraPreview.surfaceTextureListener = object : TextureView.SurfaceTextureListener {
            override fun onSurfaceTextureAvailable(surface: SurfaceTexture, w: Int, h: Int) {
                // Surface is ready — attempt to start streaming
                if (isStreamerModeSelected && !isStreaming) {
                    streamer.setPreviewTextureView(cameraPreview)
                    startStreaming()
                }
            }
            override fun onSurfaceTextureSizeChanged(surface: SurfaceTexture, w: Int, h: Int) {}
            override fun onSurfaceTextureDestroyed(surface: SurfaceTexture): Boolean = true
            override fun onSurfaceTextureUpdated(surface: SurfaceTexture) {}
        }
    }

    override fun onResume() {
        super.onResume()
        val overlay = findViewById<View>(R.id.modeSelectionOverlay)
        if (!isStreamerModeSelected) {
            overlay.visibility = View.VISIBLE
        } else {
            overlay.visibility = View.GONE
        }
        // If the TextureView is already available and we're streaming, start now
        if (isStreamerModeSelected && !isStreaming && cameraPreview.isAvailable) {
            streamer.setPreviewTextureView(cameraPreview)
            startStreaming()
        }
    }

    private fun startStreaming() {
        // Check camera permission at runtime (required for API 23+)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.CAMERA),
                CAMERA_PERMISSION_REQUEST
            )
            return
        }

        isStreaming = true
        tvStatus.text = "Starting camera…"
        streamer.start()
    }

    private fun stopStreaming() {
        isStreaming = false
        tvStatus.text = "Stopped"
        tvRecBadge.visibility = View.GONE
        streamer.stop()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == CAMERA_PERMISSION_REQUEST &&
            grantResults.isNotEmpty() &&
            grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            // Permission granted — start streaming
            startStreaming()
        } else {
            tvStatus.text = "Camera permission denied"
        }
    }

    private fun showCameraSelectionDialog() {
        val manager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val cameraIds = manager.cameraIdList
        val items = mutableListOf<String>()
        val actualIds = mutableListOf<String>()

        for (id in cameraIds) {
            try {
                val chars = manager.getCameraCharacteristics(id)
                val facing = chars.get(CameraCharacteristics.LENS_FACING)
                val facingStr = when (facing) {
                    CameraCharacteristics.LENS_FACING_BACK -> "Back Camera"
                    CameraCharacteristics.LENS_FACING_FRONT -> "Front Camera"
                    CameraCharacteristics.LENS_FACING_EXTERNAL -> "External Camera"
                    else -> "Camera"
                }
                items.add("$facingStr (ID: $id)")
                actualIds.add(id)
            } catch (e: Exception) {
                // Ignore
            }
        }

        if (items.isEmpty()) {
            android.widget.Toast.makeText(this, "No cameras found", android.widget.Toast.LENGTH_SHORT).show()
            return
        }

        val builder = androidx.appcompat.app.AlertDialog.Builder(this)
        builder.setTitle("Select Camera / Lens")
        builder.setItems(items.toTypedArray()) { _, which ->
            val selectedId = actualIds[which]
            streamer.switchCamera(selectedId)
            android.widget.Toast.makeText(this, "Switched to ${items[which]}", android.widget.Toast.LENGTH_SHORT).show()
        }
        builder.show()
    }

    override fun onDestroy() {
        super.onDestroy()
        if (isStreaming) stopStreaming()
    }
}
