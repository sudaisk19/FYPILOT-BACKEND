# app/services/mailer.py

import logging
from datetime import datetime
from email.message import EmailMessage
from html import escape
from typing import Awaitable, Optional

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    from sendgrid import SendGridAPIClient
except ImportError:
    SendGridAPIClient = None  # type: ignore


MAILTRAP_RATE_LIMIT_CODE = 550
MAILTRAP_RATE_LIMIT_HINT = "Too many emails per second"
MAILTRAP_RATE_LIMIT_DOC = "https://mailtrap.io/billing/plans/testing"


async def _send_with_rate_limit_guard(
    send_operation: Awaitable[None], *, context: str
) -> None:
    """Await a mailer send and swallow Mailtrap's per-second throttle errors (SMTP only)."""

    try:
        await send_operation
    except aiosmtplib.errors.SMTPDataError as exc:
        detail = getattr(exc, "message", "")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="ignore")
        detail_text = detail or str(exc)

        if (
            exc.code == MAILTRAP_RATE_LIMIT_CODE
            and MAILTRAP_RATE_LIMIT_HINT in detail_text
        ):
            logger.warning(
                "Mailtrap rate limit while sending %s. Email suppressed (see %s)",
                context,
                MAILTRAP_RATE_LIMIT_DOC,
            )
            return
        raise


