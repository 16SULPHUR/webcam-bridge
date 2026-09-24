package io.github.sulphur16.webcambridge

import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/** Reachable over USB once the desktop bridge runs `adb reverse tcp:5134 tcp:5134`. */
const val DEFAULT_BRIDGE_ADDRESS = "127.0.0.1:5134"

/**
 * NetworkHelper — Lightweight asynchronous HTTP client for communication with the desktop bridge API.
 * Uses a thread pool and handlers to keep network calls off the main thread without external dependencies.
 */
object NetworkHelper {

    private val executor = Executors.newSingleThreadExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())

    interface Callback<T> {
        fun onSuccess(result: T)
        fun onError(error: Exception)
    }

    /**
     * Executes a GET request to retrieve status/config from the server.
     */
    fun get(urlStr: String, callback: Callback<String>) {
        executor.execute {
            try {
                val url = URL(urlStr)
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "GET"
                conn.connectTimeout = 10000
                conn.readTimeout = 10000

                val code = conn.responseCode
                if (code == HttpURLConnection.HTTP_OK) {
                    val reader = BufferedReader(InputStreamReader(conn.inputStream))
                    val sb = StringBuilder()
                    var line: String?
                    while (reader.readLine().also { line = it } != null) {
                        sb.append(line)
                    }
                    reader.close()
                    val result = sb.toString()
                    mainHandler.post { callback.onSuccess(result) }
                } else {
                    mainHandler.post { callback.onError(Exception("HTTP Error Code: $code")) }
                }
                conn.disconnect()
            } catch (e: Exception) {
                mainHandler.post { callback.onError(e) }
            }
        }
    }

    /**
     * Executes a POST request with a JSON payload.
     */
    fun postJson(urlStr: String, jsonPayload: String, callback: Callback<String>) {
        executor.execute {
            try {
                val url = URL(urlStr)
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.connectTimeout = 10000
                conn.readTimeout = 10000
                conn.doOutput = true

                val writer = OutputStreamWriter(conn.outputStream)
                writer.write(jsonPayload)
                writer.flush()
                writer.close()

                val code = conn.responseCode
                if (code == HttpURLConnection.HTTP_OK || code == HttpURLConnection.HTTP_NO_CONTENT) {
                    val reader = BufferedReader(InputStreamReader(conn.inputStream))
                    val sb = StringBuilder()
                    var line: String?
                    while (reader.readLine().also { line = it } != null) {
                        sb.append(line)
                    }
                    reader.close()
                    val result = sb.toString()
                    mainHandler.post { callback.onSuccess(result) }
                } else {
                    // Try to read error stream
                    val errStream = conn.errorStream
                    val errMsg = if (errStream != null) {
                        val reader = BufferedReader(InputStreamReader(errStream))
                        val sb = StringBuilder()
                        var line: String?
                        while (reader.readLine().also { line = it } != null) {
                            sb.append(line)
                        }
                        reader.close()
                        sb.toString()
                    } else {
                        "HTTP Error Code: $code"
                    }
                    mainHandler.post { callback.onError(Exception(errMsg)) }
                }
                conn.disconnect()
            } catch (e: Exception) {
                mainHandler.post { callback.onError(e) }
            }
        }
    }

    /**
     * Synchronous get request, suitable for calling from a background thread/receiver directly (e.g. Widget Provider).
     */
    fun getSync(urlStr: String): String {
        val url = URL(urlStr)
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = "GET"
        conn.connectTimeout = 10000
        conn.readTimeout = 10000

        val code = conn.responseCode
        if (code == HttpURLConnection.HTTP_OK) {
            val reader = BufferedReader(InputStreamReader(conn.inputStream))
            val sb = StringBuilder()
            var line: String?
            while (reader.readLine().also { line = it } != null) {
                sb.append(line)
            }
            reader.close()
            conn.disconnect()
            return sb.toString()
        } else {
            conn.disconnect()
            throw Exception("HTTP Error: $code")
        }
    }

    /**
     * Synchronous post request, suitable for calling from a background thread/receiver directly (e.g. Widget Provider).
     */
    fun postJsonSync(urlStr: String, jsonPayload: String): String {
        val url = URL(urlStr)
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.connectTimeout = 10000
        conn.readTimeout = 10000
        conn.doOutput = true

        val writer = OutputStreamWriter(conn.outputStream)
        writer.write(jsonPayload)
        writer.flush()
        writer.close()

        val code = conn.responseCode
        if (code == HttpURLConnection.HTTP_OK || code == HttpURLConnection.HTTP_NO_CONTENT) {
            val reader = BufferedReader(InputStreamReader(conn.inputStream))
            val sb = StringBuilder()
            var line: String?
            while (reader.readLine().also { line = it } != null) {
                sb.append(line)
            }
            reader.close()
            conn.disconnect()
            return sb.toString()
        } else {
            conn.disconnect()
            throw Exception("HTTP Error: $code")
        }
    }
}
