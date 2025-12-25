import os, logging, queue, time
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener

class DatePrefixRotatingFileHandler(TimedRotatingFileHandler):
    """自定义的按时间轮转的文件处理器，支持日期前缀"""
    
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
        try:
            _listener.stop()
        except AttributeError:
            # 处理listener未启动的情况
            pass
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


