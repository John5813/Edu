"""Saytdagi 3D mavzu tekshiruvi — quruq sinov (pul ham, buyurtma ham yo'q): 20 ta namuna mavzu uchun eski (#337:
faqat «to'liq mos») va yangi (services/three_d_gate.py) qaror, haqiqiy AI bilan.

Serverda (AI kaliti bor joyda), loyiha papkasidan:
    python tools/katalog3d/tekshiruv_sinov.py [natija.json]

Har mavzu ~5-15 soniya, 6 tadan parallel; AI sarfi — har mavzuga 3 ta qisqa so'rov (mavzu yozilgandagi kabi).
"""
import concurrent.futures as cf
import json
import logging
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT); os.chdir(ROOT)
os.environ.setdefault("BOT_TOKEN", "1:x")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("services.kat3d.qidiruv").setLevel(logging.INFO)

from services import katalog3d  # noqa: E402
from services.kat3d import qidiruv  # noqa: E402
from services.med3d import auto as med3d_auto  # noqa: E402


TOPICS = [
    ("Ichki yonuv dvigatelining ishlash prinsipi", "yes"),
    ("Quyosh tizimi sayyoralari va ularning ichki tuzilishi", "yes"),
    ("Inson yuragining tuzilishi va qon aylanish tizimi", "yes"),
    ("Qadimgi Misr piramidalari", "yes"),
    ("Dinozavrlar davri", "yes"),
    ("Vulqonlar va zilzilalar", "yes"),
    ("Kosmosni zabt etish tarixi", "yes"),
    ("Samolyotlar qanday uchadi", "yes"),
    ("Hasharotlar dunyosi", "yes"),
    ("Okean va dengiz hayvonlari", "yes"),
    ("Bug' mashinasi va sanoat inqilobi", "yes"),
    ("Musiqa asboblari", "yes"),
    ("Avtomobil tuzilishi", "yes"),
    ("Mars sayyorasi", "yes"),
    ("Amir Temur davri me'morchiligi", "yes"),
    ("Inson skeleti", "yes"),
    ("Plural Noun", "no"),
    ("Inflyatsiya va uning oqibatlari", "no"),
    ("Ingliz tilida Present Perfect zamoni", "no"),
    ("Ish yuritish va hujjatlar bilan ishlash", "no"),
]


def run(topic):
    t0 = time.time()
    lang = "uz"
    try:
        med = med3d_auto.check_topic(topic, lang)
    except Exception as exc:
        med = {"ok": False, "checked": False, "err": str(exc)[:80]}
    try:
        kat = qidiruv.top(topic, lang)
    except Exception as exc:
        kat = {"ok": False, "ids": [], "err": str(exc)[:80]}
    cat = katalog3d.katalog()
    from services import three_d_gate
    anatomy = med.get("ok") and med.get("checked", True)
    lvl = kat.get("level") or ("full" if kat.get("ok") else "none")
    old = "anatomy" if (anatomy or (med.get("ok") and not kat.get("ok"))) else ("catalog" if kat.get("ids") and lvl == "full" else "rad")
    new = three_d_gate.decide(med, kat, topic)["mode"] or "rad"
    return {"old": old, "new": new, "topic": topic, "sec": round(time.time() - t0, 1), "med_ok": med.get("ok"), "med_checked": med.get("checked", True),
            "level": kat.get("level"), "coverage": kat.get("coverage"), "checked": kat.get("checked"),
            "asosiy": [cat[i]["nom_uz"] for i in kat.get("asosiy", [])][:6],
            "ids": [cat[i]["nom_uz"] for i in kat.get("ids", [])][:10], "n_ids": len(kat.get("ids", [])), "err": kat.get("err")}


with cf.ThreadPoolExecutor(6) as pool:
    rows = list(pool.map(run, [t for t, _ in TOPICS]))
want = dict(TOPICS)
for r in rows:
    r["want"] = want[r["topic"]]
def good(r, k):
    return (r[k] != "rad") == (r["want"] == "yes") and not (r["want"] == "yes" and r[k] == "anatomy" and "yurak" not in r["topic"].lower() and "skelet" not in r["topic"].lower())
print("TO'G'RI QAROR: eski", sum(good(r, "old") for r in rows), "/", len(rows), "| yangi", sum(good(r, "new") for r in rows), "/", len(rows))
json.dump(rows, open(sys.argv[1] if len(sys.argv) > 1 else "/dev/stdout", "w"), ensure_ascii=False, indent=1)
for r in rows:
    print(f"{r['want']:3} | eski={r['old']:7} yangi={r['new']:7} | med={r['med_ok']!s:5} | level={r['level']!s:7} cov={r['coverage']!s:4} asosiy={len(r['asosiy'])} ids={r['n_ids']:2} | {r['sec']:5}s | {r['topic'][:50]} | {r['err'] or ''}")
