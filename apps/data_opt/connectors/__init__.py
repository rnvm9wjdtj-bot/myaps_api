import threading
from abc import ABC, abstractmethod


class BaseConnector(ABC):
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize_connection()
        return cls._instance

    @abstractmethod
    def __init__(self, *args, **kwargs):
        pass

    @abstractmethod
    def auth(self, *args, **kwargs):
        pass

    @abstractmethod
    def get_data(self, *args, **kwargs):
        pass

    @abstractmethod
    def set_data(self, *args, **kwargs):
        pass