"""
backend/services/embedding_service.py
---------------------------------------
InsightFace face embedding generation service.

Responsibilities:
    - Load and cache the InsightFace ArcFace model
    - Accept a list of face image paths or numpy arrays
    - Detect faces and extract 512-d embeddings
    - Average multiple embeddings into one robust vector
"""

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import warnings

# InsightFace is an optional heavy dependency
try:
    import insightface
    from insightface.app import FaceAnalysis
    _INSIGHTFACE_AVAILABLE = True
except ImportError:
    _INSIGHTFACE_AVAILABLE = False
    logging.warning("InsightFace not installed.")

# numpy 2.x compatibility shim for InsightFace
_np_aliases = {
    'bool':    np.bool_,
    'int':     np.int_,
    'float':   np.float64,
    'complex': np.complex128,
    'object':  object,
    'str':     np.str_,
}
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    for _attr, _val in _np_aliases.items():
        try:
            if not hasattr(np, _attr):
                setattr(np, _attr, _val)
        except Exception:
            pass

logger = logging.getLogger(__name__)

class EmbeddingService:
    """
    Singleton-style service for generating face embeddings with InsightFace.
    Optimized for high-speed inference.
    """
    _instance: Optional["EmbeddingService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = "buffalo_s", ctx_id: int = -1, *args, **kwargs):
        if self._initialized:
            return
        self.model_name = model_name
        self.ctx_id = ctx_id
        self._model = None
        self._initialized = True

    def load_model(self) -> bool:
        if self._model is not None:
            return True

        if not _INSIGHTFACE_AVAILABLE:
            logger.error("InsightFace library not available.")
            return False

        try:
            logger.info("Loading InsightFace model '%s' …", self.model_name)
            app = FaceAnalysis(
                name=self.model_name,
                providers=["CPUExecutionProvider"],
                allowed_modules=['detection', 'recognition']
            )
            # 640x640 for maximum accuracy. ByteTrack hides latency!
            app.prepare(ctx_id=self.ctx_id, det_size=(640, 640), det_thresh=0.5)
            self._model = app
            logger.info("InsightFace model loaded successfully.")
            return True
        except Exception as exc:
            logger.error("Failed to load InsightFace model: %s", exc)
            return False

    def generate_from_images(self, image_paths: list) -> tuple[np.ndarray | None, str | None]:
        if not self.load_model():
            return None, "InsightFace model could not be loaded."

        if not image_paths:
            return None, "No images provided."

        embeddings = []
        for path in image_paths:
            img = cv2.imread(str(path))
            if img is None:
                continue

            faces = self.get_faces(img)
            if len(faces) == 1:
                embeddings.append(faces[0].embedding)
            else:
                logger.debug("Expected 1 face, found %d", len(faces))

        if not embeddings:
            return None, "No valid single face detected."

        mean_embedding = np.mean(embeddings, axis=0)
        norm = np.linalg.norm(mean_embedding)
        if norm > 0:
            mean_embedding = mean_embedding / norm

        return mean_embedding.astype(np.float32), None

    def generate_from_array(self, image: np.ndarray) -> tuple[np.ndarray | None, str | None]:
        if not self.load_model():
            return None, "InsightFace model could not be loaded."

        faces = self.get_faces(image)
        if len(faces) == 0:
            return None, "No face detected."

        embedding = faces[0].embedding
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding.astype(np.float32), None

    def detect_only(self, image: np.ndarray) -> list:
        """
        Fast detection only for live preview.
        Returns a list of [x1, y1, x2, y2].
        """
        if not self.load_model():
            return []

        try:
            faces = self._model.get(image)
            bboxes = []
            for face in faces:
                bboxes.append(face.bbox.tolist()) # [x1, y1, x2, y2]
            return bboxes
        except Exception as exc:
            logger.error("InsightFace detection error: %s", exc)
            return []

    def get_faces(self, image: np.ndarray) -> list:
        if not self.load_model():
            return []
            
        try:
            return self._model.get(image)
        except Exception as exc:
            logger.error("InsightFace inference error: %s", exc)
            return []

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

