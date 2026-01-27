from typing import List, Dict, Any#, Optional, Callable, Union
import enum

import pandas as pd, json



class DataProcessor:

    @staticmethod
    def is_equal(val1, val2):
        """判断两个值是否不同，处理不同类型之间的比较"""
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
            return DataProcessor.is_equal(enum_val1, enum_val2)
        
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
            return DataProcessor.is_equal(parsed_val1, parsed_val2)
        
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
            # 创建新字典，包含原始字典中除了expand_key以外的所有键值对
            new_dict = {k: v for k, v in data.items() if k != expand_key}
            
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

 
    @staticmethod
    def generate_hierarchy_dict(origin_data: Dict[str, Any], field_map: Dict[str, str], separator: str = " / ") -> Dict[str, Any]:
        """
        根据字段映射关系，将扁平的原始数据字典转换为具有层次结构的嵌套字典
        支持处理原始数据中的列表类型字段，生成对应的列表形式层次结构
        
        Args:
            origin_data: 原始数据字典，包含需要转换的键值对
            field_map: 字段映射字典，键是目标层次路径，值是原始数据中的键
            separator: 层次路径的分隔符，默认为 " / "
        
        Returns:
            具有层次结构的嵌套字典
        
        Raises:
            ValueError: 当field_map中的路径为空或无效时
        """
        result = {}
        
        # 辅助函数：分割路径并清理空白字符
        def _split_path(path):
            return [p.strip() for p in path.split(separator) if p.strip()]
        
        # 辅助函数：构建父路径结构
        def _build_parent_structure(parent_parts):
            current = result
            for part in parent_parts:
                if part not in current:
                    current[part] = {}
                current = current[part]
            return current
        
        # 分析字段映射，识别可能需要作为列表的字段
        # 统计每个路径段的出现次数和子路径模式
        path_analysis = {}
        
        for value_path, key in field_map.items():
            parts = _split_path(value_path)
            if not parts:
                continue
            
            # 分析路径的每个级别
            for i, part in enumerate(parts):
                if part not in path_analysis:
                    path_analysis[part] = {
                        "occurrences": 0,
                        "parent_paths": set(),
                        "child_patterns": set(),
                        "full_paths": set()
                    }
                
                path_analysis[part]["occurrences"] += 1
                
                # 记录父路径
                if i > 0:
                    parent_path = separator.join(parts[:i])
                    path_analysis[part]["parent_paths"].add(parent_path)
                
                # 记录子路径模式
                if i < len(parts) - 1:
                    child_pattern = parts[i+1]
                    path_analysis[part]["child_patterns"].add(child_pattern)
                
                # 记录完整路径
                path_analysis[part]["full_paths"].add(value_path)
        
        # 识别需要作为列表的字段
        # 规则：
        # 1. 如果多个不同的完整路径都包含同一个父路径段，并且这些路径的下一级路径段不同，那么该父路径段应该是列表
        # 例如：ManufactureOrderDetails / Inventory / Code 和 ManufactureOrderDetails / Unit / Name
        list_candidates = set()
        
        # 首先，收集所有可能的父路径段
        parent_segments = {}
        for value_path, key in field_map.items():
            parts = _split_path(value_path)
            if len(parts) >= 2:
                # 对于每个路径，检查其所有可能的父路径段
                for i in range(1, len(parts)):
                    parent_segment = parts[i-1]
                    child_segment = parts[i]
                    
                    if parent_segment not in parent_segments:
                        parent_segments[parent_segment] = set()
                    
                    # 记录该父路径段的所有子路径段
                    parent_segments[parent_segment].add(child_segment)
        
        # 然后，检查每个父路径段是否有多个不同的子路径段
        for parent_segment, child_segments in parent_segments.items():
            # 如果一个父路径段有多个不同的子路径段，那么它应该是列表
            if len(child_segments) > 1:
                list_candidates.add(parent_segment)
        
        # 特殊处理：如果一个字段在多个完整路径中出现，并且这些路径的深度相同，那么它可能是列表
        for part, analysis in path_analysis.items():
            # 检查该字段是否在多个完整路径中出现
            if len(analysis["full_paths"]) > 1:
                # 检查这些路径的深度是否相同
                depths = set()
                for full_path in analysis["full_paths"]:
                    depths.add(len(_split_path(full_path)))
                
                # 如果所有路径的深度相同，那么该字段可能是列表
                if len(depths) == 1:
                    list_candidates.add(part)
        
        # 首先收集所有列表字段的映射
        list_field_mappings = {}
        regular_mappings = []
        
        for value_path, key in field_map.items():
            # 检查目标路径是否包含分隔符，判断是否为列表字段映射
            # 列表字段映射的目标路径格式：[父路径 /] 列表字段名 [/ 目标字段 [/ 子字段]]
            # 例如：ManufactureOrderDetails / ManufactureOrderProcessDetails / Workcenter / Code
            parts = _split_path(value_path)
            
            if len(parts) >= 2:
                # 检查原始数据键是否对应列表字段
                # 列表字段的原始数据键格式：list_key[separator]sub_key
                if separator in key:
                    list_key, sub_key = [k.strip() for k in key.split(separator)]
                    if list_key not in list_field_mappings:
                        list_field_mappings[list_key] = {}
                    
                    # 动态获取目标路径的父路径和字段名
                    # 对于列表字段的映射，目标路径格式为：[父路径 /] 列表字段名 [/ 目标字段 [/ 子字段]]
                    # 例如：ManufactureOrderDetails / ManufactureOrderProcessDetails / Workcenter / Code
                    # 或者：ManufactureOrderDetails / ManufactureOrderProcessDetails / SortNo
                    # 或者：Fields / StringField
                    # 或者：StringField
                    
                    # 根据路径长度决定处理方式
                    if len(parts) == 1:
                        # 只有一个部分，直接作为列表字段名
                        target_parent_parts = []
                        target_field_name = parts[0]
                        target_field = parts[0]
                        target_subfield = None
                    elif len(parts) == 2:
                        # 两个部分，第一部分是父路径，第二部分是列表字段名
                        target_parent_parts = parts[:-1]
                        target_field_name = parts[-1]
                        target_field = parts[-1]
                        target_subfield = None
                    else:
                        # 三个或更多部分，按照正常方式处理
                        # 列表字段名（ManufactureOrderProcessDetails）
                        target_field_name = parts[-2]
                        
                        # 目标字段（如 Workcenter 或 SortNo）
                        target_field = parts[-1]
                        
                        # 子字段（如 Code），如果有的话
                        target_subfield = None
                        
                        # 检查是否有子字段（路径长度大于 3）
                        if len(parts) > 3:
                            # 有子字段，调整字段名和子字段
                            target_field_name = parts[-3]
                            target_field = parts[-2]
                            target_subfield = parts[-1]
                        
                        # 获取目标路径的父路径
                        # 父路径是除了最后两部分（或三部分，如果有子字段）之外的所有部分
                        parent_parts_count = len(parts) - (3 if target_subfield else 2)
                        target_parent_parts = parts[:parent_parts_count]
                    
                    if target_field not in list_field_mappings[list_key]:
                        list_field_mappings[list_key][target_field] = {
                            "sub_key": sub_key,
                            "target_parent_parts": target_parent_parts,
                            "target_field_name": target_field_name,
                            "target_field": target_field,
                            "target_subfield": target_subfield
                        }
                else:
                    # 处理常规字段，存储为 (key, value_path, depth) 元组
                    depth = len(parts)  # 路径深度，顶层为 1
                    regular_mappings.append((key, value_path, depth))
            else:
                # 处理常规字段，存储为 (key, value_path, depth) 元组
                depth = len(parts)  # 路径深度，顶层为 1
                regular_mappings.append((key, value_path, depth))
        
        # 按路径深度排序，深度小的（顶层）先处理
        regular_mappings.sort(key=lambda x: x[2])
        
        # 处理常规字段的映射
        for key, value_path, depth in regular_mappings:
            # 验证路径
            if not value_path:
                raise ValueError(f"Empty path for key: {key}")
            
            # 分割路径
            parts = _split_path(value_path)
            
            # 验证分割后的路径
            if not parts:
                raise ValueError(f"Invalid path for key: {key}")
            
            # 获取原始值
            original_value = origin_data.get(key)
            
            # 处理常规字段
            if isinstance(original_value, list):
                # 处理列表类型字段
                # 构建父路径结构
                parent_parts = parts[:-1]
                target_field = parts[-1]
                
                current = _build_parent_structure(parent_parts)
                
                # 确保目标字段是列表
                if target_field not in current:
                    current[target_field] = []
                
                # 处理列表中的每个元素
                for item in original_value:
                    if isinstance(item, dict):
                        # 为每个字典元素构建层次结构
                        item_result = {}
                        item_current = item_result
                        
                        # 这里简化处理，直接将整个字典作为值
                        # 如果需要更复杂的处理，可以根据具体需求扩展
                        item_current[target_field] = item
                        
                        # 将构建好的结构添加到结果列表
                        current[target_field].append(item[target_field])
                    else:
                        # 非字典元素直接添加
                        current[target_field].append(item)
            else:
                # 处理非列表类型字段
                current = result
                i = 0
                while i < len(parts):
                    part = parts[i]
                    if i == len(parts) - 1:
                        # 检查是否需要作为列表
                        # 特殊处理：如果原始值是列表，或者该字段是列表候选
                        if isinstance(original_value, list):
                            if part not in current:
                                current[part] = []
                            current[part].append(original_value)
                        else:
                            current[part] = origin_data.get(key, "N/A")
                        i += 1
                    else:
                        # 检查当前字段是否需要作为列表
                        if part in list_candidates:
                            # 如果当前字段是列表候选，确保其存在且是列表
                            if part not in current:
                                current[part] = []
                            
                            # 检查是否已经有列表元素，如果没有，创建一个
                            if not current[part]:
                                current[part].append({})
                            
                            # 移动到列表的第一个元素
                            current = current[part][0]
                            i += 1
                        else:
                            # 检查下一级字段是否需要作为列表
                            next_part = parts[i+1]
                            if next_part in list_candidates:
                                # 如果下一级字段是列表候选，确保当前字段存在
                                if part not in current:
                                    current[part] = {}
                                current = current[part]
                                i += 1
                            else:
                                # 正常处理
                                if part not in current:
                                    current[part] = {}
                                current = current[part]
                                i += 1
        
        # 处理列表字段的映射
        for list_key, mappings in list_field_mappings.items():
            list_value = origin_data.get(list_key)
            
            if isinstance(list_value, list):
                # 确定目标路径
                # 假设所有映射的目标父路径相同
                sample_mapping = next(iter(mappings.values()))
                target_parent_parts = sample_mapping["target_parent_parts"]
                
                # 构建父路径结构
                current = result
                
                # 遍历父路径部分，确保每个部分都存在
                for part in target_parent_parts:
                    if isinstance(current, list):
                        # 如果当前是列表，使用第一个元素
                        if current:
                            current = current[0]
                        else:
                            # 如果列表为空，创建一个新元素
                            current.append({})
                            current = current[0]
                    
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                
                # 目标字段名（ManufactureOrderProcessDetails）
                target_field_name = sample_mapping["target_field_name"]
                
                # 确保目标字段是列表
                if isinstance(current, list):
                    # 如果当前是列表，使用第一个元素
                    if current:
                        current = current[0]
                    else:
                        # 如果列表为空，创建一个新元素
                        current.append({})
                        current = current[0]
                
                if target_field_name not in current:
                    current[target_field_name] = []
                
                # 处理列表中的每个元素
                for item in list_value:
                    if isinstance(item, dict):
                        # 为每个元素创建一个结构
                        item_struct = {}
                        
                        # 处理每个映射
                        for target_field, mapping_info in mappings.items():
                            sub_key = mapping_info["sub_key"]
                            target_subfield = mapping_info["target_subfield"]
                            
                            if sub_key in item:
                                # 处理字段，根据是否有子字段决定结构
                                if target_subfield is None:
                                    item_struct[target_field] = item[sub_key]
                                else:
                                    # 构建层次结构
                                    if target_field not in item_struct:
                                        item_struct[target_field] = {}
                                    item_struct[target_field][target_subfield] = item[sub_key]
                        
                        # 将构建好的结构添加到结果列表
                        current[target_field_name].append(item_struct)
        
        return result


