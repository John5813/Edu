"""Z-Anatomy (Startup.blend) dan bosh mushaklarini xom holda chiqarish — Blender ichida ishlaydi.

    blender -b Z-Anatomy/Startup.blend --python tools/med3d_zanatomy_blender.py -- chiqish_papka [head|joints|nerves|extra]

Natija: `za_raw.json` + `za_raw.bin` (Blender koordinatalari: Z yuqoriga, -Y oldinga). Keyin
`python tools/med3d_zanatomy.py chiqish_papka` ularni atlasimizga moslab `assets/med3d/zanatomy/` ga yozadi.
To'plamlar: head — "Muscles of head" va "Facial muscles" dagi hamma mushak va mushakchalar; joints — "3: Joints"
dagi boylamlar, kapsulalar, menisklar; nerves — "7: Nervous system" dagi nervlar (egri chiziqlar naycha sifatida).
extra — atlasimizda yo'q, ko'p so'raladigan a'zolar (`EXTRA` ro'yxati: qalqonsimon bez, quloq, murtak va boshqalar).
Moslash uchun skelet suyaklari ham chiqariladi.
"""
import array
import json
import os
import re
import sys

import bpy  # noqa: E402  (faqat Blender ichida)

args = sys.argv[sys.argv.index("--") + 1:]
out_dir, which = args[0], (args[1] if len(args) > 1 else "head")
os.makedirs(out_dir, exist_ok=True)
HEAD_BONES = re.compile(r"^(Mandible|Frontal bone|Occipital bone|Sphenoid bone|Temporal bone|Parietal bone|Zygomatic bone|"
                        r"Maxilla|Nasal bone)(\.[lr])?$")
EXTRA = re.compile(r"^(Thyroid gland|Superior parathyroid gland|Inferior parathyroid gland|Cochlea|Malleus|Incus|Stapes|"
                   r"Tympanic membrane|Sinus of frontal bone|Sinus of sphenoid bone|Greater omentum|Lesser omentum|"
                   r"Palatine tonsil|Rectus abdominis muscle|Transversus abdominis muscle|Pyramidalis muscle|"
                   r"Internal oblique muscle|Quadratus lumborum muscle)(\.[a-z]+)?$")
chosen = []
for o in bpy.data.objects:
    cols = {c.name for c in o.users_collection}
    if o.type == "CURVE" and which == "nerves" and any(c.startswith("7:") for c in cols):
        chosen.append(("nerve", o))
        continue
    if o.type != "MESH" or not len(o.data.polygons):
        continue
    if which == "head":
        if cols & {"Muscles of head", "Facial muscles"} and re.search(r"\.[lr]$", o.name):
            chosen.append(("muscle", o))
        elif HEAD_BONES.match(o.name):
            chosen.append(("bone", o))
    else:
        if which == "joints" and "3: Joints" in cols:
            chosen.append(("joint", o))
        elif which == "extra" and EXTRA.match(o.name):
            chosen.append(("organ", o))
        elif "1: Skeletal system" in cols:
            chosen.append(("bone", o))

dg = bpy.context.evaluated_depsgraph_get()
parts, off = [], 0
with open(os.path.join(out_dir, f"za_raw_{which}.bin"), "wb") as fh:
    for kind, o in chosen:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        me.transform(o.matrix_world)
        me.calc_loop_triangles()
        n = len(me.vertices)
        co = array.array("f", [0.0]) * (n * 3)
        me.vertices.foreach_get("co", co)
        no = array.array("f", [0.0]) * (n * 3)
        me.vertices.foreach_get("normal", no)
        tri = array.array("I", [0]) * (len(me.loop_triangles) * 3)
        me.loop_triangles.foreach_get("vertices", tri)
        if not n or not len(tri):
            ev.to_mesh_clear()
            continue
        rec = dict(name=o.name, kind=kind, n=n, m=len(tri), cols=sorted(c.name for c in o.users_collection))
        for key, arr in (("pos", co), ("nrm", no), ("idx", tri)):
            data = arr.tobytes()
            rec[key] = off
            fh.write(data)
            off += len(data)
        parts.append(rec)
        ev.to_mesh_clear()
with open(os.path.join(out_dir, f"za_raw_{which}.json"), "w") as fh:
    json.dump({"parts": parts}, fh)
print("ZA:", which, len(parts), "qism")
