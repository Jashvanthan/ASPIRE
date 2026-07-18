import logging
from typing import Any, Dict, List, Tuple
import cv2
import numpy as np
import threading

logger = logging.getLogger(__name__)

# Lazy loading to avoid hard crash if ultralytics is not installed
try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False
    logger.warning("ultralytics not installed. YOLOv11n detection will be disabled.")

class DetectionService:
    """
    Singleton service for handling YOLOv11n real-time object detection.
    Optimized for fast inference on video frames.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(DetectionService, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = "yolo11n.pt"):
        if self._initialized:
            return

        self.model_name = model_name
        self.model = None
        self._inference_lock = threading.Lock()
        self._initialized = True
        
        if ULTRALYTICS_AVAILABLE:
            try:
                logger.info(f"Loading YOLO model: {self.model_name}")
                # verbose=False reduces console spam during inference
                self.model = YOLO(self.model_name)
                logger.info("YOLO model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load YOLO model: {e}")
        else:
            logger.error("Cannot load YOLO model because ultralytics is not installed.")

    def detect_people(self, frame: np.ndarray, conf_threshold: float = 0.45) -> Tuple[List[Dict[str, Any]], str]:
        """
        Run YOLOv11n inference on a single frame to detect people.
        
        Args:
            frame: BGR numpy array (from cv2).
            conf_threshold: Minimum confidence score to keep the detection.
            
        Returns:
            Tuple containing:
                - List of detection dicts: [{"bbox": [x1, y1, w, h], "confidence": float, "class": "person"}]
                - Error string (empty if success)
        """
        if not ULTRALYTICS_AVAILABLE or self.model is None:
            return [], "YOLO model is not available. Please install ultralytics."

        if frame is None or frame.size == 0:
            return [], "Invalid frame."

        try:
            # Run tracking sequentially to prevent thread locking issues
            # Filter for 'person' class only to optimize for attendance
            # persist=True keeps tracking state between frames
            with self._inference_lock:
                # Use imgsz=256 to drastically speed up CPU inference.
                # Use conf_threshold (default increased to 0.75) to avoid detecting objects.
                results = self.model.track(
                    frame, 
                    classes=[0], 
                    conf=max(conf_threshold, 0.75), 
                    persist=True, 
                    tracker="bytetrack.yaml", 
                    verbose=False,
                    imgsz=256
                )
            
            
            detections = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Bounding box format: [x1, y1, x2, y2]
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    cls_id = int(box.cls[0].cpu().numpy())
                    label = result.names[cls_id]
                    
                    # Extract Track ID (if available, sometimes YOLO loses track and id is None)
                    track_id = int(box.id[0].cpu().numpy()) if box.id is not None else None
                    
                    # Convert to [x, y, width, height] for easier frontend rendering
                    w = x2 - x1
                    h = y2 - y1
                    
                    detections.append({
                        "track_id": track_id,
                        "bbox": [float(x1), float(y1), float(w), float(h)],
                        "confidence": round(conf, 3),
                        "label": label,
                        "student_id": None
                    })
            
            logger.debug(f"YOLO tracked {len(detections)} people (conf > {conf_threshold})")
            return detections, ""
            
        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return [], str(e)

# Create a global instance getter for easy use
def get_detection_service() -> DetectionService:
    return DetectionService()
