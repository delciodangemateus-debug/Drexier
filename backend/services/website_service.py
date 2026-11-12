"""
Serviço Oficial Drexier AI para Integração de Websites Externos via Widget.
Gera o código HEAD, gerencia a conversa de criação/edição do agente com IA,
valida a instalação real nos websites e atende visitantes em tempo real.
"""

import asyncio
import json
import logging
import os
import re
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import httpx

from backend.services.agent import get_gemini_config, call_gemini_api

logger = logging.getLogger("drexier.website_service")

DEFAULT_THEME_COLOR = "#18181b"  # Preto/Grafite neutro
DEFAULT_POSITION = "bottom-right"
INITIAL_AI_PROMPT = (
    "Como imagina o seu agente virtual? Descreva o estilo visual, posicionamento, personalidade e comportamento pretendidos."
)


def normalize_domain(val: str) -> str:
    """Normaliza URLs ou domínios para formato limpo (sem protocolo, www opcional, porta ou caminhos)."""
    if not val:
        return ""
    clean = val.strip().lower()
    if not clean.startswith(("http://", "https://")):
        clean = "https://" + clean
    try:
        parsed = urlparse(clean)
        netloc = parsed.netloc or parsed.path
        # Remove porta se presente
        host = netloc.split(":")[0].strip()
        # Remove eventuais barras ou parâmetros
        host = host.split("/")[0].strip()
        return host
    except Exception:
        return val.strip().lower()


def match_domain(detected_origin: str, allowed_domain: str) -> bool:
    """Valida se o domínio que originou a requisição confere com o domínio autorizado."""
    if not allowed_domain or allowed_domain.strip() in ("", "*"):
        return True

    clean_allowed = normalize_domain(allowed_domain)
    clean_detected = normalize_domain(detected_origin)

    if not clean_allowed or not clean_detected:
        return True

    # Equivalência direta
    if clean_detected == clean_allowed:
        return True

    # Trata variações com e sem 'www.'
    no_www_allowed = re.sub(r"^www\.", "", clean_allowed)
    no_www_detected = re.sub(r"^www\.", "", clean_detected)
    if no_www_allowed == no_www_detected:
        return True

    # Suporte a subdomínios se allowed foi informado como domínio raiz
    if clean_detected.endswith("." + no_www_allowed):
        return True

    # Suporte a testes locais
    if clean_detected in ("localhost", "127.0.0.1") and clean_allowed in ("localhost", "127.0.0.1"):
        return True

    return False


def generate_site_key() -> str:
    """
    Gera um identificador exclusivo, criptograficamente seguro e inviolável (formato Chave de API)
    para a integração de website.
    Formato: drexier_live_sec_<32_bytes_hex>
    """
    return f"drexier_live_sec_{secrets.token_hex(24)}"


def generate_head_code(site_key: str, base_url: str, config: Optional[Dict[str, Any]] = None) -> str:
    """
    Gera o código limpo, moderno e independente para inclusão na secção HEAD do website externo.
    Reflete fielmente os parâmetros visuais, estruturais e comportamentais configurados para o agente.
    """
    clean_base = base_url.rstrip("/") if base_url else ""
    cfg = config or {}
    theme_color = cfg.get("theme_color") or DEFAULT_THEME_COLOR
    position = cfg.get("position") or DEFAULT_POSITION
    agent_name = cfg.get("agent_name") or "Agente Drexier"
    border_radius = cfg.get("border_radius") or "16px"
    button_shape = cfg.get("button_shape") or "circle"
    theme_mode = cfg.get("theme_mode") or "light"

    return (
        f"<!-- Início do Widget Drexier AI -->\n"
        f"<script>\n"
        f"  window.drexierSettings = {{\n"
        f"    siteKey: \"{site_key}\",\n"
        f"    apiUrl: \"{clean_base}/api\",\n"
        f"    themeColor: \"{theme_color}\",\n"
        f"    position: \"{position}\",\n"
        f"    agentName: \"{agent_name}\",\n"
        f"    borderRadius: \"{border_radius}\",\n"
        f"    buttonShape: \"{button_shape}\",\n"
        f"    themeMode: \"{theme_mode}\"\n"
        f"  }};\n"
        f"</script>\n"
        f"<script defer src=\"{clean_base}/widget.js\"></script>\n"
        f"<!-- Fim do Widget Drexier AI -->"
    )


