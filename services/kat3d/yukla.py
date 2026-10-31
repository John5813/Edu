"""Katalog modellarini serverga avtomatik yuklash — 3D Anatomiya atlasi kabi: kerak bo'lganda o'zi.

Modellar git'da yo'q (~12,5 GB). Model diskda bo'lmasa, u manbasidan (Objaverse/Smithsonian —
`data/katalog3d/tanlov.jsonl`) yuklanadi va PowerPoint'ga mos GLB ga o'giriladi
(`tools/katalog3d/glb_tayyorla.mjs`; natija katalogdagi bilan baytigacha bir xil, ~2-3 soniya):

- bot ishga tushganda konvertorning node paketlari o'zi o'rnatiladi (`tayyorla()`);
- mijoz mavzusiga modellar topilishi bilan ular fonda yuklana boshlaydi (`oldindan()`) — to'lovgacha tayyor;
- taqdimot yig'ishdan oldin `ensure()` ularni kutadi; yuklanmagan model taqdimotga kirmaydi;
- katalog yangilansa (yangi model, yangi `*.json` katalog) — yangi model ham birinchi kerak bo'lganda yuklanadi.

Yangi katalogda manba `data/katalog3d/*.jsonl` dagi yozuv (uid, manba, url/yol, muallif...) yoki katalog
yozuvining o'zidagi `manba_url` (to'g'ridan-to'g'ri GLB havolasi) bo'ladi.

`KATALOG3D_OLDINDAN=1` — bot ishga tushganda hamma yetishmagan modellarni fonda, bittadan yuklaydi
(doimiy diskli serverda: keyin hech bir buyurtma kutmaydi). `KATALOG3D_YUKLOVCHI` — bir vaqtda nechta model
yuklanadi (sukut 2); o'girish (node) esa og'ir ishlar darvozasi orqali (2 GB serverda — doim bittadan).

Xotira (2 GB li serverda bot qotib qolgan edi): bitta konvertatsiya o'rtacha ~350 MB, eng og'ir modellar
(7 mln uchburchak) ~1,6 GB oladi va node jarayoni ishdan keyin ham xotirani qo'yib yubormaydi. Shuning uchun:
- har model alohida node jarayonida o'giriladi va jarayon darhol yopiladi, past ustuvorlikda (`nice`);
- model kerak qiladigan xotira oldindan baholanadi (`ehtiyoj_mb`): serverga sig'maydigani taklif qilinmaydi;
- o'girish umumiy og'ir ishlar darvozasidan (`services.heavy_gate`) o'tadi: brauzer, LibreOffice bilan bir
  navbatda, bo'sh xotira yetgandagina boshlanadi; fonda hammasini yuklash (`FON`) mijoz ishlaridan keyin;
- qorovul: o'girish paytida bo'sh xotira `KATALOG3D_MIN_FREE_MB` (200) dan kamaysa, jarayon baholangandan
  ancha ko'p yesa yoki `KATALOG3D_TIMEOUT` (180 s) dan uzoq ishlasa — u to'xtatiladi (osilib qolgan node
  keyingi buyurtmalarni to'sib qo'ymaydi);
- to'langan buyurtma (`ensure`) modelni tashlab ketmaydi: xotira band bo'lgani uchun o'girilmagan model qayta
  sinaladi, fon navbatida turgan model navbatdan oldinga olinadi.
`KATALOG3D_RAM_MB` — bitta o'girishga ruxsat (sukut: serverning 45% xotirasi).
"""
import glob
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor, wait
from functools import lru_cache
from typing import Dict, Iterable, List, Optional

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS = os.path.join(ROOT, "tools", "katalog3d")
NODE_MODULES = os.path.join(TOOLS, "node_modules")
HF = "https://huggingface.co/datasets/allenai/objaverse/resolve/main/"
MAX_TEXTURE, MAX_TRIS = 2048, 200000
RETRY_AFTER = 3600.0                  # yuklanmagan model qayta qachon sinaladi (soniya)
RETRY_BUSY = 300.0                    # xotira band bo'lgani uchun o'girilmagan model — 5 daqiqadan keyin
RETRY_PAID = 120.0                    # to'langan buyurtma boshqa xato bilan tushgan modelni shundan keyin qayta sinaydi
MIN_FREE_MB = int(os.getenv("KATALOG3D_MIN_FREE_MB") or 200)
TIMEOUT = float(os.getenv("KATALOG3D_TIMEOUT") or 180)          # bitta model o'girishining eng uzoq vaqti
OLDINDAN_MAX = int(os.getenv("KATALOG3D_OLDINDAN_MAX") or 8)     # mavzu yozilganda fonda nechta model


