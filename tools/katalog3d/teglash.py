"""Nomzodlarni LLM bilan ko'rib chiqish: ta'limga yaroqlimi, o'zbekcha nom, fan va kalit so'zlar.

    python tools/katalog3d/teglash.py <nomzod.jsonl> <teg.jsonl> [--model anthropic/claude-sonnet-5.5]

OpenRouter orqali (OPENROUTER_API_KEY; muhitda proksi o'zi qo'yadi). 30 tadan to'plab yuboriladi,
natija <teg.jsonl> ga uid bo'yicha yoziladi — qayta ishga tushirilsa tayyorlari o'tkazib yuboriladi.
"""
import argparse
import json
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = "https://openrouter.ai/api/v1/chat/completions"
FANLAR = ["tarix", "biologiya", "geografiya", "fizika", "kimyo", "astronomiya", "texnologiya", "informatika",
          "san'at", "arxitektura", "adabiyot", "iqtisodiyot", "sport", "musiqa", "tibbiyot", "ekologiya",
          "texnika", "transport", "oshxona", "boshqa"]

PROMPT = """Sen Edufayl (o'zbek o'quvchi va o'qituvchilari uchun taqdimot xizmati) uchun 3D modellar katalogini saralaysan.
Har model Sketchfab'dan: nomi, teglari, tavsifi. Har biri uchun hal qil: bu model maktab/universitet taqdimotida
(tarix, biologiya, geografiya, fizika, texnika, san'at va h.k.) haqiqiy narsani ko'rsatish uchun yaroqlimi?

OLINMAYDI (olish=false): o'yinchoq, qo'g'irchoq, o'yin yoki film/multfilm qahramoni va buyumi, anime, fantastika
(sci-fi, fantasy, cyberpunk, o'ylab topilgan mavjudot/mashina), qurol va harbiy texnika, 18+ yoki qo'rqinchli narsa,
AI yaratgan model, low-poly/stylized/multfilm uslubi, "pack"/to'plam/sahna demo, texnik sinov, mem, reklama,
mavzusi tushunarsiz narsa ("Draft", "Room 3", "Untitled"), oddiy ichki xona yoki mebel sahnasi, shaxsiy portret.
OLINADI: haqiqiy hayvon, o'simlik, qazilma, muzey buyumi, tarixiy bino/yodgorlik, haykal, real mashina va mexanizm,
ilmiy asbob, tabiat obyekti (tosh, vulqon, landshaft), real transport, taom, cholg'u asbobi va shu kabilar.
Shubha bo'lsa — olma.

Har model uchun JSON obyekt: {"i": raqam, "olish": true/false, "nom": "o'zbekcha qisqa nom (lotin, 2-6 so'z)",
"fan": bittasi %s, "kalit": ["o'zbekcha 3-6 kalit so'z"], "sifat": 1-5 (taqdimot uchun qanchalik foydali)}.
Faqat JSON massiv qaytar, boshqa matn yo'q.

Modellar:
%s"""


def satr(i, r):
    teg = ", ".join(r.get("teglar", [])[:15])
    tav = " ".join((r.get("tavsif") or "").split())[:220]
    return f'{i}. "{r["nom"]}" | kategoriya: {",".join(r["kategoriyalar"])} | teglar: {teg} | tavsif: {tav}'


def sora(model, rows):
    body = {"model": model, "temperature": 0, "max_tokens": 8000,
            "messages": [{"role": "user", "content": PROMPT % (json.dumps(FANLAR, ensure_ascii=False),
                                                               "\n".join(satr(i, r) for i, r in enumerate(rows)))}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + os.getenv("OPENROUTER_API_KEY", "sk-or-proksi")})
    with urllib.request.urlopen(req, timeout=300) as resp:
        txt = json.load(resp)["choices"][0]["message"]["content"].strip()
    txt = txt[txt.find("["): txt.rfind("]") + 1]
    return {int(x["i"]): x for x in json.loads(txt)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nomzod")
    ap.add_argument("chiqish")
    ap.add_argument("--model", default="anthropic/claude-sonnet-5.5")
    ap.add_argument("--toplam", type=int, default=30)
    ap.add_argument("--parallel", type=int, default=8)
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.nomzod, encoding="utf-8") if l.strip()]
    tayyor = set()
    if os.path.isfile(a.chiqish):
        tayyor = {json.loads(l)["uid"] for l in open(a.chiqish, encoding="utf-8") if l.strip()}
    rows = [r for r in rows if r["uid"] not in tayyor]
    batches = [rows[i:i + a.toplam] for i in range(0, len(rows), a.toplam)]
    print(f"{len(tayyor)} tayyor, {len(rows)} navbatda ({len(batches)} so'rov)", flush=True)
    lock, fh, done = threading.Lock(), open(a.chiqish, "a", encoding="utf-8"), [0]

    def ish(batch):
        for urinish in range(4):
            try:
                res = sora(a.model, batch)
                break
            except Exception as e:  # noqa: BLE001
                print("xato:", str(e)[:200], flush=True)
                time.sleep(5 * (urinish + 1))
        else:
            return
        with lock:
            for i, r in enumerate(batch):
                x = res.get(i)
                if not x:
                    continue
                fan = x.get("fan") if x.get("fan") in FANLAR else "boshqa"
                fh.write(json.dumps({"uid": r["uid"], "olish": bool(x.get("olish")), "nom_uz": x.get("nom", ""),
                                     "fan": fan, "kalit": x.get("kalit", []), "sifat": x.get("sifat", 0)},
                                    ensure_ascii=False) + "\n")
            fh.flush()
            done[0] += 1
            if done[0] % 20 == 0:
                print(f"{done[0]}/{len(batches)}", flush=True)

    with ThreadPoolExecutor(a.parallel) as ex:
        list(ex.map(ish, batches))
    print("tugadi", flush=True)


if __name__ == "__main__":
    main()
