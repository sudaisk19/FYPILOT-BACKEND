# app/services/mailer.py

from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings

# from sendgrid import SendGridAPIClient


class DevMailer:
    """
    Development mailer using Ethereal (free SMTP test service).
    Captures emails in the Ethereal dashboard instead of sending to real inboxes.
    """

    def __init__(self):
        if not all(
            [
                settings.ethereal_smtp_host,
                settings.ethereal_smtp_port,
                settings.ethereal_smtp_user,
                settings.ethereal_smtp_pass,
            ]
        ):
            raise ValueError(
                "Ethereal SMTP settings must be configured when using ethereal provider"
            )

    async def send(self, to: str, subject: str, html_body: str):
        msg = EmailMessage()
        msg["From"] = settings.ethereal_smtp_user
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(html_body, subtype="html")

        await aiosmtplib.send(
            msg,
            hostname=settings.ethereal_smtp_host,
            port=settings.ethereal_smtp_port,
            username=settings.ethereal_smtp_user,
            password=settings.ethereal_smtp_pass,
            start_tls=True,
        )


class MailtrapMailer:
    """
    Development mailer using Mailtrap (SMTP test service).
    Captures emails in the Mailtrap dashboard instead of sending to real inboxes.
    """

    def __init__(self):
        if not all(
            [
                settings.mailtrap_smtp_host,
                settings.mailtrap_smtp_port,
                settings.mailtrap_smtp_user,
                settings.mailtrap_smtp_pass,
            ]
        ):
            raise ValueError(
                "Mailtrap SMTP settings must be configured when using mailtrap provider"
            )

    async def send(self, to: str, subject: str, html_body: str):
        msg = EmailMessage()
        msg["From"] = settings.mailtrap_smtp_user
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(html_body, subtype="html")

        await aiosmtplib.send(
            msg,
            hostname=settings.mailtrap_smtp_host,
            port=settings.mailtrap_smtp_port,
            username=settings.mailtrap_smtp_user,
            password=settings.mailtrap_smtp_pass,
            start_tls=True,
        )


class ProdMailer:
    """
    Production mailer using SendGrid.
    """

    def __init__(self):
        if not settings.sendgrid_api_key or not settings.from_email:
            raise ValueError(
                "SendGrid API key and from_email must be set in production"
            )
        self.client = SendGridAPIClient(settings.sendgrid_api_key)

    async def send(self, to: str, subject: str, html_body: str):
        message = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": settings.from_email},
            "subject": subject,
            "content": [{"type": "text/html", "value": html_body}],
        }
        response = self.client.send(message)
        if response.status_code >= 400:
            raise Exception(
                f"Failed to send email: {response.status_code}, {response.body}"
            )


def get_mailer():
    """
    Factory to choose the correct mailer based on configuration.
    In .env, set MAILER_PROVIDER to either 'ethereal', 'mailtrap', or 'sendgrid'.
    """
    provider = settings.mailer_provider.lower()
    if provider == "ethereal":
        return DevMailer()
    elif provider == "mailtrap":
        return MailtrapMailer()
    elif provider == "sendgrid":
        return ProdMailer()
    else:
        raise ValueError(f"Unknown mailer provider: {settings.mailer_provider}")


async def send_password_reset_email(to_email: str, user_name: str, reset_link: str):
    """
    Send password reset email to user.

    Args:
        to_email (str): User's email address
        user_name (str): User's full name
        reset_link (str): Password reset link with token
    """
    subject = "Password Reset Request - FYPilot"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Password Reset - FYPilot</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                background-color: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .header {{
                text-align: center;
                margin-bottom: 30px;
            }}
            .logo {{
                font-size: 24px;
                font-weight: bold;
                color: #2563eb;
                margin-bottom: 10px;
            }}
            .content {{
                margin-bottom: 30px;
            }}
            .button {{
                display: inline-block;
                background-color: #2563eb;
                color: white;
                padding: 12px 24px;
                text-decoration: none;
                border-radius: 6px;
                font-weight: 500;
                margin: 20px 0;
            }}
            .button:hover {{
                background-color: #1d4ed8;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #e5e7eb;
                font-size: 14px;
                color: #6b7280;
            }}
            .warning {{
                background-color: #fef3c7;
                border: 1px solid #f59e0b;
                border-radius: 6px;
                padding: 15px;
                margin: 20px 0;
                color: #92400e;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">FYPilot</div>
                <h1>Password Reset Request</h1>
            </div>
            
            <div class="content">
                <p>Hello {user_name},</p>
                
                <p>We received a request to reset your password for your FYPilot account. If you made this request, click the button below to reset your password:</p>
                
                <div style="text-align: center;">
                    <a href="{reset_link}" class="button">Reset My Password</a>
                </div>
                
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; background-color: #f3f4f6; padding: 10px; border-radius: 4px; font-family: monospace;">
                    {reset_link}
                </p>
                
                <div class="warning">
                    <strong>Important:</strong>
                    <ul>
                        <li>This link will expire in 1 hour for security reasons</li>
                        <li>If you didn't request this password reset, please ignore this email</li>
                        <li>Your password will remain unchanged until you click the link above</li>
                    </ul>
                </div>
            </div>
            
            <div class="footer">
                <p>This email was sent from FYPilot. If you have any questions, please contact our support team.</p>
                <p>© 2024 FYPilot. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    mailer = get_mailer()
    await mailer.send(to_email, subject, html_body)
