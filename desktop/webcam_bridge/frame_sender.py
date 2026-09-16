"""
frame_sender.py — Python stream processor.

Reads raw BGR24 video frames from stdin (piped from FFmpeg),
applies dynamic adjustments (zoom, mirror, orientation, color, unsharp,
and background blur/replacement) in real-time, and outputs them to the
OBS Virtual Camera and web preview stdout.

Performance improvements over v1:
  - MediaPipe `model_selection=1` (Landscape, 256x144) - ~44% fewer FLOPs
  - Frames pre-resized to 256x144 before inference (skip internal MP resize)
  - Exponential Moving Average (EMA) on segmentation mask - eliminates flicker
  - Background image cached and only reloaded when filename changes
"""

import os
import sys

# Launched as a script by pipeline.py — make the package importable.
package_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_parent not in sys.path:
    sys.path.insert(0, package_parent)

# Critical: Redirect standard output at the OS level to stderr
# This prevents C++ libraries (MediaPipe, TensorFlow Lite, OpenCV) from writing
# info/warning logs to file descriptor 1 (stdout), which would corrupt the
# binary framing protocol and cause pipeline deadlocks.
try:
    stdout_fd = os.dup(1)
    binary_stdout = os.fdopen(stdout_fd, 'wb')
    os.dup2(2, 1)
except Exception as e:
    sys.stderr.write(f"[PySender] WARNING: Failed stdout OS redirect: {e}\n")
    binary_stdout = sys.stdout.buffer

import numpy as np
import threading
import time
import cv2
import json

try:
    import pyvirtualcam
except ImportError:
    pyvirtualcam = None

# We read config path from argument
if len(sys.argv) < 2:
    sys.stderr.write("[PySender] ERROR: config.json path must be passed as the first argument.\n")
    sys.exit(1)

config_path = sys.argv[1]

from webcam_bridge import paths  # noqa: E402
from webcam_bridge.image_io import imread  # noqa: E402
RX_STATUS_PREFIX = "@@RX "

# Dynamic settings (default values)
WIDTH = 1280
HEIGHT = 720
FPS = 30
mirror = False
orientation = 0
zoom = 1.0
brightness = 0.0
contrast = 1.0
saturation = 1.0
sharpness = 0.0
blur = 0
vcam_enabled = True
bg_mode = "none"   # "none" | "blur" | "replace"
bg_image = ""      # filename within backgrounds/
oneko_enabled = True
oneko_size = 2.0
custom_oneko_enabled = False
custom_oneko_skin = "socks"
custom_pets_config = []
segmentation_engine = "mediapipe"
rvm_segmenter = None
rvm_downsample_ratio = 0.25
face_touchup_processor = None
face_touchup_enabled = False
face_touchup_strength = 0.35
reactions_cfg = {}
reaction_engine = None

_prev_settings = {}

def log(msg):
    print(msg, file=sys.stderr, flush=True)


