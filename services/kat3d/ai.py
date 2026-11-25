"""AI so'rovi (JSON javob) — 3D Anatomiyadagi bilan bir xil: o'ylashga cheklangan byudjet, javobga to'liq joy."""
import json
import os

# Matnni admin panelda tanlangan premium model yozadi (bo'sh — o'sha zanjir). `KAT3D_MODEL` faqat majburan
# boshqa model kerak bo'lsa; 3D Anatomiyaning `MED3D_MODEL` iga bog'liq emas.
MODEL = os.getenv("KAT3D_MODEL") or ""
# Qidiruv (kalit so'zlar, modellarni saralash) — tez va arzon bo'lsin; bo'sh — umumiy zanjir.
SEARCH_MODEL = os.getenv("KAT3D_SEARCH_MODEL") or ""
# Modellarni saralash va mavzuning necha foizini 3D bilan ko'rsatish mumkinligini baholash (qamrov) — admin
# tanlagan (arzon bo'lishi mumkin) modelga emas, nisbatan kuchli modelga mahkamlangan: shu baho mijozdan pul
# olinadimi-yo'qmi hal qiladi. 28 mavzuli quruq sinovda (tools/katalog3d/tekshiruv_sinov.py) GPT-4.1 25/28 to'g'ri
# qaror berdi (~6-10 s). Claude Sonnet 5 ham sinaldi: qamrovni haddan tashqari qattiq baholadi (Misr piramidalari
# 35%, vulqonlar 15%), to'g'ri qarorlar 18-19/28 ga tushdi, tekshiruv 15-27 s gacha cho'zildi. Ishlamasa —
# umumiy zanjir. `KAT3D_SELECT_MODEL` bilan almashtirish mumkin.
SELECT_MODEL = os.getenv("KAT3D_SELECT_MODEL") or "openai/gpt-4.1"
THINK_TOKENS = 1500


def call_json(system: str, user: str, answer_tokens: int, *, language: str = "uz", model: str = "",
              where: str = "3D katalog", temperature: float = 0.4) -> dict:
    from services import ai_usage
    from services.premium_presentation import llm_client, prompts

    from services.premium_presentation import config as premium_config

    # Admin panelda o'ylash o'chirilgan bo'lsa (arzon model, masalan DeepSeek Flash) — bu yerda ham o'ylamaydi.
    think = (premium_config.PREMIUM_REASONING or "").strip().lower() != "none"
    payload = {
        "temperature": temperature,
        "max_tokens": answer_tokens + (THINK_TOKENS if think else 0),
        "reasoning": {"max_tokens": THINK_TOKENS, "exclude": True} if think else {"effort": "none", "exclude": True},
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
        joined = llm_client._joined_objects(cleaned)
        if joined:
            return joined
        salvaged = llm_client._salvage_partial_json(cleaned)
        if salvaged:
            return salvaged
        raise


def language_rule(language: str) -> str:
    from services.premium_presentation import llm_client

    return llm_client._language_instruction(language)
