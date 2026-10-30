"""3D taqdimot uslublari va kompozitsiyalari.

Uslublar 3D Anatomiya dizayn tizimidan (`services.med3d.design`) olinadi — fon gradienti, shriftlar, ranglar,
Morph bilan suriladigan fon bezaklari, 3D yorug'ligi. Tibbiyotga xoslari (rentgen, laboratoriya) olinmaydi.
Uslubni AI mavzuga qarab tanlaydi (tarix — muzey vitrinasi, tabiat — zumrad, koinot — tungi va h.k.).
"""
from services.med3d.design import STYLES as _ALL

STYLE_GUIDE = {
    "vitrina": "museum showcase: black with gold — history, archaeology, artefacts, sculpture",
    "atlas": "old book: warm parchment, serif — history, culture, literature, old maps",
    "klinik": "deep night blue — space, astronomy, physics, modern science",
    "kobalt": "bright cobalt blue — technology, inventions, transport, engineering",
    "zumrad": "dark emerald — nature, plants, animals, ecology",
    "okean": "deep sea teal — oceans, sea life, water, geography, travel",
    "grafit": "graphite with orange — machines, industry, vehicles, tools",
    "shafaq": "sunset purple and gold — art, music, architecture, culture",
    "pastel": "soft pastel — food, flowers, everyday life, gentle topics",
    "oq": "clean white minimal — any subject, modern and calm",
}
STYLES = {k: _ALL[k] for k in STYLE_GUIDE if k in _ALL}
BY_FAN = {"tarix": "vitrina", "san'at": "shafaq", "arxitektura": "shafaq", "biologiya": "zumrad",
          "geografiya": "okean", "astronomiya": "klinik", "fizika": "klinik", "kimyo": "oq", "texnika": "grafit",
          "informatika": "kobalt", "transport": "kobalt", "musiqa": "shafaq", "oshxona": "pastel",
          "sport": "kobalt", "tibbiyot": "oq", "adabiyot": "atlas", "matematika": "oq"}
LAYOUTS = ("muqova", "matn", "chap", "ong", "xronologiya", "taqqoslash", "kartalar", "bosqichlar", "fikr", "savol",
           "raqamlar", "qahramon", "uchlik", "yakun")


def style_guide() -> str:
    return "\n".join(f"- {k}: {v}" for k, v in STYLE_GUIDE.items() if k in STYLES)
