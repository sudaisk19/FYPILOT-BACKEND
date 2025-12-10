# app/services/mailer.py

from email.message import EmailMessage
from typing import Optional

import aiosmtplib

from app.core.config import settings

try:
    from sendgrid import SendGridAPIClient
except ImportError:
    SendGridAPIClient = None  # type: ignore


def get_email_template(
    title: str,
    content: str,
    button_text: Optional[str] = None,
    button_link: Optional[str] = None,
    footer_text: Optional[str] = None,
    logo_url: Optional[str] = None,
) -> str:
    """
    Generate a professional HTML email template.

    Args:
        title: Email title/heading
        content: Main email content (HTML)
        button_text: Optional button text
        button_link: Optional button link URL
        footer_text: Optional custom footer text
        logo_url: Optional logo image URL (defaults to settings.email_logo_url)

    Returns:
        Complete HTML email template
    """
    logo = logo_url or settings.email_logo_url
    company_name = settings.email_company_name

    # Logo HTML (either image or text fallback)
    logo_html = ""
    if logo:
        logo_html = f'<img src="{logo}" alt="{company_name}" style="max-width: 200px; height: auto; margin-bottom: 20px;" />'
    else:
        logo_html = f'<div style="font-size: 28px; font-weight: bold; color: #7c3aed; margin-bottom: 20px;">{company_name}</div>'

    button_html = ""
    if button_text and button_link:
        button_html = f"""
        <div style="text-align: center; margin: 30px 0;">
            <a href="{button_link}" style="display: inline-block; background-color: #2563eb; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px;">
                {button_text}
            </a>
        </div>
        """

    footer = footer_text or f"© 2024 {company_name}. All rights reserved."

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <title>{title} - {company_name}</title>
        <!--[if mso]>
        <style type="text/css">
            body, table, td {{font-family: Arial, sans-serif !important;}}
        </style>
        <![endif]-->
    </head>
    <body style="margin: 0; padding: 0; background-color: #f5f7fa; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
        <table role="presentation" style="width: 100%; border-collapse: collapse; border-spacing: 0; background-color: #f5f7fa; padding: 20px 0;">
            <tr>
                <td align="center" style="padding: 20px 0;">
                    <table role="presentation" style="width: 100%; max-width: 600px; border-collapse: collapse; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <!-- Header -->
                        <tr>
                            <td style="padding: 40px 40px 20px; text-align: center;">
                                {logo_html}
                            </td>
                        </tr>
                        
                        <!-- Title -->
                        <tr>
                            <td style="padding: 30px 40px 20px; text-align: center;">
                                <h1 style="margin: 0; font-size: 24px; font-weight: 600; color: #1f2937; line-height: 1.4;">
                                    {title}
                                </h1>
                            </td>
                        </tr>
                        
                        <!-- Content -->
                        <tr>
                            <td style="padding: 0 40px 30px; color: #4b5563; font-size: 16px; line-height: 1.6;">
                                {content}
                                {button_html}
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="padding: 30px 40px; background-color: #f9fafb; border-top: 1px solid #e5e7eb; border-radius: 0 0 8px 8px; text-align: center; font-size: 14px; color: #6b7280; line-height: 1.5;">
                                <p style="margin: 0 0 10px;">
                                    {footer}
                                </p>
                                <p style="margin: 0; font-size: 12px; color: #9ca3af;">
                                    This email was sent from {company_name}. If you have any questions, please contact our support team.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """


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
        if SendGridAPIClient is None:
            raise ImportError("sendgrid package is not installed")
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
    subject = f"Password Reset Request - {settings.email_company_name}"

    content = f"""
    <p style="margin: 0 0 16px;">Hello <strong>{user_name}</strong>,</p>
    
    <p style="margin: 0 0 16px;">
        We received a request to reset your password for your {settings.email_company_name} account. 
        If you made this request, click the button below to reset your password.
    </p>
    
    <div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 16px; margin: 24px 0; border-radius: 4px;">
        <p style="margin: 0 0 8px; font-weight: 600; color: #92400e;">Important Security Information:</p>
        <ul style="margin: 0; padding-left: 20px; color: #92400e;">
            <li style="margin-bottom: 8px;">This link will expire in <strong>1 hour</strong> for security reasons</li>
            <li style="margin-bottom: 8px;">If you didn't request this password reset, please ignore this email</li>
            <li style="margin-bottom: 0;">Your password will remain unchanged until you click the link above</li>
        </ul>
    </div>
    
    <p style="margin: 24px 0 0; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 14px; color: #9ca3af;">
        If the button doesn't work, copy and paste this link into your browser:<br>
        <a href="{reset_link}" style="color: #2563eb; word-break: break-all;">{reset_link}</a>
    </p>
    """

    html_body = get_email_template(
        title="Password Reset Request",
        content=content,
        button_text="Reset My Password",
        button_link=reset_link,
        footer_text="If you didn't request this password reset, you can safely ignore this email.",
    )

    mailer = get_mailer()
    await mailer.send(to_email, subject, html_body)


async def send_group_invitation_email(
    to_email: str,
    invitee_name: str,
    inviter_name: str,
    accept_link: str,
    reject_link: str,
):
    """
    Send group invitation email to student.

    Args:
        to_email (str): Invitee's email address
        invitee_name (str): Invitee's full name
        inviter_name (str): Inviter's full name
        accept_link (str): Group invite accept link with token
        reject_link (str): Group invite reject link with token
    """
    subject = f"You're Invited to Join a FYP Group - {settings.email_company_name}"

    content = f"""
    <p style="margin: 0 0 16px;">Hello <strong>{invitee_name}</strong>,</p>
    
    <p style="margin: 0 0 16px;">
        <strong>{inviter_name}</strong> has invited you to join their Final Year Project (FYP) group. 
        This is a great opportunity to collaborate on an exciting project!
    </p>
    
    <div style="background-color: #dbeafe; border-left: 4px solid #0284c7; padding: 16px; margin: 24px 0; border-radius: 4px;">
        <p style="margin: 0 0 8px; font-weight: 600; color: #0c4a6e;">About This Invitation:</p>
        <ul style="margin: 0; padding-left: 20px; color: #0c4a6e;">
            <li style="margin-bottom: 8px;">This invitation will expire in <strong>7 days</strong></li>
            <li style="margin-bottom: 8px;">You can accept or decline the invitation below</li>
            <li style="margin-bottom: 0;">Your group membership status will only change if you accept</li>
        </ul>
    </div>
    
    <div style="text-align: center; margin: 30px 0;">
        <a href="{accept_link}" style="display: inline-block; background-color: #10b981; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; margin-right: 10px;">
            Accept Invitation
        </a>
        <a href="{reject_link}" style="display: inline-block; background-color: #6b7280; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600;">
            Decline Invitation
        </a>
    </div>
    
    <p style="margin: 24px 0 0; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 14px; color: #9ca3af;">
        If the buttons don't work, copy and paste these links into your browser:<br>
        <strong>Accept:</strong> <a href="{accept_link}" style="color: #2563eb; word-break: break-all;">{accept_link}</a><br>
        <strong>Decline:</strong> <a href="{reject_link}" style="color: #2563eb; word-break: break-all;">{reject_link}</a>
    </p>
    """

    html_body = get_email_template(
        title="FYP Group Invitation",
        content=content,
        footer_text="If you didn't expect this invitation, you can safely ignore this email.",
    )

    mailer = get_mailer()
    await mailer.send(to_email, subject, html_body)


async def send_supervisor_accepted_email(
    to_email: str, group_name: str, supervisor_name: str, role: str
):
    """
    Send email to group members when supervisor accepts their request.

    Args:
        to_email (str): Group member's email address
        group_name (str): Name of the group
        supervisor_name (str): Name of the supervisor who accepted
        role (str): Role accepted (supervisor or cosupervisor)
    """
    subject = f"Supervisor Request Accepted - {settings.email_company_name}"
    role_text = "Primary Supervisor" if role == "supervisor" else "Co-Supervisor"

    content = f"""
    <p style="margin: 0 0 16px;">Hi there,</p>
    
    <p style="margin: 0 0 16px;">
        Great news! <strong>{supervisor_name}</strong> has accepted your group's request to be the <strong>{role_text}</strong> 
        for your FYP project.
    </p>
    
    <div style="background-color: #d1fae5; border-left: 4px solid #10b981; padding: 16px; margin: 24px 0; border-radius: 4px;">
        <p style="margin: 0 0 8px; font-weight: 600; color: #065f46;">Request Status: Accepted ✓</p>
        <ul style="margin: 0; padding-left: 20px; color: #065f46;">
            <li style="margin-bottom: 8px;"><strong>Group:</strong> {group_name}</li>
            <li style="margin-bottom: 8px;"><strong>Supervisor:</strong> {supervisor_name}</li>
            <li style="margin-bottom: 0;"><strong>Role:</strong> {role_text}</li>
        </ul>
    </div>
    
    <p style="margin: 0 0 16px;">
        Your supervisor is now part of your team. You can start collaborating on your project right away!
    </p>
    """

    html_body = get_email_template(
        title="Supervisor Request Accepted",
        content=content,
        footer_text="Congratulations on forming your complete team!",
    )

    mailer = get_mailer()
    await mailer.send(to_email, subject, html_body)


async def send_supervisor_rejected_email(
    to_email: str, group_name: str, supervisor_name: str, role: str
):
    """
    Send email to group members when supervisor rejects their request.

    Args:
        to_email (str): Group member's email address
        group_name (str): Name of the group
        supervisor_name (str): Name of the supervisor who rejected
        role (str): Role requested (supervisor or cosupervisor)
    """
    subject = f"Supervisor Request Declined - {settings.email_company_name}"
    role_text = "Primary Supervisor" if role == "supervisor" else "Co-Supervisor"

    content = f"""
    <p style="margin: 0 0 16px;">Hi there,</p>
    
    <p style="margin: 0 0 16px;">
        Unfortunately, <strong>{supervisor_name}</strong> has declined your group's request to be the <strong>{role_text}</strong> 
        for your FYP project.
    </p>
    
    <div style="background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 16px; margin: 24px 0; border-radius: 4px;">
        <p style="margin: 0 0 8px; font-weight: 600; color: #7f1d1d;">Request Status: Declined</p>
        <ul style="margin: 0; padding-left: 20px; color: #7f1d1d;">
            <li style="margin-bottom: 8px;"><strong>Group:</strong> {group_name}</li>
            <li style="margin-bottom: 8px;"><strong>Supervisor:</strong> {supervisor_name}</li>
            <li style="margin-bottom: 0;"><strong>Role:</strong> {role_text}</li>
        </ul>
    </div>
    
    <p style="margin: 0 0 16px;">
        Don't worry! You can send requests to other supervisors or try again with a different approach.
    </p>
    """

    html_body = get_email_template(
        title="Supervisor Request Declined",
        content=content,
        footer_text="Keep exploring other supervisor options for your project.",
    )

    mailer = get_mailer()
    await mailer.send(to_email, subject, html_body)
