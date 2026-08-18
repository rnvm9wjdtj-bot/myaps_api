from contextlib import asynccontextmanager
import asyncio
import os
import sys
import time
import json
import inspect
import signal
import atexit
import tempfile
import redis
from typing import Optional, Dict, Any, Union, List
from globalobjects import logger as log_config
from globalobjects.logger import shutdown_logging
from apps.data_opt.utils.scheduler import scheduler_manager, get_scheduler_status, initialize_scheduler
from apps.data_opt.utils.binlog_listener import binlog_listener
from apps.common.utils.resource_monitor import resource_monitor
from apps.common.monitor import (
    start_db_health_checker, stop_db_health_checker,
    start_failed_operation_recovery, stop_failed_operation_recovery
)
from apps.common.monitor.log_stream_service import start_log_stream, stop_log_stream
from globalobjects import EVENT_AGGREGATOR
from core.settings import TURNON_BINLOG_LISTENER, TRUNON_SCHEDULER, MAX_EVENTS_BATCH_SIZE, BASE_DIR
from core.database import check_db_connections, warmup_connections, start_pool_monitoring, db_init_manager, ensure_sqlite_monitor_tables
from core.task_manager import get_task_manager

# ============================================================================
# 文件锁定义 - 用于 Gunicorn 多进程环境
# 使用系统临时目录（Linux 下为 /tmp，Windows 下为 %TEMP%），避免持久化目录残留旧锁
# ============================================================================

_LOCK_DIR = tempfile.gettempdir()
_BINLOG_LOCK_FILE = os.path.join(_LOCK_DIR, ".myaps_binlog.lock")
_SCHEDULER_LOCK_FILE = os.path.join(_LOCK_DIR, ".myaps_scheduler.lock")
_REDIS_CONSUMER_LOCK_FILE = os.path.join(_LOCK_DIR, ".myaps_redis_consumer.lock")
_DB_HEALTH_CHECK_LOCK_FILE = os.path.join(_LOCK_DIR, ".myaps_db_health_check.lock")
_FAILED_OP_RECOVERY_LOCK_FILE = os.path.join(_LOCK_DIR, ".myaps_failed_op_recovery.lock")
_LOG_STREAM_LOCK_FILE = os.path.join(_LOCK_DIR, ".myaps_log_stream.lock")

_LOCK_FILES: List[str] = []
_SIGNAL_HANDLERS_SET: bool = False


def _pid_is_alive(pid: int) -> bool:
    """检查进程是否存活（Linux 下通过 /proc 检测，Windows 下通过 OpenProcess，其他平台信号0检测）"""
    if sys.platform == "linux":
        try:
            return os.path.exists(f"/proc/{pid}")
        except (PermissionError, FileNotFoundError, OSError):
            return False
    if sys.platform == "win32":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    # 其他平台 fallback：信号0检测（Windows 上 os.kill(pid, 0) 会终止进程，故仅限非 Windows）
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _get_process_info(pid: int) -> Optional[Dict[str, Any]]:
    """
    获取进程信息，用于增强锁机制
    
    从 /proc 文件系统读取进程详细信息，为增强锁机制提供进程唯一标识。
    通过进程启动时间（starttime）来区分PID复用的情况。
    
    Args:
        pid: 进程ID
        
    Returns:
        包含进程信息的字典，格式为：
        {
            'pid': int,              # 进程ID
            'starttime': float,      # 进程启动时间（秒，从系统启动开始计算）
            'cmdline': str           # 进程命令行
        }
        如果无法获取进程信息，返回 None
        
    Note:
        - 仅在Linux系统上有效，非Linux系统返回None
        - 异常情况返回None，不抛出异常
    """
    if sys.platform != "linux":
        return None
    
    try:
        with open(f"/proc/{pid}/stat", 'r') as f:
            stat = f.read().split()
            starttime_ticks = int(stat[21])
            clocks_per_sec = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
            starttime = starttime_ticks / clocks_per_sec
        
        with open(f"/proc/{pid}/cmdline", 'r') as f:
            cmdline = f.read().replace('\x00', ' ').strip()
        
        return {
            'pid': pid,
            'starttime': starttime,
            'cmdline': cmdline
        }
    except (FileNotFoundError, PermissionError, ValueError, IndexError, OSError, KeyError):
        return None


def _parse_lock_file(lock_file: str) -> Union[Dict[str, Any], int, None]:
    """
    解析锁文件内容，支持新旧格式兼容
    
    优先尝试解析为JSON格式（新格式），失败则尝试解析为整数（旧格式）。
    
    Args:
        lock_file: 锁文件路径
        
    Returns:
        - Dict: JSON格式锁文件（新格式）
        - int: 整数格式锁文件（旧格式，仅包含PID）
        - None: 文件不存在、损坏或无法解析
        
    Note:
        新格式锁文件包含完整的进程标识信息：
        {
            "pid": int,
            "starttime": float,
            "cmdline": str,
            "worker_id": str,
            "timestamp": float
        }
        
        旧格式锁文件仅包含PID（整数）
    """
    try:
        with open(lock_file, 'r') as f:
            content = f.read().strip()
        
        if not content:
            return None
        
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            try:
                return int(content)
            except ValueError:
                return None
    except (FileNotFoundError, OSError):
        return None


