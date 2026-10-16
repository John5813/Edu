"""Tibbiyot uchun haqiqiy 3D taqdimot: slaydlarda `.glb` modellar va PowerPoint Morph o'tishlari.

Har slaydda anatomik qismlar (masalan bosh suyagi tepasi va pastki jag') alohida 3D model sifatida
turadi. Qo'shni slaydlarda bir xil nomli modellarni PowerPoint Morph silliq harakatlantiradi:
qism ajralib chiqib ketadi, qolgani aylanib kattalashadi. Taqdimot kompyuterdagi PowerPoint
(365 / 2019+) uchun — telefonda 3D ko'rinmaydi.

Modellar oldindan `tools/med3d_tayyorla.py` bilan tayyorlanadi (`assets/med3d/`); bot faqat tayyor
fayllarni slaydga qo'yadi — hostga og'ir hisob tushmaydi.
"""
import json
import os
from functools import lru_cache

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS_DIR = os.path.join(ROOT, "assets", "med3d")
# Z-Anatomy (CC BY-SA 4.0): erkak atlasida yo'q bosh mushaklari — `tools/med3d_zanatomy.py` tayyorlaydi.
ZA_DIR = os.path.join(ASSETS_DIR, "zanatomy")


@lru_cache(maxsize=16)
def load_scene(key: str, assets_dir: str = ASSETS_DIR) -> dict:
    with open(os.path.join(assets_dir, key, "scene.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["dir"] = os.path.join(assets_dir, key)
    return doc


def available_scenes(assets_dir: str = ASSETS_DIR) -> list:
    if not os.path.isdir(assets_dir):
        return []
    return sorted(d for d in os.listdir(assets_dir) if os.path.isfile(os.path.join(assets_dir, d, "scene.json")))
