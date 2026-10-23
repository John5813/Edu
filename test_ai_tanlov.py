"""AI model tanlovi: faqat admin tanlagani; Claude sukut va zaxira emas; kesilgan javob qayta so'raladi.

- hujjatlar va premium zaxira zanjirlarida Claude yo'q, sukut Claude emas;
- premium tanlanmagan bo'lsa — hujjatlar uchun admin tanlagan model;
- ishga tushishda admin tanlagan premium model o'rnatiladi (3D anatomiya ham shundan boshlaydi);
- token chegarasida kesilgan javob: o'sha model ikki barobar chegara bilan bir marta qayta so'raladi.

    python test_ai_tanlov.py
"""
import asyncio
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.pop("OPENROUTER_TEXT_MODEL", None)
os.environ.pop("OPENROUTER_TEXT_FALLBACKS", None)
os.environ.pop("MED3D_MODEL", None)

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


import config
import database.database as dbmod

dbmod.DATABASE_FILE = os.path.join(tempfile.mkdtemp(), "test.db")

from database.database import Database, init_db
from services.premium_presentation import config as pconfig
from services.premium_presentation import llm_client


class Resp:
    def __init__(self, content, finish="stop"):
        self.status_code = 200
        self.text = ""
        self._data = {"choices": [{"message": {"content": content}, "finish_reason": finish}],
                      "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


async def main():
    await init_db()

    print("1) Sukut va zaxiralar")
    check("hujjatlar zaxirasida Claude yo'q", not any("anthropic/" in m for m in config.AI_MODEL_FALLBACKS),
          config.AI_MODEL_FALLBACKS)
    check("premium zaxirasida Claude yo'q", not any("anthropic/" in m for m in pconfig.OPENROUTER_TEXT_MODELS),
          pconfig.OPENROUTER_TEXT_MODELS)
    check("sukut model Claude emas", "anthropic/" not in config.AI_MODELS[config.DEFAULT_AI_MODEL]["id"]
          and "anthropic/" not in config.AI_MODELS[config.PREMIUM_DEFAULT_AI_MODEL]["id"])
    from services.med3d import auto
    check("3D anatomiya o'z modelini majburlamaydi (admin tanlovi)", auto.MODEL == "" and auto.MODEL_ACADEMIC == "")

    print("\n2) Admin tanlovi")
    check("hech narsa tanlanmagan — sukut", await Database.get_premium_ai_model() == config.DEFAULT_AI_MODEL)
    await Database.set_current_ai_model("gemini_25_pro")
    check("premium tanlanmagan — hujjatlar uchun tanlangani", await Database.get_premium_ai_model() == "gemini_25_pro")
    await Database.set_premium_ai_model("gpt_4o_mini")
    check("premium tanlangan — o'shanisi", await Database.get_premium_ai_model() == "gpt_4o_mini")
    import main as mainmod
    await mainmod._load_premium_ai_model()
    check("ishga tushishda premium model o'rnatiladi", llm_client._models("text")[0] == "openai/gpt-4o-mini",
          llm_client._models("text"))

    print("\n3) Kesilgan javob")
    pconfig.OPENROUTER_API_KEY = "k"
    pconfig.PREMIUM_REASONING = ""          # bu bo'limda faqat qayta so'rash mantiqi tekshiriladi
    calls = []
    replies = [Resp("", "length"), Resp("tayyor")]
    bodies = []

    def post(url, headers=None, json=None, timeout=None):
        calls.append((json["model"], json.get("max_tokens")))
        bodies.append(json)
        return replies.pop(0)

    llm_client.requests.post = post
    payload = {"messages": [], "max_tokens": 4300}
    data = llm_client._request("text", payload, 30)
    check("o'sha model 2 barobar chegara bilan qayta so'raldi, boshqasiga o'tilmadi",
          calls == [("openai/gpt-4o-mini", 4300), ("openai/gpt-4o-mini", 8600)]
          and llm_client._content(data) == "tayyor", calls)

    check("bo'sh kesilgan javob: qayta so'rovda fikrlash kamaytiriladi (effort=low)",
          "reasoning" not in bodies[0] and bodies[1].get("reasoning") == {"effort": "low", "exclude": True}, bodies)

    calls.clear()
    bodies.clear()
    replies[:] = [Resp("yarim matn", "length"), Resp("to'liq matn")]
    payload = {"messages": [], "max_tokens": 4300}
    data = llm_client._request("text", payload, 30, accept=lambda text: text.startswith("to'liq"))
    check("matnli kesilgan javob: fikrlashga tegilmaydi, faqat chegara oshadi",
          "reasoning" not in bodies[1] and calls[1][1] == 8600 and llm_client._content(data) == "to'liq matn", bodies)

    calls.clear()
    bodies.clear()
    replies[:] = [Resp("", "length"), Resp("", "length"), Resp("zaxira")]
    data = llm_client._request("text", payload, 30)
    check("ikkinchi marta ham kesilsa — keyingi modelga (qayta so'rash bir marta)",
          len(calls) == 3 and calls[1][0] == calls[0][0] and calls[2][0] != calls[0][0]
          and llm_client._content(data) == "zaxira", calls)
    check("zaxira modelga fikrlash sozlamasi o'tmaydi", "reasoning" not in bodies[2], bodies[2])


    print("\n4) O'ylash ulushi (PREMIUM_REASONING)")
    import importlib
    check("sukut: 18%", importlib.reload(pconfig).PREMIUM_REASONING == "18%", pconfig.PREMIUM_REASONING)
    pconfig.PREMIUM_REASONING = "18%"
    body = llm_client._body({"max_tokens": 1000}, "deepseek/deepseek-v4.1-flash", "text")
    check("18%: o'ylash 180 token, javob chegarasi 1000 saqlanadi (jami 1180)",
          body["reasoning"] == {"max_tokens": 180, "exclude": True} and body["max_tokens"] == 1180, body)
    body = llm_client._body({"max_tokens": 1000}, "anthropic/claude-haiku-5.5", "text")
    check("Claude: o'ylash kamida 1024", body["reasoning"]["max_tokens"] == 1024 and body["max_tokens"] == 2024, body)
    body = llm_client._body({"max_tokens": 1000}, "google/gemini-2.5-flash", "vision")
    check("matn bo'lmagan so'rovga (rasm, chek) tegilmaydi", body["reasoning"]["max_tokens"] == 1024, body)
    pconfig.PREMIUM_REASONING = "none"
    body = llm_client._body({"max_tokens": 1000}, "deepseek/deepseek-v4.1-flash", "text")
    check("none: o'ylash o'chiriladi", body["reasoning"] == {"effort": "none", "exclude": True}
          and body["max_tokens"] == 1000, body)
    body = llm_client._body({"max_tokens": 1000, "reasoning": {"effort": "low", "exclude": True}},
                            "deepseek/deepseek-v4.1-flash", "text")
    check("bo'sh javobdan keyingi qayta so'rov sozlamasi ustun", body["reasoning"]["effort"] == "low", body)
    pconfig.PREMIUM_REASONING = ""
    body = llm_client._body({"max_tokens": 1000}, "deepseek/deepseek-v4.1-flash", "text")
    check("bo'sh sozlama: modelning o'z sukuti", "reasoning" not in body and body["max_tokens"] == 1000, body)


asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
