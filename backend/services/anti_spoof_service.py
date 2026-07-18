"""
backend/services/anti_spoof_service.py
---------------------------------------
Orchestrator for the full anti-spoofing pipeline.

This is the single entry point called from attendance_routes.py.
It coordinates LivenessService, computes the final verdict, and
logs every attempt via SecurityLogService.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Optional

import cv2
import numpy as np
from flask import current_app

from backend.services.liveness_service import get_liveness_service

logger = logging.getLogger(__name__)


# ─── Result Dataclass ─────────────────────────────────────────────────────────


@dataclass
class AntiSpoofResult:
    """Immutable result of a single anti-spoof verification."""

    is_genuine: bool = False
    recognition_confidence: float = 0.0
    liveness_score: float = 0.0
    spoof_probability: float = 1.0
    spoof_type: str = "unknown"
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Service ──────────────────────────────────────────────────────────────────


class AntiSpoofService:
    """
    Singleton orchestrator that:
      1. Crops the face from the full frame
      2. Runs LivenessService on the crop
      3. Applies configurable thresholds to produce a PASS / FAIL
      4. Logs every attempt via SecurityLogService
    """

    _instance: Optional["AntiSpoofService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._liveness = get_liveness_service()
        logger.info("AntiSpoofService created.")

    # ──────────────────────────────────────────────────────────────────────
    # Main verification entry point
    # ──────────────────────────────────────────────────────────────────────

    def verify(
        self,
        frame: np.ndarray,
        face,
        recognition_confidence: float,
        student: Optional[dict] = None,
    ) -> AntiSpoofResult:
        """
        Run the complete anti-spoof verification pipeline.

        Args:
            frame:                   Full BGR camera frame.
            face:                    InsightFace face object (has .bbox, .kps, .embedding).
            recognition_confidence:  Cosine similarity from RecognitionService.
            student:                 Matched student dict (or None if unrecognised).

        Returns:
            AntiSpoofResult with the final verdict.
        """
        # -- Extract face crop --
        bbox = face.bbox.astype(int)
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]

        # Clamp to frame boundaries
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        face_crop = frame[y1:y2, x1:x2]
        if face_crop.size == 0:
            return AntiSpoofResult(
                is_genuine=False,
                recognition_confidence=recognition_confidence,
                spoof_type="invalid_crop",
            )

        # -- Extract landmarks (relative to crop) --
        landmarks = None
        if hasattr(face, "kps") and face.kps is not None:
            landmarks = face.kps.copy()
            # Make landmarks relative to the crop origin
            landmarks[:, 0] -= x1
            landmarks[:, 1] -= y1

        # -- Generate a stable face id for temporal tracking --
        face_id = "default"
        if student:
            face_id = student.get("student_id", "default")
        else:
            # Use bbox centre as a rough tracker for unknown faces
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            face_id = f"unk_{cx // 50}_{cy // 50}"

        # -- Run liveness analysis --
        liveness_result = self._liveness.analyze(face_crop, landmarks, face_id)

        overall_liveness = liveness_result["overall_liveness"]
        spoof_probability = round(1.0 - overall_liveness, 3)
        spoof_type = liveness_result["spoof_type"]

        # -- Apply thresholds --
        liveness_threshold = current_app.config.get("LIVENESS_THRESHOLD", 0.60)
        spoof_threshold = current_app.config.get("SPOOF_THRESHOLD", 0.40)
        recognition_threshold = current_app.config.get("RECOGNITION_THRESHOLD", 0.50)

        is_genuine = (
            recognition_confidence >= recognition_threshold
            and overall_liveness >= liveness_threshold
            and spoof_probability <= spoof_threshold
        )

        result = AntiSpoofResult(
            is_genuine=is_genuine,
            recognition_confidence=round(recognition_confidence, 3),
            liveness_score=round(overall_liveness, 3),
            spoof_probability=spoof_probability,
            spoof_type=spoof_type if not is_genuine else "genuine",
            details=liveness_result,
        )

        # -- Log attempt (only spoof attempts or first genuine per student) --
        if not is_genuine:
            self._log_attempt(result, student, face_crop)

        return result

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    def _log_attempt(
        self,
        result: AntiSpoofResult,
        student: Optional[dict],
        face_crop: np.ndarray,
    ) -> None:
        """Persist a spoof attempt to the security log."""
        try:
            from backend.services.security_log_service import get_security_log_service

            svc = get_security_log_service()
            snapshot_path = self._save_snapshot(face_crop) if face_crop.size > 0 else None

            svc.log_attempt(
                student_id=student.get("student_id") if student else None,
                student_name=student.get("full_name") if student else None,
                spoof_type=result.spoof_type,
                liveness_score=result.liveness_score,
                recognition_confidence=result.recognition_confidence,
                spoof_probability=result.spoof_probability,
                decision="rejected",
                snapshot_path=snapshot_path,
                details=result.details,
            )
        except Exception as exc:
            logger.error("Failed to log security attempt: %s", exc)

    @staticmethod
    def _save_snapshot(face_crop: np.ndarray) -> Optional[str]:
        """Save a snapshot of the spoof attempt for audit purposes."""
        try:
            import time
            from pathlib import Path

            snap_dir = Path(
                current_app.config.get(
                    "SECURITY_SNAPSHOTS_FOLDER", "uploads/security_snapshots"
                )
            )
            snap_dir.mkdir(parents=True, exist_ok=True)
            
            filename = f"spoof_{int(time.time() * 1000)}.jpg"
            path = snap_dir / filename
            cv2.imwrite(str(path), face_crop)
            
            # Return relative path for frontend to use via /uploads API
            return f"security_snapshots/{filename}"
        except Exception as exc:
            logger.error("Failed to save spoof snapshot: %s", exc)
            return None


def get_anti_spoof_service() -> AntiSpoofService:
    return AntiSpoofService()
