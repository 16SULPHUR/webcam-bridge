"""
mp_compat.py — Selfie segmentation and face landmarks on any mediapipe version.

mediapipe 0.10.x ships the legacy `mp.solutions` graphs; mediapipe >= 1.0 only
has the Tasks API, which needs model files (see models.py). Each class here
uses whichever is available and exposes one small interface.
"""

import time

import numpy as np

from .models import ensure_model


def _has_solutions(mp) -> bool:
    return hasattr(mp, "solutions")


class _VideoClock:
    """Tasks VIDEO mode needs strictly increasing millisecond timestamps."""

    def __init__(self):
        self._t0 = time.monotonic()
        self._last = -1

    def next(self) -> int:
        ts = int((time.monotonic() - self._t0) * 1000)
        if ts <= self._last:
            ts = self._last + 1
        self._last = ts
        return ts


class SelfieSegmenter:
    """process(rgb) -> float32 person mask in [0, 1] at the input size, or None."""

    def __init__(self, log=None):
        import mediapipe as mp

        self._mp = mp
        if _has_solutions(mp):
            self.backend = "solutions"
            self._legacy = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)
            return

        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self.backend = "tasks"
        self._clock = _VideoClock()
        self._task = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=ensure_model("selfie_segmenter_landscape.tflite", log)),
            running_mode=vision.RunningMode.VIDEO,
            output_confidence_masks=True,
            output_category_mask=False,
        ))

    def process(self, frame_rgb: np.ndarray) -> np.ndarray | None:
        if self.backend == "solutions":
            return self._legacy.process(frame_rgb).segmentation_mask
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                               data=np.ascontiguousarray(frame_rgb))
        result = self._task.segment_for_video(image, self._clock.next())
        if not result.confidence_masks:
            return None
        mask = result.confidence_masks[0].numpy_view()
        if mask.ndim == 3:
            mask = mask[:, :, 0]
        return mask.astype(np.float32, copy=True)


class FaceMesh:
    """landmarks(rgb) -> the first face's 478 normalized landmarks (objects with .x/.y), or None."""

    def __init__(self, log=None):
        import mediapipe as mp

        self._mp = mp
        if _has_solutions(mp):
            self.backend = "solutions"
            self._legacy = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            return

        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self.backend = "tasks"
        self._clock = _VideoClock()
        self._task = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=ensure_model("face_landmarker.task", log)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
        ))

    def landmarks(self, frame_rgb: np.ndarray):
        if self.backend == "solutions":
            res = self._legacy.process(frame_rgb)
            return res.multi_face_landmarks[0].landmark if res.multi_face_landmarks else None
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                               data=np.ascontiguousarray(frame_rgb))
        res = self._task.detect_for_video(image, self._clock.next())
        return res.face_landmarks[0] if res.face_landmarks else None
