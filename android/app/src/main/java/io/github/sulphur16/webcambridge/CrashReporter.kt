package io.github.sulphur16.webcambridge

import android.app.Activity
import android.app.Application
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import java.io.File

/** Saves crash details on the phone and offers them on the next launch, so no USB data cable is needed. */
class WebcamBridgeApp : Application() {
    override fun onCreate() {
        super.onCreate()
        CrashReporter.install(this)
    }
}

object CrashReporter {
    private const val TAG = "CrashReporter"
    private const val PREFS = "CrashReporter"
    private const val KEY_STREAMING = "streaming"

    private fun crashFile(context: Context) = File(context.filesDir, "last-crash.txt")

    fun install(context: Context) {
        val app = context.applicationContext
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            try {
                crashFile(app).writeText(
                    "Thread: ${thread.name}\n\n${Log.getStackTraceString(error)}\n${recentLog()}"
                )
            } catch (e: Throwable) {
            }
            previous?.uncaughtException(thread, error)
        }
    }

    /** Native crashes skip the handler above, so streaming is flagged while it runs. */
    fun setStreaming(context: Context, streaming: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putBoolean(KEY_STREAMING, streaming).commit()
    }

    fun showPendingReport(activity: Activity) {
        val prefs = activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val wasStreaming = prefs.getBoolean(KEY_STREAMING, false)
        prefs.edit().putBoolean(KEY_STREAMING, false).apply()

        val file = crashFile(activity)
        val details = when {
            file.exists() -> file.readText().also { file.delete() }
            wasStreaming -> recentLog().takeIf { "Fatal signal" in it || "FATAL" in it } ?: return
            else -> return
        }
        val report = "Webcam Bridge ${BuildConfig.VERSION_NAME} on ${Build.MANUFACTURER} ${Build.MODEL}, " +
            "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})\n\n$details"

        AlertDialog.Builder(activity)
            .setTitle("The app crashed last time")
            .setMessage("Please send this report so it can be fixed.\n\n" + report.take(4000))
            .setPositiveButton("Share") { _, _ ->
                val send = Intent(Intent.ACTION_SEND).setType("text/plain")
                    .putExtra(Intent.EXTRA_SUBJECT, "Webcam Bridge crash report")
                    .putExtra(Intent.EXTRA_TEXT, report)
                activity.startActivity(Intent.createChooser(send, "Send crash report"))
            }
            .setNeutralButton("Copy") { _, _ ->
                val clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(ClipData.newPlainText("Webcam Bridge crash report", report))
                Toast.makeText(activity, "Copied", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Close", null)
            .show()
    }

    /** An app may read its own log lines, including those of its previous run. */
    private fun recentLog(): String = try {
        val proc = Runtime.getRuntime().exec(arrayOf("logcat", "-d", "-v", "time", "-t", "300"))
        proc.inputStream.bufferedReader().readText().also { proc.destroy() }
    } catch (e: Exception) {
        Log.w(TAG, "Could not read the log", e)
        ""
    }
}
