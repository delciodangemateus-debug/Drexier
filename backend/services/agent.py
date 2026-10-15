import json, os
import httpx
from dotenv import load_dotenv
load_dotenv()

UNKNOWN_REPLY = "De momento, não tenho essa informação cadastrada. Tem alguma outra questão em que possa ajudar?"

def compose_context(info_rows):
    return "\n".join(f"[{r['kind']}] {r['title']}: {r['content']}" for r in info_rows)

async def draft_reply(message: str, info_rows, instructions: str = "", language: str = "Português"):
    """Uses configured OpenAI-compatible endpoint when available; otherwise safely uses only known business information."""
    context = compose_context(info_rows)
    api_key = os.getenv("AI_API_KEY", "").strip()
    base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("AI_MODEL", "").strip()
    if api_key and model:
        system = (
            f"És o agente de atendimento de um negócio. Responde em {language}. "
            "Usa exclusivamente a base de informação do negócio abaixo para factos sobre preços, "
            "horários, produtos, serviços, campanhas e marcações. Nunca inventes informação. "
            f"Se a informação não estiver presente, responde exatamente que não tens essa informação "
            f"cadastrada e pergunta se há outra questão. Instruções do proprietário: {instructions or 'Nenhuma.'}\n"
            f"BASE DO NEGÓCIO:\n{context or '(Ainda sem informações cadastradas)'}"
        )
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role":"system","content":system},{"role":"user","content":message}], "temperature":0.2}
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            # Fail closed: never invent details if the AI provider fails.
            pass
    if not context.strip():
        return UNKNOWN_REPLY
    # Safe fallback: return relevant registered snippets only, without pretending to reason like a model.
    words = {w.lower().strip(".,?!:;") for w in message.split() if len(w) > 3}
    scored = []
    for row in info_rows:
        text = f"{row['title']} {row['content']}".strip()
        hay = text.lower()
        score = sum(1 for w in words if w in hay)
        if score:
            scored.append((score, text))
    if not scored:
        return UNKNOWN_REPLY
    scored.sort(key=lambda item: item[0], reverse=True)
    return "Encontrei esta informação cadastrada:\n" + "\n".join(f"• {item}" for _, item in scored[:3])
