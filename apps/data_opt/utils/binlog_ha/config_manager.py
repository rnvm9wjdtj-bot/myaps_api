"""
Binlog 监听器 - 配置热更新管理器

提供配置热更新、验证、审计日志功能
"""
import os
import json
import time
import uuid
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone
from pathlib import Path

from .models import BinlogConfig, AuditAction, AuditEntry
from globalobjects import logger


class ConfigManager:
    """配置热更新管理器"""
    
    HOT_RELOADABLE_KEYS: Set[str] = {
        "max_retry_attempts",
        "base_retry_delay_seconds",
        "max_retry_delay_seconds",
        "heartbeat_interval_seconds",
        "heartbeat_timeout_seconds",
        "backpressure_warning_threshold",
        "backpressure_limit_threshold",
        "backpressure_pause_seconds",
        "backpressure_check_interval",
        "dedup_ttl_hours",
    }
    
    RESTART_REQUIRED_KEYS: Set[str] = {
        "turnon_binlog_listener",
        "enable_binlog_position",
        "redis_host",
        "redis_port",
        "redis_password",
        "environment_mode",
    }
    
    def __init__(
        self,
        config_file: Optional[str] = None,
        audit_file: Optional[str] = None
    ):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径
            audit_file: 审计日志文件路径
        """
        self._config_file = config_file or "storage/binlog_ha_config.json"
        self._audit_file = audit_file or "storage/binlog_ha_audit.json"
        self._config: Optional[BinlogConfig] = None
        self._audit_log: List[AuditEntry] = []
        self._max_audit_entries = 1000
        
        self._load_config()
    
    def _load_config(self):
        """加载配置"""
        try:
            if os.path.exists(self._config_file):
                with open(self._config_file, 'r') as f:
                    data = json.load(f)
                self._config = BinlogConfig(**data)
                logger.info(f"✅ 配置已从文件加载: {self._config_file}")
            else:
                self._config = BinlogConfig()
                logger.info("✅ 使用默认配置")
                
        except Exception as e:
            logger.warning(f"⚠️ 配置加载失败: {e}，使用默认配置")
            self._config = BinlogConfig()
    
    def _load_audit_log(self):
        """加载审计日志"""
        try:
            if os.path.exists(self._audit_file):
                with open(self._audit_file, 'r') as f:
                    data = json.load(f)
                self._audit_log = [AuditEntry(**entry) for entry in data]
        except Exception as e:
            logger.warning(f"⚠️ 审计日志加载失败: {e}")
            self._audit_log = []
    
    def get_config(self) -> BinlogConfig:
        """获取当前配置"""
        if self._config is None:
            self._config = BinlogConfig()
        return self._config
    
    def validate_config(self, config_dict: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        验证配置合法性
        
        Args:
            config_dict: 配置字典
        
        Returns:
            (是否有效, 错误列表)
        """
        errors = []
        
        try:
            BinlogConfig(**config_dict)
        except Exception as e:
            errors.append(str(e))
        
        for key, value in config_dict.items():
            if key == "backpressure_limit_threshold":
                warning = config_dict.get("backpressure_warning_threshold", 1000)
                if value <= warning:
                    errors.append(f"限流阈值({value})必须大于告警阈值({warning})")
        
        return len(errors) == 0, errors
    
    def apply_config(
        self,
        new_config: Dict[str, Any],
        operator: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        应用新配置
        
        Args:
            new_config: 新配置字典
            operator: 操作者
            reason: 操作原因
        
        Returns:
            应用结果
        """
        audit_id = f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        is_valid, errors = self.validate_config(new_config)
        
        if not is_valid:
            self._add_audit_entry(AuditEntry(
                audit_id=audit_id,
                timestamp=datetime.now(timezone.utc),
                operator=operator,
                action=AuditAction.UPDATE_CONFIG,
                result="failure",
                reason=reason,
                error_message="; ".join(errors)
            ))
            
            return {
                "success": False,
                "errors": errors,
                "audit_id": audit_id
            }
        
        current_config = self.get_config()
        applied = {}
        requires_restart = []
        changes = []
        
        for key, new_value in new_config.items():
            if not hasattr(current_config, key):
                continue
            
            old_value = getattr(current_config, key)
            
            if old_value != new_value:
                is_hot_reloadable = key in self.HOT_RELOADABLE_KEYS
                is_restart_required = key in self.RESTART_REQUIRED_KEYS
                
                try:
                    setattr(current_config, key, new_value)
                    
                    applied[key] = {
                        "old": old_value,
                        "new": new_value,
                        "hot_reload": is_hot_reloadable
                    }
                    
                    changes.append({
                        "key": key,
                        "old": old_value,
                        "new": new_value
                    })
                    
                    if is_restart_required:
                        requires_restart.append(key)
                        
                except Exception as e:
                    errors.append(f"设置 {key} 失败: {e}")
        
        if changes:
            self._persist_config()
            
            self._add_audit_entry(AuditEntry(
                audit_id=audit_id,
                timestamp=datetime.now(timezone.utc),
                operator=operator,
                action=AuditAction.UPDATE_CONFIG,
                changes=changes,
                result="success",
                reason=reason
            ))
            
            logger.info(f"✅ 配置已更新: {len(applied)} 项")
        
        return {
            "success": True,
            "applied": applied,
            "requires_restart": requires_restart,
            "audit_id": audit_id,
            "errors": errors if errors else None
        }
    
    def _persist_config(self):
        """持久化配置到存储"""
        try:
            os.makedirs(os.path.dirname(self._config_file), exist_ok=True)
            
            with open(self._config_file, 'w') as f:
                json.dump(self._config.model_dump(), f, indent=2, default=str)
            
            logger.debug(f"✅ 配置已持久化: {self._config_file}")
            
        except Exception as e:
            logger.error(f"❌ 配置持久化失败: {e}")
    
    def _add_audit_entry(self, entry: AuditEntry):
        """添加审计日志条目"""
        self._audit_log.append(entry)
        
        if len(self._audit_log) > self._max_audit_entries:
            self._audit_log = self._audit_log[-self._max_audit_entries:]
        
        try:
            os.makedirs(os.path.dirname(self._audit_file), exist_ok=True)
            
            with open(self._audit_file, 'w') as f:
                json.dump(
                    [entry.model_dump() for entry in self._audit_log],
                    f,
                    indent=2,
                    default=str
                )
        except Exception as e:
            logger.warning(f"⚠️ 审计日志持久化失败: {e}")
    
    def get_audit_log(self, limit: int = 100) -> List[AuditEntry]:
        """
        获取审计日志
        
        Args:
            limit: 返回条数限制
        
        Returns:
            审计日志列表
        """
        return self._audit_log[-limit:]
    
    def get_hot_reloadable_keys(self) -> Set[str]:
        """获取热更新配置项"""
        return self.HOT_RELOADABLE_KEYS
    
    def get_restart_required_keys(self) -> Set[str]:
        """获取需重启配置项"""
        return self.RESTART_REQUIRED_KEYS


config_manager = ConfigManager()
