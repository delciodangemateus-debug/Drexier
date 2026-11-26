import asyncio, json, logging, os, re
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, Request, Form
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from backend.database import init_db, connect, is_test_environment
from backend.supabase_client import get_supabase_status
from backend.auth import (
    create_password_reset_token,
    decode_password_reset_token,
    create_booking_token,
    decode_booking_token,
    hash_password,
    verify_password,
    create_token,
    decode_token,
    get_token_claims,
)
from backend.services.rate_limiter import check_rate_limit
from backend.services.agent import DEFAULT_AGENT_PERSONALITY, draft_reply, effective_agent_instructions
from backend.services.analytics import (
    analyze_approaches,
    analyze_products_and_services,
    daily_acquisitions,
    generate_strategic_ai_report,
    generate_full_analysis_report,
)
from backend.services.email_service import (
    BUSINESS_TIMEZONE,
    EmailTokenExpiredError,
    sync_emails_for_user,
    process_confirmation_action,
    send_ai_booking_reminder,
    send_owner_reply,
    extract_scheduled_at,
    generate_booking_options,
    handle_booking_selection,
)
from backend.services.resend_email import (
    get_resend_config,
    is_resend_test_sender,
    send_auth_code_email,
    send_account_created_email,
    send_login_confirmation_email,
)
from backend.services.auth_challenge import (
    AuthCodeLocked,
    AuthChallengeStoreError,
    create_auth_challenge,
    consume_auth_challenge,
    get_auth_code_lockout_seconds,
    invalidate_auth_challenge,
)
from backend.services.billing_service import (
    is_subscription_active,
    get_user_subscription_status,
    schedule_subscription_cancellation,
)
from backend.routers.email import router as email_router
from backend.routers.billing import router as billing_router
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("drexier.main")
ROOT = Path(__file__).resolve().parent.parent

async def background_email_worker():
    """
    Worker contínuo em background para funcionamento pleno da automação:
    Verifica a caixa de entrada dos emails integrados de todos os utilizadores,
    gera respostas inteligentes com a IA Drexier e responde de forma 100% real.
    """
    logger.info("Worker contínuo de atendimento por e-mail via IA Drexier iniciado.")
    await asyncio.sleep(2)
    while True:
        try:
            with connect() as c:
                active_users = c.execute(
                    "SELECT DISTINCT user_id FROM email_integrations WHERE status = 'connected' AND provider = 'google'"
                ).fetchall()
            
            for row in active_users:
                uid = row["user_id"]
                # Validação SaaS: processa automações apenas se o pagamento estiver em dia
                if not is_subscription_active(uid):
                    logger.debug(f"[SaaS Paywall] Automação suspensa para user {uid}: assinatura inativa ou pendente.")
                    continue
                try:
                    processed = await sync_emails_for_user(uid)
                    if processed:
                        logger.info(f"[IA Drexier] {len(processed)} e-mail(s) real(is) processado(s) e respondido(s) para user_id {uid}.")
                except EmailTokenExpiredError as te:
                    logger.warning(f"[IA Drexier] Token expirado para user {uid}. Agente pausado aguardando reconexão: {te}")
                except Exception as ex:
                    logger.warning(f"[IA Drexier] Erro na verificação periódica de e-mails para utilizador {uid}: {ex}")
        except Exception as e:
            logger.error(f"[IA Drexier] Erro no ciclo do worker de e-mails: {e}")
        
        await asyncio.sleep(15)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # SEC-04: Verificação de configuração HTTPS obrigatória em produção
    if (os.getenv("APP_ENV") == "production" or os.getenv("ENVIRONMENT") == "production") and not is_test_environment():
        pub_url = os.getenv("PUBLIC_URL") or os.getenv("APP_URL")
        if not pub_url or not pub_url.startswith("https://"):
            raise RuntimeError("Em ambiente de produção, PUBLIC_URL deve ser uma URL HTTPS válida!")
    worker_task = asyncio.create_task(background_email_worker())
    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except (asyncio.CancelledError, Exception):
            pass

app = FastAPI(title="Drexier API", version="0.1.0", lifespan=lifespan)
# Roteadores do sistema
app.include_router(billing_router)
app.include_router(email_router)

# SEC-02: Configuração estrita de CORS com origens autorizadas
_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
if _raw_origins:
    ALLOWED_ORIGINS = [orig.strip() for orig in _raw_origins.split(",") if orig.strip()]
else:
    ALLOWED_ORIGINS = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]
    _pub = os.getenv("PUBLIC_URL") or os.getenv("APP_URL")
    if _pub:
        ALLOWED_ORIGINS.append(_pub.rstrip("/"))

is_prod_env = (os.getenv("APP_ENV") == "production" or os.getenv("ENVIRONMENT") == "production")
cors_origins = ALLOWED_ORIGINS if (is_prod_env or not is_test_environment()) else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "x-goog-api-key", "Accept"],
)


# SEC-11: Middleware global de cabeçalhos HTTP de segurança
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
    if request.url.scheme == "https" or forwarded_proto == "https" or is_prod_env:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://js.stripe.com https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.stripe.com https://*.supabase.co; "
        "frame-src https://js.stripe.com; "
        "frame-ancestors 'self'; "
        "object-src 'none'; "
        "base-uri 'self';"
    )
    return response

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return await http_exception_handler(request, exc)
    logger.error(f"Erro interno não tratado: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Ocorreu um erro. Tente novamente."}
    )

app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")

@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")

@app.get("/styles.css")
def get_styles():
    return FileResponse(ROOT / "frontend" / "styles.css")

@app.get("/app.js")
def get_app_js():
    return FileResponse(ROOT / "frontend" / "app.js")

@app.get("/i18n.js")
def get_i18n_js():
    return FileResponse(ROOT / "frontend" / "i18n.js")

@app.get("/booking")
@app.get("/agendamento")
def get_booking_page():
    booking_file = ROOT / "frontend" / "booking.html"
    if not booking_file.exists():
        booking_file = ROOT / "dist" / "booking.html"
    return FileResponse(booking_file)


