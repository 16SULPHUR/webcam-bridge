"""
detector.py — MediaPipe hand / face landmark extraction.

Two backends, picked automatically:
  • mediapipe 0.10.x — the legacy mp.solutions Hands / FaceMesh graphs
  • mediapipe ≥ 1.0  — the Tasks API, which needs *.task model files
                       (see common.MODEL_DIRS / MODEL_URLS, or run
                       `python -m webcam_bridge.fetch models`)

Only the models the enabled mappings need are created, so a gestures-only
setup never pays for face landmarks.
"""

import sys
import time

import numpy as np

from .. import paths
from .common import MODEL_URLS, find_model
from .triggers import Face, Hand


def _log(msg: str) -> None:
    sys.stderr.write(f"[Reactions] {msg}\n")


def _to_array(landmarks) -> np.ndarray:
    points = getattr(landmarks, "landmark", landmarks)
    return np.array([[p.x, p.y, p.z] for p in points], dtype=np.float32)


class _LegacyBackend:
    """mediapipe 0.10.x — mp.solutions.*"""

    name = "solutions"

    def __init__(self, mp, need_hands: bool, need_face: bool):
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            model_complexity=0,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        ) if need_hands else None
        self._face = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) if need_face else None

    def process(self, frame_rgb):
        hands, labels, faces = [], [], []
        if self._hands is not None:
            res = self._hands.process(frame_rgb)
            if res.multi_hand_landmarks:
                hands = [_to_array(l) for l in res.multi_hand_landmarks]
                labels = [h.classification[0].label for h in (res.multi_handedness or [])]
        if self._face is not None:
            res = self._face.process(frame_rgb)
            if res.multi_face_landmarks:
                faces = [_to_array(l) for l in res.multi_face_landmarks]
        return hands, labels, faces

    def close(self):
        for model in (self._hands, self._face):
            if model is not None:
                model.close()


class _TasksBackend:
    """mediapipe ≥ 1.0 — tasks.vision.*Landmarker in VIDEO mode."""

    name = "tasks"

    def __init__(self, mp, need_hands: bool, need_face: bool):
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._mp = mp
        self._t0 = time.monotonic()
        self._last_ts = -1

        def options(model, cls, opt_cls, **kw):
            path = find_model(model)
            if not path:
                raise FileNotFoundError(
                    f"{model} not found — download it from {MODEL_URLS[model]} "
                    f"into {paths.MODELS_DIR} — or run: python -m webcam_bridge.fetch models")
            return cls.create_from_options(opt_cls(
                base_options=mp_python.BaseOptions(model_asset_path=path),
                running_mode=vision.RunningMode.VIDEO, **kw))

        self._hands = options("hand_landmarker.task", vision.HandLandmarker,
                              vision.HandLandmarkerOptions, num_hands=2) if need_hands else None
        self._face = options("face_landmarker.task", vision.FaceLandmarker,
                             vision.FaceLandmarkerOptions, num_faces=1) if need_face else None

    def _stamp(self) -> int:
        ts = int((time.monotonic() - self._t0) * 1000)
        if ts <= self._last_ts:
            ts = self._last_ts + 1
        self._last_ts = ts
        return ts

    def process(self, frame_rgb):
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                               data=np.ascontiguousarray(frame_rgb))
        ts = self._stamp()
        hands, labels, faces = [], [], []
        if self._hands is not None:
            res = self._hands.detect_for_video(image, ts)
            hands = [_to_array(l) for l in res.hand_landmarks]
            labels = [c[0].category_name for c in res.handedness]
        if self._face is not None:
            res = self._face.detect_for_video(image, ts)
            faces = [_to_array(l) for l in res.face_landmarks]
        return hands, labels, faces

    def close(self):
        for model in (self._hands, self._face):
            if model is not None:
                model.close()


class LandmarkDetector:
    def __init__(self, need_hands: bool, need_face: bool):
        self.need_hands = need_hands
        self.need_face = need_face
        self._backend = None
        self.ready = False
        self._load()

    def _load(self) -> None:
        try:
            import mediapipe as mp
        except ImportError:
            _log("mediapipe is not installed — reactions disabled (pip install mediapipe)")
            return
        backend = _LegacyBackend if hasattr(mp, "solutions") else _TasksBackend
        try:
            self._backend = backend(mp, self.need_hands, self.need_face)
            self.ready = True
            _log(f"detector ready via {backend.name} backend "
                 f"(hands={self.need_hands}, face={self.need_face})")
        except Exception as exc:
            _log(f"detector init failed: {exc}")

    def process(self, frame_rgb: np.ndarray, sensitivity: float):
        if not self.ready:
            return [], []
        raw_hands, labels, raw_faces = self._backend.process(frame_rgb)
        hands = [Hand(lm, labels[i] if i < len(labels) else "Right", sensitivity)
                 for i, lm in enumerate(raw_hands)]
        faces = [Face(lm, sensitivity) for lm in raw_faces]
        return hands, faces

    def close(self) -> None:
        try:
            if self._backend is not None:
                self._backend.close()
        except Exception:
            pass
        self._backend = None
        self.ready = False