# ───────────────────────────────────────────── manba va litsenziya (tools/katalog3d/yukla.py ham ishlatadi)

def manba_url(r: dict) -> str:
    return r.get("manba_url") or r.get("url") or HF + r["yol"]


def litsenziya_matni(r: dict) -> str:
    nom = r.get("nom") or r.get("uid") or r.get("id")
    if r.get("manba") == "smithsonian":
        return (f"{nom}\nManba: Smithsonian Institution — {r.get('sahifa', '')}\n"
                f"Litsenziya: CC0 1.0 (Public Domain Dedication) — https://creativecommons.org/publicdomain/zero/1.0/\n"
                f"Muallifni ko'rsatish shart emas, lekin tavsiya etiladi: \"{r.get('attribution_full', '')}\"\n")
    lic = r.get("litsenziya", "")
    url = ("https://creativecommons.org/licenses/by/4.0/" if lic == "CC BY 4.0"
           else "https://creativecommons.org/publicdomain/zero/1.0/")
    return (f"\"{nom}\" — {r.get('muallif', '')} ({r.get('muallif_url', '')})\n"
            f"Asl sahifa: {r.get('sahifa', '')}\nLitsenziya: {lic} — {url}\n"
            f"O'zgartirishlar: PowerPoint uchun qayta formatlangan (teksturalar kichraytirilgan, to'r soddalashtirilgan).\n"
            + ("Muallifni ko'rsatish majburiy.\n" if lic == "CC BY 4.0" else ""))


def attribution(r: dict) -> str:
    if r.get("manba") == "smithsonian":
        return r.get("attribution_full") or f"{r.get('nom', '')} — Smithsonian Institution, CC0"
    return f"\"{r.get('nom', '')}\" by {r.get('muallif', '')} ({r.get('sahifa', '')}), {r['litsenziya']}"


def attribution_qisqa(r: dict) -> str:
    if r.get("manba") == "smithsonian":
        return "3D: Smithsonian · CC0"
    return f"3D: {r.get('muallif', '')} · {r['litsenziya']}"


def yuklab_ol(url: str, path: str, tries: int = 4) -> None:
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=180) as resp, open(path + ".part", "wb") as fh:
                while True:
                    block = resp.read(1 << 20)
                    if not block:
                        break
                    fh.write(block)
            os.replace(path + ".part", path)
            return
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


