import re

from ._base import ErrorType
from .staging_models import (
    ValidationError, TransformRule,
    TMaterialStaging, TWorkcenterStaging, TMatVerStaging,
    TMatWcStaging, TMatWcBomStaging, TMoldStaging, TMatWcMoldStaging,
)
# from apps.io_api.models import (
#     TMaterial, TWorkcenter, TMatVer, TMatWc, TMatWcBom, TMold, TMatWcMold
# )
# from apps.io_api.schemas import AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom, AcceptMold, AcceptMatWcMold

from globalobjects import logger as log_config, globalconst as gc, ProjectDefaultValues as pdv

logger = log_config.get_logger(__name__)

_MATVER_PATTERN = re.compile(r'^[A-Za-z0-9\-]+$')
SYS_AUTO = "SYS_AUTO"


# ==============================================
# 业务规则校验函数（保留：有特殊外键存在校验）
# ==============================================

async def validate_material_type_e_rules(cleaner, data, staging_id):
    """物料业务规则校验：自制件必须有工艺路线、BOM和产线版本"""
    if data.get("type") != gc.EfEnum.E.value:
        return []

    errors = []
    materialno = data.get("materialno")
    if materialno:
        # 校验工艺路线存在（从缓冲表查找）
        mat_wc_exists = await TMatWcStaging.filter(materialno=materialno).exists()
        if not mat_wc_exists:
            errors.append(cleaner._create_error(
                staging_id, ErrorType.BUSINESS_RULE, 
                ["materialno", "type"],
                materialno, "自制件必须有工艺路线"
            ))
        # 校验BOM存在（从缓冲表查找）
        bom_exists = await TMatWcBomStaging.filter(productno=materialno).exists()
        if not bom_exists:
            errors.append(cleaner._create_error(
                staging_id, ErrorType.BUSINESS_RULE, 
                ["materialno", "type"],
                materialno, "自制件必须有BOM"
            ))
        # 校验产线版本存在（从缓冲表查找）
        matver_exists = await TMatVerStaging.filter(materialno=materialno).exists()
        if not matver_exists:
            if not pdv.staging_auto_matver:
                errors.append(cleaner._create_error(
                    staging_id, ErrorType.BUSINESS_RULE,
                    ["materialno", "type"],
                    materialno, "自制件必须有产线版本"
                ))
    return errors


async def auto_matver_from_refs_hook(processor, table_name: str, context: dict, stats: dict) -> dict:
    """
    批量钩子：从 t_mat_wc_staging/t_mat_wc_bom_staging 扫描产线版本组合，
    自动补充到 t_mat_ver_staging。

    触发条件：pdv.staging_auto_matver == True
    扫描范围：E 类（自制件）料号在 t_mat_wc_staging 的 (materialno, matver)
             和 t_mat_wc_bom_staging 的 (productno, matver)
    过滤规则：matver 需匹配 ^[A-Za-z0-9\\-]+$（字母、数字、杠）
    幂等性：已存在于 t_mat_ver_staging 的组合跳过
    """
    if not pdv.staging_auto_matver:
        return context

    e_materials = await TMaterialStaging.filter(type=gc.EfEnum.E.value).values("materialno")
    e_material_set = {m["materialno"] for m in e_materials if m["materialno"]}
    if not e_material_set:
        return context

    mat_wc_rows = await TMatWcStaging.filter(
        materialno__in=list(e_material_set)
    ).values("materialno", "matver")

    mat_wc_bom_rows = await TMatWcBomStaging.filter(
        productno__in=list(e_material_set)
    ).values("productno", "matver")

    needed_combos = set()
    for row in mat_wc_rows:
        mn, mv = row.get("materialno"), row.get("matver")
        if mn and mv and _MATVER_PATTERN.match(mv):
            needed_combos.add((mn, mv))
    for row in mat_wc_bom_rows:
        pn, mv = row.get("productno"), row.get("matver")
        if pn and mv and _MATVER_PATTERN.match(mv):
            needed_combos.add((pn, mv))

    if not needed_combos:
        return context

    all_materialnos = {mn for mn, _ in needed_combos}
    existing_rows = await TMatVerStaging.filter(
        materialno__in=list(all_materialnos)
    ).values("materialno", "matver")
    existing = {(r["materialno"], r["matver"]) for r in existing_rows}

    to_create = needed_combos - existing
    if not to_create:
        return context

    new_records = [
        TMatVerStaging(
            materialno=mn,
            matver=mv,
            lotfrom=pdv.MATVER_LOTFROM,
            lotto=pdv.MATVER_LOTTO,
            priority=pdv.MATVER_PRIORITY,
            _source_system=SYS_AUTO,
        )
        for mn, mv in to_create
    ]
    await TMatVerStaging.bulk_create(new_records)

    logger.info(f"auto_matver_from_refs: 从 t_mat_wc/t_mat_wc_bom 补充 {len(to_create)} 条产线版本")

    return context


