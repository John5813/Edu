"""AI so'rovi (JSON javob) — 3D Anatomiyadagi bilan bir xil: o'ylashga cheklangan byudjet, javobga to'liq joy."""
import json
import os

# Reja uchun model: sukut bo'yicha admin paneldagi "premium model" zanjiri. `KAT3D_MODEL` bilan alohida.
MODEL = os.getenv("KAT3D_MODEL") or os.getenv("MED3D_MODEL") or ""
# Qidiruv (kalit so'zlar, modellarni saralash) — tez va arzon bo'lsin; bo'sh — umumiy zanjir.
SEARCH_MODEL = os.getenv("KAT3D_SEARCH_MODEL") or ""
THINK_TOKENS = 1500


def call_json(system: str, user: str, answer_tokens: int, *, language: str = "uz", model: str = "",
              where: str = "3D katalog", temperature: float = 0.4) -> dict:
    from services import ai_usage
    from services.premium_presentation import llm_client, prompts

    payload = {
        "temperature": temperature,
        "max_tokens": answer_tokens + THINK_TOKENS,
        "reasoning": {"max_tokens": THINK_TOKENS, "exclude": True},
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": llm_client._with_today(system)},
                     {"role": "user", "content": user}],
    }
    with prompts.use(language), llm_client.text_model(model), ai_usage.where(where):
        raw = llm_client._request("text", payload)["choices"][0]["message"]["content"]
    cleaned = llm_client._clean_json(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        salvaged = llm_client._salvage_partial_json(cleaned)
        if salvaged:
            return salvaged
        raise


def language_rule(language: str) -> str:
    from services.premium_presentation import llm_client

    return llm_client._language_instruction(language)