def extract_config_heuristic(
    user_message: str,
    current_config: Dict[str, Any],
    business_name: str,
    business_type: str
) -> Dict[str, Any]:
    """
    Analisa heuristicamente o pedido do utilizador para atualizar parâmetros visuais e comportamentais
    do agente caso o modelo externo não esteja disponível ou devolva formato parcial.
    Padronização padrão inicial: Preto (#18181b), Branco e Cinza (#71717a).
    """
    cfg = dict(current_config or {})
    text = user_message.lower()

    # 1. Posição do botão
    if "esquerda" in text or "left" in text:
        cfg["position"] = "bottom-left"
    elif "direita" in text or "right" in text:
        cfg["position"] = "bottom-right"

    # 2. Cores do tema
    hex_match = re.search(r"#(?:[0-9a-fA-F]{3}){1,2}\b", user_message)
    if hex_match:
        cfg["theme_color"] = hex_match.group(0)
    elif "azul" in text or "blue" in text:
        cfg["theme_color"] = "#2563eb"
    elif "verde" in text or "green" in text:
        cfg["theme_color"] = "#10b981"
    elif "roxo" in text or "lavanda" in text or "violeta" in text:
        cfg["theme_color"] = "#7c3aed"
    elif "preto" in text or "escuro" in text or "dark" in text or "minimalista" in text or "grafite" in text or "cinza" in text:
        cfg["theme_color"] = "#18181b"
    elif "dourado" in text or "ouro" in text:
        cfg["theme_color"] = "#d97706"
    elif "vermelho" in text or "laranja" in text:
        cfg["theme_color"] = "#ea580c"
    elif not cfg.get("theme_color"):
        cfg["theme_color"] = DEFAULT_THEME_COLOR

    # 3. Estrutura e formato visual do card (ditados pelo utilizador)
    if any(w in text for w in ["quadrad", "reto", "reta", "retangular", "sem arredond"]):
        cfg["border_radius"] = "4px"
    elif any(w in text for w in ["cápsula", "capsula", "muito arredondad", "bem redond"]):
        cfg["border_radius"] = "24px"
    elif any(w in text for w in ["arredondad", "curv"]):
        cfg["border_radius"] = "16px"

    if any(w in text for w in ["botão quadrad", "botao quadrad", "botão retangular", "botao retangular"]):
        cfg["button_shape"] = "square"
    elif any(w in text for w in ["botão pílula", "botao pilula", "botão capsula"]):
        cfg["button_shape"] = "pill"
    elif any(w in text for w in ["botão redond", "botao redond", "botão circular", "botao circular"]):
        cfg["button_shape"] = "circle"

    if any(w in text for w in ["tema escuro", "dark mode", "modo escuro", "fundo escuro", "fundo preto", "dark theme"]):
        cfg["theme_mode"] = "dark"
    elif any(w in text for w in ["tema claro", "light mode", "modo claro", "fundo claro", "fundo branco", "clean"]):
        cfg["theme_mode"] = "light"

    # 4. Domínio se citado explicitamente com protocolo ou extensão conhecida
    domain_match = re.search(
        r"\b(?:https?:\/\/|www\.)[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+(?:\/[^\s]*)?"
        r"|\b[a-zA-Z0-9-]+\.(?:com|pt|br|org|net|io|co|app|ai|dev|eu|online|site|store|tech|info|me|biz)(?::\d+)?\b",
        user_message,
        re.IGNORECASE
    )
    if domain_match:
        found_dom = domain_match.group(0).lower()
        if not any(found_dom.endswith(ext) for ext in [".js", ".css", ".png", ".jpg"]):
            cfg["allowed_domain"] = normalize_domain(found_dom)

    # 4. Ajustes no tom e instruções
    existing_inst = cfg.get("agent_instructions", "")
    new_instructions = []
    if "comercial" in text or "vendas" in text or "persuasivo" in text:
        new_instructions.append("Postura altamente orientada a vendas consultivas, geração de valor e fechamento de pedidos ou marcações.")
    if "profissional" in text or "executivo" in text or "formal" in text:
        new_instructions.append("Comunicação executiva, sóbria, formal e altamente precisa.")
    if "descontraído" in text or "amigável" in text or "empático" in text or "simpático" in text:
        new_instructions.append("Comunicação acolhedora, calorosa, empática e fluida com os visitantes do site.")
    if "minimalista" in text or "direto" in text or "conciso" in text:
        new_instructions.append("Respostas extremamente enxutas, objetivas e sem rodeios.")

    if new_instructions:
        joined = " ".join(new_instructions)
        cfg["agent_instructions"] = f"{existing_inst}\n{joined}".strip() if existing_inst else joined

    # 5. Nome e cargo
    if not cfg.get("agent_name") or cfg.get("agent_name") == "Agente Drexier":
        cfg["agent_name"] = f"Assistente {business_name}" if business_name else "Assistente Drexier"

    if not cfg.get("agent_role") or cfg.get("agent_role") == "Atendente Virtual":
        cfg["agent_role"] = f"Atendimento e Vendas • {business_type}" if business_type else "Consultor Online"

    # 6. Mensagem de boas-vindas
    if not cfg.get("greeting_message"):
        bname = business_name or "nossa empresa"
        cfg["greeting_message"] = f"Olá! Bem-vindo à {bname}. Como posso ajudar hoje?"

    return cfg


