"""
ffmpeg_utils.py — Build FFmpeg argument lists for the decoding pipeline.

FFmpeg only handles raw H.264 decoding, scaling to the target resolution,
and optional FPS throttling. All other filters are processed dynamically in Python.
"""

from typing import List


def build_vf_filter(
    width: int,
    height: int,
    target_fps: int = 30,
) -> str:
    """
    Compose a simple scaling and FPS throttling filter.
    Keep the pipeline load low by decoding at the target FPS and resolution.
    """
    parts: List[str] = []

    # 1. FPS throttle — only add if below 30
    if target_fps < 30:
        parts.append(f"fps={target_fps}")

    # 2. Scale — ensure the raw output matches the exact configured dimensions
    parts.append(f"scale={width}:{height}")

    return ",".join(parts)


def build_vcam_args(
    ffmpeg_path: str,
    width: int,
    height: int,
    target_fps: int,
) -> List[str]:
    """
    FFmpeg args: h264 pipe → raw BGR24 pipe (for pyvirtualcam / python processor).
    """
    vf = build_vf_filter(width, height, target_fps)
    return [
        ffmpeg_path,
        "-hide_banner", "-loglevel", "info",
        "-use_wallclock_as_timestamps", "1",
        "-fflags", "nobuffer+discardcorrupt",
        "-flags", "low_delay",
        "-threads", "1",
        "-analyzeduration", "200000",
        "-probesize", "200000",
        "-f", "h264", "-i", "pipe:0",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-fps_mode", "passthrough",
        "-vf", vf,
        "pipe:1",
    ]
