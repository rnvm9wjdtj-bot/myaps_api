"""
HAP 工具包

统一暴露接口，方便其他模块使用。
"""

from ._base import HapConfig, ModelType
from .models import Model
from .fields import Field, StrField, NumField, RelationField, ChoiceField, SubtableField
from .utils import (
    HapUtils, AdaptiveTimeout, EnhancedRetryStrategy, TokenBucket, DecimalEncoder, HapApiMonitor,
    StringInternPool, DataProcessingPipeline, LightweightRow, ObjectPool, ConnectionPoolWarmer, SmartBatchSizeCalculator,
    AdaptiveRateController, hap_async_timer
)
from .connection import HapConnection, AsyncHapConnection, async_upsert, async_bulk_create, async_query
from .data_objects import HapRowSet, HapQuerySet, AsyncHapQuerySet, Q

__all__ = [
    # 配置和类型
    'HapConfig',
    'ModelType',
    
    # 字段
    'Field',
    'StrField',
    'NumField',
    'RelationField',
    'ChoiceField',
    'SubtableField',
    
    # 模型
    'Model',
    
    # 工具类
    'HapUtils',
    'AdaptiveTimeout',
    'EnhancedRetryStrategy',
    'TokenBucket',
    'DecimalEncoder',
    'StringInternPool',
    'DataProcessingPipeline',
    'LightweightRow',
    'ObjectPool',
    'ConnectionPoolWarmer',
    'SmartBatchSizeCalculator',
    'AdaptiveRateController',
    'HapApiMonitor',
    'hap_async_timer',
    
    # 连接类
    'HapConnection',
    'AsyncHapConnection',
    'async_upsert',
    'async_bulk_create',
    'async_query',
    
    # 数据对象
    'Q',
    'HapRowSet',
    'HapQuerySet',
    'AsyncHapQuerySet',
]

# 版本信息
__version__ = '1.0.0'

# 模块描述
__description__ = 'HAP 工具包，提供明道云 API 的同步和异步操作'

# 使用方法
"""
使用方法示例：

1. 初始化连接
from apps.data_opt.utils.hap import HapConnection, AsyncHapConnection

# 同步连接
conn = HapConnection()

# 异步连接
async_hap = AsyncHapConnection(conn)

2. 定义模型
from apps.data_opt.utils.hap import Model, StrField, NumField, DateTimeField

class Customer(Model):
    _worksheet_id = 'your_worksheet_id'  # 明道云工作表ID
    
    # 字段定义
    name = StrField(field_name='name')  # field_name 对应明道云字段名
    age = NumField(field_name='age')
    created_at = DateTimeField(field_name='created_at')

3. 注册模型
conn.register_model(Customer)

4. 同步操作
# 查询数据
customers = conn.rows(Customer).filter(age__gt=18).order_by('-created_at').all()

# 创建数据
customer = conn.rows(Customer).create(name='张三', age=20)

# 更新数据
customer = conn.rows(Customer).get(name='张三')
if customer:
    customer.age = 21
    customer.save()

# 删除数据
conn.rows(Customer).filter(name='张三').delete()

5. 异步操作
import asyncio

async def main():
    # 异步查询
    customers = await async_hap.query(Customer).filter(age__gt=18).all()
    
    # 异步创建
    customer = await async_hap.create_row(Customer, {'name': '李四', 'age': 25})
    
    # 批量操作
    data_list = [
        {'name': '王五', 'age': 30},
        {'name': '赵六', 'age': 35}
    ]
    result = await async_hap.upsert(Customer, data_list)
    print(f"处理了 {result.count()} 条数据")

asyncio.run(main())

6. 批量操作优化（适用于大量数据）
def data_generator():
    # 生成数据的逻辑
    for i in range(1000):
        yield [{'name': f'用户{i}', 'age': 20 + i % 30}]

# 高性能批量 upsert
async def batch_upsert():
    result = await async_hap.query(Customer).upsert_from_generator(
        data_generator,
        buffer_size=500,  # 缓冲区大小
        max_concurrency=10,  # 最大并发数
        adaptive=True  # 启用自适应速率控制
    )
    print(f"批量处理了 {result} 条数据")

asyncio.run(batch_upsert())
"""

if __name__ == '__main__':
    pass