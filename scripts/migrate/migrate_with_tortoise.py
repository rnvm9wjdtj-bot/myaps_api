"""
使用 Tortoise ORM 直接生成表的脚本（更可靠）
替代 aerich 迁移方案，直接调用 generate_schemas()
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from tortoise import Tortoise
from core.database import TORTOISE_ORM_CONFIG
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)

async def main():
    """主函数 - 直接生成所有表"""
    logger.info("=" * 50)
    logger.info("  Tortoise ORM - 直接生成数据库表")
    logger.info("=" * 50)
    
    try:
        # 初始化 Tortoise ORM
        logger.info("⏳ 初始化 Tortoise ORM...")
        await Tortoise.init(config=TORTOISE_ORM_CONFIG)
        
        # 直接生成所有 schema
        logger.info("⏳ 生成数据库表 (generate_schemas)...")
        await Tortoise.generate_schemas(safe=True)  # safe=True: 不删除已存在的表
        
        logger.info("✅ 所有表已生成/更新成功！")
        
        # 列出所有注册的模型
        logger.info("")
        logger.info("📋 已注册的模型:")
        # 从配置中获取模型信息
        for app_name, app_config in TORTOISE_ORM_CONFIG['apps'].items():
            logger.info(f"  - App '{app_name}':")
            models = app_config.get('models', [])
            for model_path in models:
                if model_path == 'aerich.models':
                    continue
                logger.info(f"    - {model_path}")
        
        # 关闭连接
        await Tortoise.close_connections()
        logger.info("")
        logger.info("✅ 数据库连接已关闭")
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"❌ 生成表失败: {e}")
        import traceback
        logger.error(f"堆栈信息: {traceback.format_exc()}")
        raise

if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())