def _booking_confirm_success_html(res: dict) -> str:
    """Página HTML simples mostrada após o cliente confirmar uma opção de marcação."""
    mode = res.get("mode", "full")
    cname = res.get("customer_name", "")
    date_str = res.get("date_str", res.get("slot_label", ""))
    if mode == "full":
        icon, title = "✅", "Marcação Confirmada!"
        desc = "A sua marcação foi registada no quadro de agendamentos do negócio."
        status_text, status_color = "Confirmada", "#10b981"
        note = "Enviámos um e-mail de confirmação com todos os detalhes."
    else:
        icon, title = "📋", "Pedido de Marcação Enviado!"
        desc = "O seu pedido foi recebido e aguarda validação da equipa."
        status_text, status_color = "Aguardando Validação", "#f59e0b"
        note = "Assim que a marcação for validada, receberá um e-mail de confirmação."
    import html as _html
    return f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>{title}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;}}
    body{{background:#f3f4f6;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px;}}
    .card{{background:#fff;border-radius:16px;padding:40px 32px;max-width:460px;width:100%;text-align:center;box-shadow:0 20px 25px -5px rgba(0,0,0,.1);}}
    .icon{{font-size:56px;margin-bottom:20px;}}
    h1{{font-size:22px;color:#111827;margin-bottom:12px;}}
    .desc{{font-size:15px;color:#6b7280;line-height:1.6;margin-bottom:24px;}}
    .badge{{display:inline-block;background:{status_color}20;color:{status_color};border-radius:9999px;padding:6px 18px;font-size:13px;font-weight:600;margin-bottom:20px;}}
    .details{{background:#f9fafb;border-radius:10px;padding:16px;text-align:left;margin-top:4px;}}
    .row{{font-size:14px;color:#374151;margin-bottom:8px;}}
    .row:last-child{{margin-bottom:0;}}
    .lbl{{font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:2px;}}
    .note{{font-size:13px;color:#93c5fd;margin-top:20px;}}
  </style>
</head>
<body>
<div class="card">
  <div class="icon">{icon}</div>
  <h1>{title}</h1>
  <p class="desc">{desc}</p>
  <span class="badge">{status_text}</span>
  <div class="details">
    {'<div class="row"><span class="lbl">Nome</span><strong>' + _html.escape(cname) + '</strong></div>' if cname else ''}
    {'<div class="row"><span class="lbl">Data e Hora</span><strong>' + _html.escape(date_str) + '</strong></div>' if date_str else ''}
  </div>
  <p class="note">{note}</p>
</div>
</body>
</html>"""


def _booking_confirm_error_html(message: str = "") -> str:
    """Página HTML de erro para confirmação de marcação."""
    import html as _html
    return f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Erro — Agendamento</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}}
    body{{background:#f3f4f6;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px;}}
    .card{{background:#fff;border-radius:16px;padding:40px 32px;max-width:460px;width:100%;text-align:center;box-shadow:0 20px 25px -5px rgba(0,0,0,.1);}}
    .icon{{font-size:56px;margin-bottom:20px;}}
    h1{{font-size:22px;color:#111827;margin-bottom:12px;}}
    .desc{{font-size:15px;color:#6b7280;line-height:1.6;}}
    .err{{font-size:13px;color:#ef4444;margin-top:12px;}}
  </style>
</head>
<body>
<div class="card">
  <div class="icon">⚠️</div>
  <h1>Não foi possível confirmar</h1>
  <p class="desc">O link de agendamento é inválido, já foi utilizado ou expirou.</p>
  {'<p class="err">' + _html.escape(message) + '</p>' if message else ''}
</div>
</body>
</html>"""


@app.get("/api/booking/confirm")
async def confirm_booking_direct(
    request: Request,
    token: str,
    slot_id: str = "",
    slot_label: str = "",
    scheduled_at: str = "",
    customer_name: Optional[str] = None,
):
    """
    Confirma uma opção de marcação a partir do link direto enviado no e-mail.
    O cliente chega aqui ao clicar num dos cards de horário no próprio Gmail/email.
    Devolve uma página HTML simples de confirmação — sem redirecionamentos adicionais.
    """
    check_rate_limit(request, action="booking_confirm", max_requests=20, window_seconds=60)
    data = decode_booking_token(token)
    if not data:
        return HTMLResponse(
            content=_booking_confirm_error_html("Link inválido ou expirado."),
            status_code=400,
        )
    try:
        res = await handle_booking_selection(
            user_id=data["user_id"],
            contact_id=data["contact_id"],
            customer_email=data["email"],
            customer_name=customer_name or data.get("name") or "",
            slot_label=slot_label,
            scheduled_at=scheduled_at,
            notes="",
        )
        return HTMLResponse(content=_booking_confirm_success_html(res))
    except Exception as exc:
        logger.error(f"[Booking Confirm] Erro ao processar marcação: {exc}")
        return HTMLResponse(
            content=_booking_confirm_error_html(),
            status_code=500,
        )

def current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sessão necessária.")
    raw_token = authorization[7:]
    uid = decode_token(raw_token)
    if not uid:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    with connect() as c:
        row = c.execute("SELECT id,name,email,business_type,business_description,language,agent_instructions,agent_adopted_style,mandatory_responses,token_version FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        raise HTTPException(401, "Conta não encontrada.")
    user_data = dict(row)
    # SEC-05: Invalidação imediata de sessões se o token carregar versão revogada
    claims = get_token_claims(raw_token)
    if claims and "v" in claims and user_data.get("token_version") is not None:
        if int(claims["v"]) != int(user_data["token_version"]):
            raise HTTPException(401, "Sessão revogada. Por favor, inicie sessão novamente.")
    return user_data

def user_id(user=Depends(current_user)):
    return user["id"]


def require_active_subscription(user=Depends(current_user)):
    """
    Dependência FastAPI de Paywall SaaS — Ponto Crítico de Segurança.
    Bloqueia TODOS os endpoints de escrita / IA / integrações se o utilizador
    não possuir uma assinatura Stripe ativa e com pagamento em dia.
    Retorna HTTP 402 Payment Required para que o frontend redirecione para Faturação.
    Login, signup, leitura de dados, billing e webhook permanecem sempre acessíveis.
    """
    if not is_subscription_active(user["id"]):
        raise HTTPException(
            status_code=402,
            detail={
                "code": "SUBSCRIPTION_REQUIRED",
                "message": (
                    "Acesso bloqueado. O Plano Business (59€/mês) é necessário para utilizar "
                    "esta funcionalidade. Ative a sua subscrição na aba Faturação."
                )
            }
        )

class Signup(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str
    business_type: str = Field(min_length=2, max_length=100)

class Login(BaseModel):
    email: EmailStr
    password: str

class AuthCode(BaseModel):
    challenge_id: str = Field(min_length=32, max_length=64)
    code: str = Field(pattern=r"^[0-9]{6}$")

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetComplete(BaseModel):
    reset_token: str = Field(min_length=1)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str

class BusinessInfoIn(BaseModel):
    kind: str
    title: str = Field(min_length=1, max_length=250)
    content: str = Field(default="", max_length=500000)
    metadata: dict = {}

class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    business_type: str = Field(default="", max_length=120)
    business_description: str = Field(default="", max_length=5000)
    language: str = Field(default="Português", max_length=50)

class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=8, max_length=128)

class AutomationLevelIn(BaseModel):
    level: str = Field(pattern="^(full|semi|disabled)$")

class BookingSelectIn(BaseModel):
    token: str
    slot_label: str
    scheduled_at: str
    customer_name: Optional[str] = None
    notes: Optional[str] = None

class AgentSettings(BaseModel):
    instructions: str = ""
    mandatory_responses: dict = {}

class AdoptApproachIn(BaseModel):
    style: str = Field(min_length=1, max_length=6000)

class IncomingMessage(BaseModel):
    contact_key: str = Field(min_length=1, max_length=200)
    customer_name: str = ""
    message: str = Field(min_length=1, max_length=12000)

class ConversionIn(BaseModel):
    request_type: str = "purchase_or_booking"
    details: str = ""

class OwnerReplyIn(BaseModel):
    message: str = Field(min_length=1, max_length=10000)

class ConversionActionIn(BaseModel):
    action: str = Field(pattern="^(confirm|confirm_manual|reject|treated)$")
    custom_note: Optional[str] = ""

def _start_auth_challenge(email: str, name: str, purpose: str, payload: dict):
    try:
        retry_after = get_auth_code_lockout_seconds(email, purpose)
    except AuthChallengeStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "AUTH_CODE_LOCKED",
                "message": "Foram feitas 5 tentativas inválidas. Tente novamente após 15 minutos.",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    try:
        challenge_id, code = create_auth_challenge(purpose, payload)
    except AuthChallengeStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    result = send_auth_code_email(email, name, code, purpose)
    if result.get("status") != "sent":
        invalidate_auth_challenge(challenge_id)
        if result.get("status") == "skipped":
            detail = "O envio de email não está configurado. Configure RESEND_API_KEY e RESEND_FROM_EMAIL."
        elif is_resend_test_sender(get_resend_config().from_email):
            detail = (
                "O remetente de teste do Resend só permite enviar para o email da própria conta Resend. "
                "Para enviar códigos a outros usuários, configure RESEND_FROM_EMAIL com um endereço "
                "de um domínio verificado no Resend."
            )
        else:
            detail = (
                "O Resend não conseguiu enviar o código. Verifique se a chave API é válida "
                "e se o endereço/domínio remetente está autorizado no Resend."
            )
        raise HTTPException(
            status_code=503,
            detail=detail,
        )
    return challenge_id


def _validate_password_strength(password: str) -> None:
    """Valida requisitos de segurança e entropia da palavra-passe."""
    if len(password) < 8:
        raise HTTPException(400, "A senha deve conter pelo menos 8 caracteres.")
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(400, "A senha não pode exceder 72 caracteres.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise HTTPException(400, "A senha deve conter pelo menos uma letra e um número.")


def _challenge_response(challenge_id: str, email: str):
    return {
        "challenge_required": True,
        "challenge_id": challenge_id,
        "email": email,
        "expires_in": 10 * 60,
    }

@app.post("/api/auth/signup")
def signup(data: Signup, request: Request):
    check_rate_limit(request, action="signup", max_requests=5, window_seconds=600, custom_key=data.email.lower())
    if data.password != data.confirm_password:
        raise HTTPException(400, "As senhas não coincidem.")
    _validate_password_strength(data.password)
    email = data.email.lower()
    challenge_id = _start_auth_challenge(
        email,
        data.name.strip(),
        "signup",
        {
            "name": data.name.strip(),
            "email": email,
            "password_hash": hash_password(data.password),
            "business_type": data.business_type,
        },
    )
    return _challenge_response(challenge_id, email)

@app.post("/api/auth/login")
def login(data: Login, request: Request):
    check_rate_limit(request, action="login", max_requests=5, window_seconds=60, custom_key=data.email.lower())
    with connect() as c:
        row = c.execute(
            "SELECT id,name,email,password_hash,token_version FROM users WHERE email=?",
            (data.email.lower(),),
        ).fetchone()
    if not row or not verify_password(data.password, row["password_hash"]):
        raise HTTPException(401, "Email ou senha incorretos.")

    challenge_id = _start_auth_challenge(
        row["email"],
        row["name"],
        "login",
        {
            "user_id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "token_version": row["token_version"] if "token_version" in row.keys() and row["token_version"] is not None else 1,
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        },
    )
    return _challenge_response(challenge_id, row["email"])


@app.post("/api/auth/password-reset")
def request_password_reset(data: PasswordResetRequest, request: Request):
    check_rate_limit(request, action="password_reset", max_requests=3, window_seconds=600, custom_key=data.email.lower())
    email = data.email.lower()
    with connect() as c:
        row = c.execute(
            "SELECT id,name,email FROM users WHERE email=?",
            (email,),
        ).fetchone()

    if not row:
        return {
            "challenge_required": False,
            "message": "Se existir uma conta para este email, receberá um código de recuperação.",
        }

    challenge_id = _start_auth_challenge(
        row["email"],
        row["name"],
        "password_reset",
        {"user_id": row["id"], "email": row["email"], "name": row["name"]},
    )
    return _challenge_response(challenge_id, row["email"])

@app.post("/api/auth/verify")
def verify_auth_code(data: AuthCode, request: Request):
    # SEC H10: Rate limiting em tentativas de validação de código OTP
    check_rate_limit(request, action="verify", max_requests=20, window_seconds=60, custom_key=data.challenge_id)
    try:
        signup_payload = consume_auth_challenge(data.challenge_id, data.code, "signup")
        login_payload = None
        if not signup_payload:
            login_payload = consume_auth_challenge(data.challenge_id, data.code, "login")
        password_reset_payload = None
        if not signup_payload and not login_payload:
            password_reset_payload = consume_auth_challenge(
                data.challenge_id, data.code, "password_reset"
            )
    except AuthCodeLocked as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "AUTH_CODE_LOCKED",
                "message": str(exc),
                "retry_after": exc.retry_after,
            },
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except AuthChallengeStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if signup_payload:
        with connect() as c:
            try:
                cur = c.execute(
                    "INSERT INTO users(name,email,password_hash,business_type) VALUES(?,?,?,?)",
                    (
                        signup_payload["name"],
                        signup_payload["email"],
                        signup_payload["password_hash"],
                        signup_payload["business_type"],
                    ),
                )
                uid = cur.lastrowid
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(409, "Este email já está registado.")
                raise
        send_account_created_email(signup_payload["email"], signup_payload["name"])
        return {"token": create_token(uid), "user_id": uid}

    if login_payload:
        send_login_confirmation_email(
            login_payload["email"],
            login_payload["name"],
            ip_address=login_payload.get("ip_address"),
            user_agent=login_payload.get("user_agent"),
        )
        with connect() as c:
            u_row = c.execute("SELECT token_version FROM users WHERE id=?", (login_payload["user_id"],)).fetchone()
            curr_v = (
                u_row["token_version"]
                if (u_row and "token_version" in u_row.keys() and u_row["token_version"] is not None)
                else login_payload.get("token_version", 1)
            )
        return {"token": create_token(login_payload["user_id"], token_version=curr_v), "user_id": login_payload["user_id"]}

    if password_reset_payload:
        return {
            "password_reset_required": True,
            "reset_token": create_password_reset_token(password_reset_payload["user_id"]),
        }

    raise HTTPException(400, "Código inválido ou expirado.")


@app.post("/api/auth/password-reset/complete")
def complete_password_reset(data: PasswordResetComplete):
    if data.password != data.confirm_password:
        raise HTTPException(400, "As senhas não coincidem.")
    _validate_password_strength(data.password)

    user_id = decode_password_reset_token(data.reset_token)
    if not user_id:
        raise HTTPException(401, "O processo de recuperação expirou. Solicite um novo código.")

    import hashlib as _hashlib
    token_hash = _hashlib.sha256(data.reset_token.encode()).hexdigest()

    with connect() as c:
        # SEC C2: Persistência de tokens de recuperação usados na base de dados (sobrevive a restarts)
        c.execute("CREATE TABLE IF NOT EXISTS used_reset_tokens (token_hash TEXT PRIMARY KEY, used_at TEXT NOT NULL)")
        already_used = c.execute("SELECT 1 FROM used_reset_tokens WHERE token_hash=?", (token_hash,)).fetchone()
        if already_used:
            raise HTTPException(401, "Este token de recuperação já foi utilizado. Solicite um novo código.")

        c.execute("INSERT OR IGNORE INTO used_reset_tokens(token_hash, used_at) VALUES (?, ?)",
                  (token_hash, datetime.now(timezone.utc).isoformat()))

        # SEC-05: Incrementa token_version para invalidar todas as sessões ativas do utilizador
        try:
            c.execute(
                "UPDATE users SET password_hash=?, token_version=COALESCE(token_version, 1) + 1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (hash_password(data.password), user_id),
            )
        except Exception:
            c.execute(
                "UPDATE users SET password_hash=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (hash_password(data.password), user_id),
            )
    return {"password_updated": True, "message": "Senha atualizada. Já pode iniciar sessão."}

@app.get("/api/me")
def me(user=Depends(current_user)):
    user["mandatory_responses"] = json.loads(user["mandatory_responses"] or "{}")
    user["default_agent_personality"] = DEFAULT_AGENT_PERSONALITY
    return user

@app.put("/api/account")
def update_account(data: ProfileUpdate, user=Depends(current_user), _sub=Depends(require_active_subscription)):
    with connect() as c:
        c.execute("UPDATE users SET name=?,business_type=?,business_description=?,language=? WHERE id=?",
                  (data.name.strip(), data.business_type, data.business_description, data.language, user["id"]))
    return {"ok": True}

@app.delete("/api/account")
def delete_account(data: DeleteAccountIn, user=Depends(current_user)):
    """Agenda o fim da assinatura Stripe e só então remove a conta e os seus dados."""
    with connect() as c:
        row = c.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()
    if not row or not verify_password(data.password, row["password_hash"]):
        raise HTTPException(401, "Senha incorreta.")

    try:
        cancellation = schedule_subscription_cancellation(user["id"])
    except RuntimeError as exc:
        logger.error("Exclusão de conta interrompida antes da remoção local: %s", exc)
        raise HTTPException(502, str(exc)) from exc

    try:
        with connect() as c:
            deleted = c.execute(
                "DELETE FROM users WHERE id = ?",
                (user["id"],),
            )
        if not deleted.rowcount:
            raise HTTPException(404, "Conta não encontrada.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Stripe cancelou a renovação, mas falhou a remoção local da conta %s",
            user["id"],
        )
        raise HTTPException(
            503,
            "A renovação foi cancelada, mas não foi possível concluir a remoção da conta. "
            "Tente novamente; não haverá nova cobrança.",
        ) from exc

    return {
        "ok": True,
        "subscription_cancellation_scheduled": cancellation["scheduled"],
        "current_period_end": cancellation["current_period_end"],
        "message": (
            "Conta eliminada. A assinatura não será renovada e continuará válida até ao fim "
            "do período pago. Não foi emitido reembolso."
        ),
    }

# ── Endpoints Públicos de Marcação por Opções (Acesso do Cliente) ─────────────
@app.get("/api/booking/options")
def get_booking_options(token: str, request: Request):
    check_rate_limit(request, action="booking_options", max_requests=30, window_seconds=60)
    data = decode_booking_token(token)
    if not data:
        raise HTTPException(400, "Link de agendamento inválido ou expirado.")
    user_id = data["user_id"]
    contact_id = data["contact_id"]
    with connect() as c:
        user = c.execute(
            "SELECT name, business_type, business_description, mandatory_responses FROM users WHERE id=?",
            (user_id,)
        ).fetchone()
        if not user:
            raise HTTPException(404, "Negócio não encontrado.")
        contact = c.execute(
            "SELECT name, contact_key FROM contacts WHERE id=? AND user_id=?",
            (contact_id, user_id)
        ).fetchone()
        info_rows = c.execute(
            "SELECT kind, title, content FROM business_info WHERE user_id=?",
            (user_id,)
        ).fetchall()

    business_name = user["name"] or "Drexier"
    c_name = (contact["name"] if contact else "") or data.get("name") or ""
    c_email = (contact["contact_key"] if contact else "") or data.get("email") or ""

    options = generate_booking_options(info_rows)
    return {
        "ok": True,
        "business_name": business_name,
        "business_type": user["business_type"] or "Serviços",
        "customer_name": c_name,
        "customer_email": c_email,
        "options": options,
    }


@app.post("/api/booking/select")
async def select_booking_option(request: Request):
    """
    Aceita seleção de marcação do cliente via:
      - JSON (application/json) — booking.html externo
      - Form-encoded (application/x-www-form-urlencoded) — AMP4Email interativo no Gmail

    Devolve sempre JSON e inclui os cabeçalhos CORS necessários para AMP for Email
    (Access-Control-Allow-Origin: https://mail.google.com).
    """
    check_rate_limit(request, action="booking_select", max_requests=20, window_seconds=60)
    content_type = request.headers.get("content-type", "")

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        # Pedido via AMP4Email
        form = await request.form()
        token_val = form.get("token", "")
        slot_label_val = form.get("slot_label", "")
        scheduled_at_val = form.get("scheduled_at", "")
        customer_name_val = form.get("customer_name", "") or None
        notes_val = form.get("notes", "") or None
    else:
        # Pedido via JSON (booking.html / API externa)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Corpo da requisição inválido.")
        token_val = body.get("token", "")
        slot_label_val = body.get("slot_label", "")
        scheduled_at_val = body.get("scheduled_at", "")
        customer_name_val = body.get("customer_name") or None
        notes_val = body.get("notes") or None

    if not token_val:
        raise HTTPException(400, "Token de agendamento em falta.")

    data = decode_booking_token(token_val)
    if not data:
        raise HTTPException(400, "Token de agendamento inválido ou expirado.")
    user_id = data["user_id"]
    contact_id = data["contact_id"]
    customer_email = data["email"]

    res = await handle_booking_selection(
        user_id=user_id,
        contact_id=contact_id,
        customer_email=customer_email,
        customer_name=customer_name_val or data.get("name") or "",
        slot_label=slot_label_val,
        scheduled_at=scheduled_at_val,
        notes=notes_val or "",
    )

    # Cabeçalhos CORS obrigatórios para AMP for Email
    # Ref: https://amp.dev/documentation/guides-and-tutorials/learn/amp-email-format/#cors-requests-in-amp-email
    origin = request.headers.get("origin", "")
    amp_source_origin = request.query_params.get("__amp_source_origin", "")
    response_headers = {}
    if "mail.google.com" in origin or "gmail" in origin.lower():
        response_headers["Access-Control-Allow-Origin"] = origin
        response_headers["Access-Control-Allow-Credentials"] = "true"
    if amp_source_origin:
        response_headers["AMP-Access-Control-Allow-Source-Origin"] = amp_source_origin
        response_headers["Access-Control-Expose-Headers"] = "AMP-Access-Control-Allow-Source-Origin"

    return JSONResponse(content=res, headers=response_headers)


@app.options("/api/booking/select")
async def booking_select_preflight(request: Request):
    """Responde a pedidos CORS preflight do AMP for Email."""
    origin = request.headers.get("origin", "")
    amp_source_origin = request.query_params.get("__amp_source_origin", "")
    
    # SEC H6: Validar origem permitida antes de refletir
    is_amp = bool(amp_source_origin or "mail.google.com" in origin or "gmail" in origin.lower())
    is_allowed = (origin in ALLOWED_ORIGINS) or is_amp or is_test_environment()
    
    if origin and not is_allowed:
        return JSONResponse(content={"error": "Origin not allowed"}, status_code=403)

    allow_origin = origin if origin else "*"
    headers = {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Allow-Credentials": "true",
    }
    if amp_source_origin:
        headers["AMP-Access-Control-Allow-Source-Origin"] = amp_source_origin
        headers["Access-Control-Expose-Headers"] = "AMP-Access-Control-Allow-Source-Origin"
    return JSONResponse(content={}, headers=headers, status_code=200)


_dashboard_cache = {}  # uid -> (timestamp, data)
DASHBOARD_CACHE_TTL = 3.0

def invalidate_dashboard_cache(user_id: int):
    """Invalida o cache do dashboard imediatamente quando há nova interação/ação."""
    _dashboard_cache.pop(user_id, None)

@app.get("/api/dashboard")
def dashboard(user=Depends(current_user)):
    uid = user["id"]
    now = datetime.now(timezone.utc)
    now_timestamp = now.timestamp()
    cached = _dashboard_cache.get(uid)
    if cached and (now_timestamp - cached[0] < DASHBOARD_CACHE_TTL):
        return cached[1]
    today_window_start = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    yesterday_window_start = (now - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
    window_end = now.strftime("%Y-%m-%d %H:%M:%S")
    with connect() as c:
        total_messages=c.execute("SELECT COUNT(*) n FROM messages WHERE user_id=? AND sender='agent'",(uid,)).fetchone()["n"]
        received_messages=c.execute("SELECT COUNT(*) n FROM messages WHERE user_id=? AND sender='customer'",(uid,)).fetchone()["n"]
        total_contacts=c.execute("SELECT COUNT(*) n FROM contacts WHERE user_id=?",(uid,)).fetchone()["n"]
        today_contacts=c.execute(
            "SELECT COUNT(*) n FROM contacts WHERE user_id=? AND created_at>=? AND created_at<?",
            (uid, today_window_start, window_end),
        ).fetchone()["n"]
        yesterday_contacts=c.execute(
            "SELECT COUNT(*) n FROM contacts WHERE user_id=? AND created_at>=? AND created_at<?",
            (uid, yesterday_window_start, today_window_start),
        ).fetchone()["n"]
        pending=c.execute("SELECT COUNT(*) n FROM conversion_requests WHERE user_id=? AND status='pending'",(uid,)).fetchone()["n"]
        pending_rows=c.execute("""SELECT r.id,r.request_type,r.details,r.created_at,r.status,ct.name,ct.contact_key
          FROM conversion_requests r JOIN contacts ct ON ct.id=r.contact_id
          WHERE r.user_id=? AND r.status IN ('pending', 'validating') ORDER BY r.created_at DESC""",(uid,)).fetchall()
        important_rows=c.execute("""SELECT r.id,r.contact_id,r.request_type,r.details,r.created_at,r.status,r.scheduled_at,ct.name,ct.contact_key
          FROM conversion_requests r JOIN contacts ct ON ct.id=r.contact_id
          WHERE r.user_id=? AND r.status IN ('pending', 'validating', 'awaiting_schedule', 'awaiting_client_confirmation', 'confirmed', 'confirmed_manual')
          ORDER BY r.created_at DESC""",(uid,)).fetchall()
        booking_rows=c.execute("""SELECT r.id,r.request_type,r.details,r.created_at,r.resolved_at,r.status,r.scheduled_at,ct.id AS contact_id,ct.name,ct.contact_key
          FROM conversion_requests r JOIN contacts ct ON ct.id=r.contact_id
          WHERE r.user_id=? AND r.status IN ('confirmed', 'confirmed_manual')
          ORDER BY r.scheduled_at ASC""",(uid,)).fetchall()

    local_today = now.astimezone(BUSINESS_TIMEZONE).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_start = local_today.astimezone(timezone.utc)
    # Marcações atemporais: incluem todas as marcações com data futura (>= today_start)
    bookings_rows = []
    for row in booking_rows:
        item = dict(row)
        if not item["scheduled_at"]:
            continue
        details = item.get("details") or ""
        schedule_marker = "Data e hora escolhidas pelo cliente:"
        if schedule_marker in details:
            item["appointment_message"] = details.rsplit(schedule_marker, 1)[-1].strip()
        elif details.startswith("Assunto:") and "\n" in details:
            item["appointment_message"] = details.split("\n", 1)[1].strip()
        else:
            item["appointment_message"] = details.strip()
        try:
            scheduled_at = datetime.fromisoformat(str(item["scheduled_at"]).replace("Z", "+00:00"))
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if scheduled_at.astimezone(timezone.utc) >= today_start:
            item["name"] = item.get("name") or item.get("contact_key") or "Cliente"
            bookings_rows.append(item)
    bookings_count = len(bookings_rows)
    important_items = []
    seen_important_contacts = set()
    for row in important_rows:
        item = dict(row)
        cid = item.get("contact_id")
        if not cid or cid in seen_important_contacts:
            continue
        req_type = (item.get("request_type") or "").strip().lower()
        if req_type and req_type not in ("booking", "purchase", "agendamento", "compra"):
            continue
        seen_important_contacts.add(cid)
        important_items.append({
            "id": item.get("id"),
            "contact_id": cid,
            "name": item.get("name") or item.get("contact_key") or "Cliente",
            "contact_key": item.get("contact_key") or "",
            "request_type": item.get("request_type") or "",
            "message": (item.get("details") or "").strip(),
            "created_at": item.get("created_at"),
            "status": item.get("status"),
        })
    res = {"messages_answered":total_messages,"messages_received":received_messages,"total_contacts":total_contacts,"today_contacts":today_contacts,
            "yesterday_contacts":yesterday_contacts,"pending_count":pending,"pending_requests":[dict(x) for x in pending_rows],
            "bookings_count":bookings_count,"confirmed_bookings":[dict(x) for x in bookings_rows],
            "important_items":important_items}
    _dashboard_cache[uid] = (now_timestamp, res)
    return res


@app.post("/api/conversions/{request_id}/remind")
async def remind_conversion(request_id: int, user=Depends(current_user)):
    try:
        return await send_ai_booking_reminder(user["id"], request_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error(f"Erro ao enviar lembrete do pedido {request_id}: {exc}")
        raise HTTPException(500, "Não foi possível enviar o lembrete. Tente novamente.")
@app.get("/api/analytics")
def analytics(user=Depends(current_user)):
    with connect() as c:
        series = daily_acquisitions(c, user["id"], 14)
        variants = [dict(x) for x in c.execute("SELECT id,label,response_text,sent_count,conversions FROM response_variants WHERE user_id=? ORDER BY id", (user["id"],)).fetchall()]
    return {
        "acquisitions": series,
        "variants": variants
    }

@app.post("/api/reports/products-services")
async def generate_products_services_report(user=Depends(current_user)):
    try:
        with connect() as c:
            return await analyze_products_and_services(c, user["id"])
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(502, str(exc))

@app.post("/api/reports/approaches")
async def generate_approaches_report(user=Depends(current_user)):
    try:
        with connect() as c:
            return await analyze_approaches(c, user["id"])
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(502, str(exc))

@app.post("/api/reports/adopted-approach")
def adopt_approach(data: AdoptApproachIn, user=Depends(current_user), _sub=Depends(require_active_subscription)):
    with connect() as c:
        c.execute(
            "UPDATE users SET agent_adopted_style=? WHERE id=?",
            (data.style.strip(), user["id"]),
        )
    return {"ok": True}

@app.delete("/api/reports/adopted-approach")
def undo_adopted_approach(user=Depends(current_user), _sub=Depends(require_active_subscription)):
    with connect() as c:
        c.execute("UPDATE users SET agent_adopted_style='' WHERE id=?", (user["id"],))
    return {"ok": True}

@app.post("/api/reports/generate-ai-report")
async def generate_ai_report(user=Depends(current_user)):
    with connect() as c:
        report = await generate_strategic_ai_report(c, user["id"])
    return report

# ── Store for full analysis reports (database + cache) ──────────────────────
import uuid as _uuid
_analyses_store: Dict[int, list] = {}

@app.post("/api/reports/generate-full-analysis")
async def generate_full_analysis(user=Depends(current_user)):
    """Gera uma análise completa e detalhada de todas as conversas, adaptada ao perfil do negócio."""
    uid = user["id"]
    with connect() as c:
        report = await generate_full_analysis_report(c, uid)
        meta_dict = {
            "generated_at": report["generated_at"],
            "business_name": report.get("business_name", ""),
            "business_type": report.get("business_type", ""),
            "total_contacts_30d": report.get("total_contacts_30d", 0),
            "total_contacts": report.get("total_contacts", 0),
            "confirmed_orders": report.get("confirmed_orders", 0),
            "conversion_rate": report.get("conversion_rate", 0),
            "abandonment_rate": report.get("abandonment_rate", 0),
            "sample_size": report.get("sample_size", 0),
        }
        cur = c.execute(
            "INSERT INTO business_info(user_id, kind, title, content, metadata) VALUES(?,?,?,?,?)",
            (uid, "ai_report", f"Análise — {report.get('business_type', 'Negócio')}", report["report_content"], json.dumps(meta_dict, ensure_ascii=False))
        )
        row_id = cur.lastrowid
    
    analysis_id = str(row_id) if row_id else str(_uuid.uuid4())
    analysis_entry = {
        "id": analysis_id,
        "generated_at": report["generated_at"],
        "business_name": report.get("business_name", ""),
        "business_type": report.get("business_type", ""),
        "total_contacts_30d": report.get("total_contacts_30d", 0),
        "total_contacts": report.get("total_contacts", 0),
        "confirmed_orders": report.get("confirmed_orders", 0),
        "conversion_rate": report.get("conversion_rate", 0),
        "abandonment_rate": report.get("abandonment_rate", 0),
        "sample_size": report.get("sample_size", 0),
        "report_content": report["report_content"],
    }
    _analyses_store.setdefault(uid, []).insert(0, analysis_entry)
    return {"ok": True, "analysis": analysis_entry}

@app.get("/api/reports/analyses")
def list_analyses(user=Depends(current_user)):
    """Devolve a lista de análises guardadas para o utilizador atual."""
    uid = user["id"]
    analyses = []
    with connect() as c:
        rows = c.execute(
            "SELECT id, title, content, metadata, created_at FROM business_info WHERE user_id=? AND kind='ai_report' ORDER BY id DESC",
            (uid,)
        ).fetchall()
        for r in rows:
            meta = {}
            if r["metadata"]:
                try:
                    meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else (r["metadata"] or {})
                except Exception:
                    meta = {}
            analyses.append({
                "id": str(r["id"]),
                "generated_at": meta.get("generated_at") or r.get("created_at") or "",
                "business_name": meta.get("business_name", ""),
                "business_type": meta.get("business_type", ""),
                "total_contacts_30d": meta.get("total_contacts_30d", 0),
                "total_contacts": meta.get("total_contacts", 0),
                "confirmed_orders": meta.get("confirmed_orders", 0),
                "conversion_rate": meta.get("conversion_rate", 0),
                "abandonment_rate": meta.get("abandonment_rate", 0),
                "sample_size": meta.get("sample_size", 0),
                "report_content": r["content"],
            })
    if not analyses and uid in _analyses_store:
        analyses = _analyses_store[uid]
    return {"analyses": analyses}

@app.delete("/api/reports/analyses/{analysis_id}")
def delete_analysis(analysis_id: str, user=Depends(current_user)):
    """Elimina uma análise da base de dados e da memória."""
    uid = user["id"]
    with connect() as c:
        try:
            aid = int(analysis_id)
            c.execute("DELETE FROM business_info WHERE id=? AND user_id=? AND kind='ai_report'", (aid, uid))
        except (ValueError, TypeError):
            pass
    store = _analyses_store.get(uid, [])
    _analyses_store[uid] = [a for a in store if str(a["id"]) != str(analysis_id)]
    return {"ok": True}

@app.delete("/api/conversions/{booking_id}/remove-from-week")
def remove_booking_from_week(booking_id: int, user=Depends(current_user)):
    """Remove uma marcação da lista da semana resolvendo-a ou eliminando-a."""
    invalidate_dashboard_cache(user["id"])
    with connect() as c:
        cur = c.execute(
            "UPDATE conversion_requests SET status='resolved', resolved_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND user_id=? AND status IN ('confirmed','confirmed_manual')",
            (booking_id, user["id"])
        )
        if not cur.rowcount:
            cur = c.execute("DELETE FROM conversion_requests WHERE id=? AND user_id=?", (booking_id, user["id"]))
    invalidate_dashboard_cache(user["id"])
    return {"ok": True}

@app.get("/api/agent/automation-level")
def get_automation_level(user=Depends(current_user)):
    with connect() as c:
        row = c.execute("SELECT mandatory_responses FROM users WHERE id=?", (user["id"],)).fetchone()
        mandatory = {}
        if row and row["mandatory_responses"]:
            try:
                mandatory = json.loads(row["mandatory_responses"])
            except Exception:
                mandatory = {}
        level = mandatory.get("automation_level", "full")
        return {"level": level}

@app.post("/api/agent/automation-level")
def set_automation_level(data: AutomationLevelIn, user=Depends(current_user)):
    with connect() as c:
        row = c.execute("SELECT mandatory_responses FROM users WHERE id=?", (user["id"],)).fetchone()
        mandatory = {}
        if row and row["mandatory_responses"]:
            try:
                mandatory = json.loads(row["mandatory_responses"])
            except Exception:
                mandatory = {}
        mandatory["automation_level"] = data.level
        c.execute(
            "UPDATE users SET mandatory_responses=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(mandatory, ensure_ascii=False), user["id"])
        )
        auto_reply = 0 if data.level == "disabled" else 1
        try:
            c.execute("UPDATE email_integrations SET auto_reply_enabled=? WHERE user_id=?", (auto_reply, user["id"]))
        except Exception:
            pass
    return {"ok": True, "level": data.level}

@app.get("/api/contacts")
def contacts(user=Depends(current_user)):
    with connect() as c:
        rows=c.execute("""SELECT ct.id,ct.name,ct.contact_key,ct.created_at,ct.last_message_at,
          (SELECT content FROM messages m WHERE m.contact_id=ct.id ORDER BY m.id DESC LIMIT 1) last_message
          FROM contacts ct WHERE ct.user_id=? ORDER BY COALESCE(ct.last_message_at,ct.created_at) DESC""",(user["id"],)).fetchall()
    return [dict(x) for x in rows]

@app.get("/api/contacts/{contact_id}/messages")
def contact_messages(contact_id:int,user=Depends(current_user)):
    with connect() as c:
        own=c.execute("SELECT id FROM contacts WHERE id=? AND user_id=?",(contact_id,user["id"])).fetchone()
        if not own: raise HTTPException(404,"Cliente não encontrado.")
        rows=c.execute("SELECT id,sender,content,created_at FROM messages WHERE contact_id=? AND user_id=? ORDER BY id",(contact_id,user["id"])).fetchall()
    return [dict(x) for x in rows]

@app.delete("/api/messages/{message_id}")
def delete_message(message_id: int, user=Depends(current_user)):
    with connect() as c:
        row = c.execute("SELECT id, contact_id FROM messages WHERE id=? AND user_id=?", (message_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Mensagem não encontrada.")
        c.execute("DELETE FROM messages WHERE id=? AND user_id=?", (message_id, user["id"]))
        last_msg = c.execute("SELECT created_at FROM messages WHERE contact_id=? ORDER BY id DESC LIMIT 1", (row["contact_id"],)).fetchone()
        last_time = last_msg["created_at"] if last_msg else None
        c.execute("UPDATE contacts SET last_message_at=? WHERE id=?", (last_time, row["contact_id"]))
    return {"ok": True, "message": "Mensagem eliminada com sucesso."}

@app.delete("/api/contacts/{contact_id}")
def delete_contact(contact_id: int, user=Depends(current_user)):
    with connect() as c:
        row = c.execute("SELECT id FROM contacts WHERE id=? AND user_id=?", (contact_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Cliente não encontrado.")
        c.execute("DELETE FROM messages WHERE contact_id=? AND user_id=?", (contact_id, user["id"]))
        c.execute("DELETE FROM conversion_requests WHERE contact_id=? AND user_id=?", (contact_id, user["id"]))
        c.execute("DELETE FROM email_threads WHERE contact_id=? AND user_id=?", (contact_id, user["id"]))
        c.execute("DELETE FROM contacts WHERE id=? AND user_id=?", (contact_id, user["id"]))
    return {"ok": True, "message": "Conversa eliminada com sucesso."}

@app.get("/api/business-info")
def get_business_info(user=Depends(current_user)):
    with connect() as c:
        rows=c.execute("SELECT * FROM business_info WHERE user_id=? AND kind NOT IN ('subscription', 'assinatura', 'ai_report') ORDER BY updated_at DESC",(user["id"],)).fetchall()
    return [dict(x) | {"metadata":json.loads(x["metadata"] or "{}")} for x in rows]

@app.post("/api/business-info")
def create_business_info(data:BusinessInfoIn,user=Depends(current_user),_sub=Depends(require_active_subscription)):
    with connect() as c:
        cur=c.execute("INSERT INTO business_info(user_id,kind,title,content,metadata) VALUES(?,?,?,?,?)",
          (user["id"],data.kind,data.title.strip(),data.content.strip(),json.dumps(data.metadata,ensure_ascii=False)))
        item=c.execute("SELECT * FROM business_info WHERE id=?",(cur.lastrowid,)).fetchone()
    return dict(item) | {"metadata":json.loads(item["metadata"] or "{}")}

@app.put("/api/business-info/{item_id}")
def update_business_info(item_id:int,data:BusinessInfoIn,user=Depends(current_user),_sub=Depends(require_active_subscription)):
    with connect() as c:
        cur=c.execute("UPDATE business_info SET kind=?,title=?,content=?,metadata=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
          (data.kind,data.title.strip(),data.content.strip(),json.dumps(data.metadata,ensure_ascii=False),item_id,user["id"]))
        if not cur.rowcount: raise HTTPException(404,"Informação não encontrada.")
        item=c.execute("SELECT * FROM business_info WHERE id=?",(item_id,)).fetchone()
    return dict(item) | {"metadata":json.loads(item["metadata"] or "{}")}

@app.delete("/api/business-info/{item_id}")
def delete_business_info(item_id:int,user=Depends(current_user),_sub=Depends(require_active_subscription)):
    with connect() as c:
        cur=c.execute("DELETE FROM business_info WHERE id=? AND user_id=?",(item_id,user["id"]))
    if not cur.rowcount: raise HTTPException(404,"Informação não encontrada.")
    return {"ok":True}

@app.post("/api/business-info/upload-document")
async def upload_training_document(file: UploadFile = File(...), user=Depends(current_user), _sub=Depends(require_active_subscription)):
    """
    Extrai o texto integral de arquivos enviados pelo utilizador (PDF, Word DOCX, TXT, MD, CSV)
    para alimentar a base massiva de treinamento profundo da IA Drexier.
    """
    import os, io
    filename = file.filename or "documento"
    content_bytes = await file.read()

    if len(content_bytes) > 20 * 1024 * 1024:
        raise HTTPException(400, "O ficheiro excede o limite máximo permitido de 20MB.")

    extracted_text = ""
    lower_name = filename.lower()

    if lower_name.endswith(".pdf"):
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(content_bytes)
            # SEC M7: Limite de páginas para evitar DoS de CPU
            if len(pdf) > 500:
                raise HTTPException(400, "O documento PDF excede o limite máximo de 500 páginas.")
            pages = []
            for page in pdf:
                txt = page.get_textpage().get_text_range()
                if txt.strip():
                    pages.append(txt.strip())
            extracted_text = "\n\n".join(pages)
        except Exception as e:
            raise HTTPException(400, f"Falha ao ler documento PDF: {str(e)}")

    elif lower_name.endswith(".docx"):
        try:
            import zipfile, xml.etree.ElementTree as ET
            # SEC-07: Mitigação de Zip Bomb e Path Traversal
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as z:
                total_uncompressed = sum(info.file_size for info in z.infolist())
                if total_uncompressed > 25 * 1024 * 1024:
                    raise HTTPException(400, "Arquivo DOCX excede o limite seguro de descompactação (25MB).")
                for info in z.infolist():
                    if ".." in info.filename or info.filename.startswith(("/", "\\")):
                        raise HTTPException(400, "Arquivo DOCX com estrutura inválida ou suspeita.")
                xml_content = z.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            paras = []
            for elem in tree.iter():
                if elem.tag.endswith("p"):
                    t = "".join(elem.itertext()).strip()
                    if t:
                        paras.append(t)
            extracted_text = "\n".join(paras)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Falha ao ler documento Word DOCX: {str(e)}")

    elif lower_name.endswith((".txt", ".md", ".csv", ".json", ".rtf")):
        try:
            extracted_text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                extracted_text = content_bytes.decode("latin-1")
            except Exception as e:
                raise HTTPException(400, f"Falha ao ler arquivo de texto: {str(e)}")
    else:
        try:
            extracted_text = content_bytes.decode("utf-8")
        except Exception:
            raise HTTPException(400, "Formato não suportado. Carregue ficheiros PDF, DOCX, TXT, MD ou CSV.")

    clean_text = extracted_text.strip()
    if not clean_text:
        raise HTTPException(400, "O documento parece não conter texto legível.")

    words = len(clean_text.split())
    base_title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").strip().title()

    return {
        "filename": filename,
        "suggested_title": base_title,
        "text": clean_text,
        "word_count": words,
        "char_count": len(clean_text)
    }

@app.put("/api/agent-settings")
def update_agent_settings(data:AgentSettings,user=Depends(current_user),_sub=Depends(require_active_subscription)):
    with connect() as c:
        c.execute("UPDATE users SET agent_instructions=?,mandatory_responses=? WHERE id=?",
          (data.instructions,json.dumps(data.mandatory_responses,ensure_ascii=False),user["id"]))
    return {"ok":True}

@app.post("/api/simulate/incoming")
async def incoming(data:IncomingMessage,user=Depends(current_user),_sub=Depends(require_active_subscription)):
    """Endpoint de entrada preparado para integração futura. Só recebe mensagens se autenticado nesta versão."""
    with connect() as c:
        contact=c.execute("SELECT id FROM contacts WHERE user_id=? AND contact_key=?",(user["id"],data.contact_key)).fetchone()
        if contact:
            cid=contact["id"]
            c.execute("UPDATE contacts SET name=?,last_message_at=CURRENT_TIMESTAMP WHERE id=?",(data.customer_name or "",cid))
        else:
            cur=c.execute("INSERT INTO contacts(user_id,name,contact_key,last_message_at) VALUES(?,?,?,CURRENT_TIMESTAMP)",
                          (user["id"],data.customer_name or "",data.contact_key))
            cid=cur.lastrowid
        c.execute("INSERT INTO messages(user_id,contact_id,sender,content) VALUES(?,?,'customer',?)",(user["id"],cid,data.message))
        # Obter histórico recente da conversa (últimas 10 mensagens anteriores a esta)
        history_rows = c.execute(
            "SELECT sender, content FROM messages WHERE contact_id=? AND user_id=? AND id != last_insert_rowid() ORDER BY id DESC LIMIT 10",
            (cid, user["id"])
        ).fetchall()
        history = [{"sender": r["sender"], "content": r["content"]} for r in reversed(history_rows)]

        info = c.execute("SELECT kind,title,content,metadata FROM business_info WHERE user_id=? AND kind NOT IN ('subscription', 'assinatura', 'ai_report')", (user["id"],)).fetchall()
        
        mandatory = {}
        try:
            mandatory = json.loads(user.get("mandatory_responses") or "{}")
        except Exception:
            pass

        reply = await draft_reply(
            message=data.message,
            info_rows=info,
            instructions=effective_agent_instructions(user),
            language=user.get("language") or "Português",
            history=history,
            business_name=user.get("name") or "nosso negócio",
            business_type=user.get("business_type") or "Serviços",
            business_description=user.get("business_description") or "",
            mandatory_responses=mandatory
        )
        c.execute("INSERT INTO messages(user_id,contact_id,sender,content) VALUES(?,?,'agent',?)",(user["id"],cid,reply))
        c.execute("UPDATE contacts SET last_message_at=CURRENT_TIMESTAMP WHERE id=?",(cid,))
    return {"contact_id":cid,"reply":reply}

@app.post("/api/contacts/{contact_id}/reply")
async def owner_reply(contact_id: int, data: OwnerReplyIn, user=Depends(current_user), _sub=Depends(require_active_subscription)):
    try:
        res = await send_owner_reply(user["id"], contact_id, data.message)
        return res
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Erro ao enviar resposta do proprietário: {e}")
        raise HTTPException(500, f"Falha no envio da mensagem: {str(e)}")

@app.post("/api/contacts/{contact_id}/conversion")
def create_conversion(contact_id:int,data:ConversionIn,user=Depends(current_user)):
    with connect() as c:
        contact=c.execute("SELECT id FROM contacts WHERE id=? AND user_id=?",(contact_id,user["id"])).fetchone()
        if not contact: raise HTTPException(404,"Cliente não encontrado.")
        scheduled_at = extract_scheduled_at(data.details)
        cur=c.execute("INSERT INTO conversion_requests(user_id,contact_id,request_type,details,scheduled_at) VALUES(?,?,?,?,?)",
          (user["id"],contact_id,data.request_type,data.details,scheduled_at))
    return {"id":cur.lastrowid,"status":"pending"}

@app.post("/api/conversions/{request_id}/action")
async def conversion_action(request_id: int, data: ConversionActionIn, user=Depends(current_user)):
    invalidate_dashboard_cache(user["id"])
    try:
        res = await process_confirmation_action(
            user_id=user["id"],
            request_id=request_id,
            action=data.action,
            custom_note=data.custom_note or ""
        )
        invalidate_dashboard_cache(user["id"])
        return res
    except ValueError as e:
        invalidate_dashboard_cache(user["id"])
        raise HTTPException(404, str(e))
    except Exception as e:
        invalidate_dashboard_cache(user["id"])
        logger.error(f"Erro na ação de confirmação: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/conversions/{request_id}/resolve")
def resolve_conversion(request_id:int,user=Depends(current_user)):
    invalidate_dashboard_cache(user["id"])
    with connect() as c:
        cur=c.execute("UPDATE conversion_requests SET status='resolved',resolved_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND status='pending'",
          (request_id,user["id"]))
    if not cur.rowcount: raise HTTPException(404,"Pedido pendente não encontrado.")
    return {"ok":True}

@app.post("/api/conversions/{request_id}/cancel")
def cancel_conversion(request_id: int, user=Depends(current_user)):
    with connect() as c:
        cur = c.execute(
            "UPDATE conversion_requests SET status='cancelled', resolved_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
            (request_id, user["id"]),
        )
    if not cur.rowcount:
        raise HTTPException(404, "Registo não encontrado.")
    invalidate_dashboard_cache(user["id"])
    return {"ok": True}

@app.delete("/api/conversions/{request_id}")
def delete_pending_conversion(request_id: int, user=Depends(current_user)):
    with connect() as c:
        cur = c.execute(
            "DELETE FROM conversion_requests WHERE id=? AND user_id=? AND status IN ('pending','validating')",
            (request_id, user["id"])
        )
    if not cur.rowcount:
        raise HTTPException(404, "Pedido pendente não encontrado.")
    invalidate_dashboard_cache(user["id"])
    return {"ok": True}

@app.post("/api/variants")
def create_variant(data:dict,user=Depends(current_user),_sub=Depends(require_active_subscription)):
    label=str(data.get("label","")).strip()
    response_text=str(data.get("response_text","")).strip()
    if not label or not response_text: raise HTTPException(400,"Preencha o nome do teste e o texto da resposta.")
    with connect() as c:
        cur=c.execute("INSERT INTO response_variants(user_id,label,response_text) VALUES(?,?,?)",(user["id"],label,response_text))
    return {"id":cur.lastrowid}

@app.delete("/api/variants/{variant_id}")
def delete_variant(variant_id:int,user=Depends(current_user)):
    with connect() as c:
        cur=c.execute("DELETE FROM response_variants WHERE id=? AND user_id=?",(variant_id,user["id"]))
    if not cur.rowcount: raise HTTPException(404,"Teste não encontrado.")
    return {"ok":True}

@app.get("/api/database/status")
def database_status(user=Depends(current_user)):
    """Retorna o estado de conectividade do Supabase como banco de dados principal e único."""
    status = get_supabase_status()
    status["engine"] = "Supabase PostgreSQL (Cloud)"
    status["local_db_eliminated"] = True
    if "url" in status and status["url"]:
        status["url"] = "https://[masked].supabase.co"
    return status
