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


if __name__ == "__main__":
    main(sys.argv[1:])
