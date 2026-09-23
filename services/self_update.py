"""Botni GitHub'dan yangilash — admin paneldagi tugma uchun.

Har safar serverga SSH bilan kirib `git pull` qilish shart emas: admin
panelda tugma bosiladi, bot o'zini yangilaydi va qayta ishga tushadi.

Bu modul faqat mantiqni bajaradi, Telegram bilan ishlamaydi. Shu sababli
uni alohida sinash mumkin.

Xavfsizlik qoidalari — har biri haqiqiy xatodan kelib chiqqan:

  • **Chiqishdan maxfiy ma'lumot olib tashlanadi.** `git` ning xabarlarida
    remote manzili uchraydi, manzil ichida esa token bo'lishi mumkin. Shu
    sababli har qanday chiqish `_redact` dan o'tadi.
  • **Faqat `--ff-only`.** Serverda mahalliy commit bo'lsa, majburiy
    birlashtirish uning ishini yo'q qilardi. Bunday holda yangilash
    to'xtaydi va sabab aytiladi.
  • **O'zgargan fayllar bo'lsa to'xtaydi.** Serverda qo'lda tuzatilgan
    narsa bo'lsa, uni jimgina bosib ketmaymiz.
  • **Har buyruqda vaqt chegarasi.** Tarmoq osilib qolsa bot qotib
    qolmasin.

Qayta ishga tushirish `os.execv` bilan bajariladi: jarayon o'sha PID va
o'sha `screen` oynasida yangi kod bilan almashadi. Shuning uchun systemd
yoki boshqa nazoratchi shart emas.
"""

import hashlib
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Buyruqlar uchun vaqt chegaralari (soniya).
_GIT_TIMEOUT = 120
_PIP_TIMEOUT = 600

# Manzil ichidagi login/parol yoki token. `https://user:token@github.com/...`
_CREDENTIALS = re.compile(r"(https?://)[^/\s:@]+(?::[^/\s@]+)?@")
# Alohida uchragan tokenlar.
_TOKENS = re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")


def _redact(text: str) -> str:
    """Chiqishdan token va parollarni olib tashlaydi.

    `git` xabarlarida remote manzili uchraydi. Agar manzilda token bo'lsa,
    u admin chatiga tushib qolardi va chat tarixida qolib ketardi.
    """
    text = _CREDENTIALS.sub(r"\1***@", text or "")
    return _TOKENS.sub("***", text)


def repo_root() -> Path:
    """Ishlab turgan kodning papkasi."""
    return Path(__file__).resolve().parents[1]


