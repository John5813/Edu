"""Vektor dizayner: kam matnli taqdimot sahifalarini PowerPoint'ning haqiqiy shakllari bilan chizadi.

Qanday ishlaydi:
1. AI avvalgidek kompozitsiya qolipiga matn yozadi (reja, so'z chegarasi, rasmlar — o'zgarmaydi).
2. PPTX yig'ilayotganda har sahifa uchun `Designer.draw` chaqiriladi: sahifa mazmuni o'qiladi
   (`parse.spec_of`) va AQLLI TANLOVCHI uslub tanlaydi.
3. Tanlov: mazmun turi (muqova, reja, rasmli, guruh, ketma-ketlik, raqamlar, qiyos, xulosa) va punktlar
   soniga mos uslublar orasidan tasodifiy, lekin
   - ketma-ket ikki slayd bir xil uslubda bo'lmaydi;
   - kam ishlatilgan uslub afzal (bitta uslub taqdimotni egallab olmaydi);
   - eski HTML kompozitsiyalar ham tanlov ichida (yangi uslublar ularga QO'SHIMCHA) — bunday
     sahifa avvalgidek HTML dan chiziladi.
   Tasodif mavzuga bog'langan (`families`): fan oilasi va mavzu obrazi (tabiat, texnika, biznes, ta'lim,
   tibbiyot, madaniyat, sayohat) mos uslublarni ko'proq chiqaradi, mos kelmaydiganini (masalan, moliyada
   barglar) umuman chiqarmaydi. Ranglar mavzuga qarab tanlangan temadan olinadi. Tasodif urug'i (`seed`) taqdimotda saqlanadi:
   saytda sahifa qayta yig'ilganda ham uslublar o'zgarmaydi.
"""
import logging
import random
from typing import Dict, Optional

from . import families, kit, parse, styles

log = logging.getLogger(__name__)

# "Eski kompozitsiya" (HTML) tanlovdagi og'irligi: yangi uslublarning bittasiga nisbatan. Raqamlar — 0:
# eski kompozitsiyada katta raqam ("1,2 mlrd") telefonning kengroq shriftida ikki qatorga bo'linardi.
OLD_WEIGHT = {"cover": 0.0, "plan": 0.0, "photo": 1.2, "group": 2.5, "sequence": 1.5, "numbers": 0.0,
              "compare": 0.6, "finale": 0.5}
# Muqovadagi va rejadagi yangi uslublar har doim ishlatiladi (birinchi to'rt uslub — faqat shular uchun).
OLD = "html"


class Designer:
    def __init__(self, theme, topic: str = "", seed: Optional[int] = None, family: str = ""):
        self.theme = theme
        self.topic = topic or ""
        self.family = family or ""
        # Oila va obraz: mavzuga mos uslublar ko'proq chiqadi, mos kelmaydiganlari umuman chiqmaydi.
        self.mult = families.multipliers(self.family, self.topic)
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.pal = styles.Palette.of(theme)
        self.uses: Dict[str, int] = {}
        self.last = ""
        self.cover: Optional[kit.Photo] = None
        self.used_icons: set = set()
        self.topic_icon = self._topic_icon()
        self.chosen: list = []

    def _topic_icon(self) -> str:
        try:
            from .. import html_slides

            return html_slides._pick_icon([self.topic], set())
        except Exception:
            return "globe"

    # ─────────────────────────────── tanlov

    def choose(self, spec: Dict) -> str:
        kind = spec["kind"]
        n = len(spec.get("items") or spec.get("sides") or [])
        options = [s for s in styles.STYLES if kind in s.kinds and (kind in ("cover", "photo", "compare", "finale")
                                                                    or s.min_items <= n <= s.max_items)]
        fitting = [s for s in options if self.mult.get(s.name, 1.0) > 0]
        if fitting:
            options = fitting
        weights = [self.mult.get(s.name, 1.0) / (1 + self.uses.get(s.name, 0)) ** 2 if fitting
                   else 1.0 / (1 + self.uses.get(s.name, 0)) ** 2 for s in options]
        names = [s.name for s in options]
        old = OLD_WEIGHT.get(kind, 0.0)
        if spec.get("old_ok", True) and old:
            names.append(OLD)
            weights.append(old / (1 + self.uses.get(OLD + kind, 0)))
        if len(names) > 1 and self.last in names:
            i = names.index(self.last)
            names.pop(i); weights.pop(i)
        if not names:
            return OLD
        pick = self.rng.choices(names, weights=weights, k=1)[0]
        self.uses[pick if pick != OLD else OLD + kind] = self.uses.get(pick if pick != OLD else OLD + kind, 0) + 1
        self.last = pick
        return pick

    # ─────────────────────────────── chizish

    def draw(self, presentation, page: str, index: int, total: int) -> bool:
        """Sahifani vektor uslubda chizadi. False — sahifa avvalgidek HTML dan chizilsin."""
        try:
            spec = parse.spec_of(page, index, total)
        except Exception as exc:
            log.warning("%d-sahifa mazmuni o'qilmadi: %s", index + 1, exc)
            return False
        if spec is None:
            self.chosen.append(OLD)
            self.last = OLD
            return False
        photo = None
        raw = spec.get("photo")
        if raw:
            try:
                photo = kit.Photo(raw)
            except Exception as exc:
                log.warning("%d-sahifa rasmi o'qilmadi: %s", index + 1, exc)
        if spec["kind"] == "cover" and photo is not None:
            self.cover = photo
        # Eski kompozitsiya ham tanlovda, lekin: "butun fon rasm + oq karta" endi chiqmaydi, 4 tadan ko'p
        # punktli eski kartalar esa torayib so'zlari bo'linadi — bunday sahifa doim yangi uslubda.
        if spec["kind"] == "photo" and spec.get("layout") == "rasm_fon":
            spec["old_ok"] = False
        if len(spec.get("items") or []) > 4:
            spec["old_ok"] = False
        name = self.choose(spec)
        self.chosen.append(name)
        if name == OLD:
            return False
        spec["photo_obj"] = photo
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        ctx = styles.Ctx(slide=slide, pal=self.pal, rng=self.rng, used_icons=self.used_icons, photo=photo,
                         cover=self.cover, topic_icon=self.topic_icon)
        try:
            styles.BY_NAME[name].draw(ctx, spec)
        except Exception as exc:
            log.warning("%d-sahifa %s uslubida chizilmadi (%s) — HTML dan chiziladi", index + 1, name, exc)
            _drop_last(presentation)
            return False
        finally:
            if photo is not None and photo is not self.cover:
                photo.cleanup()
        log.info("%d-sahifa: %s uslubi", index + 1, name)
        return True

    def close(self) -> None:
        if self.cover is not None:
            self.cover.cleanup()


def _drop_last(presentation) -> None:
    ids = presentation.slides._sldIdLst
    last = ids[-1]
    presentation.part.drop_rel(last.rId)
    ids.remove(last)
