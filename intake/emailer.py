from dataclasses import dataclass
from typing import Tuple, Optional

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
except Exception:
    SendGridAPIClient = None
    Mail = None


@dataclass
class EmailConfig:
    provider: str
    sendgrid_api_key: str
    from_email: str
    to_email: str


def send_packet_email(cfg: EmailConfig, subject: str, body_text: str) -> Tuple[bool, Optional[str]]:
    if cfg.provider.lower() != "sendgrid":
        return False, "Unsupported provider"

    if SendGridAPIClient is None or Mail is None:
        return False, "SendGrid library not installed"

    if not cfg.sendgrid_api_key or not cfg.from_email or not cfg.to_email:
        return False, "Missing email configuration"

    try:
        message = Mail(
            from_email=cfg.from_email,
            to_emails=cfg.to_email,
            subject=subject,
            plain_text_content=body_text
        )
        sg = SendGridAPIClient(cfg.sendgrid_api_key)
        sg.send(message)
        return True, None
    except Exception as e:
        return False, str(e)
