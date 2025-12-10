import os, logging, queue
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener

global_logger = None
_listener = None

def setup_logging(log_name: str, log_filename='app.log'):
    global _listener  # 引用全局的 listener
    global global_logger  # 引用全局的 logger

    if global_logger is not None:# 如果已经配置过，则直接返回，不做任何操作
        return global_logger

    
    global_logger = logging.getLogger(log_name)
    # 防止重复添加处理器
    if global_logger.handlers:
        return global_logger

    global_logger.setLevel(logging.DEBUG)
    # 关闭日志传播，防止重复输出
    global_logger.propagate = False
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    # 创建按时间轮替的 FileHandler
    timed_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, log_filename),
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    timed_handler.suffix = "%Y%m%d"
    timed_handler.setLevel(logging.DEBUG)
    timed_handler.setFormatter(formatter)

    # 创建队列和 QueueListener
    log_queue = queue.Queue(-1)
    listener = QueueListener(log_queue, timed_handler, respect_handler_level=True)
    
    # 将 listener 赋值给全局变量
    _listener = listener

    # 创建 QueueHandler 并添加到 logger
    queue_handler = QueueHandler(log_queue)
    global_logger.addHandler(queue_handler)

    # 注意：这里不在这里启动 listener，而是在 lifespan 的启动阶段启动
    return global_logger


def close_logging():
    global _listener, global_logger
    
    # 停止并清理监听器
    if _listener is not None:
        _listener.stop()
        _listener = None
    
    # 清理logger实例和其handlers
    if global_logger is not None:
        # 移除所有handlers
        for handler in global_logger.handlers[:]:
            # 关闭handler
            if hasattr(handler, 'close'):
                handler.close()
            # 移除handler
            global_logger.removeHandler(handler)
        # 将全局logger设为None
        global_logger = None


