"""
Rotas da API Drexier para Integração de Websites Externos.
Inclui criação e ajuste do agente com IA, geração do código HEAD,
verificação real de conexão e atendimento via widget.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.auth import decode_token
from backend.database import connect
from backend.services.billing_service import is_subscription_active
from backend.services.agent import (
    DEFAULT_AGENT_PERSONALITY,
    draft_reply,
    effective_agent_instructions,
)
from backend.services.website_service import (
    DEFAULT_POSITION,
    DEFAULT_THEME_COLOR,
    INITIAL_AI_PROMPT,
    generate_head_code,
    generate_site_key,
    interact_website_agent_ai,
    match_domain,
    normalize_domain,
    verify_website_installation,
)

logger = logging.getLogger("drexier.website_router")

router = APIRouter(tags=["Website Integration"])


def get_current_user(authorization: Optional[str] = Header(default=None)):
    """Dependência para autenticar utilizador através do JWT Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sessão necessária.")
    uid = decode_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    with connect() as c:
        row = c.execute(
            "SELECT id, name, email, business_type, business_description, language, agent_instructions, agent_adopted_style, mandatory_responses FROM users WHERE id=?",
            (uid,),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Conta não encontrada.")
    return dict(row)


def get_base_url(request: Request) -> str:
    """Detecta a URL base do servidor Drexier."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    if host:
        return f"{proto}://{host}"
    return str(request.base_url).rstrip("/")


def _format_integration_response(row: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    history = []
    hist_raw = row.get("conversation_history") or "[]"
    if isinstance(hist_raw, str):
        try:
            history = json.loads(hist_raw)
        except Exception:
            history = []
    elif isinstance(hist_raw, list):
        history = hist_raw

    head_code = generate_head_code(row["site_key"], base_url, row)
    raw_status = row.get("status") or "pending"
    # Segurança de Ativação: O estado só é "active" se houver confirmação real de ligação externa
    effective_status = "active" if (raw_status == "active" and row.get("last_verified_domain")) else ("pending" if raw_status == "active" else raw_status)

    instructions_text = (row.get("agent_instructions") or "").lower()
    border_radius = row.get("border_radius")
    if not border_radius:
        if any(w in instructions_text for w in ["quadrad", "reto", "reta", "retangular", "sem arredond"]):
            border_radius = "4px"
        elif any(w in instructions_text for w in ["cápsula", "capsula", "muito arredondad", "bem redond"]):
            border_radius = "24px"
        else:
            border_radius = "16px"

    button_shape = row.get("button_shape")
    if not button_shape:
        if any(w in instructions_text for w in ["botão quadrad", "botao quadrad", "botão retangular", "botao retangular"]):
            button_shape = "square"
        elif any(w in instructions_text for w in ["botão pílula", "botao pilula"]):
            button_shape = "pill"
        else:
            button_shape = "circle"

    theme_mode = row.get("theme_mode")
    if not theme_mode:
        if any(w in instructions_text for w in ["tema escuro", "dark mode", "modo escuro", "fundo escuro", "fundo preto", "dark theme"]):
            theme_mode = "dark"
        else:
            theme_mode = "light"

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "site_key": row["site_key"],
        "site_name": row.get("site_name") or "Meu Website",
        "allowed_domain": row.get("allowed_domain") or "",
        "status": effective_status,
        "agent_name": row.get("agent_name") or "Agente Drexier",
        "agent_role": row.get("agent_role") or "Atendente Virtual",
        "greeting_message": row.get("greeting_message") or "Olá! Como posso ajudar hoje?",
        "theme_color": row.get("theme_color") or DEFAULT_THEME_COLOR,
        "position": row.get("position") or DEFAULT_POSITION,
        "border_radius": border_radius,
        "button_shape": button_shape,
        "theme_mode": theme_mode,
        "agent_instructions": row.get("agent_instructions") or "",
        "conversation_history": history,
        "last_heartbeat_at": row.get("last_heartbeat_at"),
        "last_verified_domain": row.get("last_verified_domain"),
        "error_message": row.get("error_message") or "",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "head_code": head_code,
    }


# =============================================================================
# MODELOS DE ENTRADA
# =============================================================================

class AIChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ConfigUpdateIn(BaseModel):
    agent_name: Optional[str] = None
    agent_role: Optional[str] = None
    greeting_message: Optional[str] = None
    theme_color: Optional[str] = None
    position: Optional[str] = None
    agent_instructions: Optional[str] = None
    allowed_domain: Optional[str] = None
    site_name: Optional[str] = None


class RegenerateCodeIn(BaseModel):
    reset_key: bool = False


class WidgetPingIn(BaseModel):
    site_key: str
    origin: Optional[str] = ""
    url: Optional[str] = ""


class WidgetChatIn(BaseModel):
    site_key: str
    visitor_id: str
    visitor_name: Optional[str] = "Visitante Web"
    message: str = Field(..., min_length=1, max_length=4000)
    history: Optional[List[Dict[str, str]]] = None


# =============================================================================
# ROTAS DO PAINEL DREXIER (AUTENTICADAS)
# =============================================================================

@router.get("/api/integrations/website")
def get_website_integration(request: Request, user=Depends(get_current_user)):
    """Retorna os dados da integração de website do utilizador ou estado inicial."""
    base_url = get_base_url(request)
    with connect() as c:
        row = c.execute("SELECT * FROM website_integrations WHERE user_id=?", (user["id"],)).fetchone()
        if not row:
            return {
                "exists": False,
                "status": "pending",
                "site_key": None,
                "initial_prompt": INITIAL_AI_PROMPT,
                "default_config": {
                    "agent_name": f"Assistente {user.get('name') or 'Drexier'}",
                    "agent_role": f"Atendimento • {user.get('business_type') or 'Serviços'}",
                    "greeting_message": f"Olá! Bem-vindo à {user.get('name') or 'nossa empresa'}. Como posso ajudar hoje?",
                    "theme_color": DEFAULT_THEME_COLOR,
                    "position": DEFAULT_POSITION,
                    "agent_instructions": "",
                    "allowed_domain": "",
                }
            }

        integration = dict(row)
        # Auto-reconciliação: se o status estiver 'active' mas sem domínio verificado real, corrige para 'pending'
        if integration.get("status") == "active" and not integration.get("last_verified_domain"):
            c.execute("UPDATE website_integrations SET status='pending', last_heartbeat_at=NULL WHERE id=?", (integration["id"],))
            row = c.execute("SELECT * FROM website_integrations WHERE id=?", (integration["id"],)).fetchone()
            integration = dict(row)

        res = _format_integration_response(integration, base_url)
        res["exists"] = True
        return res


@router.post("/api/integrations/website/chat")
async def website_ai_chat(data: AIChatIn, request: Request, user=Depends(get_current_user)):
    """
    Conversa interativa com a IA Drexier para desenhar ou evoluir o agente de website.
    Interpreta livremente estilo, personalidade, negócio, produtos e atendimento.
    Atualiza a configuração e gera nova versão do código HEAD preservando o site_key.
    """
    base_url = get_base_url(request)
    with connect() as c:
        row = c.execute("SELECT * FROM website_integrations WHERE user_id=?", (user["id"],)).fetchone()

        if row:
            integration = dict(row)
        else:
            # Cria a integração inicial com estado PENDENTE
            new_site_key = generate_site_key()
            default_name = f"Assistente {user.get('name') or 'Drexier'}"
            default_role = f"Atendimento • {user.get('business_type') or 'Online'}"
            default_greet = f"Olá! Bem-vindo à {user.get('name') or 'nossa empresa'}. Como posso ajudar hoje?"
            cur = c.execute(
                """INSERT INTO website_integrations
                   (user_id, site_key, site_name, allowed_domain, status, agent_name, agent_role,
                    greeting_message, theme_color, position, agent_instructions, conversation_history)
                   VALUES (?, ?, ?, '', 'pending', ?, ?, ?, ?, ?, '', '[]')""",
                (
                    user["id"],
                    new_site_key,
                    "Meu Website",
                    default_name,
                    default_role,
                    default_greet,
                    DEFAULT_THEME_COLOR,
                    DEFAULT_POSITION,
                )
            )
            row = c.execute("SELECT * FROM website_integrations WHERE id=?", (cur.lastrowid,)).fetchone()
            integration = dict(row)

    # Lê histórico da conversa com a IA
    hist_raw = integration.get("conversation_history") or "[]"
    try:
        conv_history = json.loads(hist_raw) if isinstance(hist_raw, str) else list(hist_raw)
    except Exception:
        conv_history = []

    # Se a conversa estiver vazia, adiciona o acolhimento oficial da IA
    if not conv_history:
        conv_history.append({"sender": "assistant", "content": INITIAL_AI_PROMPT})

    # Adiciona mensagem do utilizador ao histórico
    conv_history.append({"sender": "user", "content": data.message})

    # Processa com IA
    ai_reply, updated_cfg, ready = await interact_website_agent_ai(
        user=user,
        user_message=data.message,
        conversation_history=conv_history,
        current_config=integration
    )

    conv_history.append({"sender": "assistant", "content": ai_reply})

    # Atualiza na base de dados
    with connect() as c:
        c.execute(
            """UPDATE website_integrations SET
               agent_name=?,
               agent_role=?,
               greeting_message=?,
               theme_color=?,
               position=?,
               agent_instructions=?,
               allowed_domain=?,
               conversation_history=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                updated_cfg.get("agent_name", integration["agent_name"]),
                updated_cfg.get("agent_role", integration["agent_role"]),
                updated_cfg.get("greeting_message", integration["greeting_message"]),
                updated_cfg.get("theme_color", integration["theme_color"]),
                updated_cfg.get("position", integration["position"]),
                updated_cfg.get("agent_instructions", integration["agent_instructions"]),
                normalize_domain(updated_cfg.get("allowed_domain", integration.get("allowed_domain", ""))),
                json.dumps(conv_history, ensure_ascii=False),
                integration["id"],
            )
        )
        updated_row = c.execute("SELECT * FROM website_integrations WHERE id=?", (integration["id"],)).fetchone()

    formatted = _format_integration_response(dict(updated_row), base_url)
    formatted["exists"] = True
    return {
        "reply": ai_reply,
        "integration": formatted,
        "head_code": formatted["head_code"],
        "ready": ready
    }


