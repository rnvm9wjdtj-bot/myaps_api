import os

from ._json_manager import JSONManager


cache_file = JSONManager(f"cache/{os.getenv("CACHE_FILE")}")



# from globalobjects.globalconst import AbcEnum, EfEnum, YesNoEnum, LotSizeEnum


class ProjectDefaultValues:
    defaults = cache_file.get("defaults", {})

    auto_matver = defaults.get("auto_matver", True)  # 1 / 0 是否自动生成物料版本号，为True时，会在 material save时自动生成产线版本
    matver_prefix = defaults.get("matver_prefix", "V") # 产线版本前缀字母
    matver_width = defaults.get("matver_width", 1)    # 产线版本号数字宽度

    itemno_prefix = defaults.get("itemno_prefix", "A") # 工序项目前缀字母
    itemno_width = defaults.get("itemno_width", 3)    # 工序项目号数字宽度
    
    MAT_PLANT = defaults.get("plant", "None")   # 默认工厂
    MAT_PLANNER = defaults.get("planner", "None")   # 默认计划员
    MAT_LOCATION = defaults.get("location", "None")  # 默认车间

    MAT_FIFO = defaults.get("fifo", 1)   # 默认FIFO原则
    MAT_LEADDAY_E = defaults.get("leadday_e", 10)  # 自制件默认提前期
    MAT_LEADDAY_F = defaults.get("leadday_f", 1)  # 采购件默认提前期
    MAT_EXPDAY = defaults.get("expday", 365)  # 默认保质期
    # MAT_PRICE = 0  # 默认价格
    MAT_GRDAY_E = defaults.get("grday_e", 0)
    MAT_GRDAY_F = defaults.get("grday_f", 0)
    MAT_PHANTOM = defaults.get("phantom", "N")  # 是否虚拟件
    MAT_PHANTOMMIN = defaults.get("phantommin", 0)
    MAT_FIRMDAY = defaults.get("firmday", 0)
    MAT_DAYGAP = defaults.get("daygap", 1)  # 默认计划间隔
    MAT_CANDELAY = defaults.get("candelay", "Y")  # 是否允许延迟计划
    MAT_LOTSIZE = defaults.get("lotsize", "EX")  # 默认批次大小
    MAT_LOTFIX = defaults.get("lotfix", 0)  # 默认固定批
    MAT_LOTMIN = defaults.get("lotmin", 0)  # 默认最小批
    MAT_LOTMAX = defaults.get("lotmax", 0)  # 默认最大批
    MAT_LOTROUND = defaults.get("lotround", 0)  # 默认取整
    MAT_LOTSS = defaults.get("lotss", 0)  # 默认安全库存
    MAT_LOTPOINT = defaults.get("lotpoint", 0)  # 默认重订货点
    MAT_LOTTOP = defaults.get("lottop", 0)  # 默认最大库存点
    MAT_PREDAY = defaults.get("preday", 999)  # 默认向前冲销(天)
    MAT_SUBDAY = defaults.get("subday", 999)  # 默认向后冲销(天)

    MATVER = f"{matver_prefix}{1:0{matver_width}d}"  # 示例 / 默认物料版本号
    MATVER_LOTFROM = defaults.get("lotfrom", 0)  # 默认最小批
    MATVER_LOTTO = defaults.get("lotto", 9999999)  # 默认最大批
    MATVER_PRIORITY = defaults.get("priority", 0)  # 默认优先级

    WC_WORKER = defaults.get("worker", 1)  # 默认工人数
    WC_PRIORITY = defaults.get("wc_priority", 0)  # 默认优先级

    ITEMNO = f"{itemno_prefix}{1:0{itemno_width}d}" # 示例 / 默认工序项目

    MATWC_RATE = defaults.get("matwc_rate", 1.0)  # 默认配比
