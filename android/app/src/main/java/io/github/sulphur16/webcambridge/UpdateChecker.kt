package io.github.sulphur16.webcambridge

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import kotlin.concurrent.thread

/**
 * Looks for a newer GitHub release on launch and installs it through the system installer.
 * The installer itself rejects an APK that is not signed with the key of the installed app.
 */
object UpdateChecker {

    private const val LATEST_URL = "https://api.github.com/repos/16SULPHUR/webcam-bridge/releases/latest"
    private const val PREFS = "WebcamPrefs"
    private const val KEY_LAST_CHECK = "update_last_check"
    private const val KEY_SKIPPED = "update_skipped_version"
    private const val CHECK_INTERVAL_MS = 12 * 60 * 60 * 1000L

    private class Release(val version: String, val apkUrl: String, val apkName: String, val sumsUrl: String?)

    fun parseVersion(text: String?): List<Int> =
        Regex("""^v?(\d+(?:\.\d+)*)""").find(text?.trim().orEmpty())
            ?.groupValues?.get(1)?.split('.')?.map { it.toInt() } ?: emptyList()

    fun isNewer(candidate: String?, current: String): Boolean {
        val new = parseVersion(candidate)
        val cur = parseVersion(current)
        if (new.isEmpty() || cur.isEmpty()) return false
        for (i in 0 until maxOf(new.size, cur.size)) {
            val a = new.getOrElse(i) { 0 }
            val b = cur.getOrElse(i) { 0 }
            if (a != b) return a > b
        }
        return false
    }

    fun checkOnLaunch(activity: AppCompatActivity) {
        val prefs = activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        if (now - prefs.getLong(KEY_LAST_CHECK, 0) < CHECK_INTERVAL_MS) return
        thread(name = "UpdateCheck", isDaemon = true) {
            val release = try { fetchLatest() } catch (e: Exception) { null } ?: return@thread
            prefs.edit().putLong(KEY_LAST_CHECK, now).apply()
            if (!isNewer(release.version, BuildConfig.VERSION_NAME)) return@thread
            if (prefs.getString(KEY_SKIPPED, null) == release.version) return@thread
            activity.runOnUiThread { if (!activity.isFinishing) offer(activity, release) }
        }
    }

    private fun fetchLatest(): Release? {
        val json = JSONObject(httpGet(LATEST_URL))
        val version = json.optString("tag_name").removePrefix("v")
        val assets = json.optJSONArray("assets") ?: return null
        var apk: JSONObject? = null
        var sums: String? = null
        for (i in 0 until assets.length()) {
            val asset = assets.getJSONObject(i)
            val name = asset.optString("name")
            if (name.endsWith(".apk")) apk = asset
            if (name == "SHA256SUMS.txt") sums = asset.optString("browser_download_url")
        }
        apk ?: return null
        return Release(version, apk.getString("browser_download_url"), apk.getString("name"), sums)
    }

    private fun httpGet(url: String): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 8000
        conn.readTimeout = 8000
        conn.setRequestProperty("User-Agent", "webcam-bridge/${BuildConfig.VERSION_NAME}")
        conn.setRequestProperty("Accept", "application/vnd.github+json")
        return try { conn.inputStream.bufferedReader().use { it.readText() } } finally { conn.disconnect() }
    }

    private fun offer(activity: AppCompatActivity, release: Release) {
        AlertDialog.Builder(activity)
            .setTitle(R.string.update_title)
            .setMessage(activity.getString(R.string.update_message, release.version, BuildConfig.VERSION_NAME))
            .setPositiveButton(R.string.update_install) { _, _ -> download(activity, release) }
            .setNegativeButton(R.string.update_later, null)
            .setNeutralButton(R.string.update_skip) { _, _ ->
                activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .edit().putString(KEY_SKIPPED, release.version).apply()
            }
            .show()
    }

    private fun download(activity: AppCompatActivity, release: Release) {
        val dialog = AlertDialog.Builder(activity)
            .setTitle(R.string.update_downloading)
            .setMessage("0%")
            .setCancelable(false)
            .show()
        thread(name = "UpdateDownload", isDaemon = true) {
            val result = runCatching { downloadVerified(activity, release) { pct ->
                activity.runOnUiThread { dialog.setMessage("$pct%") }
            } }
            activity.runOnUiThread {
                dialog.dismiss()
                result.onSuccess { install(activity, it) }.onFailure {
                    Toast.makeText(activity, activity.getString(R.string.update_failed, it.message), Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun downloadVerified(context: Context, release: Release, progress: (Int) -> Unit): File {
        val sums = release.sumsUrl ?: throw IllegalStateException("release has no checksums")
        val expected = httpGet(sums).lineSequence()
            .map { it.trim().split(Regex("\\s+")) }
            .firstOrNull { it.size >= 2 && it.last().trimStart('*') == release.apkName }
            ?.first() ?: throw IllegalStateException("no checksum for ${release.apkName}")

        val dir = File(context.cacheDir, "updates").apply { deleteRecursively(); mkdirs() }
        val file = File(dir, release.apkName)
        val digest = MessageDigest.getInstance("SHA-256")
        val conn = URL(release.apkUrl).openConnection() as HttpURLConnection
        conn.connectTimeout = 15000
        conn.readTimeout = 30000
        try {
            val total = conn.contentLengthLong
            var done = 0L
            var lastPct = -1
            conn.inputStream.use { input ->
                file.outputStream().use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        digest.update(buf, 0, n)
                        done += n
                        val pct = if (total > 0) (done * 100 / total).toInt() else 0
                        if (pct != lastPct) { lastPct = pct; progress(pct) }
                    }
                }
            }
        } finally {
            conn.disconnect()
        }
        val actual = digest.digest().joinToString("") { "%02x".format(it) }
        if (!actual.equals(expected, ignoreCase = true)) {
            file.delete()
            throw IllegalStateException("checksum mismatch")
        }
        return file
    }

    private fun install(activity: AppCompatActivity, apk: File) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !activity.packageManager.canRequestPackageInstalls()) {
            activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().remove(KEY_LAST_CHECK).apply()
            Toast.makeText(activity, R.string.update_allow_installs, Toast.LENGTH_LONG).show()
            activity.startActivity(
                Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${activity.packageName}"))
            )
            return
        }
        val uri = FileProvider.getUriForFile(activity, "${activity.packageName}.updates", apk)
        activity.startActivity(
            Intent(Intent.ACTION_VIEW)
                .setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }
}
