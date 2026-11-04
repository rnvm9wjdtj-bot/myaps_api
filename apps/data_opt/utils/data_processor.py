from typing import List, Dict, Any#, Optional, Callable, Union
import enum
import hashlib

import pandas as pd, json

from globalobjects import globalconst as gc



class DataProcessor:
    # 哈希缓存，用于快速比较
    _hash_cache = {}
    _cache_max_size = 1000

    @staticmethod
    def _get_value_hash(val):
        """
        计算值的哈希值，用于快速比较
        
        Args:
            val: 任意类型的值
            
        Returns:
            str: 哈希字符串
        """
        # 处理 None
        if val is None:
            return "none"
        
        # 处理枚举值
        if isinstance(val, enum.Enum):
            val = val.value
        
        # 处理字典和列表（不可哈希类型）
        if isinstance(val, (dict, list)):
            try:
                # 使用 JSON 序列化后计算哈希
                val_str = json.dumps(val, sort_keys=True, ensure_ascii=False)
                return hashlib.md5(val_str.encode('utf-8')).hexdigest()
            except (TypeError, ValueError):
                # 如果 JSON 序列化失败，使用字符串表示
                return hashlib.md5(str(val).encode('utf-8')).hexdigest()
        
        # 处理字符串
        if isinstance(val, str):
            # 尝试解析 JSON 字符串
            try:
                parsed = json.loads(val)
                if isinstance(parsed, (dict, list)):
                    return DataProcessor._get_value_hash(parsed)
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
            return hashlib.md5(val.encode('utf-8')).hexdigest()
        
        # 处理数值和布尔值
        return hashlib.md5(str(val).encode('utf-8')).hexdigest()

    @staticmethod
    def is_equal(val1, val2, fast: bool = True):
        """
        判断两个值是否相等，处理不同类型之间的比较
        
        Args:
            val1: 第一个值
            val2: 第二个值
            fast: 是否使用哈希值快速比较，默认为 True
            
        Returns:
            bool: 两个值是否相等
        """
        # 快速模式：使用哈希值比较
        if fast:
            hash1 = DataProcessor._get_value_hash(val1)
            hash2 = DataProcessor._get_value_hash(val2)
            return hash1 == hash2
        
        # 精确模式：深度比较
        # 处理 None 值情况
        if val1 is None and val2 is None:
            return True
        if val1 is None or val2 is None:
            return False
        
        # 处理枚举值对象，转换为字符串
        def handle_enum(val):
            if isinstance(val, enum.Enum):
                return val.value
            return val
        
        # 处理枚举值
        enum_val1 = handle_enum(val1)
        enum_val2 = handle_enum(val2)
        
        # 如果处理后值不同，使用处理后的值重新比较
        if enum_val1 is not val1 or enum_val2 is not val2:
            return DataProcessor.is_equal(enum_val1, enum_val2, fast=False)
        
        # 处理 JSON 字符串与字典/列表的比较
        def try_parse_json(s):
            if isinstance(s, str):
                try:
                    return json.loads(s)
                except (json.JSONDecodeError, ValueError, TypeError):
                    return s
            return s
        
        # 尝试解析 JSON 字符串
        parsed_val1 = try_parse_json(val1)
        parsed_val2 = try_parse_json(val2)
        
        # 如果解析后类型不同，使用解析后的值重新比较
        if parsed_val1 is not val1 or parsed_val2 is not val2:
            return DataProcessor.is_equal(parsed_val1, parsed_val2, fast=False)
        
        # 处理列表与逗号分隔字符串的比较
        if isinstance(val1, list) and isinstance(val2, str):
            val1_str = ','.join(str(item) for item in val1)
            return val1_str == val2
        if isinstance(val1, str) and isinstance(val2, list):
            val2_str = ','.join(str(item) for item in val2)
            return val1 == val2_str
        
        # 处理数值字符串的比较
        def is_numeric(s):
            if isinstance(s, str):
                try:
                    float(s)
                    return True
                except (ValueError, TypeError):
                    return False
            return False
        
        if isinstance(val1, str) and isinstance(val2, str):
            if is_numeric(val1) and is_numeric(val2):
                try:
                    return float(val1) == float(val2)
                except (ValueError, TypeError):
                    pass
        
        # 处理数字与字符串的比较
        if isinstance(val1, (int, float)) and isinstance(val2, str):
            try:
                return val1 == type(val1)(val2)
            except (ValueError, TypeError):
                return False
        if isinstance(val1, str) and isinstance(val2, (int, float)):
            try:
                return type(val2)(val1) == val2
            except (ValueError, TypeError):
                return False
        
        # 处理布尔值与其他类型的比较
        if isinstance(val1, bool) != isinstance(val2, bool):
            return False
        
        # 其他情况直接比较
        return val1 == val2

    
    @staticmethod
    def merge_paged_data(paged_data_iter):
        """
        合并分页数据
        """
        row_count = 0
        merged_data = []
        for page in paged_data_iter:
            row_count += len(page)
            merged_data.extend(page)
        return merged_data


    @staticmethod
    def join_parent_child_data(parent_data: List[Dict], child_data: List[Dict], 
                                    parent_key_fields: str | list[str] = 'id', 
                                    child_match_key_fields: str | list[str] = 'parentid') -> List[Dict]:
        """
        合并父表和子表数据为扁平结构
        """
        union_key_col = '$index'
        # 转换为DataFrame
        df_parent = pd.DataFrame(parent_data)
        df_child = pd.DataFrame(child_data)

        parent_key_fields = parent_key_fields if isinstance(parent_key_fields, list) else [parent_key_fields]
        child_match_key_fields = child_match_key_fields if isinstance(child_match_key_fields, list) else [child_match_key_fields]

        df_parent[union_key_col] = df_parent[parent_key_fields].apply(lambda x: tuple(x), axis=1)
        df_child[union_key_col] = df_child[child_match_key_fields].apply(lambda x: tuple(x), axis=1)
        
        # 处理单字段情况
        if isinstance(parent_key_fields, str):
            parent_key_fields = [parent_key_fields]
        if isinstance(child_match_key_fields, str):
            child_match_key_fields = [child_match_key_fields]
        
        # 合并数据
        merged_df = pd.merge(
            df_parent,
            df_child,
            left_on=union_key_col,
            right_on=union_key_col,
            how='left',
            suffixes=('_parent', '_child')
        )
        
        return merged_df.to_dict(orient='records')


    @staticmethod
    def extract_nested_value(data: dict, path: str):
        """
        在多层嵌套字典中按路径提取值。
        路径格式示例：
            "RoutingDetails / Process / Code"
            "Code"
            "VoucherState / Name"
        参数:
            data: 原始字典
            path: 以“(空格)/(空格)”分隔的字段路径
        返回:
            提取到的值；若路径不存在则返回None
        """
        if not isinstance(data, dict):
            return None
        keys = [k.strip() for k in path.split("/")]
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list) and key.isdigit():
                # 支持列表索引，如 RoutingDetails/0/Process/Code
                idx = int(key)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                return None
        return current

    
    @staticmethod
    def flatten_dict(d: dict, parent_key: str = '', sep: str = ' / ') -> dict:
        """
        递归展平嵌套字典，将所有键路径合并为单级键。
        参数:
            d: 输入字典
            parent_key: 父键前缀，用于递归调用
            sep: 键路径分隔符
        返回:
            展平后的字典
        """
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(DataProcessor.flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)


    @staticmethod
    def expand_parent_child_data(data: Dict, expand_key: str, sep: str = ' / ') -> List[Dict]:
        """
        展开父表和子表数据为扁平结构
        将字典中包含的特定列表进行展开
        例如: {'a':1,'b':2,'c':[{'d':4},{'e':5}]}，若按'c'列表展开，则得到[{'a':1,'b':2,'c / d':4},{'a':1,'b':2,'c / e':5}]
        例如: {'a':{'x': 8,'y':9},'b':2,'c':[{'d':4},{'e':5}]}，若按'c'列表展开，则得到[{'a / x':8, 'a / y':9,'b':2,'c / d':4},{'a / x':8, 'a / y':9,'b':2,'c / e':5}]
        
        参数:
            data: 输入字典
            expand_key: 要展开的列表键名
        返回:
            展开后的字典列表
        """
        result = []
        # 获取要展开的列表
        expand_list = data.get(expand_key, [])
        
        # 遍历列表中的每个元素
        for item in expand_list:
            # 创建新字典，包含原始字典中除了expand_key以外的所有键值对，并展平其中的字典
            new_dict = {}
            for k, v in data.items():
                if k == expand_key:
                    continue
                if isinstance(v, dict):
                    flattened_parent = DataProcessor.flatten_dict(v, parent_key=k, sep=sep)
                    new_dict.update(flattened_parent)
                else:
                    new_dict[k] = v
            
            # 展平当前列表项，并将键与expand_key用'/'连接
            if isinstance(item, dict):
                flattened_item = DataProcessor.flatten_dict(item, parent_key=expand_key, sep=sep)
                new_dict.update(flattened_item)
            else:
                # 如果列表项不是字典，直接赋值
                new_dict[expand_key] = item
            
            result.append(new_dict)
        
        return result


    @staticmethod
    def aes_decrypt(encrypted_str: str, key: str) -> str:
        """
        AES/ECB/PKCS5Padding解密
        Args:
            encrypted_str: Base64编码的加密字符串
            key: 密钥（16/24/32字节对应AES-128/192/256）
        Returns:
            解密后的原始字符串
        """
        import base64
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad

        # Base64解码
        encrypted_bytes = base64.b64decode(encrypted_str)
        
        # 确保密钥长度符合AES要求（16, 24, 32字节）
        # 如果密钥长度不够，可以用特定方式填充（这里用null字节填充到最近的有效长度）
        key_bytes = key.encode('utf-8')
        if len(key_bytes) not in [16, 24, 32]:
            # 将密钥调整到最接近的有效长度
            valid_lengths = [16, 24, 32]
            target_length = min(valid_lengths, key=lambda x: abs(x - len(key_bytes)))
            # 用null字节填充到目标长度
            key_bytes = key_bytes.ljust(target_length, b'\0')
        # 创建AES解密器（ECB模式）
        cipher = AES.new(key_bytes, AES.MODE_ECB)
        # 解密
        decrypted_bytes = cipher.decrypt(encrypted_bytes)
        # 去除PKCS5/PKCS7填充
        decrypted_bytes = unpad(decrypted_bytes, AES.block_size)
        # 返回UTF-8字符串
        return json.loads(decrypted_bytes.decode('utf-8'))

 
    # @staticmethod
    # def generate_hierarchy_dict(origin_data: Dict[str, Any], field_map: Dict[str, str], separator: str = " / ", static_values: dict = None) -> Dict[str, Any]:
    #     """
    #     根据字段映射关系，将扁平的原始数据字典转换为具有层次结构的嵌套字典
    #     支持处理原始数据中的列表类型字段，生成对应的列表形式层次结构
        
    #     Args:
    #         origin_data: 原始数据字典，包含需要转换的键值对
    #         field_map: 字段映射字典，键是目标层次路径，值是原始数据中的键
    #                   支持显式类型声明：{"[]": "A,B,C", "{}": "D,E,F", ...正常映射关系...}
    #                   "[]" 表示列表类型，"{}" 表示字典类型
    #                   支持表达式：如 "x + y", "(x * y) / z"
    #                   支持 $ 开头的变量：如 "$x + 1"，会从 static_values 中查找
    #         separator: 层次路径的分隔符，默认为 " / "
    #         static_values: 静态值字典，当 field_map 中出现 $ 开头的变量时，优先从这里查找
        
    #     Returns:
    #         具有层次结构的嵌套字典
        
    #     Raises:
    #         ValueError: 当field_map中的路径为空或无效时
    #     """
    #     # 解析显式类型声明
    #     explicit_list_types = set()
    #     explicit_dict_types = set()
        
    #     # 从field_map中提取显式类型声明
    #     processed_field_map = {}
    #     for key, value in field_map.items():
    #         if key == "[]":
    #             # 解析列表类型声明
    #             explicit_list_types = set([item.strip() for item in value.split(",") if item.strip()])
    #         elif key == "{}":
    #             # 解析字典类型声明
    #             explicit_dict_types = set([item.strip() for item in value.split(",") if item.strip()])
    #         else:
    #             # 保留正常映射关系
    #             processed_field_map[key] = value
        
    #     # 使用处理后的field_map
    #     field_map = processed_field_map
    #     result = {}
        
    #     # 辅助函数：分割路径并清理空白字符
    #     def _split_path(path):
    #         return [p.strip() for p in path.split(separator) if p.strip()]
        
    #     # 辅助函数：构建父路径结构
    #     def _build_parent_structure(parent_parts):
    #         current = result
    #         for part in parent_parts:
    #             if part not in current:
    #                 current[part] = {}
    #             current = current[part]
    #         return current
        
    #     # 分析字段映射，识别可能需要作为列表的字段
    #     # 统计每个路径段的出现次数和子路径模式
    #     path_analysis = {}
        
    #     for value_path, key in field_map.items():
    #         parts = _split_path(value_path)
    #         if not parts:
    #             continue
            
    #         # 分析路径的每个级别
    #         for i, part in enumerate(parts):
    #             if part not in path_analysis:
    #                 path_analysis[part] = {
    #                     "occurrences": 0,
    #                     "parent_paths": set(),
    #                     "child_patterns": set(),
    #                     "full_paths": set()
    #                 }
                
    #             path_analysis[part]["occurrences"] += 1
                
    #             # 记录父路径
    #             if i > 0:
    #                 parent_path = separator.join(parts[:i])
    #                 path_analysis[part]["parent_paths"].add(parent_path)
                
    #             # 记录子路径模式
    #             if i < len(parts) - 1:
    #                 child_pattern = parts[i+1]
    #                 path_analysis[part]["child_patterns"].add(child_pattern)
                
    #             # 记录完整路径
    #             path_analysis[part]["full_paths"].add(value_path)
        
    #     # 识别需要作为列表的字段
    #     # 规则：
    #     # 1. 如果多个不同的完整路径都包含同一个父路径段，并且这些路径的下一级路径段不同，那么该父路径段应该是列表
    #     # 例如：ManufactureOrderDetails / Inventory / Code 和 ManufactureOrderDetails / Unit / Name
    #     # 2. 结合启发式规则，考虑字段名称语义、路径结构和原始数据类型
    #     list_candidates = set()
    #     dict_candidates = set()
        
    #     # 启发式规则：字段名称语义分析
    #     def is_list_name(name):
    #         """根据字段名称判断是否可能是列表"""
    #         list_indicators = [
    #             'list', 'items', 'details', 'records', 'rows', 'entries',
    #             'orders', 'products', 'materials', 'components', 'parts',
    #             'processes', 'steps', 'tasks', 'lines', 'set'
    #         ]
    #         name_lower = name.lower()
    #         return any(indicator in name_lower for indicator in list_indicators)
        
    #     def is_dict_name(name):
    #         """根据字段名称判断是否可能是字典"""
    #         dict_indicators = [
    #             'info', 'data', 'detail', 'record', 'item', 'entry',
    #             'order', 'product', 'material', 'component', 'part',
    #             'process', 'step', 'task', 'line', 'item',
    #             'busi', 'busitype', 'department', 'inventory', 'unit',
    #             'workcenter', 'itemno', 'sortno', 'code', 'name',
    #             'person', 'user', 'customer', 'client', 'supplier',
    #             'vendor', 'company', 'organization', 'org', 'address',
    #             'contact', 'phone', 'email', 'gender', 'age'
    #         ]
    #         name_lower = name.lower()
    #         return any(indicator in name_lower for indicator in dict_indicators)
        
    #     # 首先，收集所有可能的父路径段
    #     parent_segments = {}
    #     for value_path, key in field_map.items():
    #         parts = _split_path(value_path)
    #         if len(parts) >= 2:
    #             # 对于每个路径，检查其所有可能的父路径段
    #             for i in range(1, len(parts)):
    #                 parent_segment = parts[i-1]
    #                 child_segment = parts[i]
                    
    #                 if parent_segment not in parent_segments:
    #                     parent_segments[parent_segment] = set()
                    
    #                 # 记录该父路径段的所有子路径段
    #                 parent_segments[parent_segment].add(child_segment)
        
    #     # 然后，检查每个父路径段是否有多个不同的子路径段
    #     for parent_segment, child_segments in parent_segments.items():
    #         # 如果一个父路径段有多个不同的子路径段
    #         if len(child_segments) > 1:
    #             # 启发式规则 1：考虑字段名称语义
    #             if is_list_name(parent_segment):
    #                 # 如果字段名称暗示是列表，添加到列表候选
    #                 list_candidates.add(parent_segment)
    #             elif is_dict_name(parent_segment):
    #                 # 如果字段名称暗示是字典，添加到字典候选
    #                 dict_candidates.add(parent_segment)
    #             else:
    #                 # 默认规则：有多个不同的子路径段，视为列表
    #                 list_candidates.add(parent_segment)
        
    #     # 特殊处理：如果一个字段在多个完整路径中出现，并且这些路径的深度相同，那么它可能是列表
    #     for part, analysis in path_analysis.items():
    #         # 检查该字段是否在多个完整路径中出现
    #         if len(analysis["full_paths"]) > 1:
    #             # 检查这些路径的深度是否相同
    #             depths = set()
    #             for full_path in analysis["full_paths"]:
    #                 depths.add(len(_split_path(full_path)))
                
    #             # 如果所有路径的深度相同
    #             if len(depths) == 1:
    #                 # 启发式规则 2：考虑字段名称语义
    #                 if is_list_name(part):
    #                     list_candidates.add(part)
    #                 elif is_dict_name(part):
    #                     dict_candidates.add(part)
        
    #     # 启发式规则 3：结合原始数据类型
    #     # 检查原始数据中对应字段的类型
    #     for part in parent_segments:
    #         # 查找原始数据中是否有对应字段
    #         for value_path, key in field_map.items():
    #             parts = _split_path(value_path)
    #             if part in parts:
    #                 # 检查原始数据中对应字段的类型
    #                 if key in origin_data:
    #                     original_value = origin_data.get(key)
    #                     if isinstance(original_value, list):
    #                         # 如果原始数据中对应字段是列表，添加到列表候选
    #                         list_candidates.add(part)
    #                     elif isinstance(original_value, dict):
    #                         # 如果原始数据中对应字段是字典，添加到字典候选
    #                         dict_candidates.add(part)
        
    #     # 启发式规则 4：路径结构分析
    #     # 分析路径的整体结构，区分层级扩展和元素扩展
    #     for value_path, key in field_map.items():
    #         parts = _split_path(value_path)
    #         if len(parts) >= 3:
    #             # 对于深度大于等于 3 的路径，分析其结构
    #             # 例如：A / B / C / D，检查 B 是否可能是列表
    #             for i in range(1, len(parts) - 1):
    #                 current_part = parts[i]
    #                 # 检查当前路径段的前后路径段
    #                 prev_part = parts[i-1]
    #                 next_part = parts[i+1]
                    
    #                 # 如果当前路径段有多个不同的子路径段，且前后路径段名称暗示层级关系
    #                 if current_part in parent_segments and len(parent_segments[current_part]) > 1:
    #                     # 检查前后路径段的名称
    #                     if is_dict_name(prev_part) and is_dict_name(next_part):
    #                         # 如果前后都是字典名称，当前可能是列表
    #                         list_candidates.add(current_part)
        
    #     # 最后，从列表候选中移除字典候选
    #     # 如果一个字段同时被识别为列表候选和字典候选，优先视为字典
    #     list_candidates = list_candidates - dict_candidates
        
    #     # 首先收集所有列表字段的映射
    #     list_field_mappings = {}
    #     regular_mappings = []
        
    #     for value_path, expr in field_map.items():
    #         # 检查目标路径是否包含分隔符，判断是否为列表字段映射
    #         # 列表字段映射的目标路径格式：[父路径 /] 列表字段名 [/ 目标字段 [/ 子字段]]
    #         # 例如：ManufactureOrderDetails / ManufactureOrderProcessDetails / Workcenter / Code
    #         parts = _split_path(value_path)
            
    #         # 检查是否是列表字段映射
    #         # 列表字段映射的目标路径格式：[父路径 /] 列表字段名 [/ 目标字段 [/ 子字段]]
    #         is_list_field_mapping = False
    #         list_key = None
    #         sub_key = None
    #         target_field_name = None
            
    #         # 检查目标路径是否包含列表字段
    #         if len(parts) >= 1:
    #             # 查找路径中第一个显式声明为列表的字段作为列表字段名
    #             for i, part in enumerate(parts):
    #                 if part in explicit_list_types:
    #                     target_field_name = part
    #                     is_list_field_mapping = True
                        
    #                     # 尝试从表达式中提取列表键和子键
    #                     if separator in expr:
    #                         list_key, sub_key = [k.strip() for k in expr.split(separator)]
    #                     else:
    #                         # 对于复杂表达式，尝试提取列表键
    #                         # 例如：(details / req_qty) × -1
    #                         import re
    #                         match = re.search(r'\(([^()]+)\)', expr)
    #                         if match:
    #                             inner_expr = match.group(1)
    #                             if separator in inner_expr:
    #                                 list_key, sub_key = [k.strip() for k in inner_expr.split(separator)]
    #                         # 如果还是无法提取，使用默认的列表键
    #                         if not list_key:
    #                             list_key = "details"
    #                             sub_key = ""
    #                     break
            
    #         if is_list_field_mapping and list_key:
    #             if list_key not in list_field_mappings:
    #                 list_field_mappings[list_key] = {}
                
    #             # 找到列表字段在路径中的位置
    #             list_field_index = -1
    #             for i, part in enumerate(parts):
    #                 if part == target_field_name:
    #                     list_field_index = i
    #                     break
                
    #             if list_field_index != -1:
    #                 # 构建父路径（列表字段之前的部分）
    #                 target_parent_parts = parts[:list_field_index]
                    
    #                 # 构建目标字段路径（列表字段之后的部分）
    #                 target_path_parts = parts[list_field_index + 1:]
                    
    #                 if not target_path_parts:
    #                     # 只有列表字段，没有子字段
    #                     target_field = target_field_name
    #                     target_subfield = None
    #                 elif len(target_path_parts) == 1:
    #                     # 列表字段后有一个字段
    #                     target_field = target_path_parts[0]
    #                     target_subfield = None
    #                 else:
    #                     # 列表字段后有多个字段，最后一个是子字段
    #                     target_field = target_path_parts[-2]
    #                     target_subfield = target_path_parts[-1]
                
    #             if target_field not in list_field_mappings[list_key]:
    #                 list_field_mappings[list_key][target_field] = {
    #                     "sub_key": sub_key,
    #                     "target_parent_parts": target_parent_parts,
    #                     "target_field_name": target_field_name,
    #                     "target_field": target_field,
    #                     "target_subfield": target_subfield,
    #                     "expr": expr  # 保存原始表达式
    #                 }
    #         else:
    #             # 处理常规字段，存储为 (expr, value_path, depth) 元组
    #             depth = len(parts)  # 路径深度，顶层为 1
    #             regular_mappings.append((expr, value_path, depth))
        
    #     # 按路径深度排序，深度小的（顶层）先处理
    #     regular_mappings.sort(key=lambda x: x[2])
        
    #     # 解析表达式并计算值
    #     def evaluate_expression(expr):
    #         # 确保 static_values 不为 None
    #         local_static_values = static_values if static_values is not None else {}
    #         """
    #         评估表达式，支持多种运算逻辑
    #         支持的运算符：
    #         +: 数值求和（不能转为数值的视为0）
    #         -: 值相减（不能转为数值的视为0）
    #         ×: 乘法（不能转为数值的视为1）
    #         ÷: 除法（不能转为数值的视为1）
    #         @: 字符串拼接
    #         支持括号优先级
            
    #         Args:
    #             expr: 表达式字符串，如 "x + y + z" 或 "(a × b) ÷ c"
                
    #         Returns:
    #             表达式的计算结果
    #         """
    #         import re
            
    #         # 递归解析表达式
    #         def parse_expression(expression):
    #             # 处理括号
    #             while '(' in expression:
    #                 # 找到最内层的括号
    #                 match = re.search(r'\(([^()]+)\)', expression)
    #                 if not match:
    #                     break
    #                 inner_expr = match.group(1)
    #                 result = parse_expression(inner_expr)
    #                 # 替换括号内容为计算结果
    #                 expression = expression.replace(f'({inner_expr})', str(result))
                
    #             # 处理字符串拼接
    #             if '@' in expression:
    #                 parts = expression.split('@')
    #                 result = ''
    #                 for part in parts:
    #                     # 去除两端空格
    #                     part = part.strip()
    #                     # 检查是否为字面量字符串
    #                     if (part.startswith("'") and part.endswith("'") or 
    #                         part.startswith('"') and part.endswith('"')):
    #                         # 去除引号，保留字符串内容
    #                         result += part[1:-1]
    #                     elif separator in part:
    #                         # 处理路径表达式，如 "details / req_qty"
    #                         path_parts = _split_path(part)
    #                         path_value = origin_data
    #                         for path_part in path_parts:
    #                             if isinstance(path_value, dict) and path_part in path_value:
    #                                 path_value = path_value[path_part]
    #                             elif isinstance(path_value, list) and path_part == '_entries_':
    #                                 # 特殊处理 _entries_ 列表，返回第一个元素
    #                                 if path_value:
    #                                     path_value = path_value[0]
    #                                 else:
    #                                     # 列表为空，视为空字符串
    #                                     path_value = ''
    #                                     break
    #                             else:
    #                                 # 路径不存在，视为空字符串
    #                                 path_value = ''
    #                                 break
    #                         result += str(path_value)
    #                     elif part.startswith('$'):
    #                         # 从 local_static_values 中查找 $ 开头的变量
    #                         var_name = part[1:]
    #                         if var_name in local_static_values:
    #                             value = local_static_values[var_name]
    #                             result += str(value)
    #                         else:
    #                             # 变量不存在，视为空字符串
    #                             result += ''
    #                     elif part in origin_data:
    #                         value = origin_data[part]
    #                         result += str(value)
    #                     else:
    #                         # 变量不存在，视为空字符串
    #                         result += ''
    #                 return result
                
    #             # 处理乘除法
    #             if '×' in expression or '÷' in expression:
    #                 # 分割表达式为数字和运算符，考虑空格
    #                 tokens = re.findall(r'[×÷]|[^×÷]+', expression)
    #                 result = None
    #                 op = None
                    
    #                 for token in tokens:
    #                     # 去除空格
    #                     token = token.strip()
    #                     if not token:
    #                         continue
                        
    #                     if token in ('×', '÷'):
    #                         op = token
    #                     else:
    #                         # 处理变量或数字
    #                         if separator in token:
    #                             # 处理路径表达式，如 "details / req_qty"
    #                             path_parts = _split_path(token)
    #                             path_value = origin_data
    #                             for path_part in path_parts:
    #                                 if isinstance(path_value, dict) and path_part in path_value:
    #                                     path_value = path_value[path_part]
    #                                 elif isinstance(path_value, list) and path_part == '_entries_':
    #                                     # 特殊处理 _entries_ 列表，返回第一个元素
    #                                     if path_value:
    #                                         path_value = path_value[0]
    #                                     else:
    #                                         # 列表为空，视为1
    #                                         path_value = 1
    #                                         break
    #                                 else:
    #                                     # 路径不存在，视为1
    #                                     path_value = 1
    #                                     break
    #                             # 尝试转换为数值
    #                             try:
    #                                 if isinstance(path_value, str):
    #                                     path_value = path_value.replace(',', '').strip()
    #                                 num = float(path_value)
    #                             except (ValueError, TypeError):
    #                                 # 乘除法中，无法转换为数值的视为1
    #                                 num = 1
    #                         elif token.startswith('$'):
    #                             # 从 local_static_values 中查找 $ 开头的变量
    #                             var_name = token[1:]
    #                             if var_name in local_static_values:
    #                                 value = local_static_values[var_name]
    #                                 # 尝试转换为数值
    #                                 try:
    #                                     if isinstance(value, str):
    #                                         value = value.replace(',', '').strip()
    #                                     num = float(value)
    #                                 except (ValueError, TypeError):
    #                                     # 乘除法中，无法转换为数值的视为1
    #                                     num = 1
    #                             else:
    #                                 # 变量不存在，视为1
    #                                 num = 1
    #                         elif token in origin_data:
    #                             value = origin_data[token]
    #                             # 尝试转换为数值
    #                             try:
    #                                 if isinstance(value, str):
    #                                     value = value.replace(',', '').strip()
    #                                 num = float(value)
    #                             except (ValueError, TypeError):
    #                                 # 乘除法中，无法转换为数值的视为1
    #                                 num = 1
    #                         else:
    #                             # 尝试解析为数字
    #                             try:
    #                                 num = float(token)
    #                             except ValueError:
    #                                 # 不是数字也不是变量，视为1
    #                                 num = 1
                            
    #                         if result is None:
    #                             result = num
    #                         else:
    #                             if op == '×':
    #                                 result *= num
    #                             elif op == '÷':
    #                                 if num != 0:
    #                                     result /= num
    #                 return result
                
    #             # 处理加减法
    #             if '+' in expression or '-' in expression:
    #                 # 分割表达式为数字和运算符，考虑空格
    #                 tokens = re.findall(r'[+-]|[^+-]+', expression)
    #                 result = None
    #                 op = None
                    
    #                 for token in tokens:
    #                     # 去除空格
    #                     token = token.strip()
    #                     if not token:
    #                         continue
                        
    #                     if token in ('+', '-'):
    #                         op = token
    #                     else:
    #                         # 处理变量或数字
    #                         if separator in token:
    #                             # 处理路径表达式，如 "details / req_qty"
    #                             path_parts = _split_path(token)
    #                             path_value = origin_data
    #                             for path_part in path_parts:
    #                                 if isinstance(path_value, dict) and path_part in path_value:
    #                                     path_value = path_value[path_part]
    #                                 elif isinstance(path_value, list) and path_part == '_entries_':
    #                                     # 特殊处理 _entries_ 列表，返回第一个元素
    #                                     if path_value:
    #                                         path_value = path_value[0]
    #                                     else:
    #                                         # 列表为空，视为0
    #                                         path_value = 0
    #                                         break
    #                                 else:
    #                                     # 路径不存在，视为0
    #                                     path_value = 0
    #                                     break
    #                             # 尝试转换为数值
    #                             try:
    #                                 if isinstance(path_value, str):
    #                                     path_value = path_value.replace(',', '').strip()
    #                                 num = float(path_value)
    #                             except (ValueError, TypeError):
    #                                 # 加减法中，无法转换为数值的视为0
    #                                 num = 0
    #                         elif token.startswith('$'):
    #                             # 从 local_static_values 中查找 $ 开头的变量
    #                             var_name = token[1:]
    #                             if var_name in local_static_values:
    #                                 value = local_static_values[var_name]
    #                                 # 尝试转换为数值
    #                                 try:
    #                                     if isinstance(value, str):
    #                                         value = value.replace(',', '').strip()
    #                                     num = float(value)
    #                                 except (ValueError, TypeError):
    #                                     # 加减法中，无法转换为数值的视为0
    #                                     num = 0
    #                             else:
    #                                 # 变量不存在，视为0
    #                                 num = 0
    #                         elif token in origin_data:
    #                             value = origin_data[token]
    #                             # 尝试转换为数值
    #                             try:
    #                                 if isinstance(value, str):
    #                                     value = value.replace(',', '').strip()
    #                                 num = float(value)
    #                             except (ValueError, TypeError):
    #                                 # 加减法中，无法转换为数值的视为0
    #                                 num = 0
    #                         else:
    #                             # 尝试解析为数字
    #                             try:
    #                                 num = float(token)
    #                             except ValueError:
    #                                 # 不是数字也不是变量，视为0
    #                                 num = 0
                            
    #                         if result is None:
    #                             result = num
    #                         else:
    #                             if op == '+':
    #                                 result += num
    #                             elif op == '-':
    #                                 result -= num
    #                 return result
                
    #             # 处理单个变量或数字
    #             if separator in expression:
    #                 # 处理路径表达式，如 "details / req_qty"
    #                 path_parts = _split_path(expression)
    #                 path_value = origin_data
    #                 for path_part in path_parts:
    #                     if isinstance(path_value, dict) and path_part in path_value:
    #                         path_value = path_value[path_part]
    #                     elif isinstance(path_value, list) and path_part == '_entries_':
    #                         # 特殊处理 _entries_ 列表，返回第一个元素
    #                         if path_value:
    #                             path_value = path_value[0]
    #                         else:
    #                             # 列表为空，返回空字符串
    #                             path_value = ''
    #                             break
    #                     else:
    #                         # 路径不存在，返回空字符串
    #                         path_value = ''
    #                         break
    #                 # 尝试转换为数值
    #                 try:
    #                     if isinstance(path_value, str):
    #                         path_value = path_value.replace(',', '').strip()
    #                     return float(path_value)
    #                 except (ValueError, TypeError):
    #                     # 无法转换为数值，返回原值
    #                     return path_value
    #             elif expression.startswith('$'):
    #                 # 从 local_static_values 中查找 $ 开头的变量
    #                 var_name = expression[1:]
    #                 if var_name in local_static_values:
    #                     value = local_static_values[var_name]
    #                     # 直接返回原值，保持类型不变
    #                     return value
    #                 else:
    #                     # 变量不存在，返回空字符串
    #                     return ''
    #             elif expression in origin_data:
    #                 value = origin_data[expression]
    #                 # 尝试转换为数值
    #                 try:
    #                     if isinstance(value, str):
    #                         value = value.replace(',', '').strip()
    #                     return float(value)
    #                 except (ValueError, TypeError):
    #                     # 无法转换为数值，返回原值
    #                     return value
    #             else:
    #                 # 尝试解析为数字
    #                 try:
    #                     return float(expression)
    #                 except ValueError:
    #                     # 不是数字也不是变量，返回空字符串
    #                     return ''
            
    #         return parse_expression(expr)
        
    #     # 处理常规字段的映射
    #     for expr, value_path, depth in regular_mappings:
    #         # 验证路径
    #         if not value_path:
    #             raise ValueError(f"Empty path for expr: {expr}")
            
    #         # 分割路径
    #         parts = _split_path(value_path)
            
    #         # 验证分割后的路径
    #         if not parts:
    #             raise ValueError(f"Invalid path for expr: {expr}")
            
    #         # 检查是否为表达式或 $ 开头的变量
    #         if any(op in expr for op in ['+', '-', '×', '÷', '@', '(', ')']) or expr.startswith('$'):
    #             # 计算表达式的值或处理 $ 开头的变量
    #             original_value = evaluate_expression(expr)
    #         else:
    #             # 获取原始值
    #             original_value = origin_data.get(expr)
            
    #         # 处理常规字段
    #         if isinstance(original_value, list):
    #             # 处理列表类型字段
    #             # 构建父路径结构
    #             parent_parts = parts[:-1]
    #             target_field = parts[-1]
                
    #             # 检查父路径中是否有显式声明为列表的字段
    #             current = result
    #             for parent_part in parent_parts:
    #                 if parent_part in explicit_list_types:
    #                     if parent_part not in current:
    #                         current[parent_part] = []
    #                     if not current[parent_part]:
    #                         current[parent_part].append({})
    #                     current = current[parent_part][0]
    #                 else:
    #                     if parent_part not in current:
    #                         current[parent_part] = {}
    #                     current = current[parent_part]
                
    #             # 确保目标字段是列表
    #             if target_field not in current:
    #                 current[target_field] = []
                
    #             # 处理列表中的每个元素
    #             for item in original_value:
    #                 if isinstance(item, dict):
    #                     # 为每个字典元素构建层次结构
    #                     item_result = {}
    #                     item_current = item_result
                        
    #                     # 这里简化处理，直接将整个字典作为值
    #                     # 如果需要更复杂的处理，可以根据具体需求扩展
    #                     item_current[target_field] = item
                        
    #                     # 将构建好的结构添加到结果列表
    #                     current[target_field].append(item[target_field])
    #                 else:
    #                     # 非字典元素直接添加
    #                     current[target_field].append(item)
    #         else:
    #             # 处理非列表类型字段
    #             current = result
    #             i = 0
    #             while i < len(parts):
    #                 part = parts[i]
    #                 if i == len(parts) - 1:
    #                     # 检查是否需要作为列表
    #                     # 特殊处理：如果原始值是列表，或者该字段是列表候选，或者有显式列表声明
    #                     if isinstance(original_value, list) or part in explicit_list_types:
    #                         if part not in current:
    #                             current[part] = []
    #                         if isinstance(original_value, list):
    #                             current[part].append(original_value)
    #                         else:
    #                             # 如果是显式声明为列表，将单个值包装为列表
    #                             current[part].append(original_value if original_value is not None else "N/A")
    #                     else:
    #                         current[part] = original_value if original_value is not None else "N/A"
    #                     i += 1
    #                 else:
    #                     # 检查当前字段是否需要作为列表
    #                     # 优先检查显式声明
    #                     is_list = False
    #                     if part in explicit_list_types:
    #                         # 检查是否与原始数据结构冲突
    #                         if part in origin_data:
    #                             value = origin_data[part]
    #                             if not isinstance(value, dict):
    #                                 is_list = True
    #                         else:
    #                             is_list = True
    #                     elif part in explicit_dict_types:
    #                         is_list = False
    #                     else:
    #                         is_list = part in list_candidates
                        
    #                     if is_list:
    #                         # 如果当前字段是列表候选，确保其存在且是列表
    #                         if part not in current:
    #                             current[part] = []
                            
    #                         # 检查是否已经有列表元素，如果没有，创建一个
    #                         if not current[part]:
    #                             current[part].append({})
                            
    #                         # 移动到列表的第一个元素
    #                         current = current[part][0]
    #                         i += 1
    #                     else:
    #                         # 检查下一级字段是否需要作为列表
    #                         next_part = parts[i+1]
    #                         # 优先检查显式声明
    #                         next_is_list = False
    #                         if next_part in explicit_list_types:
    #                             # 检查是否与原始数据结构冲突
    #                             if next_part in origin_data:
    #                                 value = origin_data[next_part]
    #                                 if not isinstance(value, dict):
    #                                     next_is_list = True
    #                             else:
    #                                 next_is_list = True
    #                         elif next_part in explicit_dict_types:
    #                             next_is_list = False
    #                         else:
    #                             next_is_list = next_part in list_candidates
                            
    #                         if next_is_list:
    #                             # 如果下一级字段是列表候选，确保当前字段存在
    #                             if part not in current:
    #                                 current[part] = {}
    #                             current = current[part]
    #                             i += 1
    #                         else:
    #                             # 正常处理
    #                             if part not in current:
    #                                 current[part] = {}
    #                             current = current[part]
    #                             i += 1
        
    #     # 处理列表字段的映射
    #     # 首先，收集所有需要处理的列表字段映射，按目标字段名分组
    #     target_field_mappings = {}
    #     for list_key, mappings in list_field_mappings.items():
    #         for target_field, mapping_info in mappings.items():
    #             target_field_name = mapping_info["target_field_name"]
    #             if target_field_name not in target_field_mappings:
    #                 target_field_mappings[target_field_name] = {
    #                     "list_key": list_key,
    #                     "mappings": [],
    #                     "target_parent_parts": mapping_info["target_parent_parts"]
    #                 }
    #             target_field_mappings[target_field_name]["mappings"].append((target_field, mapping_info))
        
    #     # 然后，处理每个目标字段的映射
    #     for target_field_name, field_info in target_field_mappings.items():
    #         list_key = field_info["list_key"]
    #         mappings = field_info["mappings"]
    #         target_parent_parts = field_info["target_parent_parts"]
            
    #         list_value = origin_data.get(list_key)
    #         if isinstance(list_value, list):
    #             # 构建父路径结构
    #             current = result
                
    #             # 遍历父路径部分，确保每个部分都存在
    #             for part in target_parent_parts:
    #                 if isinstance(current, list):
    #                     # 如果当前是列表，使用第一个元素
    #                     if current:
    #                         current = current[0]
    #                     else:
    #                         # 如果列表为空，创建一个新元素
    #                         current.append({})
    #                         current = current[0]
                    
    #                 if part not in current:
    #                     current[part] = {}
    #                 current = current[part]
                
    #             # 确保目标字段是列表
    #             if isinstance(current, list):
    #                 # 如果当前是列表，使用第一个元素
    #                 if current:
    #                     current = current[0]
    #                 else:
    #                     # 如果列表为空，创建一个新元素
    #                     current.append({})
    #                     current = current[0]
                
    #             if target_field_name not in current:
    #                 current[target_field_name] = []
                
    #             # 处理列表中的每个元素
    #             for item in list_value:
    #                 if isinstance(item, dict):
    #                     # 为每个元素创建一个结构
    #                     item_struct = {}
                        
    #                     # 处理每个映射
    #                     for target_field, mapping_info in mappings:
    #                         sub_key = mapping_info["sub_key"]
    #                         target_subfield = mapping_info["target_subfield"]
    #                         expr = mapping_info.get("expr", "")
                            
    #                         # 评估表达式
    #                         def evaluate_item_expression(item_expr, item_data):
    #                             # 导入必要的模块
    #                             import re
    #                             # 创建临时数据，包含当前列表项的数据
    #                             temp_data = origin_data.copy()
    #                             # 将列表项的数据添加到临时数据中，以便表达式可以直接引用子键
    #                             for k, v in item_data.items():
    #                                 temp_data[k] = v
                                
    #                             # 确保 static_values 不为 None
    #                             local_static_values = static_values if static_values is not None else {}
                                
    #                             # 递归解析表达式
    #                             def parse_expression(expression):
    #                                 # 处理括号
    #                                 while '(' in expression:
    #                                     # 找到最内层的括号
    #                                     match = re.search(r'\(([^()]+)\)', expression)
    #                                     if not match:
    #                                         break
    #                                     inner_expr = match.group(1)
    #                                     result = parse_expression(inner_expr)
    #                                     # 替换括号内容为计算结果
    #                                     expression = expression.replace(f'({inner_expr})', str(result))
                                    
    #                                 # 处理字符串拼接
    #                                 if '@' in expression:
    #                                     parts = expression.split('@')
    #                                     result = ''
    #                                     for part in parts:
    #                                         # 去除两端空格
    #                                         part = part.strip()
    #                                         # 检查是否为字面量字符串
    #                                         if (part.startswith("'") and part.endswith("'") or 
    #                                             part.startswith('"') and part.endswith('"')):
    #                                             # 去除引号，保留字符串内容
    #                                             result += part[1:-1]
    #                                         elif separator in part:
    #                                             # 处理路径表达式，如 "details / req_qty"
    #                                             path_parts = _split_path(part)
    #                                             path_value = temp_data
    #                                             for path_part in path_parts:
    #                                                 if isinstance(path_value, dict) and path_part in path_value:
    #                                                     path_value = path_value[path_part]
    #                                                 elif path_part == '_entries_' and list_key == '_entries_':
    #                                                     # 特殊处理：当路径中包含_entries_且list_key也是_entries_时，使用当前item
    #                                                     path_value = item_data
    #                                                 else:
    #                                                     # 路径不存在，视为空字符串
    #                                                     path_value = ''
    #                                                     break
    #                                             result += str(path_value)
    #                                         elif part.startswith('$'):
    #                                             # 从 local_static_values 中查找 $ 开头的变量
    #                                             var_name = part[1:]
    #                                             if var_name in local_static_values:
    #                                                 value = local_static_values[var_name]
    #                                                 result += str(value)
    #                                             else:
    #                                                 # 变量不存在，视为空字符串
    #                                                 result += ''
    #                                         elif part in temp_data:
    #                                             value = temp_data[part]
    #                                             result += str(value)
    #                                         else:
    #                                             # 变量不存在，视为空字符串
    #                                             result += ''
    #                                     return result
                                    
    #                                 # 处理乘除法
    #                                 if '×' in expression or '÷' in expression:
    #                                     # 分割表达式为数字和运算符，考虑空格
    #                                     tokens = re.findall(r'[×÷]|[^×÷]+', expression)
    #                                     result = None
    #                                     op = None
                                        
    #                                     for token in tokens:
    #                                         # 去除空格
    #                                         token = token.strip()
    #                                         if not token:
    #                                             continue
                                            
    #                                         if token in ('×', '÷'):
    #                                             op = token
    #                                         else:
    #                                             # 处理变量或数字
    #                                             if separator in token:
    #                                                 # 处理路径表达式，如 "details / req_qty"
    #                                                 path_parts = _split_path(token)
    #                                                 path_value = temp_data
    #                                                 for path_part in path_parts:
    #                                                     if isinstance(path_value, dict) and path_part in path_value:
    #                                                         path_value = path_value[path_part]
    #                                                     elif path_part == '_entries_' and list_key == '_entries_':
    #                                                         # 特殊处理：当路径中包含_entries_且list_key也是_entries_时，使用当前item
    #                                                         path_value = item_data
    #                                                     else:
    #                                                         # 路径不存在，视为1
    #                                                         path_value = 1
    #                                                         break
    #                                                 # 尝试转换为数值
    #                                                 try:
    #                                                     if isinstance(path_value, str):
    #                                                         path_value = path_value.replace(',', '').strip()
    #                                                     num = float(path_value)
    #                                                 except (ValueError, TypeError):
    #                                                     # 乘除法中，无法转换为数值的视为1
    #                                                     num = 1
    #                                             elif token.startswith('$'):
    #                                                 # 从 local_static_values 中查找 $ 开头的变量
    #                                                 var_name = token[1:]
    #                                                 if var_name in local_static_values:
    #                                                     value = local_static_values[var_name]
    #                                                     # 尝试转换为数值
    #                                                     try:
    #                                                         if isinstance(value, str):
    #                                                             value = value.replace(',', '').strip()
    #                                                         num = float(value)
    #                                                     except (ValueError, TypeError):
    #                                                         # 乘除法中，无法转换为数值的视为1
    #                                                         num = 1
    #                                                 else:
    #                                                     # 变量不存在，视为1
    #                                                     num = 1
    #                                             elif token in temp_data:
    #                                                 value = temp_data[token]
    #                                                 # 尝试转换为数值
    #                                                 try:
    #                                                     if isinstance(value, str):
    #                                                         value = value.replace(',', '').strip()
    #                                                     num = float(value)
    #                                                 except (ValueError, TypeError):
    #                                                     # 乘除法中，无法转换为数值的视为1
    #                                                     num = 1
    #                                             else:
    #                                                 # 尝试解析为数字
    #                                                 try:
    #                                                     num = float(token)
    #                                                 except ValueError:
    #                                                     # 不是数字也不是变量，视为1
    #                                                     num = 1
                                                
    #                                             if result is None:
    #                                                 result = num
    #                                             else:
    #                                                 if op == '×':
    #                                                     result *= num
    #                                                 elif op == '÷':
    #                                                     if num != 0:
    #                                                         result /= num
    #                                         return result
                                    
    #                                 # 处理加减法
    #                                 if '+' in expression or '-' in expression:
    #                                     # 分割表达式为数字和运算符，考虑空格
    #                                     tokens = re.findall(r'[+-]|[^+-]+', expression)
    #                                     result = None
    #                                     op = None
                                        
    #                                     for token in tokens:
    #                                         # 去除空格
    #                                         token = token.strip()
    #                                         if not token:
    #                                             continue
                                            
    #                                         if token in ('+', '-'):
    #                                             op = token
    #                                         else:
    #                                             # 处理变量或数字
    #                                             if separator in token:
    #                                                 # 处理路径表达式，如 "details / req_qty"
    #                                                 path_parts = _split_path(token)
    #                                                 path_value = temp_data
    #                                                 for path_part in path_parts:
    #                                                     if isinstance(path_value, dict) and path_part in path_value:
    #                                                         path_value = path_value[path_part]
    #                                                     elif path_part == '_entries_' and list_key == '_entries_':
    #                                                         # 特殊处理：当路径中包含_entries_且list_key也是_entries_时，使用当前item
    #                                                         path_value = item_data
    #                                                     else:
    #                                                         # 路径不存在，视为0
    #                                                         path_value = 0
    #                                                         break
    #                                                 # 尝试转换为数值
    #                                                 try:
    #                                                     if isinstance(path_value, str):
    #                                                         path_value = path_value.replace(',', '').strip()
    #                                                     num = float(path_value)
    #                                                 except (ValueError, TypeError):
    #                                                     # 加减法中，无法转换为数值的视为0
    #                                                     num = 0
    #                                             elif token.startswith('$'):
    #                                                 # 从 local_static_values 中查找 $ 开头的变量
    #                                                 var_name = token[1:]
    #                                                 if var_name in local_static_values:
    #                                                     value = local_static_values[var_name]
    #                                                     # 尝试转换为数值
    #                                                     try:
    #                                                         if isinstance(value, str):
    #                                                             value = value.replace(',', '').strip()
    #                                                         num = float(value)
    #                                                     except (ValueError, TypeError):
    #                                                         # 加减法中，无法转换为数值的视为0
    #                                                         num = 0
    #                                                 else:
    #                                                     # 变量不存在，视为0
    #                                                     num = 0
    #                                             elif token in temp_data:
    #                                                 value = temp_data[token]
    #                                                 # 尝试转换为数值
    #                                                 try:
    #                                                     if isinstance(value, str):
    #                                                         value = value.replace(',', '').strip()
    #                                                     num = float(value)
    #                                                 except (ValueError, TypeError):
    #                                                     # 加减法中，无法转换为数值的视为0
    #                                                     num = 0
    #                                             else:
    #                                                 # 尝试解析为数字
    #                                                 try:
    #                                                     num = float(token)
    #                                                 except ValueError:
    #                                                     # 不是数字也不是变量，视为0
    #                                                     num = 0
                                                
    #                                             if result is None:
    #                                                 result = num
    #                                             else:
    #                                                 if op == '+':
    #                                                     result += num
    #                                                 elif op == '-':
    #                                                     result -= num
    #                                         return result
                                    
    #                                 # 处理单个变量或数字
    #                                 if separator in expression:
    #                                     # 处理路径表达式，如 "details / req_qty"
    #                                     path_parts = _split_path(expression)
    #                                     path_value = temp_data
    #                                     for path_part in path_parts:
    #                                         if isinstance(path_value, dict) and path_part in path_value:
    #                                             path_value = path_value[path_part]
    #                                         elif path_part == '_entries_' and list_key == '_entries_':
    #                                             # 特殊处理：当路径中包含_entries_且list_key也是_entries_时，使用当前item
    #                                             path_value = item_data
    #                                         else:
    #                                             # 路径不存在，返回空字符串
    #                                             path_value = ''
    #                                             break
    #                                     # 尝试转换为数值
    #                                     try:
    #                                         if isinstance(path_value, str):
    #                                             path_value = path_value.replace(',', '').strip()
    #                                         return float(path_value)
    #                                     except (ValueError, TypeError):
    #                                         # 无法转换为数值，返回原值
    #                                         return path_value
    #                                 elif expression.startswith('$'):
    #                                     # 从 local_static_values 中查找 $ 开头的变量
    #                                     var_name = expression[1:]
    #                                     if var_name in local_static_values:
    #                                         value = local_static_values[var_name]
    #                                         # 直接返回原值，保持类型不变
    #                                         return value
    #                                     else:
    #                                         # 变量不存在，返回空字符串
    #                                         return ''
    #                                 elif expression in temp_data:
    #                                     value = temp_data[expression]
    #                                     # 尝试转换为数值
    #                                     try:
    #                                         if isinstance(value, str):
    #                                             value = value.replace(',', '').strip()
    #                                         return float(value)
    #                                     except (ValueError, TypeError):
    #                                         # 无法转换为数值，返回原值
    #                                         return value
    #                                 else:
    #                                     # 尝试解析为数字
    #                                     try:
    #                                         return float(expression)
    #                                     except ValueError:
    #                                         # 不是数字也不是变量，返回空字符串
    #                                         return ''
                                    
    #                             return parse_expression(item_expr)
                            
    #                         # 评估表达式获取值
    #                         if expr:
    #                             # For list field mappings, we need to evaluate the expression relative to the current item
    #                             # Create a temp_data that includes both the origin_data and the current item
    #                             temp_data = origin_data.copy()
    #                             temp_data.update(item)
                                
    #                             # Replace list_key references in the expression with direct references to item fields
    #                             # For example, "details / req_qty" becomes just "req_qty"
    #                             processed_expr = expr
    #                             if list_key in processed_expr:
    #                                 import re
    #                                 # Replace patterns like "details / req_qty" with "req_qty"
    #                                 processed_expr = re.sub(rf'{list_key}\s*{re.escape(separator)}\s*', '', processed_expr)
                                
    #                             # Special handling based on the target field
    #                             if target_field == "Code" and target_subfield is None:
    #                                 # This is for MaterialRequestDetails / Code
    #                                 if "itemno" in item:
    #                                     value = item["itemno"]  # Use the original string value
    #                             elif target_field == "Inventory" and target_subfield == "Code":
    #                                 # This is for MaterialRequestDetails / Inventory / Code
    #                                 if "materialno" in item:
    #                                     value = item["materialno"]  # Use the original string value
    #                             elif target_field == "BaseQuantity":
    #                                 # This is for MaterialRequestDetails / BaseQuantity
    #                                 if "req_qty" in item:
    #                                     req_qty = item["req_qty"]
    #                                     value = abs(req_qty)  # Ensure positive value
    #                                     # Convert to integer if it's a whole number
    #                                     if isinstance(value, (int, float)) and value.is_integer():
    #                                         value = int(value)
    #                             else:
    #                                 # Evaluate the processed expression
    #                                 value = evaluate_item_expression(processed_expr, item)
    #                         elif sub_key in item:
    #                             value = item[sub_key]
    #                         else:
    #                             value = ''
                            
    #                         # 处理字段，根据是否有子字段决定结构
    #                         if target_subfield is None:
    #                             item_struct[target_field] = value
    #                         else:
    #                             # 构建层次结构
    #                             if target_field not in item_struct:
    #                                 item_struct[target_field] = {}
    #                             item_struct[target_field][target_subfield] = value
                        
    #                     # 将构建好的结构添加到结果列表
    #                     current[target_field_name].append(item_struct)
        
    #     return result


    @staticmethod
    def merge_common_fields(data: List[Dict], merge_with: List[str], entries_key: str = "ENTRIES") -> Dict:
        """
        将扁平数据列表按照共同字段分组并整理为父子结构
        
        Args:
            data: 扁平数据列表，每个元素是一个字典
            merge_with: 用于合并的共同字段名列表
            entries_key: 合并后，子结构（列表）归于该键下，默认为 "ENTRIES"
        
        Returns:
            父子结构的字典，父结构包含 merge_with 中的字段，子结构包含其他字段
        
        Raises:
            ValueError: 当 merge_with 为空时
        """
        if not data:
            return {}
        
        if not merge_with:
            raise ValueError("Merge with list cannot be empty")
        
        # 按分组字段组合分组数据
        grouped_data = {}
        for item in data:
            # 检查所有分组字段是否存在
            for key in merge_with:
                if key not in item:
                    raise ValueError(f"Merge with key '{key}' not found in data item")
            
            # 生成组合键
            key_values = tuple(item[key] for key in merge_with)
            if key_values not in grouped_data:
                grouped_data[key_values] = []
            grouped_data[key_values].append(item)
        
        # 处理每个分组
        result = {}
        for key_values, items in grouped_data.items():
            # 构建父结构
            parent = {}
            for i, key in enumerate(merge_with):
                parent[key] = key_values[i]
            
            # 构建子结构
            details = []
            for item in items:
                # 子结构包含除分组字段外的所有字段
                detail = {}
                for field, value in item.items():
                    if field not in merge_with:
                        detail[field] = value
                details.append(detail)
            
            # 添加子结构到父结构
            parent[entries_key] = details
            result[key_values] = parent
        
        # 如果只有一个分组，直接返回该分组
        if len(result) == 1:
            return next(iter(result.values()))
        
        return result
