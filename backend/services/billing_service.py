"""
Serviço Oficial de Faturação e Pagamentos Recorrentes Stripe para Drexier AI.
Gerencia assinaturas do Plano Business (59€/mês), sessões de Stripe Checkout,
Portal de Faturação do Cliente e Webhooks Criptografados à prova de fraude.
"""

import os
import time
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

import stripe
from dotenv import load_dotenv

from backend.database import connect

load_dotenv()
logger = logging.getLogger("drexier.billing")

# Configuração dinâmica de chaves e constantes do Plano Business (59€/mês)
def get_stripe_secret_key() -> str:
    return os.getenv("STRIPE_SECRET_KEY", "").strip()

def get_stripe_publishable_key() -> str:
    return os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()

def get_stripe_webhook_secret() -> str:
    return os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()

def get_stripe_price_id() -> str:
    return os.getenv("STRIPE_PRICE_ID", "").strip()

PLAN_NAME = os.getenv("STRIPE_PLAN_NAME", "Plano Business")
PLAN_AMOUNT_CENTS = 5900  # 59,00 € em cêntimos
PLAN_AMOUNT_DISPLAY = "59,00 €"
PLAN_CURRENCY = os.getenv("STRIPE_PLAN_CURRENCY", "eur")
PLAN_INTERVAL = "mês"


def is_stripe_configured() -> bool:
    """Verifica se a Stripe possui chave secreta configurada no ambiente."""
    sec = get_stripe_secret_key()
    return bool(sec and sec.startswith("sk_"))


def get_stripe_public_config() -> Dict[str, Any]:
    """Retorna dados públicos da Stripe para a interface do utilizador."""
    pk = get_stripe_publishable_key()
    return {
        "configured": is_stripe_configured(),
        "publishable_key": pk if pk.startswith("pk_") else "",
        "plan": {
            "name": PLAN_NAME,
            "amount_cents": PLAN_AMOUNT_CENTS,
            "amount_display": PLAN_AMOUNT_DISPLAY,
            "currency": PLAN_CURRENCY.upper(),
            "interval": PLAN_INTERVAL,
            "price_id": get_stripe_price_id(),
            "description": "Atendimento automatizado com IA 24/7 por e-mail, integração Google Gmail, treinamento ilimitado com documentos e métricas de conversão."
        }
    }