def load_config(initial=False):
    global WIDTH, HEIGHT, mirror, orientation, zoom, brightness, contrast
    global saturation, sharpness, blur, vcam_enabled, bg_mode, bg_image, oneko_enabled, oneko_size
    global custom_oneko_enabled, custom_oneko_skin, custom_pets_config, segmentation_engine, _prev_settings
    global rvm_downsample_ratio, face_touchup_enabled, face_touchup_strength, rvm_segmenter
    global reactions_cfg
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)

        # Resolution is parsed only once at startup or pipeline restarts
        if initial:
            res_str = cfg.get("resolution", "640x360")
            if not res_str or res_str == "auto":
                res_str = "1280x720"
            w, h = res_str.split("x")
            WIDTH = int(w)
            HEIGHT = int(h)

        mirror      = cfg.get("mirror", False)
        orientation = int(cfg.get("orientation", 0))
        zoom        = float(cfg.get("zoom", 1.0))
        brightness  = float(cfg.get("brightness", 0.0))
        contrast    = float(cfg.get("contrast", 1.0))
        saturation  = float(cfg.get("saturation", 1.0))
        sharpness   = float(cfg.get("sharpness", 0.0))
        blur        = int(cfg.get("blur", 0))
        vcam_enabled = cfg.get("vcamEnabled", True)
        bg_mode     = cfg.get("bgMode", "none")
        bg_image    = cfg.get("bgImage", "")
        oneko_enabled = cfg.get("onekoEnabled", True)
        oneko_size  = float(cfg.get("onekoSize", 2.0))
        custom_oneko_enabled = cfg.get("customOnekoEnabled", False)
        custom_oneko_skin  = cfg.get("customOnekoSkin", "socks")
        prev_engine = segmentation_engine
        segmentation_engine = cfg.get("segmentationEngine", "mediapipe")
        rvm_downsample_ratio = float(cfg.get("rvmDownsampleRatio", 0.25))
        face_touchup_enabled = cfg.get("faceTouchupEnabled", False)
        face_touchup_strength = float(cfg.get("faceTouchupStrength", 35)) / 100.0
        reactions_cfg = cfg.get("reactions") or {}
        # Reset RVM recurrent states when engine switches to/from RVM
        if rvm_segmenter is not None and prev_engine != segmentation_engine:
            rvm_segmenter.reset_states()
        
        custom_pets_config = cfg.get("customPets", [])
        if not isinstance(custom_pets_config, list):
            custom_pets_config = []
            
        # Fallback for backward compatibility
        if not custom_pets_config:
            custom_pets_config = [{"skin": custom_oneko_skin, "enabled": custom_oneko_enabled}]

        current_state = {
            "mirror": mirror, "orientation": orientation, "zoom": zoom,
            "brightness": brightness, "contrast": contrast, "saturation": saturation,
            "sharpness": sharpness, "blur": blur, "vcam_enabled": vcam_enabled,
            "bg_mode": bg_mode, "bg_image": bg_image,
            "oneko_enabled": oneko_enabled,
            "oneko_size": oneko_size,
            "custom_pets": json.dumps(custom_pets_config),
            "segmentation_engine": segmentation_engine,
            "rvm_downsample_ratio": rvm_downsample_ratio,
            "face_touchup_enabled": face_touchup_enabled,
            "face_touchup_strength": face_touchup_strength,
            "reactions": json.dumps(reactions_cfg, sort_keys=True),
        }

        if not initial and current_state != _prev_settings:
            _prev_settings = current_state
            log(f"[PySender] Config updated: Zoom={zoom}x, Mirror={mirror}, "
                f"Ori={orientation}deg, Blur={blur}, BgMode={bg_mode}, BgImage='{bg_image}', Oneko={oneko_enabled}, OnekoSize={oneko_size}, CustomPets={custom_pets_config}")
        elif initial:
            _prev_settings = current_state
    except Exception as e:
        log(f"[PySender] Error loading config: {e}")

# Initial load of configuration
load_config(initial=True)

FRAME_SIZE = WIDTH * HEIGHT * 3

vcam_lock = threading.Lock()
py_cam = None
running = True

# MediaPipe segmenter (lazy load)
segmenter = None
segmenter_loading = False
segmenter_thread = None

# Shared state for segmentation thread
seg_input_lock = threading.Lock()
seg_input_frame = None        # latest frame_rgb resized to MP_W, MP_H (MediaPipe/BgMattingV2)
seg_input_full_frame = None   # latest full-res frame_rgb (RVM)
seg_input_w = 0
seg_input_h = 0

seg_output_lock = threading.Lock()
seg_output_mask = None      # latest upsampled float32 3-channel mask

# Landscape model native resolution (faster: ~44% fewer FLOPs vs. model 0)
MP_W, MP_H = 256, 144

# EMA mask state
_ema_mask = None   # float32, same shape as processed frame
_EMA_ALPHA = 0.65  # weight for the new frame's mask (higher = faster tracking, less smoothing)

