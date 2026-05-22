"""
去重检测工具
支持缓冲表数据去重、重复标记等功能
"""
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict
from enum import Enum

from apps.data_opt.mds.staging_cleaner import STAGING_TABLE_CONFIG, STAGING_MODEL_MAPPING, ensure_config_initialized
from globalobjects import logger as log_config, globalconst as gc

logger = log_config.get_logger(__name__)

# 内部字段（比对时排除）
INTERNAL_FIELDS = {'_staging_id', '_status', '_error_msg', '_createtime', '_updatetime', 
                   '_synced_time', '_retry_count', '_source_system'}


def compare_content(existing_record, new_data: Dict, field_map: Dict = None, update_mode: str = "partial") -> Tuple[bool, str]:
    """
    比对已存在记录与新数据的内容是否一致
    
    Args:
        existing_record: 已存在的记录（ORM对象）
        new_data: 新数据（字典）
        field_map: 字段映射（Python字段名 -> 数据库字段名）
        update_mode: 更新模式
            - "partial": 部分更新，跳过new_data中不存在的字段（默认）
            - "full": 完整更新，所有字段都参与比对（不存在的字段视为None）
    
    Returns:
        (是否一致, 差异字段列表)
    
    关键逻辑：
    - partial模式：new_data中不存在的字段 → 跳过比对（部分更新语义）
    - new_data中存在但值为None/空字符串 → 参与比对（显式清空）
    - 与API的model_dump(exclude_none=True)行为一致
    """
    if not existing_record:
        return False, "无已存在记录"
    
    try:
        diff_fields = []
        same_count = 0
        diff_count = 0
        skip_count = 0
        
        # 获取模型的所有字段
        model_fields = existing_record._meta.fields_map.keys()
        
        for field_name in model_fields:
            # 跳过内部字段
            if field_name in INTERNAL_FIELDS:
                continue
            
            # 部分更新模式：跳过new_data中不存在的字段
            if update_mode == "partial" and field_name not in new_data:
                skip_count += 1
                continue
            
            # 获取已存在记录的值
            existing_value = getattr(existing_record, field_name, None)
            
            # 获取新数据的值
            new_value = new_data.get(field_name)
            
            # 统一NULL/空字符串处理
            existing_value = normalize_value(existing_value)
            new_value = normalize_value(new_value)
            
            # 类型一致性处理
            if existing_value is not None and new_value is not None:
                existing_value, new_value = normalize_types(existing_value, new_value)
            
            # 比较
            if existing_value != new_value:
                diff_fields.append(field_name)
                diff_count += 1
            else:
                same_count += 1
        
        # logger.info(f"内容比对: 相同字段={same_count}, 差异字段={diff_count}, 跳过字段={skip_count}, 差异列表={diff_fields[:5]}")
        
        if diff_fields:
            return False, f"差异字段: {', '.join(diff_fields[:5])}"
        
        return True, ""
        
    except Exception as e:
        logger.warning(f"内容比对异常: {str(e)}")
        # 有任何不确定时，保守策略：执行覆盖
        return False, f"比对异常: {str(e)}"