@router.put("/api/integrations/website/config")
def update_website_config(data: ConfigUpdateIn, request: Request, user=Depends(get_current_user)):
    """Atualização direta de parâmetros (nome, cargo, cores, posição, diretrizes, domínio)."""
    base_url = get_base_url(request)
    with connect() as c:
        row = c.execute("SELECT * FROM website_integrations WHERE user_id=?", (user["id"],)).fetchone()
        if not row:
            raise HTTPException(404, "Integração ainda não iniciada.")

        current = dict(row)
        new_name = data.agent_name if data.agent_name is not None else current["agent_name"]
        new_role = data.agent_role if data.agent_role is not None else current["agent_role"]
        new_greet = data.greeting_message if data.greeting_message is not None else current["greeting_message"]
        new_color = data.theme_color if data.theme_color is not None else current["theme_color"]
        new_pos = data.position if data.position in ("bottom-right", "bottom-left") else current["position"]
        new_inst = data.agent_instructions if data.agent_instructions is not None else current["agent_instructions"]
        new_dom = normalize_domain(data.allowed_domain) if data.allowed_domain is not None else current["allowed_domain"]
        new_sname = data.site_name if data.site_name is not None else current.get("site_name", "Meu Website")

        c.execute(
            """UPDATE website_integrations SET
               agent_name=?, agent_role=?, greeting_message=?, theme_color=?,
               position=?, agent_instructions=?, allowed_domain=?, site_name=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (new_name, new_role, new_greet, new_color, new_pos, new_inst, new_dom, new_sname, current["id"])
        )
        updated_row = c.execute("SELECT * FROM website_integrations WHERE id=?", (current["id"],)).fetchone()

    formatted = _format_integration_response(dict(updated_row), base_url)
    formatted["exists"] = True
    return formatted


@router.post("/api/integrations/website/regenerate-code")
def regenerate_head_code_endpoint(data: RegenerateCodeIn, request: Request, user=Depends(get_current_user)):
    """
    Gera novamente o código HEAD.
    Por padrão preserva o identificador site_key existente.
    Se reset_key for True, gera uma nova chave exclusiva.
    """
    base_url = get_base_url(request)
    with connect() as c:
        row = c.execute("SELECT * FROM website_integrations WHERE user_id=?", (user["id"],)).fetchone()
        if not row:
            raise HTTPException(404, "Integração não encontrada.")

        current = dict(row)
        site_key = current["site_key"]
        if data.reset_key:
            site_key = generate_site_key()
            c.execute(
                "UPDATE website_integrations SET site_key=?, status='pending', last_heartbeat_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (site_key, current["id"])
            )
            current["site_key"] = site_key
            current["status"] = "pending"

    code = generate_head_code(site_key, base_url, current)
    return {
        "ok": True,
        "site_key": site_key,
        "head_code": code,
        "status": current.get("status", "pending")
    }


@router.post("/api/integrations/website/verify")
async def verify_website_endpoint(request: Request, user=Depends(get_current_user)):
    """
    Mecanismo real de verificação entre o website externo e o servidor Drexier:
    - Valida acessibilidade da URL e presença da tag do widget no HTML do website.
    - Avalia a comunicação e heartbeats recebidos do widget real.
    - Atualiza automaticamente o estado para ATIVO, PENDENTE, DESCONECTADO ou ERRO.
    """
    base_url = get_base_url(request)
    with connect() as c:
        row = c.execute("SELECT * FROM website_integrations WHERE user_id=?", (user["id"],)).fetchone()
        if not row:
            raise HTTPException(404, "Integração não encontrada.")
        integration = dict(row)

    status, err_msg, verified_domain = await verify_website_installation(
        site_key=integration["site_key"],
        allowed_domain=integration.get("allowed_domain", ""),
        last_heartbeat_at=integration.get("last_heartbeat_at")
    )

    with connect() as c:
        c.execute(
            """UPDATE website_integrations SET
               status=?,
               error_message=?,
               last_verified_domain=COALESCE(?, last_verified_domain),
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (status, err_msg, verified_domain, integration["id"])
        )
        updated_row = c.execute("SELECT * FROM website_integrations WHERE id=?", (integration["id"],)).fetchone()

    formatted = _format_integration_response(dict(updated_row), base_url)
    formatted["exists"] = True
    return {
        "status": status,
        "error_message": err_msg,
        "verified_domain": verified_domain or integration.get("last_verified_domain"),
        "integration": formatted
    }


