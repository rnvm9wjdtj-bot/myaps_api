"""
数据清洗模块
包含字段校验、关联校验、数据转换等功能
"""
import json
from datetime import datetime
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
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)


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
    LOT_SIZE_ENUM = {"EX", "FX", "D1", "D2", "D3", "D4", "D5", "D6", "W1", "W2", "W3", "W4", "M1", "M2", "VB"}
    MOLD_TYPE_ENUM = {"注塑", "冲压", "压铸", "夹具"}
    MOLD_STATUS_ENUM = {"空闲", "生产中", "维修中", "报废"}

    def __init__(self, db_name: str):
        self.db_name = db_name
        self.errors: List[Dict] = []
    
    async def check_duplicate(self, table_name: str, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """检测缓冲表中是否存在重复数据"""
        pk_fields = BUSINESS_KEYS.get(table_name, [])
        if not pk_fields:
            return True, []
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            return True, []
        
        conditions = {}
        for pk in pk_fields:
            value = data.get(pk)
            if value is not None and value != '':
                conditions[pk] = value
        
        if not conditions:
            return True, []
        
        query = staging_model.filter(**conditions)
        if staging_id:
            query = query.exclude(_staging_id=staging_id)
        
        try:
            count = await query.count()
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
        for err in errors:
            await ValidationError.create(
                staging_table=staging_table,
                staging_id=err.get("staging_id"),
                error_type=err["error_type"],
                error_field=err["error_field"],
                error_value=err.get("error_value"),
                error_message=err["error_message"],
                suggestion=self._get_suggestion(err["error_type"])
            )

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

    async def process_staging(self, table_name: str, batch_size: int = 100, use_transaction: bool = True) -> Dict[str, int]:
        """处理缓冲表数据"""
        from tortoise.transactions import in_transaction
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")

        stats = {"validated": 0, "rejected": 0, "synced": 0}

        pending_records = await staging_model.filter(_status=StagingStatus.PENDING).limit(batch_size)

        if not pending_records:
            return stats

        if use_transaction:
            async with in_transaction(connection_name=self.db_name) as tx:
                for record in pending_records:
                    data = self._record_to_dict(record)

                    is_valid, errors = await self._validate(table_name, record._staging_id, data)

                    if is_valid:
                        record._status = StagingStatus.VALIDATED
                        stats["validated"] += 1
                    else:
                        record._status = StagingStatus.REJECTED
                        record._error_msg = json.dumps(errors, ensure_ascii=False)
                        stats["rejected"] += 1
                        await self.cleaner.save_errors(table_name, errors)

                    await record.save(using_db=tx)
        else:
            for record in pending_records:
                data = self._record_to_dict(record)

                is_valid, errors = await self._validate(table_name, record._staging_id, data)

                if is_valid:
                    record._status = StagingStatus.VALIDATED
                    stats["validated"] += 1
                else:
                    record._status = StagingStatus.REJECTED
                    record._error_msg = json.dumps(errors, ensure_ascii=False)
                    stats["rejected"] += 1
                    await self.cleaner.save_errors(table_name, errors)

                await record.save()

        return stats

    async def sync_to_production(self, table_name: str, batch_size: int = 100, 
                                   max_retries: int = 3, use_transaction: bool = True) -> Dict[str, int]:
        """同步到正式表（使用原生SQL）"""
        from tortoise import Tortoise
        from tortoise.transactions import in_transaction
        from core.settings import THIS_DB_NAME, MYAPS_MAIN_DB
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        target_model = self.TARGET_MODELS.get(table_name)
        
        if not staging_model or not target_model:
            raise ValueError(f"未知的表: {table_name}")

        stats = {"synced": 0, "failed": 0, "skipped": 0}

        validated_records = await staging_model.filter(
            _status=StagingStatus.VALIDATED
        ).filter(
            _retry_count__lt=max_retries
        ).limit(batch_size)

        if not validated_records:
            return stats

        pg_conn = Tortoise.get_connection(THIS_DB_NAME)
        mysql_conn = Tortoise.get_connection(MYAPS_MAIN_DB)

        pk_fields = []
        for field_name, field in target_model._meta.fields_map.items():
            if field.pk:
                pk_fields.append(field_name)

        staging_field_map = {}
        target_field_map = {}
        for field in staging_model._meta.fields_map.values():
            db_col = field.source_field if field.source_field else field.model_field_name
            staging_field_map[field.model_field_name] = db_col
        for field in target_model._meta.fields_map.values():
            db_col = field.source_field if field.source_field else field.model_field_name
            target_field_map[field.model_field_name] = db_col

        staging_table_name = staging_model._meta.table
        target_table_name = target_model._meta.table

        for record in validated_records:
            try:
                staging_data = self._record_to_dict(record, exclude_staging_fields=True)
                
                target_data = {}
                for staging_field, value in staging_data.items():
                    if staging_field not in target_field_map:
                        continue
                    target_col = target_field_map.get(staging_field, staging_field)
                    target_data[target_col] = value

                pk_conditions = []
                pk_values = []
                for pk_field in pk_fields:
                    pk_col = staging_field_map.get(pk_field, pk_field)
                    if pk_col in target_data:
                        pk_conditions.append(f"`{pk_col}` = %s")
                        pk_values.append(target_data[pk_col])

                if not pk_conditions:
                    stats["skipped"] += 1
                    continue

                check_query = f"SELECT COUNT(*) as cnt FROM `{target_table_name}` WHERE {' AND '.join(pk_conditions)}"
                result = await mysql_conn.execute_query(check_query, tuple(pk_values))
                exists = result[1][0]['cnt'] > 0 if result[1] else False

                if exists:
                    set_parts = []
                    values = []
                    for col, val in target_data.items():
                        if col not in [staging_field_map.get(pk, pk) for pk in pk_fields]:
                            set_parts.append(f"`{col}` = %s")
                            values.append(val)
                    values.extend(pk_values)
                    
                    sync_query = f"UPDATE `{target_table_name}` SET {', '.join(set_parts)} WHERE {' AND '.join(pk_conditions)}"
                else:
                    columns = [f"`{col}`" for col in target_data.keys()]
                    placeholders = ", ".join(["%s"] * len(target_data))
                    sync_query = f"INSERT INTO `{target_table_name}` ({', '.join(columns)}) VALUES ({placeholders})"
                    values = list(target_data.values())

                await mysql_conn.execute_query(sync_query, tuple(values))
                
                update_query = f'UPDATE "{staging_table_name}" SET "_status" = $1, "_synced_time" = $2 WHERE "_staging_id" = $3'
                await pg_conn.execute_query(update_query, ("synced", datetime.now(), record._staging_id))
                
                stats["synced"] += 1
                
            except Exception as e:
                record._retry_count += 1
                record._error_msg = str(e)
                stats["failed"] += 1
                logger.error(f"同步失败 [{table_name}] _staging_id={record._staging_id}, retry={record._retry_count}: {str(e)}")
                
                if record._retry_count >= max_retries:
                    record._status = StagingStatus.REJECTED
                    logger.warning(f"记录达到最大重试次数，已标记为拒绝: _staging_id={record._staging_id}")
                
                await record.save()

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