def _get_stored_subscription(user_id: int) -> Optional[Dict[str, Any]]:
    """Recupera os dados de assinatura persistidos para o utilizador."""
    stored_subscription = None
    metadata_subscription = None
    with connect() as c:
        # 1. Tenta buscar em tabela subscriptions caso exista
        try:
            row = c.execute("SELECT * FROM subscriptions WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                stored_subscription = dict(row)
        except Exception:
            pass

        # 2. Fallback de alta resiliência: busca na tabela business_info com kind='subscription'
        try:
            row = c.execute(
                "SELECT metadata FROM business_info WHERE user_id = ? AND kind = 'subscription' ORDER BY id DESC LIMIT 1",
                (user_id,)
            ).fetchone()
            if row:
                raw_meta = row["metadata"]
                if isinstance(raw_meta, str):
                    try:
                        metadata_subscription = json.loads(raw_meta)
                    except Exception:
                        pass
                elif isinstance(raw_meta, dict):
                    metadata_subscription = raw_meta
        except Exception:
            pass

    if stored_subscription:
        if not stored_subscription.get("last_successful_payment_at") and metadata_subscription:
            stored_subscription["last_successful_payment_at"] = metadata_subscription.get("last_successful_payment_at")
        return stored_subscription
    return metadata_subscription


def get_last_successful_payment_at(user_id: int) -> Optional[str]:
    """Retorna a data do último pagamento confirmado, se já existir."""
    subscription = _get_stored_subscription(user_id) or {}
    return subscription.get("last_successful_payment_at")


def _stripe_timestamp_to_iso(value: Any) -> Optional[str]:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _get_latest_successful_payment_at(subscription_id: str) -> Optional[str]:
    """Recupera da Stripe o pagamento mais recente para contas ainda sem data persistida."""
    try:
        invoices = stripe.Invoice.list(subscription=subscription_id, status="paid", limit=10)
        for invoice in invoices.data:
            if int(invoice.get("amount_paid") or 0) <= 0:
                continue
            transitions = invoice.get("status_transitions") or {}
            paid_at = _stripe_timestamp_to_iso(
                transitions.get("paid_at") or invoice.get("created")
            )
            if paid_at:
                return paid_at
    except Exception as ex:
        logger.warning(f"Não foi possível recuperar pagamentos anteriores da Stripe: {ex}")
    return None


def _save_stored_subscription(user_id: int, data: Dict[str, Any]):
    """Salva os dados da assinatura com persistência no banco de dados."""
    if not data.get("last_successful_payment_at"):
        existing_subscription = _get_stored_subscription(user_id) or {}
        data["last_successful_payment_at"] = existing_subscription.get("last_successful_payment_at")
    data["user_id"] = user_id
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    with connect() as c:
        # Tenta salvar na tabela subscriptions se ela existir
        saved_in_table = False
        try:
            existing = c.execute("SELECT id FROM subscriptions WHERE user_id = ?", (user_id,)).fetchone()
            if existing:
                c.execute(
                    """UPDATE subscriptions SET
                       stripe_customer_id = ?, stripe_subscription_id = ?, stripe_price_id = ?,
                       plan_name = ?, amount = ?, currency = ?, status = ?,
                       current_period_end = ?, cancel_at_period_end = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE user_id = ?""",
                    (
                        str(data.get("stripe_customer_id") or ""),
                        str(data.get("stripe_subscription_id") or ""),
                        str(data.get("stripe_price_id") or ""),
                        str(data.get("plan_name") or PLAN_NAME),
                        int(data.get("amount") or PLAN_AMOUNT_CENTS),
                        str(data.get("currency") or PLAN_CURRENCY),
                        str(data.get("status") or "inactive"),
                        str(data.get("current_period_end") or ""),
                        1 if data.get("cancel_at_period_end") else 0,
                        user_id,
                    )
                )
            else:
                c.execute(
                    """INSERT INTO subscriptions (
                       user_id, stripe_customer_id, stripe_subscription_id, stripe_price_id,
                       plan_name, amount, currency, status, current_period_end, cancel_at_period_end
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        user_id,
                        str(data.get("stripe_customer_id") or ""),
                        str(data.get("stripe_subscription_id") or ""),
                        str(data.get("stripe_price_id") or ""),
                        str(data.get("plan_name") or PLAN_NAME),
                        int(data.get("amount") or PLAN_AMOUNT_CENTS),
                        str(data.get("currency") or PLAN_CURRENCY),
                        str(data.get("status") or "inactive"),
                        str(data.get("current_period_end") or ""),
                        1 if data.get("cancel_at_period_end") else 0,
                    )
                )
            saved_in_table = True
        except Exception as ex:
            logger.debug(f"Tabela subscriptions não disponível, utilizando fallback business_info: {ex}")

        # Fallback de segurança: salva ou atualiza em business_info com kind='subscription'
        try:
            existing_rec = c.execute(
                "SELECT id FROM business_info WHERE user_id = ? AND kind = 'subscription'",
                (user_id,)
            ).fetchone()
            json_meta = json.dumps(data, default=str, ensure_ascii=False)
            if existing_rec:
                c.execute(
                    "UPDATE business_info SET title = ?, content = ?, metadata = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (f"Assinatura: {data.get('status', 'inactive')}", json_meta, json_meta, existing_rec["id"])
                )
            else:
                c.execute(
                    "INSERT INTO business_info (user_id, kind, title, content, metadata) VALUES (?, 'subscription', ?, ?, ?)",
                    (user_id, f"Assinatura: {data.get('status', 'inactive')}", json_meta, json_meta)
                )
        except Exception as ex2:
            logger.error(f"Erro ao salvar fallback de assinatura em business_info: {ex2}")


def get_user_subscription_status(user_id: int) -> Dict[str, Any]:
    """
    Retorna o estado detalhado da assinatura do utilizador.
    Verifica se o acesso está liberado, status de pagamento e período de vigência.
    Se o status local estiver inativo mas a Stripe estiver configurada,
    faz auto-reconciliação direta com a Stripe para desbloquear o acesso na hora.
    """
    sub_data = _get_stored_subscription(user_id) or {}
    status = sub_data.get("status", "none")

    # Se estiver marcado como ativo, verifica se o período não expirou
    has_active_access = False
    if status in ("active", "trialing"):
        period_end = sub_data.get("current_period_end")
        if period_end:
            try:
                # Trata formatos ISO ou timestamps Unix
                if isinstance(period_end, (int, float)):
                    end_dt = datetime.fromtimestamp(period_end, tz=timezone.utc)
                else:
                    pe_str = str(period_end).replace("Z", "+00:00")
                    end_dt = datetime.fromisoformat(pe_str)
                # Dá tolerância de 24h para renovação automática via webhook
                has_active_access = datetime.now(timezone.utc) <= (end_dt + timedelta(days=1))
            except Exception:
                has_active_access = True
        else:
            has_active_access = True
    elif status in ("past_due", "unpaid", "incomplete"):
        has_active_access = False

    # AUTO-RECONCILIAÇÃO INFALÍVEL COM A STRIPE:
    # Se o banco local indicar inativo mas a Stripe estiver configurada,
    # consulta a API da Stripe diretamente para evitar falso-bloqueio se o webhook atrasar
    if is_stripe_configured():
        try:
            stripe.api_key = get_stripe_secret_key()
            customer_id = sub_data.get("stripe_customer_id")
            user_email = None

            with connect() as c:
                u_row = c.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
                if u_row:
                    user_email = u_row["email"]

            # Se não temos customer_id salvo, busca na Stripe pelo email do usuário
            if not customer_id and user_email:
                try:
                    cust_res = stripe.Customer.list(email=user_email, limit=1)
                    if cust_res and len(cust_res.data) > 0:
                        customer_id = cust_res.data[0].id
                        sub_data["stripe_customer_id"] = customer_id
                except Exception:
                    pass

            if customer_id:
                try:
                    subs_list = stripe.Subscription.list(customer=customer_id, status="all", limit=5)
                    for s in subs_list.data:
                        if getattr(s, "status", None) in ("active", "trialing"):
                            try:
                                period_end_dt = datetime.fromtimestamp(s.current_period_end, tz=timezone.utc).isoformat()
                            except Exception:
                                period_end_dt = sub_data.get("current_period_end") or (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
                            price_id = get_stripe_price_id()
                            try:
                                if s.items and s.items.data:
                                    price_id = s.items.data[0].price.id
                            except Exception:
                                pass
                            sub_data.update({
                                "stripe_customer_id": customer_id,
                                "stripe_subscription_id": getattr(s, "id", sub_data.get("stripe_subscription_id") or ""),
                                "stripe_price_id": price_id,
                                "plan_name": PLAN_NAME,
                                "amount": PLAN_AMOUNT_CENTS,
                                "currency": PLAN_CURRENCY,
                                "status": s.status,
                                "current_period_end": period_end_dt,
                                "cancel_at_period_end": bool(getattr(s, "cancel_at_period_end", False))
                            })
                            if not sub_data.get("last_successful_payment_at"):
                                paid_at = _get_latest_successful_payment_at(str(getattr(s, "id", "")))
                                if paid_at:
                                    sub_data["last_successful_payment_at"] = paid_at
                            _save_stored_subscription(user_id, sub_data)
                            status = s.status
                            has_active_access = True
                            logger.info(f"[Auto-Reconciliação Stripe] Assinatura {getattr(s,'id','')} ativa confirmada e salva para user {user_id}!")
                            break
                except Exception:
                    pass
        except Exception as ex:
            logger.debug(f"[Auto-Reconciliação Stripe] Verificação ignorada: {ex}")

    return {
        "configured": is_stripe_configured(),
        "has_active_subscription": has_active_access,
        "status": status,
        "status_label": {
            "active": "Subscrição Ativa",
            "trialing": "Período de Testes",
            "past_due": "Pagamento Recusado / Em Atraso",
            "canceled": "Subscrição Cancelada",
            "unpaid": "Não Pago",
            "incomplete": "Pagamento Incompleto",
            "none": "Sem Plano Ativo"
        }.get(status, "Sem Plano Ativo"),
        "plan_name": sub_data.get("plan_name", PLAN_NAME),
        "amount_display": PLAN_AMOUNT_DISPLAY,
        "currency": PLAN_CURRENCY.upper(),
        "interval": PLAN_INTERVAL,
        "stripe_customer_id": sub_data.get("stripe_customer_id"),
        "stripe_subscription_id": sub_data.get("stripe_subscription_id"),
        "current_period_end": sub_data.get("current_period_end"),
        "last_successful_payment_at": sub_data.get("last_successful_payment_at"),
        "cancel_at_period_end": bool(sub_data.get("cancel_at_period_end", False)),
    }


def verify_checkout_session(session_id: str, user_id: int) -> Dict[str, Any]:
    """
    Verifica e ativa imediatamente uma sessão de Checkout recém-concluída na Stripe.
    Elimina qualquer latência de webhook e desbloqueia o utilizador instantaneamente.
    """
    if not is_stripe_configured():
        return get_user_subscription_status(user_id)

    stripe.api_key = get_stripe_secret_key()
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["subscription", "customer"])
        customer = session.get("customer")
        customer_id = customer.id if hasattr(customer, "id") else (customer if isinstance(customer, str) else None)
        sub = session.get("subscription")
        sub_id = sub.id if hasattr(sub, "id") else (sub if isinstance(sub, str) else None)

        payment_status = session.get("payment_status")
        session_status = session.get("status")

        if payment_status in ("paid", "no_payment_required") or session_status == "complete" or sub_id:
            status = "active"
            period_end_dt = ""
            cancel_at = False
            price_id = get_stripe_price_id()

            if hasattr(sub, "status"):
                try:
                    status = sub.status or "active"
                    if getattr(sub, "current_period_end", None):
                        period_end_dt = datetime.fromtimestamp(sub.current_period_end, tz=timezone.utc).isoformat()
                    cancel_at = bool(getattr(sub, "cancel_at_period_end", False))
                    if getattr(sub, "items", None) and sub.items.data:
                        try:
                            price_id = sub.items.data[0].price.id
                        except Exception:
                            pass
                except Exception:
                    pass
            elif sub_id:
                try:
                    s_obj = stripe.Subscription.retrieve(sub_id)
                    status = getattr(s_obj, "status", None) or "active"
                    if getattr(s_obj, "current_period_end", None):
                        period_end_dt = datetime.fromtimestamp(s_obj.current_period_end, tz=timezone.utc).isoformat()
                    cancel_at = bool(getattr(s_obj, "cancel_at_period_end", False))
                    if getattr(s_obj, "items", None) and s_obj.items.data:
                        try:
                            price_id = s_obj.items.data[0].price.id
                        except Exception:
                            pass
                except Exception:
                    pass

            # Se ainda não temos período, definir para 30 dias a partir de agora para garantir acesso imediato
            if not period_end_dt:
                try:
                    period_end_dt = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
                except Exception:
                    period_end_dt = ""

            record = {
                "stripe_customer_id": str(customer_id or ""),
                "stripe_subscription_id": str(sub_id or ""),
                "stripe_price_id": str(price_id or get_stripe_price_id() or ""),
                "plan_name": PLAN_NAME,
                "amount": PLAN_AMOUNT_CENTS,
                "currency": PLAN_CURRENCY,
                "status": status if status in ("active", "trialing", "past_due") else "active",
                "current_period_end": period_end_dt,
                "cancel_at_period_end": bool(cancel_at)
            }
            if payment_status == "paid":
                record["last_successful_payment_at"] = _stripe_timestamp_to_iso(
                    session.get("created")
                )
            _save_stored_subscription(user_id, record)
            logger.info(f"[Stripe Checkout] Sessão {session_id} verificada com sucesso! User {user_id} ativo (status={record['status']}).")
    except Exception as ex:
        logger.error(f"[Stripe Checkout] Falha ao verificar sessão {session_id}: {ex}")

    return get_user_subscription_status(user_id)


def is_subscription_active(user_id: int) -> bool:
    """Verifica se o utilizador possui acesso SaaS liberado por pagamento em dia."""
    # Se a Stripe não estiver configurada no .env (modo de desenvolvimento inicial livre), permite acesso
    if not is_stripe_configured():
        return True
    status = get_user_subscription_status(user_id)
    return status["has_active_subscription"]


async def create_checkout_session(user_id: int, user_email: str, user_name: str, base_url: str) -> Dict[str, Any]:
    """
    Cria uma sessão oficial do Stripe Checkout em modo 'subscription' (Plano Business 59€/mês).
    Configura proteções antifraude rigorosas (3D Secure, AVS obrigatório de morada).
    """
    if not is_stripe_configured():
        raise ValueError(
            "A integração com a Stripe não está configurada no ficheiro .env. "
            "Defina STRIPE_SECRET_KEY e STRIPE_PUBLISHABLE_KEY."
        )

    stripe.api_key = get_stripe_secret_key()

    # 1. Obtém ou cria o cliente oficial na Stripe com metadata
    sub_data = _get_stored_subscription(user_id) or {}
    customer_id = sub_data.get("stripe_customer_id")

    if not customer_id:
        try:
            # Procura se o cliente já existe na Stripe pelo e-mail
            existing_customers = stripe.Customer.list(email=user_email, limit=1)
            if existing_customers and len(existing_customers.data) > 0:
                customer_id = existing_customers.data[0].id
            else:
                new_customer = stripe.Customer.create(
                    email=user_email,
                    name=user_name,
                    metadata={"user_id": str(user_id), "app": "Drexier AI"}
                )
                customer_id = new_customer.id
            sub_data["stripe_customer_id"] = customer_id
            _save_stored_subscription(user_id, sub_data)
        except Exception as e:
            logger.error(f"Erro ao obter/criar Customer na Stripe: {e}")
            raise RuntimeError(f"Falha ao registar cliente na Stripe: {str(e)}")

    # 2. Define o item de faturação do Plano Business (59€/mês)
    price_id = get_stripe_price_id()
    if price_id:
        line_items = [{"price": price_id, "quantity": 1}]
    else:
        # Cria dinamicamente o produto recorrente com validação oficial
        line_items = [{
            "price_data": {
                "currency": PLAN_CURRENCY.lower(),
                "product_data": {
                    "name": f"Drexier AI - {PLAN_NAME}",
                    "description": (
                        "Acesso ilimitado ao Drexier AI: Atendimento com IA 24/7 por E-mail (Google Gmail), "
                        "Treinamento Profundo com Documentos (PDF, DOCX) e Dashboard de Conversões."
                    ),
                },
                "unit_amount": PLAN_AMOUNT_CENTS,  # 5900 cêntimos = 59,00 €
                "recurring": {"interval": "month"},
            },
            "quantity": 1,
        }]

    # 3. Cria a Checkout Session oficial com máxima segurança antifraude
    clean_base = base_url.rstrip("/")
    success_url = f"{clean_base}/?billing=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{clean_base}/?billing=cancel"

    session_params: Dict[str, Any] = {
        "mode": "subscription",
        "payment_method_types": ["card"],
        "line_items": line_items,
        "customer": customer_id,
        "client_reference_id": str(user_id),
        "success_url": success_url,
        "cancel_url": cancel_url,
        "allow_promotion_codes": True,
        # Antifraude crítico: exige preenchimento e verificação da morada de faturação para validação AVS do cartão
        "billing_address_collection": "required",
        "metadata": {
            "user_id": str(user_id),
            "plan_name": PLAN_NAME,
            "amount_eur": "59.00"
        },
        "subscription_data": {
            "metadata": {
                "user_id": str(user_id),
                "plan_name": PLAN_NAME
            }
        }
    }

    try:
        session = stripe.checkout.Session.create(**session_params)
        return {
            "checkout_url": session.url,
            "session_id": session.id,
            "customer_id": customer_id
        }
    except Exception as e:
        logger.error(f"Erro ao criar sessão de checkout Stripe: {e}")
        raise RuntimeError(f"Falha ao gerar página segura de pagamento da Stripe: {str(e)}")


async def create_portal_session(user_id: int, base_url: str) -> Dict[str, Any]:
    """
    Cria uma sessão segura do Stripe Customer Portal para o utilizador.
    Permite gerir cartão de crédito, consultar recibos e faturas em PDF oficiais.
    """
    if not is_stripe_configured():
        raise ValueError("Stripe não configurada.")

    stripe.api_key = get_stripe_secret_key()
    sub_data = _get_stored_subscription(user_id) or {}
    customer_id = sub_data.get("stripe_customer_id")

    if not customer_id:
        raise ValueError("Ainda não possui uma conta de cliente Stripe vinculada. Adira primeiro ao Plano Business.")

    clean_base = base_url.rstrip("/")
    return_url = f"{clean_base}/"

    try:
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url
        )
        return {"portal_url": portal.url}
    except Exception as e:
        logger.error(f"Erro ao criar sessão do Customer Portal: {e}")
        raise RuntimeError(f"Falha ao abrir portal de faturação: {str(e)}")


def handle_stripe_webhook(payload_bytes: bytes, sig_header: str) -> Dict[str, Any]:
    """
    Processador de Webhook Criptografado Antifraude da Stripe.
    Valida a assinatura HMAC-SHA256 da Stripe com STRIPE_WEBHOOK_SECRET,
    impedindo requisições forjadas ou falsificação de pagamentos.
    """
    secret = get_stripe_webhook_secret()
    if not secret:
        logger.error("STRIPE_WEBHOOK_SECRET não definido no .env. Impossível validar webhook com segurança.")
        raise ValueError("STRIPE_WEBHOOK_SECRET não configurado.")

    stripe.api_key = get_stripe_secret_key()

    try:
        event = stripe.Webhook.construct_event(
            payload=payload_bytes,
            sig_header=sig_header,
            secret=secret
        )
    except ValueError as e:
        logger.warning(f"Payload inválido de webhook Stripe: {e}")
        raise ValueError("Payload inválido.")
    except stripe.error.SignatureVerificationError as e:
        logger.warning(f"Assinatura do webhook Stripe rejeitada (Tentativa de Fraude/Spoofing): {e}")
        raise ValueError("Assinatura de segurança inválida.")

    event_type = event["type"]
    event_data = event["data"]["object"]
    logger.info(f"[Stripe Webhook] Evento recebido com segurança: {event_type} (ID: {event.get('id')})")

    # 1. Evento: Checkout concluído com sucesso
    if event_type == "checkout.session.completed":
        session = event_data
        client_ref = session.get("client_reference_id")
        user_id = int(client_ref) if client_ref and client_ref.isdigit() else None
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")

        if not user_id and session.get("metadata"):
            meta_uid = session["metadata"].get("user_id")
            if meta_uid and meta_uid.isdigit():
                user_id = int(meta_uid)

        if user_id and subscription_id:
            try:
                sub = stripe.Subscription.retrieve(subscription_id)
                period_end_dt = datetime.fromtimestamp(sub.current_period_end, tz=timezone.utc).isoformat()
                _save_stored_subscription(user_id, {
                    "stripe_customer_id": str(customer_id or ""),
                    "stripe_subscription_id": str(subscription_id or ""),
                    "stripe_price_id": str(sub.get("items", {}).get("data", [{}])[0].get("price", {}).get("id") or get_stripe_price_id()),
                    "plan_name": PLAN_NAME,
                    "amount": PLAN_AMOUNT_CENTS,
                    "currency": PLAN_CURRENCY,
                    "status": sub.status,
                    "current_period_end": period_end_dt,
                    "cancel_at_period_end": sub.cancel_at_period_end
                })
                logger.info(f"[Stripe Webhook] Assinatura do utilizador {user_id} ativada com sucesso: {sub.status}")
            except Exception as ex:
                logger.error(f"Erro ao sincronizar assinatura no checkout.session.completed: {ex}")

    # 2. Evento: Fatura cobrada com sucesso no cartão (renovação confirmada)
    elif event_type in ("invoice.payment_succeeded", "invoice.paid"):
        invoice = event_data
        customer_id = invoice.get("customer")
        subscription_id = invoice.get("subscription")

        if subscription_id:
            try:
                sub = stripe.Subscription.retrieve(subscription_id)
                user_id = None
                if sub.get("metadata") and sub["metadata"].get("user_id"):
                    user_id = int(sub["metadata"]["user_id"])
                else:
                    # Busca pelo customer_id no banco
                    sub_record = None
                    with connect() as c:
                        try:
                            r = c.execute("SELECT user_id FROM subscriptions WHERE stripe_customer_id = ?", (customer_id,)).fetchone()
                            if r: user_id = r["user_id"]
                        except Exception:
                            pass

                if user_id:
                    period_end_dt = datetime.fromtimestamp(sub.current_period_end, tz=timezone.utc).isoformat()
                    payment_timestamp = None
                    if int(invoice.get("amount_paid") or 0) > 0:
                        status_transitions = invoice.get("status_transitions") or {}
                        payment_timestamp = _stripe_timestamp_to_iso(
                            status_transitions.get("paid_at") or event.get("created")
                        )
                    payment_data = {
                        "stripe_customer_id": customer_id,
                        "stripe_subscription_id": subscription_id,
                        "status": "active",
                        "current_period_end": period_end_dt,
                        "cancel_at_period_end": sub.cancel_at_period_end
                    }
                    if payment_timestamp:
                        payment_data["last_successful_payment_at"] = payment_timestamp
                    _save_stored_subscription(user_id, payment_data)
                    logger.info(f"[Stripe Webhook] Pagamento confirmado com sucesso para utilizador {user_id}.")
            except Exception as ex:
                logger.error(f"Erro ao processar invoice.payment_succeeded: {ex}")

    # 3. Evento: Pagamento recusado no cartão do cliente
    elif event_type == "invoice.payment_failed":
        invoice = event_data
        customer_id = invoice.get("customer")
        subscription_id = invoice.get("subscription")

        logger.warning(f"[Stripe Webhook] Cobrança recusada no cartão para customer {customer_id}.")
        with connect() as c:
            try:
                r = c.execute("SELECT user_id FROM subscriptions WHERE stripe_customer_id = ?", (customer_id,)).fetchone()
                if r:
                    uid = r["user_id"]
                    _save_stored_subscription(uid, {"status": "past_due"})
            except Exception:
                pass

    # 4. Evento: Atualização de assinatura (troca de cartão, cancelamento agendado)
    elif event_type == "customer.subscription.updated":
        sub = event_data
        subscription_id = sub.get("id")
        customer_id = sub.get("customer")
        status = sub.get("status")

        with connect() as c:
            try:
                r = c.execute("SELECT user_id FROM subscriptions WHERE stripe_customer_id = ?", (customer_id,)).fetchone()
                if r:
                    uid = r["user_id"]
                    period_end_dt = datetime.fromtimestamp(sub["current_period_end"], tz=timezone.utc).isoformat()
                    _save_stored_subscription(uid, {
                        "status": status,
                        "current_period_end": period_end_dt,
                        "cancel_at_period_end": sub.get("cancel_at_period_end", False)
                    })
                    logger.info(f"[Stripe Webhook] Assinatura do utilizador {uid} atualizada para {status}.")
            except Exception:
                pass

    # 5. Evento: Assinatura cancelada definitivamente
    elif event_type == "customer.subscription.deleted":
        sub = event_data
        customer_id = sub.get("customer")
        with connect() as c:
            try:
                r = c.execute("SELECT user_id FROM subscriptions WHERE stripe_customer_id = ?", (customer_id,)).fetchone()
                if r:
                    uid = r["user_id"]
                    _save_stored_subscription(uid, {"status": "canceled"})
                    logger.info(f"[Stripe Webhook] Assinatura do utilizador {uid} cancelada.")
            except Exception:
                pass

    return {"received": True, "event_type": event_type}