@router.post("/api/integrations/website/chat/undo")
def undo_last_website_instruction(request: Request, user=Depends(get_current_user)):
    """
    Retrocede a última instrução dada à IA (remove o último par pergunta-resposta).
    Restaura a conversa mantendo a chave API de instalação.
    """
    base_url = get_base_url(request)
    with connect() as c:
        row = c.execute("SELECT * FROM website_integrations WHERE user_id=?", (user["id"],)).fetchone()
        if not row:
            raise HTTPException(404, "Integração não encontrada.")
        integration = dict(row)

        hist_raw = integration.get("conversation_history") or "[]"
        try:
            conv_history = json.loads(hist_raw) if isinstance(hist_raw, str) else list(hist_raw)
        except Exception:
            conv_history = []

        # Remove o último par (última resposta do assistant + última pergunta do user)
        # Mantém pelo menos a mensagem inicial de boas-vindas da IA
        if len(conv_history) > 1:
            # Se a última mensagem for assistant, remove
            if conv_history and conv_history[-1].get("sender") == "assistant":
                conv_history.pop()
            # Remove a pergunta anterior do utilizador correspondente
            if conv_history and conv_history[-1].get("sender") == "user":
                conv_history.pop()

        if not conv_history:
            conv_history = [{"sender": "assistant", "content": INITIAL_AI_PROMPT}]

        c.execute(
            """UPDATE website_integrations SET
               conversation_history=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (json.dumps(conv_history, ensure_ascii=False), integration["id"])
        )
        updated_row = c.execute("SELECT * FROM website_integrations WHERE id=?", (integration["id"],)).fetchone()

    formatted = _format_integration_response(dict(updated_row), base_url)
    formatted["exists"] = True
    return {
        "ok": True,
        "message": "Última instrução retrocedida com sucesso.",
        "integration": formatted
    }


@router.post("/api/integrations/website/chat/clear")
def clear_website_instructions(request: Request, user=Depends(get_current_user)):
    """
    Apaga todas as instruções do agente, restaurando o estilo visual padrão neutro
    (preto #18181b, branco e cinza), mantendo intactos o código HEAD e a chave de API única.
    """
    base_url = get_base_url(request)
    fresh_history = [{"sender": "assistant", "content": INITIAL_AI_PROMPT}]

    with connect() as c:
        row = c.execute("SELECT * FROM website_integrations WHERE user_id=?", (user["id"],)).fetchone()
        if not row:
            raise HTTPException(404, "Integração não encontrada.")
        integration = dict(row)

        c.execute(
            """UPDATE website_integrations SET
               conversation_history=?,
               agent_instructions='',
               theme_color=?,
               position=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (json.dumps(fresh_history, ensure_ascii=False), DEFAULT_THEME_COLOR, DEFAULT_POSITION, integration["id"])
        )
        updated_row = c.execute("SELECT * FROM website_integrations WHERE id=?", (integration["id"],)).fetchone()

    formatted = _format_integration_response(dict(updated_row), base_url)
    formatted["exists"] = True
    return {
        "ok": True,
        "message": "Instruções apagadas e restauradas para o padrão neutro com sucesso.",
        "integration": formatted
    }


@router.delete("/api/integrations/website")
def delete_website_integration(user=Depends(get_current_user)):
    """Remove ou desconecta a integração de website."""
    with connect() as c:
        c.execute("DELETE FROM website_integrations WHERE user_id=?", (user["id"],))
    return {"ok": True}


# =============================================================================
# ROTAS PÚBLICAS DO WIDGET PARA WEBSITES EXTERNOS (CORS LIVRE)
# =============================================================================

@router.get("/api/widget/config")
def get_widget_public_config(key: str = Query(..., alias="key"), request: Request = None):
    """
    Fornece as configurações visuais e comportamentais para o widget no website externo.
    Segurança rigorosa:
    - Valida se a chave é autêntica e única.
    - Se a integração já foi vinculada a um domínio (ou allowed_domain configurado),
      impede categoricamente que qualquer outro site utilize este mesmo código/chave.
    - Registra e bloqueia o uso exclusivo ao primeiro site conectado caso allowed_domain esteja em branco.
    """
    clean_key = key.strip()
    with connect() as c:
        row = c.execute("SELECT * FROM website_integrations WHERE site_key=?", (clean_key,)).fetchone()
        if not row:
            raise HTTPException(404, "Widget não encontrado ou chave inválida.")
        integration = dict(row)

    req_origin = request.headers.get("origin") or request.headers.get("referer") or ""
    detected_dom = normalize_domain(req_origin) if req_origin else ""

    # Determina o domínio oficial fixado para esta chave API (allowed_domain explícito ou domínio verificado na ativação)
    locked_domain = normalize_domain(integration.get("allowed_domain") or integration.get("last_verified_domain") or "")

    # Se já existir um domínio fixado/bloqueado para esta chave única, rejeita qualquer tentativa de outro site
    if locked_domain and detected_dom:
        if not match_domain(req_origin, locked_domain):
            err = f"Acesso negado: Este código HEAD e Chave de Integração são exclusivos do website '{locked_domain}' e não podem ser utilizados em '{detected_dom}'."
            with connect() as c:
                c.execute(
                    "UPDATE website_integrations SET status='error', error_message=? WHERE id=?",
                    (err, integration["id"])
                )
            raise HTTPException(403, err)

    # Primeira ativação / Confirmação da ligação:
    # Apenas atualiza para 'active' se houver origem HTTP real externa (não requisição sem origem nem preview local)
    is_external_handshake = bool(detected_dom and detected_dom not in ("", "localhost", "127.0.0.1"))
    if is_external_handshake:
        effective_domain = locked_domain or detected_dom
        with connect() as c:
            c.execute(
                """UPDATE website_integrations SET
                   status='active',
                   error_message='',
                   last_heartbeat_at=CURRENT_TIMESTAMP,
                   last_verified_domain=COALESCE(NULLIF(?, ''), last_verified_domain),
                   updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (effective_domain, integration["id"])
            )

    instructions_text = (integration.get("agent_instructions") or "").lower()
    border_radius = integration.get("border_radius") or ("4px" if any(w in instructions_text for w in ["quadrad", "reto", "reta", "retangular", "sem arredond"]) else ("24px" if any(w in instructions_text for w in ["cápsula", "capsula", "muito arredondad", "bem redond"]) else "16px"))
    button_shape = integration.get("button_shape") or ("square" if any(w in instructions_text for w in ["botão quadrad", "botao quadrad", "botão retangular", "botao retangular"]) else ("pill" if any(w in instructions_text for w in ["botão pílula", "botao pilula"]) else "circle"))
    theme_mode = integration.get("theme_mode") or ("dark" if any(w in instructions_text for w in ["tema escuro", "dark mode", "modo escuro", "fundo escuro", "fundo preto", "dark theme"]) else "light")

    return {
        "site_key": integration["site_key"],
        "agent_name": integration.get("agent_name") or "Agente Drexier",
        "agent_role": integration.get("agent_role") or "Atendente Virtual",
        "greeting_message": integration.get("greeting_message") or "Olá! Como posso ajudar hoje?",
        "theme_color": integration.get("theme_color") or DEFAULT_THEME_COLOR,
        "position": integration.get("position") or DEFAULT_POSITION,
        "border_radius": border_radius,
        "button_shape": button_shape,
        "theme_mode": theme_mode,
        "business_name": integration.get("site_name") or "Atendimento",
    }


@router.post("/api/widget/ping")
def widget_ping(data: WidgetPingIn, request: Request):
    """
    Heartbeat emitido pelo widget para comprovação de presença no website externo.
    Garante exclusividade: só aceita sinal do domínio fixado.
    """
    with connect() as c:
        row = c.execute("SELECT * FROM website_integrations WHERE site_key=?", (data.site_key,)).fetchone()
        if not row:
            raise HTTPException(404, "Chave de integração não reconhecida.")
        integration = dict(row)

    req_origin = request.headers.get("origin") or data.origin or request.headers.get("referer") or ""
    detected_dom = normalize_domain(req_origin) if req_origin else ""
    locked_domain = normalize_domain(integration.get("allowed_domain") or integration.get("last_verified_domain") or "")

    if locked_domain and detected_dom:
        if not match_domain(req_origin, locked_domain):
            err = f"Chave de integração não autorizada para o domínio '{detected_dom}'. Exclusiva de '{locked_domain}'."
            with connect() as c:
                c.execute(
                    "UPDATE website_integrations SET status='error', error_message=? WHERE id=?",
                    (err, integration["id"])
                )
            raise HTTPException(403, err)

    is_external_handshake = bool(detected_dom and detected_dom not in ("", "localhost", "127.0.0.1"))
    if is_external_handshake:
        effective_domain = locked_domain or detected_dom
        with connect() as c:
            c.execute(
                """UPDATE website_integrations SET
                   status='active',
                   error_message='',
                   last_heartbeat_at=CURRENT_TIMESTAMP,
                   last_verified_domain=COALESCE(NULLIF(?, ''), last_verified_domain),
                   updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (effective_domain, integration["id"])
            )

    return {"ok": True, "status": "active"}


@router.post("/api/widget/chat")
async def widget_chat(data: WidgetChatIn, request: Request):
    """
    Atendimento em tempo real ao visitante do website externo.
    Carrega o conhecimento de negócio da empresa, as diretrizes desenhadas para o agente,
    gera a resposta através da IA Drexier e registra o contacto e mensagem no sistema.
    Proteção de segurança: valida vinculação estrita ao domínio único.
    """
    with connect() as c:
        row = c.execute("SELECT * FROM website_integrations WHERE site_key=?", (data.site_key,)).fetchone()
        if not row:
            raise HTTPException(404, "Widget não encontrado.")
        integration = dict(row)

        user_row = c.execute("SELECT * FROM users WHERE id=?", (integration["user_id"],)).fetchone()
        if not user_row:
            raise HTTPException(404, "Conta associada não encontrada.")
        user = dict(user_row)

    # Validação de segurança de domínio exclusivo
    req_origin = request.headers.get("origin") or request.headers.get("referer") or ""
    detected_dom = normalize_domain(req_origin) if req_origin else ""
    locked_domain = normalize_domain(integration.get("allowed_domain") or integration.get("last_verified_domain") or "")

    if locked_domain and detected_dom and not match_domain(req_origin, locked_domain):
        raise HTTPException(403, f"Acesso proibido. Esta chave é exclusiva de '{locked_domain}'.")

    # Registro do contacto (visitante)
    contact_key = f"web_{data.site_key[:8]}_{data.visitor_id}"
    visitor_name = (data.visitor_name or "Visitante Web").strip()

    with connect() as c:
        ct = c.execute(
            "SELECT id FROM contacts WHERE user_id=? AND contact_key=?",
            (user["id"], contact_key)
        ).fetchone()

        if ct:
            cid = ct["id"]
        else:
            cur = c.execute(
                "INSERT INTO contacts (user_id, name, contact_key) VALUES (?, ?, ?)",
                (user["id"], visitor_name, contact_key)
            )
            cid = cur.lastrowid

        # Salva mensagem do visitante
        c.execute(
            "INSERT INTO messages (user_id, contact_id, sender, content) VALUES (?, ?, 'customer', ?)",
            (user["id"], cid, data.message)
        )

        # Histórico recente para o agente
        hist_rows = c.execute(
            "SELECT sender, content FROM messages WHERE user_id=? AND contact_id=? ORDER BY id DESC LIMIT 10",
            (user["id"], cid)
        ).fetchall()
        history = [{"sender": r["sender"], "content": r["content"]} for r in reversed(hist_rows)]

        # Base de conhecimento e diretrizes
        info = c.execute("SELECT kind, title, content, metadata FROM business_info WHERE user_id=?", (user["id"],)).fetchall()
        mandatory = {}
        try:
            mandatory = json.loads(user.get("mandatory_responses") or "{}")
        except Exception:
            pass

    # Combina instruções base com as instruções específicas do website
    base_inst = effective_agent_instructions(user)
    widget_inst = (integration.get("agent_instructions") or "").strip()
    agent_name = integration.get("agent_name") or user.get("name") or "nosso negócio"
    combined_inst = f"{base_inst}\n\nDIRETRIZES ESPECÍFICAS DESTE ATENDIMENTO NO WEBSITE:\n{widget_inst}" if widget_inst else base_inst

    reply = await draft_reply(
        message=data.message,
        info_rows=info,
        instructions=combined_inst,
        language=user.get("language") or "Português",
        history=history,
        business_name=agent_name,
        business_type=user.get("business_type") or "Serviços",
        business_description=user.get("business_description") or "",
        mandatory_responses=mandatory
    )

    with connect() as c:
        c.execute(
            "INSERT INTO messages (user_id, contact_id, sender, content) VALUES (?, ?, 'agent', ?)",
            (user["id"], cid, reply)
        )
        c.execute("UPDATE contacts SET last_message_at=CURRENT_TIMESTAMP WHERE id=?", (cid,))

    return {"reply": reply}
