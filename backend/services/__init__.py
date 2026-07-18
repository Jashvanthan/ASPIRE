"""
backend/services/__init__.py
------------------------------
Services package initializer.
"""

from .student_service import StudentService
from .face_service import FaceService
from .embedding_service import EmbeddingService

__all__ = ["StudentService", "FaceService", "EmbeddingService"]
