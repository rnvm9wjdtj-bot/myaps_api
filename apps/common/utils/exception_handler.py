from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from globalobjects import logger as log_config
import os

LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
logger = log_config.get_logger(__name__, level=LOG_LEVEL)

class AppException(Exception):
    """应用异常基类"""
    def __init__(self, message, error_code=500, status_code=500):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(self.message)

class DatabaseException(AppException):
    """数据库异常"""
    def __init__(self, message, error_code=503, status_code=503):
        super().__init__(message, error_code, status_code)

class ValidationException(AppException):
    """数据验证异常"""
    def __init__(self, message, error_code=400, status_code=400):
        super().__init__(message, error_code, status_code)

class AuthenticationException(AppException):
    """认证异常"""
    def __init__(self, message, error_code=401, status_code=401):
        super().__init__(message, error_code, status_code)

class AuthorizationException(AppException):
    """授权异常"""
    def __init__(self, message, error_code=403, status_code=403):
        super().__init__(message, error_code, status_code)

class NotFoundException(AppException):
    """资源不存在异常"""
    def __init__(self, message, error_code=404, status_code=404):
        super().__init__(message, error_code, status_code)

def handle_app_exception(request: Request, exc: AppException):
    """处理应用异常"""
    logger.error(f"应用异常: {exc.message} (code: {exc.error_code})")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status_code": exc.error_code,
            "success": 0,
            "meta": {},
            "message": exc.message
        }
    )

def handle_generic_exception(request: Request, exc: Exception):
    """处理通用异常"""
    logger.error(f"未处理的异常: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status_code": 500,
            "success": 0,
            "meta": {},
            "message": f"内部服务器错误: {str(exc)}"
        }
    )

def register_exception_handlers(app: FastAPI):
    """注册异常处理器"""
    # 注册应用异常处理器
    app.add_exception_handler(AppException, handle_app_exception)
    app.add_exception_handler(DatabaseException, handle_app_exception)
    app.add_exception_handler(ValidationException, handle_app_exception)
    app.add_exception_handler(AuthenticationException, handle_app_exception)
    app.add_exception_handler(AuthorizationException, handle_app_exception)
    app.add_exception_handler(NotFoundException, handle_app_exception)
    
    # 注册通用异常处理器
    app.add_exception_handler(Exception, handle_generic_exception)
    
    logger.success("异常处理器", "", "已注册")

def handle_exceptions(func):
    """统一异常处理装饰器"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except AppException as e:
            logger.error(f"应用异常: {e.message} (code: {e.error_code})")
            raise
        except Exception as e:
            logger.error(f"未处理的异常: {str(e)}", exc_info=True)
            raise AppException(f"内部服务器错误: {str(e)}")
    return wrapper