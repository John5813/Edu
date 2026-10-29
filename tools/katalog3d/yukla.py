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
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
HF = "https://huggingface.co/datasets/allenai/objaverse/resolve/main/"


def manba_url(r):
    return r.get("url") or HF + r["yol"]


def litsenziya_matni(r):
    nom = r.get("nom") or r["uid"]
    if r["manba"] == "smithsonian":
        return (f"{nom}\nManba: Smithsonian Institution — {r.get('sahifa', '')}\n"
                f"Litsenziya: CC0 1.0 (Public Domain Dedication) — https://creativecommons.org/publicdomain/zero/1.0/\n"
                f"Muallifni ko'rsatish shart emas, lekin tavsiya etiladi: \"{r.get('attribution_full', '')}\"\n")
    lic = r["litsenziya"]
    url = ("https://creativecommons.org/licenses/by/4.0/" if lic == "CC BY 4.0"
           else "https://creativecommons.org/publicdomain/zero/1.0/")
    return (f"\"{nom}\" — {r.get('muallif', '')} ({r.get('muallif_url', '')})\n"
            f"Asl sahifa: {r.get('sahifa', '')}\nLitsenziya: {lic} — {url}\n"
            f"O'zgartirishlar: PowerPoint uchun qayta formatlangan (teksturalar kichraytirilgan, to'r soddalashtirilgan).\n"
            + ("Muallifni ko'rsatish majburiy.\n" if lic == "CC BY 4.0" else ""))


def attribution(r):
    if r["manba"] == "smithsonian":
        return r.get("attribution_full") or f"{r.get('nom', '')} — Smithsonian Institution, CC0"
    return f"\"{r.get('nom', '')}\" by {r.get('muallif', '')} ({r.get('sahifa', '')}), {r['litsenziya']}"


def attribution_qisqa(r):
    if r["manba"] == "smithsonian":
        return "3D: Smithsonian · CC0"
    return f"3D: {r.get('muallif', '')} · {r['litsenziya']}"


def yuklab_ol(url, path, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=180) as resp, open(path + ".part", "wb") as fh:
                while True:
                    b = resp.read(1 << 20)
                    if not b:
                        break
                    fh.write(b)
            os.replace(path + ".part", path)
            return
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


class Konvertor:
    def __init__(self, node_path):
        env = dict(os.environ, NODE_PATH=node_path)
        self.p = subprocess.Popen(["node", os.path.join(HERE, "glb_tayyorla.mjs")], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)

    def __call__(self, job):
        self.p.stdin.write(json.dumps(job) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError("konvertor to'xtab qoldi")
        return json.loads(line)


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
            meta = dict(r, **{k: res[k] for k in ("tris", "tris_before", "size", "textures", "bbox", "animations", "baked")})
            meta["attribution_full"] = attribution(r)
            meta["attribution"] = attribution_qisqa(r)
            meta["fayl"] = os.path.relpath(os.path.join(d, "model.glb"), a.katalog)
            with open(os.path.join(d, "LICENSE.txt"), "w", encoding="utf-8") as fh:
                fh.write(litsenziya_matni(meta))
            with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=1)
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
