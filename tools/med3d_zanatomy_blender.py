"""Z-Anatomy (Startup.blend) dan bosh mushaklarini xom holda chiqarish — Blender ichida ishlaydi.

    blender -b Z-Anatomy/Startup.blend --python tools/med3d_zanatomy_blender.py -- chiqish_papka

Natija: `za_raw.json` + `za_raw.bin` (Blender koordinatalari: Z yuqoriga, -Y oldinga). Keyin
`python tools/med3d_zanatomy.py chiqish_papka` ularni atlasimizga moslab `assets/med3d/zanatomy/` ga yozadi.
Olinadi: "Muscles of head" va "Facial muscles" to'plamlaridagi hamma mushak va mushakchalar (chap/o'ng),
hamda moslash uchun bosh suyagi suyaklari.
"""
import array
import json
import os
import re
import sys

import bpy  # noqa: E402  (faqat Blender ichida)

out_dir = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out_dir, exist_ok=True)
BONES = re.compile(r"^(Mandible|Frontal bone|Occipital bone|Sphenoid bone|Temporal bone|Parietal bone|Zygomatic bone|"
                   r"Maxilla|Nasal bone)(\.[lr])?$")
chosen = []
for o in bpy.data.objects:
    if o.type != "MESH" or not len(o.data.polygons):
        continue
    cols = {c.name for c in o.users_collection}
    if cols & {"Muscles of head", "Facial muscles"} and re.search(r"\.[lr]$", o.name):
        chosen.append(("muscle", o))
    elif BONES.match(o.name):
        chosen.append(("bone", o))

dg = bpy.context.evaluated_depsgraph_get()
parts, off = [], 0
with open(os.path.join(out_dir, "za_raw.bin"), "wb") as fh:
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
        rec = dict(name=o.name, kind=kind, n=n, m=len(tri))
        for key, arr in (("pos", co), ("nrm", no), ("idx", tri)):
            data = arr.tobytes()
            rec[key] = off
            fh.write(data)
            off += len(data)
        parts.append(rec)
        ev.to_mesh_clear()
with open(os.path.join(out_dir, "za_raw.json"), "w") as fh:
    json.dump({"parts": parts}, fh)
print("ZA:", sum(k == "muscle" for k, _ in chosen), "mushak,", sum(k == "bone" for k, _ in chosen), "suyak")