async def interact_website_agent_ai(
    user: Dict[str, Any],
    user_message: str,
    conversation_history: List[Dict[str, str]],
    current_config: Dict[str, Any]
) -> Tuple[str, Dict[str, Any], bool]:
    """
    Processa a conversa entre o proprietário e a IA Drexier para criação ou edição contínua do agente.
    Retorna: (resposta_da_ia, configuracao_atualizada, pronta_para_gerar).
    """
    gemini_conf = get_gemini_config()
    api_key = gemini_conf.get("api_key")
    business_name = user.get("name") or "nosso negócio"
    business_type = user.get("business_type") or "Serviços e Atendimento"
    business_desc = user.get("business_description") or ""

    # Heurística inicial como baseline segura
    heuristic_cfg = extract_config_heuristic(user_message, current_config, business_name, business_type)

    system_prompt = f"""Você é o Arquiteto de Agentes Virtuais da plataforma Drexier AI.
A sua missão é conversar com o utilizador ({business_name}, ramo: {business_type}) para criar ou evoluir
o agente de atendimento inteligente que será instalado no website externo da empresa através de um widget no HEAD.

DADOS DA EMPRESA:
- Nome: {business_name}
- Tipo: {business_type}
- Descrição: {business_desc or "Empresa focada em atendimento ao cliente de excelência"}

CONFIGURAÇÃO ATUAL DO AGENTE:
- Nome do agente: {current_config.get("agent_name", heuristic_cfg.get("agent_name"))}
- Cargo/Função: {current_config.get("agent_role", heuristic_cfg.get("agent_role"))}
- Cor de destaque: {current_config.get("theme_color", heuristic_cfg.get("theme_color"))}
- Posição do botão: {current_config.get("position", heuristic_cfg.get("position"))}
- Mensagem de boas-vindas: {current_config.get("greeting_message", heuristic_cfg.get("greeting_message"))}
- Diretrizes comportamentais: {current_config.get("agent_instructions", heuristic_cfg.get("agent_instructions"))}
- Domínio autorizado: {current_config.get("allowed_domain", "")}

DIRETRIZES DA SUA RESPOSTA:
1. Responda em Português de forma elegante, acolhedora, executiva e altamente consultiva.
2. Agradeça as orientações do utilizador, resuma as características que compreendeu e explique como essas diretrizes tornarão o atendimento do site mais eficiente.
3. Se o utilizador pediu alguma alteração (ex: "mais profissional", "botão na esquerda", "cor azul", "mais persuasivo"), confirme a atualização com entusiasmo e objetividade.
4. Ao final da sua resposta em texto, OBRIGATORIAMENTE adicione um bloco de código JSON demarcado por ```json ... ``` com a configuração resultante completa, contendo:
   {{
     "agent_name": "Nome oficial do agente",
     "agent_role": "Cargo ou especialidade exibida no cabeçalho",
     "theme_color": "#HEX (ex: #6366f1, #2563eb, #10b981, #0f172a, etc.)",
     "position": "bottom-right" ou "bottom-left",
     "greeting_message": "Frase de boas-vindas do agente para os visitantes",
     "agent_instructions": "Diretrizes específicas de tom de voz, regras e persuasão para o atendimento",
     "allowed_domain": "domínio do site se mencionado, ou manter o existente",
     "ready_to_generate": true
   }}
"""

    gemini_contents: List[Dict[str, Any]] = []
    # Adiciona histórico recente
    for msg in conversation_history[-8:]:
        role = "user" if msg.get("sender") == "user" else "model"
        gemini_contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})

    gemini_contents.append({"role": "user", "parts": [{"text": user_message}]})

    if api_key:
        try:
            # Seleciona modelo configurado ou recorre ao fallback estável com timeout de proteção
            model_to_use = gemini_conf.get("model") or "gemini-3.5-flash"
            raw_ai = await asyncio.wait_for(
                call_gemini_api(
                    system_instruction=system_prompt,
                    contents=gemini_contents,
                    api_key=api_key,
                    model=model_to_use,
                    base_url=gemini_conf.get("base_url", "https://generativelanguage.googleapis.com/v1beta")
                ),
                timeout=5.0
            )
            if raw_ai:
                # Extrai bloco JSON da resposta
                json_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", raw_ai)
                parsed_json = {}
                clean_text = raw_ai
                if json_match:
                    try:
                        parsed_json = json.loads(json_match.group(1))
                        # Remove o bloco json do texto exibido ao utilizador para manter o chat limpo
                        clean_text = raw_ai.replace(json_match.group(0), "").strip()
                    except Exception as err:
                        logger.warning(f"Erro ao parsear JSON da IA: {err}")

                updated_cfg = dict(current_config)
                for k in ["agent_name", "agent_role", "theme_color", "greeting_message", "agent_instructions", "allowed_domain", "border_radius", "button_shape", "theme_mode"]:
                    if k in parsed_json and parsed_json[k]:
                        val = parsed_json[k]
                        if k == "allowed_domain":
                            val = normalize_domain(str(val))
                        updated_cfg[k] = val
                    elif k in heuristic_cfg and heuristic_cfg[k]:
                        updated_cfg[k] = heuristic_cfg[k]

                # Posição: prioriza solicitação explícita do utilizador no pedido
                if "esquerda" in user_message.lower() or "left" in user_message.lower():
                    updated_cfg["position"] = "bottom-left"
                elif "direita" in user_message.lower() or "right" in user_message.lower():
                    updated_cfg["position"] = "bottom-right"
                elif "position" in parsed_json and parsed_json["position"] in ("bottom-right", "bottom-left"):
                    updated_cfg["position"] = parsed_json["position"]
                elif "position" in heuristic_cfg:
                    updated_cfg["position"] = heuristic_cfg["position"]

                return clean_text, updated_cfg, True
        except Exception as e:
            logger.warning(f"Falha na chamada Gemini para criação do agente: {e}")

    # Fallback conversacional determinístico de altíssima qualidade
    updated_cfg = dict(current_config)
    for k, v in heuristic_cfg.items():
        if v:
            updated_cfg[k] = v

    pos_text = "canto inferior direito" if updated_cfg.get("position") == "bottom-right" else "canto inferior esquerdo"
    reply = (
        f"Compreendi perfeitamente a sua visão para o agente virtual de {business_name}! "
        f"Configurei o agente '{updated_cfg.get('agent_name')}' com foco em {business_type}, "
        f"comunicação alinhada aos seus objetivos de atendimento, botão flutuante posicionado no {pos_text} "
        f"e destaque visual na cor {updated_cfg.get('theme_color')}. "
        f"O código de instalação exclusivo para a secção HEAD do seu website foi gerado e está pronto para ser copiado. "
        f"Pode pré-visualizar o widget abaixo ou pedir novos ajustes a qualquer momento!"
    )
    return reply, updated_cfg, True


