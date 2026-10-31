"""Og'ir ishlar darvozasi — server xotirasi to'lib, bot qotib qolmasligi uchun.

2 GB li serverda xotira 100% ga chiqib, bot 40 daqiqa qotib turgan edi. Sabab bitta emas: xotira ko'p
yeydigan ishlar (brauzer — Chromium, LibreOffice, 3D model o'girish — node, ONNX, PDF→Word) har biri o'zi
xohlagan paytda boshlanardi; bir vaqtda 3-4 mijoz buyurtma bersa, ular birga xotirani to'ldirardi.

Endi har shunday ish shu yerdan ruxsat oladi (pikni kutib turmaymiz — unga yo'l qo'ymaymiz):

- bir vaqtda ko'pi bilan `parallel()` ta: 2 GB serverda 1, 4 GB da 2, kattasida 3 (`HEAVY_PARALLEL`);
- boshlashdan oldin bo'sh xotira (`MemAvailable`) tekshiriladi: ishning ehtiyoji + `RESERVE_MB` (250) bo'lishi
  shart, yaqinda boshlangan ishlarning hali yemagan xotirasi ham hisobga olinadi;
- yetmasa ish boshlanmaydi — navbatda kutadi. Ortiqcha yuk qotishga emas, kechikishga aylanadi; mijoz navbatni
  ko'rmaydi (kutish xabarlari va qiziqarli ma'lumotlar almashib turadi);
- navbat ustuvorlik bo'yicha: mijoz kutayotgan ish (`ODDIY`) fon ishidan (`FON` — do'kon ko'rgazmasi, 3D
  katalogni oldindan yuklash) oldin o'tadi, bir xil ustuvorlikda — kelish tartibida;
- ichma-ich so'rov (bosqich ruxsat olgan, uning ichidagi render ham so'raydi) qayta kutmaydi — ruxsat
  `contextvars` orqali oqimga ham o'tadi (`asyncio.to_thread`, `context.run`);
- buyurtma abadiy osilib qolmasin: hech narsa ishlamayotgan bo'lsa-yu xotira baribir yetmasa (masalan bot o'zi
  katta), `GRACE` soniyadan keyin ish boshlanadi; ruxsat olib `STALE` dan ko'p turgan ish (osilib qolgan)
  sanalmaydi.

Kernel bilan ham kelishilgan: brauzer, node, LibreOffice jarayonlari `oom_score_adj=1000` bilan belgilanadi
(`mark_children`) — xotira baribir tugasa, Linux (yoki earlyoom) botni emas, avval ularni o'chiradi.
"""
import asyncio
import contextlib
import contextvars
import functools
import heapq
import itertools
import logging
import os
import threading
import time
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Ustuvorlik: kichigi oldin.
TEZ, ODDIY, FON = 0, 1, 2


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except ValueError:
        return default


# Har ish turining taxminiy eng katta xotirasi (MB) — o'lchovlar bo'yicha, `HEAVY_*_MB` bilan o'zgaradi.
BROWSER_MB = _env_int("HEAVY_BROWSER_MB", 450)     # Chromium + Playwright drayveri, 1920×1080 sahifa
OFFICE_MB = _env_int("HEAVY_OFFICE_MB", 350)       # LibreOffice (PPTX/DOCX → PDF)
ONNX_MB = _env_int("HEAVY_ONNX_MB", 500)           # ISNet (fonni olib tashlash)
PDF_MB = _env_int("HEAVY_PDF_MB", 400)             # pdf2docx
DECK3D_MB = _env_int("HEAVY_DECK3D_MB", 400)       # 3D taqdimotni yig'ish (GLB modellar, soddalashtirish)
RESERVE_MB = _env_int("HEAVY_RESERVE_MB", 250)     # bot va tizim uchun doim bo'sh qoladigan xotira
GRACE = float(_env_int("HEAVY_GRACE_SEC", 45))
STALE = float(_env_int("HEAVY_STALE_SEC", 20 * 60))
RAMP = 20.0                                        # yangi boshlangan ish shu vaqt ichida xotirasini to'liq yeydi
POLL = 0.5

# Kernel xotira tugaganda birinchi o'chiradigan jarayonlar (nomi /proc/<pid>/comm, 15 belgigacha).
VICTIMS = ("chrome", "headless", "node", "soffice", "ffmpeg", "oosplash")


