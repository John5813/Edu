"""Together image requests are bounded and honor rate-limit retry headers."""
import asyncio
import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:test")

from services import together_service

FAILS = []


def check(name, condition, detail=""):
    print(("  ok   " if condition else "  XATO ") + name +
          ("" if condition else f" — {detail}"))
    if not condition:
        FAILS.append(name)


print("1) SDK retries are disabled; service retries use rate-limit headers")
with patch.dict(os.environ, {"TOGETHER_API_KEY": "test-key"}), \
        patch.object(together_service, "Together") as sdk, \
        patch.object(together_service, "AsyncOpenAI"):
    service = together_service.TogetherImageService()
check("SDK retries disabled", sdk.call_args.kwargs.get("max_retries") == 0, sdk.call_args)
check("default global image concurrency is two", service.image_semaphore._value == 2)

error = SimpleNamespace(response=SimpleNamespace(headers={
    "Retry-After": "4",
    "X-RateLimit-Reset": "8",
}))
with patch.object(together_service.random, "uniform", return_value=0.5):
    check("longest rate-limit reset plus jitter is used",
          together_service._retry_delay(error, 0) == 8.5)


print("2) Concurrent image requests stay within the shared limit")
active = 0
peak = 0
lock = threading.Lock()


def generate(**kwargs):
    global active, peak
    with lock:
        active += 1
        peak = max(peak, active)
    time.sleep(0.03)
    with lock:
        active -= 1
    return object()


service.client = SimpleNamespace(images=SimpleNamespace(generate=generate))


async def run_concurrent():
    await asyncio.gather(*(service._call_model("prompt", "model") for _ in range(6)))


asyncio.run(run_concurrent())
check("no more than two image API requests run at once", peak == 2, peak)


print("3) A 429 retry waits according to Retry-After")


class RateLimited(Exception):
    status_code = 429
    response = SimpleNamespace(headers={"Retry-After": "4"})


calls = 0
waits = []


def generate_once_limited(**kwargs):
    global calls
    calls += 1
    if calls == 1:
        raise RateLimited("429 Too Many Requests")
    return object()


async def record_sleep(seconds):
    waits.append(seconds)


service.client = SimpleNamespace(images=SimpleNamespace(generate=generate_once_limited))
with patch.object(together_service.asyncio, "sleep", record_sleep), \
        patch.object(together_service.random, "uniform", return_value=0.5):
    result = asyncio.run(service._call_model("prompt", "model"))
check("request succeeds after one retry", result is not None and calls == 2, (result, calls))
# Kutish umumiy muddatdan (cooldown) hisoblanadi — bir necha mikrosoniya kamroq bo'lishi mumkin.
check("retry waits the server-provided interval", len(waits) == 1 and 4.45 <= waits[0] <= 4.5, waits)


print("4) A 429 pauses ALL parallel requests (shared cooldown)")
service._cooldown_until = 0.0
sent = []


def generate_first_limited(**kwargs):
    sent.append(time.monotonic())
    if len(sent) == 1:
        raise RateLimited("429 Too Many Requests")
    return object()


async def parallel():
    service.client = SimpleNamespace(images=SimpleNamespace(generate=generate_first_limited))
    first = asyncio.create_task(service._call_model("a", "model"))
    await asyncio.sleep(0.01)
    second = asyncio.create_task(service._call_model("b", "model"))
    return await asyncio.gather(first, second)


RateLimited.response = SimpleNamespace(headers={"Retry-After": "0.3"})
with patch.object(together_service, "_retry_delay", return_value=0.3):
    results = asyncio.run(parallel())
check("both succeed", all(r is not None for r in results), results)
check("parallel request waited for the cooldown instead of hitting 429 again",
      len(sent) == 3 and sent[1] - sent[0] >= 0.25, [round(t - sent[0], 3) for t in sent])


print("5) 429 gets more attempts than other transient errors")
service._cooldown_until = 0.0
tries = []


def always_limited(**kwargs):
    tries.append(1)
    raise RateLimited("429 Too Many Requests")


service.client = SimpleNamespace(images=SimpleNamespace(generate=always_limited))
with patch.object(together_service, "_retry_delay", return_value=0.0):
    result = asyncio.run(service._call_model("p", "model"))
check(f"429: {together_service._RATE_LIMIT_ATTEMPTS} attempts, then gives up",
      result is None and len(tries) == together_service._RATE_LIMIT_ATTEMPTS, len(tries))


print("6) Bitta modelga 402 — butun hisob tugagan emas: zaxira model chizadi, xabar tinch, model chetlab o'tiladi")
from services import admin_alerts

