"""Atlas ma'lumoti (erkak va ayol tanasi) — serverga bir marta yuklanadi va keshda turadi.

Manba: https://github.com/slorksmo/Human-Atlas (aniq commit — ma'lumot o'zgarib qolmaydi, lug'atdagi qism
id lari unga mos). Fayllar git'ga qo'shilmaydi (~130 MB): birinchi so'rovda yoki oldindan
`python tools/med3d_lugat.py --yukla` bilan `data/med3d_atlas/` ga yuklanadi. Joyni `MED3D_ATLAS_DIR`
o'zgartiradi.

Erkak: BodyParts3D 4.0 (DBCLS), CC BY 4.0. Ayol: Human Reference Atlas v1.10 (HuBMAP, NLM Visible Human
Female), CC BY 4.0. Manba har slaydda ko'rsatiladi.
"""
import gzip
import json
import logging
import os
import threading
import urllib.request

from . import ROOT
from .atlas import Atlas

log = logging.getLogger(__name__)

REPO_SHA = "5bb5713aab18d7fe9380c3339eb09f173491ea06"
BASE_URL = f"https://raw.githubusercontent.com/slorksmo/Human-Atlas/{REPO_SHA}/public/models/"
CATALOGS = {"male": "atlas.json", "female": "atlas-female.json"}
ATLAS_DIR = os.getenv("MED3D_ATLAS_DIR") or os.path.join(ROOT, "data", "med3d_atlas")

_lock = threading.Lock()


def _fetch(url: str, path: str) -> None:
    tmp = path + ".part"
    with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as fh:
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            fh.write(block)
    os.replace(tmp, path)


def ensure(body: str, directory: str = ATLAS_DIR) -> str:
    """Shu tana atlasi diskda bo'lishini ta'minlaydi (yo'q bo'lsa yuklaydi). Papka yo'lini qaytaradi."""
    catalog = CATALOGS[body]
    with _lock:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, catalog)
        if not os.path.isfile(path):
            log.info("med3d: atlas yuklanmoqda: %s", catalog)
            _fetch(BASE_URL + catalog, path)
        with open(path, encoding="utf-8") as fh:
            chunks = json.load(fh)["chunks"]
        for chunk in chunks:
            name = os.path.basename(chunk["url"])
            target = os.path.join(directory, name)
            if os.path.isfile(target):
                continue
            log.info("med3d: atlas bo'lagi yuklanmoqda: %s", name)
            gz = target + ".gz"
            _fetch(BASE_URL + name + ".gz", gz)
            with gzip.open(gz, "rb") as src, open(target + ".part", "wb") as dst:
                dst.write(src.read())
            os.replace(target + ".part", target)
            os.remove(gz)
    return directory


def atlas(body: str, directory: str = ATLAS_DIR) -> Atlas:
    """Yangi Atlas obyekti (bo'laklar xotirada so'rov davomida turadi, keyin bo'shatiladi)."""
    return Atlas(ensure(body, directory), CATALOGS[body])
