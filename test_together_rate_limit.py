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

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
