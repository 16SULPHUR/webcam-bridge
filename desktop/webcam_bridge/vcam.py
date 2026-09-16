"""
vcam.py — Virtual camera output.

Backends:
  builtin  "Webcam Bridge" DirectShow camera (Windows, vcam/windows/). Needs a
           one-time `webcam-bridge camera install` (admin prompt).
  obs      OBS Virtual Camera through pyvirtualcam (Windows / macOS), or
           v4l2loopback on Linux.
  auto     builtin when it is installed, otherwise obs.

This module must stay importable without numpy/cv2 for the CLI and dashboard;
frame conversion imports them lazily.
"""

import ctypes
import os
import shutil
import sys

from . import paths

CLSID = "{F23C4002-953E-4221-AD81-B03CB81F72B2}"
DEVICE_NAME = "Webcam Bridge"
DLL_NAME = "webcam_bridge_cam.dll"
BACKENDS = ("auto", "builtin", "obs")

IS_WINDOWS = sys.platform == "win32"
ARCHES = ("x64", "x86")
ERROR_CANCELLED = 1223  # user declined the UAC prompt


class VirtualCameraError(RuntimeError):
    pass


# ── Installation (Windows) ────────────────────────────────────────────────────

def bundled_dll(arch: str) -> str:
    return os.path.join(paths.VCAM_BUNDLED_DIR, arch, DLL_NAME)


def installed_dll(arch: str) -> str:
    return os.path.join(paths.VCAM_INSTALL_DIR, arch, DLL_NAME)


def registered_path(arch: str) -> str | None:
    """DLL path registered for our CLSID in the given registry view, if any."""
    if not IS_WINDOWS:
        return None
    import winreg
    view = winreg.KEY_WOW64_64KEY if arch == "x64" else winreg.KEY_WOW64_32KEY
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            rf"SOFTWARE\Classes\CLSID\{CLSID}\InprocServer32",
                            0, winreg.KEY_READ | view) as key:
            value, _ = winreg.QueryValueEx(key, "")
            return value or None
    except OSError:
        return None


def status() -> dict:
    """Everything the CLI and dashboard show about the built-in camera."""
    info = {"platform": sys.platform, "supported": IS_WINDOWS, "name": DEVICE_NAME, "arches": {}}
    for arch in ARCHES:
        reg = registered_path(arch)
        info["arches"][arch] = {
            "bundled": os.path.isfile(bundled_dll(arch)),
            "registered": bool(reg and os.path.isfile(reg)),
            "path": reg,
        }
    info["installed"] = info["arches"]["x64"]["registered"]
    info["available"] = info["installed"] or os.path.isfile(bundled_dll("x64"))
    return info


def _regsvr32(arch: str) -> str:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    # 32-bit regsvr32 lives in SysWOW64 on 64-bit Windows.
    folder = "System32" if arch == "x64" else "SysWOW64"
    return os.path.join(windir, folder, "regsvr32.exe")


def elevated_command_line(commands: list[list[str]]) -> str:
    """cmd.exe arguments that run each command in turn, stopping at the first failure."""
    def arg(part: str) -> str:
        return part if part.startswith("/") else f'"{part}"'

    chain = " && ".join(" ".join(arg(p) for p in cmd) for cmd in commands)
    return f'/s /c "{chain}"'


def _run_elevated(commands: list[list[str]]) -> int:
    """Run commands through one elevated cmd.exe (a single UAC prompt); returns the exit code."""
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
        ]

    SEE_MASK_NOCLOSEPROCESS = 0x40
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "cmd.exe")
    info.lpParameters = elevated_command_line(commands)
    info.nShow = 0  # SW_HIDE

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        return ctypes.get_last_error() or 1
    try:
        kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        return code.value
    finally:
        kernel32.CloseHandle(info.hProcess)


def install() -> str:
    """Copy the DLLs to ProgramData and register them. Returns a status message."""
    if not IS_WINDOWS:
        raise VirtualCameraError("The built-in camera is Windows-only. Use OBS or v4l2loopback instead.")
    commands = []
    for arch in ARCHES:
        src = bundled_dll(arch)
        if not os.path.isfile(src):
            if arch == "x64":
                raise VirtualCameraError(
                    f"{DLL_NAME} not found in {paths.VCAM_BUNDLED_DIR}. "
                    "Run: python -m webcam_bridge.fetch vcam")
            continue  # 32-bit support is optional
        dest = installed_dll(arch)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        try:
            shutil.copy2(src, dest)
        except PermissionError as exc:
            raise VirtualCameraError(
                f"Could not replace {dest} — close apps that are using the camera and retry.") from exc
        commands.append([_regsvr32(arch), "/s", dest])

    code = _run_elevated(commands)
    if code == ERROR_CANCELLED:
        raise VirtualCameraError("Installation cancelled at the administrator prompt.")
    if code != 0:
        raise VirtualCameraError(f"regsvr32 failed with exit code {code}.")
    return f'"{DEVICE_NAME}" camera installed. Restart camera apps (Zoom, Teams, browsers) to see it.'


