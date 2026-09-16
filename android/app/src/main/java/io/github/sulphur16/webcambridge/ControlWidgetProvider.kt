package io.github.sulphur16.webcambridge

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.widget.RemoteViews
import android.widget.Toast
import org.json.JSONObject
import java.util.concurrent.Executors

/**
 * ControlWidgetProvider — Home Screen AppWidget.
 * Allows quick toggling of Zoom, Brightness, Recording, and Pipeline Reset.
 */
class ControlWidgetProvider : AppWidgetProvider() {

    companion object {
        const val ACTION_WIDGET_CONTROL = "io.github.sulphur16.webcambridge.ACTION_WIDGET_CONTROL"
        const val EXTRA_CONTROL_ACTION = "control_action"

        const val ACTION_ZOOM_UP = "zoom_up"
        const val ACTION_ZOOM_DOWN = "zoom_down"
        const val ACTION_BRIGHT_UP = "bright_up"
        const val ACTION_BRIGHT_DOWN = "bright_down"
        const val ACTION_RECORD_TOGGLE = "record_toggle"
        const val ACTION_RESET = "reset"
        const val ACTION_SYNC = "sync"

        private val executor = Executors.newSingleThreadExecutor()
    }

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        for (appWidgetId in appWidgetIds) {
            updateWidget(context, appWidgetManager, appWidgetId, null)
        }
        // Poll current status on update using goAsync to keep thread alive
        val pendingResult = goAsync()
        refreshWidgetStatus(context, pendingResult)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        android.util.Log.d("WebcamWidget", "onReceive: action = ${intent.action}")

