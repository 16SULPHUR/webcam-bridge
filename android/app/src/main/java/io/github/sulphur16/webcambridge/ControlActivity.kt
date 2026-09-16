package io.github.sulphur16.webcambridge

import android.content.Context
import android.content.SharedPreferences
import android.os.Bundle
import android.view.View
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import com.google.android.material.switchmaterial.SwitchMaterial
import org.json.JSONObject

/**
 * ControlActivity — Remote Controller Mode.
 * Communicates with the Windows bridge HTTP API to sync and update camera/filter settings.
 */
class ControlActivity : AppCompatActivity() {

    private lateinit var etBridgeIp: EditText
    private lateinit var btnConnect: Button
    private lateinit var tvStatus: TextView

    private lateinit var btnRecord: MaterialButton
    private lateinit var btnCapture: MaterialButton
    private lateinit var btnResetPipeline: MaterialButton

    private lateinit var sbBrightness: SeekBar
    private lateinit var tvBrightnessVal: TextView

    private lateinit var sbContrast: SeekBar
    private lateinit var tvContrastVal: TextView

    private lateinit var sbSaturation: SeekBar
    private lateinit var tvSaturationVal: TextView

    private lateinit var sbSharpness: SeekBar
    private lateinit var tvSharpnessVal: TextView

    private lateinit var sbBlur: SeekBar
    private lateinit var tvBlurVal: TextView

    private lateinit var sbZoom: SeekBar
    private lateinit var tvZoomVal: TextView

    private lateinit var swMirror: SwitchMaterial
    private lateinit var swVcam: SwitchMaterial

    private lateinit var spResolution: Spinner
    private lateinit var spFps: Spinner
    private lateinit var spOrientation: Spinner

    private lateinit var prefs: SharedPreferences
    private var isRecordingState = false
    private var isSyncingFromServer = false // Flag to ignore seekbar change listeners during GET sync

    private lateinit var btnResetFilters: MaterialButton
    private lateinit var spCameraFacing: Spinner

