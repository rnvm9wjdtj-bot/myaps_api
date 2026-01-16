import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, TypeVar, Generic
from dataclasses import dataclass, asdict, field, is_dataclass
import logging
from datetime import datetime
from contextlib import contextmanager
import threading
from enum import Enum
import hashlib

T = TypeVar('T')

class JSONManager:
    """基础的JSON文件管理器"""
    
    def __init__(self, 
                 filepath: Union[str, Path], 
                 auto_save: bool = True,
                 indent: int = 2,
                 encoding: str = 'utf-8'):
        """
        初始化JSON管理器
        
        Args:
            filepath: JSON文件路径
            auto_save: 是否自动保存（每次修改后）
            indent: JSON缩进
            encoding: 文件编码
        """
        self.filepath = Path(filepath)
        self.auto_save = auto_save
        self.indent = indent
        self.encoding = encoding
        self._data: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._modified = False
        
        # 自动创建目录
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载现有数据
        self._load()
    
    def _load(self) -> None:
        """从文件加载数据"""
        if not self.filepath.exists():
            self._data = {}
            return
        
        try:
            with self.filepath.open('r', encoding=self.encoding) as f:
                self._data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logging.warning(f"无法加载 {self.filepath}，使用空数据")
            self._data = {}
    
    def _save(self) -> None:
        """保存数据到文件"""
        with self._lock:
            try:
                # 创建临时文件
                temp_path = self.filepath.with_suffix('.tmp')
                with temp_path.open('w', encoding=self.encoding) as f:
                    json.dump(self._data, f, 
                             indent=self.indent, 
                             ensure_ascii=False)
                
                # 原子替换
                temp_path.replace(self.filepath)
                self._modified = False
                
            except Exception as e:
                logging.error(f"保存失败: {e}")
                raise
    
    def get(self, 
            key: str, 
            default: Any = None, 
            *subkeys: str) -> Any:
        """
        获取值
        
        Args:
            key: 主键
            default: 默认值
            *subkeys: 子键（支持嵌套）
            
        Returns:
            对应的值或默认值
        """
        with self._lock:
            if key not in self._data:
                return default
            
            value = self._data[key]
            
            # 支持嵌套获取
            for subkey in subkeys:
                if isinstance(value, dict) and subkey in value:
                    value = value[subkey]
                else:
                    return default
            
            return value
    
    def set(self, 
            key: str, 
            value: Any, 
            *subkeys: str,
            save: Optional[bool] = None) -> None:
        """
        设置值
        
        Args:
            key: 主键
            value: 值
            *subkeys: 子键（支持嵌套设置）
            save: 是否保存（None使用auto_save设置）
        """
        with self._lock:
            if subkeys:
                # 嵌套设置
                if key not in self._data or not isinstance(self._data[key], dict):
                    self._data[key] = {}
                
                current = self._data[key]
                for i, subkey in enumerate(subkeys[:-1]):
                    if subkey not in current or not isinstance(current[subkey], dict):
                        current[subkey] = {}
                    current = current[subkey]
                
                current[subkeys[-1]] = value
            else:
                # 直接设置
                self._data[key] = value
            
            self._modified = True
            
            # 自动保存
            save = self.auto_save if save is None else save
            if save:
                self._save()
    
    def delete(self, 
               key: str, 
               *subkeys: str,
               save: Optional[bool] = None) -> bool:
        """
        删除键
        
        Args:
            key: 主键
            *subkeys: 子键
            save: 是否保存
            
        Returns:
            是否成功删除
        """
        with self._lock:
            if key not in self._data:
                return False
            
            if not subkeys:
                # 删除整个键
                del self._data[key]
                deleted = True
            else:
                # 删除嵌套键
                current = self._data[key]
                for i, subkey in enumerate(subkeys[:-1]):
                    if not isinstance(current, dict) or subkey not in current:
                        return False
                    current = current[subkey]
                
                if isinstance(current, dict) and subkeys[-1] in current:
                    del current[subkeys[-1]]
                    deleted = True
                else:
                    deleted = False
            
            if deleted:
                self._modified = True
                save = self.auto_save if save is None else save
                if save:
                    self._save()
            
            return deleted
    
    def update(self, 
               key: str, 
               updates: Dict[str, Any], 
               *subkeys: str,
               save: Optional[bool] = None) -> None:
        """
        更新字典（合并）
        
        Args:
            key: 主键
            updates: 要更新的字典
            *subkeys: 子键
            save: 是否保存
        """
        with self._lock:
            if not subkeys:
                if key not in self._data or not isinstance(self._data[key], dict):
                    self._data[key] = {}
                self._data[key].update(updates)
            else:
                # 获取目标字典
                if key not in self._data:
                    self._data[key] = {}
                
                current = self._data[key]
                for subkey in subkeys[:-1]:
                    if subkey not in current or not isinstance(current[subkey], dict):
                        current[subkey] = {}
                    current = current[subkey]
                
                if subkeys[-1] not in current or not isinstance(current[subkeys[-1]], dict):
                    current[subkeys[-1]] = {}
                
                current[subkeys[-1]].update(updates)
            
            self._modified = True
            save = self.auto_save if save is None else save
            if save:
                self._save()
    
    def append(self, 
               key: str, 
               value: Any, 
               *subkeys: str,
               save: Optional[bool] = None) -> None:
        """
        向列表追加值
        
        Args:
            key: 主键
            value: 要追加的值
            *subkeys: 子键
            save: 是否保存
        """
        with self._lock:
            if not subkeys:
                if key not in self._data or not isinstance(self._data[key], list):
                    self._data[key] = []
                self._data[key].append(value)
            else:
                # 获取目标列表
                if key not in self._data:
                    self._data[key] = {}
                
                current = self._data[key]
                for subkey in subkeys[:-1]:
                    if subkey not in current or not isinstance(current[subkey], dict):
                        current[subkey] = {}
                    current = current[subkey]
                
                if subkeys[-1] not in current or not isinstance(current[subkeys[-1]], list):
                    current[subkeys[-1]] = []
                
                current[subkeys[-1]].append(value)
            
            self._modified = True
            save = self.auto_save if save is None else save
            if save:
                self._save()
    
    def exists(self, key: str, *subkeys: str) -> bool:
        """检查键是否存在"""
        with self._lock:
            if key not in self._data:
                return False
            
            if not subkeys:
                return True
            
            current = self._data[key]
            for subkey in subkeys:
                if not isinstance(current, dict) or subkey not in current:
                    return False
                current = current[subkey]
            
            return True
    
    def keys(self) -> List[str]:
        """获取所有键"""
        with self._lock:
            return list(self._data.keys())
    
    def clear(self, save: bool = True) -> None:
        """清空所有数据"""
        with self._lock:
            self._data.clear()
            self._modified = True
            if save:
                self._save()
    
    def save(self) -> None:
        """手动保存"""
        if self._modified:
            self._save()
    
    def reload(self) -> None:
        """重新加载文件"""
        with self._lock:
            self._load()
    
    @property
    def data(self) -> Dict[str, Any]:
        """获取完整数据（只读副本）"""
        with self._lock:
            return self._data.copy()
    
    def count(self) -> int:
        """获取键的数量"""
        with self._lock:
            return len(self._data)
    
    def backup(self, backup_dir: Union[str, Path] = "backups") -> Path:
        """
        创建备份
        
        Args:
            backup_dir: 备份目录
            
        Returns:
            备份文件路径
        """
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{self.filepath.stem}_{timestamp}.json"
        
        with self._lock:
            with backup_path.open('w', encoding=self.encoding) as f:
                json.dump(self._data, f, indent=self.indent, ensure_ascii=False)
        
        return backup_path



if __name__ == "__main__":
    # 使用示例
    # 初始化
    db = JSONManager("cache/config.json")

    # 增
    db.set("user", {"name": "张三", "age": 25})
    db.set("settings", {"theme": "dark", "language": "zh"})

    # 嵌套设置
    db.set("app", "v1.0", "version")
    db.set("app", True, "auto_update")

    # 改
    db.update("user", {"age": 26, "city": "北京"})
    db.set("user", "李四", "name")  # 修改名字

    # 查
    name = db.get("user", "name")  # 获取嵌套值
    age = db.get("user", "age")
    version = db.get("app", "version")

    # 删
    db.delete("user", "city")  # 删除嵌套字段
    db.delete("settings")  # 删除整个键

    # 列表操作
    db.append("logs", "用户登录")
    db.append("logs", "用户操作")

    # 保存
    db.save()