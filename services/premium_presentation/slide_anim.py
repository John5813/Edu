"""Yozuv animatsiyasi: taqdimotning har sahifasi ochilganda mazmuni o'zi, navbat bilan paydo bo'ladi.

Bosish shart emas — sahifa ochilishi bilan avval sarlavha, keyin infografika qismlari (barglar, kublar,
kartalar...) chizilish tartibida birin-ketin chiqadi. Dizayner har punktni o'z navbatida chizadi, shuning
uchun chizilish tartibi — ko'rinish tartibi ham: punktlar ketma-ket "teriladi".

Animatsiyasiz qoladiganlar: fon va katta panellar (sahifaning yarmidan kattasi), sahifa chetidan chiqib
turgan bezaklar, jadval/diagramma (graphicFrame), ovoz/video, allaqachon animatsiyasi bor sahifa.
Telefon ilovalari va PDF animatsiyani ko'rsatmaydi — sahifa to'liq holida ko'rinadi, hech narsa buzilmaydi.
"""
import logging
from typing import List, Tuple

from lxml import etree
from pptx import Presentation
from pptx.oxml.ns import qn

log = logging.getLogger(__name__)

FEATURE = "text_anim"     # "🎛 Funksiyalar boshqaruvi" dagi nom; sukut bo'yicha o'chiq
P_NS = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
TITLE_ZONE = 0.2          # sahifa balandligining yuqori qismi: shu yerdagi yozuv — sarlavha, birinchi chiqadi
TITLE_PT = 20.0           # sarlavha shundan kichik bo'lmaydi
BIG = 0.5                 # sahifaning yarmidan katta shakl — fon
ZOOM_MAX = 0.2            # bundan katta shakl kattalashib emas, sekin paydo bo'ladi
SPREAD_MS = 1500          # oxirgi qism shuncha vaqtdan keyin chiqa boshlaydi (+ sarlavha 350 ms)
GAP_MIN, GAP_MAX = 20, 220


def _tgt(spid: int) -> str:
    return f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'


def _visible(cid: int, spid: int) -> str:
    return (f'<p:set><p:cBhvr><p:cTn id="{cid}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>'
            f'</p:cTn>{_tgt(spid)}<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
            f'</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>')


def _fade(cid: int, spid: int, dur: int) -> str:
    return (f'<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{cid}" dur="{dur}"/>{_tgt(spid)}'
            f'</p:cBhvr></p:animEffect>')


def _anim(cid: int, spid: int, dur: int, attr: str, start: str, end: str) -> str:
    def val(v):
        return f'<p:fltVal val="{v}"/>' if v.replace(".", "").isdigit() else f'<p:strVal val="{v}"/>'
    return (f'<p:anim calcmode="lin" valueType="num"><p:cBhvr><p:cTn id="{cid}" dur="{dur}" fill="hold"/>'
            f'{_tgt(spid)}<p:attrNameLst><p:attrName>{attr}</p:attrName></p:attrNameLst></p:cBhvr><p:tavLst>'
            f'<p:tav tm="0"><p:val>{val(start)}</p:val></p:tav><p:tav tm="100000"><p:val>{val(end)}</p:val>'
            f'</p:tav></p:tavLst></p:anim>')


def _effect(cid: int, spid: int, kind: str, delay: int) -> Tuple[str, int]:
    """Bitta shaklning kirish animatsiyasi. Qaytaradi: (xml, ishlatilgan id lar soni)."""
    if kind == "float":        # "Suzib kirish": pastdan biroz ko'tarilib paydo bo'ladi
        preset, sub, dur = 42, 0, 600
        body = (_visible(cid + 1, spid) + _fade(cid + 2, spid, dur)
                + _anim(cid + 3, spid, dur, "ppt_x", "#ppt_x", "#ppt_x")
                + _anim(cid + 4, spid, dur, "ppt_y", "#ppt_y+.05", "#ppt_y"))
        used = 5
    elif kind == "zoom":       # "Kattalashish": nuqtadan o'z o'lchamiga
        preset, sub, dur = 53, 16, 450
        body = (_visible(cid + 1, spid) + _anim(cid + 2, spid, dur, "ppt_w", "0", "#ppt_w")
                + _anim(cid + 3, spid, dur, "ppt_h", "0", "#ppt_h") + _fade(cid + 4, spid, dur))
        used = 5
    else:                      # "Paydo bo'lish"
        preset, sub, dur = 10, 0, 500
        body = _visible(cid + 1, spid) + _fade(cid + 2, spid, dur)
        used = 3
    xml = (f'<p:par><p:cTn id="{cid}" presetID="{preset}" presetClass="entr" presetSubtype="{sub}" fill="hold" '
           f'grpId="0" nodeType="withEffect"><p:stCondLst><p:cond delay="{delay}"/></p:stCondLst><p:childTnLst>'
           f'{body}</p:childTnLst></p:cTn></p:par>')
    return xml, used