def _write_lock_file(fd: int) -> bool:
    """
    写入增强格式的锁文件
    
    将当前进程的完整标识信息写入锁文件，用于PID复用检测。
    
    Args:
        fd: 文件描述符（已通过 os.open 打开）
        
    Returns:
        True: 写入成功
        False: 写入失败（无法获取进程信息或写入异常）
        
    Note:
        锁文件格式为JSON，包含以下字段：
        - pid: 进程ID
        - starttime: 进程启动时间（秒）
        - cmdline: 进程命令行
        - worker_id: Gunicorn Worker ID（如果存在）
        - timestamp: 锁创建时间戳
    """
    try:
        current_pid = os.getpid()
        process_info = _get_process_info(current_pid)
        
        if not process_info:
            return False
        
        lock_data = {
            'pid': current_pid,
            'starttime': process_info['starttime'],
            'cmdline': process_info['cmdline'],
            'worker_id': os.environ.get('GUNICORN_WORKER_ID', str(current_pid)),
            'timestamp': time.time()
        }
        
        json_str = json.dumps(lock_data, ensure_ascii=False)
        os.write(fd, json_str.encode('utf-8'))
        os.fsync(fd)
        
        return True
    except (OSError, TypeError):
        return False


def _try_acquire_lock_simple(lock_file: str) -> bool:
    """
    简单锁获取函数（降级方案）
    
    当无法获取进程信息时使用简单锁机制，仅检查PID是否存在。
    
    Args:
        lock_file: 锁文件路径
        
    Returns:
        True: 锁获取成功
        False: 锁已被占用或获取失败
    """
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, 'w') as f:
            f.write(str(os.getpid()))
        register_lock_file(lock_file)
        log_config.info(f"✅ 简单锁获取成功: {lock_file}, PID={os.getpid()}")
        return True
    except FileExistsError:
        try:
            with open(lock_file, 'r') as f:
                stored_pid_str = f.read().strip()
            if stored_pid_str:
                stored_pid = int(stored_pid_str)
                if not _pid_is_alive(stored_pid):
                    os.unlink(lock_file)
                    fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                    with os.fdopen(fd, 'w') as f:
                        f.write(str(os.getpid()))
                    register_lock_file(lock_file)
                    log_config.info(f"✅ 简单锁获取成功（清理废弃锁）: {lock_file}, PID={os.getpid()}")
                    return True
        except (ValueError, OSError, FileNotFoundError):
            pass
        log_config.info(f"ℹ️ 简单锁已被占用: {lock_file}")
        return False
    except Exception as e:
        log_config.error(f"❌ 简单锁获取失败: {lock_file}, 错误: {e}")
        return False


def _try_acquire_lock_enhanced(lock_file: str) -> bool:
    """
    增强的锁获取函数
    
    通过进程启动时间检测PID复用，支持新旧格式锁文件兼容。
    
    Args:
        lock_file: 锁文件路径
        
    Returns:
        True: 锁获取成功
        False: 锁已被占用或获取失败
        
    Note:
        核心逻辑：
        1. 尝试创建锁文件，成功则写入增强格式数据
        2. 锁文件存在时，解析并判断：
           - JSON格式（新）：比较starttime，检测PID复用
           - 整数格式（旧）：检查PID是否存在
           - 损坏：清理并重试
        3. 无法获取进程信息时降级到简单锁机制
    """
    current_pid = os.getpid()
    current_info = _get_process_info(current_pid)
    
    if not current_info:
        log_config.debug(f"⚠️ 无法获取进程信息，降级到简单锁机制: {lock_file}")
        return _try_acquire_lock_simple(lock_file)
    
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        if _write_lock_file(fd):
            os.close(fd)
            register_lock_file(lock_file)
            log_config.info(f"✅ 增强锁获取成功: {lock_file}, PID={current_pid}")
            return True
        else:
            os.close(fd)
            log_config.warning(f"⚠️ 增强锁写入失败，降级到简单锁: {lock_file}")
            return _try_acquire_lock_simple(lock_file)
    except FileExistsError:
        stored_data = _parse_lock_file(lock_file)
        
        if stored_data is None:
            log_config.warning(f"⚠️ 锁文件损坏，清理并重试: {lock_file}")
            try:
                os.unlink(lock_file)
                fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                if _write_lock_file(fd):
                    os.close(fd)
                    register_lock_file(lock_file)
                    log_config.info(f"✅ 增强锁获取成功（清理损坏锁）: {lock_file}, PID={current_pid}")
                    return True
                else:
                    os.close(fd)
                    return False
            except Exception as e:
                log_config.error(f"❌ 清理损坏锁失败: {lock_file}, 错误: {e}")
                return False
        
        if isinstance(stored_data, dict):
            stored_pid = stored_data.get('pid')
            stored_starttime = stored_data.get('starttime')
            
            if stored_pid == current_pid:
                if stored_starttime is not None and abs(current_info['starttime'] - stored_starttime) < 1.0:
                    log_config.info(f"ℹ️ 增强锁已被当前进程持有: {lock_file}, PID={current_pid}")
                    return False
                else:
                    log_config.warning(f"⚠️ 检测到PID复用，清理废弃锁: {lock_file}, 旧starttime={stored_starttime}, 新starttime={current_info['starttime']}")
                    try:
                        os.unlink(lock_file)
                        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                        if _write_lock_file(fd):
                            os.close(fd)
                            register_lock_file(lock_file)
                            log_config.info(f"✅ 增强锁获取成功（清理PID复用锁）: {lock_file}, PID={current_pid}")
                            return True
                        else:
                            os.close(fd)
                            return False
                    except Exception as e:
                        log_config.error(f"❌ 清理PID复用锁失败: {lock_file}, 错误: {e}")
                        return False
            else:
                if not _pid_is_alive(stored_pid):
                    log_config.warning(f"⚠️ 检测到废弃锁（进程已终止），清理: {lock_file}, PID={stored_pid}")
                    try:
                        os.unlink(lock_file)
                        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                        if _write_lock_file(fd):
                            os.close(fd)
                            register_lock_file(lock_file)
                            log_config.info(f"✅ 增强锁获取成功（清理废弃锁）: {lock_file}, PID={current_pid}")
                            return True
                        else:
                            os.close(fd)
                            return False
                    except Exception as e:
                        log_config.error(f"❌ 清理废弃锁失败: {lock_file}, 错误: {e}")
                        return False
                else:
                    log_config.info(f"ℹ️ 增强锁已被其他进程持有: {lock_file}, PID={stored_pid}")
                    return False
        
        elif isinstance(stored_data, int):
            stored_pid = stored_data
            if not _pid_is_alive(stored_pid):
                log_config.warning(f"⚠️ 检测到旧格式废弃锁，清理: {lock_file}, PID={stored_pid}")
                try:
                    os.unlink(lock_file)
                    fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                    if _write_lock_file(fd):
                        os.close(fd)
                        register_lock_file(lock_file)
                        log_config.info(f"✅ 增强锁获取成功（清理旧格式废弃锁）: {lock_file}, PID={current_pid}")
                        return True
                    else:
                        os.close(fd)
                        return False
                except Exception as e:
                    log_config.error(f"❌ 清理旧格式废弃锁失败: {lock_file}, 错误: {e}")
                    return False
            else:
                log_config.info(f"ℹ️ 旧格式锁已被其他进程持有: {lock_file}, PID={stored_pid}")
                return False
        
        return False
    except Exception as e:
        log_config.error(f"❌ 增强锁获取失败: {lock_file}, 错误: {e}")
        return False


