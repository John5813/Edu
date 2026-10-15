"""Tibbiy 3D sahnalar katalogi: qaysi atlas qismlari qaysi guruhga kiradi va ularning o'zbekcha nomlari.

Sahna (masalan "skull") — bir koordinata tizimidagi bir nechta guruh (masalan "cranium" va
"mandible"). Har guruh alohida GLB bo'ladi: PowerPoint Morph bitta modelni bo'laklarga ajrata olmaydi,
shuning uchun "tepasi ajralib chiqib ketadi" effekti ikki alohida model bilan qilinadi.

Yorliqlar (`labels`) — slaydda chiziq bilan ko'rsatiladigan qismlar. Kalit (masalan "frontal") AI
rejasida ishlatiladi; `parts` — atlasdagi aniq nomlar (yorliq nuqtasi shu qismlar ustiga tushadi).
"""
from typing import Dict, List

BONE = (0.89, 0.85, 0.75)
TOOTH = (0.97, 0.96, 0.91)
CARTILAGE = (0.80, 0.86, 0.90)

_UPPER_TEETH = [f"{side} upper {t}" for side in ("Left", "Right") for t in (
    "central secondary incisor tooth", "lateral secondary incisor tooth", "secondary canine tooth",
    "first secondary premolar tooth", "second secondary premolar tooth",
    "first secondary molar tooth", "second secondary molar tooth")]
_LOWER_TEETH = [n.replace(" upper ", " lower ") for n in _UPPER_TEETH]

SCENES: Dict[str, dict] = {
    "skull": {
        "uz": "Bosh suyagi",
        "groups": {
            "cranium": {
                "uz": "Miya va yuz suyaklari",
                "materials": [
                    (BONE, ["Frontal bone", "Left parietal bone", "Right parietal bone", "Occipital bone",
                            "Left temporal bone", "Right temporal bone", "Sphenoid bone", "Ethmoid",
                            "Left maxilla", "Right maxilla", "Left zygomatic bone", "Right zygomatic bone",
                            "Left nasal bone", "Right nasal bone", "Left palatine bone", "Right palatine bone",
                            "Vomer", "Left lacrimal bone", "Right lacrimal bone",
                            "Left inferior nasal concha", "Right inferior nasal concha"]),
                    (TOOTH, _UPPER_TEETH),
                ],
            },
            "mandible": {
                "uz": "Pastki jag'",
                "materials": [(BONE, ["Mandible"]), (TOOTH, _LOWER_TEETH)],
            },
        },
        "labels": {
            "frontal": ("Peshona suyagi", ["Frontal bone"]),
            "parietal_l": ("Tepa suyagi", ["Left parietal bone"]),
            "parietal_r": ("Tepa suyagi", ["Right parietal bone"]),
            "occipital": ("Ensa suyagi", ["Occipital bone"]),
            "temporal_l": ("Chakka suyagi", ["Left temporal bone"]),
            "temporal_r": ("Chakka suyagi", ["Right temporal bone"]),
            "sphenoid": ("Ponasimon suyak", ["Sphenoid bone"]),
            "zygomatic_l": ("Yonoq suyagi", ["Left zygomatic bone"]),
            "zygomatic_r": ("Yonoq suyagi", ["Right zygomatic bone"]),
            "nasal": ("Burun suyagi", ["Left nasal bone", "Right nasal bone"]),
            "maxilla_l": ("Yuqori jag' suyagi", ["Left maxilla"]),
            "maxilla_r": ("Yuqori jag' suyagi", ["Right maxilla"]),
            "upper_teeth": ("Yuqori tishlar", _UPPER_TEETH),
            "mandible": ("Pastki jag' suyagi", ["Mandible"]),
            "incisors_lower": ("Kesuv tishlar", ["Left lower central secondary incisor tooth",
                                                 "Right lower central secondary incisor tooth",
                                                 "Left lower lateral secondary incisor tooth",
                                                 "Right lower lateral secondary incisor tooth"]),
            "canine_lower_l": ("Qoziq tish", ["Left lower secondary canine tooth"]),
            "canine_lower_r": ("Qoziq tish", ["Right lower secondary canine tooth"]),
            "premolars_lower_l": ("Kichik oziq tishlar", ["Left lower first secondary premolar tooth",
                                                          "Left lower second secondary premolar tooth"]),
            "premolars_lower_r": ("Kichik oziq tishlar", ["Right lower first secondary premolar tooth",
                                                          "Right lower second secondary premolar tooth"]),
            "molars_lower_l": ("Katta oziq tishlar", ["Left lower first secondary molar tooth",
                                                      "Left lower second secondary molar tooth"]),
            "molars_lower_r": ("Katta oziq tishlar", ["Right lower first secondary molar tooth",
                                                      "Right lower second secondary molar tooth"]),
        },
    },
}


TONGUE = (0.80, 0.42, 0.44)
GLAND = (0.93, 0.79, 0.52)
GUT = (0.89, 0.58, 0.52)
STOMACH = (0.86, 0.50, 0.46)
LIVER = (0.52, 0.20, 0.17)
BILE = (0.36, 0.60, 0.30)
PANCREAS = (0.94, 0.77, 0.48)
DUODENUM = (0.90, 0.63, 0.44)
SMALL = (0.93, 0.67, 0.60)
LARGE = (0.74, 0.50, 0.40)

