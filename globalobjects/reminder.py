import sys
import httpx
import asyncio
import inspect
import argparse
import hashlib, hmac, json, os, time, smtplib
from collections import defaultdict
from typing import Callable, Optional, Dict, Any, List, Union
from enum import Enum
from abc import ABC, abstractmethod
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header






class RemindType(Enum):
    """提示类型"""
    REQUEST_SLOW = "request_slow"
    REQUEST_ERROR = "request_error"
    DB_CONNECTION_BREAK = "db_connection_break"
    DB_POOL_BREAK = "db_pool_break"
    BINLOG_LISTENER_BREAK = "binlog_listener_break"
    BINLOG_LISTENER_RESUME = "binlog_listener_resume"

    # APS_EVENT = "aps_event"



class RemindManager:
    """提示发送器"""
    
    def __init__(self, remind_cooldown: Optional[Dict[RemindType, int]] = {}, *args, **kwargs):
        self._remind_callbacks: Dict[RemindType, List[Callable]] = defaultdict(list)
        self._last_remind_time: Dict[str, float] = {}    # 记录每种告警的最后发送时间
        # 初始化冷却时间字典
        self._remind_cooldown = {
            RemindType.REQUEST_SLOW.value: 7200,
            RemindType.REQUEST_ERROR.value: 7200,
            RemindType.DB_CONNECTION_BREAK.value: 7200,
            RemindType.DB_POOL_BREAK.value: 7200,
            RemindType.BINLOG_LISTENER_BREAK.value: 7200,
            RemindType.BINLOG_LISTENER_RESUME.value: 7200,
            # RemindType.APS_EVENT.value: 0,
        }
        # 更新自定义冷却时间
        if remind_cooldown:
            for key, value in remind_cooldown.items():
                if isinstance(key, RemindType):
                    self._remind_cooldown[key.value] = value
                else:
                    self._remind_cooldown[key] = value
    

    def register(self, reminder: 'Reminder', remind_types: List[RemindType]):
        """
        注册提示回调函数
        
        Args:
            reminder: 提示发送器
            remind_types: 适用于哪些提示类型
        """
        for remind_type in remind_types:
            self._remind_callbacks[remind_type].append(reminder.remind)
    

    async def trigger_remind(self, remind_type: RemindType, remind_content: Any):
        """
        触发提示回调，包含提示去重和频率限制
        
        Args:
            remind_type: 提示类型
            remind_content: 提示讯息，可以是字符串、整数、浮点数或字典类型
        """
        # 生成提示唯一标识
        content_str = json.dumps(remind_content, sort_keys=True, ensure_ascii=False)
        content_hash = hashlib.sha256(content_str.encode('utf-8')).hexdigest()
        remind_key = f"{remind_type.value}:{content_hash}"
        
        # 检查是否在冷却期内
        current_time = time.time()
        last_time = self._last_remind_time.get(remind_key, 0)
        # 获取该类型提示的冷却时间
        cooldown = self._remind_cooldown.get(remind_type.value, 7200)  # 默认7200秒
        if current_time - last_time < cooldown:
            return
        
        # 触发提示回调
        callback = self._remind_callbacks.get(remind_type)   
        if callback:
            try:
                if inspect.iscoroutinefunction(callback):
                    # 检查回调函数参数数量
                    sig = inspect.signature(callback)
                    if len(sig.parameters) == 2:
                        await callback(remind_type, remind_content)
                    else:
                        await callback(remind_content)
                else:
                    # 检查回调函数参数数量
                    sig = inspect.signature(callback)
                    if len(sig.parameters) == 2:
                        callback(remind_type, remind_content)
                    else:
                        callback(alert_content)
                # 更新最后发送时间
                self._last_remind_time[alert_key] = current_time
            except Exception as e:
                pass




# 全局提示发送器实例
remind_manager = RemindManager()