def _try_acquire_lock(lock_file: str) -> bool:
    """
    通用的文件锁获取函数（增强版）
    
    使用增强锁机制，通过进程启动时间检测PID复用。
    如果无法获取进程信息，自动降级到简单锁机制。
    
    Args:
        lock_file: 锁文件路径
        
    Returns:
        True: 锁获取成功
        False: 锁已被占用或获取失败
    """
    return _try_acquire_lock_enhanced(lock_file)


def register_lock_file(lock_file: str) -> None:
    """
    注册锁文件，用于进程退出时自动清理
    
    Args:
        lock_file: 锁文件路径
    """
    global _LOCK_FILES
    if lock_file not in _LOCK_FILES:
        _LOCK_FILES.append(lock_file)
        log_config.debug(f"📝 注册锁文件: {lock_file}")


def _cleanup_lock_files() -> None:
    """
    清理当前进程持有的所有锁文件
    
    在进程退出时自动调用，确保锁文件不会残留。
    """
    global _LOCK_FILES
    current_pid = os.getpid()
    
    cleaned_count = 0
    for lock_file in _LOCK_FILES:
        try:
            stored_data = _parse_lock_file(lock_file)
            
            should_delete = False
            if isinstance(stored_data, dict):
                if stored_data.get('pid') == current_pid:
                    should_delete = True
            elif isinstance(stored_data, int):
                if stored_data == current_pid:
                    should_delete = True
            
            if should_delete:
                os.unlink(lock_file)
                cleaned_count += 1
                log_config.info(f"🧹 清理锁文件: {lock_file}")
        except (FileNotFoundError, PermissionError, OSError):
            pass
        except Exception as e:
            log_config.warning(f"⚠️ 清理锁文件失败: {lock_file}, 错误: {e}")
    
    _LOCK_FILES.clear()
    if cleaned_count > 0:
        log_config.info(f"✅ 已清理 {cleaned_count} 个锁文件")


def _setup_signal_handlers() -> None:
    """
    设置信号处理函数，确保进程退出时清理锁文件
    
    捕获 SIGTERM、SIGINT、SIGABRT 信号，在进程终止前清理锁文件。
    """
    global _SIGNAL_HANDLERS_SET
    
    if _SIGNAL_HANDLERS_SET:
        return
    
    def _signal_handler(signum, frame):
        try:
            _cleanup_lock_files()
            log_config.info(f"📤 收到信号 {signum}，已清理锁文件")
        except Exception as e:
            log_config.error(f"❌ 信号处理失败: {e}")
        finally:
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
    
    for sig in [signal.SIGTERM, signal.SIGINT, signal.SIGABRT]:
        try:
            signal.signal(sig, _signal_handler)
        except (ValueError, OSError):
            pass
    
    atexit.register(_cleanup_lock_files)
    _SIGNAL_HANDLERS_SET = True
    log_config.info("✅ 信号处理函数已注册")


def _try_acquire_binlog_lock() -> bool:
    """尝试获取 Binlog 监听器的文件锁"""
    return _try_acquire_lock(_BINLOG_LOCK_FILE)


def _try_acquire_scheduler_lock() -> bool:
    """尝试获取调度器的文件锁"""
    return _try_acquire_lock(_SCHEDULER_LOCK_FILE)


def _try_acquire_redis_consumer_lock() -> bool:
    """尝试获取 Redis 消费者的文件锁"""
    return _try_acquire_lock(_REDIS_CONSUMER_LOCK_FILE)


def _try_acquire_db_health_check_lock() -> bool:
    """尝试获取数据库健康检查器的文件锁"""
    return _try_acquire_lock(_DB_HEALTH_CHECK_LOCK_FILE)


def _try_acquire_failed_op_recovery_lock() -> bool:
    """尝试获取失败操作恢复管理器的文件锁"""
    return _try_acquire_lock(_FAILED_OP_RECOVERY_LOCK_FILE)


def _try_acquire_log_stream_lock() -> bool:
    """尝试获取实时日志流服务的文件锁"""
    return _try_acquire_lock(_LOG_STREAM_LOCK_FILE)


