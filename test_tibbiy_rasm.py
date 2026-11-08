"""Tibbiy rasm: admin tanlagan arzon modeldan BIR POG'ONA yuqori o'rta model; FLUX.2 Pro va undan qimmatiga o'tilmaydi.

    python test_tibbiy_rasm.py
"""
import asyncio, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("TOGETHER_API_KEY", "test")
os.environ.pop("MEDICAL_IMAGE_MODEL", None)

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import config
from services import together_service as ts

JUG, QWEN = "RunDiffusion/Juggernaut-pro-flux", "Qwen/Qwen-Image"
F2DEV, F2PRO, F11PRO, SCHNELL = ("black-forest-labs/FLUX.2-dev", "black-forest-labs/FLUX.2-pro",
                                 "black-forest-labs/FLUX.1.1-pro", "black-forest-labs/FLUX.1-schnell")
EXPENSIVE = {m for m in (info["id"] for info in config.IMAGE_MODELS.values())
             if (ts.image_price(m) or 0) >= ts.image_price(F2PRO)}

print("1) Zanjir")
check("narx yozuvdan o'qiladi", ts.image_price(F2PRO) == 0.03 and ts.image_price(JUG) == 0.005 and ts.image_price("x") is None)
chain = ts.medical_chain([JUG, *config.IMAGE_MODEL_FALLBACKS])
check("Juggernaut → bir pog'ona yuqori FLUX.2 Dev, keyin admin modeli", chain[:2] == [F2DEV, JUG], chain)
check("tibbiy zanjirda FLUX.2 Pro va undan qimmati yo'q", not EXPENSIVE & set(chain), chain)
check("o'rta model FLUX.2 Pro'dan arzon", ts.image_price(chain[0]) < ts.image_price(F2PRO))
check("Qwen ham → FLUX.2 Dev", ts.medical_chain([QWEN, F2PRO, SCHNELL])[0] == F2DEV)
check("admin modeli ishlamay oxiriga surilgan bo'lsa ham (zanjir boshi FLUX.2 Pro)",
      ts.medical_chain([F2PRO, F11PRO, SCHNELL, JUG], JUG)[:2] == [F2DEV, JUG])
check("admin kuchli modelni o'zi tanlagan — o'zgarmaydi", ts.medical_chain([F2PRO, F11PRO, SCHNELL]) == [F2PRO, F11PRO, SCHNELL])
check("admin o'rta modelni tanlagan — o'zgarmaydi", ts.medical_chain([F2DEV, F2PRO]) == [F2DEV, F2PRO])
os.environ["MEDICAL_IMAGE_MODEL"] = "google/imagen-4.0-fast"
config.MEDICAL_IMAGE_MODEL = os.environ["MEDICAL_IMAGE_MODEL"]
check("MEDICAL_IMAGE_MODEL — aniq model", ts.medical_chain([JUG, F2PRO])[0] == "google/imagen-4.0-fast")
config.MEDICAL_IMAGE_MODEL = ""
os.environ.pop("MEDICAL_IMAGE_MODEL")

print("2) Rasm chizish (_render)")
calls = []

async def fake_chain(target):
    return [JUG, *config.IMAGE_MODEL_FALLBACKS]

async def fake_chosen(target):
    return JUG

async def run(prompt, topic, fail=()):
    calls.clear()
    service = ts.TogetherImageService()

    async def call_model(p, model):
        calls.append(model)
        return None if model in fail else {"ok": model}

    async def save(response, stem):
        return "/tmp/rasm.png"

    service._call_model, service._save_response = call_model, save
    return await service._render(prompt, "presentation", "t", topic=topic)

ts.image_model_chain, ts.chosen_image_model = fake_chain, fake_chosen
asyncio.run(run("A doctor talks with a patient in a hospital room", "Tibbiyot"))
check("tibbiy rasm — avval FLUX.2 Dev", calls == [F2DEV], calls)
asyncio.run(run("A doctor examines a patient", "Kardiologiya", fail={F2DEV, JUG, SCHNELL}))
check("hamma o'rta va arzon model ishlamasa ham FLUX.2 Pro'ga o'tilmaydi", not EXPENSIVE & set(calls)
      and calls[:2] == [F2DEV, JUG], calls)
asyncio.run(run("Mountain landscape at sunrise", "Geografiya"))
check("tibbiy bo'lmagan mavzu — admin modeli (o'zgarmagan)", calls == [JUG], calls)

print("3) 3D taqdimotlar o'z modellarida qoladi")
import services.kat3d as kat3d
check("aralash 3D rasmlari — avvalgidek", kat3d.AI_IMAGE_MODELS[0] == F2PRO, kat3d.AI_IMAGE_MODELS)
import inspect
from services.med3d import auto as med3d_auto
check("3D Anatomiya tibbiy zanjirga o'tkazilmaydi", "medical_chain" not in inspect.getsource(med3d_auto))

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta XATO")
sys.exit(1 if FAILS else 0)
