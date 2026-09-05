from email.message import EmailMessage
import smtplib
from app.core.config import settings


class EmailService:
    def _send(self, recipient: str, subject: str, body: str, debug_url: str) -> None:
        if settings.app_env == "local" and not settings.smtp_host:
            print(f"[local-email] to={recipient} subject={subject} url={debug_url}")
            return
        if not settings.smtp_host:
            raise RuntimeError("SMTP must be configured outside local development")

        message = EmailMessage()
        message["From"] = settings.smtp_from_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)

    def send_verification(self, recipient: str, verification_url: str) -> None:
        subject = "Verify your Document Organizer email"
        body = (
            "Verify your email address to activate your account.\n\n"
            f"{verification_url}\n\n"
            f"This link expires in {settings.verification_token_minutes} minutes and can be used once."
        )
        self._send(recipient, subject, body, verification_url)

    def send_password_reset(self, recipient: str, reset_url: str) -> None:
        subject = "Reset your Document Organizer password"
        body = (
            "Use the link below to reset your password.\n\n"
            f"{reset_url}\n\n"
            f"This link expires in {settings.password_reset_token_minutes} minutes and can be used once."
        )
        self._send(recipient, subject, body, reset_url)


email_service = EmailService()