    // Dropdown options matching the web dashboard
    private val resolutionOptions = arrayOf("auto", "640x360", "640x480", "960x540", "1280x720", "1280x960", "1920x1080")
    private val fpsOptions = arrayOf("10", "15", "20", "24", "30")
    private val orientationOptions = arrayOf("0", "90", "180", "270")
    private val cameraOptions = arrayOf("back", "front")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_control)

        // Setup Toolbar back button
        val toolbar = findViewById<androidx.appcompat.widget.Toolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        toolbar.setNavigationOnClickListener { onBackPressedDispatcher.onBackPressed() }

        prefs = getSharedPreferences("WebcamPrefs", Context.MODE_PRIVATE)

        initViews()
        setupSpinners()
        loadSavedIp()
        setupListeners()

        // Auto-connect if IP exists
        if (etBridgeIp.text.isNotEmpty()) {
            fetchStatus()
        }
    }

    private fun initViews() {
        etBridgeIp = findViewById(R.id.etBridgeIp)
        btnConnect = findViewById(R.id.btnConnect)
        tvStatus = findViewById(R.id.tvConnectionStatus)

        btnRecord = findViewById(R.id.btnRecord)
        btnCapture = findViewById(R.id.btnCapture)
        btnResetPipeline = findViewById(R.id.btnResetPipeline)

        sbBrightness = findViewById(R.id.sbBrightness)
        tvBrightnessVal = findViewById(R.id.tvBrightnessValue)

        sbContrast = findViewById(R.id.sbContrast)
        tvContrastVal = findViewById(R.id.tvContrastValue)

        sbSaturation = findViewById(R.id.sbSaturation)
        tvSaturationVal = findViewById(R.id.tvSaturationValue)

        sbSharpness = findViewById(R.id.sbSharpness)
        tvSharpnessVal = findViewById(R.id.tvSharpnessValue)

        sbBlur = findViewById(R.id.sbBlur)
        tvBlurVal = findViewById(R.id.tvBlurValue)

        sbZoom = findViewById(R.id.sbZoom)
        tvZoomVal = findViewById(R.id.tvZoomValue)

        swMirror = findViewById(R.id.swMirror)
        swVcam = findViewById(R.id.swVcam)

        spResolution = findViewById(R.id.spResolution)
        spFps = findViewById(R.id.spFps)
        spOrientation = findViewById(R.id.spOrientation)
        spCameraFacing = findViewById(R.id.spCameraFacing)
        btnResetFilters = findViewById(R.id.btnResetFilters)
    }

    private fun setupSpinners() {
        val resAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, resolutionOptions)
        resAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spResolution.adapter = resAdapter

        val fpsAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, fpsOptions.map { "$it fps" })
        fpsAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spFps.adapter = fpsAdapter

        val oriAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, orientationOptions.map { "$it°" })
        oriAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spOrientation.adapter = oriAdapter

        val camAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, cameraOptions.map { if (it == "back") "Back Camera" else "Front Camera" })
        camAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spCameraFacing.adapter = camAdapter
    }

    private fun loadSavedIp() {
        val savedIp = prefs.getString("bridge_ip", DEFAULT_BRIDGE_ADDRESS)
        etBridgeIp.setText(savedIp)
    }

    private fun saveIp(ip: String) {
        prefs.edit().putString("bridge_ip", ip).apply()
    }

    private fun getBaseUrl(): String {
        var ip = etBridgeIp.text.toString().trim()
        if (ip.isEmpty()) return ""
        if (!ip.startsWith("http://") && !ip.startsWith("https://")) {
            ip = "http://$ip"
        }
        return ip
    }

    private fun fetchStatus() {
        val baseUrl = getBaseUrl()
        if (baseUrl.isEmpty()) {
            Toast.makeText(this, "Please enter an IP address", Toast.LENGTH_SHORT).show()
            return
        }

        saveIp(etBridgeIp.text.toString().trim())
        tvStatus.text = "Syncing with bridge..."

        NetworkHelper.get("$baseUrl/api/status", object : NetworkHelper.Callback<String> {
            override fun onSuccess(result: String) {
                try {
                    val json = JSONObject(result)
                    val config = json.getJSONObject("config")

                    isSyncingFromServer = true
                    updateUiFromConfig(config)
                    isSyncingFromServer = false

                    // Update connection/recording status
                    val androidConnected = json.optBoolean("androidConnected", false)
                    val activeConnections = json.optInt("decodedFrames", 0)
                    isRecordingState = json.optBoolean("recording", false)

                    tvStatus.text = "Connected. Phone connected to PC: $androidConnected. Frames: $activeConnections"
                    updateRecordButtonUi()
                } catch (e: Exception) {
                    tvStatus.text = "Failed to parse status response: ${e.message}"
                }
            }

            override fun onError(error: Exception) {
                tvStatus.text = "Connection Error: ${error.message}"
            }
        })
    }

    private fun updateUiFromConfig(config: JSONObject) {
        // Brightness: maps progress 0-200 to -1.0 to 1.0 (default 0)
        val brightness = config.optDouble("brightness", 0.0)
        sbBrightness.progress = ((brightness + 1.0) * 100).toInt().coerceIn(0, 200)
        tvBrightnessVal.text = String.format("%.2f", brightness)

        // Contrast: maps progress 0-150 to 0.5 to 2.0 (default 1.0)
        val contrast = config.optDouble("contrast", 1.0)
        sbContrast.progress = ((contrast - 0.5) * 100).toInt().coerceIn(0, 150)
        tvContrastVal.text = String.format("%.2f", contrast)

        // Saturation: maps progress 0-200 to 0.0 to 2.0 (default 1.0)
        val saturation = config.optDouble("saturation", 1.0)
        sbSaturation.progress = (saturation * 100).toInt().coerceIn(0, 200)
        tvSaturationVal.text = String.format("%.2f", saturation)

        // Sharpness: maps progress 0-20 to 0.0 to 2.0 (default 0.0)
        val sharpness = config.optDouble("sharpness", 0.0)
        sbSharpness.progress = (sharpness * 10).toInt().coerceIn(0, 20)
        tvSharpnessVal.text = String.format("%.1f", sharpness)

        // Blur: progress 0-25 (default 0)
        val blur = config.optInt("blur", 0)
        sbBlur.progress = blur.coerceIn(0, 25)
        tvBlurVal.text = if (blur == 0) "Off" else "${blur}px"

        // Zoom: maps progress 0-20 to 1.0 to 3.0 (default 1.0)
        val zoom = config.optDouble("zoom", 1.0)
        sbZoom.progress = ((zoom - 1.0) * 10).toInt().coerceIn(0, 20)
        tvZoomVal.text = String.format("%.1fx", zoom)

        // Switches
        swMirror.isChecked = config.optBoolean("mirror", false)
        swVcam.isChecked = config.optBoolean("vcamEnabled", true)

        // Dropdowns
        val resolution = config.optString("resolution", "auto")
        val resIdx = resolutionOptions.indexOf(resolution)
        if (resIdx >= 0) spResolution.setSelection(resIdx)

        val fps = config.optInt("targetFps", 30)
        val fpsIdx = fpsOptions.indexOf(fps.toString())
        if (fpsIdx >= 0) spFps.setSelection(fpsIdx)

        val orientation = config.optInt("orientation", 0)
        val oriIdx = orientationOptions.indexOf(orientation.toString())
        if (oriIdx >= 0) spOrientation.setSelection(oriIdx)

        val cameraFacing = config.optString("cameraFacing", "back")
        val camIdx = cameraOptions.indexOf(cameraFacing)
        if (camIdx >= 0) spCameraFacing.setSelection(camIdx)
    }

    private fun updateRecordButtonUi() {
        if (isRecordingState) {
            btnRecord.text = "Stop"
            btnRecord.setBackgroundColor(0xffef4444.toInt()) // Red
        } else {
            btnRecord.text = "Record"
            btnRecord.setBackgroundColor(0xff3b82f6.toInt()) // Blue (or original default color)
        }
    }

    private fun sendConfig() {
        if (isSyncingFromServer) return

        val baseUrl = getBaseUrl()
        if (baseUrl.isEmpty()) return

        val payload = JSONObject()
        // Brightness
        val brightness = (sbBrightness.progress - 100) / 100.0
        payload.put("brightness", brightness)

        // Contrast
        val contrast = 0.5 + (sbContrast.progress / 100.0)
        payload.put("contrast", contrast)

        // Saturation
        val saturation = sbSaturation.progress / 100.0
        payload.put("saturation", saturation)

        // Sharpness
        val sharpness = sbSharpness.progress / 10.0
        payload.put("sharpness", sharpness)

        // Blur
        val blur = sbBlur.progress
        payload.put("blur", blur)

        // Zoom
        val zoom = 1.0 + (sbZoom.progress / 10.0)
        payload.put("zoom", zoom)

        // Switches
        payload.put("mirror", swMirror.isChecked)
        payload.put("vcamEnabled", swVcam.isChecked)

        // Spinners
        payload.put("resolution", resolutionOptions[spResolution.selectedItemPosition])
        payload.put("targetFps", fpsOptions[spFps.selectedItemPosition].toInt())
        payload.put("orientation", orientationOptions[spOrientation.selectedItemPosition].toInt())
        payload.put("cameraFacing", cameraOptions[spCameraFacing.selectedItemPosition])

        NetworkHelper.postJson("$baseUrl/api/config", payload.toString(), object : NetworkHelper.Callback<String> {
            override fun onSuccess(result: String) {
                // Config applied successfully
            }
            override fun onError(error: Exception) {
                tvStatus.text = "Failed to update settings: ${error.message}"
            }
        })
    }

    private fun setupListeners() {
        btnConnect.setOnClickListener {
            fetchStatus()
        }

        btnResetPipeline.setOnClickListener {
            val baseUrl = getBaseUrl()
            if (baseUrl.isEmpty()) return@setOnClickListener
            NetworkHelper.postJson("$baseUrl/api/reconnect", "{}", object : NetworkHelper.Callback<String> {
                override fun onSuccess(result: String) {
                    Toast.makeText(this@ControlActivity, "Pipeline reset requested", Toast.LENGTH_SHORT).show()
                }
                override fun onError(error: Exception) {
                    Toast.makeText(this@ControlActivity, "Failed to reset: ${error.message}", Toast.LENGTH_SHORT).show()
                }
            })
        }

        btnResetFilters.setOnClickListener {
            val baseUrl = getBaseUrl()
            if (baseUrl.isEmpty()) return@setOnClickListener

            val payload = JSONObject().apply {
                put("brightness", 0.0)
                put("contrast", 1.0)
                put("saturation", 1.0)
                put("sharpness", 0.0)
                put("blur", 0)
                put("zoom", 1.0)
                put("mirror", false)
                put("vcamEnabled", true)
                put("resolution", "auto")
                put("targetFps", 30)
                put("orientation", 0)
                put("cameraFacing", cameraOptions[spCameraFacing.selectedItemPosition]) // preserve current camera facing
            }

            isSyncingFromServer = true // temporarily ignore change listeners
            NetworkHelper.postJson("$baseUrl/api/config", payload.toString(), object : NetworkHelper.Callback<String> {
                override fun onSuccess(result: String) {
                    Toast.makeText(this@ControlActivity, "Filters reset to default", Toast.LENGTH_SHORT).show()
                    fetchStatus()
                }
                override fun onError(error: Exception) {
                    isSyncingFromServer = false
                    Toast.makeText(this@ControlActivity, "Reset failed: ${error.message}", Toast.LENGTH_SHORT).show()
                }
            })
        }

        btnRecord.setOnClickListener {
            val baseUrl = getBaseUrl()
            if (baseUrl.isEmpty()) return@setOnClickListener
            val endpoint = if (isRecordingState) "/api/record/stop" else "/api/record/start"

            NetworkHelper.postJson("$baseUrl$endpoint", "{}", object : NetworkHelper.Callback<String> {
                override fun onSuccess(result: String) {
                    isRecordingState = !isRecordingState
                    updateRecordButtonUi()
                    val statusStr = if (isRecordingState) "Recording started" else "Recording stopped"
                    Toast.makeText(this@ControlActivity, statusStr, Toast.LENGTH_SHORT).show()
                }
                override fun onError(error: Exception) {
                    Toast.makeText(this@ControlActivity, "Record action failed: ${error.message}", Toast.LENGTH_SHORT).show()
                }
            })
        }

        btnCapture.setOnClickListener {
            val baseUrl = getBaseUrl()
            if (baseUrl.isEmpty()) return@setOnClickListener

            NetworkHelper.postJson("$baseUrl/api/record/snapshot", "{}", object : NetworkHelper.Callback<String> {
                override fun onSuccess(result: String) {
                    Toast.makeText(this@ControlActivity, "Snapshot captured", Toast.LENGTH_SHORT).show()
                }
                override fun onError(error: Exception) {
                    Toast.makeText(this@ControlActivity, "Capture failed: ${error.message}", Toast.LENGTH_SHORT).show()
                }
            })
        }

        // Sliders (Update textual label live on progress, save only when slider is released)
        sbBrightness.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val brightness = (progress - 100) / 100.0
                tvBrightnessVal.text = String.format("%.2f", brightness)
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) { sendConfig() }
        })

        sbContrast.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val contrast = 0.5 + (progress / 100.0)
                tvContrastVal.text = String.format("%.2f", contrast)
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) { sendConfig() }
        })

        sbSaturation.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val saturation = progress / 100.0
                tvSaturationVal.text = String.format("%.2f", saturation)
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) { sendConfig() }
        })

        sbSharpness.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val sharpness = progress / 10.0
                tvSharpnessVal.text = String.format("%.1f", sharpness)
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) { sendConfig() }
        })

        sbBlur.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                tvBlurVal.text = if (progress == 0) "Off" else "${progress}px"
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) { sendConfig() }
        })

        sbZoom.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val zoom = 1.0 + (progress / 10.0)
                tvZoomVal.text = String.format("%.1fx", zoom)
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) { sendConfig() }
        })

        // Switches and Dropdowns update on immediate click
        swMirror.setOnCheckedChangeListener { _, _ -> sendConfig() }
        swVcam.setOnCheckedChangeListener { _, _ -> sendConfig() }

        val spinnerListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                sendConfig()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
        spResolution.onItemSelectedListener = spinnerListener
        spFps.onItemSelectedListener = spinnerListener
        spOrientation.onItemSelectedListener = spinnerListener
        spCameraFacing.onItemSelectedListener = spinnerListener
    }

    override fun onCreateOptionsMenu(menu: android.view.Menu?): Boolean {
        menu?.add(0, 1001, 0, "Switch Mode")?.apply {
            setShowAsAction(android.view.MenuItem.SHOW_AS_ACTION_IF_ROOM)
        }
        return true
    }

    override fun onOptionsItemSelected(item: android.view.MenuItem): Boolean {
        if (item.itemId == 1001) {
            prefs.edit().remove("remembered_role").apply()
            val intent = android.content.Intent(this, MainActivity::class.java)
            intent.flags = android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP or android.content.Intent.FLAG_ACTIVITY_SINGLE_TOP
            startActivity(intent)
            finish()
            return true
        }
        return super.onOptionsItemSelected(item)
    }
}
