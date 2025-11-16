# service_locator.py
import threading
from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class ServiceLocator:
    _services = {}
    _lock = threading.Lock()
    
    # Chat mode flags
    test_mode = False
    memo_mode = False

    @classmethod
    def register(cls, name: str, service: object) -> None:
        with cls._lock:
            cls._services[name] = service

    @classmethod
    def get(cls, name: str) -> object:
        with cls._lock:
            return cls._services.get(name)
    
    @classmethod
    def set_test_mode(cls, enabled: bool):
        with cls._lock:
            cls.test_mode = enabled
            cls.memo_mode = False  # Ensure only one mode is active
    
    @classmethod
    def set_memo_mode(cls, enabled: bool):
        with cls._lock:
            cls.memo_mode = enabled
            cls.test_mode = False  # Ensure only one mode is active
    
    @classmethod
    def set_normal_mode(cls):
        with cls._lock:
            cls.test_mode = False
            cls.memo_mode = False

class DIProxy:
    def __getattr__(self, name: str) -> object:
        service = ServiceLocator.get(name)
        if service is None:
            raise AttributeError(f"Service '{name}' not registered.")
        return service

# Global DI instance for convenience
DI = DIProxy()
