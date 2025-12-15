import pandas as pd, json, warnings, os
from typing import List, Dict, Any



MD_CTRLID = {
    'product_no': 'pn',
    'product_version': 'pv',
    'sort_no': 'sn',
    'item_no': 'in',
    'dto': 'dto'
}


def process_json_route_data(
        json_data: str | List[Dict[str, Any]], 
        mainfield_mapper: dict, 
        dtofield_mapper: dict={},
    ) -> pd.DataFrame:
    """
    处理JSON格式的工艺路线数据，转换为适合校验的结构
    """

    # 如果输入是字符串，先解析为JSON
    if isinstance(json_data, str):
        try:
            route_list = json.loads(json_data)
        except json.JSONDecodeError:
            # 如果已经是列表格式，直接使用
            route_list = eval(json_data)
    else:
        route_list = json_data

    # 从项目配置获取 ItemNo 前缀和宽度
    try:
        from projects import active_connector
        itemno_prefix = active_connector.itemno_prefix
        itemno_width = active_connector.itemno_width
    except:
        itemno_prefix = 'P'
        itemno_width = 2
        print(f"⚠️ 未配置 ItemNo 前缀和宽度，默认使用 {itemno_prefix} 作为前缀，宽度为 {itemno_width}")
    
    # 转换为DataFrame
    df_data = []
    for item in route_list:
        row = {mk: item.get(ok, '') for mk, ok in mainfield_mapper.items()}
        
        # 填充 ItemNo
        if not row.get(MD_CTRLID['item_no']):
            sort_no = row[MD_CTRLID['sort_no']]
            try:
                # 先转换为整数，处理可能的异常
                sort_no = int(sort_no)
                row[MD_CTRLID['item_no']] = f"{itemno_prefix}{sort_no:0{itemno_width}d}"
            except (ValueError, TypeError):
                # 处理转换失败的情况，例如使用默认值或记录错误
                # row[MD_CTRLID['item_no']] = f"{itemno_prefix}{itemno_width * '0'}"  # 默认值
                row[MD_CTRLID['item_no']] = f"{itemno_prefix}{sort_no}"  # 默认值

        row[MD_CTRLID['dto']] = {mk: item.get(ok, '') for mk, ok in dtofield_mapper.items()} if dtofield_mapper else None
        df_data.append(row)

    df = pd.DataFrame(df_data)

    return df


def route_check_core_processor(
    route_df: pd.DataFrame,
    product_col: str = MD_CTRLID['product_no'],
    productversion_col: str = MD_CTRLID['product_version'],
    sortno_col: str = MD_CTRLID['sort_no'],
    itemno_col: str = MD_CTRLID['item_no'],
):
    marked_data = route_df.copy()
    marked_data['E'] = marked_data.apply(lambda _:[], axis=1)
    marked_data['W'] = marked_data.apply(lambda _:[], axis=1)

    # 初始化摘要
    issue_summary = {
        'ERROR': {
            'sortno_notint': [],
            'itemno_repeat': [],
            # 'orphan_items': [],
            # 'multi_parents': defaultdict(list)
        },
        'WARNING': {
            'sortno_repeat': [],
            # 'non_child': [],
            # 'invalid_qty': [],
            # 'missing_cols': [],
            # 'duplicate_relations': []
        }
    }

    if productversion_col not in marked_data.columns:
        has_version_col = False
        marked_data[productversion_col] = ''
    else:
        has_version_col = True

    # required_cols = [product_col, sortno_col, itemno_col]
    # missing_cols = [col for col in required_cols if col not in marked_data.columns]
    # if missing_cols:
    #     raise ValueError(f"缺失必要列: {', '.join(missing_cols)}")

    product_item_map = {}
    for idx, row in marked_data.iterrows():
        pn = row[product_col]
        pv = str(row[productversion_col])
        sn = row[sortno_col]
        itn = row[itemno_col]
        data_key = (pn, pv, itn)

        # 检查是否有重复的 ItemNo
        if data_key in product_item_map:
            marked_data.at[idx, 'E'].append("工序项重复")
            issue_summary['ERROR']['itemno_repeat'].append(data_key)
        else:
            product_item_map[data_key] = set()

        # SortNo 必须是整数
        try:
            int(sn)
        except ValueError:
            marked_data.at[idx, 'E'].append("顺序号非整数")
            issue_summary['ERROR']['sortno_notint'].append(data_key)

        # 检查是否有重复的 SortNo
        if sn in product_item_map[data_key]:
            marked_data.at[idx, 'W'].append(f"顺序号重复")
            issue_summary['WARNING']['sortno_repeat'].append(data_key)
        else:
            product_item_map[data_key].add(sn)

    return {
        'marked_data': marked_data,
        'issue_summary': issue_summary,
    }


if __name__ == '__main__':
    # 测试数据
    test_json = """
    [
        {"productno": "A123", "productversion": "V1", "sortno": 1, "itemno": "A001"},
        {"productno": "A123", "productversion": "V1", "sortno": "a", "itemno": "A002"},
        {"productno": "A123", "productversion": "V1", "sortno": "a", "itemno": "A002"}
    ]
    """
    # 测试映射
    mainfield_mapper = {
        MD_CTRLID['product_no']: 'productno',
        MD_CTRLID['product_version']: 'productversion',
        MD_CTRLID['sort_no']: 'sortno',
        MD_CTRLID['item_no']: 'itemno',
    }
    dtofield_mapper = {
        'materialno': 'productno',
        'matver': 'productversion',
    }
     # 测试处理
    df = process_json_route_data(
        test_json, 
        mainfield_mapper, 
        dtofield_mapper
    )

    marked_data, issue_summary = route_check_core_processor(df)
    print(marked_data)
    print(issue_summary)
