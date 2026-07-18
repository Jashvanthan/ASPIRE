import time
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class CooldownService:
    """
    Singleton service for managing rate limits and cooldowns in memory.
    Useful for throttling logs, heavy ML pipelines, and attendance marks.
    """
    _instance: Optional["CooldownService"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._last_seen: dict[str, float] = {}
        self._data_lock = threading.Lock()
        logger.info("CooldownService created.")

    def is_on_cooldown(self, key: str, cooldown_seconds: float) -> bool:
        """
        Check if an event keyed by `key` is currently on cooldown.
        If it is NOT on cooldown, the cooldown timestamp is updated to the current time.
        
        Args:
            key: Unique string identifying the event/action (e.g., 'sec_genuine_CS101').
            cooldown_seconds: The required wait time in seconds before it can trigger again.
            
        Returns:
            True if it's on cooldown (cannot run), False if it is allowed to run.
        """
        current_time = time.time()
        
        with self._data_lock:
            last_time = self._last_seen.get(key, 0.0)
            
            if current_time - last_time < cooldown_seconds:
                return True
                
            # Not on cooldown, update timestamp
            self._last_seen[key] = current_time
            return False

    def clear_key(self, key: str) -> None:
        """Manually clear a cooldown key."""
        with self._data_lock:
            self._last_seen.pop(key, None)

    def clear_all(self) -> None:
        """Clear all cooldowns."""
        with self._data_lock:
            self._last_seen.clear()

def get_cooldown_service() -> CooldownService:
    return CooldownService()
