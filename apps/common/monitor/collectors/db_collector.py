"""
数据库指标采集器

采集数据库连接状态、连接池信息等
"""

import time
import asyncio
from typing import Dict, Any, List
from globalobjects import logger as log_config, RemindType, reminder_manager
from globalobjects.db_manager import get_db_managers
from core.settings import MYAPS_MAIN_DB


logger = log_config.get_logger(__name__)


def sort_databases(db_names: List[str]) -> List[str]:
    """
    对数据库名称进行排序，MYAPS_MAIN_DB 排在第一位

    Args:
        db_names: 数据库名称列表

    Returns:
        List[str]: 排序后的数据库名称列表
    """
    if MYAPS_MAIN_DB not in db_names:
        return db_names
    
    sorted_names = [MYAPS_MAIN_DB]
    for name in db_names:
        if name != MYAPS_MAIN_DB:
            sorted_names.append(name)
    return sorted_names


class DatabaseCollector:
    """数据库指标采集器"""

    def __init__(self):
        self._db_managers = get_db_managers()


    async def get_connection_status(self) -> Dict[str, Any]:
        """
        获取数据库连接状态

        Returns:
            Dict: 各数据库连接状态
        """
        status = {
            "timestamp": time.time(),
            "connections": {},
            "summary": {
                "total": 0,
                "healthy": 0,
                "unhealthy": 0,
            },
        }

        try:
            db_names = list(self._db_managers.keys())
            sorted_db_names = sort_databases(db_names)
            
            for db_name in sorted_db_names:
                manager = self._db_managers[db_name]
                try:
                    is_healthy = await manager.check_connection_health()
                    status["connections"][db_name] = {
                        "healthy": is_healthy,
                        "last_check": time.time(),
                    }
                    status["summary"]["total"] += 1
                    if is_healthy:
                        status["summary"]["healthy"] += 1
                    else:
                        status["summary"]["unhealthy"] += 1
                except Exception as e:
                    status["connections"][db_name] = {
                        "healthy": False,
                        "error": str(e),
                    }
                    status["summary"]["total"] += 1
                    status["summary"]["unhealthy"] += 1
            if status["summary"]["unhealthy"] > 0:
                await reminder_manager.trigger_remind(RemindType.DB_CONNECTION, status["summary"]["unhealthy"])
        except Exception as e:
            logger.error(f"获取数据库连接状态失败: {e}")
            status["error"] = str(e)
            await reminder_manager.trigger_remind(RemindType.DB_CONNECTION, status)

        return status


    async def get_pool_status(self) -> Dict[str, Any]:
        """
        获取连接池状态

        Returns:
            Dict: 连接池信息
        """
        pool_info = {
            "timestamp": time.time(),
            "pools": {},
        }

        try:
            # 每次都获取最新的数据库管理器实例
            self._db_managers = get_db_managers()
            
            db_names = list(self._db_managers.keys())
            sorted_db_names = sort_databases(db_names)
            
            for db_name in sorted_db_names:
                manager = self._db_managers[db_name]
                try:
                    status = await manager.get_connection_pool_status()
                    status["stats"] = manager.stats if hasattr(manager, 'stats') else None
                    pool_info["pools"][db_name] = status
                except Exception as e:
                    pool_info["pools"][db_name] = {
                        "pool_available": False,
                        "error": str(e),
                    }
                    await reminder_manager.trigger_remind(RemindType.DB_POOL, pool_info)
        
        except Exception as e:
            logger.error(f"获取连接池状态失败: {e}")
            pool_info["error"] = str(e)
            await reminder_manager.trigger_remind(RemindType.DB_POOL, pool_info)
        
        return pool_info


    async def get_all_metrics(self) -> Dict[str, Any]:
        """
        获取所有数据库相关指标

        Returns:
            Dict: 完整的数据库监控指标
        """
        connections = await self.get_connection_status()
        pool = await self.get_pool_status()

        return {
            "timestamp": time.time(),
            "main_db": MYAPS_MAIN_DB,
            "connections": connections,
            "pool": pool,
        }
