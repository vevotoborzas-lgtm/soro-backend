import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import Settings

log = logging.getLogger("soro.email")


def send_password_reset_email(settings: Settings, *, to_email: str, reset_link: str) -> bool:
    if not settings.smtp_host:
        log.warning("SMTP is not configured; password reset link for %s: %s", to_email, reset_link)
        return False

    message = EmailMessage()
    message["Subject"] = "Soro.hu jelszo visszaallitasa"
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    message["To"] = to_email
    message.set_content(
        "\n".join(
            [
                "Szia!",
                "",
                "Jelszo-visszaallitast kertel a Soro.hu fiokodhoz.",
                f"Itt tudsz uj jelszot beallitani: {reset_link}",
                "",
                "Ha nem te kerted, ezt az emailt nyugodtan figyelmen kivul hagyhatod.",
                "",
                "Soro.hu",
            ]
        )
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except Exception:
        log.exception("password reset email failed to_email=%s", to_email)
        return False

    log.info("password reset email sent to_email=%s", to_email)
    return True
