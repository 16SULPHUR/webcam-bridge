# Webcam Bridge virtual camera (Windows)

A DirectShow "video input device" named **Webcam Bridge** that apps such as
Zoom, Teams, Discord, Chrome/Meet and OBS can select. The desktop bridge pushes
frames into it through shared memory, so OBS is no longer required.

It is built from [softcam](https://github.com/tshino/softcam) (MIT), vendored in
`third_party/softcam` from commit `5113173d22a6aac4c9f30c36bb2cf900afef05f4`.

## Local changes to softcam

Marked with `[webcam-bridge]` comments:

- `src/softcam/softcam.cpp` — our own CLSID `{F23C4002-953E-4221-AD81-B03CB81F72B2}`
  and device name `Webcam Bridge`.
- `src/softcamcore/FrameBuffer.cpp` — our own mutex / shared-memory names, so
  another softcam-based app on the same machine cannot clash with us.

Only the library sources were vendored (no tests, examples or VS projects);
the build uses `CMakeLists.txt` with a static C runtime.

## Build

Requires Visual Studio 2019+ with the *Desktop development with C++* workload.

```bat
cmake -S vcam/windows -B build/vcam-x64 -A x64
cmake --build build/vcam-x64 --config Release
cmake -S vcam/windows -B build/vcam-x86 -A Win32
cmake --build build/vcam-x86 --config Release
```

Copy the results to `desktop/webcam_bridge/bin/x64/` and `bin/x86/`. CI does
this for every pull request and release, so contributors who only touch Python
can instead run `python -m webcam_bridge.fetch vcam`.

## Install / uninstall

```bat
webcam-bridge camera install     :: copies DLLs to %ProgramData%\WebcamBridge\vcam and runs regsvr32 (UAC)
webcam-bridge camera status
webcam-bridge camera uninstall
```

The 64-bit DLL serves 64-bit apps and the 32-bit DLL serves 32-bit apps.
Apps that were open during installation must be restarted to see the camera.

## How it works

`webcam_bridge/vcam.py` loads the DLL with `ctypes` and calls the softcam
sender API (`scCreateCamera`, `scSendFrame`, `scDeleteCamera`) with top-down
BGR frames. Width and height are rounded down to multiples of four. When an app
opens the camera, Windows loads the same DLL into that app, which reads the
latest frame from shared memory.

- **Start the bridge before selecting the camera** in an app: without a
  running sender the device has no format and apps report it as unavailable.
- If the bridge stops mid-call, the app keeps showing the last frame, darkened,
  and resumes when the bridge sends again.
- After changing the resolution or rotation, re-select the camera in the app
  if the picture does not come back.

## Limitations

- DirectShow only: the Windows Camera app and some Microsoft Store apps use
  Media Foundation exclusively and won't list it. A Media Foundation backend
  (`MFCreateVirtualCamera`, Windows 11) is a possible future addition.
- One sender at a time.
