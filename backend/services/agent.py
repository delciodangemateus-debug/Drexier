import json
import logging
import os
import re
from typing import List, Dict, Optional, Any
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("drexier.ai")

UNKNOWN_REPLY = "De momento, não tenho essa informação cadastrada. Tem alguma outra questão em que possa ajudar?"

def get_gemini_config() -> Dict[str, str]:
    """Obtém a configuração do Gemini a partir das variáveis de ambiente."""
    # Recarrega variáveis caso tenham sido atualizadas
    load_dotenv(override=False)
    api_key = (
        os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("AI_API_KEY", "").strip()
    )
    model = (
        os.getenv("GEMINI_MODEL", "").strip()
        or os.getenv("AI_MODEL", "").strip()
        or "gemini-3.8-flash"
    )
    base_url = (
        os.getenv("GEMINI_BASE_URL", "").strip()
        or "https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/")
    provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
    return {
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "provider": provider,
    }

def compose_context(info_rows: List[Any]) -> str:
    """Formata o conhecimento do negócio cadastrado para ser consumido pela IA."""
    if not info_rows:
        return "(Ainda sem informações detalhadas cadastradas)"
    
    entries = []
    for r in info_rows:
        kind = r["kind"] if isinstance(r, dict) else r["kind"]
        title = r["title"] if isinstance(r, dict) else r["title"]
        content = r["content"] if isinstance(r, dict) else r["content"]
        meta = r.get("metadata", {}) if isinstance(r, dict) else {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta or "{}")
            except Exception:
                meta = {}
        items = meta.get("items") if isinstance(meta, dict) else None
        if items and isinstance(items, list):
            item_lines = []
            for it in items:
                name = it.get("name") or it.get("title") or ""
                price = it.get("price", "")
                details = it.get("details") or it.get("description", "")
                parts = [name]
                if price:
                    parts.append(f"Preço: {price}")
                if details:
                    parts.append(f"Detalhes: {details}")
                if name:
                    item_lines.append("  • " + " | ".join(parts))
            if item_lines:
                entries.append(f"[{kind.upper()}] {title}:\n" + "\n".join(item_lines))
                continue
        entries.append(f"[{kind.upper()}] {title}: {content}")
    return "\n\n".join(entries)

def build_system_instruction(
    business_context: str,
    instructions: str = "",
    language: str = "Português",
    business_name: str = "nosso negócio",
    business_type: str = "Serviços",
    business_description: str = "",
    mandatory_responses: Optional[Dict[str, str]] = None
) -> str:
    """
    Constrói as diretrizes para o Gemini atuar como o atendente principal e condutor da conversa.
    O agente é consultivo, humano, respeitoso e adapta-se estritamente à mensagem enviada.
    """
    mandatory_text = ""
    if mandatory_responses:
        valid_items = [f"- {k}: {v}" for k, v in mandatory_responses.items() if v]
        if valid_items:
            mandatory_text = "\nRESPOSTAS OBRIGATÓRIAS / DIRETRIZES ESPECÍFICAS:\n" + "\n".join(valid_items)

    system_prompt = f"""Você é o atendente consultivo oficial de {business_name} ({business_type}).
Idioma principal: {language}.

MISSÃO E POSTURA:
1. Você responde às mensagens dos clientes e é responsável por DIRIGIR a conversa ativamente com foco no objetivo do negócio (esclarecer dúvidas, agendamentos, atendimento e vendas).
2. ADAPTAÇÃO AO CONTEXTO DA MENSAGEM (NUNCA ATIRAR PRODUTOS NA CARA DO CLIENTE):
   - Você NÃO deve se basear cegamente em despejar dados, preços ou produtos da Base de Negócio logo na primeira mensagem se o cliente não perguntou por eles.
   - Responda estritamente e com empatia ao que o cliente disse ou perguntou.
   - EXEMPLO FUNDAMENTAL: Se o cliente disser apenas uma saudação (ex: "Olá, boa tarde", "Bom dia", "Olá tudo bem?"), responda cordialmente acolhendo o cliente, identificando-se como atendente de {business_name} e perguntando gentilmente em que pode ajudar. Exemplo: "Olá, boa tarde! Aqui é do atendimento da {business_name}. Em que podemos ajudar hoje?".
   - Somente apresente respostas sobre produtos, preços ou regras mediante a pergunta ou dúvida expressa pelo cliente.
3. RESPOSTAS ESPECÍFICAS E DIRECIONADAS AO QUE FOI PERGUNTADO:
   - Apresente respostas objetivas ao que foi solicitado, dentro da janela dos assuntos da empresa (produtos, serviços, horários, marcações, agendamentos, políticas, instruções cadastradas, suporte e reclamações).
   - Não liste produtos ou serviços irrelevantes para a dúvida apresentada.
   - Conduza as respostas de forma livre, fluida e amigável sobre o negócio, nunca como um chat robótico de perguntas e respostas.
4. GESTÃO DE MARCAÇÕES E AGENDAMENTOS:
   - Se o cliente desejar marcar ou agendar uma data/horário ou comprar, acolha o pedido, confirme os detalhes solicitados e informe com simpatia que o agendamento/pedido foi registrado para validação e confirmação da nossa equipe.
5. COMPLETUDE OBRIGATÓRIA DA RESPOSTA (NUNCA CORTAR FRASES):
   - NUNCA deixe frases inacabadas, pensamentos interrompidos ou mensagens cortadas no meio.
   - Toda e qualquer frase que iniciar deve ser obrigatoriamente concluída com ponto final, exclamação ou interrogação.
   - Responda de forma completa, limpa e coesa até o ponto final.

SOBRE O NEGÓCIO:
{business_description or f"Atendimento e serviços especializados em {business_type}."}

BASE DE CONHECIMENTO DO NEGÓCIO:
{business_context}

INSTRUÇÕES DO PROPRIETÁRIO:
{instructions or "Atenda com respeito, agilidade e simpatia, sempre priorizando as necessidades do cliente."}
{mandatory_text}

REGRAS CRÍTICAS DE CONFIABILIDADE (GROUNDING):
- Suas recomendações e informações devem ser baseadas EXCLUSIVAMENTE nos itens e dados cadastrados na Base do Negócio.
- NUNCA invente produtos, marcas, preços ou condições que não estejam cadastrados.
- Se não houver nenhum produto ou dado que atenda ao pedido do cliente, explique com cordialidade e objetividade:
  "{UNKNOWN_REPLY}"
"""
    return system_prompt.strip()

