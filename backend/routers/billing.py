"""
Roteador da API de Faturação e Pagamentos Stripe (Plano Business 59€/mês).
Endpoints para checkout, gestão de faturas, verificação de status e webhooks criptografados.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel

from backend.auth import decode_token
from backend.database import connect
from backend.services.billing_service import (
    get_stripe_public_config,
    get_user_subscription_status,
    create_checkout_session,
    create_portal_session,
    handle_stripe_webhook,
    is_stripe_configured,
    verify_checkout_session,
)

logger = logging.getLogger("drexier.billing_router")
router = APIRouter(prefix="/api/billing", tags=["Faturação e Stripe"])


def get_current_user(authorization: Optional[str] = Header(default=None)):
    """Dependência para autenticar utilizador através do JWT Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sessão necessária.")
    uid = decode_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    with connect() as c:
        row = c.execute(
            "SELECT id, name, email, business_type, business_description, language FROM users WHERE id=?",
            (uid,),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Conta não encontrada.")
    return dict(row)


@router.get("/config")
def get_billing_config():
    """Retorna a configuração pública da Stripe e os dados do Plano Business (59€/mês)."""
    return get_stripe_public_config()


@router.get("/status")
def get_subscription_status(user=Depends(get_current_user)):
    """Retorna o estado detalhado da assinatura e acesso do utilizador autenticado."""
    return get_user_subscription_status(user["id"])


@router.get("/verify-session")
def verify_session(session_id: str, user=Depends(get_current_user)):
    """
    Verifica e ativa imediatamente a sessão de Checkout recém-paga pelo cliente na Stripe,
    garantindo desbloqueio instantâneo sem depender de atrasos de webhook.
    """
    if not session_id:
        raise HTTPException(400, "session_id obrigatório.")
    return verify_checkout_session(session_id=session_id.strip(), user_id=user["id"])


class CheckoutRequestPayload(BaseModel):
    base_url: Optional[str] = None


@router.post("/checkout")
async def start_checkout(payload: CheckoutRequestPayload, request: Request, user=Depends(get_current_user)):
    """
    Cria uma sessão oficial no Stripe Checkout para subscrição do Plano Business (59€/mês).
    Retorna a URL protegida com 3D Secure / SCA e validação antifraude.
    """
    base_url = payload.base_url or str(request.base_url)
    try:
        session_info = await create_checkout_session(
            user_id=user["id"],
            user_email=user["email"],
            user_name=user.get("name", ""),
            base_url=base_url
        )
        return session_info
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Erro ao iniciar checkout Stripe: {e}")
        raise HTTPException(500, f"Falha ao gerar checkout: {str(e)}")


@router.post("/portal")
async def open_customer_portal(payload: CheckoutRequestPayload, request: Request, user=Depends(get_current_user)):
    """
    Cria uma sessão do Stripe Customer Portal para o cliente consultar recibos,
    faturas em PDF ou atualizar os dados do cartão de crédito.
    """
    base_url = payload.base_url or str(request.base_url)
    try:
        portal_info = await create_portal_session(user_id=user["id"], base_url=base_url)
        return portal_info
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Erro ao abrir portal Stripe: {e}")
        raise HTTPException(500, f"Falha ao aceder ao portal: {str(e)}")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Endpoint de Webhook Oficial da Stripe à Prova de Fraude.
    Exige e valida criptograficamente a assinatura HMAC-SHA256 (Stripe-Signature),
    garantindo que os eventos provêm genuinamente dos servidores da Stripe.
    """
    payload_bytes = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not sig_header:
        logger.warning("[Stripe Webhook] Requisição rejeitada: cabeçalho Stripe-Signature ausente.")
        raise HTTPException(400, "Assinatura do webhook ausente.")

    try:
        result = handle_stripe_webhook(payload_bytes, sig_header)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"[Stripe Webhook] Erro no processamento do webhook: {e}")
        raise HTTPException(500, "Erro interno ao processar evento.")
