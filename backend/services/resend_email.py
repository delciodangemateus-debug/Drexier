"""Transactional authentication emails sent with Resend."""

import html
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("drexier.resend")


@dataclass(frozen=True)
class ResendConfig:
    api_key: str
    from_email: str


def get_resend_config() -> ResendConfig:
    return ResendConfig(
        api_key=os.getenv("RESEND_API_KEY", "").strip(),
        from_email=os.getenv("RESEND_FROM_EMAIL", "").strip(),
    )


def _base_template(title: str, name: str, body: str) -> str:
    safe_name = html.escape(name)
    safe_title = html.escape(title)
    app_name = html.escape(os.getenv("APP_NAME", "Drexier").strip() or "Drexier")
    return f"""
<!doctype html>
<html lang="pt">
  <body style="margin:0;background:#f5f7fb;font-family:Arial,sans-serif;color:#202b3c">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
      <tr><td align="center" style="padding:32px 16px">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#fff;border-radius:12px;padding:32px">
          <tr><td>
            <p style="margin:0 0 24px;font-size:20px;font-weight:bold;color:#5a34a4">{app_name}</p>
            <h1 style="margin:0 0 16px;font-size:24px">{safe_title}</h1>
            <p style="margin:0 0 16px">Olá, {safe_name}.</p>
            {body}
            <p style="margin:24px 0 0;color:#667085;font-size:13px">Esta mensagem foi enviada automaticamente pelo {app_name}.</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
""".strip()


def _send_email(to_email: str, subject: str, html_body: str) -> dict:
    config = get_resend_config()
    if not config.api_key or not config.from_email:
        logger.warning("Email Resend não enviado: configure RESEND_API_KEY e RESEND_FROM_EMAIL.")
        return {"status": "skipped", "reason": "resend_not_configured"}

    try:
        import resend

        resend.api_key = config.api_key
        response = resend.Emails.send({
            "from": config.from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        })
        logger.info("Email Resend enviado para %s", to_email)
        return {"status": "sent", "id": response.get("id")}
    except Exception as exc:
        logger.exception("Falha ao enviar email Resend para %s: %s", to_email, exc)
        return {"status": "failed", "error": str(exc)}


def send_account_created_email(to_email: str, name: str) -> dict:
    body = """
      <p style="margin:0 0 16px">A sua conta foi criada com sucesso no Drexier.</p>
      <p style="margin:0">Já pode iniciar sessão e começar a configurar o seu assistente.</p>
    """
    return _send_email(
        to_email,
        "Conta criada com sucesso no Drexier",
        _base_template("A sua conta está pronta", name, body),
    )


def send_login_confirmation_email(
    to_email: str,
    name: str,
    *,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    login_time = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    safe_ip = html.escape(ip_address or "não disponível")
    safe_agent = html.escape((user_agent or "não disponível")[:300])
    body = f"""
      <p style="margin:0 0 16px">Foi iniciado sessão na sua conta Drexier.</p>
      <table role="presentation" style="width:100%;border-collapse:collapse;background:#f8fafc" cellpadding="12">
        <tr><td style="border-bottom:1px solid #e8edf4"><strong>Data</strong></td><td style="border-bottom:1px solid #e8edf4">{login_time}</td></tr>
        <tr><td style="border-bottom:1px solid #e8edf4"><strong>Endereço IP</strong></td><td style="border-bottom:1px solid #e8edf4">{safe_ip}</td></tr>
        <tr><td><strong>Dispositivo/Navegador</strong></td><td>{safe_agent}</td></tr>
      </table>
      <p style="margin:16px 0 0">Se não fez este acesso, recomendamos alterar imediatamente a sua senha.</p>
    """
    return _send_email(
        to_email,
        "Confirmação de início de sessão no Drexier",
        _base_template("Novo início de sessão", name, body),
    )