def get_email_template(
    title: str,
    content: str,
    button_text: Optional[str] = None,
    button_link: Optional[str] = None,
    footer_text: Optional[str] = None,
    logo_url: Optional[str] = None,
    hero_title: Optional[str] = None,
    hero_subtitle: Optional[str] = None,
    secondary_button_text: Optional[str] = None,
    secondary_button_link: Optional[str] = None,
) -> str:
    """
    Shared HTML shell for all transactional emails (password reset, invites, etc.).

    Dark FYPilot-branded layout. ``title`` is the card headline; ``hero_title`` overrides
    the large hero line (defaults to ``title``).
    """
    company_name = settings.email_company_name
    safe_company = escape(company_name)
    safe_title = escape(title)
    hero_h2 = escape(hero_title) if hero_title else safe_title
    default_sub = (
        "Build smarter, faster, and better with tools designed for your "
        "Final Year Project workflow."
    )
    hero_p = escape(hero_subtitle) if hero_subtitle else default_sub

    logo = logo_url or settings.email_logo_url
    logo_block = ""
    if logo:
        logo_block = f'<img src="{escape(logo)}" alt="{safe_company}" style="max-height:40px;margin-bottom:12px;" />'

    primary_btn = ""
    if button_text and button_link:
        safe_btn = escape(button_text)
        primary_btn = f"""
<table cellpadding="0" cellspacing="0" border="0" style="margin:24px 0 12px;">
<tr>
<td align="center" style="background:#6D28D9;border-radius:999px;">
<a href="{escape(button_link, quote=True)}"
   style="display:inline-block;padding:14px 28px;color:#FFFFFF;text-decoration:none;font-weight:600;font-size:15px;">
{safe_btn}
</a>
</td>
</tr>
</table>"""

    secondary_btn = ""
    if secondary_button_text and secondary_button_link:
        sbt = escape(secondary_button_text)
        secondary_btn = f"""
<table cellpadding="0" cellspacing="0" border="0" style="margin:0 0 8px;">
<tr>
<td align="center" style="background:#1E293B;border-radius:999px;border:1px solid #334155;">
<a href="{escape(secondary_button_link, quote=True)}"
   style="display:inline-block;padding:12px 26px;color:#E6EAF0;text-decoration:none;font-weight:600;font-size:14px;">
{sbt}
</a>
</td>
</tr>
</table>"""

    support = settings.email_support_contact or ""
    support_line = (
        f"<br><br>Need help? {escape(support)}"
        if support
        else "<br><br>Need help? Contact your course administrator."
    )
    footer_main = escape(
        footer_text
        or f"© {datetime.utcnow().year} {company_name}. All rights reserved."
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{safe_title} · {safe_company}</title>
<!--[if mso]><style type="text/css">body,table,td{{font-family:Arial,sans-serif!important;}}</style><![endif]-->
</head>
<body style="margin:0;padding:0;background:#0B0F13;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#E6EAF0;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">
<tr>
<td align="center" style="padding:40px 20px;">
<table width="600" cellpadding="0" cellspacing="0" border="0" role="presentation" style="max-width:600px;width:100%;background:#0F141A;border-radius:24px;overflow:hidden;border:1px solid #1F2937;">
<tr>
<td align="center" style="padding:28px 32px;background:linear-gradient(135deg,#6D28D9 0%,#8B5CF6 100%);">
{logo_block}
<h1 style="margin:0;font-size:30px;font-weight:700;color:#FFFFFF;letter-spacing:-0.5px;">{safe_company}</h1>
<p style="margin:10px 0 0;color:#EDE9FE;font-size:15px;">Your AI-Powered Project Assistant</p>
</td>
</tr>
<tr>
<td style="padding:36px 36px 16px;">
<h2 style="margin:0 0 14px;font-size:26px;line-height:1.25;color:#FFFFFF;">{hero_h2}</h2>
<p style="margin:0;color:#A7B0BB;font-size:16px;line-height:1.75;">{hero_p}</p>
</td>
</tr>
<tr>
<td style="padding:8px 36px 36px;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#141A22;border-radius:20px;border:1px solid #1E293B;">
<tr>
<td style="padding:28px 28px 32px;">
<h3 style="margin:0 0 14px;color:#FFFFFF;font-size:20px;line-height:1.3;">{safe_title}</h3>
<div style="color:#A7B0BB;font-size:15px;line-height:1.75;">
{content}
</div>
{primary_btn}
{secondary_btn}
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td align="center" style="padding:28px 32px;border-top:1px solid #1F2937;">
<p style="color:#6B7280;font-size:13px;line-height:1.7;margin:0;">
{footer_main}
{support_line}
</p>
<p style="margin:16px 0 0;font-size:12px;color:#4B5563;">This email was sent by {safe_company}.</p>
</td>
</tr>
</table>
</td>
</tr>
</table>
</body>
</html>"""


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
    Default dev mailer — Mailtrap SMTP (inbox capture at mailtrap.io).

    Set ``MAILER_PROVIDER=mailtrap`` and ``MAILTRAP_SMTP_USER`` / ``MAILTRAP_SMTP_PASS``.
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


# ---------------------------------------------------------------------------
# Resend HTTP mailer — commented for later; use MAILER_PROVIDER=mailtrap now.
# Uncomment class + get_mailer() branch and restore RESEND_* in config when ready.
# ---------------------------------------------------------------------------
# class ResendMailer:
#     """Transactional email via Resend HTTP API (https://resend.com)."""
#     _API = "https://api.resend.com/emails"
#
#     def __init__(self) -> None:
#         if not settings.resend_api_key or not settings.resend_from_email:
#             raise ValueError(
#                 "Resend requires RESEND_API_KEY and RESEND_FROM_EMAIL in environment"
#             )
#
#     async def send(self, to: str, subject: str, html_body: str) -> None:
#         import httpx
#
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             response = await client.post(
#                 self._API,
#                 headers={
#                     "Authorization": f"Bearer {settings.resend_api_key}",
#                     "Content-Type": "application/json",
#                 },
#                 json={
#                     "from": settings.resend_from_email,
#                     "to": [to],
#                     "subject": subject,
#                     "html": html_body,
#                 },
#             )
#             if response.status_code >= 400:
#                 logger.error(
#                     "Resend API error %s: %s",
#                     response.status_code,
#                     response.text[:500],
#                 )
#                 response.raise_for_status()


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
    Factory to choose the correct mailer based on ``MAILER_PROVIDER``.

    Active: ``mailtrap`` (default), ``ethereal``, ``sendgrid``.
    Resend: see commented ``ResendMailer`` above + add ``elif provider == "resend"``.
    """
    provider = settings.mailer_provider.lower()
    # if provider == "resend":
    #     return ResendMailer()
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

    safe_name = escape(user_name)
    safe_link = escape(reset_link, quote=True)
    safe_link_text = escape(reset_link)

    content = f"""
    <p style="margin: 0 0 16px;">Hello <strong>{safe_name}</strong>,</p>

    <p style="margin: 0 0 16px;">
        We received a request to reset your password for your {escape(settings.email_company_name)} account.
        If you made this request, use the button below.
    </p>

    <div style="background:rgba(245,158,11,0.12);border-left:4px solid #F59E0B;padding:16px;margin:20px 0;border-radius:10px;">
        <p style="margin:0 0 8px;font-weight:600;color:#FCD34D;">Security</p>
        <ul style="margin:0;padding-left:20px;color:#CBD5E1;font-size:14px;line-height:1.65;">
            <li style="margin-bottom:8px;">This link expires in <strong>1 hour</strong>.</li>
            <li style="margin-bottom:8px;">If you did not request a reset, ignore this email.</li>
            <li>Your password stays the same until you complete the reset.</li>
        </ul>
    </div>

    <p style="margin:20px 0 0;font-size:13px;color:#94A3B8;line-height:1.6;">
        If the button does not work, copy this link:<br>
        <a href="{safe_link}" style="color:#A78BFA;word-break:break-all;">{safe_link_text}</a>
    </p>
    """

    html_body = get_email_template(
        title="Password Reset",
        content=content,
        button_text="Reset my password",
        button_link=reset_link,
        footer_text="If you didn't request this password reset, you can safely ignore this email.",
        hero_title="Reset your password",
        hero_subtitle="We will get you back into your account in just a few clicks.",
    )

    mailer = get_mailer()
    await _send_with_rate_limit_guard(
        mailer.send(to_email, subject, html_body),
        context="password reset email",
    )


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

    safe_invitee = escape(invitee_name)
    safe_inviter = escape(inviter_name)
    a_link = escape(accept_link, quote=True)
    r_link = escape(reject_link, quote=True)
    a_text = escape(accept_link)
    r_text = escape(reject_link)

    content = f"""
    <p style="margin: 0 0 16px;">Hello <strong>{safe_invitee}</strong>,</p>

    <p style="margin: 0 0 16px;">
        <strong>{safe_inviter}</strong> invited you to join their <strong>Final Year Project</strong> group on {escape(settings.email_company_name)}.
    </p>

    <div style="background:rgba(56,189,248,0.1);border-left:4px solid #38BDF8;padding:16px;margin:20px 0;border-radius:10px;">
        <p style="margin:0 0 8px;font-weight:600;color:#7DD3FC;">Invitation details</p>
        <ul style="margin:0;padding-left:20px;color:#CBD5E1;font-size:14px;line-height:1.65;">
            <li style="margin-bottom:8px;">Expires in <strong>7 days</strong>.</li>
            <li style="margin-bottom:8px;">Accept or decline using the buttons below.</li>
            <li>Your membership only changes if you accept.</li>
        </ul>
    </div>

    <p style="margin:16px 0 0;font-size:13px;color:#94A3B8;line-height:1.65;">
        <strong style="color:#E6EAF0;">Accept:</strong><br>
        <a href="{a_link}" style="color:#A78BFA;word-break:break-all;">{a_text}</a>
    </p>
    <p style="margin:12px 0 0;font-size:13px;color:#94A3B8;line-height:1.65;">
        <strong style="color:#E6EAF0;">Decline:</strong><br>
        <a href="{r_link}" style="color:#A78BFA;word-break:break-all;">{r_text}</a>
    </p>
    """

    html_body = get_email_template(
        title="Group invitation",
        content=content,
        button_text="Accept invitation",
        button_link=accept_link,
        secondary_button_text="Decline invitation",
        secondary_button_link=reject_link,
        footer_text="If you didn't expect this invitation, you can safely ignore this email.",
        hero_title="You are invited",
        hero_subtitle="Join your teammates and start collaborating on your FYP.",
    )

    mailer = get_mailer()
    await _send_with_rate_limit_guard(
        mailer.send(to_email, subject, html_body),
        context="group invitation email",
    )


async def send_supervisor_accepted_email(
    to_email: str, project_name: str, supervisor_name: str, role: str
):
    """
    Send email to group members when supervisor accepts their request.

    Args:
        to_email (str): Group member's email address
        project_name (str): Name of the project
        supervisor_name (str): Name of the supervisor who accepted
        role (str): Role accepted (supervisor or cosupervisor)
    """
    subject = f"Supervisor Request Accepted - {settings.email_company_name}"
    role_text = "Primary Supervisor" if role == "supervisor" else "Co-Supervisor"
    safe_proj = escape(project_name)
    safe_sup = escape(supervisor_name)

    content = f"""
    <p style="margin: 0 0 16px;">Hi there,</p>

    <p style="margin: 0 0 16px;">
        <strong>{safe_sup}</strong> accepted your group's request to be the <strong>{role_text}</strong> for <strong>{safe_proj}</strong>.
    </p>

    <div style="background:rgba(16,185,129,0.12);border-left:4px solid #10B981;padding:16px;margin:20px 0;border-radius:10px;">
        <p style="margin:0 0 8px;font-weight:600;color:#6EE7B7;">Status: Accepted</p>
        <ul style="margin:0;padding-left:20px;color:#CBD5E1;font-size:14px;line-height:1.65;">
            <li style="margin-bottom:8px;"><strong style="color:#E6EAF0;">Project:</strong> {safe_proj}</li>
            <li style="margin-bottom:8px;"><strong style="color:#E6EAF0;">Supervisor:</strong> {safe_sup}</li>
            <li><strong style="color:#E6EAF0;">Role:</strong> {role_text}</li>
        </ul>
    </div>

    <p style="margin: 0 0 16px;">You can start collaborating with your supervisor right away.</p>
    """

    html_body = get_email_template(
        title="Supervisor accepted",
        content=content,
        footer_text="Congratulations on forming your complete team!",
        hero_title="Great news",
        hero_subtitle="Your supervisor request was accepted.",
    )

    mailer = get_mailer()
    await _send_with_rate_limit_guard(
        mailer.send(to_email, subject, html_body),
        context="supervisor request accepted email",
    )


async def send_supervisor_rejected_email(
    to_email: str, project_name: str, supervisor_name: str, role: str
):
    """
    Send email to group members when supervisor rejects their request.

    Args:
        to_email (str): Group member's email address
        project_name (str): Name of the project
        supervisor_name (str): Name of the supervisor who rejected
        role (str): Role requested (supervisor or cosupervisor)
    """
    subject = f"Supervisor Request Declined - {settings.email_company_name}"
    role_text = "Primary Supervisor" if role == "supervisor" else "Co-Supervisor"
    safe_proj = escape(project_name)
    safe_sup = escape(supervisor_name)

    content = f"""
    <p style="margin: 0 0 16px;">Hi there,</p>

    <p style="margin: 0 0 16px;">
        <strong>{safe_sup}</strong> declined your group's request to be the <strong>{role_text}</strong> for <strong>{safe_proj}</strong>.
    </p>

    <div style="background:rgba(239,68,68,0.12);border-left:4px solid #F87171;padding:16px;margin:20px 0;border-radius:10px;">
        <p style="margin:0 0 8px;font-weight:600;color:#FCA5A5;">Status: Declined</p>
        <ul style="margin:0;padding-left:20px;color:#CBD5E1;font-size:14px;line-height:1.65;">
            <li style="margin-bottom:8px;"><strong style="color:#E6EAF0;">Project:</strong> {safe_proj}</li>
            <li style="margin-bottom:8px;"><strong style="color:#E6EAF0;">Supervisor:</strong> {safe_sup}</li>
            <li><strong style="color:#E6EAF0;">Role:</strong> {role_text}</li>
        </ul>
    </div>

    <p style="margin: 0 0 16px;">You can explore other supervisors from the platform.</p>
    """

    html_body = get_email_template(
        title="Supervisor declined",
        content=content,
        footer_text="Keep exploring other supervisor options for your project.",
        hero_title="Update on your request",
        hero_subtitle="Your supervisor request was not accepted this time.",
    )

    mailer = get_mailer()
    await _send_with_rate_limit_guard(
        mailer.send(to_email, subject, html_body),
        context="supervisor request rejected email",
    )