# ───────────────────────────────────────────── xotira

def meminfo() -> Dict[str, int]:
    """/proc/meminfo (MB). Linux bo'lmasa — bo'sh."""
    out: Dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                key, value = line.split(":", 1)
                out[key] = int(value.split()[0]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return out


def available_mb() -> Optional[int]:
    return meminfo().get("MemAvailable")


def parallel() -> int:
    """Bir vaqtda nechta og'ir ish: `HEAVY_PARALLEL` yoki server xotirasiga qarab."""
    env = os.getenv("HEAVY_PARALLEL")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    total = meminfo().get("MemTotal", 0)
    if not total:
        return 2
    return 1 if total < 3000 else 2 if total < 6000 else 3


# ───────────────────────────────────────────── navbat

_cond = threading.Condition(threading.Lock())
_seq = itertools.count(1)
_active: Dict[int, dict] = {}            # ruxsat olganlar: chipta → {label, need, since}
_queue: List[Tuple[int, int]] = []       # kutayotganlar (heap): (ustuvorlik, chipta)
_waiting: Dict[int, dict] = {}           # chipta → {label, need, since, priority}
_held: contextvars.ContextVar = contextvars.ContextVar("heavy_gate_held", default=None)
_priority: contextvars.ContextVar = contextvars.ContextVar("heavy_gate_priority", default=ODDIY)
stats = {"admitted": 0, "waited": 0, "longest_wait": 0.0, "forced": 0}


def _live(now: float) -> List[dict]:
    return [a for a in _active.values() if now - a["since"] < STALE]


def _admit(ticket: int) -> bool:
    """Navbat boshidagi chiptani o'tkazish mumkinmi (qulf ostida chaqiriladi)."""
    if not _queue or _queue[0][1] != ticket:
        return False
    info = _waiting[ticket]
    now = time.time()
    live = _live(now)
    if len(live) >= parallel():
        return False
    forced = False
    avail = available_mb()
    if avail is not None:
        # Yaqinda boshlangan ish hali xotirasini to'liq yemagan — uni ham band deb hisoblaymiz.
        ramping = sum(a["need"] for a in live if now - a["since"] < RAMP)
        if avail - ramping < info["need"] + RESERVE_MB:
            if live or now - info["since"] < GRACE:
                return False
            forced = True                       # hech narsa ishlamayapti — kutishdan foyda yo'q
    heapq.heappop(_queue)
    _waiting.pop(ticket, None)
    _active[ticket] = {"label": info["label"], "need": info["need"], "since": now}
    waited = now - info["since"]
    stats["admitted"] += 1
    if waited >= 1.0:
        stats["waited"] += 1
        stats["longest_wait"] = max(stats["longest_wait"], waited)
    if forced:
        stats["forced"] += 1
        log.warning("Og'ir ish: xotira kam (%s MB), lekin boshqa ish yo'q — boshlanadi: %s", avail, info["label"])
    elif waited >= 5.0:
        log.info("Og'ir ish %.0f s navbatda kutdi: %s", waited, info["label"])
    return True


def _enqueue(label: str, need_mb: int, priority: Optional[int]) -> int:
    prio = _priority.get() if priority is None else priority
    with _cond:
        ticket = next(_seq)
        _waiting[ticket] = {"label": label, "need": int(need_mb or 0), "since": time.time(), "priority": prio}
        heapq.heappush(_queue, (prio, ticket))
    return ticket


def _drop(ticket: int) -> None:
    """Kutish bekor bo'ldi (xato yoki vazifa bekor qilindi)."""
    with _cond:
        if ticket in _waiting:
            _waiting.pop(ticket, None)
            _queue[:] = [item for item in _queue if item[1] != ticket]
            heapq.heapify(_queue)
        _cond.notify_all()


def _release(ticket: int) -> None:
    with _cond:
        _active.pop(ticket, None)
        _cond.notify_all()


def held() -> bool:
    """Joriy ish allaqachon ruxsat olganmi."""
    return _held.get() is not None


@contextlib.contextmanager
def slot(label: str, need_mb: int, priority: Optional[int] = None):
    """Sinxron (oqimdagi) ish uchun ruxsat: xotira va navbat yetguncha kutadi."""
    if _held.get() is not None:
        yield
        return
    ticket = _enqueue(label, need_mb, priority)
    try:
        with _cond:
            while not _admit(ticket):
                _cond.wait(POLL)
    except BaseException:
        _drop(ticket)
        raise
    token = _held.set(ticket)
    try:
        yield
    finally:
        _held.reset(token)
        _release(ticket)


@contextlib.asynccontextmanager
async def aslot(label: str, need_mb: int, priority: Optional[int] = None):
    """Asinxron kod uchun ruxsat: kutish hodisalar siklini to'xtatmaydi. Ruxsat ichidagi
    `asyncio.to_thread` / `context.run` oqimlariga ham o'tadi — u yerdagi `slot` qayta kutmaydi."""
    if _held.get() is not None:
        yield
        return
    ticket = _enqueue(label, need_mb, priority)
    try:
        while True:
            with _cond:
                if _admit(ticket):
                    break
            await asyncio.sleep(POLL)
    except BaseException:
        _drop(ticket)
        raise
    token = _held.set(ticket)
    try:
        yield
    finally:
        _held.reset(token)
        _release(ticket)


def guard(label: str, need_mb: int, priority: Optional[int] = None):
    """Sinxron funksiyani `slot` bilan o'raydigan dekorator."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with slot(label, need_mb, priority):
                return fn(*args, **kwargs)
        return wrapper
    return deco


@contextlib.contextmanager
def fon():
    """Ichidagi og'ir ishlar fon ustuvorligida (mijoz ishlaridan keyin) navbatga turadi."""
    token = _priority.set(FON)
    try:
        yield
    finally:
        _priority.reset(token)


def snapshot() -> dict:
    """Admin uchun: hozir nima ishlayapti, nechta kutyapti."""
    now = time.time()
    with _cond:
        active = [(a["label"], int(now - a["since"])) for a in _active.values()]
        waiting = [(w["label"], int(now - w["since"])) for _p, t in sorted(_queue) for w in [_waiting[t]]]
    return {"parallel": parallel(), "active": active, "waiting": waiting, **stats}


# ───────────────────────────────────────────── kernel: kim birinchi o'chiriladi

def set_oom_score(pid: int, value: int = 1000) -> bool:
    """Jarayonni xotira tugaganda birinchi o'chiriladigan qiladi (qiymatni oshirish uchun ruxsat kerak emas)."""
    path = f"/proc/{pid}/oom_score_adj"
    try:
        with open(path, encoding="ascii") as fh:
            if int(fh.read().strip() or 0) >= value:
                return False
        with open(path, "w", encoding="ascii") as fh:
            fh.write(str(value))
        return True
    except (OSError, ValueError):
        return False


def _process_tree() -> Dict[int, List[Tuple[int, str]]]:
    children: Dict[int, List[Tuple[int, str]]] = {}
    try:
        names = os.listdir("/proc")
    except OSError:
        return children
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", encoding="utf-8", errors="replace") as fh:
                data = fh.read()
            close = data.rfind(")")
            comm = data[data.find("(") + 1:close]
            ppid = int(data[close + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        children.setdefault(ppid, []).append((int(name), comm))
    return children


def mark_children(root: Optional[int] = None) -> int:
    """Botning avlod jarayonlaridan brauzer/node/LibreOffice'ni `oom_score_adj=1000` qiladi.
    Nechta yangi belgilanganini qaytaradi."""
    tree = _process_tree()
    stack, seen, marked = [root or os.getpid()], set(), 0
    while stack:
        for child, comm in tree.get(stack.pop(), []):
            if child in seen:
                continue
            seen.add(child)
            stack.append(child)
            if any(v in comm.lower() for v in VICTIMS) and set_oom_score(child):
                marked += 1
    return marked


def top_processes(limit: int = 6) -> List[Tuple[str, int, int]]:
    """Eng ko'p xotira yeydigan jarayonlar: [(nomi, pid, MB)]."""
    rows = []
    try:
        names = os.listdir("/proc")
    except OSError:
        return rows
    for name in names:
        if not name.isdigit():
            continue
        try:
            comm, rss = "", 0
            with open(f"/proc/{name}/status", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.startswith("Name:"):
                        comm = line.split(None, 1)[1].strip()
                    elif line.startswith("VmRSS:"):
                        rss = int(line.split()[1]) // 1024
                        break
        except (OSError, ValueError, IndexError):
            continue
        if rss:
            rows.append((comm, int(name), rss))
    rows.sort(key=lambda r: -r[2])
    return rows[:limit]
