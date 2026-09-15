# src/notifier/email/sender.py
import smtplib
from email.message import EmailMessage


class EmailSender:
    def __init__(self, smtp_host: str, sender: str):
        self.smtp_host = smtp_host
        self.sender = sender

    def send(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
    ) -> None:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(self.smtp_host) as smtp:
            smtp.send_message(msg)
