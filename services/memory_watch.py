"""Server holatini kuzatish: xotira va disk tugashidan OLDIN adminga xabar.

Grafikda xotira 100% ga chiqib 40 daqiqa turgan edi — admin buni bot to'xtagandan keyin bildi. Endi:

- har `INTERVAL` soniyada bo'sh xotira (`MemAvailable`) o'qiladi; ketma-ket ikki marta `ALERT_MB` (300 MB) dan
  kam bo'lsa — adminga xabar: nechta MB qoldi, hozir qaysi og'ir ishlar ketyapti, kim eng ko'p yeyapti
  (xabar 30 daqiqada bir martadan ko'p takrorlanmaydi — `admin_alerts`);
- shu yerning o'zida botning bola jarayonlari (brauzer, node, LibreOffice) `oom_score_adj=1000` bilan
  belgilanadi: xotira baribir tugasa, Linux botni emas, ularni o'chiradi;
- diskda `DISK_ALERT_GB` (2 GB) dan kam joy qolsa ham xabar beriladi (disk to'lsa baza yozilmaydi, bot to'xtaydi).
"""
import asyncio
import logging
import os
import shutil

from services import admin_alerts, heavy_gate

log = logging.getLogger(__name__)

ALERT_MB = int(os.getenv("MEMORY_ALERT_MB") or 300)
DISK_ALERT_GB = float(os.getenv("DISK_ALERT_GB") or 2)
INTERVAL = 10.0
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def memory_report(avail: int) -> str:
    """Adminga xabar matni (oddiy matn)."""
    info = heavy_gate.meminfo()
    gate = heavy_gate.snapshot()
    lines = [f"⚠️ Serverda bo'sh xotira kam: {avail} MB (jami {info.get('MemTotal', '?')} MB"
             + (f", swap bo'sh {info.get('SwapFree')} / {info.get('SwapTotal')} MB" if info.get("SwapTotal") else "")
             + ")."]
    if gate["active"]:
        lines.append("Hozir ishlayapti: " + "; ".join(f"{label} ({age} s)" for label, age in gate["active"]))
    if gate["waiting"]:
        lines.append(f"Navbatda kutyapti: {len(gate['waiting'])} ta og'ir ish (mijozlarga ko'rinmaydi).")
    top = heavy_gate.top_processes()
    if top:
        lines.append("Eng ko'p yeydiganlar: " + ", ".join(f"{name} {mb} MB" for name, _pid, mb in top))
    lines.append("Bot og'ir ishlarni navbat bilan bajaryapti. Bu xabar tez-tez kelsa — serverni kattalashtiring "
                 "(4 GB) yoki deploy/README.md dagi sozlamalarni tekshiring.")
    return "\n".join(lines)


def disk_free_gb(path: str = ROOT) -> float:
    try:
        return shutil.disk_usage(path).free / 1e9
    except OSError:
        return float("inf")


def check_once(state: dict) -> None:
    """Bitta tekshiruv (sinash uchun alohida). `state` — ketma-ket past o'qishlar soni."""
    heavy_gate.mark_children()
    avail = heavy_gate.available_mb()
    if avail is not None and avail < ALERT_MB:
        state["low"] = state.get("low", 0) + 1
        if state["low"] >= 2:
            log.warning("Serverda bo'sh xotira kam: %s MB", avail)
            admin_alerts.alert("memory_low", memory_report(avail))
    else:
        state["low"] = 0
    state["tick"] = state.get("tick", 0) + 1
    if state["tick"] % 60 == 1:                       # disk — taxminan har 10 daqiqada
        free = disk_free_gb()
        if free < DISK_ALERT_GB:
            log.warning("Diskda joy kam: %.1f GB", free)
            admin_alerts.alert("disk_low", f"⚠️ Server diskida {free:.1f} GB joy qoldi. Disk to'lsa bot to'xtaydi: "
                                           f"temp/ papkasini va eski fayllarni tozalang yoki diskni kattalashtiring.")


async def run() -> None:
    state: dict = {}
    while True:
        try:
            check_once(state)
        except Exception as exc:                      # noqa: BLE001 — kuzatuv hech qachon botni yiqitmasin
            log.debug("Xotira kuzatuvida xato: %s", exc)
        await asyncio.sleep(INTERVAL)
