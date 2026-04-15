"""
监控服务模块

整合各类采集器，提供统一的监控数据接口
"""

import time
import asyncio
from typing import Dict, Any, List, Optional, Set
from fastapi import WebSocket
from .collectors import ResourceCollector, DatabaseCollector, SchedulerCollector, HTTPCollector
from .collectors.outbound_http_collector import outbound_http_collector
from .collectors.event_collector import EventCollector
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)


class MonitorService:
    """监控服务"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.resource_collector = ResourceCollector()
        self.db_collector = DatabaseCollector()
        self.scheduler_collector = SchedulerCollector()
        self.http_collector = HTTPCollector()
        self.outbound_http_collector = outbound_http_collector
        self.event_collector = EventCollector()
        self._alerts: List[Dict[str, Any]] = []
        self._max_alerts = 100
        self._cache = {}
        self._cache_expiry = {
            "resource": 5,  # 5秒
            "database": 10,  # 10秒
            "scheduler": 30,  # 30秒
            "http": 1,  # 1秒
            "outbound_http": 1,  # 1秒
            "event": 5,  # 5秒
        }
        self._log_cache = {}
        self._log_cache_expiry = 120  # 120秒（优化：增加缓存时间）
        # 日志文件位置跟踪（优化：实现增量读取）
        self._log_file_position = {}
        # 日志轮转支持（优化：支持多个日志文件）
        self._log_files = []
        # 数据库连接检查缓存（优化：增加连接检查缓存）
        self._db_connection_cache = {}
        self._db_connection_cache_expiry = 60  # 60秒
        # 数据库健康状态（优化：实现智能检查策略）
        self._db_health_status = {}
        # WebSocket 连接管理
        self._websocket_connections: Set[WebSocket] = set()
        self._broadcast_task: Optional[asyncio.Task] = None
        self._broadcast_running = False
        self._initialized = True

    def _get_cached_data(self, key):
        """获取缓存数据"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < self._cache_expiry.get(key, 5):
                return data
        return None

    def _set_cache_data(self, key, data):
        """设置缓存数据"""
        self._cache[key] = (data, time.time())

    def get_resource_metrics(self) -> Dict[str, Any]:
        """获取资源指标"""
        # 尝试从缓存获取
        cached = self._get_cached_data("resource")
        if cached:
            return cached
        
        # 缓存过期，重新采集
        metrics = self.resource_collector.get_current_metrics()
        alerts = self.resource_collector.check_thresholds(metrics)

        for alert in alerts:
            self._add_alert("warning", alert, "resource")

        # 设置缓存
        self._set_cache_data("resource", metrics)
        return metrics

    async def get_database_metrics(self) -> Dict[str, Any]:
        """获取数据库指标"""
        # 尝试从缓存获取
        cached = self._get_cached_data("database")
        if cached:
            return cached
        
        # 缓存过期，重新采集
        metrics = await self.db_collector.get_all_metrics()
        
        # 设置缓存
        self._set_cache_data("database", metrics)
        return metrics
    
    async def get_cached_db_connection_status(self) -> Dict[str, Any]:
        """
        获取数据库连接状态（带缓存和智能检查策略）
        
        Returns:
            Dict: 各数据库连接状态
        """
        import time
        
        # 生成缓存键
        cache_key = "db_connection_status"
        
        # 检查缓存是否有效
        if cache_key in self._db_connection_cache:
            status, timestamp = self._db_connection_cache[cache_key]
            
            # 智能检查策略：根据数据库健康状态调整缓存时间
            unhealthy_count = status.get("summary", {}).get("unhealthy", 0)
            
            # 健康状态：使用较长的缓存时间
            if unhealthy_count == 0:
                cache_expiry = 60  # 60秒
            # 警告状态：使用中等缓存时间
            elif unhealthy_count < len(status.get("connections", {})):
                cache_expiry = 30  # 30秒
            # 异常状态：使用较短的缓存时间
            else:
                cache_expiry = 10  # 10秒
            
            if time.time() - timestamp < cache_expiry:
                return status
        
        # 缓存过期或不存在，重新检查
        status = await self.db_collector.get_connection_status()
        
        # 更新数据库健康状态
        self._update_db_health_status(status)
        
        # 设置缓存
        self._db_connection_cache[cache_key] = (status, time.time())
        
        return status
    
    def _update_db_health_status(self, status: Dict[str, Any]) -> None:
        """
        更新数据库健康状态
        
        Args:
            status: 数据库连接状态
        """
        connections = status.get("connections", {})
        for db_name, conn_status in connections.items():
            self._db_health_status[db_name] = {
                "healthy": conn_status.get("healthy", False),
                "last_check": conn_status.get("last_check", time.time()),
                "error": conn_status.get("error", None)
            }

    def get_scheduler_metrics(self) -> Dict[str, Any]:
        """获取定时任务指标"""
        # 尝试从缓存获取
        cached = self._get_cached_data("scheduler")
        if cached:
            return cached
        
        # 缓存过期，重新采集
        metrics = self.scheduler_collector.get_all_metrics()
        
        # 设置缓存
        self._set_cache_data("scheduler", metrics)
        return metrics

    def get_http_metrics(self) -> Dict[str, Any]:
        """获取 HTTP 指标"""
        # 尝试从缓存获取
        cached = self._get_cached_data("http")
        if cached:
            return cached
        
        # 缓存过期，重新采集
        metrics = self.http_collector.get_metrics()
        
        # 设置缓存
        self._set_cache_data("http", metrics)
        return metrics

    def get_outbound_http_metrics(self) -> Dict[str, Any]:
        """获取对外 HTTP 请求指标"""
        # 尝试从缓存获取
        cached = self._get_cached_data("outbound_http")
        if cached:
            return cached
        
        # 缓存过期，重新采集
        metrics = self.outbound_http_collector.get_metrics()
        
        # 设置缓存
        self._set_cache_data("outbound_http", metrics)
        return metrics

    def get_event_metrics(self) -> Dict[str, Any]:
        """获取事件监控指标"""
        # 尝试从缓存获取
        cached = self._get_cached_data("event")
        if cached:
            return cached
        
        # 缓存过期，重新采集
        metrics = self.event_collector.get_event_metrics()
        
        # 设置缓存
        self._set_cache_data("event", metrics)
        return metrics

    def flush_events_now(self, event_type: str = None):
        """立即刷新事件聚合器"""
        self.event_collector.flush_now(event_type)

    def reset_event_stats(self, event_type: str = None):
        """重置事件统计数据"""
        self.event_collector.reset_stats(event_type)

    async def get_overview(self) -> Dict[str, Any]:
        """获取监控总览"""
        return {
            "timestamp": time.time(),
            "resource": self.get_resource_metrics(),
            "database": await self.get_database_metrics(),
            "scheduler": self.get_scheduler_metrics(),
            "http": self.get_http_metrics(),
            "outbound_http": self.get_outbound_http_metrics(),
            "alerts": self.get_recent_alerts(10),
        }

    async def get_health_status(self) -> Dict[str, Any]:
        """获取健康检查状态"""
        checks = {}
        healthy_count = 0
        total_count = 0

        # 检查资源
        try:
            resource = self.resource_collector.get_current_metrics()
            resource_alerts = self.resource_collector.check_thresholds(resource)
            checks["resource"] = {
                "status": "healthy" if not resource_alerts else "warning",
                "message": "资源使用正常" if not resource_alerts else f"有 {len(resource_alerts)} 个告警",
            }
            if not resource_alerts:
                healthy_count += 1
            total_count += 1
        except Exception as e:
            checks["resource"] = {"status": "error", "message": str(e)}
            total_count += 1

        # 检查数据库
        try:
            db_status = await self.get_cached_db_connection_status()
            summary = db_status.get("summary", {})
            if summary.get("unhealthy", 0) == 0:
                checks["database"] = {"status": "healthy", "message": "所有数据库连接正常"}
                healthy_count += 1
            else:
                checks["database"] = {
                    "status": "warning",
                    "message": f"{summary.get('unhealthy', 0)} 个数据库连接异常",
                }
            total_count += 1
        except Exception as e:
            checks["database"] = {"status": "error", "message": str(e)}
            total_count += 1

        # 检查调度器
        try:
            scheduler = self.scheduler_collector.get_scheduler_status()
            if scheduler.get("running", False):
                checks["scheduler"] = {"status": "healthy", "message": "调度器运行正常"}
                healthy_count += 1
            else:
                checks["scheduler"] = {"status": "warning", "message": "调度器未运行"}
            total_count += 1
        except Exception as e:
            checks["scheduler"] = {"status": "error", "message": str(e)}
            total_count += 1

        # 检查 HTTP
        try:
            http_metrics = self.http_collector.get_metrics()
            summary = http_metrics.get("summary", {})
            error_rate = summary.get("error_rate", 0)
            if error_rate < 5:
                checks["http"] = {"status": "healthy", "message": f"HTTP 服务正常 (错误率: {error_rate}%)"}
                healthy_count += 1
            else:
                checks["http"] = {"status": "warning", "message": f"HTTP 错误率较高: {error_rate}%"}
            total_count += 1
        except Exception as e:
            checks["http"] = {"status": "error", "message": str(e)}
            total_count += 1

        # 检查对外 HTTP 请求
        try:
            outbound_http_metrics = self.get_outbound_http_metrics()
            summary = outbound_http_metrics.get("summary", {})
            error_rate = summary.get("error_rate", 0)
            if error_rate < 5:
                checks["outbound_http"] = {"status": "healthy", "message": f"对外 HTTP 请求正常 (错误率: {error_rate}%)"}
                healthy_count += 1
            else:
                checks["outbound_http"] = {"status": "warning", "message": f"对外 HTTP 请求错误率较高: {error_rate}%"}
            total_count += 1
        except Exception as e:
            checks["outbound_http"] = {"status": "error", "message": str(e)}
            total_count += 1

        # 确定整体状态
        if healthy_count == total_count:
            status = "healthy"
            message = "所有系统运行正常"
        elif healthy_count >= total_count - 1:  # 最多只有一个系统有问题
            status = "degraded"
            message = "部分系统存在警告"
        else:
            status = "unhealthy"
            message = "多个系统异常，需要关注"

        return {
            "status": status,
            "timestamp": time.time(),
            "checks": checks,
            "message": message,
        }

    def _add_alert(self, level: str, message: str, source: str):
        """添加告警"""
        # 生成告警类型标识（基于来源和消息内容的前半部分）
        alert_type = f"{source}_{message.split(':')[0]}"
        
        # 检查是否存在相同类型的告警
        for i, existing_alert in enumerate(self._alerts):
            existing_type = f"{existing_alert['source']}_{existing_alert['message'].split(':')[0]}"
            if existing_type == alert_type:
                # 替换为新的告警
                self._alerts[i] = {
                    "level": level,
                    "message": message,
                    "timestamp": time.time(),
                    "source": source,
                }
                return
        
        # 如果不存在相同类型的告警，添加新告警
        alert = {
            "level": level,
            "message": message,
            "timestamp": time.time(),
            "source": source,
        }
        self._alerts.append(alert)

        # 限制告警数量
        if len(self._alerts) > self._max_alerts:
            self._alerts = self._alerts[-self._max_alerts:]

    def get_recent_alerts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近告警"""
        # 定义告警级别优先级
        level_priority = {
            "critical": 4,
            "error": 3,
            "warning": 2,
            "info": 1
        }
        
        # 先按级别优先级排序，再按时间戳排序
        return sorted(
            self._alerts,
            key=lambda x: (level_priority.get(x["level"], 0), x["timestamp"]),
            reverse=True
        )[:limit]

    def clear_alerts(self):
        """清空告警"""
        self._alerts = []

    def _read_logs_reverse(self, file_path: str, max_logs: int, level_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        反向读取日志文件，从文件末尾开始读取
        
        Args:
            file_path: 日志文件路径
            max_logs: 最大日志数量
            level_filter: 日志级别过滤
            
        Returns:
            日志列表
        """
        import os
        from datetime import datetime
        import re
        
        logs = []
        CHUNK_SIZE = 64 * 1024
        
        # 优化：支持日志轮转，获取所有相关日志文件
        log_files = self._get_log_files(file_path)
        
        for log_file in log_files:
            if len(logs) >= max_logs:
                break
            
            try:
                file_size = os.path.getsize(log_file)
                if file_size == 0:
                    continue
                
                # 优化：增量读取，从上次读取的位置开始
                last_position = self._log_file_position.get(log_file, file_size)
                start_position = min(last_position, file_size)
                
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    position = start_position
                    buffer = ""
                    lines_buffer = []
                    
                    while position > 0 and len(logs) < max_logs:
                        read_size = min(CHUNK_SIZE, position)
                        position -= read_size
                        f.seek(position)
                        chunk = f.read(read_size)
                        
                        buffer = chunk + buffer
                        
                        lines = buffer.split('\n')
                        
                        if position > 0:
                            buffer = lines[0]
                            lines_to_process = lines[1:]
                        else:
                            lines_to_process = lines
                        
                        for line in reversed(lines_to_process):
                            if not line.strip():
                                continue
                            lines_buffer.append(line)
                            
                            if len(lines_buffer) >= 100:
                                self._parse_log_lines(lines_buffer, logs, max_logs, level_filter, datetime)
                                lines_buffer = []
                                
                                if len(logs) >= max_logs:
                                    break
                    
                    if lines_buffer and len(logs) < max_logs:
                        self._parse_log_lines(lines_buffer, logs, max_logs, level_filter, datetime)
                    
                    # 更新文件读取位置
                    self._log_file_position[log_file] = file_size
                    
            except Exception as e:
                logger.error(f"反向读取日志文件失败: {e}")
        
        return logs
    
    def _get_log_files(self, base_file: str) -> List[str]:
        """
        获取所有相关的日志文件（支持日志轮转）
        
        Args:
            base_file: 基础日志文件路径
            
        Returns:
            日志文件列表，按时间从新到旧排序
        """
        import os
        import glob
        
        log_files = []
        base_dir = os.path.dirname(base_file)
        base_name = os.path.basename(base_file)
        
        # 查找所有相关的日志文件
        pattern = os.path.join(base_dir, f"{base_name}*")
        all_files = glob.glob(pattern)
        
        # 按修改时间从新到旧排序
        all_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        return all_files
    
    def _parse_log_lines(self, lines: List[str], logs: List[Dict], max_logs: int, 
                         level_filter: Optional[str], datetime) -> None:
        """
        解析日志行并添加到日志列表
        
        Args:
            lines: 日志行列表
            logs: 日志结果列表
            max_logs: 最大日志数量
            level_filter: 日志级别过滤
            datetime: datetime 模块
        """
        from collections import OrderedDict
        
        log_entries = OrderedDict()
        current_key = None
        
        for line in lines:
            # 优化：使用字符串方法替代正则表达式判断是否为日志开头
            if line and line[0].isdigit() and len(line) > 20:
                # 尝试提取时间戳部分
                timestamp_part = line[:23]
                try:
                    # 验证时间戳格式
                    datetime.strptime(timestamp_part, '%Y-%m-%d %H:%M:%S,%f')
                    # 是日志开头
                    current_key = line
                    log_entries[current_key] = line
                except ValueError:
                    # 不是日志开头，作为多行日志的一部分
                    if current_key and line.strip():
                        log_entries[current_key] += '\n' + line
            elif current_key and line.strip():
                # 不是日志开头，作为多行日志的一部分
                log_entries[current_key] += '\n' + line
        
        for full_log_entry in reversed(list(log_entries.values())):
            if len(logs) >= max_logs:
                break
                
            # 优化：使用字符串方法解析日志
            try:
                # 提取时间戳
                timestamp_str = full_log_entry[:23]
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f').timestamp()
                
                # 提取模块、函数、行号和日志级别
                # 格式：2026-04-15 10:59:43,123 - module - function:line - LEVEL - message
                parts = full_log_entry[24:].split(' - ')
                if len(parts) >= 4:
                    module = parts[0].strip()
                    # 提取函数:行号部分
                    function_line = parts[1].strip()
                    log_level_str = parts[2].strip()
                    message = ' - '.join(parts[3:]).strip()
                    # 将函数名和行号添加到模块字段
                    module_with_location = f"{module} - {function_line}"
                elif len(parts) >= 3:
                    # 兼容旧格式：2026-04-15 10:59:43,123 - module - LEVEL - message
                    module = parts[0].strip()
                    log_level_str = parts[1].strip()
                    message = ' - '.join(parts[2:]).strip()
                    module_with_location = module
                else:
                    continue
                
                module = module.replace('.log', '')
                module_with_location = module_with_location.replace('.log', '')
                log_level_str = log_level_str.lower()
                
                if level_filter and log_level_str != level_filter:
                    continue
                
                logs.append({
                    "level": log_level_str,
                    "message": message,
                    "timestamp": timestamp,
                    "module": module_with_location,
                    "traceback": None
                })
            except Exception:
                continue

    def get_recent_logs(self, limit: int = 50, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取最近的日志（使用反向读取优化）

        Args:
            limit: 返回日志数量限制
            level: 日志级别过滤 (warning, error)

        Returns:
            日志列表
        """
        import os
        
        # 生成缓存键
        cache_key = f"logs_{limit}_{level}"
        
        # 尝试从缓存获取
        if cache_key in self._log_cache:
            logs, timestamp = self._log_cache[cache_key]
            if time.time() - timestamp < self._log_cache_expiry:
                return logs

        # 缓存过期，重新读取
        logs = []
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
        log_dir = os.path.join(project_root, "logs")

        log_file = os.path.join(log_dir, "app.log")

        if os.path.exists(log_file):
            logs = self._read_logs_reverse(log_file, limit, level)

        logs.sort(key=lambda x: x["timestamp"], reverse=True)
        result = logs[:limit]
        
        # 设置缓存
        self._log_cache[cache_key] = (result, time.time())

        return result

    async def register_websocket(self, websocket: WebSocket):
        """注册 WebSocket 连接"""
        await websocket.accept()
        self._websocket_connections.add(websocket)
        logger.info(f"新的 WebSocket 连接已注册，当前连接数: {len(self._websocket_connections)}")
        
        # 如果广播任务未启动，启动它
        if not self._broadcast_running:
            await self.start_broadcast()

    def unregister_websocket(self, websocket: WebSocket):
        """注销 WebSocket 连接"""
        if websocket in self._websocket_connections:
            self._websocket_connections.remove(websocket)
            logger.info(f"WebSocket 连接已注销，当前连接数: {len(self._websocket_connections)}")
            
            # 如果没有连接了，停止广播任务
            if len(self._websocket_connections) == 0 and self._broadcast_running:
                self.stop_broadcast()

    async def broadcast_data(self, data: Dict[str, Any]):
        """广播数据到所有 WebSocket 连接"""
        disconnected = []
        for connection in self._websocket_connections:
            try:
                await connection.send_json(data)
            except Exception as e:
                logger.error(f"发送数据到 WebSocket 失败: {e}")
                disconnected.append(connection)
        
        # 移除断开的连接
        for connection in disconnected:
            self.unregister_websocket(connection)

    async def start_broadcast(self):
        """启动广播任务"""
        if self._broadcast_running:
            return
        
        self._broadcast_running = True
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        logger.info("WebSocket 广播任务已启动")

    def stop_broadcast(self):
        """停止广播任务"""
        if not self._broadcast_running:
            return
        
        self._broadcast_running = False
        if self._broadcast_task:
            self._broadcast_task.cancel()
            self._broadcast_task = None
        logger.info("WebSocket 广播任务已停止")

    async def _broadcast_loop(self):
        """广播循环，定期发送监控数据"""
        try:
            while self._broadcast_running:
                # 收集监控数据
                try:
                    overview = await self.get_overview()
                    
                    # 收集日志数据
                    logs = self.get_recent_logs(limit=100)
                    
                    # 收集 API 请求数据
                    api_requests = self.http_collector.get_metrics()
                    
                    # 收集发送请求数据
                    outbound_requests = self.get_outbound_http_metrics()
                    
                    data = {
                        "type": "monitor_data",
                        "data": {
                            **overview,
                            "logs": logs,
                            "api_requests": api_requests,
                            "outbound_requests": outbound_requests
                        }
                    }
                    # 广播数据
                    await self.broadcast_data(data)
                except Exception as e:
                    logger.error(f"广播数据收集失败: {e}")
                
                # 等待一段时间后再次广播
                await asyncio.sleep(1)  # 每秒广播一次
        except asyncio.CancelledError:
            logger.info("广播循环已取消")
        except Exception as e:
            logger.error(f"广播循环异常: {e}")
        finally:
            self._broadcast_running = False


# 全局监控服务实例
monitor_service = MonitorService()
