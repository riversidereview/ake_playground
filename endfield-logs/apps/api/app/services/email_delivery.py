from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    pass


class EmailDeliveryService:
    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(
            settings.smtp_host
            and settings.smtp_username
            and settings.smtp_password
            and settings.mail_from_address
        )

    def send_verification_code(self, *, to_email: str, code: str, purpose: str) -> None:
        if not self.is_configured():
            logger.warning("SMTP email delivery is not configured; skipping verification email to %s", to_email)
            return

        settings = get_settings()
        subject = "ZMDLogs 验证码"
        purpose_label = "网站登录" if purpose == "web_login" else "上传器登录"
        text_body = (
            f"你的 ZMDLogs {purpose_label}验证码是：{code}\n\n"
            "验证码 10 分钟内有效。如果不是你本人操作，可以忽略这封邮件。"
        )
        html_body = f"""
<!doctype html>
<html>
  <body style="margin:0;padding:24px;background:#f6f7fb;font-family:Arial,'Microsoft YaHei',sans-serif;color:#111827;">
    <div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:24px;">
      <h1 style="margin:0 0 16px;font-size:20px;line-height:1.4;">ZMDLogs 验证码</h1>
      <p style="margin:0 0 16px;font-size:14px;line-height:1.7;">你正在进行 {purpose_label}，验证码为：</p>
      <div style="font-size:28px;letter-spacing:6px;font-weight:700;margin:18px 0;color:#0f172a;">{code}</div>
      <p style="margin:0;font-size:13px;line-height:1.7;color:#64748b;">验证码 10 分钟内有效。如果不是你本人操作，可以忽略这封邮件。</p>
    </div>
  </body>
</html>
""".strip()

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((settings.mail_from_name, settings.mail_from_address))
        message["To"] = to_email
        message["Date"] = formatdate(localtime=False, usegmt=True)
        message["Message-ID"] = make_msgid(domain=self._message_id_domain(settings.mail_from_address))
        message["Auto-Submitted"] = "auto-generated"
        message["X-Auto-Response-Suppress"] = "All"
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

        try:
            if settings.smtp_use_ssl:
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as smtp:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as smtp:
                    smtp.starttls()
                    smtp.login(settings.smtp_username, settings.smtp_password)
                    smtp.send_message(message)
        except Exception as exc:
            raise EmailDeliveryError("failed to send verification email") from exc

    @staticmethod
    def _message_id_domain(from_address: str) -> str | None:
        parsed_address = parseaddr(from_address)[1]
        if "@" not in parsed_address:
            return None
        return parsed_address.rsplit("@", 1)[1].strip().lower() or None


email_delivery_service = EmailDeliveryService()
