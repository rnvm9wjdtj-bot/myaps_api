"""
数据清洗模块
包含字段校验、关联校验、数据转换等功能
"""
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, Type
from enum import Enum

from tortoise import Tortoise
from tortoise.models import Model

from apps.data_opt.staging_models import (
    StagingStatus, ValidationError, TransformRule,
    TMaterialStaging, TWorkcenterStaging, TMatVerStaging,
    TMatWcStaging, TMatWcBomStaging, TMoldStaging, TMatWcMoldStaging,
    STAGING_MODEL_MAPPING
)
from apps.io_api.models import (
    TMaterial, TWorkcenter, TMatVer, TMatWc, TMatWcBom, TMold, TMatWcMold
)
from apps.io_api.schemas import AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom, AcceptMold, AcceptMatWcMold
from globalobjects import logger as log_config, globalconst as gc

logger = log_config.get_logger(__name__)


NONE_AND_EMPTY = {None, ""}


SCHEMA_DEFAULTS = {
    "t_material": {
        "plant": AcceptMaterial.model_fields["plant"].default,
        "planner": AcceptMaterial.model_fields["planner"].default,
        "fifo": AcceptMaterial.model_fields["fifo"].default,
        "expday": AcceptMaterial.model_fields["expday"].default,
        "phantom": AcceptMaterial.model_fields["phantom"].default,
        "phantommin": AcceptMaterial.model_fields["phantommin"].default,
        "firmday": AcceptMaterial.model_fields["firmday"].default,
        "daygap": AcceptMaterial.model_fields["daygap"].default,
        "candelay": AcceptMaterial.model_fields["candelay"].default,
        "lotsize": AcceptMaterial.model_fields["lotsize"].default,
        "lotfix": AcceptMaterial.model_fields["lotfix"].default,
        "lotmin": AcceptMaterial.model_fields["lotmin"].default,
        "lotmax": AcceptMaterial.model_fields["lotmax"].default,
        "lotround": AcceptMaterial.model_fields["lotround"].default,
        "lotss": AcceptMaterial.model_fields["lotss"].default,
        "lotpoint": AcceptMaterial.model_fields["lotpoint"].default,
        "lottop": AcceptMaterial.model_fields["lottop"].default,
        "preday": AcceptMaterial.model_fields["preday"].default,
        "subday": AcceptMaterial.model_fields["subday"].default,
    },
    "t_workcenter": {
        "pri_wc": AcceptWorkcenter.model_fields["pri_wc"].default,
        "bottleneck": AcceptWorkcenter.model_fields["bottleneck"].default,
        "plant": AcceptWorkcenter.model_fields["plant"].default,
        "finite": AcceptWorkcenter.model_fields["finite"].default,
        "type": AcceptWorkcenter.model_fields["type"].default,
    },
    "t_mat_ver": {
        "lotfrom": AcceptMatVer.model_fields["lotfrom"].default,
        "lotto": AcceptMatVer.model_fields["lotto"].default,
        "priority": AcceptMatVer.model_fields["priority"].default,
        "active": AcceptMatVer.model_fields["active"].default,
    },
    "t_mat_wc": {
        "fixqty": AcceptMatWc.model_fields["fixqty"].default,
        "fixsec": AcceptMatWc.model_fields["fixsec"].default,
        "sf": AcceptMatWc.model_fields["sf"].default,
        "offsetsec": AcceptMatWc.model_fields["offsetsec"].default,
        "rate": AcceptMatWc.model_fields["rate"].default,
    },
    "t_mat_wc_bom": {
        "offsethour": AcceptMatWcBom.model_fields["offsethour"].default,
    },
    "t_mold": {},
    "t_mat_wc_mold": {
        "moldno": AcceptMatWcMold.model_fields["moldno"].default,
        "fixsec": AcceptMatWcMold.model_fields["fixsec"].default,
    },
}


