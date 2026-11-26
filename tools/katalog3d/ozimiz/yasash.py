"""O'zimizning 3D to'plamni yasash: har fan moduli → `data/katalog3d/ozimiz_<fan>.json` + preview/niqob + GLB.

    python -m tools.katalog3d.ozimiz.yasash              # hammasi
    python -m tools.katalog3d.ozimiz.yasash kimyo fizika # faqat shu fanlar
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))           # tools/katalog3d

MODULES = ["kimyo", "fizika", "geografiya", "chizmachilik", "biologiya", "astronomiya", "informatika", "statistika", "sport"]


def main(names):
    from ozimiz import asos

    total = 0
    for name in names or MODULES:
        mod = importlib.import_module(f"ozimiz.{name}")
        rows = asos.build(mod.entries(), "ozimiz_" + name, source=getattr(mod, "SOURCE", ""),
                          licenses=getattr(mod, "LICENSES", None))
        total += len(rows)
        print(f"── {name}: {len(rows)} ta model\n")
    print("Jami:", total)


def yetishmaganlar() -> int:
    """Serverda: git'da faqat katalog (JSON, preview), GLB'lar esa yo'q bo'lsa shu yerda yasaladi (~1-2 daqiqa).
    Tarmoq va RDKit kerak emas: teksturalar, relyef, PDB va molekula geometriyasi `data/katalog3d/` da."""
    import importlib

    from tools.katalog3d import geometriya
    from tools.katalog3d.ozimiz import asos

    made = len(geometriya.build_all(glb_only=True))
    for name in MODULES:
        mod = importlib.import_module(f"tools.katalog3d.ozimiz.{name}")
        made += len(asos.build(mod.entries(), "ozimiz_" + name, glb_only=True))
    return made


if __name__ == "__main__":
    main(sys.argv[1:])