class Konvertor:
    """`glb_tayyorla.mjs` jarayoni: har qatorda bitta vazifa (JSON) oladi, bitta natija qaytaradi.
    `past=True` — past ustuvorlikda (bot serverida: CPU va disk avval botga)."""

    def __init__(self, node_path: str = NODE_MODULES, past: bool = False):
        env = dict(os.environ, NODE_PATH=node_path or NODE_MODULES)
        cmd = ["node", os.path.join(TOOLS, "glb_tayyorla.mjs")]
        if past and shutil.which("ionice"):
            cmd = ["ionice", "-c", "2", "-n", "7"] + cmd
        if past and shutil.which("nice"):
            cmd = ["nice", "-n", "15"] + cmd
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, env=env)
        if past:                                      # xotira tugasa kernel botni emas, avval shu jarayonni o'chirsin
            from services import heavy_gate

            heavy_gate.set_oom_score(self.p.pid)

    def __call__(self, job: dict) -> dict:
        self.p.stdin.write(json.dumps(job) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError("konvertor to'xtab qoldi")
        return json.loads(line)

    def close(self) -> None:
        try:
            self.p.kill()
            self.p.wait(timeout=10)                   # jarayon to'liq tozalansin (zombie qolmasin)
        except Exception:                             # noqa: BLE001
            pass


def saqla(r: dict, res: dict, model_dir: str, fayl: str) -> dict:
    """Konvertatsiyadan keyin: LICENSE.txt va meta.json (model papkasida). meta ni qaytaradi."""
    meta = dict(r, **{k: res[k] for k in ("tris", "tris_before", "size", "textures", "bbox", "animations", "baked")
                      if k in res})
    meta["attribution_full"] = attribution(r)
    meta["attribution"] = attribution_qisqa(r)
    meta["fayl"] = fayl
    with open(os.path.join(model_dir, "LICENSE.txt"), "w", encoding="utf-8") as fh:
        fh.write(litsenziya_matni(meta))
    with open(os.path.join(model_dir, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)
    return meta


# ───────────────────────────────────────────── xotira

def _meminfo() -> Dict[str, int]:
    """/proc/meminfo (MB). Linux bo'lmasa — bo'sh."""
    from services import heavy_gate

    return heavy_gate.meminfo()


def _rss_mb(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/status", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


def ehtiyoj_mb(r: dict) -> int:
    """O'girishning taxminiy eng katta xotirasi (MB) — manba hajmi, uchburchak va tekstura bo'yicha.
    O'lchangan: 0,5-0,75 mln uchburchak ~350 MB, 1 mln + 16K tekstura ~500 MB, 6,9 mln ~1,6 GB."""
    if not r.get("uchburchak"):
        return 600                                    # manba ma'lumoti yo'q (to'g'ridan-to'g'ri havola)
    est = (220 + 200 * r["uchburchak"] / 1e6 + 0.3 * (r.get("hajm") or 0) / 1e6
           + (100 if (r.get("tekstura_max") or 0) >= 16384 else 0))
    return int(est * 1.15)


def byudjet_mb() -> int:
    """Bitta o'girishga ruxsat etilgan xotira: `KATALOG3D_RAM_MB` yoki serverning 45% i (2 GB da ~880 MB)."""
    if os.getenv("KATALOG3D_RAM_MB"):
        return int(os.getenv("KATALOG3D_RAM_MB"))
    total = _meminfo().get("MemTotal", 0)
    return int(total * 0.45) if total else 4000


def sigadi(mid: str) -> bool:
    """Bu serverda o'girsa bo'ladimi (juda og'ir model kichik serverni swap'ga tushirib qotirardi)."""
    r = manbalar().get(mid)
    return bool(r) and ehtiyoj_mb(r) <= byudjet_mb()


class XotiraBand(RuntimeError):
    """Xotira yetmagani uchun o'girilmadi — model og'ir emas, keyinroq qayta urinsa bo'ladi."""


def _aylantir(raw: str, out: str, need: int) -> dict:
    """Modelni alohida node jarayonida o'giradi; jarayon ish tugashi bilan yopiladi (xotira qaytadi).
    Qorovul: bo'sh xotira juda kamaysa yoki jarayon baholangandan ancha ko'p yesa — to'xtatadi."""
    konv = _konvertor()
    stop, why = threading.Event(), []
    limit = max(int(need * 1.6), need + 400)
    t0 = time.time()

    def qorovul():
        proc = getattr(konv, "p", None)
        while proc is not None and not stop.wait(0.5):
            if proc.poll() is not None:
                return
            avail = _meminfo().get("MemAvailable")
            rss = _rss_mb(proc.pid)
            if avail is not None and avail < MIN_FREE_MB:
                why.append(f"serverda bo'sh xotira {avail} MB qoldi")
            elif rss > limit:
                why.append(f"jarayon {rss} MB yedi (chegara {limit} MB)")
            elif time.time() - t0 > TIMEOUT:
                why.append(f"o'girish {TIMEOUT:.0f} s da tugamadi (osilib qoldi)")
            if why:
                proc.kill()
                return

    watch = threading.Thread(target=qorovul, name="katalog3d-qorovul", daemon=True)
    watch.start()
    try:
        return konv({"in": raw, "out": out, "max_texture": MAX_TEXTURE, "max_tris": MAX_TRIS})
    except Exception as exc:
        if why:
            raise (XotiraBand if "bo'sh xotira" in why[0] else RuntimeError)(why[0]) from exc
        raise
    finally:
        stop.set()
        konv.close()


# ───────────────────────────────────────────── serverda avtomatik

_setup_lock = threading.Lock()
_state = {"ready": None, "error": ""}          # ready: None — hali tekshirilmagan


def _paketlar_bor() -> bool:
    return bool(shutil.which("node")) and os.path.isdir(os.path.join(NODE_MODULES, "@gltf-transform", "core"))


def tayyorla() -> Optional[str]:
    """Konvertor ishlashi uchun node va paketlar. Paketlar yo'q bo'lsa bir marta `npm install` qilinadi
    (bot ishga tushganda, alohida oqimda). Xato matnini qaytaradi (hammasi joyida bo'lsa None)."""
    with _setup_lock:
        if _state["ready"] or _paketlar_bor():
            _state.update(ready=True, error="")
            return None
        error = ""
        if not shutil.which("node"):
            error = "node topilmadi"
        elif not shutil.which("npm"):
            error = "npm topilmadi"
        else:
            log.info("3D katalog: konvertor paketlari o'rnatilmoqda (npm install)...")
            try:
                run = subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--omit=dev"], cwd=TOOLS,
                                     capture_output=True, text=True, timeout=900)
                if run.returncode or not _paketlar_bor():
                    error = "npm install: " + (run.stderr or run.stdout)[-400:]
            except Exception as exc:                  # noqa: BLE001
                error = f"npm install: {exc}"
        _state.update(ready=not error, error=error)
        if error:
            log.warning("3D katalog: modellarni avtomatik yuklab bo'lmaydi — %s (faqat diskdagilari ishlaydi)", error)
        else:
            log.info("3D katalog: avtomatik yuklash tayyor")
        return error or None


def ishlaydi() -> bool:
    """Yetishmagan modelni hozir yuklab-o'gira olamizmi (kutmaydi: paketlar o'rnatilayotgan bo'lsa — yo'q)."""
    if not _state["ready"] and _paketlar_bor():
        _state.update(ready=True, error="")
    return bool(_state["ready"])


@lru_cache(maxsize=1)
def manbalar() -> Dict[str, dict]:
    """Har model qayerdan olinadi: `data/katalog3d/*.jsonl` (uid → yozuv) va katalogdagi `manba_url`."""
    from services import katalog3d

    out: Dict[str, dict] = {}
    for path in sorted(glob.glob(os.path.join(katalog3d.KATALOG_DIR, "*.jsonl"))):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    if r.get("uid") and (r.get("url") or r.get("yol") or r.get("manba_url")):
                        out.setdefault(r["uid"], r)
    for mid, m in katalog3d.katalog().items():
        if mid not in out and m.get("manba_url"):
            out[mid] = dict(m, uid=mid)
    return out


def mumkin() -> frozenset:
    """Mijozga taklif qilsa bo'ladigan modellar: diskdagilar + (avtomatik yuklash ishlasa) manbasi borlar."""
    from services import katalog3d

    have = katalog3d.mavjud()
    if not ishlaydi():
        return have
    now, budget = time.time(), byudjet_mb()
    return have | frozenset(i for i, r in manbalar().items() if i in katalog3d.katalog()
                            and now - _failed.get(i, 0.0) > RETRY_AFTER and ehtiyoj_mb(r) <= budget)


_jobs: Dict[str, Future] = {}
_job_pool: Dict[str, ThreadPoolExecutor] = {}
_failed: Dict[str, float] = {}
_busy: set = set()                    # oxirgi urinish xotira band bo'lgani uchun o'tmagan modellar
_jobs_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=int(os.getenv("KATALOG3D_YUKLOVCHI") or 2), thread_name_prefix="katalog3d")
_bulk = ThreadPoolExecutor(max_workers=1, thread_name_prefix="katalog3d-fon")


def _konvertor() -> Konvertor:
    return Konvertor(past=True)


def _bitta(mid: str, priority: Optional[int] = None) -> bool:
    """Bitta modelni yuklab, o'giradi va katalogdagi joyiga qo'yadi. True — tayyor."""
    from services import katalog3d

    if katalog3d.model_yoli(mid):
        return True
    m, r = katalog3d.katalog().get(mid), manbalar().get(mid)
    if not m or not r:
        return False
    target = os.path.join(katalog3d.MODELS_DIR, m["fayl"])
    model_dir = os.path.dirname(target)
    raw_dir = os.path.join(katalog3d.MODELS_DIR, "_xom")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(model_dir, exist_ok=True)
    raw = os.path.join(raw_dir, mid + ".glb")
    tmp = os.path.join(model_dir, "model.tmp.glb")
    need = ehtiyoj_mb(r)
    t0 = time.time()
    try:
        if need > byudjet_mb():
            raise RuntimeError(f"bu server uchun juda og'ir (~{need} MB kerak, ruxsat {byudjet_mb()} MB)")
        if not os.path.isfile(raw):
            yuklab_ol(manba_url(r), raw)
        from services import heavy_gate

        # Brauzer va LibreOffice bilan bitta navbat: bo'sh xotira yetgandagina boshlanadi (kutish — pik emas).
        prio = heavy_gate.ODDIY if priority is None else priority
        with heavy_gate.slot(f"3D model ({m.get('nom_uz') or mid})", need, prio):
            res = _aylantir(raw, tmp, need)
        if not res.get("ok"):
            raise RuntimeError(res.get("error") or "konvertatsiya o'tmadi")
        saqla(r, res, model_dir, m["fayl"])
        os.replace(tmp, target)                           # model.glb faqat to'liq tayyor bo'lganda paydo bo'ladi
        _busy.discard(mid)
        _failed.pop(mid, None)
        log.info("3D katalog: model yuklandi — %s (%.1f MB, %.0f s)", m.get("nom_uz") or mid,
                 os.path.getsize(target) / 1e6, time.time() - t0)
        return True
    except Exception as exc:                              # noqa: BLE001
        # Xotira band bo'lgani uchun — 5 daqiqadan keyin yana; boshqa xatoda — bir soatdan keyin.
        busy = isinstance(exc, XotiraBand)
        _failed[mid] = time.time() - (RETRY_AFTER - RETRY_BUSY if busy else 0.0)
        (_busy.add if busy else _busy.discard)(mid)
        log.warning("3D katalog: model yuklanmadi — %s: %s", mid, str(exc)[:300])
        return False
    finally:
        for path in (raw, tmp):
            if os.path.isfile(path):
                os.remove(path)


def _start(mid: str, pool: ThreadPoolExecutor, priority: Optional[int] = None,
           paid: bool = False) -> Optional[Future]:
    """Model yuklanishini boshlaydi (yoki boshlanganini qaytaradi). `paid=True` — to'langan buyurtma kutyapti:
    xotira band bo'lgani uchun o'tmagan model sovushni kutmasdan qayta sinaladi, fon navbatida (`_bulk`) hali
    boshlanmay turgan model navbatdan olinib oldinga qo'yiladi."""
    from services import katalog3d

    with _jobs_lock:
        job = _jobs.get(mid)
        if job is not None and not job.done():
            if not (pool is _pool and _job_pool.get(mid) is _bulk and job.cancel()):
                return job
        if katalog3d.model_yoli(mid) or not sigadi(mid):
            return None
        since = time.time() - _failed.get(mid, 0.0)
        if since < RETRY_AFTER and not (paid and (mid in _busy or since >= RETRY_PAID)):
            return None
        if priority is None:
            from services import heavy_gate

            priority = heavy_gate.FON if pool is _bulk else heavy_gate.ODDIY
        job = _jobs[mid] = pool.submit(_bitta, mid, priority)
        _job_pool[mid] = pool
        job.add_done_callback(lambda _f: katalog3d.mavjud(ttl=0))
        return job


def oldindan(ids: Iterable[str]) -> int:
    """Yetishmagan modellarni fonda yuklay boshlaydi (kutmaydi). Nechta navbatga qo'yilganini qaytaradi.
    Ko'pi bilan `OLDINDAN_MAX` ta — qolgani kerak bo'lganda (`ensure`) yuklanadi."""
    if not ishlaydi():
        return 0
    return sum(1 for mid in list(ids)[:OLDINDAN_MAX] if _start(mid, _pool) is not None)


def ensure(ids: Iterable[str], timeout: float = 600.0) -> List[str]:
    """To'langan buyurtma uchun: modellar diskda bo'lishini kutadi (yo'qlari yuklanadi). Tayyorlarini tartibi
    bilan qaytaradi. Xotira band bo'lgani uchun o'girilmagan model vaqt tugaguncha qayta sinaladi — mijozga
    to'lovdan oldin ko'rsatilgan model taqdimotdan tushib qolmasin."""
    from services import katalog3d

    ids = list(dict.fromkeys(ids))
    deadline = time.time() + timeout
    todo = [mid for mid in ids if not katalog3d.model_yoli(mid)] if ishlaydi() else []
    while todo:
        jobs = {mid: job for mid in todo for job in [_start(mid, _pool, paid=True)] if job is not None}
        if not jobs:
            break
        _done, pending = wait(list(jobs.values()), timeout=max(0.0, deadline - time.time()))
        if pending:
            log.warning("3D katalog: %d ta model %.0f s da yuklanib ulgurmadi", len(pending), timeout)
            break
        katalog3d.mavjud(ttl=0)
        todo = [mid for mid in jobs if mid in _busy and not katalog3d.model_yoli(mid)]
        if todo:
            if time.time() + 5 >= deadline:
                break
            log.info("3D katalog: %d ta model xotira bo'shagach qayta o'giriladi", len(todo))
            time.sleep(3.0)
    katalog3d.mavjud(ttl=0)
    return [mid for mid in ids if katalog3d.model_yoli(mid)]


def hammasini_fonda() -> int:
    """Hamma yetishmagan modelni fonda bittadan yuklaydi (buyurtmalar navbati bundan ustun)."""
    from services import katalog3d

    if not ishlaydi():
        return 0
    have = katalog3d.mavjud(ttl=0)
    missing = [mid for mid in katalog3d.katalog() if mid not in have and sigadi(mid)]
    for mid in missing:
        _start(mid, _bulk)
    log.info("3D katalog: %d ta model fonda yuklanadi", len(missing))
    return len(missing)


def start_background() -> None:
    """Bot ishga tushganda: paketlarni tayyorlash (va so'ralgan bo'lsa hamma modellarni yuklash) alohida oqimda."""

    def run():
        try:
            if tayyorla() is None and os.getenv("KATALOG3D_OLDINDAN", "0") == "1":
                hammasini_fonda()
        except Exception as exc:                          # noqa: BLE001
            log.error("3D katalog: avtomatik yuklashni tayyorlashda xato: %s", exc)

    threading.Thread(target=run, name="katalog3d-prepare", daemon=True).start()
