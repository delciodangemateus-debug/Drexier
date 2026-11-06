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
    existing_subscription = _get_stored_subscription(user_id) or {}
    merged = dict(existing_subscription)
    for key, value in data.items():
        if value is not None and not (
            key in ("stripe_customer_id", "stripe_subscription_id", "stripe_price_id")
            and value == ""
        ):
            merged[key] = value
    merged["user_id"] = user_id
    merged["updated_at"] = datetime.now(timezone.utc).isoformat()

    fields = (
        "stripe_customer_id",
        "stripe_subscription_id",
        "stripe_price_id",
        "plan_name",
        "amount",
        "currency",
        "status",
        "current_period_end",
        "cancel_at_period_end",
        "last_successful_payment_at",
    )
    values = (
        str(merged.get("stripe_customer_id") or ""),
        str(merged.get("stripe_subscription_id") or ""),
        str(merged.get("stripe_price_id") or ""),
        str(merged.get("plan_name") or PLAN_NAME),
        int(merged.get("amount") or PLAN_AMOUNT_CENTS),
        str(merged.get("currency") or PLAN_CURRENCY),
        str(merged.get("status") or "inactive"),
        str(merged.get("current_period_end") or "") or None,
        bool(merged.get("cancel_at_period_end", False)),
        merged.get("last_successful_payment_at"),
    )
    with connect() as c:
        existing = c.execute(
            "SELECT id FROM subscriptions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if existing:
            c.execute(
                """UPDATE subscriptions SET
                   stripe_customer_id = ?, stripe_subscription_id = ?, stripe_price_id = ?,
                   plan_name = ?, amount = ?, currency = ?, status = ?,
                   current_period_end = ?, cancel_at_period_end = ?,
                   last_successful_payment_at = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE user_id = ?""",
                (*values, user_id),
            )
        else:
            c.execute(
                """INSERT INTO subscriptions (
                   stripe_customer_id, stripe_subscription_id, stripe_price_id,
                   plan_name, amount, currency, status, current_period_end,
                   cancel_at_period_end, last_successful_payment_at, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*values, user_id),
            )
    _stripe_reconcile_cache.pop(user_id, None)


# Cache em memória para evitar chamadas bloqueantes repetitivas à API da Stripe
_stripe_reconcile_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}
RECONCILE_CACHE_TTL = 300  # 5 minutos

def get_user_subscription_status(user_id: int, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Retorna o estado detalhado da assinatura do utilizador.
    Verifica se o acesso está liberado, status de pagamento e período de vigência.
    Se o status local estiver inativo mas a Stripe estiver configurada,
    faz auto-reconciliação com cache de 5 minutos para performance ultra-rápida.
    """
    import time

    sub_data = _get_stored_subscription(user_id) or {}
    status = sub_data.get("status", "none")

    # Se estiver marcado como ativo, verifica se o período não expirou
    has_active_access = False
    if status in ("active", "trialing"):
        period_end = sub_data.get("current_period_end")
        if period_end:
            try:
                if isinstance(period_end, (int, float)):
                    end_dt = datetime.fromtimestamp(period_end, tz=timezone.utc)
                else:
                    pe_str = str(period_end).replace("Z", "+00:00")
                    end_dt = datetime.fromisoformat(pe_str)
                has_active_access = datetime.now(timezone.utc) <= (end_dt + timedelta(days=1))
            except Exception:
                logger.warning(
                    "[Stripe] Data de renovação inválida na subscrição do utilizador %s.",
                    user_id,
                )
                has_active_access = False
        else:
            has_active_access = True
    elif status in ("past_due", "unpaid", "incomplete"):
        has_active_access = False

    # Evita chamadas externas repetidas, exceto quando a reconciliação é solicitada explicitamente.
    now = time.time()
    cached_reconcile = _stripe_reconcile_cache.get(user_id)
    recently_checked = cached_reconcile and (now - cached_reconcile[0] < RECONCILE_CACHE_TTL)

    # A atualização manual sempre consulta a Stripe, inclusive para corrigir estados locais ativos obsoletos.
    if is_stripe_configured() and (
        force_refresh or (not has_active_access and not recently_checked)
    ):
        try:
            stripe.api_key = get_stripe_secret_key()
            customer_id = sub_data.get("stripe_customer_id")
            user_email = None

            with connect() as c:
                u_row = c.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
                if u_row:
                    user_email = u_row["email"]

            if not customer_id and user_email:
                try:
                    cust_res = stripe.Customer.list(email=user_email, limit=1)
                    if cust_res and len(cust_res.data) > 0:
                        customer_id = cust_res.data[0].id
                        sub_data["stripe_customer_id"] = customer_id
                except Exception as exc:
                    if force_refresh:
                        raise RuntimeError(
                            "Não foi possível localizar o cliente na Stripe."
                        ) from exc
                    logger.warning("[Auto-Reconciliação Stripe] Falha ao localizar cliente: %s", exc)

            if customer_id:
                try:
                    subs_list = stripe.Subscription.list(customer=customer_id, status="all", limit=5)
                    subscriptions = list(subs_list.data)
                    active_subscription = next(
                        (
                            item for item in subscriptions
                            if getattr(item, "status", None) in ("active", "trialing")
                        ),
                        None,
                    )
                    selected_subscription = active_subscription or next(
                        (
                            item for item in subscriptions
                            if getattr(item, "id", None)
                            == sub_data.get("stripe_subscription_id")
                        ),
                        subscriptions[0] if subscriptions else None,
                    )
                    if selected_subscription:
                        selected_status = getattr(selected_subscription, "status", "inactive")
                        period_end_dt = datetime.fromtimestamp(
                            selected_subscription.current_period_end,
                            tz=timezone.utc,
                        ).isoformat()
                        price_id = get_stripe_price_id()
                        try:
                            if selected_subscription.items and selected_subscription.items.data:
                                price_id = selected_subscription.items.data[0].price.id
                        except Exception as exc:
                            logger.warning(
                                "[Stripe] Não foi possível ler o preço da assinatura %s: %s",
                                getattr(selected_subscription, "id", ""),
                                exc,
                            )
                        sub_data.update({
                            "stripe_customer_id": customer_id,
                            "stripe_subscription_id": getattr(
                                selected_subscription,
                                "id",
                                sub_data.get("stripe_subscription_id") or "",
                            ),
                            "stripe_price_id": price_id,
                            "plan_name": PLAN_NAME,
                            "amount": PLAN_AMOUNT_CENTS,
                            "currency": PLAN_CURRENCY,
                            "status": selected_status,
                            "current_period_end": period_end_dt,
                            "cancel_at_period_end": bool(
                                getattr(selected_subscription, "cancel_at_period_end", False)
                            ),
                        })
                        subscription_id = str(
                            getattr(selected_subscription, "id", "")
                        )
                        if (
                            selected_status in ("active", "trialing")
                            and not sub_data.get("last_successful_payment_at")
                        ):
                            paid_at = _get_latest_successful_payment_at(subscription_id)
                            if paid_at:
                                sub_data["last_successful_payment_at"] = paid_at
                        _save_stored_subscription(user_id, sub_data)
                        status = selected_status
                        has_active_access = selected_status in ("active", "trialing")
                        try:
                            period_end = datetime.fromisoformat(
                                period_end_dt.replace("Z", "+00:00")
                            )
                            has_active_access = has_active_access and (
                                datetime.now(timezone.utc)
                                <= period_end + timedelta(days=1)
                            )
                        except (TypeError, ValueError):
                            has_active_access = False
                        logger.info(
                            "[Auto-Reconciliação Stripe] Assinatura %s reconciliada para user %s (status=%s).",
                            subscription_id,
                            user_id,
                            selected_status,
                        )
                    else:
                        if force_refresh:
                            _save_stored_subscription(user_id, {"status": "inactive"})
                            status = "inactive"
                            has_active_access = False
                except Exception as exc:
                    if force_refresh:
                        raise RuntimeError(
                            "Não foi possível consultar as assinaturas na Stripe."
                        ) from exc
                    logger.warning("[Auto-Reconciliação Stripe] Falha ao consultar assinaturas: %s", exc)
            elif force_refresh:
                _save_stored_subscription(user_id, {"status": "inactive"})
                status = "inactive"
                has_active_access = False
            _stripe_reconcile_cache[user_id] = (time.time(), sub_data)
        except Exception as ex:
            _stripe_reconcile_cache.pop(user_id, None)
            logger.debug(f"[Auto-Reconciliação Stripe] Verificação ignorada: {ex}")
            if force_refresh:
                raise RuntimeError(
                    "Não foi possível atualizar o estado do pagamento com a Stripe."
                ) from ex

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
        raise RuntimeError("A integração Stripe não está configurada.")

    stripe.api_key = get_stripe_secret_key()
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["subscription", "customer"])
    except Exception as exc:
        logger.exception("[Stripe Checkout] Falha ao consultar sessão %s", session_id)
        raise RuntimeError("Não foi possível confirmar o pagamento com a Stripe.") from exc

    client_reference_id = session.get("client_reference_id")
    metadata = session.get("metadata") or {}
    metadata_user_id = metadata.get("user_id") if hasattr(metadata, "get") else None
    session_user_id = client_reference_id or metadata_user_id
    if str(session_user_id or "") != str(user_id):
        raise PermissionError("Esta sessão de pagamento não pertence a esta conta.")

    session_status = session.get("status")
    payment_status = session.get("payment_status")
    if session_status != "complete" or payment_status not in ("paid", "no_payment_required"):
        raise ValueError("A Stripe ainda não confirmou a conclusão do pagamento.")

    customer = session.get("customer")
    customer_id = (
        customer.id if hasattr(customer, "id")
        else customer.get("id") if hasattr(customer, "get")
        else customer if isinstance(customer, str)
        else None
    )
    sub = session.get("subscription")
    sub_id = (
        sub.id if hasattr(sub, "id")
        else sub.get("id") if hasattr(sub, "get")
        else sub if isinstance(sub, str)
        else None
    )
    if not sub_id:
        raise ValueError("A sessão concluída não contém uma assinatura Stripe.")

    try:
        if isinstance(sub, str):
            sub = stripe.Subscription.retrieve(sub_id)
        sub_status = getattr(sub, "status", None) or sub.get("status")
        if sub_status not in ("active", "trialing"):
            raise ValueError(
                f"A assinatura Stripe ainda não está ativa (status: {sub_status or 'desconhecido'})."
            )
        current_period_end = getattr(sub, "current_period_end", None)
        if current_period_end is None:
            current_period_end = sub.get("current_period_end")
        period_end_dt = (
            datetime.fromtimestamp(current_period_end, tz=timezone.utc).isoformat()
            if isinstance(current_period_end, (int, float))
            else str(current_period_end or "")
        )
        cancel_at = getattr(sub, "cancel_at_period_end", None)
        if cancel_at is None:
            cancel_at = sub.get("cancel_at_period_end", False)
        price_id = get_stripe_price_id()
        items = sub.get("items") if isinstance(sub, dict) else getattr(sub, "items", None)
        item_data = getattr(items, "data", None) if items is not None else None
        if item_data is None and hasattr(items, "get"):
            item_data = items.get("data")
        if item_data:
            first_item = item_data[0]
            price = getattr(first_item, "price", None) or first_item.get("price")
            stripe_price_id = getattr(price, "id", None) if price is not None else None
            if stripe_price_id is None and hasattr(price, "get"):
                stripe_price_id = price.get("id")
            if stripe_price_id:
                price_id = stripe_price_id
    except (ValueError, PermissionError):
        raise
    except Exception as exc:
        logger.exception("[Stripe Checkout] Falha ao consultar assinatura %s", sub_id)
        raise RuntimeError("Não foi possível confirmar a assinatura com a Stripe.") from exc

    record = {
        "stripe_customer_id": str(customer_id or ""),
        "stripe_subscription_id": str(sub_id),
        "stripe_price_id": str(price_id or get_stripe_price_id() or ""),
        "plan_name": PLAN_NAME,
        "amount": PLAN_AMOUNT_CENTS,
        "currency": PLAN_CURRENCY,
        "status": sub_status,
        "current_period_end": period_end_dt or None,
        "cancel_at_period_end": bool(cancel_at),
    }
    if payment_status == "paid":
        record["last_successful_payment_at"] = _get_latest_successful_payment_at(str(sub_id))
    _save_stored_subscription(user_id, record)
    logger.info(
        "[Stripe Checkout] Sessão %s confirmada para user %s (status=%s).",
        session_id,
        user_id,
        sub_status,
    )
    return get_user_subscription_status(user_id)


def is_subscription_active(user_id: int) -> bool:
    """Verifica se o utilizador possui acesso SaaS liberado por pagamento em dia."""
    # Se a Stripe não estiver configurada no .env (modo de desenvolvimento inicial livre), permite acesso
    if not is_stripe_configured():
        return True
    status = get_user_subscription_status(user_id)
    return status["has_active_subscription"]


def schedule_subscription_cancellation(user_id: int) -> Dict[str, Any]:
    """Agenda o cancelamento no fim do período pago sem emitir reembolso."""
    with connect() as c:
        row = c.execute(
            """SELECT stripe_customer_id, stripe_subscription_id, status,
                      current_period_end, cancel_at_period_end
               FROM subscriptions WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
        if row:
            row = dict(row)

        if not row:
            legacy = c.execute(
                """SELECT metadata FROM business_info
                   WHERE user_id = ? AND kind IN ('subscription', 'assinatura')
                   ORDER BY id DESC LIMIT 1""",
                (user_id,),
            ).fetchone()
            if legacy:
                raw_metadata = legacy["metadata"]
                data = (
                    json.loads(raw_metadata)
                    if isinstance(raw_metadata, str)
                    else raw_metadata
                )
                row = data or {}

    if not row:
        return {"scheduled": False, "current_period_end": None}

    subscription_id = str(row.get("stripe_subscription_id") or "").strip()
    status = str(row.get("status") or "inactive")
    if not subscription_id:
        if status in ("active", "trialing", "past_due", "unpaid", "incomplete"):
            raise RuntimeError(
                "A assinatura está ativa, mas o identificador Stripe não está salvo. "
                "A conta foi preservada; contate o suporte para cancelar a cobrança."
            )
        return {"scheduled": False, "current_period_end": row.get("current_period_end")}

    if not is_stripe_configured():
        raise RuntimeError(
            "A Stripe não está configurada. A conta foi preservada e a assinatura "
            "não foi cancelada; configure a integração e tente novamente."
        )

    stripe.api_key = get_stripe_secret_key()
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        actual_customer_id = subscription.get("customer")
        if hasattr(actual_customer_id, "id"):
            actual_customer_id = actual_customer_id.id
        expected_customer_id = str(row.get("stripe_customer_id") or "").strip()
        if expected_customer_id and str(actual_customer_id or "") != expected_customer_id:
            raise RuntimeError(
                "A assinatura Stripe não corresponde ao cliente salvo. "
                "A conta foi preservada por segurança."
            )

        remote_status = str(subscription.get("status") or status)
        if remote_status not in ("canceled", "incomplete_expired"):
            if not subscription.get("cancel_at_period_end"):
                subscription = stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True,
                )
            if not subscription.get("cancel_at_period_end"):
                raise RuntimeError(
                    "A Stripe não confirmou o cancelamento no fim do período."
                )

        period_end = subscription.get("current_period_end")
        if isinstance(period_end, (int, float)):
            period_end = datetime.fromtimestamp(
                period_end, tz=timezone.utc
            ).isoformat()
        elif period_end is not None:
            period_end = str(period_end)

    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception("Falha ao agendar cancelamento Stripe para user_id=%s", user_id)
        raise RuntimeError(
            "A Stripe não confirmou o cancelamento. A conta foi preservada; "
            "verifique a integração e tente novamente."
        ) from exc

    try:
        with connect() as c:
            c.execute(
                """UPDATE subscriptions
                   SET cancel_at_period_end = ?, current_period_end = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE user_id = ?""",
                (1, period_end, user_id),
            )
    except Exception as exc:
        logger.exception(
            "Stripe confirmou cancelamento, mas falhou atualizar o registro local user_id=%s",
            user_id,
        )
        raise RuntimeError(
            "A Stripe confirmou que a assinatura não será renovada, mas não foi possível "
            "atualizar o registro local. A conta foi preservada; tente novamente."
        ) from exc

    return {
        "scheduled": remote_status not in ("canceled", "incomplete_expired"),
        "current_period_end": period_end or row.get("current_period_end"),
    }


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
                logger.exception("Falha ao persistir assinatura do checkout concluído.")
                raise RuntimeError(
                    "Não foi possível persistir o estado da assinatura do checkout."
                ) from ex
        else:
            raise RuntimeError(
                "O evento de checkout concluído não contém o utilizador ou a assinatura."
            )

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
                    with connect() as c:
                        r = c.execute(
                            "SELECT user_id FROM subscriptions WHERE stripe_customer_id = ?",
                            (customer_id,),
                        ).fetchone()
                        if not r and subscription_id:
                            r = c.execute(
                                "SELECT user_id FROM subscriptions WHERE stripe_subscription_id = ?",
                                (subscription_id,),
                            ).fetchone()
                    if r:
                        user_id = r["user_id"]

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
                else:
                    raise RuntimeError(
                        "Não foi possível associar a fatura paga a uma conta Drexier."
                    )
            except Exception as ex:
                logger.exception("Falha ao processar fatura paga.")
                raise RuntimeError(
                    "Não foi possível persistir o pagamento confirmado."
                ) from ex

    # 3. Evento: Pagamento recusado no cartão do cliente
    elif event_type == "invoice.payment_failed":
        invoice = event_data
        customer_id = invoice.get("customer")
        subscription_id = invoice.get("subscription")

        logger.warning(f"[Stripe Webhook] Cobrança recusada no cartão para customer {customer_id}.")
        try:
            with connect() as c:
                r = c.execute("SELECT user_id FROM subscriptions WHERE stripe_customer_id = ?", (customer_id,)).fetchone()
                if not r and subscription_id:
                    r = c.execute(
                        "SELECT user_id FROM subscriptions WHERE stripe_subscription_id = ?",
                        (subscription_id,),
                    ).fetchone()
            if not r:
                raise RuntimeError(
                    "Não foi possível associar a cobrança recusada a uma conta Drexier."
                )
            _save_stored_subscription(r["user_id"], {"status": "past_due"})
        except Exception as ex:
            logger.exception("Falha ao persistir cobrança recusada.")
            raise RuntimeError("Não foi possível atualizar o estado do pagamento.") from ex

    # 4. Evento: Atualização de assinatura (troca de cartão, cancelamento agendado)
    elif event_type == "customer.subscription.updated":
        sub = event_data
        subscription_id = sub.get("id")
        customer_id = sub.get("customer")
        status = sub.get("status")

        try:
            with connect() as c:
                r = c.execute("SELECT user_id FROM subscriptions WHERE stripe_customer_id = ?", (customer_id,)).fetchone()
                if not r:
                    r = c.execute(
                        "SELECT user_id FROM subscriptions WHERE stripe_subscription_id = ?",
                        (subscription_id,),
                    ).fetchone()
            if not r:
                raise RuntimeError(
                    "Não foi possível associar a assinatura atualizada a uma conta Drexier."
                )
            period_end_dt = datetime.fromtimestamp(sub["current_period_end"], tz=timezone.utc).isoformat()
            _save_stored_subscription(r["user_id"], {
                "stripe_customer_id": str(customer_id or ""),
                "stripe_subscription_id": str(subscription_id or ""),
                "status": status,
                "current_period_end": period_end_dt,
                "cancel_at_period_end": sub.get("cancel_at_period_end", False)
            })
            logger.info(f"[Stripe Webhook] Assinatura do utilizador {r['user_id']} atualizada para {status}.")
        except Exception as ex:
            logger.exception("Falha ao persistir atualização de assinatura.")
            raise RuntimeError("Não foi possível atualizar o estado da assinatura.") from ex

    # 5. Evento: Assinatura cancelada definitivamente
    elif event_type == "customer.subscription.deleted":
        sub = event_data
        customer_id = sub.get("customer")
        subscription_id = sub.get("id")
        try:
            with connect() as c:
                r = c.execute("SELECT user_id FROM subscriptions WHERE stripe_customer_id = ?", (customer_id,)).fetchone()
                if not r:
                    r = c.execute(
                        "SELECT user_id FROM subscriptions WHERE stripe_subscription_id = ?",
                        (subscription_id,),
                    ).fetchone()
            if not r:
                raise RuntimeError(
                    "Não foi possível associar a assinatura cancelada a uma conta Drexier."
                )
            _save_stored_subscription(r["user_id"], {
                "stripe_customer_id": str(customer_id or ""),
                "stripe_subscription_id": str(subscription_id or ""),
                "status": "canceled",
            })
            logger.info(f"[Stripe Webhook] Assinatura do utilizador {r['user_id']} cancelada.")
        except Exception as ex:
            logger.exception("Falha ao persistir cancelamento de assinatura.")
            raise RuntimeError("Não foi possível atualizar o estado da assinatura.") from ex

    return {"received": True, "event_type": event_type}
