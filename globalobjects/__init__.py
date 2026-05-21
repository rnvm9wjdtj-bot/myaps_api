import os
from pathlib import Path

from .logger import (
    SmartLogger,
    get_logger,
    logger,
    LogHelper,
    EmojiManager,
    emoji_manager,
    initialize_logging,
    shutdown_logging,
    set_db_initialized,
)

current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
pf_dir = os.getenv("PROJECT_DIR")

if pf_dir is not None:
    from .json_manager import JSONManager
    project_json = (os.getenv("PROJECT_JSON") or "dev") + ".json"
    PROJECT_JSON_FILE = JSONManager(f"{root_dir}/project_files/{pf_dir}/{project_json}")
    
    from .event_aggregator import get_global_handler_aggregator
    EVENT_AGGREGATOR = get_global_handler_aggregator()
    
    from .reminder import Reminder, RemindType, remind_manager, QqEmailReminder
    from .globalconst import StaticString
else:
    PROJECT_JSON_FILE = None
    EVENT_AGGREGATOR = None

__all__ = [
    "SmartLogger",
    "get_logger",
    "logger",
    "LogHelper",
    "EmojiManager",
    "emoji_manager",
    "initialize_logging",
    "shutdown_logging",
    "set_db_initialized",
]

if pf_dir is not None:
    __all__.extend([
        "Reminder",
        "RemindType",
        "remind_manager",
        "QqEmailReminder",
        "StaticString",
        "ProjectDefaultValues",
    ])
    
    class ProjectDefaultValues:
        defaults = PROJECT_JSON_FILE.get("defaults", {})
        no_fill_defaults = defaults.get("!no_fill_defaults", [])
        auto_matver = defaults.get("auto_matver", False)
        matver_prefix = defaults.get("matver_prefix", "V")
        matver_width = defaults.get("matver_width", 1)
        itemno_prefix = defaults.get("itemno_prefix", "A")
        itemno_width = defaults.get("itemno_width", 3)
        MAT_PLANT = defaults.get("plant", "None")
        MAT_PLANNER = defaults.get("planner", "None")
        MAT_LOCATION = defaults.get("location", "None")
        MAT_FIFO = defaults.get("fifo", 1)
        MAT_LEADDAY_E = defaults.get("leadday_e", 10)
        MAT_LEADDAY_F = defaults.get("leadday_f", 1)
        MAT_EXPDAY = defaults.get("expday", 365)
        MAT_GRDAY_E = defaults.get("grday_e", 0)
        MAT_GRDAY_F = defaults.get("grday_f", 0)
        MAT_PHANTOM = defaults.get("phantom", "N")
        MAT_PHANTOMMIN = defaults.get("phantommin", 0)
        MAT_FIRMDAY = defaults.get("firmday", 0)
        MAT_DAYGAP = defaults.get("daygap", 1)
        MAT_CANDELAY = defaults.get("candelay", "Y")
        MAT_LOTSIZE = defaults.get("lotsize", "EX")
        MAT_LOTFIX = defaults.get("lotfix", 0)
        MAT_LOTMIN = defaults.get("lotmin", 0)
        MAT_LOTMAX = defaults.get("lotmax", 0)
        MAT_LOTROUND = defaults.get("lotround", 0)
        MAT_LOTSS = defaults.get("lotss", 0)
        MAT_LOTPOINT = defaults.get("lotpoint", 0)
        MAT_LOTTOP = defaults.get("lottop", 0)
        MAT_PREDAY = defaults.get("preday", 999)
        MAT_SUBDAY = defaults.get("subday", 999)
        MATVER = f"{matver_prefix}{1:0{matver_width}d}"
        MATVER_LOTFROM = defaults.get("lotfrom", 0)
        MATVER_LOTTO = defaults.get("lotto", 9999999)
        MATVER_PRIORITY = defaults.get("priority", 0)
        WC_WORKER = defaults.get("worker", 1)
        WC_PRIORITY = defaults.get("wc_priority", 0)
        WC_CAPNUM = defaults.get("capnum", 1)
        WC_CAPMAX = defaults.get("capmax", 1)
        ITEMNO = f"{itemno_prefix}{1:0{itemno_width}d}"
        MATWC_RATE = defaults.get("matwc_rate", 1.0)
        WORKREPORT_STATUS = defaults.get("workreport_status", "N")