def normalize_value(value: Any) -> Any:
    """
    统一NULL/空字符串处理
    
    Args:
        value: 原始值
    
    Returns:
        标准化后的值
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == '':
        return None
    return value


def normalize_types(val1: Any, val2: Any) -> Tuple[Any, Any]:
    """
    类型一致性处理
    
    Args:
        val1: 值1
        val2: 值2
    
    Returns:
        (标准化后的值1, 标准化后的值2)
    """
    try:
        # 如果都是数值型字符串，转换为float比较
        if isinstance(val1, str) and isinstance(val2, str):
            if val1.replace('.', '').replace('-', '').isdigit() and \
               val2.replace('.', '').replace('-', '').isdigit():
                return float(val1), float(val2)
        
        # 如果一个是数值一个是字符串，统一转换
        if isinstance(val1, (int, float)) and isinstance(val2, str):
            return val1, float(val2) if val2.replace('.', '').replace('-', '').isdigit() else val2
        if isinstance(val2, (int, float)) and isinstance(val1, str):
            return float(val1) if val1.replace('.', '').replace('-', '').isdigit() else val1, val2
        
        return val1, val2
    except:
        return val1, val2


class DedupStrategy(str, Enum):
    """去重策略"""
    OVERWRITE = "overwrite"  # 覆盖已有记录
    SKIP = "skip"            # 跳过重复记录
    REJECT = "reject"        # 拒绝并报错


class DuplicateChecker:
    """去重检测器"""
    
    def __init__(self, table_name: str):
        """
        初始化去重检测器
        
        Args:
            table_name: 表名
        """
        self.table_name = table_name
        ensure_config_initialized()
        config = STAGING_TABLE_CONFIG.get(table_name, {})
        self.pk_fields = config.get("business_keys", [])
        self.staging_model = STAGING_MODEL_MAPPING.get(table_name)
        
        logger.debug(f"DuplicateChecker初始化: 表={table_name}, business_keys={self.pk_fields}, model={self.staging_model.__name__ if self.staging_model else None}")
        
        if not self.pk_fields:
            logger.warning(f"表 {table_name} 未配置 business_keys，去重策略将不生效")
    
    async def check_duplicate_in_staging(
        self,
        data: Dict[str, Any],
        exclude_staging_id: int = None
    ) -> Tuple[bool, Optional[str]]:
        """
        检测缓冲表中是否存在重复数据
        
        Args:
            data: 待检测数据
            exclude_staging_id: 排除的staging_id（更新时排除自身）
        
        Returns:
            (是否唯一, 重复的主键值)
        """
        if not self.pk_fields or not self.staging_model:
            return True, None
        
        conditions = {}
        for pk in self.pk_fields:
            value = data.get(pk)
            if value is not None and value != '':
                conditions[pk] = value
        
        if not conditions:
            return True, None
        
        query = self.staging_model.filter(**conditions)
        if exclude_staging_id:
            query = query.exclude(_staging_id=exclude_staging_id)
        
        try:
            count = await query.count()
            if count > 0:
                pk_value = "/".join([str(data.get(pk, "")) for pk in self.pk_fields])
                return False, pk_value
            return True, None
        except Exception as e:
            logger.error(f"检测重复失败: {str(e)}")
            return True, None
    
    async def batch_check_duplicates(
        self,
        data_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        批量检测重复（内部去重 + 缓冲表去重）
        
        Args:
            data_list: 数据列表
        
        Returns:
            {
                "unique": [唯一数据],
                "duplicates": [重复数据],
                "existing": [已存在于缓冲表的数据],
                "pk_map": {主键值: [索引列表]}
            }
        """
        if not self.pk_fields:
            return {
                "unique": [{"index": idx, "data": data, "pk_value": None} for idx, data in enumerate(data_list)],
                "duplicates": [],
                "existing": [],
                "pk_map": {}
            }
        
        pk_map = defaultdict(list)
        for idx, data in enumerate(data_list):
            pk_value = self._get_pk_value(data)
            if pk_value:
                pk_map[pk_value].append(idx)
        
        internal_duplicates = []
        for pk_value, indices in pk_map.items():
            if len(indices) > 1:
                internal_duplicates.append({
                    "pk_value": pk_value,
                    "indices": indices,
                    "count": len(indices)
                })
        
        unique_indices = set()
        for pk_value, indices in pk_map.items():
            unique_indices.add(indices[0])
        
        existing_in_db = []
        unique_data = []
        
        # 批量查询已存在记录（优化：一次查询替代N次查询）
        if unique_indices and self.pk_fields:
            idx_to_pk_map = {}
            
            for idx in unique_indices:
                data = data_list[idx]
                pk_value = self._get_pk_value(data)
                if pk_value:
                    idx_to_pk_map[idx] = pk_value
            
            if idx_to_pk_map:
                try:
                    # 对于复合主键，需要查询所有可能的记录后在内存中匹配
                    # 步骤1：收集每个主键字段的所有可能值
                    pk_field_values = {pk: set() for pk in self.pk_fields}
                    for idx, pk_value in idx_to_pk_map.items():
                        data = data_list[idx]
                        for pk in self.pk_fields:
                            val = data.get(pk)
                            if val is not None and val != '':
                                pk_field_values[pk].add(val)
                    
                    # 步骤2：构建查询条件（每个字段用 __in）
                    query = self.staging_model.all()
                    for pk, values in pk_field_values.items():
                        if values:
                            query = query.filter(**{f"{pk}__in": list(values)})
                    
                    # 步骤3：执行查询
                    existing_records = await query.all()
                    
                    # 步骤4：构建复合主键 -> 记录列表的映射（注意：可能有多条相同主键的记录）
                    existing_map = {}
                    for record in existing_records:
                        pk_val = self._get_pk_value_from_record(record)
                        if pk_val:
                            if pk_val not in existing_map:
                                existing_map[pk_val] = []
                            existing_map[pk_val].append(record)
                    
                    logger.debug(f"批量查询已存在记录: 表={self.table_name}, 主键字段={self.pk_fields}, 查询返回{len(existing_records)}条, 唯一主键数={len(existing_map)}")
                except Exception as e:
                    logger.error(f"批量查询已存在记录失败: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    existing_map = {}
            else:
                logger.warning(f"无有效主键值，跳过批量查询")
                existing_map = {}
            
            # 分类处理
            for idx in unique_indices:
                data = data_list[idx]
                pk_value = idx_to_pk_map.get(idx)
                
                if pk_value and pk_value in existing_map:
                    # 已存在于缓冲表
                    existing_in_db.append({
                        "index": idx,
                        "data": data,
                        "pk_value": pk_value,
                        "existing_records": existing_map[pk_value]  # 所有已存在记录列表
                    })
                else:
                    # 新数据
                    unique_data.append({
                        "index": idx,
                        "data": data,
                        "pk_value": pk_value
                    })
        else:
            # 无主键配置，全部视为新数据
            for idx in unique_indices:
                data = data_list[idx]
                pk_value = self._get_pk_value(data)
                unique_data.append({
                    "index": idx,
                    "data": data,
                    "pk_value": pk_value
                })
        
        duplicate_data = []
        for dup_info in internal_duplicates:
            # 只将重复的记录（除第一条外）加入 duplicate_data
            for idx in dup_info["indices"][1:]:
                duplicate_data.append({
                    "index": idx,
                    "data": data_list[idx],
                    "pk_value": dup_info["pk_value"],
                    "duplicate_count": dup_info["count"]
                })
        
        return {
            "unique": unique_data,
            "duplicates": duplicate_data,
            "existing": existing_in_db,
            "pk_map": dict(pk_map),
            "summary": {
                "total": len(data_list),
                "unique_count": len(unique_data),
                "duplicate_count": len(duplicate_data),
                "existing_count": len(existing_in_db)
            }
        }
    
    def _get_pk_value(self, data: Dict[str, Any]) -> Optional[str]:
        """获取数据的主键值"""
        values = []
        for pk in self.pk_fields:
            value = data.get(pk)
            if value is not None and value != '':
                values.append(str(value))
            else:
                return None
        return "/".join(values) if values else None
    
    def _get_pk_value_from_record(self, record) -> Optional[str]:
        """从ORM记录对象获取主键值"""
        values = []
        for pk in self.pk_fields:
            value = getattr(record, pk, None)
            if value is not None and value != '':
                values.append(str(value))
            else:
                return None
        return "/".join(values) if values else None
    
    def mark_duplicates_in_dataframe(
        self,
        df: pd.DataFrame,
        duplicate_indices: List[int]
    ) -> pd.DataFrame:
        """
        在DataFrame中标记重复数据
        
        Args:
            df: 数据DataFrame
            duplicate_indices: 重复数据索引列表
        
        Returns:
            标记后的DataFrame
        """
        if 'D' not in df.columns:
            df['D'] = ''
        
        for idx in duplicate_indices:
            if idx in df.index:
                df.at[idx, 'D'] = '重复'
        
        return df


async def apply_dedup_strategy(
    table_name: str,
    data_list: List[Dict[str, Any]],
    strategy: DedupStrategy = DedupStrategy.SKIP,
    update_mode: str = "partial"
) -> Tuple[List[Dict], List[Dict]]:
    """
    应用去重策略
    
    Args:
        table_name: 表名
        data_list: 数据列表
        strategy: 去重策略
        update_mode: 更新模式
            - "partial": 部分更新，跳过未传递的字段（默认）
            - "full": 完整更新，所有字段都参与比对
    
    Returns:
        (处理后的数据列表, 被处理的数据列表)
    """
    checker = DuplicateChecker(table_name)
    result = await checker.batch_check_duplicates(data_list)
    
    processed_data = []
    handled_data = []
    
    if strategy == DedupStrategy.SKIP:
        for item in result["unique"]:
            processed_data.append(item["data"])
        
        for item in result["duplicates"]:
            handled_data.append({
                "data": item["data"],
                "reason": "内部重复",
                "pk_value": item["pk_value"]
            })
        
        for item in result["existing"]:
            handled_data.append({
                "data": item["data"],
                "reason": "已存在于缓冲表",
                "pk_value": item["pk_value"]
            })
    
    elif strategy == DedupStrategy.OVERWRITE:
        # 收集所有内部重复的主键
        internal_dup_pk_values = set(item["pk_value"] for item in result["duplicates"])
        
        # 处理 unique 数据：如果主键有内部重复，跳过（保留最后一条）
        for item in result["unique"]:
            if item["pk_value"] in internal_dup_pk_values:
                # 这条会被 duplicates 中的最后一条替代
                handled_data.append({
                    "data": item["data"],
                    "reason": "内部重复（保留最后一条）",
                    "pk_value": item["pk_value"]
                })
            else:
                processed_data.append(item["data"])
        
        # 处理内部重复：保留每组最后一条，但需要检查数据库是否已存在
        internal_dup_groups = {}
        for item in result["duplicates"]:
            pk_value = item["pk_value"]
            if pk_value not in internal_dup_groups:
                internal_dup_groups[pk_value] = []
            internal_dup_groups[pk_value].append(item)
        
        for pk_value, items in internal_dup_groups.items():
            # 按索引排序，保留最后一条
            items_sorted = sorted(items, key=lambda x: x["index"])
            last_item = items_sorted[-1]
            
            # 检查该主键是否在数据库中已存在（从existing中查找）
            existing_item = None
            for ex_item in result["existing"]:
                if ex_item["pk_value"] == pk_value:
                    existing_item = ex_item
                    break
            
            if existing_item:
                # 数据库中已存在，进行内容比对
                existing_records = existing_item.get("existing_records", [])
                new_data = last_item["data"]
                
                all_same = True
                diff_info = ""
                if existing_records:
                    for existing_record in existing_records:
                        is_same, diff = compare_content(existing_record, new_data, update_mode=update_mode)
                        if not is_same:
                            all_same = False
                            diff_info = diff
                            break
                else:
                    all_same = False
                
                if all_same:
                    # 内容相同，跳过
                    handled_data.append({
                        "data": new_data,
                        "reason": "内部重复+内容相同，跳过",
                        "pk_value": pk_value,
                        "action": "skip"
                    })
                    skip_unchanged_count += 1
                else:
                    # 内容不同，覆盖
                    processed_data.append(new_data)
                    handled_data.append({
                        "data": new_data,
                        "reason": f"内部重复+覆盖已存在记录 ({diff_info})",
                        "pk_value": pk_value,
                        "action": "overwrite",
                        "existing_count": len(existing_records)
                    })
            else:
                # 数据库中不存在，直接导入
                processed_data.append(last_item["data"])
            
            # 其他内部重复条：跳过
            for item in items_sorted[:-1]:
                handled_data.append({
                    "data": item["data"],
                    "reason": "内部重复（保留最后一条）",
                    "pk_value": item["pk_value"]
                })
        
        # 处理缓冲表已存在的记录（添加内容比对）
        skip_unchanged_count = 0
        for item in result["existing"]:
            pk_value = item["pk_value"]
            
            # 如果该主键在内部重复组中，跳过（已由duplicates逻辑处理）
            if pk_value in internal_dup_pk_values:
                handled_data.append({
                    "data": item["data"],
                    "reason": "内部重复（已在duplicates中处理）",
                    "pk_value": pk_value,
                    "action": "skip"
                })
                continue
            
            existing_records = item.get("existing_records", [])
            new_data = item["data"]
            
            # 对所有已存在记录进行内容比对
            all_same = True
            diff_info = ""
            if existing_records:
                for existing_record in existing_records:
                    is_same, diff = compare_content(existing_record, new_data, update_mode=update_mode)
                    if not is_same:
                        all_same = False
                        diff_info = diff
                        break
            else:
                all_same = False
            
            if all_same:
                # 所有已存在记录内容都相同，跳过覆盖
                handled_data.append({
                    "data": new_data,
                    "reason": f"内容相同，跳过覆盖",
                    "pk_value": item["pk_value"],
                    "action": "skip"
                })
                skip_unchanged_count += 1
            else:
                # 内容不同，执行覆盖
                processed_data.append(new_data)
                handled_data.append({
                    "data": new_data,
                    "reason": f"覆盖已存在记录 ({diff_info})",
                    "pk_value": item["pk_value"],
                    "action": "overwrite",
                    "existing_count": len(existing_records)  # 标记要删除的记录数
                })
        
        # 日志记录跳过数量
        if skip_unchanged_count > 0:
            logger.info(f"内容相同跳过覆盖: {skip_unchanged_count}条")
    
    elif strategy == DedupStrategy.REJECT:
        if result["duplicates"] or result["existing"]:
            # 有重复数据，拒绝整个批次
            for item in result["unique"]:
                handled_data.append({
                    "data": item["data"],
                    "reason": "存在重复数据，拒绝导入",
                    "pk_value": item["pk_value"]
                })
            
            for item in result["duplicates"]:
                handled_data.append({
                    "data": item["data"],
                    "reason": "存在重复数据，拒绝导入",
                    "pk_value": item["pk_value"]
                })
            
            for item in result["existing"]:
                handled_data.append({
                    "data": item["data"],
                    "reason": "存在重复数据，拒绝导入",
                    "pk_value": item["pk_value"]
                })
        else:
            # 无重复数据，全部导入
            for item in result["unique"]:
                processed_data.append(item["data"])
                processed_data.append(item["data"])
    
    logger.info(
        f"去重处理完成: 策略={strategy.value}, "
        f"原始={len(data_list)}, 处理后={len(processed_data)}, 被处理={len(handled_data)}"
    )
    
    return processed_data, handled_data


def get_pk_fields(table_name: str) -> List[str]:
    """获取表的业务主键字段"""
    config = STAGING_TABLE_CONFIG.get(table_name, {})
    return config.get("business_keys", [])