if __name__ == "__main__":
    # 测试代码
    def test_generate_hierarchy_dict():
        # 调整 field_map 结构为 {目标路径: 原始数据键}
        field_map = {
            "ExternalCode": "supplyno",
            "StartDate": "dt_ordstart",
            "FinishDate": "dt_ordend",
            "BusiType / Code": "AAAAA",
            "Department / Code": "BBBBB",
            "VoucherDate": "create_date",
            "ManufactureOrderDetails / Inventory / Code": "materialno",
            "ManufactureOrderDetails / Unit / Name": "unit",
            "ManufactureOrderDetails / Quantity": "avail_qty",
            "ManufactureOrderDetails / ManufactureOrderProcessDetails / Workcenter / Code": "orderwc / workcenter",
            "ManufactureOrderDetails / ManufactureOrderProcessDetails / ItemNo / Code": "orderwc / itemno",
            "ManufactureOrderDetails / ManufactureOrderProcessDetails / SortNo": "orderwc / sortno"
        }


        origin_data = {
            "supplyno": "123456",
            "dt_ordstart": "2023-01-01",
            "dt_ordend": "2023-01-31",
            "AAAAA": "1001",
            "BBBBB": "2001",
            "create_date": "2023-01-15",
            "materialno": "M001",
            "unit": "个",
            "avail_qty": 100,
            "orderwc": [
                {
                    "workcenter": "WC001", "itemno": "P001", "sortno": 1
                },
                {
                    "workcenter": "WC003", "itemno": "P001", "sortno": 2
                }
            ]
        }

        # 生成层次结构字典
        hierarchy_dict = DataProcessor.generate_hierarchy_dict(origin_data, field_map)

        # 打印结果
        import json
        print(json.dumps(hierarchy_dict, indent=2, ensure_ascii=False))

        # 测试更深层次的路径
        print("\n=== 测试更深层次的路径 ===")

        deep_origin_data = {
            "supplyno": "123456",
            "deep_list": [
                {"level1": {"level2": {"level3": "value1"}}},
                {"level1": {"level2": {"level3": "value2"}}}
            ]
        }

        deep_field_map = {
            "ExternalCode": "supplyno",
            "Level1 / Level2 / Level3 / Value": "deep_list / level1"
        }

        deep_result = DataProcessor.generate_hierarchy_dict(deep_origin_data, deep_field_map)
        print(json.dumps(deep_result, indent=2, ensure_ascii=False))

        # 测试边缘情况
        print("\n=== 测试边缘情况 ===")

        # 测试不同类型的字段值
        type_origin_data = {
            "supplyno": "123456",
            "mixed_list": [
                {"string_field": "value1", "int_field": 1, "bool_field": True},
                {"string_field": "value2", "int_field": 2, "bool_field": False}
            ]
        }

        # 调整 type_field_map 结构为 {目标路径: 原始数据键}
        type_field_map = {
            "ExternalCode": "supplyno",
            "Fields / StringField": "mixed_list / string_field",
            "Fields / IntField": "mixed_list / int_field",
            "Fields / BoolField": "mixed_list / bool_field"
        }

        type_result = DataProcessor.generate_hierarchy_dict(type_origin_data, type_field_map)
        print("不同类型的字段值测试:")
        print(json.dumps(type_result, indent=2, ensure_ascii=False))

        # 测试缺少字段的情况
        missing_origin_data = {
            "supplyno": "123456",
            "orderwc": [
                {"workcenter": "WC001"},  # 缺少 itemno 和 sortno
                {"itemno": "P001"}  # 缺少 workcenter 和 sortno
            ]
        }

        # 调整 missing_field_map 结构为 {目标路径: 原始数据键}
        missing_field_map = {
            "ExternalCode": "supplyno",
            "ManufactureOrderDetails / ManufactureOrderProcessDetails / Workcenter / Code": "orderwc / workcenter",
            "ManufactureOrderDetails / ManufactureOrderProcessDetails / ItemNo / Code": "orderwc / itemno",
            "ManufactureOrderDetails / ManufactureOrderProcessDetails / SortNo": "orderwc / sortno"
        }

        missing_result = DataProcessor.generate_hierarchy_dict(missing_origin_data, missing_field_map)
        print("\n缺少字段的情况测试:")
        print(json.dumps(missing_result, indent=2, ensure_ascii=False))


    test_generate_hierarchy_dict()

    # 测试 ManufactureOrderDetails 应该是列表的情况
    print("\n=== 测试 ManufactureOrderDetails 列表情况 ===")
    
    # 模拟 yonyou_tplus.py 中的字段映射结构
    yonyou_field_map = {
        "ExternalCode": "supplyno",
        "StartDate": "dt_ordstart",
        "FinishDate": "dt_ordend",
        "BusiType / Code": "AAAAA",
        "Department / Code": "BBBBB",
        "VoucherDate": "create_date",
        "ManufactureOrderDetails / Inventory / Code": "materialno",
        "ManufactureOrderDetails / Unit / Name": "unit",
        "ManufactureOrderDetails / Quantity": "avail_qty"
    }
    
    yonyou_origin_data = {
        "supplyno": "123456",
        "dt_ordstart": "2023-01-01",
        "dt_ordend": "2023-01-31",
        "AAAAA": "1001",
        "BBBBB": "2001",
        "create_date": "2023-01-15",
        "materialno": "M001",
        "unit": "个",
        "avail_qty": 100
    }
    
    yonyou_result = DataProcessor.generate_hierarchy_dict(yonyou_origin_data, yonyou_field_map)
    print("ManufactureOrderDetails 列表测试:")
    print(json.dumps(yonyou_result, indent=2, ensure_ascii=False))
    
    # 检查 ManufactureOrderDetails 是否为列表
    if "ManufactureOrderDetails" in yonyou_result:
        print(f"\nManufactureOrderDetails 类型: {type(yonyou_result['ManufactureOrderDetails'])}")
        if isinstance(yonyou_result['ManufactureOrderDetails'], list):
            print("✓ ManufactureOrderDetails 正确识别为列表")
        else:
            print("✗ ManufactureOrderDetails 未识别为列表")