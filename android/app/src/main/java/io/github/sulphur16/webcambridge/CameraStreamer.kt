package io.github.sulphur16.webcambridge

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.hardware.camera2.*
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.os.Handler
import android.os.HandlerThread
import android.view.Surface
import android.view.TextureView
import android.util.Log
import androidx.core.content.ContextCompat
import java.io.OutputStream
import java.io.BufferedReader
import java.io.InputStreamReader
import org.json.JSONObject
import java.net.ServerSocket
import java.net.Socket
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

/**
 * CameraStreamer
 *
 * Orchestrates:
 *  1. Camera2 → captures preview frames from back camera
 *  2. MediaCodec → encodes frames as H.264 Annex-B
 *  3. TCP Server on port 8080 → streams the H.264 bitstream to any connected client
 *  4. Optional TextureView preview surface for in-app camera preview
 *
 * Lifecycle: call start() to begin, stop() to tear down.
 * The statusCallback is invoked on changes (camera open, client connect, errors).
 */
class CameraStreamer(
    private val context: Context,
    private val statusCallback: (String) -> Unit
) {

    companion object {
        private const val TAG = "CameraStreamer"

        // ─── TUNE: Resolution — must match Windows-side FFmpeg/pyvirtualcam settings ──
        private const val VIDEO_WIDTH  = 1280
        private const val VIDEO_HEIGHT = 720
        // ─────────────────────────────────────────────────────────────────────────────

        // ─── TUNE: Bitrate — 2 Mbps is a good USB/localhost starting point ───────────
        private const val VIDEO_BITRATE = 2_000_000  // 2 Mbps
        // ─────────────────────────────────────────────────────────────────────────────

        // ─── TUNE: Framerate ──────────────────────────────────────────────────────────
        private const val VIDEO_FPS = 30
        // ─────────────────────────────────────────────────────────────────────────────

        // ─── TUNE: I-frame interval in seconds — lower = faster seek, more data ───────
        private const val IFRAME_INTERVAL = 1
        // ─────────────────────────────────────────────────────────────────────────────

        private const val TCP_PORT = 8080  // must match adb forward and Windows client

        // Annex B start code — every NAL unit must be prefixed with this for FFmpeg
        private val ANNEXB_START_CODE = byteArrayOf(0x00, 0x00, 0x00, 0x01)
    }

    private val running = AtomicBoolean(false)

    // Optional preview TextureView — if set, camera will also send frames there
    private var previewTextureView: TextureView? = null

    // Threads
    private var cameraThread: HandlerThread? = null
    private var cameraHandler: Handler? = null
    private var serverThread: Thread? = null
    private var encoderThread: Thread? = null

    // Camera2
    private var cameraDevice: CameraDevice? = null
    private var captureSession: CameraCaptureSession? = null
    private var currentCameraId: String? = null

    // MediaCodec encoder
    private var encoder: MediaCodec? = null
    private var encoderInputSurface: Surface? = null  // Camera writes into this surface

    // TCP
    private var serverSocket: ServerSocket? = null

    /**
     * Shared SPS/PPS bytes sent to every new TCP client so they can decode immediately.
     * Set once when MediaCodec outputs BUFFER_FLAG_CODEC_CONFIG.
     */
    @Volatile private var spsppsBuf: ByteArray? = null

    /** Current connected client output stream — replaced on reconnect */
    @Volatile private var clientStream: OutputStream? = null

    // ─────────────────────────────────────────────────────────────────────────
    // Public API
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Set the TextureView used for live camera preview.
     * Must be called before start() to take effect.
     */
    fun setPreviewTextureView(textureView: TextureView) {
        previewTextureView = textureView
    }

    fun start() {
        if (running.getAndSet(true)) return

        // Start camera background thread
        cameraThread = HandlerThread("CameraThread").also { it.start() }
        cameraHandler = Handler(cameraThread!!.looper)

        // Start encoder first so its input Surface is ready for camera
        setupEncoder()

        // Open camera
        openCamera()

        // Start TCP server on a separate thread
        serverThread = Thread(::runTcpServer, "TcpServerThread").also { it.start() }

        statusCallback("Server started on :$TCP_PORT — waiting for PC connection…")
    }

    fun stop() {
        if (!running.getAndSet(false)) return

        statusCallback("Stopping…")

        try { captureSession?.close() } catch (e: Exception) { Log.w(TAG, e) }
        try { cameraDevice?.close()  } catch (e: Exception) { Log.w(TAG, e) }
        try { serverSocket?.close()  } catch (e: Exception) { Log.w(TAG, e) }
        try { clientStream?.close()  } catch (e: Exception) { Log.w(TAG, e) }
        try { encoder?.stop(); encoder?.release() } catch (e: Exception) { Log.w(TAG, e) }

        cameraThread?.quitSafely()
        cameraThread = null
        spsppsBuf = null
        clientStream = null
        encoder = null
    }

    // ─────────────────────────────────────────────────────────────────────────
    // MediaCodec Encoder Setup
    // ─────────────────────────────────────────────────────────────────────────
    private fun setupEncoder() {
        val format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, VIDEO_WIDTH, VIDEO_HEIGHT).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
            setInteger(MediaFormat.KEY_BIT_RATE, VIDEO_BITRATE)
            setInteger(MediaFormat.KEY_FRAME_RATE, VIDEO_FPS)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, IFRAME_INTERVAL)

            // ─── TUNE: Low-latency encoding flags ─────────────────────────────────
            setInteger(MediaFormat.KEY_PROFILE, MediaCodecInfo.CodecProfileLevel.AVCProfileBaseline)
            setInteger(MediaFormat.KEY_LATENCY, 0)
            setInteger(MediaFormat.KEY_PRIORITY, 0) // Real-time priority mode
            // ─────────────────────────────────────────────────────────────────────

            // Prepend SPS/PPS headers before every sync frame (Android Q+)
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
                setInteger(MediaFormat.KEY_PREPEND_HEADER_TO_SYNC_FRAMES, 1)
            }
        }

        encoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
        encoder!!.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)

        // Camera will write frames directly into this Surface — no CPU copy needed
        encoderInputSurface = encoder!!.createInputSurface()

        // Start encoder in async-output mode: poll output on a dedicated thread
        encoder!!.start()

        encoderThread = Thread(::drainEncoder, "EncoderDrainThread").also { it.start() }
        Log.i(TAG, "Encoder started: ${VIDEO_WIDTH}x${VIDEO_HEIGHT} @ ${VIDEO_FPS}fps, bitrate=$VIDEO_BITRATE")
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Encoder Output Drain → TCP
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Ensure data has an Annex B start code (0x00 0x00 0x00 0x01) at the front.
     * Some devices (e.g. Realme/MediaTek) emit CODEC_CONFIG without start codes.
     */
    private fun ensureAnnexB(data: ByteArray): ByteArray {
        if (data.size >= 4 &&
            data[0] == 0x00.toByte() &&
            data[1] == 0x00.toByte() &&
            data[2] == 0x00.toByte() &&
            data[3] == 0x01.toByte()) {
            return data  // already has Annex B start code
        }
        return ANNEXB_START_CODE + data
    }

    /**
     * Continuously drain MediaCodec output buffers and send encoded H.264 NAL units
     * over the TCP connection.
     *
     * Special handling for BUFFER_FLAG_CODEC_CONFIG: this contains SPS+PPS which
     * must be sent first to any new client so they can decode the stream.
     * BUG FIX: Also send SPS/PPS to any already-connected client when first received,
     * in case the client connected before the encoder emitted its CODEC_CONFIG.
     */
    private fun drainEncoder() {
        val bufferInfo = MediaCodec.BufferInfo()

        while (running.get()) {
            val enc = encoder ?: break

            // Dequeue output buffer (timeout 10ms to allow loop to check running flag)
            val outIndex = try {
                enc.dequeueOutputBuffer(bufferInfo, 10_000)
            } catch (e: IllegalStateException) {
                break  // encoder was stopped
            }

            when {
                outIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                    // Format changed — SPS/PPS will arrive as CODEC_CONFIG buffer next
                    Log.i(TAG, "Encoder output format changed")
                }
                outIndex >= 0 -> {
                    val outBuf: ByteBuffer = enc.getOutputBuffer(outIndex) ?: continue
                    outBuf.position(bufferInfo.offset)
                    outBuf.limit(bufferInfo.offset + bufferInfo.size)

                    val raw = ByteArray(bufferInfo.size)
                    outBuf.get(raw)

                    if (bufferInfo.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0) {
                        // SPS+PPS — ensure Annex B start codes, then:
                        // 1. Save for future new clients
                        // 2. Also send to any currently connected client (race-condition fix)
                        val data = ensureAnnexB(raw)
                        spsppsBuf = data
                        sendToClient(data)  // send to existing client if any
                        Log.i(TAG, "Got SPS/PPS (${data.size} bytes), sent to existing client")
                    } else {
                        // Regular encoded frame — send to current TCP client
                        sendToClient(raw)
                    }

                    enc.releaseOutputBuffer(outIndex, false)
                }
            }
        }
        Log.i(TAG, "Encoder drain thread exiting")
    }

    /**
     * Write encoded bytes to the current TCP client stream.
     * If no client is connected, silently drop the frame (encoder keeps running).
     */
    private fun sendToClient(data: ByteArray) {
        val stream = clientStream ?: return
        try {
            stream.write(data)
            stream.flush()
        } catch (e: Exception) {
            // Client disconnected — clear the stream; TCP server will reconnect
            Log.w(TAG, "Client write failed: ${e.message}")
            clientStream = null
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Camera2 — open back camera and create a capture session
    // ─────────────────────────────────────────────────────────────────────────

    fun switchCamera(cameraId: String) {
        if (currentCameraId == cameraId) return
        currentCameraId = cameraId
        if (running.get()) {
            cameraHandler?.post {
                try {
                    captureSession?.close()
                    captureSession = null
                    cameraDevice?.close()
                    cameraDevice = null
                } catch (e: Exception) {
                    Log.w(TAG, "Error closing camera for switch: ${e.message}")
                }
                openCamera()
            }
        }
    }

    private fun handleRemoteCameraSwitch(facing: String) {
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        for (id in manager.cameraIdList) {
            try {
                val chars = manager.getCameraCharacteristics(id)
                val lensFacing = chars.get(CameraCharacteristics.LENS_FACING)
                val targetFacing = if (facing.equals("front", ignoreCase = true)) {
                    CameraCharacteristics.LENS_FACING_FRONT
                } else {
                    CameraCharacteristics.LENS_FACING_BACK
                }
                if (lensFacing == targetFacing) {
                    switchCamera(id)
                    break
                }
            } catch (e: Exception) {
                // Ignore
            }
        }
    }

    private fun openCamera() {
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager

        val cameraId = currentCameraId ?: manager.cameraIdList.firstOrNull { id ->
            try {
                manager.getCameraCharacteristics(id)
                    .get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK
            } catch (e: Exception) {
                false
            }
        } ?: manager.cameraIdList.firstOrNull() ?: throw IllegalStateException("No camera available")

        currentCameraId = cameraId
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED
        ) {
            statusCallback("Camera permission not granted")
            return
        }
        Log.i(TAG, "Opening camera ID: $cameraId")

        manager.openCamera(cameraId, object : CameraDevice.StateCallback() {
            override fun onOpened(camera: CameraDevice) {
                Log.i(TAG, "Camera opened")
                cameraDevice = camera
                createCaptureSession(camera)
            }

            override fun onDisconnected(camera: CameraDevice) {
                Log.w(TAG, "Camera disconnected")
                camera.close()
                statusCallback("Camera disconnected")
            }

            override fun onError(camera: CameraDevice, error: Int) {
                Log.e(TAG, "Camera error: $error")
                camera.close()
                statusCallback("Camera error: $error")
            }
        }, cameraHandler)
    }

    private fun createCaptureSession(camera: CameraDevice) {
        val encoderSurface = encoderInputSurface ?: return

        // Build list of output surfaces: encoder + optional preview
        val outputSurfaces = mutableListOf(encoderSurface)

        // Add TextureView preview surface if available and ready
        val previewSurface: Surface? = previewTextureView?.let { tv ->
            val st = tv.surfaceTexture ?: return@let null
            st.setDefaultBufferSize(VIDEO_WIDTH, VIDEO_HEIGHT)
            Surface(st)
        }
        previewSurface?.let { outputSurfaces.add(it) }

        camera.createCaptureSession(
            outputSurfaces,
            object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(session: CameraCaptureSession) {
                    captureSession = session

                    // Build a repeating capture request targeting encoder + preview surfaces
                    val request = camera.createCaptureRequest(CameraDevice.TEMPLATE_RECORD).apply {
                        addTarget(encoderSurface)
                        previewSurface?.let { addTarget(it) }

                        // ─── TUNE: AE / AF modes ─────────────────────────────────────
                        set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO)
                        set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON)
                        // ─── TUNE: Lock sensor framerate to 30 FPS to prevent variable frame delays
                        set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, android.util.Range<Int>(30, 30))
                        // ─────────────────────────────────────────────────────────────
                    }.build()

                    session.setRepeatingRequest(request, null, cameraHandler)
                    Log.i(TAG, "Capture session configured — encoding started with preview=${previewSurface != null}")
                    statusCallback("Camera ready — waiting for PC to connect…")
                }

                override fun onConfigureFailed(session: CameraCaptureSession) {
                    Log.e(TAG, "Capture session configure failed")
                    statusCallback("Camera session failed")
                }
            },
            cameraHandler
        )
    }

    // ─────────────────────────────────────────────────────────────────────────
    // TCP Server
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Runs a TCP server that accepts one client at a time.
     * On connect: sends SPS+PPS, then the encoder drain thread delivers subsequent NALUs.
     * On disconnect: waits for the next client (encoder keeps running uninterrupted).
     */
    private fun runTcpServer() {
        try {
            serverSocket = ServerSocket(TCP_PORT)
            Log.i(TAG, "TCP server listening on :$TCP_PORT")

            while (running.get()) {
                val client: Socket = try {
                    serverSocket!!.accept()  // blocks until a client connects
                } catch (e: Exception) {
                    if (running.get()) Log.w(TAG, "Accept failed: ${e.message}")
                    break
                }

                client.tcpNoDelay = true // Disable Nagle's algorithm for instant packet delivery
                Log.i(TAG, "Client connected: ${client.inetAddress}")
                statusCallback("PC connected — streaming!")

                val stream = client.getOutputStream()
                clientStream = stream

                // Send SPS+PPS immediately so the client can start decoding
                spsppsBuf?.let { spspps ->
                    try {
                        stream.write(spspps)
                        stream.flush()
                        Log.i(TAG, "Sent SPS/PPS to new client")
                    } catch (e: Exception) {
                        Log.w(TAG, "Failed to send SPS/PPS: ${e.message}")
                    }
                }

                // Request a fresh IDR keyframe from the encoder so the client gets
                // a complete, self-contained frame immediately after SPS/PPS
                encoder?.setParameters(android.os.Bundle().apply {
                    putInt(android.media.MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 0)
                })

                // Block here until the client disconnects by reading from its InputStream.
                // Since the client never sends data, read() will block until EOF (-1) or exception.
                // Block here until the client disconnects, reading lines for JSON commands
                try {
                    val inputStream = client.getInputStream()
                    val reader = BufferedReader(InputStreamReader(inputStream))
                    var line: String?
                    while (running.get() && clientStream != null) {
                        line = reader.readLine()
                        if (line == null) {
                            Log.i(TAG, "Client socket read returned EOF (null)")
                            break
                        }
                        try {
                            val json = JSONObject(line)
                            val action = json.optString("action")
                            if (action == "switch_camera") {
                                val facing = json.optString("cameraFacing")
                                handleRemoteCameraSwitch(facing)
                            }
                        } catch (e: Exception) {
                            Log.w(TAG, "Failed to parse command from client: ${e.message}")
                        }
                    }
                } catch (e: Exception) {
                    Log.i(TAG, "Client socket read exception: ${e.message}")
                }

                clientStream = null
                try { client.close() } catch (e: Exception) { /* ignore */ }
                Log.i(TAG, "Client disconnected — waiting for next connection")
                statusCallback("PC disconnected — waiting for reconnect…")
            }
        } catch (e: Exception) {
            if (running.get()) {
                Log.e(TAG, "TCP server error: ${e.message}")
                statusCallback("Server error: ${e.message}")
            }
        }
        Log.i(TAG, "TCP server thread exiting")
    }
}
