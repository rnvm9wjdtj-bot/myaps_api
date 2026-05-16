"""
去重检测工具
支持缓冲表数据去重、重复标记等功能
"""
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict
from enum import Enum

from apps.data_opt.mds.staging_cleaner import STAGING_TABLE_CONFIG, STAGING_MODEL_MAPPING, ensure_config_initialized
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)


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
        
        for idx in unique_indices:
            data = data_list[idx]
            pk_value = self._get_pk_value(data)
            
            is_unique, _ = await self.check_duplicate_in_staging(data)
            
            if is_unique:
                unique_data.append({
                    "index": idx,
                    "data": data,
                    "pk_value": pk_value
                })
            else:
                existing_in_db.append({
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
    strategy: DedupStrategy = DedupStrategy.SKIP
) -> Tuple[List[Dict], List[Dict]]:
    """
    应用去重策略
    
    Args:
        table_name: 表名
        data_list: 数据列表
        strategy: 去重策略
    
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
        
        # 处理内部重复：保留每组最后一条
        internal_dup_groups = {}
        for item in result["duplicates"]:
            pk_value = item["pk_value"]
            if pk_value not in internal_dup_groups:
                internal_dup_groups[pk_value] = []
            internal_dup_groups[pk_value].append(item)
        
        for pk_value, items in internal_dup_groups.items():
            # 按索引排序，保留最后一条
            items_sorted = sorted(items, key=lambda x: x["index"])
            # 最后一条：导入
            processed_data.append(items_sorted[-1]["data"])
            # 其他条：跳过
            for item in items_sorted[:-1]:
                handled_data.append({
                    "data": item["data"],
                    "reason": "内部重复（保留最后一条）",
                    "pk_value": item["pk_value"]
                })
        
        # 处理缓冲表已存在的记录
        for item in result["existing"]:
            processed_data.append(item["data"])
            handled_data.append({
                "data": item["data"],
                "reason": "覆盖已存在记录",
                "pk_value": item["pk_value"],
                "action": "overwrite"
            })
    
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