async def bom_structure_check_hook(processor, table_name: str, context: dict) -> dict:
    """
    BOM结构完整性校验钩子
    使用 bomchecker 对 BOM 数据进行结构校验和单位一致性检查
    
    校验内容:
    - 循环引用检测
    - 父子同号检查
    - 孤立项目检测
    - 多父项检查
    - 单位一致性检查
    
    Args:
        processor: StagingProcessor实例
        table_name: 表名
        context: 上下文字典
    
    Returns:
        更新后的context
    """
    from apps.data_opt.utils.bomchecker import BOMChecker
    from tortoise import Tortoise
    
    conn = Tortoise.get_connection(processor.db_name)
    
    logger.info(f"[BOM校验钩子] 开始加载 {table_name} 数据")
    
    query = '''
        SELECT "_staging_id", "ProductNo", "MaterialNo", "Qty", "MatVer", "ItemNo",
               "ProductUnit", "MaterialUnit"
        FROM t_mat_wc_bom_staging 
        WHERE "_status" IN ('pending', 'relation_pass')
    '''
    result = await conn.execute_query(query)
    records = result[1] if result[1] else []
    
    if not records:
        logger.info(f"[BOM校验钩子] 无待校验数据")
        return context
    
    logger.info(f"[BOM校验钩子] 加载 {len(records)} 条数据")
    
    staging_id_map = {}
    bom_data = []
    
    for row in records:
        row_dict = dict(row)
        staging_id = row_dict['_staging_id']
        business_key = (
            str(row_dict['ProductNo'] or ''),
            str(row_dict['MaterialNo'] or ''),
            str(row_dict['MatVer'] or ''),
            str(row_dict.get('ItemNo', '') or '')
        )
        staging_id_map[business_key] = staging_id
        
        bom_data.append({
            'productno': row_dict['ProductNo'],
            'materialno': row_dict['MaterialNo'],
            'qty': row_dict['Qty'] or 0,
            'matver': row_dict['MatVer'],
            'itemno': row_dict.get('ItemNo', ''),
            'productunit': row_dict.get('ProductUnit'),
            'materialunit': row_dict.get('MaterialUnit'),
        })
    
    checker = BOMChecker(
        parent_col="productno",
        child_col="materialno",
        numerator_col="qty",
        parentversion_col="matver",
        parentunit_col="productunit",
        childunit_col="materialunit"
    )
    
    logger.info(f"[BOM校验钩子] 开始执行BOM结构校验")
    check_result = checker.start_check(bom_data)
    
    if not check_result.get('success'):
        logger.error(f"[BOM校验钩子] 校验执行失败: {check_result.get('message')}")
        context['bom_check_error'] = check_result.get('message')
        return context
    
    marked_data = check_result.get('marked_data', [])
    statistics = check_result.get('statistics', {})
    
    logger.info(f"[BOM校验钩子] 校验完成 - 总计:{statistics.get('total_records', 0)}, "
                f"错误:{statistics.get('error_records', 0)}, "
                f"警告:{statistics.get('warning_records', 0)}")
    
    batch_errors = {}
    error_count = 0
    warning_count = 0
    
    for item in marked_data:
        business_key = (
            str(item.get('productno') or ''),
            str(item.get('materialno') or ''),
            str(item.get('matver') or ''),
            str(item.get('itemno', '') or '')
        )
        staging_id = staging_id_map.get(business_key)
        
        if not staging_id:
            continue
        
        errors = item.get('E', '')
        warnings = item.get('W', '')
        
        if not errors and not warnings:
            continue
        
        batch_errors[staging_id] = []
        
        if errors:
            batch_errors[staging_id].append({
                'staging_id': staging_id,
                'error_type': 'bom_structure_error',
                'error_field': 'bom_structure',
                'error_value': None,
                'error_message': errors
            })
            error_count += 1
        
        if warnings:
            batch_errors[staging_id].append({
                'staging_id': staging_id,
                'error_type': 'bom_structure_warning',
                'error_field': 'bom_structure',
                'error_value': None,
                'error_message': warnings
            })
            warning_count += 1
    
    logger.info(f"[BOM校验钩子] 发现问题 - 错误:{error_count}条, 警告:{warning_count}条 (未写入数据库，将在后续校验中合并)")
    
    # 处理单位不一致问题
    unit_result = checker.unit_result
    unit_stats = {}
    if unit_result and unit_result.get('exec_success'):
        unit_summary = unit_result.get('summary', {})
        unit_stats = {
            'total_materials': unit_summary.get('total_unique_materials', 0),
            'unified_materials': unit_summary.get('unified_materials_count', 0),
            'problematic_materials': unit_summary.get('problematic_materials_count', 0),
            'pass_rate': unit_summary.get('pass_rate_percent', 0)
        }
        logger.info(f"[BOM校验钩子] 单位校验 - 总计:{unit_stats['total_materials']}, "
                    f"通过率:{unit_stats['pass_rate']}%")
        
        # 将单位不一致问题写入 batch_errors
        problematic_details = unit_result.get('problematic_details', [])
        for detail in problematic_details:
            material_number = detail.get('material_number', '')
            unit_distribution = detail.get('unit_distribution', {})
            material_number_lower = (material_number or '').lower()
            
            # 找到所有涉及该物料的记录
            for business_key, sid in staging_id_map.items():
                productno, materialno, matver, itemno = business_key
                if (productno or '').lower() == material_number_lower or (materialno or '').lower() == material_number_lower:
                    if sid not in batch_errors:
                        batch_errors[sid] = []
                    
                    # 避免重复添加同一物料的单位警告
                    existing_msg = [e.get('error_message', '') for e in batch_errors[sid]]
                    unit_msg = f"物料 {material_number} 单位不一致: {dict(unit_distribution)}"
                    
                    if not any('单位不一致' in msg for msg in existing_msg):
                        batch_errors[sid].append({
                            'staging_id': sid,
                            'error_type': 'unit_inconsistency',
                            'error_field': 'productunit' if (productno or '').lower() == material_number_lower else 'materialunit',
                            'error_value': str(unit_distribution),
                            'error_message': unit_msg
                        })
                        warning_count += 1
    
    context['batch_errors'] = batch_errors
    context['bom_check_result'] = {
        'total': statistics.get('total_records', 0),
        'errors': error_count,
        'warnings': warning_count,
        'unit_stats': unit_stats
    }
    
    return context