def _timing(steps: List[Tuple[int, str, int]], builds: List[str]) -> str:
    inner, cid = [], 5
    for spid, kind, delay in steps:
        xml, used = _effect(cid, spid, kind, delay)
        inner.append(xml)
        cid += used
    bld = f'<p:bldLst>{"".join(builds)}</p:bldLst>' if builds else ""
    return (f'<p:timing {P_NS}><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">'
            f'<p:childTnLst><p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
            f'<p:childTnLst><p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="indefinite"/>'
            f'<p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst>'
            f'<p:par><p:cTn id="4" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
            f'{"".join(inner)}</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn>'
            f'<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
            f'<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>'
            f'</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst>{bld}</p:timing>')


def _has_text(shape) -> bool:
    return bool(shape.has_text_frame and shape.text_frame.text.strip())


def _font_size(shape) -> float:
    """Shakldagi eng katta yozuv o'lchami (pt); o'lcham berilmagan bo'lsa 0."""
    sizes = [r.font.size.pt for p in shape.text_frame.paragraphs for r in p.runs if r.font.size]
    return max(sizes, default=0.0)


def _is_media(el) -> bool:
    return el.find(".//" + qn("a:videoFile")) is not None or el.find(".//" + qn("a:audioFile")) is not None


def _plan(slide, width: int, height: int) -> Tuple[List[Tuple[int, str, int]], List[str]]:
    """Qaysi shakl qanday va qachon chiqadi."""
    order, builds = [], []
    area = width * height
    for shape in slide.shapes:
        el = shape._element
        tag = etree.QName(el).localname
        if tag not in ("sp", "pic", "grpSp") or _is_media(el):
            continue
        try:
            x, y, w, h = int(shape.left), int(shape.top), int(shape.width), int(shape.height)
        except (TypeError, ValueError):
            continue
        if w <= 0 or h <= 0 or w * h >= area * BIG:
            continue
        if x < 0 or y < 0 or x + w > width * 1.002 or y + h > height * 1.002:
            continue
        text = tag == "sp" and _has_text(shape)
        if tag == "pic":
            kind = "fade"
        elif text:
            kind = "float"
        else:
            kind = "zoom" if w * h < area * ZOOM_MAX else "fade"
        top = text and y < height * TITLE_ZONE
        order.append((shape.shape_id, kind, _font_size(shape) if top else 0.0))
        if tag == "sp" and el.find(qn("p:txBody")) is not None:
            builds.append(f'<p:bldP spid="{shape.shape_id}" grpId="0"{"" if text else " animBg=\"1\""}/>')
    # Sarlavha — yuqoridagi eng katta yozuv(lar). Yuqoridagi mayda yozuvlar (masalan reja punktlari) o'z
    # navbatida, o'z shakli bilan chiqadi.
    biggest = max((size for _, _, size in order), default=0.0)
    is_title = [size >= max(biggest * 0.75, TITLE_PT) for _, _, size in order]
    titles = [(spid, kind) for (spid, kind, _), t in zip(order, is_title) if t]
    rest = [(spid, kind) for (spid, kind, _), t in zip(order, is_title) if not t]
    steps = [(spid, kind, 0) for spid, kind in titles]
    start = 350 if titles else 0
    gap = max(GAP_MIN, min(GAP_MAX, SPREAD_MS // max(len(rest), 1)))
    steps += [(spid, kind, start + i * gap) for i, (spid, kind) in enumerate(rest)]
    return steps, builds


def apply(path: str) -> int:
    """`path` dagi taqdimotning har sahifasiga avtomatik kirish animatsiyalarini qo'shadi.

    Qaytaradi: animatsiya qo'shilgan sahifalar soni. Xato bo'lsa fayl o'zgarmaydi.
    """
    prs = Presentation(path)
    width, height = int(prs.slide_width), int(prs.slide_height)
    done = 0
    for slide in prs.slides:
        if slide._element.find(qn("p:timing")) is not None:
            continue
        steps, builds = _plan(slide, width, height)
        if not steps:
            continue
        timing = etree.fromstring(_timing(steps, builds))
        ext = slide._element.find(qn("p:extLst"))
        if ext is not None:                       # p:timing p:extLst dan oldin turadi
            ext.addprevious(timing)
        else:
            slide._element.append(timing)
        done += 1
    prs.save(path)
    log.info("Yozuv animatsiyasi: %d sahifa", done)
    return done
