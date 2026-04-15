import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from globalobjects import logger as log_config

class WebSocketConnectionManager:
    def __init__(self):
        self.active_connections = set()
        self.ip_connection_count = {}
        self.max_connections_per_ip = 10  # 每IP最大连接数
        self.max_total_connections = 100  # 总最大连接数

    async def connect(self, websocket: WebSocket):
        client_ip = websocket.client.host
        
        # 检查连接数限制
        if len(self.active_connections) >= self.max_total_connections:
            log_config.warning(f"WebSocket 连接数达到上限: {self.max_total_connections}")
            return False
        
        # 检查每IP连接数限制
        if self.ip_connection_count.get(client_ip, 0) >= self.max_connections_per_ip:
            log_config.warning(f"IP {client_ip} 连接数达到上限: {self.max_connections_per_ip}")
            return False
        
        # 接受连接
        await websocket.accept()
        
        # 记录连接
        self.active_connections.add(websocket)
        self.ip_connection_count[client_ip] = self.ip_connection_count.get(client_ip, 0) + 1
        
        return True

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            client_ip = websocket.client.host
            if client_ip in self.ip_connection_count:
                self.ip_connection_count[client_ip] -= 1
                if self.ip_connection_count[client_ip] <= 0:
                    del self.ip_connection_count[client_ip]

    def get_active_connections_count(self):
        return len(self.active_connections)

    def get_ip_connection_count(self, client_ip):
        return self.ip_connection_count.get(client_ip, 0)

# 初始化 WebSocket 连接管理器
websocket_manager = WebSocketConnectionManager()

async def websocket_endpoint(websocket: WebSocket, path: str = ""):
    """
    通用 WebSocket 端点，捕获所有 WebSocket 连接请求。
    使用 {path:path} 通配符匹配任意路径，避免 "Unsupported upgrade request" 警告。
    """
    # 尝试连接，检查连接数限制
    connected = await websocket_manager.connect(websocket)
    if not connected:
        # 连接被拒绝，直接关闭
        try:
            await websocket.close(code=1008, reason="Connection limit reached")
        except:
            pass
        return
    
    full_path = f"/{path}" if path else "/"
    client_info = {
        "client": f"{websocket.client.host}:{websocket.client.port}",
        "path": full_path,
        "query_params": dict(websocket.query_params),
        "headers": {k: v for k, v in websocket.headers.items() if k.lower() not in ['cookie', 'authorization']},
    }
    log_config.info(f"WebSocket 连接请求: {client_info}")

    try:
        # 保持连接并接收消息，3秒超时后自动关闭（缩短超时时间）
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                log_config.info(f"WebSocket 收到消息 [{full_path}]: {message}")
                await websocket.send_json({
                    "status": "received",
                    "path": full_path,
                    "message": message
                })
            except asyncio.TimeoutError:
                break
    except WebSocketDisconnect:
        log_config.info(f"WebSocket 客户端断开连接: {client_info['client']} - {full_path}")
    except Exception as e:
        log_config.warning(f"WebSocket 异常 [{full_path}]: {e}")
    finally:
        # 确保断开连接并清理资源
        try:
            await websocket.close()
        except:
            pass
        # 从连接管理器中移除
        websocket_manager.disconnect(websocket)
        log_config.info(f"WebSocket 连接已关闭: {client_info['client']} - {full_path}")
        # 记录当前活跃连接数
        log_config.debug(f"当前活跃 WebSocket 连接数: {websocket_manager.get_active_connections_count()}")

async def websocket_root(websocket: WebSocket):
    """
    根路径 WebSocket 端点，捕获对根路径的 WebSocket 连接请求。
    """
    # 尝试连接，检查连接数限制
    connected = await websocket_manager.connect(websocket)
    if not connected:
        # 连接被拒绝，直接关闭
        try:
            await websocket.close(code=1008, reason="Connection limit reached")
        except:
            pass
        return
    
    client_info = {
        "client": f"{websocket.client.host}:{websocket.client.port}",
        "path": "/",
        "query_params": dict(websocket.query_params),
        "headers": {k: v for k, v in websocket.headers.items() if k.lower() not in ['cookie', 'authorization']},
    }
    log_config.info(f"WebSocket 根路径连接请求: {client_info}")

    try:
        # 60秒超时后自动关闭
        await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        pass
    except Exception as e:
        log_config.warning(f"WebSocket 根路径异常: {e}")
    finally:
        # 确保断开连接并清理资源
        try:
            await websocket.close()
        except:
            pass
        # 从连接管理器中移除
        websocket_manager.disconnect(websocket)
        log_config.info(f"WebSocket 根路径连接已关闭: {client_info['client']}")
        # 记录当前活跃连接数
        log_config.debug(f"当前活跃 WebSocket 连接数: {websocket_manager.get_active_connections_count()}")