def format_gemini_contents(history: List[Dict[str, str]], current_message: str) -> List[Dict[str, Any]]:
    """
    Formata o histórico para o formato do Gemini API (roles: 'user' e 'model').
    Garante alternância e funde mensagens consecutivas do mesmo emissor.
    """
    contents: List[Dict[str, Any]] = []

    for msg in history:
        sender = msg.get("sender", "customer")
        content = msg.get("content", "").strip()
        if not content:
            continue
        
        role = "user" if sender == "customer" else "model"
        
        if contents and contents[-1]["role"] == role:
            # Funde textos consecutivos do mesmo papel
            contents[-1]["parts"][0]["text"] += f"\n{content}"
        else:
            contents.append({"role": role, "parts": [{"text": content}]})

    # Adiciona a mensagem atual do cliente
    if contents and contents[-1]["role"] == "user":
        contents[-1]["parts"][0]["text"] += f"\n{current_message.strip()}"
    else:
        contents.append({"role": "user", "parts": [{"text": current_message.strip()}]})

    return contents

def ensure_complete_sentence(text: str) -> str:
    """
    Garante que a resposta gerada pela IA nunca seja entregue cortada no meio de uma frase.
    Se o texto tiver sido truncado por limites de tokens ou interrupção na conexão:
    1. Se já terminar com pontuação terminal válida (. ! ? … » " ' ) ou emoji, preserva.
    2. Remove caracteres soltos de ligação no final (, ; : - – / \).
    3. Se houver frases completas anteriores no texto, descarta o fragmento final cortado,
       mantendo a resposta 100% íntegra, fluida e natural.
    4. Se for uma frase única sem pontuação terminal, finaliza adequadamente com ponto final.
    """
    if not text:
        return ""
    
    clean = text.strip()
    if not clean:
        return ""

    terminal_chars = (".", "!", "?", "…", "»", '"', "'", ")", "]", "}", "😊", "👍", "🙏", "✨", "👋", "🤝", "🎯", "💬")
    
    if clean.endswith(terminal_chars):
        return clean

    # Remove pontuações de conexão pendentes no final
    clean = re.sub(r"[\s,;:\-–—\\/]+$", "", clean)
    if clean.endswith(terminal_chars):
        return clean

    # Procura a última pontuação de término de frase válida
    matches = list(re.finditer(r"[.!?…][\"')\]}]*(?:\s+|\Z)", clean))
    if matches:
        last_match = matches[-1]
        cut_index = last_match.end()
        candidate = clean[:cut_index].strip()
        # Se a porção preservada for significativa (pelo menos 20 caracteres ou 35% do texto total)
        if len(candidate) >= 20 and len(candidate) >= len(clean) * 0.35:
            return candidate

    # Se não houver frase anterior completa ou o texto for curto, fecha com ponto final
    return clean + "."