def segmenter_thread_func():
    global segmenter, rvm_segmenter
    global seg_output_mask, _ema_mask
    log("[PySender] Segmenter thread active.")
    while running:
        # ── Engine readiness checks ──────────────────────────────────────
        if segmentation_engine == "mediapipe":
            if segmenter is None:
                time.sleep(0.05)
                continue

        elif segmentation_engine == "rvm":
            if rvm_segmenter is None:
                try:
                    from webcam_bridge.rvm_matting import RVMSegmenter
                    rvm_segmenter = RVMSegmenter(downsample_ratio=rvm_downsample_ratio)
                except Exception as e:
                    sys.stderr.write(f"[PySender] ERROR loading RVM: {e}\n")
                    time.sleep(1.0)
                    continue
            if rvm_segmenter.model is None:
                time.sleep(0.1)
                continue
        else:
            time.sleep(0.05)
            continue

        # ── Read the correct input queue ─────────────────────────────────
        frame_to_process = None
        target_w, target_h = 0, 0
        with seg_input_lock:
            if segmentation_engine == "rvm":
                if seg_input_full_frame is not None:
                    frame_to_process = seg_input_full_frame.copy()
                    target_w = seg_input_w
                    target_h = seg_input_h
                    globals()['seg_input_full_frame'] = None
            else:
                if seg_input_frame is not None:
                    frame_to_process = seg_input_frame.copy()
                    target_w = seg_input_w
                    target_h = seg_input_h
                    globals()['seg_input_frame'] = None

        if frame_to_process is None:
            time.sleep(0.005)
            continue

        # ── Run inference ────────────────────────────────────────────────
        try:
            mask_full = None
            if segmentation_engine == "mediapipe":
                results = segmenter.process(frame_to_process)
                if results.segmentation_mask is not None:
                    mask_small = results.segmentation_mask
                    mask_full = cv2.resize(mask_small, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
                    # mediapipe returns [H, W] — already 2D

            elif segmentation_engine == "rvm":
                mask_full = rvm_segmenter.process_frame(frame_to_process, rvm_downsample_ratio)
                # rvm returns [H, W, 1] — squeeze to 2D
                if mask_full is not None and mask_full.ndim == 3:
                    mask_full = mask_full[:, :, 0]

            if mask_full is not None:
                # RVM is temporally stable via recurrent states — skip EMA.
                # MediaPipe is single-frame model — apply EMA.
                if segmentation_engine == "rvm":
                    final_mask = mask_full.astype(np.float32)
                else:
                    if _ema_mask is None or _ema_mask.shape[:2] != (target_h, target_w):
                        _ema_mask = mask_full.astype(np.float32)
                    else:
                        _ema_mask = (_EMA_ALPHA * mask_full.astype(np.float32)
                                     + (1.0 - _EMA_ALPHA) * _ema_mask)
                    final_mask = _ema_mask

                # Stack to [H, W, 3] for compositing
                mask_3d = np.stack((final_mask,) * 3, axis=-1)
                with seg_output_lock:
                    seg_output_mask = mask_3d

        except Exception as e:
            sys.stderr.write(f"[PySender] Segmenter thread exception: {e}\n")
            time.sleep(0.02)


def load_mediapipe_worker():
    global segmenter, segmenter_loading
    log("[PySender] Loading MediaPipe Selfie Segmentation (landscape model)...")
    try:
        import mediapipe as mp
        mp_selfie = mp.solutions.selfie_segmentation
        segmenter = mp_selfie.SelfieSegmentation(model_selection=1)
        log("[PySender] MediaPipe Selfie Segmentation loaded successfully.")
    except Exception as exc:
        log(f"[PySender] ERROR loading MediaPipe: {exc}")
    finally:
        segmenter_loading = False


# Background image cache
_cached_bg_filename = ""
_cached_bg_rgb = None

def get_background_rgb(filename, target_w, target_h):
    """Load and cache the selected background image, resized to the current frame dimensions."""
    global _cached_bg_filename, _cached_bg_rgb
    if filename != _cached_bg_filename:
        _cached_bg_filename = filename
        _cached_bg_rgb = None
        if filename:
            path = paths.find_background(filename)
            if path:
                img = imread(path)
                if img is not None:
                    _cached_bg_rgb = img[:, :, ::-1]  # BGR to RGB
                    log(f"[PySender] Background loaded: {filename}")
                else:
                    log(f"[PySender] WARNING: Could not read background image: {path}")
            else:
                log(f"[PySender] WARNING: Background file not found: {filename}")

    if _cached_bg_rgb is None:
        return None
    h, w = _cached_bg_rgb.shape[:2]
    if w != target_w or h != target_h:
        _cached_bg_rgb = cv2.resize(_cached_bg_rgb, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
    return _cached_bg_rgb

# Color EQ precomputation table
last_applied_brightness = None
last_applied_contrast = None
lut = None

def apply_color_eq(frame_bgr, b, c):
    global last_applied_brightness, last_applied_contrast, lut
    if last_applied_brightness != b or last_applied_contrast != c:
        last_applied_brightness = b
        last_applied_contrast = c
        x = np.arange(256, dtype=np.float32)
        lut_data = (x - 128.0) * c + 128.0 + b * 255.0
        lut = np.clip(lut_data, 0, 255).astype(np.uint8)
    return cv2.LUT(frame_bgr, lut)


COORDS_TO_FILE = {
    # Scratch Wall
    (0, 0): "nscratch1",
    (0, 1): "nscratch2",
    (7, 1): "sscratch1",
    (6, 2): "sscratch2",
    (4, 0): "wscratch1",
    (4, 1): "wscratch2",
    (2, 2): "escratch1",
    (2, 3): "escratch2",
    # Runs
    (1, 2): "nrun1",
    (1, 3): "nrun2",
    (0, 2): "nerun1",
    (0, 3): "nerun2",
    (3, 0): "erun1",
    (3, 1): "erun2",
    (5, 1): "serun1",
    (5, 2): "serun2",
    (6, 3): "srun1",
    (7, 2): "srun2",
    (5, 3): "swrun1",
    (6, 1): "swrun2",
    (4, 2): "wrun1",
    (4, 3): "wrun2",
    (1, 0): "nwrun1",
    (1, 1): "nwrun2",
    # States
    (3, 3): "still",
    (7, 3): "alert",
    (5, 0): "wash",
    (6, 0): "itch1",
    (7, 0): "itch2",
    (3, 2): "yawn",
    (2, 0): "sleep1",
    (2, 1): "sleep2",
}

class OnekoAnimator:
    def __init__(self, sprite_sheet_path=None, is_custom=False):
        self.is_custom = is_custom
        self.sprite_sheet = None
        self.custom_frames = {}  # (col, row) -> image_array
        self.current_skin = None
        self.sprite_size = 32
        self.speed = 3
        
        # Stagger starting positions so they don't overlap exactly
        self.x = 180 if is_custom else 80
        self.y = 0
        self.target_x = 280 if is_custom else 140
        
        self.frame_count = 0
        self.state_timer = 0
        self.state_duration = 20
        self.state = "idle"
        self.sprite_name = "idle"
        self.direction = 1

        if not is_custom and sprite_sheet_path:
            self.sprite_sheet = imread(sprite_sheet_path, cv2.IMREAD_UNCHANGED)
            if self.sprite_sheet is None:
                sys.stderr.write(f"[Oneko] ERROR: Could not load sprite sheet from {sprite_sheet_path}\n")

        # Sprite coordinates col, row mapping from the 8x4 sheet
        self.sprite_sets = {
            "idle":         [(3, 3)],
            "alert":        [(7, 3)],
            "scratchSelf":  [(5, 0), (6, 0), (7, 0)],
            "scratchWallN": [(0, 0), (0, 1)],
            "scratchWallS": [(7, 1), (6, 2)],
            "scratchWallE": [(2, 2), (2, 3)],
            "scratchWallW": [(4, 0), (4, 1)],
            "tired":        [(3, 2)],
            "sleeping":     [(2, 0), (2, 1)],
            "N":  [(1, 2), (1, 3)],
            "NE": [(0, 2), (0, 3)],
            "E":  [(3, 0), (3, 1)],
            "SE": [(5, 1), (5, 2)],
            "S":  [(6, 3), (7, 2)],
            "SW": [(5, 3), (6, 1)],
            "W":  [(4, 2), (4, 3)],
            "NW": [(1, 0), (1, 1)],
        }

    def preload_custom_skin(self, skin_name):
        if self.current_skin == skin_name:
            return
        
        self.custom_frames.clear()
        self.current_skin = skin_name
        
        skin_dir = paths.safe_join(paths.SKINS_DIR, skin_name) or ""
        
        if not os.path.isdir(skin_dir):
            sys.stderr.write(f"[Oneko] Custom skin dir not found: {skin_dir}\n")
            return
            
        sys.stderr.write(f"[Oneko] Preloading custom skin: {skin_name}\n")
        
        loaded_count = 0
        for (col, row), filename in COORDS_TO_FILE.items():
            img_path = os.path.join(skin_dir, f"{filename}.png")
            if os.path.isfile(img_path):
                img = imread(img_path, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    # Ensure 4 channels (BGRA)
                    if len(img.shape) == 2:
                        # Grayscale -> BGRA
                        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
                    elif img.shape[2] == 3:
                        # BGR -> BGRA
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                    
                    self.custom_frames[(col, row)] = img
                    loaded_count += 1
                    
        sys.stderr.write(f"[Oneko] Preloaded {loaded_count}/32 frames for custom skin: {skin_name}\n")

    def tick(self, width, height, scale):
        self.frame_count += 1
        self.state_timer += 1
        
        scaled_size = int(self.sprite_size * scale)
        max_x = width - scaled_size
        self.y = height - scaled_size
        
        if self.state == "idle":
            self.sprite_name = "idle"
            if self.state_timer >= self.state_duration:
                self.pick_next_state(max_x, scaled_size)
        elif self.state == "alert":
            self.sprite_name = "alert"
            if self.state_timer >= 5:
                self.pick_next_state(max_x, scaled_size)
        elif self.state == "walking":
            dx = self.target_x - self.x
            if abs(dx) < self.speed + 1:
                self.x = self.target_x
                self.state = "idle"
                self.state_duration = np.random.randint(10, 30)
                self.state_timer = 0
                self.sprite_name = "idle"
            else:
                self.direction = 1 if dx > 0 else -1
                self.x += self.direction * self.speed
                self.x = max(0, min(max_x, self.x))
                self.sprite_name = "E" if self.direction > 0 else "W"
            if self.state_timer >= self.state_duration:
                self.state = "idle"
                self.state_duration = np.random.randint(10, 30)
                self.state_timer = 0
        elif self.state == "scratching":
            if self.x <= 2:
                self.sprite_name = "scratchWallW"
            elif self.x >= max_x - 2:
                self.sprite_name = "scratchWallE"
            else:
                self.sprite_name = "scratchSelf"
            if self.state_timer >= self.state_duration:
                self.pick_next_state(max_x, scaled_size)
        elif self.state == "tired":
            self.sprite_name = "tired"
            if self.state_timer >= self.state_duration:
                self.state = "sleeping"
                self.state_duration = np.random.randint(60, 150)
                self.state_timer = 0
        elif self.state == "sleeping":
            self.sprite_name = "sleeping"
            if self.state_timer >= self.state_duration:
                self.state = "alert"
                self.state_duration = 5
                self.state_timer = 0
                
    def pick_next_state(self, max_x, scaled_size):
        roll = np.random.random()
        if roll < 0.50:
            self.state = "walking"
            self.state_duration = np.random.randint(30, 80)
            self.target_x = np.random.randint(scaled_size, max_x)
        elif roll < 0.70:
            self.state = "scratching"
            self.state_duration = np.random.randint(15, 40)
        elif roll < 0.85:
            self.state = "tired"
            self.state_duration = 8
        else:
            self.state = "idle"
            self.state_duration = np.random.randint(10, 30)
        self.state_timer = 0

    def draw(self, frame_rgb, scale):
        if not self.is_custom and self.sprite_sheet is None:
            return
        if self.is_custom and not self.custom_frames:
            return
            
        h, w = frame_rgb.shape[:2]
        self.tick(w, h, scale)
        
        # Get frame of current state
        sprites = self.sprite_sets.get(self.sprite_name, [(3, 3)])
        idx = (self.frame_count // 3) % len(sprites)
        col, row = sprites[idx]
        
        if self.is_custom:
            sprite = self.custom_frames.get((col, row))
            if sprite is None:
                # fallback to still
                sprite = self.custom_frames.get((3, 3))
            if sprite is None:
                return
        else:
            # Extract 32x32 sprite from sheet
            sy = row * self.sprite_size
            sx = col * self.sprite_size
            sprite = self.sprite_sheet[sy:sy+self.sprite_size, sx:sx+self.sprite_size]
        
        # Scale the sprite using nearest neighbor to preserve clean pixel art
        scaled_size = int(self.sprite_size * scale)
        sprite = cv2.resize(sprite, (scaled_size, scaled_size), interpolation=cv2.INTER_NEAREST)
        
        # Ensure we draw inside boundaries
        x_start = int(self.x)
        y_start = int(self.y)
        
        if x_start < 0 or y_start < 0 or x_start + scaled_size > w or y_start + scaled_size > h:
            return
            
        # Blend using alpha channel
        sprite_bgr = sprite[:, :, :3]
        sprite_alpha = sprite[:, :, 3] / 255.0
        sprite_alpha_3d = np.stack([sprite_alpha]*3, axis=-1)
        
        roi = frame_rgb[y_start:y_start+scaled_size, x_start:x_start+scaled_size]
        sprite_rgb = sprite_bgr[:, :, ::-1]
        
        blended = (sprite_rgb * sprite_alpha_3d + roi * (1.0 - sprite_alpha_3d)).astype(np.uint8)
        frame_rgb[y_start:y_start+scaled_size, x_start:x_start+scaled_size] = blended



def sync_reaction_engine():
    """Create / reconfigure / stop the reaction overlay engine after a config poll."""
    global reaction_engine
    if not (reactions_cfg.get("enabled") or reactions_cfg.get("testFire")
            or reactions_cfg.get("showTracking")):
        if reaction_engine is not None:
            reaction_engine.configure(reactions_cfg)
        return
    if reaction_engine is None:
        try:
            from webcam_bridge.reactions import ReactionEngine
            reaction_engine = ReactionEngine()
            log("[PySender] Reaction overlays enabled.")
        except Exception as exc:
            log(f"[PySender] ERROR loading reaction overlays: {exc}")
            return
    reaction_engine.configure(reactions_cfg)


def main():
    global py_cam, running, segmenter_loading, seg_input_frame, seg_input_w, seg_input_h
    log(f"[PySender] Starting Python frame_sender: {WIDTH}x{HEIGHT} @ {FPS}fps")

    oneko_gif_path = paths.ONEKO_GIF
    oneko_animator = OnekoAnimator(oneko_gif_path, is_custom=False)
    custom_animators = []

    stdin_buf = sys.stdin.buffer
    frames_processed = 0

    try:
        while True:
            # Poll configuration changes every 10 frames (~300ms at 30fps)
            if frames_processed % 10 == 0:
                load_config(initial=False)
                sync_reaction_engine()
                
                # Sync animators count with customPets config list
                while len(custom_animators) < len(custom_pets_config):
                    new_animator = OnekoAnimator(is_custom=True)
                    # Randomise coordinates so multiple custom pets start at different positions
                    new_animator.x = np.random.randint(50, 450)
                    new_animator.target_x = np.random.randint(50, 450)
                    custom_animators.append(new_animator)
                while len(custom_animators) > len(custom_pets_config):
                    custom_animators.pop()
                    
                # Preload custom skins for each animator slot
                for idx, pet_cfg in enumerate(custom_pets_config):
                    skin_name = pet_cfg.get("skin", "socks")
                    custom_animators[idx].preload_custom_skin(skin_name)

            # Lazy-load segmenters when any background effect is needed
            needs_segmentation = bg_mode in ("blur", "replace")
            if needs_segmentation:
                global segmenter_thread
                if segmenter_thread is None:
                    segmenter_thread = threading.Thread(target=segmenter_thread_func, name="SegmenterThread", daemon=True)
                    segmenter_thread.start()
                    log("[PySender] Background segmenter thread started.")
                
                if segmentation_engine == "mediapipe" and segmenter is None and not segmenter_loading:
                    segmenter_loading = True
                    threading.Thread(target=load_mediapipe_worker, name="MpLoader", daemon=True).start()

            # Read raw BGR24 frame from stdin
            raw = b''
            while len(raw) < FRAME_SIZE:
                chunk = stdin_buf.read(FRAME_SIZE - len(raw))
                if not chunk:
                    log("[PySender] stdin closed, exiting.")
                    running = False
                    return
                raw += chunk

            try:
                frame_bgr = np.frombuffer(raw, dtype=np.uint8).reshape((HEIGHT, WIDTH, 3))


                # 1. Crop-zoom
                if zoom > 1.0:
                    cx, cy = WIDTH // 2, HEIGHT // 2
                    cw, ch = int(WIDTH / zoom), int(HEIGHT / zoom)
                    x1 = max(0, cx - cw // 2)
                    y1 = max(0, cy - ch // 2)
                    x2 = min(WIDTH, x1 + cw)
                    y2 = min(HEIGHT, y1 + ch)
                    cropped = frame_bgr[y1:y2, x1:x2]
                    frame_bgr = cv2.resize(cropped, (WIDTH, HEIGHT), interpolation=cv2.INTER_LINEAR)

                # 2. Mirror
                if mirror:
                    frame_bgr = cv2.flip(frame_bgr, 1)

                # 3. Rotation
                if orientation == 90:
                    frame_bgr = cv2.rotate(frame_bgr, cv2.ROTATE_90_CLOCKWISE)
                elif orientation == 180:
                    frame_bgr = cv2.rotate(frame_bgr, cv2.ROTATE_180)
                elif orientation == 270:
                    frame_bgr = cv2.rotate(frame_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)

                h_rot, w_rot = frame_bgr.shape[:2]


                # 4. Brightness / Contrast
                if abs(brightness) > 0.01 or abs(contrast - 1.0) > 0.01:
                    frame_bgr = apply_color_eq(frame_bgr, brightness, contrast)

                # 5. Saturation
                if abs(saturation - 1.0) > 0.01:
                    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
                    hsv[:, :, 1] = np.clip(hsv[:, :, 1].astype(np.float32) * saturation, 0, 255).astype(np.uint8)
                    frame_bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

                # 6. Sharpness (Unsharp Mask)
                if sharpness > 0.05:
                    blurred_sh = cv2.GaussianBlur(frame_bgr, (5, 5), 0)
                    frame_bgr = cv2.addWeighted(frame_bgr, 1.0 + sharpness, blurred_sh, -sharpness, 0)

                # Convert BGR to RGB for downstream processing
                frame_rgb = frame_bgr[:, :, ::-1].copy()



                # 7. Virtual Background (Blur / Replace)
                if bg_mode in ("blur", "replace"):
                    # Feed the correct input queue based on the active engine
                    if segmentation_engine == "rvm":
                        # RVM operates on full-res RGB — no pre-downscale
                        with seg_input_lock:
                            globals()['seg_input_full_frame'] = frame_rgb
                            globals()['seg_input_w'] = w_rot
                            globals()['seg_input_h'] = h_rot
                    else:
                        # MediaPipe / BgMattingV2: downscale to 256×144 first
                        seg_in = cv2.resize(frame_rgb, (MP_W, MP_H), interpolation=cv2.INTER_LINEAR)
                        with seg_input_lock:
                            globals()['seg_input_frame'] = seg_in
                            globals()['seg_input_w'] = w_rot
                            globals()['seg_input_h'] = h_rot

                    # Read the latest computed mask from the background thread
                    with seg_output_lock:
                        mask_3d = seg_output_mask

                    if mask_3d is not None and mask_3d.shape[:2] == (h_rot, w_rot):
                        if bg_mode == "blur" and blur > 0:
                            ksize = blur * 2 + 1
                            if ksize % 2 == 0:
                                ksize += 1
                            blurred_rgb = cv2.GaussianBlur(frame_rgb, (ksize, ksize), 0)
                            frame_rgb = (frame_rgb * mask_3d + blurred_rgb * (1.0 - mask_3d)).astype(np.uint8)
                        elif bg_mode == "replace" and bg_image:
                            bg_rgb = get_background_rgb(bg_image, w_rot, h_rot)
                            if bg_rgb is not None:
                                frame_rgb = (frame_rgb * mask_3d + bg_rgb * (1.0 - mask_3d)).astype(np.uint8)

                # 7.7 Face Touch-up (bilateral skin smoothing)
                if face_touchup_enabled and face_touchup_strength > 0.01:
                    if face_touchup_processor is None:
                        try:
                            from webcam_bridge.face_touchup import FaceTouchup
                            globals()['face_touchup_processor'] = FaceTouchup()
                        except Exception as _e:
                            log(f"[PySender] ERROR loading FaceTouchup: {_e}")
                    if face_touchup_processor is not None:
                        frame_rgb = face_touchup_processor.process_frame(frame_rgb, face_touchup_strength)

                # 7.5 Draw Oneko Pet Overlay
                if oneko_enabled and oneko_animator is not None:
                    oneko_animator.draw(frame_rgb, oneko_size)
                for idx, pet_cfg in enumerate(custom_pets_config):
                    if pet_cfg.get("enabled", False) and idx < len(custom_animators):
                        custom_animators[idx].draw(frame_rgb, oneko_size)

                # 7.9 Reaction overlays (gesture / expression driven emoji & memes)
                if reaction_engine is not None:
                    if reactions_cfg.get("enabled"):
                        reaction_engine.submit(frame_rgb)
                    reaction_engine.render(frame_rgb)

                # 8. Send to Virtual Camera
                if vcam_enabled:
                    with vcam_lock:
                        if py_cam is None or py_cam.width != w_rot or py_cam.height != h_rot:
                            if py_cam:
                                try:
                                    py_cam.close()
                                except Exception:
                                    pass
                                py_cam = None
                            try:
                                if pyvirtualcam is not None:
                                    py_cam = pyvirtualcam.Camera(
                                        width=w_rot, height=h_rot, fps=FPS,
                                        print_fps=False, backend='obs'
                                    )
                                    log(f"[PySender] Virtual camera opened: {py_cam.device} ({w_rot}x{h_rot})")
                                else:
                                    if frames_processed % 90 == 0:
                                        log("[PySender] pyvirtualcam module not found.")
                            except Exception as e:
                                if frames_processed % 90 == 0:
                                    log(f"[PySender] Error opening camera: {e}. Make sure OBS -> Virtual Camera is started.")
                                py_cam = None

                        if py_cam:
                            try:
                                py_cam.send(frame_rgb)
                            except Exception as e:
                                if frames_processed % 90 == 0:
                                    log(f"[PySender] Error writing to virtual camera: {e}")
                else:
                    with vcam_lock:
                        if py_cam is not None:
                            try:
                                py_cam.close()
                            except Exception:
                                pass
                            py_cam = None
                            log("[PySender] Virtual camera closed (disabled in config).")

                # 9. Send to Web Preview (always active)
                if w_rot >= h_rot:
                    preview_w = 640
                    preview_h = int(640 * h_rot / w_rot)
                else:
                    preview_h = 640
                    preview_w = int(640 * w_rot / h_rot)
                preview_w = (preview_w // 2) * 2
                preview_h = (preview_h // 2) * 2

                preview_frame = cv2.resize(frame_rgb, (preview_w, preview_h), interpolation=cv2.INTER_LINEAR)

                # Tracking overlay goes on the dashboard preview only — never on
                # the virtual camera, so calls stay clean while you tune gestures.
                if reaction_engine is not None and reactions_cfg.get("showTracking"):
                    reaction_engine.draw_tracking(preview_frame)

                preview_frame_bgr = preview_frame[:, :, ::-1]
                _, jpeg_bytes_arr = cv2.imencode('.jpg', preview_frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
                jpeg_bytes = jpeg_bytes_arr.tobytes()

                binary_stdout.write(len(jpeg_bytes).to_bytes(4, byteorder='big'))
                binary_stdout.write(jpeg_bytes)
                binary_stdout.flush()

            except Exception as e:
                if frames_processed % 90 == 0:
                    log(f"[PySender] Frame processing loop exception: {e}")

            frames_processed += 1
            if frames_processed % 15 == 0 and reaction_engine is not None:
                # Structured status line — the bridge parses this out of stderr
                log(f"{RX_STATUS_PREFIX}{json.dumps(reaction_engine.stats())}")
            if frames_processed % 90 == 0:
                log(f"[PySender] Processed frame #{frames_processed}")

    except KeyboardInterrupt:
        log("[PySender] Interrupted.")
    finally:
        running = False
        with vcam_lock:
            if py_cam:
                try:
                    py_cam.close()
                except Exception:
                    pass
                py_cam = None

if __name__ == '__main__':
    main()
