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
    calls = []
    replies = [Resp("", "length"), Resp("tayyor")]

    def post(url, headers=None, json=None, timeout=None):
        calls.append((json["model"], json.get("max_tokens")))
        return replies.pop(0)

    llm_client.requests.post = post
    payload = {"messages": [], "max_tokens": 4300}
    data = llm_client._request("text", payload, 30)
    check("o'sha model 2 barobar chegara bilan qayta so'raldi, boshqasiga o'tilmadi",
          calls == [("openai/gpt-4o-mini", 4300), ("openai/gpt-4o-mini", 8600)]
          and llm_client._content(data) == "tayyor", calls)

    calls.clear()
    replies[:] = [Resp("", "length"), Resp("", "length"), Resp("zaxira")]
    data = llm_client._request("text", payload, 30)
    check("ikkinchi marta ham kesilsa — keyingi modelga (qayta so'rash bir marta)",
          len(calls) == 3 and calls[1][0] == calls[0][0] and calls[2][0] != calls[0][0]
          and llm_client._content(data) == "zaxira", calls)


asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