async def call_gemini_api(
    system_instruction: str,
    contents: List[Dict[str, Any]],
    api_key: str,
    model: str,
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
) -> Optional[str]:
    """Chama a API nativa do Google Gemini via HTTP REST assíncrono com tolerância a falhas e sem cortes."""
    candidate_models = [model]
    for fallback_model in ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash"]:
        if fallback_model not in candidate_models:
            candidate_models.append(fallback_model)

    payload = {
        "system_instruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.55,
            "maxOutputTokens": 2500,
            "topP": 0.95
        }
    }

    client_timeout = httpx.Timeout(45.0, connect=10.0)

    async with httpx.AsyncClient(timeout=client_timeout) as client:
        for m in candidate_models:
            url = f"{base_url}/models/{m}:generateContent?key={api_key}"
            try:
                response = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload
                )
                if response.status_code in (404, 429, 503) and m != candidate_models[-1]:
                    logger.info(f"Modelo {m} retornou {response.status_code}, a tentar alternativa...")
                    continue
                response.raise_for_status()
                data = response.json()
                
                candidates = data.get("candidates", [])
                if candidates:
                    first_candidate = candidates[0]
                    parts = first_candidate.get("content", {}).get("parts", [])
                    text_pieces = []
                    for p in parts:
                        if isinstance(p, dict):
                            # Ignora blocos de pensamento interno se o modelo os emitir
                            if p.get("thought") is True:
                                continue
                            txt = p.get("text", "")
                            if txt:
                                text_pieces.append(txt)
                    
                    full_reply = "".join(text_pieces).strip()
                    if full_reply:
                        return ensure_complete_sentence(full_reply)
            except Exception as e:
                logger.warning(f"Falha na chamada com o modelo {m}: {e}")
                if m == candidate_models[-1]:
                    return None
    return None

async def call_openai_compatible_api(
    system_instruction: str,
    history: List[Dict[str, str]],
    current_message: str,
    api_key: str,
    model: str,
    base_url: str
) -> Optional[str]:
    """Suporte opcional para provedores compatíveis com OpenAI."""
    messages = [{"role": "system", "content": system_instruction}]
    for msg in history:
        role = "user" if msg.get("sender") == "customer" else "assistant"
        messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": current_message})

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.35,
                    "max_tokens": 2000
                }
            )
            response.raise_for_status()
            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip()
            return ensure_complete_sentence(raw)
    except Exception as e:
        logger.warning(f"Falha na API OpenAI compatível: {e}")
        return None

def is_initial_greeting(text: str) -> bool:
    clean = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = clean.split()
    if not words:
        return False
    greeting_words = {"ola", "olá", "oi", "bom", "boa", "dia", "tarde", "noite", "tudo", "bem", "prezados", "caros", "alô", "alo"}
    if all(w in greeting_words for w in words) or (len(words) <= 3 and words[0] in ("ola", "olá", "oi", "bom", "boa")):
        return True
    return False

def local_fallback(message: str, info_rows: List[Any], business_name: str = "nosso negócio") -> str:
    """
    Fallback seguro e determinístico caso a IA externa não esteja disponível.
    Responde cordialmente a saudações ou fornece a informação específica solicitada sem despejar catálogos.
    """
    if is_initial_greeting(message):
        return f"Olá, boa tarde! Aqui é do atendimento de {business_name}. Em que podemos ajudar hoje?"

    context = compose_context(info_rows)
    if not context.strip() or context.startswith("(Ainda sem"):
        return UNKNOWN_REPLY

    words = {w.lower().strip(".,?!:;") for w in message.split() if len(w) > 3}
    scored = []
    for row in info_rows:
        title = row["title"] if isinstance(row, dict) else row["title"]
        content = row["content"] if isinstance(row, dict) else row["content"]
        text = f"{title}: {content}".strip()
        hay = text.lower()
        score = sum(1 for w in words if w in hay)
        if score:
            scored.append((score, text))

    if not scored:
        return UNKNOWN_REPLY

    scored.sort(key=lambda item: item[0], reverse=True)
    best_item = scored[0][1]
    return f"Olá! Relativamente ao que perguntou:\n• {best_item}\n\nFicamos à sua inteira disposição se desejar saber mais ou agendar!"

async def draft_reply(
    message: str,
    info_rows: List[Any],
    instructions: str = "",
    language: str = "Português",
    history: Optional[List[Dict[str, str]]] = None,
    business_name: str = "nosso negócio",
    business_type: str = "Serviços",
    business_description: str = "",
    mandatory_responses: Optional[Dict[str, str]] = None
) -> str:
    """
    Ponto de entrada do sistema de atendimento com IA.
    Utiliza o Gemini como motor principal para gerar respostas e conduzir a conversa.
    Mantém histórico, regras do proprietário e dados do negócio.
    """
    history = history or []
    config = get_gemini_config()
    context = compose_context(info_rows)

    system_instruction = build_system_instruction(
        business_context=context,
        instructions=instructions,
        language=language,
        business_name=business_name,
        business_type=business_type,
        business_description=business_description,
        mandatory_responses=mandatory_responses
    )

    # 1. Tenta usar o Gemini nativo se a chave estiver presente
    if config["api_key"]:
        if config["provider"] == "gemini":
            contents = format_gemini_contents(history, message)
            reply = await call_gemini_api(
                system_instruction=system_instruction,
                contents=contents,
                api_key=config["api_key"],
                model=config["model"],
                base_url=config["base_url"]
            )
            if reply:
                return reply
        elif config["provider"] == "openai":
            base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            reply = await call_openai_compatible_api(
                system_instruction=system_instruction,
                history=history,
                current_message=message,
                api_key=config["api_key"],
                model=config["model"],
                base_url=base_url
            )
            if reply:
                return reply

    # 2. Se a API do Gemini não estiver configurada ou falhar, ativa o fallback local
    return local_fallback(message, info_rows, business_name)