_JEJUNUM = ["Proximal part of jejunum", "Middle part of jejunum", "Distal part of jejunum"]
_ILEUM = ["Proximal part of ileum", "Middle part of ileum", "Distal part of ileum", "Ileocecal junction"]
# Jigar to'qimasi atlasda Couinaud segmentlari ("Hepatovenous segment ...") va dum bo'lagi sifatida.
# VI/VII va VIII/IX juftliklari bir xil chegarali takror bo'laklar — har biridan bittasi olinadi.
_LIVER = ["Caudate lobe of liver", "Hepatovenous segment II", "Hepatovenous segment III",
          "Hepatovenous segment IV", "Hepatovenous segment V", "Hepatovenous segment VI", "FJ2823", "FJ2824"]

SCENES["digestive"] = {
    "uz": "Hazm qilish organlari",
    "groups": {
        # Yuqori tishlar alohida: og'iz slaydida ularsiz til va bezlar yuqoridan ko'rinadi.
        "ogiz": {"uz": "Og'iz bo'shlig'i", "materials": [
            (TONGUE, ["Tongue"]),
            (GLAND, ["Left sublingual gland", "Right sublingual gland",
                     "Left submandibular gland", "Right submandibular gland"]),
            (TOOTH, _LOWER_TEETH)]},
        "tish_yuqori": {"uz": "Yuqori tishlar", "materials": [(TOOTH, _UPPER_TEETH)]},
        "qizilongach": {"uz": "Qizilo'ngach", "materials": [(GUT, ["Esophagus"])]},
        "oshqozon": {"uz": "Oshqozon", "materials": [(STOMACH, ["Stomach"])]},
        "jigar": {"uz": "Jigar", "materials": [(LIVER, _LIVER)]},
        "ot": {"uz": "O't pufagi", "materials": [(BILE, ["Gallbladder", "Cystic duct", "Common hepatic duct"])]},
        "oshqozon_osti": {"uz": "Oshqozon osti bezi", "materials": [(PANCREAS, ["Pancreas"])]},
        "duodenum": {"uz": "O'n ikki barmoq ichak", "materials": [(DUODENUM, ["Duodenum"])]},
        "ingichka": {"uz": "Ingichka ichak", "materials": [(SMALL, _JEJUNUM + _ILEUM)]},
        "yogon": {"uz": "Yo'g'on ichak", "materials": [(LARGE, [
            "Ascending colon", "Transverse colon", "Descending colon", "Appendix", "Rectum"])]},
    },
    "labels": {
        "til": ("Til", ["Tongue"]),
        "tishlar": ("Tishlar", _LOWER_TEETH),
        "til_osti": ("Til osti bezi", ["Left sublingual gland", "Right sublingual gland"]),
        "jag_osti": ("Jag' osti bezi", ["Left submandibular gland", "Right submandibular gland"]),
        "qizilongach": ("Qizilo'ngach", ["Esophagus"]),
        "oshqozon": ("Oshqozon", ["Stomach"]),
        "jigar": ("Jigar", _LIVER),
        "ot_pufagi": ("O't pufagi", ["Gallbladder"]),
        "pufak_yoli": ("Pufak yo'li", ["Cystic duct"]),
        "jigar_yoli": ("Umumiy jigar yo'li", ["Common hepatic duct"]),
        "oshqozon_osti": ("Oshqozon osti bezi", ["Pancreas"]),
        "duodenum": ("O'n ikki barmoq ichak", ["Duodenum"]),
        "och_ichak": ("Och ichak", _JEJUNUM),
        "yonbosh_ichak": ("Yonbosh ichak", _ILEUM),
        "kotariluvchi": ("Ko'tariluvchi ichak", ["Ascending colon"]),
        "kondalang": ("Ko'ndalang ichak", ["Transverse colon"]),
        "tushuvchi": ("Tushuvchi ichak", ["Descending colon"]),
        "appendiks": ("Appendiks", ["Appendix"]),
        "togri_ichak": ("To'g'ri ichak", ["Rectum"]),
    },
}


def _subset(base: str, uz: str, groups: List[str]) -> dict:
    """Katta sahnaning bir qismi — o'z chegara qutisi bilan: mayda organlar yaqinroq ko'rinadi."""
    src = SCENES[base]
    names = {n for g in groups for _, ns in src["groups"][g]["materials"] for n in ns}
    return {"uz": uz, "groups": {g: src["groups"][g] for g in groups},
            "labels": {k: v for k, v in src["labels"].items() if v[1][0] in names}}


# Og'izdan to'g'ri ichakkacha ~73 sm: bitta sahnada o't pufagi kabi mayda organni kattalashtirib
# bo'lmaydi (ramka slayddan bir necha barobar katta bo'lib ketadi). Shuning uchun qo'shimcha sahnalar.
SCENES["digestive_head"] = _subset("digestive", "Og'iz bo'shlig'i", ["ogiz", "tish_yuqori"])
SCENES["digestive_abdomen"] = _subset("digestive", "Qorin bo'shlig'i a'zolari", [
    "oshqozon", "jigar", "ot", "oshqozon_osti", "duodenum", "ingichka", "yogon"])


def group_parts(scene: str, group: str) -> List[str]:
    return [name for _, names in SCENES[scene]["groups"][group]["materials"] for name in names]
