import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, TypeVar, Generic
import logging
from datetime import datetime
import threading


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
            default: Any = None) -> Any:
        """
        获取值
        
        Args:
            key: 键路径，使用 ' / ' 分隔表示嵌套层级（如 "user / name"）
            default: 默认值
            
        Returns:
            对应的值或默认值
        """
        with self._lock:
            # 分割键路径（支持 ' / ' 格式）
            keys = [k.strip() for k in key.split('/')]
            
            # 从根开始获取
            value = self._data
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            
            return value
    
    def set(self, 
            key: str, 
            value: Any, 
            save: Optional[bool] = None) -> None:
        """
        设置值
        
        Args:
            key: 键路径，使用 ' / ' 分隔表示嵌套层级（如 "user / name"）
            value: 值
            save: 是否保存（None使用auto_save设置）
        """
        with self._lock:
            # 分割键路径（支持 ' / ' 格式）
            keys = [k.strip() for k in key.split('/')]
            
            if len(keys) > 1:
                # 嵌套设置
                # 获取主键
                main_key = keys[0]
                
                if main_key not in self._data or not isinstance(self._data[main_key], dict):
                    self._data[main_key] = {}
                
                current = self._data[main_key]
                for subkey in keys[1:-1]:
                    if subkey not in current or not isinstance(current[subkey], dict):
                        current[subkey] = {}
                    current = current[subkey]
                
                current[keys[-1]] = value
            else:
                # 直接设置
                self._data[keys[0]] = value
            
            self._modified = True
            
            # 自动保存
            save = self.auto_save if save is None else save
            if save:
                self._save()
    
    def delete(self, 
               key: str, 
               save: Optional[bool] = None) -> bool:
        """
        删除键
        
        Args:
            key: 键路径，使用 ' / ' 分隔表示嵌套层级（如 "user / city"）
            save: 是否保存
            
        Returns:
            是否成功删除
        """
        with self._lock:
            # 分割键路径（支持 ' / ' 格式）
            keys = [k.strip() for k in key.split('/')]
            
            if len(keys) > 1:
                # 嵌套删除
                # 获取主键
                main_key = keys[0]
                
                if main_key not in self._data:
                    return False
                
                current = self._data[main_key]
                for subkey in keys[1:-1]:
                    if not isinstance(current, dict) or subkey not in current:
                        return False
                    current = current[subkey]
                
                last_key = keys[-1]
                if isinstance(current, dict) and last_key in current:
                    del current[last_key]
                    deleted = True
                else:
                    deleted = False
            else:
                # 直接删除
                main_key = keys[0]
                if main_key in self._data:
                    del self._data[main_key]
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
               save: Optional[bool] = None) -> None:
        """
        更新字典（合并）
        
        Args:
            key: 键路径，使用 ' / ' 分隔表示嵌套层级（如 "user / profile"）
            updates: 要更新的字典
            save: 是否保存
        """
        with self._lock:
            # 分割键路径（支持 ' / ' 格式）
            keys = [k.strip() for k in key.split('/')]
            
            if len(keys) > 1:
                # 嵌套更新
                # 获取主键
                main_key = keys[0]
                
                if main_key not in self._data:
                    self._data[main_key] = {}
                
                current = self._data[main_key]
                for subkey in keys[1:-1]:
                    if subkey not in current or not isinstance(current[subkey], dict):
                        current[subkey] = {}
                    current = current[subkey]
                
                last_key = keys[-1]
                if last_key not in current or not isinstance(current[last_key], dict):
                    current[last_key] = {}
                
                current[last_key].update(updates)
            else:
                # 直接更新
                main_key = keys[0]
                if main_key not in self._data or not isinstance(self._data[main_key], dict):
                    self._data[main_key] = {}
                self._data[main_key].update(updates)
            
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
    db.set("app / version", "v1.0")
    db.set("app / auto_update", True)

    # 改
    db.update("user", {"age": 26, "city": "北京"})
    db.set("user / name", "李四")  # 修改名字

    # 查
    name = db.get("user / name")  # 获取嵌套值
    age = db.get("user / age")
    version = db.get("app / version")

    # 删
    db.delete("user / city")  # 删除嵌套字段
    db.delete("settings")  # 删除整个键

    # 列表操作
    db.append("logs", "用户登录")
    db.append("logs", "用户操作")

    # 保存
    db.save()