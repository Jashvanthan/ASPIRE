"""
backend/services/antispoof_service.py
--------------------------------------
Deep Learning based AI Anti-Spoofing Service.

Uses MiniFASNet (Silent-Face-Anti-Spoofing) via ONNX Runtime to 
detect presentation attacks (printed photos, screens, replays).
"""

import logging
import math
from typing import Optional

import cv2
import numpy as np

# We try to import onnxruntime; if not available, we can't run DL anti-spoof
try:
    import onnxruntime as ort
    _ONNX_AVAILABLE = True
except ImportError:
    _ONNX_AVAILABLE = False

from flask import current_app

logger = logging.getLogger(__name__)

class AntispoofService:
    """
    Singleton service for deep learning based liveness detection.
    Loads the MiniFASNet ONNX model once on startup and reuses it.
    """
    _instance: Optional["AntispoofService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._model_path = current_app.config.get("ANTISPOOF_MODEL_PATH", "models/2.7_80x80_MiniFASNetV2.onnx")
        self._session = None
        self._load_model()

    def _load_model(self):
        """Loads the ONNX model into memory."""
        if not _ONNX_AVAILABLE:
            logger.warning("onnxruntime is not installed. AI Anti-spoofing is disabled.")
            return

        try:
            # We use CPUExecutionProvider by default for lightweight CPU inference.
            self._session = ort.InferenceSession(
                self._model_path,
                providers=['CPUExecutionProvider']
            )
            logger.info("Successfully loaded AI Anti-Spoofing model: %s", self._model_path)
        except Exception as exc:
            logger.error("Failed to load Anti-Spoofing model %s: %s", self._model_path, exc)
            self._session = None

    def get_liveness(self, frame: np.ndarray, bbox: list) -> tuple[float, float, str]:
        """
        Analyzes a face to determine if it is a live person or a spoof.
        
        Args:
            frame: Full BGR image frame from the camera.
            bbox: [x, y, w, h] of the detected face.
            
        Returns:
            tuple: (live_confidence, spoof_confidence, label)
            - live_confidence: 0.0 to 1.0 (higher means real human)
            - spoof_confidence: 0.0 to 1.0 (higher means photo/screen)
            - label: "genuine" or "spoof"
        """
        if self._session is None:
            # If model failed to load or onnxruntime is missing, fallback to pass
            return 1.0, 0.0, "genuine"

        try:
            x, y, w, h = bbox
            
            # MiniFASNet requires a specific face crop expansion (scale around 2.7)
            # We will expand the bounding box to capture context
            scale = 2.7
            center_x, center_y = x + w // 2, y + h // 2
            size = int(max(w, h) * scale)
            
            x1 = max(0, center_x - size // 2)
            y1 = max(0, center_y - size // 2)
            x2 = min(frame.shape[1], x1 + size)
            y2 = min(frame.shape[0], y1 + size)
            
            # Adjust if we hit the boundaries to keep aspect ratio 1:1 if possible
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                return 0.0, 1.0, "invalid_crop"

            # Preprocess image
            crop_resized = cv2.resize(crop, (80, 80))
            
            # MiniFASNet expects RGB (OpenCV provides BGR)
            img = cv2.cvtColor(crop_resized, cv2.COLOR_BGR2RGB)
            
            # Convert to float32 and scale to [0, 1] (equivalent to PyTorch's ToTensor)
            img = img.astype(np.float32) / 255.0
            
            # Convert HWC to CHW
            img = np.transpose(img, (2, 0, 1))
            
            # Add batch dimension
            img = np.expand_dims(img, axis=0)
            
            # Run inference
            input_name = self._session.get_inputs()[0].name
            outputs = self._session.run(None, {input_name: img})
            
            # MiniFASNet outputs 3 classes typically: 
            # 0: spoof (screen/printed)
            # 1: real (live face)
            # 2: spoof (other)
            # Or sometimes 2 classes (spoof, real) depending on the exact ONNX file.
            logits = outputs[0][0]
            
            # Apply softmax to get probabilities
            exp_preds = np.exp(logits - np.max(logits))
            probs = exp_preds / np.sum(exp_preds)
            
            # Assume binary class or 3-class. Usually class 1 is "Real", rest are spoof.
            if len(probs) == 3:
                real_score = float(probs[1])
                spoof_score = float(probs[0] + probs[2])
            elif len(probs) == 2:
                # Typically [spoof, real]
                real_score = float(probs[1])
                spoof_score = float(probs[0])
            else:
                # Fallback if unknown shape
                real_score = float(probs[0] if probs[0] > 0.5 else 0.0)
                spoof_score = 1.0 - real_score

            label = "genuine" if real_score > spoof_score else "spoof"
            return real_score, spoof_score, label

        except Exception as exc:
            logger.error("DL Anti-Spoofing inference failed: %s", exc)
            # Fallback to reject if we encounter an error, to be secure
            return 0.0, 1.0, "error"

def get_antispoof_service() -> AntispoofService:
    return AntispoofService()
