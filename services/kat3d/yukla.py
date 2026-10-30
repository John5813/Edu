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
(doimiy diskli serverda: keyin hech bir buyurtma kutmaydi). `KATALOG3D_YUKLOVCHI` — bir vaqtda nechta model.
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
    """`glb_tayyorla.mjs` jarayoni: har qatorda bitta vazifa (JSON) oladi, bitta natija qaytaradi."""

    def __init__(self, node_path: str = NODE_MODULES):
        env = dict(os.environ, NODE_PATH=node_path or NODE_MODULES)
        self.p = subprocess.Popen(["node", os.path.join(TOOLS, "glb_tayyorla.mjs")], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)

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
    now = time.time()
    return have | frozenset(i for i in manbalar() if i in katalog3d.katalog()
                            and now - _failed.get(i, 0.0) > RETRY_AFTER)


_jobs: Dict[str, Future] = {}
_failed: Dict[str, float] = {}
_jobs_lock = threading.Lock()
_local = threading.local()
_pool = ThreadPoolExecutor(max_workers=int(os.getenv("KATALOG3D_YUKLOVCHI") or 3), thread_name_prefix="katalog3d")
_bulk = ThreadPoolExecutor(max_workers=1, thread_name_prefix="katalog3d-fon")


def _konvertor() -> Konvertor:
    konv = getattr(_local, "konv", None)
    if konv is None or konv.p.poll() is not None:
        konv = _local.konv = Konvertor()
    return konv


def _bitta(mid: str) -> bool:
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
    t0 = time.time()
    try:
        if not os.path.isfile(raw):
            yuklab_ol(manba_url(r), raw)
        try:
            res = _konvertor()({"in": raw, "out": tmp, "max_texture": MAX_TEXTURE, "max_tris": MAX_TRIS})
        except Exception:
            _local.konv = None                            # jarayon yiqildi — keyingisi yangisini ochadi
            raise
        if not res.get("ok"):
            raise RuntimeError(res.get("error") or "konvertatsiya o'tmadi")
        saqla(r, res, model_dir, m["fayl"])
        os.replace(tmp, target)                           # model.glb faqat to'liq tayyor bo'lganda paydo bo'ladi
        log.info("3D katalog: model yuklandi — %s (%.1f MB, %.0f s)", m.get("nom_uz") or mid,
                 os.path.getsize(target) / 1e6, time.time() - t0)
        return True
    except Exception as exc:                              # noqa: BLE001
        _failed[mid] = time.time()
        log.warning("3D katalog: model yuklanmadi — %s: %s", mid, str(exc)[:300])
        return False
    finally:
        for path in (raw, tmp):
            if os.path.isfile(path):
                os.remove(path)


def _start(mid: str, pool: ThreadPoolExecutor) -> Optional[Future]:
    from services import katalog3d

    with _jobs_lock:
        job = _jobs.get(mid)
        if job is not None and not job.done():
            return job
        if katalog3d.model_yoli(mid) or mid not in manbalar() or time.time() - _failed.get(mid, 0.0) < RETRY_AFTER:
            return None
        job = _jobs[mid] = pool.submit(_bitta, mid)
        job.add_done_callback(lambda _f: katalog3d.mavjud(ttl=0))
        return job


def oldindan(ids: Iterable[str]) -> int:
    """Yetishmagan modellarni fonda yuklay boshlaydi (kutmaydi). Nechta navbatga qo'yilganini qaytaradi."""
    if not ishlaydi():
        return 0
    return sum(1 for mid in ids if _start(mid, _pool) is not None)


def ensure(ids: Iterable[str], timeout: float = 240.0) -> List[str]:
    """Modellar diskda bo'lishini kutadi (yo'qlari yuklanadi). Tayyorlarini tartibi bilan qaytaradi."""
    from services import katalog3d

    ids = list(dict.fromkeys(ids))
    jobs = [j for j in (_start(mid, _pool) for mid in ids) if j is not None] if ishlaydi() else []
    if jobs:
        done, pending = wait(jobs, timeout=timeout)
        if pending:
            log.warning("3D katalog: %d ta model %.0f s da yuklanib ulgurmadi", len(pending), timeout)
    katalog3d.mavjud(ttl=0)
    return [mid for mid in ids if katalog3d.model_yoli(mid)]


def hammasini_fonda() -> int:
    """Hamma yetishmagan modelni fonda bittadan yuklaydi (buyurtmalar navbati bundan ustun)."""
    from services import katalog3d

    if not ishlaydi():
        return 0
    have = katalog3d.mavjud(ttl=0)
    missing = [mid for mid in katalog3d.katalog() if mid not in have and mid in manbalar()]
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