def fill_defaults(table_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    填充默认值：对于NULL或空字符串的字段，使用schemas.py中定义的默认值填充
    
    Args:
        table_name: 表名
        data: 原始数据字典
        
    Returns:
        填充后的数据字典
    """
    defaults = SCHEMA_DEFAULTS.get(table_name, {})
    
    result = data.copy()
    
    # 根据字段类型获取默认值
    schema_map = {
        "t_material": AcceptMaterial,
        "t_workcenter": AcceptWorkcenter,
        "t_mat_ver": AcceptMatVer,
        "t_mat_wc": AcceptMatWc,
        "t_mat_wc_bom": AcceptMatWcBom,
        "t_mold": AcceptMold,
        "t_mat_wc_mold": AcceptMatWcMold,
    }
    
    schema_class = schema_map.get(table_name)
    if not schema_class:
        return data
    
    # 遍历所有字段，填充默认值
    for field_name, field_info in schema_class.model_fields.items():
        current_value = result.get(field_name)
        
        # 如果当前值是 None 或空字符串
        if current_value in NONE_AND_EMPTY:
            # 优先使用 SCHEMA_DEFAULTS 中的默认值
            if field_name in defaults and defaults[field_name] is not None:
                default_value = defaults[field_name]
                if isinstance(default_value, datetime):
                    default_value = default_value.replace(tzinfo=timezone.utc)
                result[field_name] = default_value
                logger.debug(f"填充默认值: {table_name}.{field_name} = {default_value}")
            else:
                # 根据 Field 定义获取默认值
                field_default = field_info.default
                
                # 如果 Field 默认值不是 None 且不是 PydanticUndefined
                if field_default is not None and str(field_default) != 'PydanticUndefined':
                    result[field_name] = field_default
                    logger.debug(f"填充字段默认值: {table_name}.{field_name} = {field_default}")
                # 对于可选的字符串字段，填充空字符串
                elif field_name in ['size', 'planitem', 'memo', 'free1', 'free2', 'free3']:
                    result[field_name] = ""
                    logger.debug(f"填充空字符串: {table_name}.{field_name} = ''")
                # 对于可选的数值字段，填充 0
                elif field_name in ['lotmin', 'lotmax']:
                    result[field_name] = 0.0
                    logger.debug(f"填充零值: {table_name}.{field_name} = 0.0")
    
    return result


class ErrorType(str, Enum):
    """错误类型枚举"""
    REQUIRED_FIELD = "required_field"           # 必填字段缺失
    INVALID_ENUM = "invalid_enum"               # 枚举值非法
    INVALID_TYPE = "invalid_type"               # 类型错误
    INVALID_RANGE = "invalid_range"             # 数值范围错误
    FK_NOT_FOUND = "fk_not_found"               # 外键引用不存在
    DUPLICATE_KEY = "duplicate_key"             # 主键重复
    BUSINESS_RULE = "business_rule"             # 业务规则违反


BUSINESS_KEYS = {
    "t_material": ["materialno"],
    "t_workcenter": ["workcenter"],
    "t_mat_ver": ["materialno", "matver"],
    "t_mat_wc": ["materialno", "matver", "itemno"],
    "t_mat_wc_bom": ["productno", "matver", "itemno", "materialno"],
    "t_mold": ["moldno"],
    "t_mat_wc_mold": ["materialno", "workcenter", "itemno", "moldno"],
}


class DataCleaner:
    """数据清洗器"""

    MATERIAL_TYPE_ENUM = {"E", "P", "F", "M", "B"}
    YES_NO_ENUM = {"Y", "N"}
    ABC_ENUM = {"A", "B", "C"}
    FIFO_ENUM = {0, 1, "0", "1"}
    LOT_SIZE_ENUM = {"EX", "FX", "D1", "D2", "D3", "D4", "D5", "D6", "W1", "W2", "W3", "W4", "M1", "M2", "VB"}
    MOLD_TYPE_ENUM = {"注塑", "冲压", "压铸", "夹具"}
    MOLD_STATUS_ENUM = {"空闲", "生产中", "维修中", "报废"}

    def __init__(self, db_name: str):
        self.db_name = db_name
        self.errors: List[Dict] = []
    
    async def check_duplicate(self, table_name: str, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """检测缓冲表中是否存在重复数据（使用原生SQL避免ORM时区问题）"""
        from tortoise import Tortoise
        
        pk_fields = BUSINESS_KEYS.get(table_name, [])
        if not pk_fields:
            return True, []
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            return True, []
        
        conditions = {}
        field_map = {}
        for field in staging_model._meta.fields_map.values():
            db_col = field.source_field if field.source_field else field.model_field_name
            field_map[field.model_field_name] = db_col
        
        for pk in pk_fields:
            value = data.get(pk)
            if value is not None and value != '':
                conditions[pk] = value
        
        if not conditions:
            return True, []
        
        table_name_staging = f"{table_name}_staging"
        conn = Tortoise.get_connection(self.db_name)
        
        try:
            where_clauses = []
            params = []
            for pk, value in conditions.items():
                db_col = field_map.get(pk, pk)
                where_clauses.append(f'"{db_col}" = ${len(params) + 1}')
                params.append(value)
            
            if staging_id:
                where_clauses.append(f'"_staging_id" != ${len(params) + 1}')
                params.append(staging_id)
            
            query = f'SELECT COUNT(*) as cnt FROM "{table_name_staging}" WHERE {" AND ".join(where_clauses)}'
            result = await conn.execute_query(query, tuple(params))
            count = result[1][0]["cnt"] if result[1] else 0
            
            if count > 0:
                pk_values = "/".join([str(data.get(pk, "")) for pk in pk_fields])
                pk_fields_str = "/".join(pk_fields)
                return False, [self._create_error(
                    staging_id, ErrorType.DUPLICATE_KEY,
                    pk_fields_str, pk_values,
                    f"缓冲表中已存在相同记录（主键：{pk_values}）"
                )]
            return True, []
        except Exception as e:
            logger.error(f"检测重复失败: {str(e)}")
            return True, []

    async def validate_material(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验物料数据"""
        errors = []

        if not data.get("materialno"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "materialno", None, "物料号不能为空"))

        if not data.get("description"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "description", None, "物料描述不能为空"))

        if not data.get("plant"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "plant", None, "工厂不能为空"))

        abc_value = data.get("abc")
        logger.info(f"[校验] staging_id={staging_id}, abc={abc_value}, ABC_ENUM={self.ABC_ENUM}")
        if abc_value and str(abc_value) not in self.ABC_ENUM:
            logger.warning(f"[校验失败] abc={abc_value} 不在合法枚举值中")
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "abc", abc_value,
                f"ABC分类必须为: A, B, C"))

        if data.get("fifo") is not None and str(data["fifo"]) not in {"0", "1"}:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "fifo", data["fifo"],
                f"FIFO必须为: 0 或 1"))

        if data.get("type") and data["type"] not in self.MATERIAL_TYPE_ENUM:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "type", data["type"], 
                f"物料类型必须为: {self.MATERIAL_TYPE_ENUM}"))

        if data.get("phantom") and data["phantom"] not in self.YES_NO_ENUM:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "phantom", data["phantom"],
                f"虚拟件标识必须为: {self.YES_NO_ENUM}"))

        if data.get("candelay") and data["candelay"] not in self.YES_NO_ENUM:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "candelay", data["candelay"],
                f"可否延迟必须为: {self.YES_NO_ENUM}"))

        if data.get("lotsize") and data["lotsize"] not in self.LOT_SIZE_ENUM:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "lotsize", data["lotsize"],
                f"批量策略必须为: {self.LOT_SIZE_ENUM}"))

        leadday = data.get("leadday")
        if leadday is not None and leadday < 0:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_RANGE, "leadday", leadday, "提前期不能为负数"))

        lotmin = data.get("lotmin")
        lotmax = data.get("lotmax")
        if lotmin is not None and lotmax is not None and lotmin > lotmax:
            errors.append(self._create_error(staging_id, ErrorType.BUSINESS_RULE, "lotmin/lotmax", 
                f"{lotmin}/{lotmax}", "最小批量不能大于最大批量"))

        is_unique, dup_errors = await self.check_duplicate("t_material", data, staging_id)
        errors.extend(dup_errors)

        return len(errors) == 0, errors

    async def validate_workcenter(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验工作中心数据"""
        errors = []

        if not data.get("workcenter"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "workcenter", None, "工作中心编号不能为空"))

        if data.get("bottleneck") and data["bottleneck"] not in self.YES_NO_ENUM:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "bottleneck", data["bottleneck"],
                f"瓶颈标识必须为: {self.YES_NO_ENUM}"))

        if data.get("finite") and data["finite"] not in self.YES_NO_ENUM:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "finite", data["finite"],
                f"有限产能标识必须为: {self.YES_NO_ENUM}"))

        if data.get("type") and data["type"] not in self.YES_NO_ENUM:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "type", data["type"],
                f"首页显示标识必须为: {self.YES_NO_ENUM}"))

        is_unique, dup_errors = await self.check_duplicate("t_workcenter", data, staging_id)
        errors.extend(dup_errors)

        return len(errors) == 0, errors

    async def validate_mat_ver(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验产线版本数据"""
        errors = []

        if not data.get("materialno"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "materialno", None, "物料号不能为空"))
        else:
            exists = await TMaterial.filter(materialno=data["materialno"]).exists()
            if not exists:
                errors.append(self._create_error(staging_id, ErrorType.FK_NOT_FOUND, "materialno", 
                    data["materialno"], "关联的物料不存在"))

        if not data.get("matver"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "matver", None, "版本号不能为空"))

        if data.get("active") and data["active"] not in self.YES_NO_ENUM:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "active", data["active"],
                f"激活标识必须为: {self.YES_NO_ENUM}"))

        lotfrom = data.get("lotfrom")
        lotto = data.get("lotto")
        if lotfrom is not None and lotto is not None and lotfrom > lotto:
            errors.append(self._create_error(staging_id, ErrorType.BUSINESS_RULE, "lotfrom/lotto",
                f"{lotfrom}/{lotto}", "批量下限不能大于批量上限"))

        is_unique, dup_errors = await self.check_duplicate("t_mat_ver", data, staging_id)
        errors.extend(dup_errors)

        return len(errors) == 0, errors

    async def validate_mat_wc(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验工艺路线数据"""
        errors = []

        if not data.get("materialno"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "materialno", None, "物料号不能为空"))
        else:
            exists = await TMaterial.filter(materialno=data["materialno"]).exists()
            if not exists:
                errors.append(self._create_error(staging_id, ErrorType.FK_NOT_FOUND, "materialno",
                    data["materialno"], "关联的物料不存在"))

        if not data.get("workcenter"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "workcenter", None, "工作中心不能为空"))
        else:
            exists = await TWorkcenter.filter(workcenter=data["workcenter"]).exists()
            if not exists:
                errors.append(self._create_error(staging_id, ErrorType.FK_NOT_FOUND, "workcenter",
                    data["workcenter"], "关联的工作中心不存在"))

        if data.get("materialno") and data.get("matver"):
            exists = await TMatVer.filter(materialno=data["materialno"], matver=data["matver"]).exists()
            if not exists:
                errors.append(self._create_error(staging_id, ErrorType.FK_NOT_FOUND, "matver",
                    f"{data['materialno']}/{data['matver']}", "关联的产线版本不存在"))

        if not data.get("itemno"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "itemno", None, "工序号不能为空"))

        if data.get("sf") and data["sf"] not in {"S", "F"}:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "sf", data["sf"],
                "串并行标识必须为 S(串行) 或 F(并行)"))

        if data.get("basesec") is None:
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "basesec", None, "基础工时不能为空"))
        elif data["basesec"] < 0:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_RANGE, "basesec", data["basesec"], "基础工时不能为负数"))

        is_unique, dup_errors = await self.check_duplicate("t_mat_wc", data, staging_id)
        errors.extend(dup_errors)

        return len(errors) == 0, errors

    async def validate_mat_wc_bom(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验物料清单数据"""
        errors = []

        if not data.get("productno"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "productno", None, "父件料号不能为空"))
        else:
            exists = await TMaterial.filter(materialno=data["productno"]).exists()
            if not exists:
                errors.append(self._create_error(staging_id, ErrorType.FK_NOT_FOUND, "productno",
                    data["productno"], "关联的父件物料不存在"))

        if not data.get("materialno"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "materialno", None, "子件料号不能为空"))
        else:
            exists = await TMaterial.filter(materialno=data["materialno"]).exists()
            if not exists:
                errors.append(self._create_error(staging_id, ErrorType.FK_NOT_FOUND, "materialno",
                    data["materialno"], "关联的子件物料不存在"))

        if data.get("productno") == data.get("materialno"):
            errors.append(self._create_error(staging_id, ErrorType.BUSINESS_RULE, "productno/materialno",
                f"{data.get('productno')}/{data.get('materialno')}", "父件和子件不能为同一物料"))

        if data.get("productno") and data.get("matver"):
            exists = await TMatVer.filter(materialno=data["productno"], matver=data["matver"]).exists()
            if not exists:
                errors.append(self._create_error(staging_id, ErrorType.FK_NOT_FOUND, "matver",
                    f"{data['productno']}/{data['matver']}", "关联的产线版本不存在"))

        if data.get("productno") and data.get("matver") and data.get("itemno"):
            exists = await TMatWc.filter(
                materialno=data["productno"], 
                matver=data["matver"], 
                itemno=data["itemno"]
            ).exists()
            if not exists:
                errors.append(self._create_error(staging_id, ErrorType.FK_NOT_FOUND, "itemno",
                    f"{data['productno']}/{data['matver']}/{data['itemno']}", "关联的工序不存在"))

        if data.get("qty") is None:
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "qty", None, "用量不能为空"))
        elif data["qty"] <= 0:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_RANGE, "qty", data["qty"], "用量必须大于0"))

        if data.get("scrap") is not None and (data["scrap"] < 0 or data["scrap"] > 100):
            errors.append(self._create_error(staging_id, ErrorType.INVALID_RANGE, "scrap", data["scrap"], "损耗率必须在0-100之间"))

        if data.get("mto") and data["mto"] not in self.YES_NO_ENUM:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "mto", data["mto"],
                f"MTO标识必须为: {self.YES_NO_ENUM}"))

        if data.get("alt") and data["alt"] not in self.YES_NO_ENUM:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "alt", data["alt"],
                f"替代料标识必须为: {self.YES_NO_ENUM}"))

        is_unique, dup_errors = await self.check_duplicate("t_mat_wc_bom", data, staging_id)
        errors.extend(dup_errors)

        return len(errors) == 0, errors

    async def validate_mold(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验模具数据"""
        errors = []

        if not data.get("moldno"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "moldno", None, "模具编号不能为空"))

        if data.get("type") and data["type"] not in self.MOLD_TYPE_ENUM:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "type", data["type"],
                f"模具类型必须为: {self.MOLD_TYPE_ENUM}"))

        if data.get("status") and data["status"] not in self.MOLD_STATUS_ENUM:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "status", data["status"],
                f"模具状态必须为: {self.MOLD_STATUS_ENUM}"))

        if data.get("moldnum") is not None and data["moldnum"] < 1:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_RANGE, "moldnum", data["moldnum"], "模具穴数必须≥1"))

        if data.get("qty") is not None and data["qty"] < 1:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_RANGE, "qty", data["qty"], "模具台数必须≥1"))

        is_unique, dup_errors = await self.check_duplicate("t_mold", data, staging_id)
        errors.extend(dup_errors)

        return len(errors) == 0, errors

    async def validate_mat_wc_mold(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验机台模具关联数据"""
        errors = []

        if not data.get("materialno"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "materialno", None, "物料号不能为空"))
        else:
            exists = await TMaterial.filter(materialno=data["materialno"]).exists()
            if not exists:
                errors.append(self._create_error(staging_id, ErrorType.FK_NOT_FOUND, "materialno",
                    data["materialno"], "关联的物料不存在"))

        if not data.get("workcenter"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "workcenter", None, "工作中心不能为空"))
        else:
            exists = await TWorkcenter.filter(workcenter=data["workcenter"]).exists()
            if not exists:
                errors.append(self._create_error(staging_id, ErrorType.FK_NOT_FOUND, "workcenter",
                    data["workcenter"], "关联的工作中心不存在"))

        if not data.get("moldno"):
            errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "moldno", None, "模具编号不能为空"))
        else:
            exists = await TMold.filter(moldno=data["moldno"]).exists()
            if not exists:
                errors.append(self._create_error(staging_id, ErrorType.FK_NOT_FOUND, "moldno",
                    data["moldno"], "关联的模具不存在"))

        if data.get("materialno") and data.get("workcenter") and data.get("itemno"):
            exists = await TMatWc.filter(
                materialno=data["materialno"],
                workcenter=data["workcenter"],
                itemno=data["itemno"]
            ).exists()
            if not exists:
                errors.append(self._create_error(staging_id, ErrorType.FK_NOT_FOUND, "itemno",
                    f"{data['materialno']}/{data['workcenter']}/{data['itemno']}", "关联的工序不存在"))

        if data.get("basesec") is not None and data["basesec"] < 0:
            errors.append(self._create_error(staging_id, ErrorType.INVALID_RANGE, "basesec", data["basesec"], "UPH不能为负数"))

        is_unique, dup_errors = await self.check_duplicate("t_mat_wc_mold", data, staging_id)
        errors.extend(dup_errors)

        return len(errors) == 0, errors

    def _create_error(self, staging_id: int, error_type: ErrorType, field: str, 
                      value: Any, message: str) -> Dict:
        """创建错误记录"""
        return {
            "staging_id": staging_id,
            "error_type": error_type.value,
            "error_field": field,
            "error_value": str(value) if value is not None else None,
            "error_message": message
        }

    async def save_errors(self, staging_table: str, errors: List[Dict]):
        """保存错误记录"""
        try:
            for err in errors:
                try:
                    await ValidationError.create(
                        staging_table=staging_table,
                        staging_id=err.get("staging_id"),
                        error_type=err["error_type"],
                        error_field=err["error_field"],
                        error_value=err.get("error_value"),
                        error_message=err["error_message"],
                        suggestion=self._get_suggestion(err["error_type"])
                    )
                except Exception as e:
                    logger.warning(f"保存单条错误记录失败(已忽略): {str(e)}")
        except Exception as e:
            import traceback
            logger.error(f"保存错误记录失败: {str(e)}")
            logger.error(traceback.format_exc())

    def _get_suggestion(self, error_type: ErrorType) -> str:
        """根据错误类型获取修复建议"""
        suggestions = {
            ErrorType.REQUIRED_FIELD: "请补充必填字段值",
            ErrorType.INVALID_ENUM: "请填写合法的枚举值",
            ErrorType.INVALID_TYPE: "请修正字段类型",
            ErrorType.INVALID_RANGE: "请修正数值范围",
            ErrorType.FK_NOT_FOUND: "请先导入关联的主数据，或检查引用值是否正确",
            ErrorType.DUPLICATE_KEY: "请检查是否存在重复数据",
            ErrorType.BUSINESS_RULE: "请检查业务规则约束",
        }
        return suggestions.get(error_type, "请检查数据正确性")


