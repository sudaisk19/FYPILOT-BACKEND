# app/services/mailer.py

from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings


class DevMailer:
    """
    Development mailer using Ethereal (free SMTP test service).
    Captures emails in the Ethereal dashboard instead of sending to real inboxes.
    """

    async def send(self, to: str, subject: str, html_body: str):
        msg = EmailMessage()
        msg["From"] = settings.ETHEREAL_SMTP_USER
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(html_body, subtype="html")

        await aiosmtplib.send(
            msg,
            hostname=settings.ETHEREAL_SMTP_HOST,
            port=settings.ETHEREAL_SMTP_PORT,
            username=settings.ETHEREAL_SMTP_USER,
            password=settings.ETHEREAL_SMTP_PASS,
            start_tls=True,
        )


# ----------------------------------prod mail servcice

# class ProdMailer:
#     """
#     Production mailer using SendGrid.
#     Swap in your preferred ESP client here.
#     """
#     def __init__(self):
#         from sendgrid import SendGridAPIClient
#         self.client = SendGridAPIClient(settings.SENDGRID_API_KEY)

#     async def send(self, to: str, subject: str, html_body: str):
#         # SendGrid's Python client is synchronous; wrap if you need true async.
#         message = {
#             "personalizations": [{"to": [{"email": to}]}],
#             "from": {"email": settings.FROM_EMAIL},
#             "subject": subject,
#             "content": [{"type": "text/html", "value": html_body}],
#         }
#         response = self.client.send(message)
#         if response.status_code >= 400:
#             raise Exception(f"Failed to send email: {response.status_code}")


def get_mailer():
    """
    Factory to choose the correct mailer based on configuration.
    MAILER_PROVIDER in .env should be either 'ethereal' or 'sendgrid'.
    """
    if settings.MAILER_PROVIDER == "ethereal":
        return DevMailer()
    # else:
    #     # return ProdMailer()