CREDIT_402 = ("Error code: 402 - {'error': {'message': 'A positive credit balance is required to use this model. "
              "Please navigate to https://api.together.ai/settings/billing to add additional credits.', "
              "'type': 'credit_limit'}}")
sent = []
admin_alerts._bot = object()
admin_alerts._sent.clear()
admin_alerts.alert = lambda key, text, cooldown=admin_alerts.COOLDOWN: sent.append((key, text, cooldown))
together_service._unavailable.clear()
calls = []


def generate_402_first(**kwargs):
    calls.append(kwargs["model"])
    if kwargs["model"] == "RunDiffusion/Juggernaut-pro-flux":
        raise Exception(CREDIT_402)
    return SimpleNamespace(data=[SimpleNamespace(url=None, b64_json="aGVsbG8=")])


service.client = SimpleNamespace(images=SimpleNamespace(generate=generate_402_first))
models = ["RunDiffusion/Juggernaut-pro-flux", "black-forest-labs/FLUX.2-pro"]


async def two_images():
    return [await service.generate_with_models("a mosque", models, stem="t_402") for _ in range(2)]


paths = asyncio.run(two_images())
check("ikkala rasm zaxira model bilan chizildi", all(paths), paths)
check("402 bergan model ikkinchi rasmda qayta sinalmadi", calls.count("RunDiffusion/Juggernaut-pro-flux") == 1, calls)
check("«limit tugadi» deb shoshilinch xabar YO'Q", not [k for k, _, _ in sent if k == "together_credits"], sent)
info = [x for x in sent if x[0] == "together_model_402"]
check("tinch ma'lumot xabari bor, 6 soatda bir marta", len(info) >= 1 and all(c == 6 * 3600.0 for _, _, c in info)
      and "ish to'xtamagan" in info[0][1] and "Juggernaut" in info[0][1], info)
for path in paths:
    try:
        os.remove(path)
    except OSError:
        pass

sent.clear()
together_service._unavailable.clear()


def generate_all_402(**kwargs):
    raise Exception(CREDIT_402)


service.client = SimpleNamespace(images=SimpleNamespace(generate=generate_all_402))
none = asyncio.run(service.generate_with_models("a mosque", models, stem="t_402"))
check("hamma model 402 bersa — rasm yo'q va shoshilinch xabar bor", none is None
      and [k for k, _, _ in sent] == ["together_credits"], sent)

print("6) Javob bermagan model qayta-qayta kutilmaydi (taqdimot «aylanib qolmasin»)")
together_service._unavailable.clear()
calls = []


def slow_then_ok(**kwargs):
    calls.append(kwargs["model"])
    if kwargs["model"] == "slow/model":
        time.sleep(0.5)
    return SimpleNamespace(data=[SimpleNamespace(url=None, b64_json="aGk=")])


service.client = SimpleNamespace(images=SimpleNamespace(generate=slow_then_ok))
with patch.object(together_service, "IMAGE_TIMEOUT", 0.1), patch.object(together_service, "_count_image"):
    path = asyncio.run(service.generate_with_models("a bridge", ["slow/model", "fast/model"], stem="t_slow"))
check("vaqt tugagan modelga qayta urinilmaydi — darhol keyingisi", calls == ["slow/model", "fast/model"] and path, calls)
calls.clear()
with patch.object(together_service, "IMAGE_TIMEOUT", 0.1), patch.object(together_service, "_count_image"):
    asyncio.run(service.generate_with_models("a river", ["slow/model", "fast/model"], stem="t_slow2"))
check("sekin model keyingi rasmlarda bir necha daqiqa chetlab o'tiladi", calls == ["fast/model"], calls)

together_service._unavailable.clear()
calls.clear()


def always_slow(**kwargs):
    calls.append(kwargs["model"])
    time.sleep(0.3)
    return object()


service.client = SimpleNamespace(images=SimpleNamespace(generate=always_slow))
with patch.object(together_service, "IMAGE_TIMEOUT", 0.2), patch.object(together_service, "IMAGE_BUDGET", 0.3):
    t0 = time.monotonic()
    none = asyncio.run(service.generate_with_models("x", ["a/1", "b/2", "c/3", "d/4"], stem="t_budget"))
    spent = time.monotonic() - t0
check("bitta rasmga ajratilgan vaqt tugasa — qolgan modellar sinalmaydi, rasmsiz davom etiladi",
      none is None and len(calls) == 2 and spent < 0.7, (calls, spent))

import config
check("Together'da yopilgan FLUX.1-schnell zaxira ro'yxatida yo'q",
      not any("schnell" in m.lower() for m in config.IMAGE_MODEL_FALLBACKS), config.IMAGE_MODEL_FALLBACKS)

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