class DataTransformer:
    """数据转换器"""

    def __init__(self):
        self.rules_cache: Dict[str, TransformRule] = {}

    async def load_rules(self, source_system: str, target_table: str) -> Optional[TransformRule]:
        """加载转换规则"""
        cache_key = f"{source_system}_{target_table}"
        if cache_key not in self.rules_cache:
            rule = await TransformRule.filter(
                source_system=source_system,
                target_table=target_table,
                is_active=True
            ).first()
            self.rules_cache[cache_key] = rule
        return self.rules_cache.get(cache_key)

    async def transform(self, data: Dict[str, Any], source_system: str, target_table: str) -> Dict[str, Any]:
        """执行数据转换"""
        rule = await self.load_rules(source_system, target_table)
        if not rule:
            return data

        result = {}

        if rule.field_mappings:
            field_mappings = json.loads(rule.field_mappings)
            for target_field, source_field in field_mappings.items():
                if isinstance(source_field, str):
                    result[target_field] = data.get(source_field)
                elif isinstance(source_field, dict):
                    result[target_field] = self._extract_nested(data, source_field)

        if rule.default_values:
            default_values = json.loads(rule.default_values)
            for field, default_val in default_values.items():
                if result.get(field) is None:
                    result[field] = default_val

        if rule.value_mappings:
            value_mappings = json.loads(rule.value_mappings)
            for field, mapping in value_mappings.items():
                if result.get(field) in mapping:
                    result[field] = mapping[result[field]]

        return result

    def _extract_nested(self, data: Dict, mapping: Dict) -> Any:
        """提取嵌套字段值"""
        path = mapping.get("path", "")
        default = mapping.get("default")
        
        value = data
        for key in path.split("."):
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
        
        return value if value is not None else default