async def verify_website_installation(
    site_key: str,
    allowed_domain: str,
    last_heartbeat_at: Optional[str] = None
) -> Tuple[str, str, Optional[str]]:
    """
    Executa a verificação real da ligação entre o website externo e o servidor Drexier:
    - Se houver domínio configurado: testa se o site é acessível via HTTP e se o script com o site_key está presente.
    - Avalia o histórico de heartbeats enviados pelo widget real.
    Retorna: (status, error_message, verified_domain) onde status pode ser:
    'active', 'pending', 'disconnected', 'error'.
    """
    clean_domain = normalize_domain(allowed_domain) if allowed_domain else ""

    # Se temos um domínio especificado, tenta verificação de rede ativa no código do website
    if clean_domain and clean_domain not in ("localhost", "127.0.0.1"):
        candidate_urls = [f"https://{clean_domain}", f"http://{clean_domain}"]
        scraped_ok = False
        site_error = None
        detected_domain = None

        timeout = httpx.Timeout(5.0, connect=3.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
            for url in candidate_urls:
                try:
                    res = await client.get(url, headers={"User-Agent": "Drexier-Verification-Bot/1.0"})
                    if res.status_code < 400:
                        detected_domain = clean_domain
                        html = res.text
                        # Verifica se o código do Drexier e a chave do site estão presentes na página
                        has_key = site_key in html
                        has_drexier = "drexier" in html.lower() and ("widget.js" in html.lower() or "drexiersettings" in html.lower())
                        if has_key or has_drexier:
                            scraped_ok = True
                            break
                        else:
                            site_error = "O website respondeu com sucesso, mas o código de instalação do Drexier não foi encontrado no HTML."
                    else:
                        site_error = f"O website respondeu com status HTTP {res.status_code}."
                except Exception as ex:
                    logger.debug(f"Falha ao aceder a {url}: {ex}")
                    site_error = f"Não foi possível estabelecer ligação com {clean_domain}."

        if scraped_ok:
            return "active", "", detected_domain

        # Se a raspagem falhou mas houve heartbeat recente, o widget ainda pode estar ativo (ex: por trás de login ou SPA)
        if last_heartbeat_at:
            try:
                hb_time = datetime.fromisoformat(last_heartbeat_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if (now - hb_time) < timedelta(hours=24):
                    return "active", "", clean_domain
                else:
                    return "disconnected", "A tag do widget não foi detectada no website e o último sinal recebido expirou.", clean_domain
            except Exception:
                pass

        if site_error:
            # Se for erro de conexão ou 404/500, marca erro
            if "Não foi possível" in site_error or "HTTP" in site_error:
                return "error", site_error, None
            # Se o site abriu mas não tem o código
            return "pending", site_error, None

    # Se não temos domínio para testar ativamente, confia no sinal de heartbeat do widget
    if last_heartbeat_at:
        try:
            hb_time = datetime.fromisoformat(last_heartbeat_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            diff = now - hb_time
            if diff < timedelta(days=7):
                return "active", "", None
            else:
                return "disconnected", "Nenhum sinal recebido do widget nos últimos 7 dias. Verifique se o código ainda está instalado.", None
        except Exception:
            return "active", "", None

    return "pending", "Código gerado. Aguardando a instalação no website e a primeira comunicação do widget.", None