class Reminder(ABC):
    """提示发送器"""
    
    def __init__(self, *args, **kwargs):
        pass


    @abstractmethod
    async def remind(self, *args, **kwargs):
        """
        发送提示（供本项目内部调用）
        """
        pass


    @abstractmethod
    def remind_by_shell(self, *args, **kwargs):
        """
        发送提示（供外部shell脚本调用）
        """
        pass


    async def send_alert(self, message: str, level: str = "warning", subject: str = None):
        """发送告警"""

        if subject is None:
            level_prefix = {
                "info": "ℹ️ 信息",
                "warning": "⚠️ 警告",
                "error": "❌ 错误"
            }.get(level, "🔔")
            subject = f"{level_prefix} 系统告警"

        alert_content = {
            "level": level,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "source": "service_daemon"
        }

        await self.remind(alert_content)
        return True


    def regist_to_manager(self, remind_types: List[RemindType], *args, **kwargs):
        """
        注册为提示器
        """
        remind_manager.register(self, remind_types=remind_types)



class TencentSmsReminder(Reminder):
    """
    腾讯云短信提示发送器
    """
    def __init__(
        self,
        secret_id: str,
        secret_key: str,
        sms_sdk_app_id: str,
        sign_name: str,
        template_id: str,
        phone_numbers: Union[str, List[str]],
    ):
        """
        Args:
            secret_id: 腾讯云短信应用密钥ID，从 https://console.cloud.tencent.com/cam/capi 获取
            secret_key: 腾讯云短信应用密钥，从 https://console.cloud.tencent.com/cam/capi 获取
            sms_sdk_app_id: 腾讯云短信应用ID，从 https://console.cloud.tencent.com/smsv2/app-manage 获取
            sign_name: 腾讯云短信签名名称，从 https://console.cloud.tencent.com/smsv2/csms-sign 获取
            template_id: 腾讯云短信模板ID，从 https://console.cloud.tencent.com/smsv2/csms-template 获取
            phone_numbers: 默认手机号列表，逗号分隔
        """
        super().__init__(remind_types=remind_types)
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.sms_sdk_app_id = sms_sdk_app_id
        self.sign_name = sign_name
        self.template_id = template_id
        self.phone_numbers = phone_numbers
        if isinstance(phone_numbers, list):
            self.phone_number_set = [f"+86{num.strip()}" for num in phone_numbers if num.strip()]
        else:
            self.phone_number_set = [f"+86{num.strip()}" for num in self.phone_numbers.split(',') if num.strip()]


    @staticmethod
    async def call_tecent_api(
        secret_id: str, secret_key: str, http_request_method="POST",
        service="sms", host="sms.tencentcloudapi.com",
        region="ap-nanjing", action="SendSms", version="2021-01-11",
        payload={}
    ):
        def _sign(key, msg):
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
        
        endpoint = "https://" + host
        algorithm = "TC3-HMAC-SHA256"
        timestamp = int(time.time())
        # date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
        date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")

        # ************* 步骤 1：拼接规范请求串 *************
        canonical_uri = "/"
        canonical_querystring = ""
        ct = "application/json; charset=utf-8"
        payload = json.dumps(payload)
        canonical_headers = "content-type:%s\nhost:%s\nx-tc-action:%s\n" % (ct, host, action.lower())
        signed_headers = "content-type;host;x-tc-action"
        hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        canonical_request = (http_request_method + "\n" +
                        canonical_uri + "\n" +
                        canonical_querystring + "\n" +
                        canonical_headers + "\n" +
                        signed_headers + "\n" +
                        hashed_request_payload)

        # ************* 步骤 2：拼接待签名字符串 *************
        credential_scope = date + "/" + service + "/" + "tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = (algorithm + "\n" +
                        str(timestamp) + "\n" +
                        credential_scope + "\n" +
                        hashed_canonical_request)

        # ************* 步骤 3：计算签名 *************
        secret_date = _sign(("TC3" + secret_key).encode("utf-8"), date)
        secret_service = _sign(secret_date, service)
        secret_signing = _sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        # ************* 步骤 4：拼接 Authorization *************
        authorization = (algorithm + " " +
                    "Credential=" + secret_id + "/" + credential_scope + ", " +
                    "SignedHeaders=" + signed_headers + ", " +
                    "Signature=" + signature)

        headers = {
            "Authorization": authorization,
            "Content-Type": ct,
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": version,
            "X-TC-Region": region,
        }

        async with httpx.AsyncClient() as client:
            if http_request_method == "POST":
                response = await client.post(endpoint, headers=headers, data=payload)
            else:
                response = await client.get(endpoint, headers=headers, params=payload)

            response.raise_for_status()
        return response.json()


    async def remind(
        self,
        *args, **kwargs
    ):
        # 构建手机号列表

        phone_number_set = self.phone_number_set
        # 构建请求参数
        payload = {
            "SmsSdkAppId": self.sms_sdk_app_id,
            "SignName": self.sign_name,
            "TemplateId": self.template_id,
            # "TemplateParamSet": [str(remind_content)[:50]],
        }

        max_retries = 3
        
        # 持续重试直到所有手机号都成功或达到最大重试次数
        for retry_count in range(max_retries):
            if not phone_number_set:
                break  # 所有手机号都已成功发送
            
            # 构建请求参数
            payload["PhoneNumberSet"] = phone_number_set
            
            try:
                response = await self.call_tecent_api(
                    secret_id=self.secret_id, secret_key=self.secret_key,
                    payload=payload
                )
                
                # 检查响应是否成功
                if 'Response' in response and 'SendStatusSet' in response['Response']:
                    # 收集发送失败的手机号
                    failed_numbers = []
                    for status in response['Response']['SendStatusSet']:
                        if status.get('Code', '').lower() != 'ok':
                            failed_numbers.append(status.get('PhoneNumber'))
                    
                    if not failed_numbers:
                        break  # 所有手机号都发送成功
                    
                    # 只对失败的手机号进行重试
                    phone_number_set = failed_numbers
            except Exception as e:
                pass
            
            if retry_count <= max_retries:
                await asyncio.sleep(1)  # 重试前等待1秒


    def remind_by_shell(self, *args, **kwargs):
        pass



