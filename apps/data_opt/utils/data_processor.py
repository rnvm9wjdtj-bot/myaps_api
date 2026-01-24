from typing import List, Dict#, Optional, Callable, Union
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