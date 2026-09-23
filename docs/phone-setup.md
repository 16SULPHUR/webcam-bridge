# Phone setup

Webcam Bridge talks to your phone over USB with `adb`, so the phone needs
**USB debugging** turned on. You only do this once.

## Turn on USB debugging

1. Open **Settings → About phone** and tap **Build number** seven times.
   You'll see "You are now a developer".
2. Go back to **Settings → System → Developer options** (on some phones it's
   directly under Settings) and turn on **USB debugging**.
3. Plug the phone into your computer and start Webcam Bridge.
4. Unlock the phone. When it asks **Allow USB debugging?**, tick
   **Always allow from this computer** and tap **Allow**.

That's it. The bridge installs the Webcam Bridge app on the phone, opens it and
starts streaming. The first time, Android asks for camera permission.

Official guide: [Android developer options](https://developer.android.com/studio/debug/dev-options).

## Phone-specific notes

| Phone | What to do |
|---|---|
| Xiaomi / Redmi / POCO | Also turn on **Install via USB** and **USB debugging (Security settings)** in Developer options, or the app can't be installed automatically. These need a Mi account and a SIM card. |
| OPPO / Realme / OnePlus (ColorOS) | Turn off **Permission monitoring** in Developer options if the install is blocked. |
| Samsung | Windows may need the [Samsung USB driver](https://developer.samsung.com/android-usb-driver). |
| Huawei / Honor | Turn on **Allow ADB debugging in charge only mode**. |
| Any phone | Use a data cable (some cables only charge) and set the USB mode to **File transfer** if the phone isn't detected. |

## Windows USB drivers

Windows 10 and 11 install a driver automatically for most phones. If
`webcam-bridge doctor` shows no phone even though it's plugged in and unlocked,
install your manufacturer's driver, or Google's generic
[USB driver](https://developer.android.com/studio/run/win-usb).

## Installing the app yourself

If you'd rather not let the bridge install the app, download
`webcam-bridge-<version>.apk` from the
[latest release](https://github.com/16SULPHUR/webcam-bridge/releases/latest)
and open it on the phone. You can keep it updated with
[Obtainium](https://github.com/ImranR98/Obtainium) by adding the repository URL.

## Using it without USB

The camera stream needs the USB connection. The phone's **Control** screen and
home-screen widget can also work over Wi-Fi: start the bridge with
`--host 0.0.0.0` and enter your computer's LAN address in the app (for example
`192.168.1.5:5134`). The dashboard has no password, so only do this on a
network you trust.
