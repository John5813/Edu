import re
from typing import Any, List, Optional, Literal
from pydantic import BaseModel, field_validator

Role = Literal["hook", "context", "breakdown", "detail", "comparison", "application", "synthesis"]
ROLE_ORDER = ["hook", "context", "breakdown", "detail", "comparison", "application", "synthesis"]


INFOGRAPHIC_PRESETS = ("cards", "steps", "timeline", "cycle", "pyramid")


# Model ba'zan matnni HTML bilan bezaydi: "<b>Samaradorlik:</b> ...".
# PowerPoint uni teg deb tanimaydi va mijoz slaydda qavslarni o'qiydi.
# Faqat ma'lum teglar olib tashlanadi — "E > 1" yoki "x < y" kabi
# ifodalar matnda uchraydi va ular tegilmasligi kerak.
_TAG_RE = re.compile(
    r"</?(?:b|i|u|s|em|strong|span|p|br|div|ul|ol|li|h[1-6])\s*/?>",
    re.IGNORECASE,
)


def strip_markup(value: Any) -> Any:
    """Matndagi HTML bezaklarini olib tashlaydi, qolganini tegmaydi."""
    if not isinstance(value, str) or "<" not in value and "&" not in value:
        return value
    cleaned = _TAG_RE.sub("", value)
    cleaned = cleaned.replace("&nbsp;", " ").replace("&quot;", '"')
    cleaned = cleaned.replace("&lt;", "<").replace("&gt;", ">")
    cleaned = cleaned.replace("&amp;", "&")     # oxirida: qayta ochilmasin
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


class CleanText(BaseModel):
    """Matn maydonlari HTML bezaklaridan tozalanadigan model.

    Tozalash shu yerda turadi, chunki matn modelga faqat shu yo'l bilan
    kiradi: LLM javobi ham, vizual QA tuzatishlari ham.
    """

    @field_validator("*", mode="before")
    @classmethod
    def _drop_markup(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [strip_markup(item) for item in value]
        return strip_markup(value)


class InfographicItem(CleanText):
    """Infografikaning bitta bandi — mazmun; koordinatani kod hisoblaydi."""
    title: str = ""
    text: str = ""
    icon: Optional[str] = None
    value: Optional[str] = None   # timeline uchun yil, steps uchun raqam


class VisualElement(CleanText):
    """Slayddagi bitta vizual element."""
    type: Literal["rect", "text", "circle", "image", "chart", "kpi", "icon",
                  "infographic", "scheme"]
    x: float
    y: float
    w: Optional[float] = None
    h: Optional[float] = None
    # rect / circle rangi
    fill: Optional[str] = None
    radius: bool = False
    # matn
    text: Optional[str] = None
    size: float = 14
    bold: bool = False
    italic: bool = False
    color: Optional[str] = None
    align: Literal["left", "center", "right"] = "left"
    font: str = "Calibri"
    # circle — d bilan aylana, w/h bilan ellips; `line` faqat kontur chizadi
    d: Optional[float] = None
    line: Optional[str] = None
    # image
    prompt: Optional[str] = None
    # kpi — ko'rsatkich kartochkasi (katta raqam + izoh)
    value: Optional[str] = None
    label: Optional[str] = None
    # icon — lokal ikonka: `icon` nomi, `shape` fon shakli
    icon: Optional[str] = None
    shape: Literal["circle", "square", "none"] = "circle"
    # infographic — preset + bandlar; kod uni ibtidoiy elementlarga yoyadi
    preset: Optional[Literal["cards", "steps", "timeline", "cycle", "pyramid"]] = None
    items: Optional[List[InfographicItem]] = None
    # scheme — tuzilma sxemasi (loyiha ishidagi bilan bir xil chizuvchi).
    # Shakl `scheme_kind` va mavzudan tanlanadi: daraxt, radial, oqim,
    # halqa, bosqichlar... Bandlar `items` da: `title` — tarmoq nomi,
    # `text` — uning tarkibi (vergul bilan).
    scheme_kind: Optional[Literal["hierarchy", "components", "process",
                                  "cycle", "levels"]] = None
    scheme_root: Optional[str] = None
    # kod hosil qilgan element: ustma-ustlik tuzatuvchisi unga tegmaydi
    locked: bool = False
    # shrifti sig'dirish uchun ataylab kichraytirilgan: minimal o'lcham
    # kafolati uni qaytarib kattalashtirmasligi kerak, aks holda matn yana
    # qutidan toshib, quyidagi blok ustiga minib qoladi
    fitted: bool = False
    # chart
    chart_type: Optional[Literal["bar", "column", "line", "area", "pie",
                                 "donut", "radar", "scatter"]] = None
    chart_title: Optional[str] = None
    caption: Optional[str] = None   # diagramma ostida ko'rsatiladigan izoh matni
    categories: Optional[List[str]] = None
    series: Optional[List[Any]] = None   # [{"name": str, "values": [float, ...]}]


class Theme(BaseModel):
    primary: str
    accent: str
    light: str
    heading_font: str = "Calibri"
    body_font: str = "Calibri"


class SlideCanvas(BaseModel):
    background: str
    elements: List[VisualElement]


class Slide(CleanText):
    index: int
    role: Role
    title: str
    key_text: str

    canvas: SlideCanvas

    def all_text(self) -> str:
        parts = [self.title, self.key_text]
        for el in (self.canvas.elements or []):
            if el.type == "text" and el.text:
                parts.append(el.text)
        return " ".join([p for p in parts if p])


class Brief(CleanText):
    topic: str
    theme: Theme
    slides: List[Slide]

    @field_validator("slides")
    @classmethod
    def check_roles(cls, slides: List[Slide]):
        if not slides:
            raise ValueError("Slaydlar ro'yxati bo'sh")
        if slides[0].role != "hook":
            raise ValueError("Birinchi slayd role='hook' bo'lishi shart")
        if slides[-1].role != "synthesis":
            raise ValueError("Oxirgi slayd role='synthesis' bo'lishi shart")
        last_rank = -1
        for s in slides:
            rank = ROLE_ORDER.index(s.role)
            if rank < last_rank:
                raise ValueError(
                    f"Role tartibi buzilgan: slayd {s.index} ({s.role}) oldingi roledan orqada"
                )
            last_rank = rank
        return slides


GROUNDING_PATTERN = re.compile(r"\d|(?:[A-ZЎҚҲЁ][a-zʻ'']+\s+[A-ZЎҚҲЁ][a-zʻ'']+)")


def grounding_check(slide: Slide) -> bool:
    if slide.role not in ("detail", "comparison"):
        return True
    return bool(GROUNDING_PATTERN.search(slide.all_text()))
