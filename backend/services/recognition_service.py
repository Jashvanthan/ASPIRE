import logging
import numpy as np
from typing import Tuple, Dict, Any, Optional

from backend.models.student import Student
from backend.database.db import db
from flask import current_app

logger = logging.getLogger(__name__)

class RecognitionService:
    """
    Singleton service for matching face embeddings against the database.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RecognitionService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # Cache for student embeddings to avoid querying the DB for every single frame
        self._embedding_matrix: Optional[np.ndarray] = None
        self._student_list: list = []
        self._cache_loaded = False
        logger.info("RecognitionService created.")

    def load_cache(self):
        """Preload all student embeddings into memory for fast comparison."""
        try:
            students = Student.query.all()
            
            embeddings = []
            student_data = []
            
            for student in students:
                emb = student.get_embedding()
                if emb is not None:
                    embeddings.append(emb)
                    student_data.append(student.to_dict())
            
            if embeddings:
                self._embedding_matrix = np.vstack(embeddings)
                self._student_list = student_data
            else:
                self._embedding_matrix = None
                self._student_list = []
                
            self._cache_loaded = True
            logger.info(f"Loaded {len(student_data)} student embeddings into memory cache.")
        except Exception as e:
            logger.error(f"Failed to load embedding cache: {e}")

    def invalidate_cache(self):
        """Force reload of cache on next request."""
        self._cache_loaded = False

    def recognize_face(self, target_embedding: np.ndarray) -> Tuple[Optional[dict], float]:
        """
        Compare the target embedding against all registered students using vectorized numpy operations.
        
        Args:
            target_embedding: 1D numpy array (512-d)
            
        Returns:
            Tuple of (student_dict or None, highest_confidence_score)
        """
        if not self._cache_loaded:
            self.load_cache()
            
        if self._embedding_matrix is None or len(self._student_list) == 0:
            return None, 0.0

        threshold = current_app.config.get("RECOGNITION_THRESHOLD", 0.50)
        
        # Vectorized cosine similarity (Dot product of L2 normalized vectors)
        # target_embedding: (512,)
        # _embedding_matrix: (N, 512)
        # similarities: (N,)
        similarities = np.dot(self._embedding_matrix, target_embedding)
        
        best_idx = np.argmax(similarities)
        highest_sim = float(similarities[best_idx])
        
        if highest_sim >= threshold:
            return self._student_list[best_idx], highest_sim
            
        return None, highest_sim

def get_recognition_service() -> RecognitionService:
    return RecognitionService()
