package io.github.sulphur16.webcambridge

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Build
import android.util.Log
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.Inet4Address
import java.net.InetSocketAddress
import java.net.NetworkInterface

/** Answers the desktop bridge's Wi-Fi discovery broadcasts so it can find this phone. */
class DiscoveryResponder(private val context: Context, private val streamPort: Int) {

    companion object {
        private const val TAG = "DiscoveryResponder"
        const val DISCOVERY_PORT = 8081
        private const val PROBE = "WEBCAM_BRIDGE_DISCOVER"

        fun wifiAddress(): String? = try {
            NetworkInterface.getNetworkInterfaces().toList()
                .filter { it.isUp && !it.isLoopback && !it.name.startsWith("rmnet") }
                .sortedByDescending { it.name.startsWith("wlan") }
                .flatMap { it.inetAddresses.toList() }
                .firstOrNull { it is Inet4Address && !it.isLoopbackAddress }
                ?.hostAddress
        } catch (e: Exception) {
            null
        }
    }

    @Volatile private var socket: DatagramSocket? = null
    private var lock: WifiManager.MulticastLock? = null

    fun start() {
        if (socket != null) return
        lock = try {
            (context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager)
                ?.createMulticastLock("webcam-bridge-discovery")
                ?.apply { setReferenceCounted(false); acquire() }
        } catch (e: Exception) {
            Log.w(TAG, "No multicast lock; Wi-Fi discovery may miss broadcasts: ${e.message}")
            null
        }
        Thread(::serve, "DiscoveryResponder").start()
    }

    fun stop() {
        socket?.close()
        socket = null
        try { lock?.release() } catch (e: Exception) { Log.w(TAG, e) }
        lock = null
    }

    private fun serve() {
        try {
            val sock = DatagramSocket(null).apply {
                reuseAddress = true
                broadcast = true
                bind(InetSocketAddress(DISCOVERY_PORT))
            }
            socket = sock
            val reply = JSONObject()
                .put("app", "webcam-bridge")
                .put("name", "${Build.MANUFACTURER} ${Build.MODEL}".trim())
                .put("port", streamPort)
                .toString().toByteArray()
            val buf = ByteArray(256)
            while (!sock.isClosed) {
                val packet = DatagramPacket(buf, buf.size)
                sock.receive(packet)
                if (String(packet.data, 0, packet.length).trim() != PROBE) continue
                sock.send(DatagramPacket(reply, reply.size, packet.socketAddress))
            }
        } catch (e: Exception) {
            if (socket != null) Log.w(TAG, "Discovery stopped: ${e.message}")
        }
    }
}
