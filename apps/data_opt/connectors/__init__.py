# import threading
from abc import ABC, abstractmethod


class ScheduleTasks(ABC):
    
    @classmethod
    @abstractmethod
    def get_material(cls, *args, **kwargs):
        pass
    
    @classmethod
    @abstractmethod
    def refresh_stock(cls, *args, **kwargs):
        pass



class MyapsDbEvents(ABC):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)