def _run(args: list, timeout: int = _GIT_TIMEOUT) -> tuple:
    """Buyruqni bajaradi va (muvaffaqiyat, tozalangan chiqish) qaytaradi."""
    try:
        result = subprocess.run(
            args, cwd=str(repo_root()), capture_output=True, text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"⏱ Buyruq {timeout} soniyada tugamadi: {args[0]}"
    except OSError as e:
        return False, f"Buyruq ishga tushmadi: {e}"

    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, _redact(output.strip())


def is_git_repo() -> bool:
    ok, _ = _run(["git", "rev-parse", "--git-dir"])
    return ok


def _branch() -> str:
    ok, out = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return out.strip() if ok else ""


def _commit(ref: str = "HEAD") -> str:
    ok, out = _run(["git", "log", "-1", "--format=%h %s", ref])
    return out.strip() if ok else ""


def _dirty_files() -> list:
    """O'zgartirilgan, lekin commit qilinmagan fayllar."""
    ok, out = _run(["git", "status", "--porcelain", "--untracked-files=no"])
    if not ok or not out:
        return []
    return [line[3:].strip() for line in out.splitlines() if line.strip()]


def status() -> dict:
    """Hozirgi holat: qaysi shoxcha, qaysi commit, nechta yangilik bor."""
    if not is_git_repo():
        return {"ok": False, "error": "Bu papka git ombori emas."}

    branch = _branch()
    if not branch or branch == "HEAD":
        return {"ok": False, "error": "Shoxcha aniqlanmadi (detached HEAD)."}

    fetched, fetch_out = _run(["git", "fetch", "origin", branch])
    if not fetched:
        return {"ok": False, "error": f"GitHub'ga ulanib bo'lmadi:\n{fetch_out}"}

    ok, out = _run(["git", "log", "--oneline", f"HEAD..origin/{branch}"])
    incoming = [line for line in out.splitlines() if line.strip()] if ok else []

    ok, out = _run(["git", "log", "--oneline", f"origin/{branch}..HEAD"])
    local_only = [line for line in out.splitlines() if line.strip()] if ok else []

    return {
        "ok": True,
        "branch": branch,
        "current": _commit(),
        "incoming": incoming,
        "local_only": local_only,
        "dirty": _dirty_files(),
    }


def _requirements_hash() -> str:
    path = repo_root() / "requirements.txt"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def update() -> dict:
    """Kodni tortib oladi va kerak bo'lsa kutubxonalarni yangilaydi.

    Qayta ishga tushirmaydi — buni chaqiruvchi alohida hal qiladi, chunki
    to'xtatishdan oldin adminni ogohlantirish kerak.
    """
    state = status()
    if not state["ok"]:
        return {"ok": False, "error": state["error"]}

    if state["dirty"]:
        listed = "\n".join(f"• {name}" for name in state["dirty"][:10])
        return {"ok": False, "error":
                "Serverda saqlanmagan o'zgarishlar bor. Ular yo'qolib "
                f"ketmasligi uchun yangilash to'xtatildi:\n{listed}"}

    if state["local_only"]:
        listed = "\n".join(f"• {line}" for line in state["local_only"][:10])
        return {"ok": False, "error":
                "Serverda GitHub'ga yuborilmagan commitlar bor:\n"
                f"{listed}\n\nAvval ularni push qiling."}

    if not state["incoming"]:
        return {"ok": True, "changed": False, "branch": state["branch"],
                "current": state["current"], "log": []}

    # Yangilash butunicha bajariladi yoki umuman bajarilmaydi. Kutubxonalar
    # o'rnatilmay qolsa, kod yangi-yu kutubxonalar eski holat yuzaga kelardi
    # va bot keyingi ishga tushishda import xatosi bilan yiqilardi.
    ok, rollback_to = _run(["git", "rev-parse", "HEAD"])
    rollback_to = rollback_to.strip() if ok else ""

    before = _requirements_hash()
    merged, merge_out = _run(["git", "merge", "--ff-only", f"origin/{state['branch']}"])
    if not merged:
        return {"ok": False, "error": f"Kodni birlashtirib bo'lmadi:\n{merge_out}"}

    steps = []
    if _requirements_hash() != before:
        installed, pip_out = _run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
            timeout=_PIP_TIMEOUT,
        )
        if not installed:
            restored = ""
            if rollback_to:
                back, _ = _run(["git", "reset", "--hard", rollback_to])
                restored = ("\n\n↩️ Kod eski holatiga qaytarildi — bot avvalgidek "
                            "ishlayveradi." if back else
                            "\n\n⚠️ Kodni qaytarib bo'lmadi, serverni tekshiring.")
            return {"ok": False, "error":
                    f"Kutubxonalar o'rnatilmadi:\n{pip_out[:500]}{restored}"}
        steps.append("Kutubxonalar yangilandi")

    return {"ok": True, "changed": True, "branch": state["branch"],
            "current": _commit(), "log": state["incoming"], "steps": steps}


def restart() -> None:
    """Jarayonni yangi kod bilan almashtiradi.

    `os.execv` joriy jarayon o'rnini egallaydi: PID ham, `screen` oynasi
    ham o'zgarmaydi, ya'ni nazoratchi dastur kerak emas. Bu funksiya
    qaytmaydi.
    """
    logger.warning("Bot qayta ishga tushirilmoqda (yangilashdan keyin)")
    # Bufer tozalanmasa oxirgi loglar yo'qoladi.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    root = repo_root()
    # Bot nisbiy yo'llarga tayanadi (`temp/`, `generated_documents/`), shuning
    # uchun yangi jarayon ham o'sha papkadan boshlanishi kerak.
    try:
        os.chdir(root)
    except OSError as e:
        logger.error("Papkaga o'tib bo'lmadi (%s): %s", root, e)
    os.execv(sys.executable, [sys.executable, str(root / "main.py")])
