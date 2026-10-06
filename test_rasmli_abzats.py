"""Rasmli slayd: matn mayda bandlarga emas, yaxlit abzatslarga bo'linadi.

    python test_rasmli_abzats.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import deck_logic as dl, deck_style, html_slides as hs

def item(head, rest):
    return (f'<div class="item"><span class="item-ikon"><img class="ikon" data-icon="star" alt=""></span>'
            f'<div class="item-text"><b>{head}</b> {rest}</div></div>')

LIST = ('<div class="list">'
        + item("Raqamli fuqarolikni rivojlantirish.", "O'quvchilarda mas'uliyatli, xavfsiz va samarali onlayn xulq-atvor ko'nikmalarini shakllantirish.")
        + item("Kreativlik va innovatsiyani rag'batlantirish.", "Raqamli vositalardan foydalangan holda ijodiy loyihalar yaratishga undash.")
        + item("Tanqidiy fikrlashni o'stirish.", "Axborotni tahlil qilish va to'g'ri xulosa chiqarish qobiliyatini rivojlantirish.")
        + item("Muammolarni hal qilish ko'nikmalari", "Texnologiyalar yordamida real hayotiy vazifalarni yechishga o'rgatish.")
        + item("Hamkorlikni kuchaytirish.", "Raqamli muhitda birgalikda ishlash va loyihalarni bajarish malakasini oshirish.")
        + '</div>')
PHOTO = '<div class="rasm" data-prompt="a teacher helping pupils"><p class="rasm-matn">Qo\'shimcha matn.</p></div>'

def slide(side):
    return ('<section class="slide"><div class="head"><h2 class="title">Asosiy maqsadlar</h2><div class="rule"></div></div>'
            '<div class="body"><p class="lead">Bosh fikr.</p><div class="split">' + side + PHOTO + '</div></div></section>')

print("1) Ro'yxat → yaxlit abzatslar")
out = dl.flow_photo_text(slide(LIST))
check("par-col paydo bo'ldi", 'class="par-col"' in out)
paras = re.findall(r'<p class="par">(.*?)</p>', out, re.S)
check("abzats 2-3 ta", 2 <= len(paras) <= 3, len(paras))
check("ro'yxat bandi va ikonka qolmadi", "item-text" not in out and "item-ikon" not in out)
check("barcha matn saqlandi", all(w in " ".join(paras) for w in
      ["mas'uliyatli", "rag'batlantirish", "Tanqidiy", "Hamkorlikni kuchaytirish", "Muammolarni hal qilish ko'nikmalari — Texnologiyalar"]) or "Muammolarni hal qilish ko'nikmalari. Texnologiyalar" in " ".join(paras), paras)
check("har abzats nuqta bilan tugaydi", all(p.rstrip()[-1] in ".!?" for p in paras), paras)
check("rasm bloki va bosh gap joyida", 'data-prompt="a teacher helping pupils"' in out and '<p class="lead">Bosh fikr.</p>' in out)
check("sarlavha o'zgarmadi", '<h2 class="title">Asosiy maqsadlar</h2>' in out)

print("2) Kartochkalar → abzats")
cards = ('<div class="cols cols-3">' + "".join(
    f'<div class="card"><div class="ikon-dot"><img class="ikon" data-icon="x" alt=""></div>'
    f'<div class="card-title">Sarlavha {i}</div><div class="card-note">Izoh matni {i} to\'liq gap.</div></div>' for i in range(1, 4)) + '</div>')
out2 = dl.flow_photo_text(slide(cards))
p2 = re.findall(r'<p class="par">(.*?)</p>', out2, re.S)
check("kartochkalar abzatsga aylandi", len(p2) == 3 and "card" not in out2.split('class="split"')[1].split('class="rasm"')[0], p2)
check("sarlavha + izoh birga", p2 and p2[0].startswith("Sarlavha 1. Izoh matni 1"), p2)

print("3) Tegilmasligi kerak bo'lganlar")
ready = slide('<div class="par-col"><p class="par">Tayyor abzats.</p></div>')
check("tayyor abzats o'zgarmadi", dl.flow_photo_text(ready) == ready)
noimg = ('<section class="slide"><div class="head"><h2 class="title">T</h2></div><div class="body"><div class="split">' + LIST +
         '<div class="chart" data-kind="bar"></div></div></div></section>')
check("rasmsiz slayd o'zgarmadi", dl.flow_photo_text(noimg) == noimg)
plain_list = ('<section class="slide"><div class="head"><h2 class="title">T</h2></div><div class="body">' + LIST + '</div></section>')
check("rasmsiz ro'yxat o'zgarmadi", dl.flow_photo_text(plain_list) == plain_list)
cover = '<section class="slide dark cover-photo"><div class="body cover-split"><div class="rasm cover-img" data-prompt="x"></div></div></section>'
check("muqova o'zgarmadi", dl.flow_photo_text(cover) == cover)
twelve = slide('<div class="list">' + "".join(item(f"Band {i}.", f"Matn {i}.") for i in range(1, 8)) + '</div>')
p3 = re.findall(r'<p class="par">(.*?)</p>', dl.flow_photo_text(twelve), re.S)
check("7 band ham 3 abzatsdan oshmaydi", len(p3) == 3 and "Band 7." in p3[-1], p3)
check("ikkinchi chaqiruv natijani o'zgartirmaydi", dl.flow_photo_text(out) == out)

print("4) Prompt va uslub")
check("prompt yaxlit abzatsni so'raydi", "YAXLIT ABZATS" in deck_style.BLOCKS and 'class="par-col"' in deck_style.BLOCKS)
check("par uslubi bor", ".par{" in deck_style.CSS if hasattr(deck_style, "CSS") else True)
src = open("services/premium_presentation/html_slides.py", encoding="utf8").read()
check("repair_deck ulangan", "flow_photo_text" in src)

print("\nXATO:" if FAILS else "\nHAMMASI YAXSHI", FAILS or "")
sys.exit(1 if FAILS else 0)
