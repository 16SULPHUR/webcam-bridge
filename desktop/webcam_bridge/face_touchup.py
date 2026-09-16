"""
face_touchup.py — MediaPipe Face Mesh based skin-smoothing touch-up.

Builds a skin-region mask from facial landmarks (face oval, minus eyes,
eyebrows, lips, and nostrils), applies a bilateral filter within that mask,
and blends the result back at configurable strength (0-1).

This replicates the subtle "Meet/Zoom beauty" effect — just enough smoothing
to look natural without the plasticky over-smoothed look.

Requires: pip install mediapipe
"""

import sys
import cv2
import numpy as np


# ---------------------------------------------------------------------------
# MediaPipe face mesh landmark index sets
# ---------------------------------------------------------------------------

# Outer face oval (36 points)
FACE_OVAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
    397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
    172,  58, 132,  93, 234, 127, 162,  21,  54, 103,  67, 109,
]

# Left eye contour (exclusion zone)
LEFT_EYE = [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466]

# Right eye contour (exclusion zone)
RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 246, 161, 160, 159, 158, 157, 173]

# Left eyebrow (exclusion)
LEFT_BROW = [276, 283, 282, 295, 285, 300, 293, 334, 296, 336]

# Right eyebrow (exclusion)
RIGHT_BROW = [46, 53, 52, 65, 55, 70, 63, 105, 66, 107]

# Lips outer contour (exclusion)
LIPS = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146]

# Nostril region (exclusion) — approximate
NOSTRILS = [48, 115, 220, 45, 275, 440, 344, 278]


def _pts(landmarks, indices, w, h):
    """Extract pixel coordinates for given landmark indices."""
    return np.array(
        [[int(landmarks[i].x * w), int(landmarks[i].y * h)] for i in indices],
        dtype=np.int32,
    )


class FaceTouchup:
    def __init__(self):
        self._face_mesh = None
        self._load()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _load(self):
        try:
            from .mp_compat import FaceMesh
            self._face_mesh = FaceMesh(log=lambda m: sys.stderr.write(m + "\n"))
            sys.stderr.write(f"[FaceTouchup] Face landmarks loaded ({self._face_mesh.backend} backend).\n")
        except Exception as e:
            sys.stderr.write(f"[FaceTouchup] ERROR loading Face Mesh: {e}\n")

    # ------------------------------------------------------------------
    # Per-frame processing
    # ------------------------------------------------------------------

    def process_frame(self, frame_rgb: np.ndarray, strength: float = 0.35) -> np.ndarray:
        """
        Args:
            frame_rgb: uint8 RGB [H, W, 3]
            strength:  blend opacity 0.0 (off) → 1.0 (full)

        Returns:
            Processed frame_rgb with skin smoothing applied.
        """
        if self._face_mesh is None or strength < 0.01:
            return frame_rgb

        try:
            h, w = frame_rgb.shape[:2]
            lm = self._face_mesh.landmarks(frame_rgb)
            if lm is None:
                return frame_rgb

            # Calculate face bounding box from outer face oval
            oval = _pts(lm, FACE_OVAL, w, h)
            x, y, w_box, h_box = cv2.boundingRect(oval)

            # Clip bounds to image dimensions with a safe margin
            margin = 15
            x1 = max(0, x - margin)
            y1 = max(0, y - margin)
            x2 = min(w, x + w_box + margin)
            y2 = min(h, y + h_box + margin)

            crop_w = x2 - x1
            crop_h = y2 - y1

            if crop_w <= 10 or crop_h <= 10:
                return frame_rgb

            # Crop face region
            face_crop = frame_rgb[y1:y2, x1:x2]

            # ── Build local skin mask ─────────────────────────────────────
            skin_mask = np.zeros((crop_h, crop_w), dtype=np.uint8)

            # Fill face oval relative to crop origin
            oval_rel = oval - np.array([x1, y1])
            hull = cv2.convexHull(oval_rel)
            cv2.fillConvexPoly(skin_mask, hull, 255)

            # Punch out exclusion zones relative to crop origin
            excl_kernel = np.ones((5, 5), np.uint8)
            for region in (LEFT_EYE, RIGHT_EYE, LEFT_BROW, RIGHT_BROW, LIPS, NOSTRILS):
                pts_rel = _pts(lm, region, w, h) - np.array([x1, y1])
                excl_mask = np.zeros((crop_h, crop_w), dtype=np.uint8)
                cv2.fillConvexPoly(excl_mask, cv2.convexHull(pts_rel), 255)
                excl_mask = cv2.dilate(excl_mask, excl_kernel, iterations=1)
                skin_mask = cv2.bitwise_and(skin_mask, cv2.bitwise_not(excl_mask))

            skin_mask = cv2.erode(skin_mask, np.ones((3, 3), np.uint8), iterations=1)

            # ── Apply bilateral filter on downscaled face crop ────────────
            # Downscale by 2x to massively speed up bilateral filtering (O(N^2) complexity)
            small_w = max(4, crop_w // 2)
            small_h = max(4, crop_h // 2)
            small_crop = cv2.resize(face_crop, (small_w, small_h), interpolation=cv2.INTER_LINEAR)

            # Stronger bilateral filter parameters for a distinct, high-quality smooth look
            smoothed_small = cv2.bilateralFilter(small_crop, d=7, sigmaColor=85, sigmaSpace=85)

            # Upscale back to cropped resolution
            smoothed_face = cv2.resize(smoothed_small, (crop_w, crop_h), interpolation=cv2.INTER_LINEAR)

            # ── Soft-edge blend local mask ────────────────────────────────
            # Gaussian blur size is scaled down proportionally to the smaller local crop
            soft_mask = cv2.GaussianBlur(skin_mask.astype(np.float32) / 255.0, (11, 11), 0)
            soft_mask_3d = np.stack([soft_mask] * 3, axis=-1) * float(strength)

            # ── Composite face crop ───────────────────────────────────────
            result_face = (
                face_crop.astype(np.float32) * (1.0 - soft_mask_3d)
                + smoothed_face.astype(np.float32) * soft_mask_3d
            ).astype(np.uint8)

            # Paste processed crop back into a copy of the main frame
            result = frame_rgb.copy()
            result[y1:y2, x1:x2] = result_face
            return result

        except Exception as e:
            sys.stderr.write(f"[FaceTouchup] Error: {e}\n")
            return frame_rgb

