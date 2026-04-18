
from .settings import BASE_DIR, SQLITE_FILE
from .database import TORTOISE_ORM_CONFIG


__all__ = [
    "TORTOISE_ORM_CONFIG",
    "BASE_DIR", "SQLITE_FILE"
]