        if (intent.action == ACTION_WIDGET_CONTROL) {
            val controlAction = intent.getStringExtra(EXTRA_CONTROL_ACTION) ?: return
            android.util.Log.d("WebcamWidget", "onReceive: controlAction = $controlAction")
            val prefs = context.getSharedPreferences("WebcamPrefs", Context.MODE_PRIVATE)
            val savedIp = prefs.getString("bridge_ip", DEFAULT_BRIDGE_ADDRESS) ?: ""

            if (savedIp.isEmpty()) {
                android.util.Log.w("WebcamWidget", "onReceive: savedIp is empty")
                Toast.makeText(context, "Set Bridge IP in the app first", Toast.LENGTH_SHORT).show()
                return
            }

            val baseUrl = if (savedIp.startsWith("http://") || savedIp.startsWith("https://")) savedIp else "http://$savedIp"
            android.util.Log.d("WebcamWidget", "onReceive: baseUrl = $baseUrl")

            val pendingResult = goAsync()
            executor.execute {
                try {
                    android.util.Log.d("WebcamWidget", "Executing handleAction on background thread")
                    handleAction(context, baseUrl, controlAction)
                    android.util.Log.d("WebcamWidget", "handleAction completed successfully")
                } catch (e: Exception) {
                    android.util.Log.e("WebcamWidget", "handleAction error", e)
                    // Show error on UI thread
                    android.os.Handler(android.os.Looper.getMainLooper()).post {
                        Toast.makeText(context, "Action failed: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                } finally {
                    android.util.Log.d("WebcamWidget", "Finishing pendingResult")
                    pendingResult.finish()
                }
            }
        }
    }

    private fun handleAction(context: Context, baseUrl: String, action: String) {
        try {
            android.util.Log.d("WebcamWidget", "handleAction: sending request for $action")
            val responseStr = when (action) {
                ACTION_ZOOM_UP -> {
                    val payload = JSONObject().put("zoom_delta", 0.2)
                    NetworkHelper.postJsonSync("$baseUrl/api/config", payload.toString())
                }
                ACTION_ZOOM_DOWN -> {
                    val payload = JSONObject().put("zoom_delta", -0.2)
                    NetworkHelper.postJsonSync("$baseUrl/api/config", payload.toString())
                }
                ACTION_BRIGHT_UP -> {
                    val payload = JSONObject().put("brightness_delta", 0.1)
                    NetworkHelper.postJsonSync("$baseUrl/api/config", payload.toString())
                }
                ACTION_BRIGHT_DOWN -> {
                    val payload = JSONObject().put("brightness_delta", -0.1)
                    NetworkHelper.postJsonSync("$baseUrl/api/config", payload.toString())
                }
                ACTION_RECORD_TOGGLE -> {
                    NetworkHelper.postJsonSync("$baseUrl/api/record/toggle", "{}")
                }
                ACTION_RESET -> {
                    NetworkHelper.postJsonSync("$baseUrl/api/reconnect", "{}")
                }
                ACTION_SYNC -> {
                    NetworkHelper.getSync("$baseUrl/api/status")
                }
                else -> throw IllegalArgumentException("Unknown action: $action")
            }
            android.util.Log.d("WebcamWidget", "handleAction: request succeeded, parsing response")
            val statusJson = JSONObject(responseStr)
            updateAllWidgets(context, statusJson)
        } catch (e: Exception) {
            android.util.Log.e("WebcamWidget", "handleAction: request failed", e)
            updateAllWidgets(context, null)
            throw Exception("Action failed. Verify Bridge PC is running: ${e.message}")
        }
    }

    private fun refreshWidgetStatus(context: Context, pendingResult: PendingResult? = null) {
        val prefs = context.getSharedPreferences("WebcamPrefs", Context.MODE_PRIVATE)
        val savedIp = prefs.getString("bridge_ip", DEFAULT_BRIDGE_ADDRESS) ?: ""
        if (savedIp.isEmpty()) {
            pendingResult?.finish()
            return
        }

        val baseUrl = if (savedIp.startsWith("http://") || savedIp.startsWith("https://")) savedIp else "http://$savedIp"

        executor.execute {
            try {
                val finalStatusStr = NetworkHelper.getSync("$baseUrl/api/status")
                updateAllWidgets(context, JSONObject(finalStatusStr))
            } catch (e: Exception) {
                updateAllWidgets(context, null)
            } finally {
                pendingResult?.finish()
            }
        }
    }

    private fun updateAllWidgets(context: Context, statusJson: JSONObject?) {
        val appWidgetManager = AppWidgetManager.getInstance(context)
        val thisWidget = ComponentName(context, ControlWidgetProvider::class.java)
        val appWidgetIds = appWidgetManager.getAppWidgetIds(thisWidget)
        for (appWidgetId in appWidgetIds) {
            updateWidget(context, appWidgetManager, appWidgetId, statusJson)
        }
    }

    private fun updateWidget(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetId: Int,
        statusJson: JSONObject?
    ) {
        val views = RemoteViews(context.packageName, R.layout.widget_control)

        // Setup PendingIntents for buttons
        views.setOnClickPendingIntent(R.id.widget_btn_zoom_up, getPendingIntent(context, ACTION_ZOOM_UP, appWidgetId))
        views.setOnClickPendingIntent(R.id.widget_btn_zoom_down, getPendingIntent(context, ACTION_ZOOM_DOWN, appWidgetId))
        views.setOnClickPendingIntent(R.id.widget_btn_brightness_up, getPendingIntent(context, ACTION_BRIGHT_UP, appWidgetId))
        views.setOnClickPendingIntent(R.id.widget_btn_brightness_down, getPendingIntent(context, ACTION_BRIGHT_DOWN, appWidgetId))
        views.setOnClickPendingIntent(R.id.widget_btn_record, getPendingIntent(context, ACTION_RECORD_TOGGLE, appWidgetId))
        views.setOnClickPendingIntent(R.id.widget_btn_reset, getPendingIntent(context, ACTION_RESET, appWidgetId))
        views.setOnClickPendingIntent(R.id.widget_btn_sync, getPendingIntent(context, ACTION_SYNC, appWidgetId))

        // Update UI based on status
        if (statusJson != null) {
            val androidConnected = statusJson.optBoolean("androidConnected", false)
            val isRecording = statusJson.optBoolean("recording", false)

            if (androidConnected) {
                views.setTextViewText(R.id.widget_tv_status, "Live")
                views.setInt(R.id.widget_status_dot, "setBackgroundResource", R.drawable.widget_dot_active)
            } else {
                views.setTextViewText(R.id.widget_tv_status, "No Stream")
                views.setInt(R.id.widget_status_dot, "setBackgroundResource", R.drawable.widget_dot_ready)
            }

            // Update Zoom and Brightness values if available in config
            val config = statusJson.optJSONObject("config")
            if (config != null) {
                val zoom = config.optDouble("zoom", 1.0)
                val brightness = config.optDouble("brightness", 0.0)
                views.setTextViewText(R.id.widget_tv_zoom_val, String.format(java.util.Locale.US, "%.1fx", zoom))
                views.setTextViewText(R.id.widget_tv_brightness_val, String.format(java.util.Locale.US, "%+.1f", brightness))
            } else {
                views.setTextViewText(R.id.widget_tv_zoom_val, "Zoom")
                views.setTextViewText(R.id.widget_tv_brightness_val, "Bright")
            }

            // Update REC button state
            if (isRecording) {
                views.setTextViewText(R.id.widget_btn_record, "STOP")
                views.setInt(R.id.widget_btn_record, "setBackgroundResource", R.drawable.widget_btn_rec_inactive_bg)
            } else {
                views.setTextViewText(R.id.widget_btn_record, "REC")
                views.setInt(R.id.widget_btn_record, "setBackgroundResource", R.drawable.widget_btn_rec_bg)
            }
        } else {
            views.setTextViewText(R.id.widget_tv_status, "Offline")
            views.setInt(R.id.widget_status_dot, "setBackgroundResource", R.drawable.widget_dot_inactive)
            views.setTextViewText(R.id.widget_tv_zoom_val, "Zoom")
            views.setTextViewText(R.id.widget_tv_brightness_val, "Bright")
            views.setTextViewText(R.id.widget_btn_record, "REC")
            views.setInt(R.id.widget_btn_record, "setBackgroundResource", R.drawable.widget_btn_rec_bg)
        }

        appWidgetManager.updateAppWidget(appWidgetId, views)
    }

    private fun getPendingIntent(context: Context, action: String, widgetId: Int): PendingIntent {
        val intent = Intent(context, ControlWidgetProvider::class.java).apply {
            this.action = ACTION_WIDGET_CONTROL
            putExtra(EXTRA_CONTROL_ACTION, action)
        }
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        // Use a unique request code per action/widget to avoid intent caching issues
        val requestCode = action.hashCode() + widgetId
        return PendingIntent.getBroadcast(context, requestCode, intent, flags)
    }
}
