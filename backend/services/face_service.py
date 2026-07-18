"""
backend/services/face_service.py
----------------------------------
Webcam management and face capture service.

Responsibilities:
    - Open / close the system webcam
    - Stream MJPEG frames for the frontend preview
    - Detect faces in live frames using OpenCV's Haar cascade
    - Automatically capture N images when a face is stable
    - Save captured face images to disk
    - Interface with EmbeddingService to generate embeddings
"""

import logging
import os
import time
import threading
import uuid
from pathlib import Path
from typing import Generator

import cv2
import numpy as np

from backend.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)




class FaceService:
    """
    Thread-safe webcam and face capture manager.

    Only one webcam session can be active at a time.  The session is
    identified by a unique `session_id` string returned to the client
    so the frontend can correlate requests.
    """

    def __init__(self, face_images_dir: Path, capture_count: int = 7):
        """
        Args:
            face_images_dir: Directory where captured face images are saved.
            capture_count:   Number of valid face images to capture per session.
        """
        self.face_images_dir = Path(face_images_dir)
        self.capture_count = capture_count

        # ── Camera state ───────────────────────────────────────────────────────
        self._cap: cv2.VideoCapture | None = None
        self._camera_lock = threading.Lock()

        # ── Capture state ──────────────────────────────────────────────────────
        self._session_id: str | None = None
        self._session_dir: Path | None = None
        self._captured_paths: list[Path] = []
        self._capture_complete: bool = False
        self._capture_error: str | None = None
        self._capture_in_progress: bool = False

        # ── Face detector ──────────────────────────────────────────────────────
        # We now use face_recognition for face detection, no Haar cascades needed.

        # ── Embedding service ──────────────────────────────────────────────────
        self._embedding_service: EmbeddingService | None = None

        logger.info("FaceService initialized (capture_count=%d)", capture_count)

    # ─────────────────────────────────────────────────────────────────────────
    # Camera Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def start_camera(self, camera_index: int = 0) -> tuple[bool, str]:
        """
        Open the webcam and start a new capture session.
        Tries multiple backends: CAP_DSHOW → CAP_MSMF → default.

        Args:
            camera_index: OS camera index (default 0 = primary webcam).

        Returns:
            Tuple (success: bool, session_id_or_error: str).
        """
        with self._camera_lock:
            if self._cap is not None and self._cap.isOpened():
                logger.debug("Camera already open, returning existing session.")
                return True, self._session_id

            logger.info("Opening camera index %d …", camera_index)

            # Try backends in order: DirectShow → MSMF → default
            backends = [
                (cv2.CAP_DSHOW,  "DirectShow"),
                (cv2.CAP_MSMF,   "MSMF"),
                (cv2.CAP_ANY,    "Default"),
            ]

            cap = None
            for backend, name in backends:
                logger.debug("Trying camera backend: %s", name)
                try:
                    _cap = cv2.VideoCapture(camera_index, backend)
                    if _cap.isOpened():
                        # Warm-up: confirm we can actually read a frame
                        ret, _ = _cap.read()
                        if ret:
                            cap = _cap
                            logger.info("Camera opened with %s backend.", name)
                            break
                        else:
                            _cap.release()
                            logger.debug("%s backend opened but no frames.", name)
                    else:
                        _cap.release()
                except Exception as exc:
                    logger.debug("Backend %s failed: %s", name, exc)

            if cap is None or not cap.isOpened():
                msg = (
                    f"Webcam (index {camera_index}) could not be opened. "
                    "Check: 1) Camera is connected  2) No other app is using it  "
                    "3) Windows camera permission is granted."
                )
                logger.error(msg)
                return False, msg

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)

            self._cap = cap
            self._session_id = str(uuid.uuid4())
            self._session_dir = self.face_images_dir / self._session_id
            self._session_dir.mkdir(parents=True, exist_ok=True)
            self._captured_paths = []
            self._capture_complete = False
            self._capture_error = None
            self._capture_in_progress = False

            logger.info("Camera opened. Session: %s", self._session_id)
            return True, self._session_id

    def stop_camera(self) -> None:
        """Release the webcam and clean up session state."""
        with self._camera_lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None
                logger.info("Camera released. Session %s ended.", self._session_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Frame Streaming (MJPEG)
    # ─────────────────────────────────────────────────────────────────────────

    def generate_frames(self) -> Generator[bytes, None, None]:
        """
        Yield MJPEG-encoded frames for the browser preview stream.

        The generator draws a face bounding box and a capture counter
        overlay on each frame so the user can see detection progress.

        Yields:
            bytes: Multipart frame boundary + JPEG bytes.
        """
        while self._cap is not None and self._cap.isOpened():
            ret, frame = self._cap.read()
            if not ret:
                logger.warning("Failed to read frame from camera.")
                break

            # Annotate frame
            frame = self._annotate_frame(frame)

            # Encode to JPEG
            _, buffer = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85]
            )
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buffer.tobytes()
                + b"\r\n"
            )
            time.sleep(0.033)  # ~30 fps

    def _annotate_frame(self, frame: np.ndarray) -> np.ndarray:
        """Draw face detection box and capture progress on a frame."""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService()
            
        bboxes = self._embedding_service.detect_only(frame)
        faces_count = len(bboxes)

        # Draw face rectangles
        for (x1, y1, x2, y2) in bboxes:
            color = (0, 255, 120) if faces_count == 1 else (0, 60, 255)
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)

        # Overlay: face count
        status_text = f"Faces: {faces_count}"
        cv2.putText(
            frame, status_text, (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2
        )

        # Overlay: capture progress
        captured = len(self._captured_paths)
        progress_text = f"Captured: {captured}/{self.capture_count}"
        cv2.putText(
            frame, progress_text, (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8,
            (0, 255, 120) if captured > 0 else (200, 200, 200), 2
        )

        return frame

    # ─────────────────────────────────────────────────────────────────────────
    # Face Capture
    # ─────────────────────────────────────────────────────────────────────────

    def start_capture(self, student_id: str) -> dict:
        """
        Capture face images in a background thread.

        Captures `self.capture_count` frames where exactly one face is
        detected.  Stores JPEGs to disk under the session directory.

        Args:
            student_id: Used to prefix saved image filenames.

        Returns:
            dict with keys: 'session_id', 'status', 'message'.
        """
        if self._cap is None or not self._cap.isOpened():
            return {"status": "error", "message": "Camera is not open."}

        if self._capture_in_progress:
            return {"status": "error", "message": "Capture already in progress."}

        self._capture_in_progress = True
        self._captured_paths = []
        self._capture_complete = False
        self._capture_error = None

        thread = threading.Thread(
            target=self._capture_loop,
            args=(student_id,),
            daemon=True,
        )
        thread.start()

        return {
            "status": "started",
            "session_id": self._session_id,
            "message": f"Capturing {self.capture_count} face images…",
        }

    def _capture_loop(self, student_id: str) -> None:
        """
        Background thread: continuously reads frames and saves those
        containing exactly one detected face until `capture_count` is reached.
        """
        logger.info("Capture loop started for student: %s", student_id)
        interval = 0.4  # seconds between captures

        while len(self._captured_paths) < self.capture_count:
            if self._cap is None or not self._cap.isOpened():
                self._capture_error = "Camera disconnected during capture."
                break

            ret, frame = self._cap.read()
            if not ret:
                logger.warning("Capture loop: failed to read frame.")
                time.sleep(0.1)
                continue

            if self._embedding_service is None:
                self._embedding_service = EmbeddingService()
                
            bboxes = self._embedding_service.detect_only(frame)
            faces_count = len(bboxes)

            if faces_count == 1:
                idx = len(self._captured_paths) + 1
                filename = f"{student_id}_face_{idx:02d}.jpg"
                save_path = self._session_dir / filename
                cv2.imwrite(str(save_path), frame)
                self._captured_paths.append(save_path)
                logger.debug("Captured %d/%d: %s", idx, self.capture_count, filename)
            elif len(faces) == 0:
                logger.debug("No face detected – waiting…")
            else:
                logger.debug("Multiple faces detected – skipping frame.")

            time.sleep(interval)

        self._capture_complete = True
        self._capture_in_progress = False

        if self._capture_error:
            logger.error("Capture failed: %s", self._capture_error)
        else:
            logger.info(
                "Capture complete: %d images saved for %s.",
                len(self._captured_paths),
                student_id,
            )

    def get_capture_status(self) -> dict:
        """
        Return the current capture progress as a JSON-serializable dict.

        Returns:
            dict with keys: captured, total, complete, error, session_id.
        """
        return {
            "session_id": self._session_id,
            "captured": len(self._captured_paths),
            "total": self.capture_count,
            "complete": self._capture_complete,
            "error": self._capture_error,
            "in_progress": self._capture_in_progress,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Embedding Generation
    # ─────────────────────────────────────────────────────────────────────────

    def generate_embedding_from_session(
        self, model_name: str = "buffalo_s", ctx_id: int = -1
    ) -> tuple[np.ndarray | None, str | None]:
        """
        Generate a face embedding from all captured session images.

        Args:
            model_name: InsightFace model to use.
            ctx_id:     ONNX execution context (-1 = CPU).

        Returns:
            Tuple (embedding_array, error_message).
        """
        if not self._capture_complete:
            return None, "Face capture has not completed yet."

        if not self._captured_paths:
            return None, "No captured images found in this session."

        svc = EmbeddingService(model_name=model_name, ctx_id=ctx_id)
        embedding, error = svc.generate_from_images(self._captured_paths)

        if embedding is not None:
            logger.info(
                "Embedding generated: shape=%s, session=%s",
                embedding.shape,
                self._session_id,
            )

        return embedding, error

    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────

    def reset_session(self) -> None:
        """Reset capture state without closing the camera."""
        self._captured_paths = []
        self._capture_complete = False
        self._capture_error = None
        self._capture_in_progress = False
        logger.info("Capture session reset.")

    @property
    def session_id(self) -> str | None:
        """Active session identifier."""
        return self._session_id

    @property
    def is_camera_open(self) -> bool:
        """True if the webcam is currently open."""
        return self._cap is not None and self._cap.isOpened()