def uninstall() -> str:
    if not IS_WINDOWS:
        raise VirtualCameraError("The built-in camera is Windows-only.")
    commands = []
    for arch in ARCHES:
        reg = registered_path(arch)
        if reg and os.path.isfile(reg):
            commands.append([_regsvr32(arch), "/u", "/s", reg])
    if not commands:
        return "The camera is not installed."
    code = _run_elevated(commands)
    if code == ERROR_CANCELLED:
        raise VirtualCameraError("Uninstall cancelled at the administrator prompt.")
    if code != 0:
        raise VirtualCameraError(f"regsvr32 failed with exit code {code}.")
    return f'"{DEVICE_NAME}" camera removed.'


# ── Sending frames ────────────────────────────────────────────────────────────

class _BuiltinCamera:
    """ctypes wrapper around the softcam sender API in webcam_bridge_cam.dll."""

    def __init__(self, width: int, height: int, fps: float):
        dll_path = registered_path("x64") if sys.maxsize > 2**32 else registered_path("x86")
        if not dll_path or not os.path.isfile(dll_path):
            dll_path = bundled_dll("x64" if sys.maxsize > 2**32 else "x86")
        if not os.path.isfile(dll_path):
            raise VirtualCameraError(f"{DLL_NAME} not found")

        self._dll = ctypes.CDLL(dll_path)
        self._dll.scCreateCamera.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_float]
        self._dll.scCreateCamera.restype = ctypes.c_void_p
        self._dll.scDeleteCamera.argtypes = [ctypes.c_void_p]
        self._dll.scDeleteCamera.restype = None
        self._dll.scSendFrame.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._dll.scSendFrame.restype = None
        self._dll.scIsConnected.argtypes = [ctypes.c_void_p]
        self._dll.scIsConnected.restype = ctypes.c_bool

        # softcam requires dimensions that are multiples of four.
        self.width = max(4, width - width % 4)
        self.height = max(4, height - height % 4)
        # framerate 0: never sleep inside scSendFrame — our input is already
        # paced by the phone, and blocking would stall the preview.
        self._handle = self._dll.scCreateCamera(self.width, self.height, 0.0)
        if not self._handle:
            raise VirtualCameraError("could not create the camera (is another Webcam Bridge running?)")
        self.device = DEVICE_NAME

    @property
    def connected(self) -> bool:
        return bool(self._handle) and self._dll.scIsConnected(self._handle)

    def send(self, frame_rgb) -> None:
        import cv2
        import numpy as np

        h, w = frame_rgb.shape[:2]
        if (w, h) != (self.width, self.height):
            frame_rgb = frame_rgb[: self.height, : self.width]
        bgr = np.ascontiguousarray(frame_rgb[:, :, ::-1])
        if bgr.shape[:2] != (self.height, self.width):
            bgr = cv2.resize(bgr, (self.width, self.height))
        self._dll.scSendFrame(self._handle, bgr.ctypes.data)

    def close(self) -> None:
        if self._handle:
            self._dll.scDeleteCamera(self._handle)
            self._handle = None


class _PyVirtualCam:
    def __init__(self, width: int, height: int, fps: float):
        try:
            import pyvirtualcam
        except ImportError as exc:
            raise VirtualCameraError("pyvirtualcam is not installed") from exc
        kwargs = {"backend": "obs"} if sys.platform == "win32" else {}
        try:
            self._cam = pyvirtualcam.Camera(width=width, height=height, fps=fps,
                                            print_fps=False, **kwargs)
        except Exception as exc:
            hint = " Install/start OBS Virtual Camera, or run `webcam-bridge camera install`." \
                if sys.platform == "win32" else ""
            raise VirtualCameraError(f"{exc}.{hint}") from exc
        self.width = width
        self.height = height
        self.device = self._cam.device

    def send(self, frame_rgb) -> None:
        self._cam.send(frame_rgb)

    def close(self) -> None:
        self._cam.close()


def resolve_backend(requested: str) -> str:
    if requested not in BACKENDS:
        requested = "auto"
    if requested != "auto":
        return requested
    if IS_WINDOWS and status()["installed"]:
        return "builtin"
    return "obs"


def open_camera(width: int, height: int, fps: float, backend: str = "auto"):
    """Open a virtual camera; returns an object with send(rgb), close(), width, height, device."""
    chosen = resolve_backend(backend)
    if chosen == "builtin":
        if not IS_WINDOWS:
            raise VirtualCameraError("The built-in camera is Windows-only.")
        return _BuiltinCamera(width, height, fps)
    return _PyVirtualCam(width, height, fps)
