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


def group_parts(scene: str, group: str) -> List[str]:
    return [name for _, names in SCENES[scene]["groups"][group]["materials"] for name in names]