async def mat_wc_route_check_hook(processor, table_name: str, context: dict) -> dict:
    """
    工艺路线结构完整性校验钩子
    使用 RouteChecker 对工序数据进行结构校验
    
    校验内容:
    - 工序项重复检测
    - 顺序号非整数检测
    - 物料号为空检测
    - 工作中心为空检测
    - 顺序号重复检测
    - 工作中心重复检测
    
    Args:
        processor: StagingProcessor实例
        table_name: 表名
        context: 上下文字典
    
    Returns:
        更新后的context
    """
    from apps.data_opt.utils.routechecker import RouteChecker
    from tortoise import Tortoise
    
    conn = Tortoise.get_connection(processor.db_name)
    
    logger.info(f"[工序路线校验钩子] 开始加载 {table_name} 数据")
    
    query = '''
        SELECT "_staging_id", "MaterialNo", "MatVer", "ItemNo", "SortNo", "WorkCenter"
        FROM t_mat_wc_staging 
        WHERE "_status" IN ('pending', 'relation_pass')
    '''
    result = await conn.execute_query(query)
    records = result[1] if result[1] else []
    
    if not records:
        logger.info(f"[工序路线校验钩子] 无待校验数据")
        return context
    
    logger.info(f"[工序路线校验钩子] 加载 {len(records)} 条数据")
    
    staging_ids = []
    route_data = []
    
    for row in records:
        row_dict = dict(row)
        staging_ids.append(row_dict['_staging_id'])
        
        route_data.append({
            'pn': row_dict['MaterialNo'],
            'pv': row_dict['MatVer'],
            'in': row_dict.get('ItemNo', ''),
            'sn': row_dict['SortNo'],
            'wc': row_dict.get('WorkCenter', ''),
        })
    
    checker = RouteChecker(
        product_col='pn',
        productversion_col='pv',
        sortno_col='sn',
        itemno_col='in',
        workcenter_col='wc'
    )
    
    logger.info(f"[工序路线校验钩子] 开始执行工序结构校验")
    check_result = checker.start_check(route_data)
    
    if not check_result.get('success'):
        logger.error(f"[工序路线校验钩子] 校验执行失败: {check_result.get('message')}")
        context['route_check_error'] = check_result.get('message')
        return context
    
    marked_data = check_result.get('marked_data', [])
    statistics = check_result.get('statistics', {})
    
    logger.info(f"[工序路线校验钩子] 校验完成 - 总计:{statistics.get('total_records', 0)}, "
                f"错误:{statistics.get('error_records', 0)}, "
                f"警告:{statistics.get('warning_records', 0)}")
    
    batch_errors = {}
    error_count = 0
    warning_count = 0
    
    for idx, item in enumerate(marked_data):
        if idx >= len(staging_ids):
            logger.warning(f"[工序路线校验钩子] 索引越界: idx={idx}, staging_ids长度={len(staging_ids)}")
            break
        
        staging_id = staging_ids[idx]
        
        errors = item.get('E', '')
        warnings = item.get('W', '')
        
        if not errors and not warnings:
            continue
        
        batch_errors[staging_id] = []
        
        if errors:
            batch_errors[staging_id].append({
                'staging_id': staging_id,
                'error_type': 'route_structure_error',
                'error_field': 'route_structure',
                'error_value': None,
                'error_message': errors
            })
            error_count += 1
        
        if warnings:
            batch_errors[staging_id].append({
                'staging_id': staging_id,
                'error_type': 'route_structure_warning',
                'error_field': 'route_structure',
                'error_value': None,
                'error_message': warnings
            })
            warning_count += 1
    
    logger.info(f"[工序路线校验钩子] 发现问题 - 错误:{error_count}条, 警告:{warning_count}条")
    
    context['batch_errors'] = batch_errors
    context['route_check_result'] = {
        'total': statistics.get('total_records', 0),
        'errors': error_count,
        'warnings': warning_count,
        'error_counts': statistics.get('error_counts', {}),
        'warning_counts': statistics.get('warning_counts', {})
    }
    
    return context