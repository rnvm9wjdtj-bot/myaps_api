import os, logging, queue, time
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener

class DatePrefixRotatingFileHandler(TimedRotatingFileHandler):
    """自定义的按时间轮转的文件处理器，支持日期前缀"""
    
    def __init__(self, *args, **kwargs):
        """初始化方法，确保编码参数被正确处理"""
        super().__init__(*args, **kwargs)
        # 确保编码参数被正确存储
        self.encoding = kwargs.get('encoding', 'utf-8')
    
    def doRollover(self):
        """重写轮转方法，实现日期前缀"""
        if self.stream:
            self.stream.close()
            self.stream = None
            
        # 获取当前时间
        current_time = int(time.time())
        
        # 计算下一次轮转的时间
        self.rolloverAt = self.computeRollover(current_time)
        
        # 处理文件名
        if self.backupCount > 0:
            # 获取原始文件名的信息
            base_dir, filename = os.path.split(self.baseFilename)
            name_without_ext, ext = os.path.splitext(filename)
            
            # 生成带日期前缀的文件名
            date_prefix = time.strftime("%Y%m%d", time.localtime(current_time))
            
            # 新的文件名格式：[日期前缀]_[原始文件名][扩展名]
            new_filename = f"{date_prefix}_{name_without_ext}{ext}"
            new_filepath = os.path.join(base_dir, new_filename)
            
            # 如果文件已存在，先删除
            if os.path.exists(new_filepath):
                os.remove(new_filepath)
            
            # 重命名当前文件
            if os.path.exists(self.baseFilename):
                os.rename(self.baseFilename, new_filepath)
        
        # 重新打开文件
        self.mode = 'a'
        self.stream = self._open()

# 存储多个logger实例和对应的listener
logger_instances = {}
listeners = {}

def setup_logging(log_name: str, log_filename='app.log'):
    """
    设置日志配置
    支持多个不同文件名的logger实例
    
    Args:
        log_name: 日志名称
        log_filename: 日志文件名
    
    Returns:
        logging.Logger: 配置好的logger实例
    """
    # 使用log_filename作为key，确保不同文件名有不同的logger
    logger_key = f"{log_name}:{log_filename}"
    
    if logger_key in logger_instances:
        return logger_instances[logger_key]

    logger = logging.getLogger(f"{log_name}_{log_filename}")
    # 防止重复添加处理器
    if logger.handlers:
        logger_instances[logger_key] = logger
        return logger

    logger.setLevel(logging.DEBUG)
    # 关闭日志传播，防止重复输出
    logger.propagate = False
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    # 创建按时间轮替的 FileHandler（支持日期前缀）
    timed_handler = DatePrefixRotatingFileHandler(
        filename=os.path.join(log_dir, log_filename),
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    timed_handler.setLevel(logging.DEBUG)
    timed_handler.setFormatter(formatter)

    # 创建队列和 QueueListener
    log_queue = queue.Queue(-1)
    listener = QueueListener(log_queue, timed_handler, respect_handler_level=True)
    
    # 存储listener
    listeners[logger_key] = listener

    # 创建 QueueHandler 并添加到 logger
    queue_handler = QueueHandler(log_queue)
    logger.addHandler(queue_handler)

    # 存储logger实例
    logger_instances[logger_key] = logger

    # 注意：这里不在这里启动 listener，而是在 lifespan 的启动阶段启动
    return logger


def start_all_listeners():
    """启动所有存储的listener"""
    for key, listener in listeners.items():
        try:
            listener.start()
            print(f"✅ 已启动日志监听器: {key}")
        except Exception as e:
            print(f"❌ 启动日志监听器失败 {key}: {e}")


def close_logging():
    """关闭所有日志系统"""
    # 停止并清理所有listener
    for key, listener in listeners.items():
        try:
            listener.stop()
        except AttributeError:
            # 处理listener未启动的情况
            pass
    listeners.clear()
    
    # 清理所有logger实例和其handlers
    for key, logger in logger_instances.items():
        # 移除所有handlers
        for handler in logger.handlers[:]:
            # 关闭handler
            if hasattr(handler, 'close'):
                handler.close()
            # 移除handler
            logger.removeHandler(handler)
    logger_instances.clear()



if __name__ == "__main__":
    """
    使用方法示例
    """
    print("=== file_timed_logger 使用方法示例 ===")
    
    # 1. 创建不同文件名的logger实例
    print("\n1. 创建不同文件名的logger实例:")
    app_logger = setup_logging("app", "app.log")
    project_logger = setup_logging("project", "project.log")
    error_logger = setup_logging("error", "error.log")
    print("   ✅ 已创建3个不同文件名的logger实例")
    
    # 2. 启动所有日志监听器
    print("\n2. 启动所有日志监听器:")
    start_all_listeners()
    
    # 3. 测试不同级别的日志
    print("\n3. 测试不同级别的日志:")
    # 测试 app.log
    app_logger.debug("app.log - DEBUG 级别的日志")
    app_logger.info("app.log - INFO 级别的日志")
    # 测试 project.log
    project_logger.warning("project.log - WARNING 级别的日志")
    project_logger.error("project.log - ERROR 级别的日志")
    # 测试 error.log
    error_logger.critical("error.log - CRITICAL 级别的日志")
    print("   ✅ 已写入测试日志到各个文件")
    
    # 4. 等待日志处理完成
    print("\n4. 等待日志处理完成...")
    import time
    time.sleep(2)
    
    # 5. 检查日志文件是否生成
    print("\n5. 检查日志文件是否生成:")
    log_dir = "logs"
    if os.path.exists(log_dir):
        log_files = [f for f in os.listdir(log_dir) if f.endswith('.log')]
        print(f"   ✅ 日志目录存在，生成的文件: {log_files}")
    else:
        print("   ❌ 日志目录不存在")
    
    # 6. 关闭日志系统
    print("\n6. 关闭日志系统:")
    close_logging()
    print("   ✅ 已关闭所有日志系统")
    
    print("\n=== 使用方法示例结束 ===")
    print("\n完整使用流程:")
    print("1. 导入: from globalobjects import file_timed_logger")
    print("2. 创建logger: logger = file_timed_logger.setup_logging(__name__, log_filename='your_log.log')")
    print("3. 启动监听器: file_timed_logger.start_all_listeners() (在应用启动时执行一次)")
    print("4. 写入日志: logger.info('日志内容')")
    print("5. 关闭日志: file_timed_logger.close_logging() (在应用关闭时执行一次)")