class QqEmailReminder(Reminder):
    """
    QQ邮箱提示发送器
    """
    def __init__(
        self,
        smtp_user: str,
        smtp_password: str,
        email_from: str,
        email_to: Union[str, List[str]],
        smtp_server: str = "smtp.qq.com",
        smtp_port: int = 587,
    ):
        super().__init__()
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.email_from = email_from

        if isinstance(email_to, str):
            self.email_to = email_to
        else:
            self.email_to = ','.join(email_to)

    async def remind(self, remind_content: Any, *args, **kwargs):
        """
        使用QQ邮箱发送提示
        Args:
            email_to: 收件人邮箱，默认使用默认收件人邮箱
            remind_content: 提示信息字典
        """
        from core.settings import PROJECT_DIR, PROJECT_JSON
        
        # 构建邮件内容
        subject = f"🔷APS🔹{PROJECT_DIR}_{PROJECT_JSON.lower().replace('.json','')}🔷"
        body = f"📆 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        # body += f"提示类型: {[rem.value for rem in self.remind_types]}\n"
        body += f"📝 内容:\n{str(remind_content)}\n"

        # 构建邮件
        msg = MIMEMultipart()
        msg['From'] = self.email_from    # Header(email_from, 'utf-8')
        msg['To'] = self.email_to    # Header(email_to, 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        max_retries = 3
        for retry_count in range(max_retries):
            try:
                # 连接 SMTP 服务器
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
                break  # 发送成功，退出重试 
            except Exception as e:
                if retry_count < max_retries - 1:
                    await asyncio.sleep(1)  # 重试前等待1秒
                pass


    def remind_by_shell(self, *args, **kwargs):
        parser = argparse.ArgumentParser(description="项目告警发送工具")
        parser.add_argument("--message", required=True, help="告警消息内容")
        parser.add_argument("--level", default="warning",
                            choices=["info", "warning", "error"], help="告警级别")
        parser.add_argument("--subject", help="邮件主题（可选）")

        args = parser.parse_args()

        try:
            asyncio.run(self.send_alert(args.message, args.level, args.subject))
            print(f"[SUCCESS] Alert sent: {args.subject or args.message}")
            return 0
        except Exception as e:
            print(f"[ERROR] Failed to send alert: {e}", file=sys.stderr)
            return 1