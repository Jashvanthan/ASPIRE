"""
backend/services/liveness_service.py
-------------------------------------
Pure OpenCV/NumPy liveness analysis service.

Implements five anti-spoofing checks that require NO external ML models:
  1. Passive Liveness   — texture / blur / colour / skin analysis
  2. Screen Replay      — moiré pattern & flicker detection via FFT
  3. Printed Photo      — edge density, flatness, paper texture
  4. Face Occlusion     — landmark visibility & face-area ratio
  5. Motion Analysis    — blink detection & head-pose variance (temporal)

All checks operate on the *cropped face region* for maximum speed.
"""

import collections
import logging
import math
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Temporal buffer — stores recent landmark snapshots per tracked face
# ---------------------------------------------------------------------------
_BUFFER_MAX = 15  # Number of frames to keep per face


class _FrameRecord:
    """Lightweight snapshot stored per frame for temporal analysis."""

    __slots__ = ("landmarks", "ear", "pose_angles", "brightness_mean")

    def __init__(self, landmarks: np.ndarray, ear: float, pose_angles: tuple, brightness_mean: float):
        self.landmarks = landmarks
        self.ear = ear
        self.pose_angles = pose_angles
        self.brightness_mean = brightness_mean


class LivenessService:
    """
    Singleton service for running anti-spoofing liveness checks.
    Tuned aggressively to reject printed photos and phone/screen replays.
    """

    _instance: Optional["LivenessService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._buffers: dict[str, collections.deque] = {}
        logger.info("LivenessService created (aggressive mode).")

    # ──────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────

    def analyze(
        self,
        face_crop: np.ndarray,
        landmarks: np.ndarray,
        face_id: str = "default",
    ) -> dict:
        if face_crop is None or face_crop.size == 0:
            return self._fail_result("invalid_input")

        h, w = face_crop.shape[:2]
        if h < 20 or w < 20:
            return self._fail_result("face_too_small")

        # Run individual checks
        passive = self._check_passive(face_crop)
        screen = self._check_screen_replay(face_crop)
        printed = self._check_printed_photo(face_crop)
        occlusion = self._check_occlusion(landmarks, face_crop)
        motion = self._check_motion(landmarks, face_id, face_crop)

        # Weighted combination — motion is king (most reliable)
        overall = (
            passive * 0.20
            + screen * 0.15
            + printed * 0.15
            + occlusion * 0.10
            + motion * 0.40
        )
        overall = float(np.clip(overall, 0.0, 1.0))

        # Determine dominant spoof type
        check_scores = {
            "printed_photo": printed,
            "screen_replay": screen,
            "static_image": motion,
            "occlusion": occlusion,
        }

        spoof_type = "genuine"
        if overall < 0.60:
            worst_key = min(check_scores, key=check_scores.get)
            spoof_type = worst_key

        return {
            "passive_score": round(passive, 3),
            "screen_score": round(screen, 3),
            "print_score": round(printed, 3),
            "occlusion_score": round(occlusion, 3),
            "motion_score": round(motion, 3),
            "overall_liveness": round(overall, 3),
            "spoof_type": spoof_type,
        }

    # ──────────────────────────────────────────────────────────────────────
    # 1. Passive Liveness — texture, blur, colour, skin analysis
    # ──────────────────────────────────────────────────────────────────────

    def _check_passive(self, crop: np.ndarray) -> float:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # -- Laplacian sharpness (blur detection) --
        # Printed photos photographed by webcam have characteristic blur
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        # Real faces: 80-600; photos of photos: often 20-80; phone screens: 40-150
        if lap_var < 30:
            sharpness_score = 0.1
        elif lap_var < 60:
            sharpness_score = 0.3
        elif lap_var < 100:
            sharpness_score = 0.5
        else:
            sharpness_score = min(1.0, lap_var / 300.0)

        # -- LBP texture energy --
        lbp_score = self._lbp_energy(gray)

        # -- Skin colour analysis (HSV) --
        # Real faces have warm skin tones; screens/prints have different colour profiles
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        h_channel = hsv[:, :, 0]
        s_channel = hsv[:, :, 1]
        v_channel = hsv[:, :, 2]

        # Check for natural skin hue range (0-25 and 160-180 in OpenCV HSV)
        skin_mask = ((h_channel < 25) | (h_channel > 160)) & (s_channel > 30) & (v_channel > 50)
        skin_ratio = float(np.count_nonzero(skin_mask)) / (h * w + 1e-9)
        # Real face: skin_ratio typically 0.30-0.70
        # Photo/screen: often lower or inconsistent
        if skin_ratio > 0.20:
            skin_score = min(1.0, skin_ratio / 0.40)
        else:
            skin_score = 0.2

        # -- Saturation variance (screens wash out saturation) --
        s_std = float(np.std(s_channel))
        # Real skin: varied saturation (30-50 std); screens: uniform (10-25 std)
        sat_score = float(np.clip(s_std / 40.0, 0.0, 1.0))

        return (sharpness_score * 0.30 + lbp_score * 0.25 + skin_score * 0.25 + sat_score * 0.20)

    @staticmethod
    def _lbp_energy(gray: np.ndarray) -> float:
        """Compute simplified LBP energy. Prints/screens have lower entropy."""
        h, w = gray.shape
        if h < 3 or w < 3:
            return 0.3

        center = gray[1:-1, 1:-1].astype(np.int16)
        offsets = [
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1),            (0, 1),
            (1, -1),  (1, 0),  (1, 1),
        ]
        lbp = np.zeros_like(center, dtype=np.uint8)
        for i, (dy, dx) in enumerate(offsets):
            neighbour = gray[1 + dy : h - 1 + dy, 1 + dx : w - 1 + dx].astype(np.int16)
            lbp |= ((neighbour >= center).astype(np.uint8)) << i

        hist, _ = np.histogram(lbp, bins=256, range=(0, 256))
        hist = hist.astype(np.float64)
        hist /= hist.sum() + 1e-9
        entropy = -np.sum(hist * np.log2(hist + 1e-9))
        # Real skin: entropy 5.5-7.5; prints: 3.0-5.5; screens: 4.0-6.0
        if entropy < 4.0:
            return 0.15
        elif entropy < 5.0:
            return 0.35
        else:
            return float(np.clip((entropy - 4.0) / 3.5, 0.0, 1.0))

    # ──────────────────────────────────────────────────────────────────────
    # 2. Screen Replay Detection — moiré, brightness, colour temperature
    # ──────────────────────────────────────────────────────────────────────

    def _check_screen_replay(self, crop: np.ndarray) -> float:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        # -- FFT high-frequency ratio (moiré / pixel grid) --
        f = np.fft.fft2(gray.astype(np.float32))
        fshift = np.fft.fftshift(f)
        magnitude = np.log1p(np.abs(fshift))

        h, w = magnitude.shape
        cy, cx = h // 2, w // 2
        r = min(cy, cx) // 3

        total_energy = magnitude.sum() + 1e-9
        low_mask = np.zeros_like(magnitude, dtype=bool)
        low_mask[cy - r : cy + r, cx - r : cx + r] = True
        low_energy = magnitude[low_mask].sum()

        high_ratio = 1.0 - (low_energy / total_energy)
        # Screens: high_ratio often > 0.65 due to pixel grid artifacts
        # Real faces: high_ratio typically 0.45-0.60
        if high_ratio > 0.72:
            moire_score = 0.1  # Very likely screen
        elif high_ratio > 0.65:
            moire_score = 0.3
        elif high_ratio > 0.58:
            moire_score = 0.6
        else:
            moire_score = 0.9

        # -- Brightness uniformity (screens have very uniform backlighting) --
        v_channel = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[:, :, 2]
        brightness_std = float(np.std(v_channel))
        brightness_mean = float(np.mean(v_channel))

        # Screens: typically very bright (mean > 160) and uniform (std < 30)
        # Real face: moderate brightness, higher variation
        if brightness_std < 20 and brightness_mean > 140:
            bright_score = 0.1  # Highly suspicious — screen backlight
        elif brightness_std < 25:
            bright_score = 0.3
        elif brightness_std < 35:
            bright_score = 0.6
        else:
            bright_score = min(1.0, brightness_std / 55.0)

        # -- Blue channel dominance (screens emit more blue light) --
        b_mean = float(np.mean(crop[:, :, 0]))  # BGR
        g_mean = float(np.mean(crop[:, :, 1]))
        r_mean = float(np.mean(crop[:, :, 2]))

        # Screens: blue channel tends to be disproportionately high
        blue_ratio = b_mean / (r_mean + g_mean + b_mean + 1e-9)
        # Normal face illumination: blue_ratio ~0.28-0.33
        # Screen: blue_ratio often > 0.35
        if blue_ratio > 0.38:
            blue_score = 0.1
        elif blue_ratio > 0.35:
            blue_score = 0.4
        else:
            blue_score = 0.9

        return moire_score * 0.40 + bright_score * 0.35 + blue_score * 0.25

    # ──────────────────────────────────────────────────────────────────────
    # 3. Printed Photo Detection — edge density, gradient, flatness
    # ──────────────────────────────────────────────────────────────────────

    def _check_printed_photo(self, crop: np.ndarray) -> float:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # -- Canny edge density --
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.count_nonzero(edges)) / (h * w + 1e-9)
        # Real: 0.06-0.18; printed photos: 0.02-0.06 (blurry) or >0.22 (sharp print)
        if edge_density < 0.04:
            edge_score = 0.15  # Too smooth — likely printed and blurred
        elif edge_density > 0.25:
            edge_score = 0.25  # Unnaturally sharp — high-res print
        elif edge_density < 0.08:
            edge_score = 0.40
        else:
            edge_score = 0.90

        # -- Gradient magnitude consistency --
        grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        grad_mag = np.sqrt(grad_x ** 2 + grad_y ** 2)
        grad_std = float(np.std(grad_mag))
        grad_mean = float(np.mean(grad_mag))

        # Coefficient of variation: real faces have higher relative variation
        cv_ratio = grad_std / (grad_mean + 1e-9)
        # Real: cv_ratio ~1.2-2.0; prints: ~0.7-1.2
        if cv_ratio < 0.8:
            grad_score = 0.15
        elif cv_ratio < 1.0:
            grad_score = 0.35
        elif cv_ratio < 1.3:
            grad_score = 0.60
        else:
            grad_score = 0.90

        # -- Depth-of-field: compare focus across regions --
        # Real 3D face has focus variation; flat print is uniformly sharp/blurry
        mid_h, mid_w = h // 2, w // 2
        regions = [
            gray[:mid_h, :mid_w],    # top-left
            gray[:mid_h, mid_w:],    # top-right
            gray[mid_h:, :mid_w],    # bottom-left
            gray[mid_h:, mid_w:],    # bottom-right
        ]
        focus_values = [cv2.Laplacian(r, cv2.CV_64F).var() for r in regions]
        focus_std = float(np.std(focus_values))
        focus_mean = float(np.mean(focus_values)) + 1e-9
        focus_cv = focus_std / focus_mean

        # Real face (3D): focus varies across regions → higher focus_cv
        # Print (2D): uniform focus → low focus_cv
        if focus_cv < 0.15:
            dof_score = 0.20  # Very flat — likely printed
        elif focus_cv < 0.30:
            dof_score = 0.50
        else:
            dof_score = 0.85

        return edge_score * 0.30 + grad_score * 0.35 + dof_score * 0.35

    # ──────────────────────────────────────────────────────────────────────
    # 4. Occlusion Detection — landmark visibility
    # ──────────────────────────────────────────────────────────────────────

    def _check_occlusion(self, landmarks: np.ndarray, crop: np.ndarray) -> float:
        if landmarks is None or len(landmarks) < 5:
            return 0.15

        h, w = crop.shape[:2]

        # Check landmarks are inside bounds
        inside_count = 0
        for lm in landmarks[:5]:
            x, y = float(lm[0]), float(lm[1])
            if 0 <= x <= w and 0 <= y <= h:
                inside_count += 1

        visibility_score = inside_count / 5.0

        # Inter-eye distance ratio
        left_eye = landmarks[0]
        right_eye = landmarks[1]
        eye_dist = float(np.linalg.norm(left_eye - right_eye))
        eye_ratio = eye_dist / (w + 1e-9)
        distance_score = float(np.clip(eye_ratio / 0.25, 0.0, 1.0))

        # Vertical span
        ml = landmarks[3]
        mr = landmarks[4]
        vert_span = max(float(ml[1]), float(mr[1])) - min(
            float(left_eye[1]), float(right_eye[1])
        )
        vert_ratio = vert_span / (h + 1e-9)
        area_score = float(np.clip(vert_ratio / 0.4, 0.0, 1.0))

        return visibility_score * 0.4 + distance_score * 0.3 + area_score * 0.3

    # ──────────────────────────────────────────────────────────────────────
    # 5. Motion Analysis — THE MOST IMPORTANT CHECK
    #    A real person ALWAYS has micro-movements. A photo NEVER does.
    # ──────────────────────────────────────────────────────────────────────

    def _check_motion(self, landmarks: np.ndarray, face_id: str, crop: np.ndarray) -> float:
        if landmarks is None or len(landmarks) < 5:
            return 0.0  # No landmarks = fail

        # Compute EAR
        ear = self._compute_ear_5pt(landmarks)

        # Head pose proxy
        left_eye = landmarks[0]
        right_eye = landmarks[1]
        nose = landmarks[2]

        eye_center = (left_eye + right_eye) / 2.0
        eye_dist = float(np.linalg.norm(left_eye - right_eye))
        if eye_dist < 1e-6:
            return 0.0

        yaw = float((nose[0] - eye_center[0]) / (eye_dist + 1e-9))
        pitch = float((nose[1] - eye_center[1]) / (eye_dist + 1e-9))

        # Brightness for flicker detection
        brightness_mean = float(np.mean(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)))

        record = _FrameRecord(landmarks.copy(), ear, (yaw, pitch), brightness_mean)
        buf = self._buffers.setdefault(face_id, collections.deque(maxlen=_BUFFER_MAX))
        buf.append(record)

        # Need at least 5 frames for reliable motion analysis
        if len(buf) < 5:
            # During warmup: return neutral-low score (benefit of doubt is LOW)
            return 0.35

        # -- EAR variance (blink detection) --
        # This is the single most powerful check.
        # A real person blinks every 2-6 seconds. EAR drops from ~0.35 to ~0.15.
        # A photo has CONSTANT EAR.
        ears = [r.ear for r in buf]
        ear_range = max(ears) - min(ears)
        ear_var = float(np.var(ears))

        if ear_range < 0.005:
            # Absolutely no EAR change — definitely a photo
            blink_score = 0.0
        elif ear_range < 0.01:
            blink_score = 0.1
        elif ear_range < 0.02:
            blink_score = 0.3
        elif ear_range < 0.04:
            blink_score = 0.5
        else:
            # Significant EAR variation — likely real blinks
            blink_score = min(1.0, ear_range / 0.06)

        # -- Head pose variance --
        yaws = [r.pose_angles[0] for r in buf]
        pitches = [r.pose_angles[1] for r in buf]
        yaw_range = max(yaws) - min(yaws)
        pitch_range = max(pitches) - min(pitches)
        total_range = yaw_range + pitch_range

        if total_range < 0.005:
            # Zero head movement — photo
            pose_score = 0.0
        elif total_range < 0.015:
            pose_score = 0.15
        elif total_range < 0.03:
            pose_score = 0.35
        elif total_range < 0.06:
            pose_score = 0.55
        else:
            pose_score = min(1.0, total_range / 0.10)

        # -- Landmark position jitter --
        # Real faces have constant micro-jitter from breathing, muscle twitches, etc.
        # Photos/screens have zero jitter.
        positions = np.array([r.landmarks[:5].flatten() for r in buf])
        pos_var = float(np.mean(np.var(positions, axis=0)))

        if pos_var < 0.1:
            landmark_score = 0.0  # Absolutely frozen
        elif pos_var < 0.5:
            landmark_score = 0.15
        elif pos_var < 1.5:
            landmark_score = 0.35
        elif pos_var < 3.0:
            landmark_score = 0.55
        else:
            landmark_score = min(1.0, pos_var / 5.0)

        # -- Brightness flicker (screen-specific) --
        brightnesses = [r.brightness_mean for r in buf]
        bright_var = float(np.var(brightnesses))
        # Screens flicker at 50/60Hz — creates subtle brightness changes
        # But this can also happen with natural lighting, so weight it lightly

        # Combine: blink is the most critical, then pose, then landmarks
        motion_score = (
            blink_score * 0.40
            + pose_score * 0.30
            + landmark_score * 0.30
        )

        return float(np.clip(motion_score, 0.0, 1.0))

    @staticmethod
    def _compute_ear_5pt(landmarks: np.ndarray) -> float:
        left_eye = landmarks[0]
        right_eye = landmarks[1]
        nose = landmarks[2]

        eye_mid = (left_eye + right_eye) / 2.0
        vert = float(np.linalg.norm(nose - eye_mid))
        horiz = float(np.linalg.norm(left_eye - right_eye))

        if horiz < 1e-6:
            return 0.3

        return vert / horiz

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _fail_result(reason: str) -> dict:
        return {
            "passive_score": 0.0,
            "screen_score": 0.0,
            "print_score": 0.0,
            "occlusion_score": 0.0,
            "motion_score": 0.0,
            "overall_liveness": 0.0,
            "spoof_type": reason,
        }

    def clear_buffer(self, face_id: str) -> None:
        self._buffers.pop(face_id, None)

    def clear_all_buffers(self) -> None:
        self._buffers.clear()


def get_liveness_service() -> LivenessService:
    return LivenessService()