class StagingProcessor:
    """缓冲表处理器"""

    VALIDATORS = {
        "t_material": DataCleaner.validate_material,
        "t_workcenter": DataCleaner.validate_workcenter,
        "t_mat_ver": DataCleaner.validate_mat_ver,
        "t_mat_wc": DataCleaner.validate_mat_wc,
        "t_mat_wc_bom": DataCleaner.validate_mat_wc_bom,
        "t_mold": DataCleaner.validate_mold,
        "t_mat_wc_mold": DataCleaner.validate_mat_wc_mold,
    }

    TARGET_MODELS = {
        "t_material": TMaterial,
        "t_workcenter": TWorkcenter,
        "t_mat_ver": TMatVer,
        "t_mat_wc": TMatWc,
        "t_mat_wc_bom": TMatWcBom,
        "t_mold": TMold,
        "t_mat_wc_mold": TMatWcMold,
    }

    def __init__(self, db_name: str):
        self.db_name = db_name
        self.cleaner = DataCleaner(db_name)
        self.transformer = DataTransformer()

    async def process_staging(self, table_name: str, batch_size: int = 100, use_transaction: bool = True, max_batches: int = 100) -> Dict[str, int]:
        """处理缓冲表数据（校验前先填充默认值，循环处理直到没有pending记录）
        
        Args:
            table_name: 表名
            batch_size: 每批处理数量
            use_transaction: 是否使用事务
            max_batches: 最大批次数（防止无限循环）
        """
        from tortoise import Tortoise
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")

        stats = {"validated": 0, "rejected": 0, "synced": 0, "filled": 0}
        
        conn = Tortoise.get_connection(self.db_name)
        table_name_staging = f"{table_name}_staging"
        
        field_map = {}
        for field in staging_model._meta.fields_map.values():
            db_col_name = field.source_field if field.source_field else field.model_field_name
            field_map[field.model_field_name] = db_col_name
        
        batch_count = 0
        while batch_count < max_batches:
            try:
                query = f'SELECT * FROM "{table_name_staging}" WHERE "_status" = $1 LIMIT $2'
                result = await conn.execute_query(query, ("pending", batch_size))
                pending_records = result[1] if result[1] else []
            except Exception as e:
                logger.error(f"查询pending记录失败: {str(e)}")
                break
            
            if not pending_records:
                break
            
            batch_count += 1
            logger.info(f"处理第{batch_count}批，共{len(pending_records)}条记录")
            
            for raw_record in pending_records:
                record_dict = dict(raw_record)
                staging_id = record_dict["_staging_id"]
                
                try:
                    data = {}
                    for python_field, db_field in field_map.items():
                        if python_field.startswith('_'):
                            continue
                        value = record_dict.get(db_field)
                        if isinstance(value, datetime):
                            if value.tzinfo is None:
                                value = value.replace(tzinfo=timezone.utc)
                        data[python_field] = value
                    
                    logger.info(f"[校验] staging_id={staging_id}, 开始校验")
                    
                    filled_data = fill_defaults(table_name, data)
                    
                    is_valid, errors = await self._validate(table_name, staging_id, filled_data)
                    
                    logger.info(f"[校验] staging_id={staging_id}, 结果: is_valid={is_valid}, errors={len(errors)}")

                    if is_valid:
                        update_query = f'UPDATE "{table_name_staging}" SET "_status" = $1 WHERE "_staging_id" = $2'
                        await conn.execute_query(update_query, ("validated", staging_id))
                        stats["validated"] += 1
                    else:
                        error_json = json.dumps(errors, ensure_ascii=False)
                        update_query = f'UPDATE "{table_name_staging}" SET "_status" = $1, "_error_msg" = $2 WHERE "_staging_id" = $3'
                        await conn.execute_query(update_query, ("rejected", error_json, staging_id))
                        stats["rejected"] += 1
                        await self.cleaner.save_errors(table_name, errors)
                        
                except Exception as e:
                    import traceback
                    error_trace = traceback.format_exc()
                    logger.error(f"处理记录失败 [{table_name}] _staging_id={staging_id}:")
                    logger.error(error_trace)
                    error_json = json.dumps([{
                        "staging_id": staging_id,
                        "error_type": "process_error",
                        "error_field": None,
                        "error_value": None,
                        "error_message": f"处理异常: {str(e)}\n\n堆栈:\n{error_trace[:500]}"
                    }], ensure_ascii=False)
                    try:
                        update_query = f'UPDATE "{table_name_staging}" SET "_status" = $1, "_error_msg" = $2 WHERE "_staging_id" = $3'
                        await conn.execute_query(update_query, ("rejected", error_json, staging_id))
                        stats["rejected"] += 1
                    except Exception as e2:
                        logger.error(f"更新错误状态失败: {str(e2)}")

        logger.info(f"校验完成: validated={stats['validated']}, rejected={stats['rejected']}, batches={batch_count}")
        return stats

    async def sync_to_production(self, table_name: str, batch_size: int = 100, 
                                   max_retries: int = 3, use_transaction: bool = True,
                                   mode: str = "incremental", target_db: str = None,
                                   update_status: bool = True) -> Dict[str, int]:
        """同步到正式表（复用自有API的db_bupsert）
        
        Args:
            table_name: 表名
            batch_size: 每批同步数量
            max_retries: 最大重试次数
            use_transaction: 是否使用事务
            mode: 同步模式
                - incremental: 仅同步校验通过的记录
                - refresh: 清空正式表后同步全部记录
            target_db: 目标账套名，为空则使用 MYAPS_MAIN_DB
            update_status: 是否更新缓冲表状态为synced（刷新模式多账套时可能需要设为False）
        """
        from tortoise import Tortoise
        from core.settings import THIS_DB_NAME, MYAPS_MAIN_DB
        from apps.io_api.utils.db_operation import db_bupsert
        from apps.io_api.schemas import (
            AcceptMaterial, AcceptWorkcenter, AcceptMatVer, 
            AcceptMatWc, AcceptMatWcBom, AcceptMold, AcceptMatWcMold
        )
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        target_model = self.TARGET_MODELS.get(table_name)
        
        if not staging_model or not target_model:
            raise ValueError(f"未知的表: {table_name}")
        
        target_db_name = target_db if target_db else MYAPS_MAIN_DB
        stats = {"synced": 0, "failed": 0, "skipped": 0, "target_db": target_db_name}

        pg_conn = Tortoise.get_connection(THIS_DB_NAME)
        staging_table_name = staging_model._meta.db_table
        target_table_name = target_model._meta.db_table
        
        if mode == "refresh":
            mysql_conn = Tortoise.get_connection(target_db_name)
            truncate_query = f'TRUNCATE TABLE `{target_table_name}`'
            await mysql_conn.execute_query(truncate_query)
            logger.info(f"已清空正式表: {target_table_name} (账套: {target_db_name})")
        
        query = f'SELECT * FROM "{staging_table_name}" WHERE "_status" = $1 AND ("_retry_count" IS NULL OR "_retry_count" < $2) LIMIT $3'
        result = await pg_conn.execute_query(query, ("validated", max_retries, batch_size))
        records_to_sync = result[1] if result[1] else []
        
        # 检查retry_count分布
        retry_check = await pg_conn.execute_query(
            f'SELECT "_retry_count", COUNT(*) as cnt FROM "{staging_table_name}" WHERE "_status" = $1 GROUP BY "_retry_count"',
            ("validated",)
        )
        retry_dist = {row["_retry_count"]: row["cnt"] for row in retry_check[1]} if retry_check[1] else {}
        
        logger.info(f"同步查询: 表={staging_table_name}, 状态=validated, 重试<{max_retries}, 批次={batch_size}, 找到{len(records_to_sync)}条记录, retry分布={retry_dist}")
        
        if not records_to_sync:
            return stats

        # Schema映射
        schema_map = {
            "t_material": AcceptMaterial,
            "t_workcenter": AcceptWorkcenter,
            "t_mat_ver": AcceptMatVer,
            "t_mat_wc": AcceptMatWc,
            "t_mat_wc_bom": AcceptMatWcBom,
            "t_mold": AcceptMold,
            "t_mat_wc_mold": AcceptMatWcMold,
        }
        
        schema_class = schema_map.get(table_name)
        if not schema_class:
            stats["skipped"] = len(records_to_sync)
            return stats

        staging_field_map = {}
        for field in staging_model._meta.fields_map.values():
            db_col = field.source_field if field.source_field else field.model_field_name
            staging_field_map[field.model_field_name] = db_col

        data_list = []
        staging_ids = []
        
        for raw_record in records_to_sync:
            record_dict = dict(raw_record)
            staging_id = record_dict.get("_staging_id")
            
            data = {}
            for python_field, db_field in staging_field_map.items():
                if python_field.startswith('_'):
                    continue
                value = record_dict.get(db_field)
                if isinstance(value, datetime):
                    if value.tzinfo is None:
                        value = value.replace(tzinfo=timezone.utc)
                data[python_field] = value
            
            # 填充默认值（关键步骤）
            data = fill_defaults(table_name, data)
            
            try:
                schema_obj = schema_class(**data)
                data_list.append(schema_obj)
                staging_ids.append(staging_id)
            except Exception as e:
                logger.error(f"Schema转换失败 [{table_name}] _staging_id={staging_id}: {str(e)}")
                retry_count = (record_dict.get("_retry_count") or 0) + 1
                # Schema转换失败直接标记为rejected，不再重试
                error_json = json.dumps([{
                    "staging_id": staging_id,
                    "error_type": "schema_error",
                    "error_field": None,
                    "error_value": None,
                    "error_message": f"Schema转换失败: {str(e)}"
                }], ensure_ascii=False)
                
                try:
                    update_query = f'UPDATE "{staging_table_name}" SET "_retry_count" = $1, "_error_msg" = $2, "_status" = $3 WHERE "_staging_id" = $4'
                    await pg_conn.execute_query(update_query, (retry_count, error_json, "rejected", staging_id))
                except Exception as update_err:
                    logger.error(f"更新失败记录状态时出错: {update_err}")
                
                stats["failed"] = (stats.get("failed") or 0) + 1

        if not data_list:
            logger.warning(f"同步跳过 [{table_name}]: data_list为空，无有效数据可同步")
            return stats

        logger.info(f"准备同步 [{table_name}] 账套={target_db_name}: {len(data_list)}条数据, staging_ids={staging_ids[:5]}...")

        try:
            result = await db_bupsert(
                db_names=target_db_name,
                model_or_tablename=table_name,
                data_list=data_list,
                use_orm_or_sql="sql"
            )
            
            logger.info(f"db_bupsert结果 [{table_name}]: success={result.success}, message={result.message}, meta={result.meta}")
            
            synced_count = result.affected_rows or 0
            stats["synced"] = synced_count
            
            # 只有在 update_status=True 时才更新缓冲表状态
            if update_status and synced_count > 0:
                synced_time = datetime.now(timezone.utc).replace(tzinfo=None)
                for staging_id in staging_ids[:synced_count]:
                    update_query = f'UPDATE "{staging_table_name}" SET "_status" = $1, "_synced_time" = $2 WHERE "_staging_id" = $3'
                    await pg_conn.execute_query(update_query, ("synced", synced_time, staging_id))
            
            if result.has_errors:
                logger.warning(f"同步部分失败 [{table_name}] 账套={target_db_name}: {result.message}")
                stats["failed"] += len(data_list) - (synced_count or 0)
            
        except Exception as e:
            import traceback
            logger.error(f"同步失败 [{table_name}] 账套={target_db_name}: {str(e)}")
            logger.error(traceback.format_exc())
            stats["failed"] = len(data_list)
            for staging_id in staging_ids:
                retry_count = 1
                error_json = json.dumps([{
                    "staging_id": staging_id,
                    "error_type": "sync_error",
                    "error_field": None,
                    "error_value": None,
                    "error_message": f"同步失败: {str(e)}"
                }], ensure_ascii=False)
                update_query = f'UPDATE "{staging_table_name}" SET "_retry_count" = $1, "_error_msg" = $2 WHERE "_staging_id" = $3'
                await pg_conn.execute_query(update_query, (retry_count, error_json, staging_id))

        return stats

    async def _validate(self, table_name: str, staging_id: int, data: Dict) -> Tuple[bool, List[Dict]]:
        """执行校验"""
        validator = self.VALIDATORS.get(table_name)
        if validator:
            return await validator(self.cleaner, data, staging_id)
        return True, []

    def _record_to_dict(self, record: Model, exclude_staging_fields: bool = False) -> Dict[str, Any]:
        """将模型记录转换为字典"""
        data = {}
        for field_name in record._meta.fields_map:
            if exclude_staging_fields and field_name.startswith("_"):
                continue
            data[field_name] = getattr(record, field_name)
        return data
