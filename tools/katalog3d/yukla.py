"""Nomzodlar ro'yxatidagi modellarni yuklab, PowerPoint'ga mos GLB qilib, litsenziyasi bilan saqlaydi.

    python tools/katalog3d/yukla.py <nomzod.jsonl> <katalog_papka> [--max-texture 2048] [--max-tris 200000]

Har model: <katalog_papka>/<bolim>/<id>/model.glb + LICENSE.txt + meta.json.
Natijalar <katalog_papka>/natija.jsonl ga yoziladi — qayta ishga tushirilsa tayyorlari o'tkazib yuboriladi.
Konvertor: glb_tayyorla.mjs (NODE_PATH — @gltf-transform/*, draco3dgltf, meshoptimizer, sharp).
"""
import argparse
import json
import os
import queue
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

# Yuklash, litsenziya va konvertor bot bilan umumiy: bot ham yetishmagan modelni shu yo'l bilan o'zi yuklaydi.
from services.kat3d.yukla import Konvertor, manba_url, saqla, yuklab_ol  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nomzod")
    ap.add_argument("katalog")
    ap.add_argument("--max-texture", type=int, default=2048)
    ap.add_argument("--max-tris", type=int, default=200000)
    ap.add_argument("--yuklovchi", type=int, default=8)
    ap.add_argument("--konvertor", type=int, default=3)
    ap.add_argument("--node-path", default=os.getenv("NODE_PATH", ""))
    ap.add_argument("--max", type=int, default=0)
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.nomzod, encoding="utf-8") if l.strip()]
    natija_path = os.path.join(a.katalog, "natija.jsonl")
    tayyor = set()
    if os.path.isfile(natija_path):
        tayyor = {json.loads(l)["uid"] for l in open(natija_path, encoding="utf-8") if l.strip()}
    rows = [r for r in rows if r["uid"] not in tayyor]
    if a.max:
        rows = rows[:a.max]
    raw_dir = os.path.join(a.katalog, "_xom")
    os.makedirs(raw_dir, exist_ok=True)
    print(f"{len(tayyor)} tayyor, {len(rows)} navbatda", flush=True)

    ishlov = queue.Queue(maxsize=a.konvertor * 3)
    lock = threading.Lock()
    out_fh = open(natija_path, "a", encoding="utf-8")
    hisob = {"ok": 0, "xato": 0, "bayt": 0}
    t0 = time.time()

    def yoz(rec):
        with lock:
            out_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_fh.flush()
            hisob["ok" if rec.get("ok") else "xato"] += 1
            n = hisob["ok"] + hisob["xato"]
            if n % 25 == 0:
                print(f"[{time.time() - t0:6.0f}s] {n}/{len(rows)} ok={hisob['ok']} xato={hisob['xato']} "
                      f"{hisob['bayt'] / 1e9:.2f} GB", flush=True)

    def yuklovchi(r):
        raw = os.path.join(raw_dir, r["uid"] + ".glb")
        try:
            if not os.path.isfile(raw):
                yuklab_ol(manba_url(r), raw)
        except Exception as e:  # noqa: BLE001
            yoz({"uid": r["uid"], "ok": False, "bosqich": "yuklash", "error": str(e)[:300]})
            return
        ishlov.put((r, raw))

    def ishchi():
        konv = Konvertor(a.node_path)
        while True:
            item = ishlov.get()
            if item is None:
                return
            r, raw = item
            d = os.path.join(a.katalog, r["bolim"], r["uid"])
            os.makedirs(d, exist_ok=True)
            try:
                res = konv({"in": raw, "out": os.path.join(d, "model.glb"),
                            "max_texture": a.max_texture, "max_tris": a.max_tris})
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "error": str(e)}
                konv = Konvertor(a.node_path)
            os.remove(raw)
            if not res.get("ok"):
                yoz({"uid": r["uid"], "ok": False, "bosqich": "konvert", "error": res.get("error")})
                for f in os.listdir(d):
                    os.remove(os.path.join(d, f))
                os.rmdir(d)
                continue
            meta = saqla(r, res, d, os.path.relpath(os.path.join(d, "model.glb"), a.katalog))
            with lock:
                hisob["bayt"] += res["size"]
            yoz(dict(meta, ok=True))

    workers = [threading.Thread(target=ishchi, daemon=True) for _ in range(a.konvertor)]
    for w in workers:
        w.start()
    with ThreadPoolExecutor(a.yuklovchi) as ex:
        list(ex.map(yuklovchi, rows))
    for _ in workers:
        ishlov.put(None)
    for w in workers:
        w.join()
    print("tugadi:", hisob, f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