@asynccontextmanager
async def lifespan(app):
    """应用生命周期管理器"""
    _setup_signal_handlers()
    
    # 在 Gunicorn 环境中，只在 worker 进程中初始化
    # 通过检查进程命令行判断是否在 worker 进程中
    import sys
    gunicorn_running = os.environ.get('GUNICORN_RUNNING') == 'true'
    
    # 如果没有设置环境变量，检查进程命令行
    if not gunicorn_running:
        # 检查是否在 Gunicorn 环境中
        if 'gunicorn' in sys.modules:
            # 检查当前进程是否是 worker 进程
            # Worker 进程的父进程应该是 gunicorn master
            parent_pid = os.getppid()
            try:
                if sys.platform == "linux":
                    with open(f'/proc/{parent_pid}/cmdline', 'r') as f:
                        parent_cmdline = f.read()
                        if 'gunicorn' in parent_cmdline:
                            # 父进程是 gunicorn master，说明当前是 worker 进程
                            gunicorn_running = True
                            os.environ['GUNICORN_RUNNING'] = 'true'
                            os.environ['GUNICORN_WORKER_PID'] = str(os.getpid())
                # 非 Linux（如 Windows）不依赖 /proc 检测；gunicorn 本身不支持 Windows，由 GUNICORN_RUNNING 环境变量控制
            except:
                pass
    
    # 如果是 Gunicorn master 进程（gunicorn 模块已加载但不是 worker），跳过初始化
    if not gunicorn_running and 'gunicorn' in sys.modules:
        yield
        return
    
    from globalobjects.logger.lifespan import initialize_logging
    await initialize_logging()

    
    main_loop = asyncio.get_running_loop()
    scheduler_manager.set_main_loop(main_loop)
    log_config.info(f"已将主应用事件循环传递给调度器: {main_loop}")
    
    from core.database import validate_database_config
    from tortoise import Tortoise
    
    try:
        validate_database_config()
    except Exception as e:
        log_config.error(f"❌ 数据库配置验证失败: {e}")
        raise
    
    # register_tortoise已经通过_merge_lifespan_context确保Tortoise先初始化
    # 这里只需检查状态并等待连接建立完成
    max_wait = 30.0
    start_wait = time.time()
    
    while not Tortoise._inited:
        elapsed = time.time() - start_wait
        if elapsed > max_wait:
            error_msg = f"Tortoise ORM 初始化超时（{elapsed:.1f}秒）"
            log_config.error(f"❌ {error_msg}")
            raise RuntimeError(error_msg)
        log_config.debug(f"⏳ 等待 Tortoise ORM 初始化... ({elapsed:.1f}s)")
        await asyncio.sleep(0.1)
    
    elapsed = time.time() - start_wait
    log_config.info(f"✅ Tortoise ORM 已初始化（等待{elapsed:.2f}秒）")
    
    # 标记初始化完成
    db_init_manager.mark_initialized()
    
    log_config.set_db_initialized(True)
    log_config.info("✅ 日志数据库写入已启用")
    
    log_config.info("开始预热数据库连接...")
    try:
        await asyncio.wait_for(warmup_connections(), timeout=60)

    except asyncio.TimeoutError:
        log_config.warning("⚠️ 数据库连接预热超时，继续启动其他服务")
    except Exception as e:
        log_config.error(f"❌ 数据库连接预热失败: {e}")

    log_config.info("检查 SQLite 监控表...")
    try:
        tables_ready = await asyncio.wait_for(ensure_sqlite_monitor_tables(), timeout=30)
        if tables_ready:
            log_config.info("✅ SQLite 监控表检查完成")
        else:
            log_config.warning("⚠️ SQLite 监控表检查未通过，部分功能可能受影响")
    except asyncio.TimeoutError:
        log_config.warning("⚠️ SQLite 监控表检查超时")
    except Exception as e:
        log_config.error(f"❌ SQLite 监控表检查异常: {e}")

    log_config.info("开始启动资源监控...")
    resource_monitor.start_monitoring(interval=30)
    log_config.info("系统资源监控已启动")
    
    log_config.info("等待服务器完全就绪...")
    await asyncio.sleep(1)
    log_config.info("服务器已就绪")
    
    if TURNON_BINLOG_LISTENER:
        if os.environ.get('GUNICORN_RUNNING') != 'true':
            # 非 Gunicorn 环境（如 dev_run.bat 的 uvicorn 直启）直接启动
            binlog_listener.start_monitoring()
            log_config.info("MySQL Binlog监控已启动")
        else:
            # Gunicorn 环境：使用文件锁确保只有一个 Worker 启动监听器
            worker_id = os.environ.get('GUNICORN_WORKER_ID', '?')
            if _try_acquire_binlog_lock():
                binlog_listener.start_monitoring()
                log_config.info(f"✅ Gunicorn Worker {worker_id}：通过文件锁获取权限，Binlog 监控已启动")
            else:
                log_config.info(f"ℹ️ Gunicorn Worker {worker_id}：Binlog 监控已在其他 Worker 中运行，跳过")
    else:
        log_config.warning("⚠️ MySQL Binlog监控未启动")
    
    # 延迟启动定时任务，确保服务器完全就绪
    if TRUNON_SCHEDULER:
        log_config.info("准备启动定时任务...")
        await asyncio.sleep(1)  # 减少等待时间
        
        if os.environ.get('GUNICORN_RUNNING') != 'true':
            # 非 Gunicorn 环境（如 dev_run.bat 的 uvicorn 直启）直接启动
            initialize_scheduler()
            log_config.info("✅ 定时任务系统已启动")
        else:
            # Gunicorn 环境：使用文件锁确保只有一个 Worker 启动调度器
            worker_id = os.environ.get('GUNICORN_WORKER_ID', '?')
            if _try_acquire_scheduler_lock():
                initialize_scheduler()
                log_config.info(f"✅ Gunicorn Worker {worker_id}：通过文件锁获取权限，定时任务已启动")
            else:
                log_config.info(f"ℹ️ Gunicorn Worker {worker_id}：定时任务已在其他 Worker 中运行，跳过")
    else:
        log_config.warning("⚠️ 定时任务初始化被跳过，因为 TRUNON_SCHEDULER=false")
    
    log_config.info("🔹 进入数据库连接检查任务设置阶段...")
    
    # 设置定期检查数据库连接的任务（从原startup_event迁移）
    log_config.info("🔹 定义 schedule_db_checks 函数...")
    async def schedule_db_checks():
        """定期执行数据库连接检查"""
        log_config.info("🔍 数据库连接检查任务开始执行")
        while True:
            try:
                log_config.debug("🔍 开始执行 check_db_connections...")
                # 添加超时保护
                await asyncio.wait_for(check_db_connections(), timeout=30)
                log_config.debug("🔍 check_db_connections 执行完成")
            except asyncio.TimeoutError:
                log_config.warning("⚠️ check_db_connections 执行超时")
            except Exception as e:
                log_config.error(f"❌ check_db_connections 执行失败: {e}")
            # 每300秒（5分钟）检查一次
            await asyncio.sleep(300)

    log_config.info("🔹 schedule_db_checks 函数定义完成")
    
    # 启动数据库连接检查任务（从原startup_event迁移）
    log_config.info("启动数据库连接检查任务...")
    task_manager = get_task_manager()
    db_check_task = task_manager.create_and_register(
        "db_check_task", 
        schedule_db_checks()
    )
    log_config.info("数据库连接检查任务已启动")
    
    # 启动连接池监控任务
    log_config.info("启动连接池监控任务...")
    pool_monitor_task = task_manager.create_and_register(
        "pool_monitor_task",
        start_pool_monitoring()
    )
    log_config.info("连接池监控任务已启动")
    
    # 启动日志数据库批次刷新任务
    async def schedule_log_db_flush():
        """定期刷新日志数据库批次"""
        from globalobjects.logger.core import SmartLogger
        logger_instance = SmartLogger._instance
        while True:
            try:
                await asyncio.sleep(5)
                if logger_instance and logger_instance._database_handler:
                    handler = logger_instance._database_handler
                    batch_size = len(handler._batch)
                    if batch_size > 0:
                        await handler.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                pass
    
    log_config.info("启动日志数据库批次刷新任务...")
    log_db_flush_task = task_manager.create_and_register(
        "log_db_flush_task",
        schedule_log_db_flush()
    )
    log_config.info("日志数据库批次刷新任务已启动")

    # 启动数据库健康检查器（独立后台任务，不依赖前端访问）
    log_config.info("启动数据库健康检查器...")
    if os.environ.get('GUNICORN_RUNNING') != 'true':
        # 非 Gunicorn 环境直接启动
        try:
            await asyncio.wait_for(start_db_health_checker(), timeout=30)
            log_config.info("✅ 数据库健康检查器已启动")
        except asyncio.TimeoutError:
            log_config.warning("⚠️ 数据库健康检查器启动超时")
        except Exception as e:
            log_config.error(f"❌ 数据库健康检查器启动失败: {e}")
    else:
        # Gunicorn 环境：使用文件锁确保只有一个 Worker 启动
        worker_id = os.environ.get('GUNICORN_WORKER_ID', '?')
        if _try_acquire_db_health_check_lock():
            try:
                await asyncio.wait_for(start_db_health_checker(), timeout=30)
                log_config.info(f"✅ Gunicorn Worker {worker_id}：通过文件锁获取权限，数据库健康检查器已启动")
            except asyncio.TimeoutError:
                log_config.warning(f"⚠️ Gunicorn Worker {worker_id}：数据库健康检查器启动超时")
            except Exception as e:
                log_config.error(f"❌ Gunicorn Worker {worker_id}：数据库健康检查器启动失败: {e}")
        else:
            log_config.info(f"ℹ️ Gunicorn Worker {worker_id}：数据库健康检查器已在其他 Worker 中运行，跳过")

    # 启动失败操作恢复管理器（后台自动重试失败的数据库操作）
    log_config.info("启动失败操作恢复管理器...")
    if os.environ.get('GUNICORN_RUNNING') != 'true':
        # 非 Gunicorn 环境直接启动
        try:
            await asyncio.wait_for(start_failed_operation_recovery(), timeout=30)
            log_config.info("✅ 失败操作恢复管理器已启动")
        except asyncio.TimeoutError:
            log_config.warning("⚠️ 失败操作恢复管理器启动超时")
        except Exception as e:
            log_config.error(f"❌ 失败操作恢复管理器启动失败: {e}")
    else:
        # Gunicorn 环境：使用文件锁确保只有一个 Worker 启动
        worker_id = os.environ.get('GUNICORN_WORKER_ID', '?')
        if _try_acquire_failed_op_recovery_lock():
            try:
                await asyncio.wait_for(start_failed_operation_recovery(), timeout=30)
                log_config.info(f"✅ Gunicorn Worker {worker_id}：通过文件锁获取权限，失败操作恢复管理器已启动")
            except asyncio.TimeoutError:
                log_config.warning(f"⚠️ Gunicorn Worker {worker_id}：失败操作恢复管理器启动超时")
            except Exception as e:
                log_config.error(f"❌ Gunicorn Worker {worker_id}：失败操作恢复管理器启动失败: {e}")
        else:
            log_config.info(f"ℹ️ Gunicorn Worker {worker_id}：失败操作恢复管理器已在其他 Worker 中运行，跳过")

    # 启动实时日志流服务
    log_config.info("启动实时日志流服务...")
    # 每个 Worker 都启动日志流服务，因为 SSE 连接可能被路由到任何 Worker
    try:
        await asyncio.wait_for(start_log_stream(), timeout=30)
        if os.environ.get('GUNICORN_RUNNING') == 'true':
            worker_id = os.environ.get('GUNICORN_WORKER_ID', '?')
            log_config.info(f"✅ Gunicorn Worker {worker_id}：实时日志流服务已启动")
        else:
            log_config.info("✅ 实时日志流服务已启动")
    except asyncio.TimeoutError:
        if os.environ.get('GUNICORN_RUNNING') == 'true':
            worker_id = os.environ.get('GUNICORN_WORKER_ID', '?')
            log_config.warning(f"⚠️ Gunicorn Worker {worker_id}：实时日志流服务启动超时")
        else:
            log_config.warning("⚠️ 实时日志流服务启动超时")
    except Exception as e:
        if os.environ.get('GUNICORN_RUNNING') == 'true':
            worker_id = os.environ.get('GUNICORN_WORKER_ID', '?')
            log_config.error(f"❌ Gunicorn Worker {worker_id}：实时日志流服务启动失败: {e}")
        else:
            log_config.error(f"❌ 实时日志流服务启动失败: {e}")

    # 启动 Redis 健康检查任务
    async def schedule_redis_checks():
        """定期执行 Redis 连接检查"""
        # 系统启动阶段延迟执行，避免与其他服务竞争资源
        await asyncio.sleep(10)
        
        while True:
            try:
                from apps.common.utils.redis_pool_manager import get_redis_pool_manager
                pool_manager = get_redis_pool_manager()
                is_healthy = pool_manager.is_healthy()
                if is_healthy:
                    log_config.debug("Redis 连接健康")
                else:
                    log_config.warning("Redis 连接不健康，尝试重新初始化")
                    pool_manager._init_pool()
                
                # 检查缓冲大小
                buffer_size = pool_manager.get_buffer_size()
                if buffer_size > 0:
                    log_config.info(f"Redis 本地缓冲中有 {buffer_size} 个事件")
                    # 尝试刷新缓冲
                    flushed = pool_manager.flush_buffer()
                    if flushed > 0:
                        log_config.info(f"成功刷新 {flushed} 个事件到 Redis")
                
                # 获取监控指标并检查是否需要告警
                metrics = pool_manager.get_monitoring_metrics()
                if metrics.get('needs_alert', False):
                    alerts = metrics.get('alerts', [])
                    for alert in alerts:
                        log_config.warning(f"Redis 监控告警: {alert}")
                    # 这里可以添加告警通知逻辑，如发送邮件、短信等
            except Exception as e:
                log_config.error(f"Redis 健康检查失败: {e}")
            
            # 每90秒检查一次，与数据库检查时间错开
            await asyncio.sleep(90)

    # 创建 Redis 健康检查任务
    redis_check_task = task_manager.create_and_register(
        "redis_check_task",
        schedule_redis_checks()
    )
    log_config.info("Redis 健康检查任务已启动")

    # 启动 Redis 消息消费者（处理来自数据库监听器的事件）
    async def start_redis_consumer():
        """启动 Redis 消息消费者，处理来自数据库监听器的事件"""
        try:
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
            loop = asyncio.get_event_loop()

            # 在线程池中获取连接池管理器
            def get_pool_manager():
                from apps.common.utils.redis_pool_manager import get_redis_pool_manager
                return get_redis_pool_manager()

            pool_manager = await loop.run_in_executor(executor, get_pool_manager)

            # 在线程池中获取 Redis 客户端
            def get_redis_client():
                return pool_manager.get_client()

            redis_client = await loop.run_in_executor(executor, get_redis_client)
            if redis_client is None:
                log_config.error("Redis 连接池获取失败，Redis 消费者无法启动")
                return

            log_config.info(f"Redis 连接已建立，等待事件...")

            while True:
                try:
                    events = []
                    for _ in range(MAX_EVENTS_BATCH_SIZE):
                        # 在线程池中执行 blpop 操作
                        def blpop():
                            return redis_client.blpop('db_events', timeout=1)

                        result = await loop.run_in_executor(executor, blpop)
                        if result:
                            events.append(result)
                        else:
                            break

                    for result in events:
                        _, message = result
                        event_data = json.loads(message.decode('utf-8'))
                        event_type = event_data.get('event_type')
                        data = event_data.get('data')
                        log_config.info(f"从消息队列接收到事件: {event_type}")
                        asyncio.create_task(handle_redis_event(event_type, data))
                except (redis.ConnectionError, redis.TimeoutError) as e:
                    log_config.warning(f"Redis 连接断开或超时，尝试重新获取连接: {e}")
                    await asyncio.sleep(1)
                    redis_client = await loop.run_in_executor(executor, get_redis_client)
                    if redis_client is None:
                        log_config.error("Redis 连接获取失败")
                        break
                except Exception as e:
                    log_config.error(f"Redis 消费者处理事件时出错: {e}")
                    await asyncio.sleep(1)
        except Exception as e:
            log_config.error(f"Redis 消费者启动失败: {e}")


    async def handle_redis_event(event_type: str, event_data):
        """处理从 Redis 消息队列接收的事件"""
        log_config.info(f"开始处理事件: {event_type}")
        try:
            import importlib
            import concurrent.futures
            PROJECT_DIR_VALUE = os.getenv('PROJECT_DIR')
            if not PROJECT_DIR_VALUE:
                log_config.warning("PROJECT_DIR 环境变量未设置，无法处理 Redis 事件")
                return
            
            project_module = importlib.import_module(f'project_files.{PROJECT_DIR_VALUE}.client')
            event_handler_name = f"batch_handle_{event_type}"
            event_handler = getattr(project_module, event_handler_name, None)
            
            if event_handler:
                log_config.info(f"找到事件处理器: {event_handler_name}")
                # 创建独立的线程池，避免阻塞主事件循环
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    if inspect.iscoroutinefunction(event_handler):
                        # 对于协程函数，在事件循环中执行
                        await event_handler(event_data)
                    else:
                        # 对于同步函数，在线程池中执行
                        await loop.run_in_executor(executor, event_handler, event_data)
                log_config.info(f"事件处理成功: {event_type}")
            else:
                log_config.debug(f"⚠️ 未找到事件处理器: {event_handler_name}")
        except Exception as e:
            log_config.error(f"处理 Redis 事件 {event_type} 时出错: {e}")

    async def cleanup_expired_events():
        """定期清理过期事件"""
        try:
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            loop = asyncio.get_event_loop()

            # 在线程池中获取连接池管理器
            def get_pool_manager():
                from apps.common.utils.redis_pool_manager import get_redis_pool_manager
                return get_redis_pool_manager()

            pool_manager = await loop.run_in_executor(executor, get_pool_manager)
            log_config.info("Redis 事件清理任务已启动，每小时清理一次过期事件")

            while True:
                try:
                    # 在线程池中获取 Redis 客户端
                    def get_redis_client():
                        return pool_manager.get_client()

                    redis_client = await loop.run_in_executor(executor, get_redis_client)
                    if redis_client is None:
                        await asyncio.sleep(60)
                        continue

                    # 在线程池中获取列表长度
                    def get_list_length():
                        return redis_client.llen('db_events')

                    length = await loop.run_in_executor(executor, get_list_length)
                    if length > 0:
                        log_config.info(f"开始清理过期事件，当前队列长度: {length}")
                        processed_count = 0
                        expired_count = 0

                        for _ in range(min(length, 1000)):
                            # 在线程池中执行 rpop 操作
                            def rpop():
                                return redis_client.rpop('db_events')

                            event_data = await loop.run_in_executor(executor, rpop)
                            if event_data:
                                processed_count += 1
                                try:
                                    event = json.loads(event_data.decode('utf-8'))
                                    event_timestamp = event.get('timestamp', 0)
                                    if time.time() - event_timestamp <= 86400:
                                        # 在线程池中执行 lpush 操作
                                        def lpush():
                                            return redis_client.lpush('db_events', event_data)
                                        await loop.run_in_executor(executor, lpush)
                                    else:
                                        expired_count += 1
                                except Exception as e:
                                    log_config.debug(f"解析事件失败，跳过: {e}")
                                    expired_count += 1

                        log_config.info(f"事件清理完成，处理了 {processed_count} 个事件，清理了 {expired_count} 个过期事件")
                except (redis.ConnectionError, redis.TimeoutError) as e:
                    log_config.warning(f"Redis 连接断开或超时: {e}")
                    await asyncio.sleep(10)
                except Exception as e:
                    log_config.error(f"清理过期事件失败: {e}")

                await asyncio.sleep(3600)
        except Exception as e:
            log_config.error(f"Redis 事件清理任务启动失败: {e}")

    # 启动 Redis 消息消费者（处理来自数据库监听器的事件）
    if os.environ.get('GUNICORN_RUNNING') != 'true':
        # 非 Gunicorn 环境直接启动
        task_manager.create_and_register(
            "redis_consumer_task",
            start_redis_consumer()
        )
        log_config.info("✅ Redis 消息消费者已启动")
    else:
        # Gunicorn 环境：使用文件锁确保只有一个 Worker 启动
        worker_id = os.environ.get('GUNICORN_WORKER_ID', '?')
        if _try_acquire_redis_consumer_lock():
            task_manager.create_and_register(
                "redis_consumer_task",
                start_redis_consumer()
            )
            log_config.info(f"✅ Gunicorn Worker {worker_id}：通过文件锁获取权限，Redis 消息消费者已启动")
        else:
            log_config.info(f"ℹ️ Gunicorn Worker {worker_id}：Redis 消息消费者已在其他 Worker 中运行，跳过")
    
    # 启动 Redis 事件清理任务
    task_manager.create_and_register(
        "redis_cleanup_task",
        cleanup_expired_events()
    )
    log_config.info("Redis 事件清理任务已启动")

    # 等待一段时间，确保所有服务正常启动
    await asyncio.sleep(1)
    log_config.info("==================应用启动完成，开始运行==================")
    
    yield  # 应用运行期间
    
    # ============ 应用关闭阶段 ============
    # 关闭顺序：任务 -> 服务 -> 资源
    log_config.info("==================应用开始关闭==================")
    
    # 阶段1: 取消所有后台任务（优先执行）
    log_config.info("【阶段1】取消所有后台任务...")
    task_manager = get_task_manager()
    await task_manager.cancel_all(timeout=10.0)
    log_config.info("✅ 所有后台任务已取消")
    
    # 阶段2: 停止各服务和监控器
    log_config.info("【阶段2】停止服务和监控器...")
    
    # 2.1 停止实时日志流服务
    log_config.info("停止实时日志流服务...")
    await stop_log_stream()
    log_config.info("✅ 实时日志流服务已停止")
    
    # 2.2 停止数据库健康检查器
    log_config.info("停止数据库健康检查器...")
    await stop_db_health_checker()
    log_config.info("✅ 数据库健康检查器已停止")
    
    # 2.3 停止失败操作恢复管理器
    log_config.info("停止失败操作恢复管理器...")
    await stop_failed_operation_recovery()
    log_config.info("✅ 失败操作恢复管理器已停止")
    
    # 2.4 停止 MySQL Binlog 监控
    if TURNON_BINLOG_LISTENER:
        # 非 Gunicorn 环境下停止监听；Gunicorn 环境由文件锁控制
        if os.environ.get('GUNICORN_RUNNING') != 'true':
            log_config.info("停止 MySQL Binlog 监控...")
            binlog_listener.stop_monitoring()
            log_config.info("✅ MySQL Binlog监控已停止")
        else:
            worker_id = os.environ.get('GUNICORN_WORKER_ID', '?')
            # Gunicorn 环境：只有持有文件锁的 Worker 才停止监听器
            is_owner = False
            if os.path.exists(_BINLOG_LOCK_FILE):
                try:
                    with open(_BINLOG_LOCK_FILE, 'r') as f:
                        started_pid = f.read().strip()
                    is_owner = (started_pid == str(os.getpid()))
                except (FileNotFoundError, OSError):
                    pass

            if is_owner:
                log_config.info(f"停止 MySQL Binlog 监控（Worker {worker_id} 持有锁）...")
                binlog_listener.stop_monitoring()
                try:
                    os.unlink(_BINLOG_LOCK_FILE)
                    log_config.info(f"✅ 已清除 Binlog 锁文件（Worker {worker_id}）")
                except FileNotFoundError:
                    pass
                log_config.info("✅ MySQL Binlog监控已停止")
            else:
                log_config.info(f"ℹ️ Gunicorn Worker {worker_id}：非锁持有者，跳过停止 Binlog 监控")
    
    # 2.5 停止资源监控
    log_config.info("停止资源监控...")
    resource_monitor.stop_monitoring()
    log_config.info("✅ 系统资源监控已停止")
    
    # 2.6 停止事件聚合器
    log_config.info("停止事件聚合器...")
    EVENT_AGGREGATOR.stop()
    log_config.info("✅ 事件聚合器已停止")
    
    # 2.7 关闭事件线程池管理器
    log_config.info("关闭事件线程池...")
    from globalobjects.event_aggregator import get_event_pool_manager
    get_event_pool_manager().shutdown_all()
    log_config.info("✅ 事件线程池已关闭")
    
    # 2.8 关闭调度器
    if TRUNON_SCHEDULER:
        log_config.info("关闭调度器...")
        scheduler_manager.shutdown()
        log_config.info("✅ 定时任务管理器已关闭")
    
    log_config.info("✅ 所有服务已停止")
    
    # 阶段3: 释放资源和连接（最后执行）
    log_config.info("【阶段3】释放资源和连接...")
    
    # 3.1 刷新 Redis 缓冲
    log_config.info("刷新 Redis 缓冲...")
    import concurrent.futures
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    loop = asyncio.get_event_loop()
    
    def get_buffer_size():
        from apps.common.utils.redis_pool_manager import get_redis_pool_manager
        return get_redis_pool_manager().get_buffer_size()
    
    try:
        buffer_size = await loop.run_in_executor(executor, get_buffer_size)
        if buffer_size > 0:
            log_config.info(f"发现 {buffer_size} 个事件在本地缓冲中，准备刷新...")
            
            def flush_buffer():
                from apps.common.utils.redis_pool_manager import flush_event_buffer
                return flush_event_buffer('db_events')
            
            flushed = await loop.run_in_executor(executor, flush_buffer)
            log_config.info(f"✅ 缓冲刷新完成，成功刷新 {flushed} 个事件")
    except Exception as e:
        log_config.warning(f"⚠️ 刷新Redis缓冲失败: {e}")
    
    # 3.2 关闭事件辅助模块
    log_config.info("关闭事件辅助模块...")
    try:
        from apps.common.utils.event_helpers import shutdown_event_helpers
        shutdown_event_helpers()
        log_config.info("✅ 事件辅助模块已关闭")
    except Exception as e:
        log_config.warning(f"⚠️ 关闭事件辅助模块失败: {e}")
    
    # 3.2.1 关闭项目HTTP客户端（如SAP异步客户端，释放连接池）
    log_config.info("关闭项目HTTP客户端...")
    try:
        from project_files import project_client
        close_fn = getattr(project_client, 'close_sap_async_client', None)
        if close_fn:
            await close_fn()
        else:
            log_config.debug("项目客户端未定义 close_sap_async_client，跳过")
    except Exception as e:
        log_config.warning(f"⚠️ 关闭项目HTTP客户端失败: {e}")
    
    # 3.3 关闭数据库连接（最后关闭）
    log_config.info("关闭数据库连接...")
    try:
        from tortoise import Tortoise
        await Tortoise.close_connections()
        log_config.info("✅ 数据库连接已关闭")
    except Exception as e:
        log_config.warning(f"⚠️ 关闭数据库连接失败: {e}")
    
    # 阶段4: 关闭日志系统（最后）
    log_config.info("【阶段4】关闭日志系统...")
    
    # 在关闭日志系统前输出最终提示
    log_config.info("==================应用关闭完成==================")
    log_config.info("所有资源已释放，服务已完全停止")
    
    await shutdown_logging()
    
    # 使用print确保关闭后的提示能输出（日志系统已关闭）
    print("=" * 50)
    print("MyAPS API 应用已完全关闭")
    print("=" * 50)
