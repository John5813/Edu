"""Formulani o'qiladigan ko'rinishga keltiradi.

Matematika, fizika va iqtisod mavzularida model formulani deyarli
har doim LaTeX bilan yozadi — u shunday o'rgatilgan:

    "$1/n$ ketma-ketligi", "$x \\to \\infty$", "$x^n$ uchun $nx^{n-1}$"

Brauzerda LaTeX ni hech kim o'qib bermaydi, shuning uchun bu matn
slaydga AYNAN shu ko'rinishda — dollar belgilari va teskari chiziqlar
bilan tushardi. Slaydda "$nx^{n-1}$" deb turgan formula esa mijoz
uchun xato.

Shu modul LaTeX ni Unicode belgilariga o'giradi:

    $nx^{n-1}$   →   nxⁿ⁻¹
    $x \\to \\infty$  →   x → ∞
    \\frac{a}{b}  →   ustma-ust yozilgan kasr (HTML bilan)
    \\sqrt{x}     →   √(x)

Kasr HTML bilan chiziladi, chunki ustma-ust yozilgan surat va maxraj
PowerPointda ham shunday ko'rinishi kerak. Qolgani Unicode: u oddiy
matn bo'lgani uchun PowerPointda tahrirlanadi va hech qayerda
buzilmaydi.
"""

import logging
import re

log = logging.getLogger("deck_math")

# Buyruq → belgi. Ro'yxat uzun emas: taqdimotda uchraydigan
# formulalar oddiy bo'ladi.
_WORDS = {
    r"\to": "→", r"\rightarrow": "→", r"\leftarrow": "←",
    r"\Rightarrow": "⇒", r"\Leftarrow": "⇐", r"\leftrightarrow": "↔",
    r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇",
    r"\times": "×", r"\cdot": "·", r"\div": "÷", r"\pm": "±", r"\mp": "∓",
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥",
    r"\neq": "≠", r"\ne": "≠", r"\approx": "≈", r"\equiv": "≡",
    r"\sim": "∼", r"\propto": "∝",
    r"\sum": "∑", r"\prod": "∏", r"\int": "∫", r"\iint": "∬",
    r"\in": "∈", r"\notin": "∉", r"\subset": "⊂", r"\supset": "⊃",
    r"\cup": "∪", r"\cap": "∩", r"\emptyset": "∅",
    r"\forall": "∀", r"\exists": "∃", r"\therefore": "∴",
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ε", r"\varepsilon": "ε", r"\zeta": "ζ", r"\eta": "η",
    r"\theta": "θ", r"\lambda": "λ", r"\mu": "μ", r"\nu": "ν",
    r"\xi": "ξ", r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ",
    r"\tau": "τ", r"\phi": "φ", r"\varphi": "φ", r"\chi": "χ",
    r"\psi": "ψ", r"\omega": "ω",
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ",
    r"\Sigma": "Σ", r"\Phi": "Φ", r"\Psi": "Ψ", r"\Omega": "Ω",
    r"\ldots": "…", r"\dots": "…", r"\cdots": "⋯",
    r"\prime": "′", r"\degree": "°", r"\angle": "∠",
    r"\lim": "lim", r"\log": "log", r"\ln": "ln", r"\exp": "exp",
    r"\sin": "sin", r"\cos": "cos", r"\tan": "tan", r"\cot": "cot",
    r"\max": "max", r"\min": "min", r"\det": "det", r"\dim": "dim",
    # Joy tashlaydigan va ko'rinmaydigan buyruqlar.
    r"\left": "", r"\right": "", r"\displaystyle": "", r"\text": "",
    r"\mathrm": "", r"\mathbf": "", r"\quad": " ", r"\qquad": "  ",
}

_SUP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵",
    "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻",
    "−": "⁻", "=": "⁼", "(": "⁽", ")": "⁾", "n": "ⁿ", "i": "ⁱ",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "f": "ᶠ",
    "g": "ᵍ", "h": "ʰ", "j": "ʲ", "k": "ᵏ", "l": "ˡ", "m": "ᵐ",
    "o": "ᵒ", "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ",
    "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ", " ": " ",
}

_SUB = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅",
    "6": "₆", "7": "₇", "8": "₈", "9": "₉", "+": "₊", "-": "₋",
    "−": "₋", "=": "₌", "(": "₍", ")": "₎", "a": "ₐ", "e": "ₑ",
    "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ", "m": "ₘ",
    "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ",
    "u": "ᵤ", "v": "ᵥ", "x": "ₓ", " ": " ",
}

_MATH = re.compile(r"\$\$(.+?)\$\$|\$([^$]+)\$|\\\((.+?)\\\)|\\\[(.+?)\\\]",
                   re.DOTALL)
_TAGS = re.compile(r"(<[^>]+>)")
_COMMAND = re.compile(r"\\([a-zA-Z]+)")

# Harf ustidagi belgi: \bar{x} → x̄ (o'rtacha), \hat{y} → ŷ (baho).
_ACCENTS = {"bar": "\u0304", "overline": "\u0304", "hat": "\u0302",
            "widehat": "\u0302", "tilde": "\u0303", "widetilde": "\u0303",
            "vec": "\u20d7", "dot": "\u0307", "ddot": "\u0308"}
# Ichidagi matn o'zi qoladigan buyruqlar.
_KEEP = {"text", "textrm", "textbf", "textit", "mathrm", "mathbf", "mathit",
         "mathsf", "mathcal", "mathbb", "boldsymbol", "operatorname", "mbox"}
# Faqat o'lcham yoki joy bildiradigan buyruqlar — tashlanadi.
_SKIP = {"left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr",
         "Bigl", "Bigr", "displaystyle", "textstyle", "limits", "nolimits"}
# `\%`, `\,` kabi bir belgili buyruqlar.
_ESCAPES = {"%": "%", "{": "{", "}": "}", "$": "$", "&": "&", "#": "#",
            "_": "_", ",": " ", ";": " ", ":": " ", "!": "", " ": " ",
            "\\": " ", "|": "‖"}
_SIMPLE = re.compile(r"[\w\u0300-\u036f\u20d7\u2070-\u209f.′]+")


def _group(text: str, i: int):
    """`i` dan boshlanadigan argument: `{...}` (ichma-ich qavslar
    hisobga olinadi), buyruq yoki bitta belgi. (mazmun, keyingi o'rin)."""
    n = len(text)
    while i < n and text[i] == " ":
        i += 1
    if i >= n:
        return "", i
    if text[i] == "{":
        depth = 0
        for j in range(i, n):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    return text[i + 1:j], j + 1
        return text[i + 1:], n
    if text[i] == "\\":
        match = _COMMAND.match(text, i)
        if match:
            return match.group(0), match.end()
        return text[i:i + 2], i + 2
    return text[i], i + 1


def _wrap(text: str) -> str:
    """Oddiy bo'lmagan ifoda qavsga olinadi: a+b → (a+b)."""
    return text if _SIMPLE.fullmatch(text) else f"({text})"


def _accent(text: str, mark: str) -> str:
    return "".join(char + mark if char.isalnum() else char for char in text)


# Yuqori/quyi shakli yo'q, lekin indeks ichida ma'nosi o'zgarmaydigan
# belgilar. Ilgari bittasi uchrasa butun indeks oddiy matnga tushib,
# mediana formulasidagi x_{(n+1)/2} "x ((n+1)/2)" bo'lib qolardi.
_NEUTRAL = {"/": "⁄", ",": ",", ".": ".", "'": "′"}


def _scripted(mark: str, body: str) -> str:
    """Daraja yoki indeksni yuqori/quyi belgiga o'giradi.

    Qisqa indeks (x_i, P_x, x_{n+1}) Unicode quyi belgi bo'ladi. So'zli
    indeks (A_{o'sish}) esa o'qib bo'lmas "ₒ′ₛᵢₛₕ" bo'lib qolardi — u
    "A_(o'sish)" deb yoziladi.
    """
    if mark == "_" and sum(char.isalpha() for char in body) > 3:
        return "_(" + body + ")"
    table = _SUP if mark == "^" else _SUB
    if "<" not in body and any(char in table for char in body) and all(
            char in table or char in _NEUTRAL for char in body):
        return "".join(table.get(char) or _NEUTRAL[char] for char in body)
    if mark == "^":
        return "^" + _wrap(body)
    return " (" + body + ")"


def _convert(text: str, depth: int = 0) -> str:
    out = []
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char == "\\":
            match = _COMMAND.match(text, i)
            if not match:
                nxt = text[i + 1:i + 2]
                out.append(_ESCAPES.get(nxt, nxt))
                i += 2
                continue
            name = match.group(1)
            i = match.end()
            if name in ("frac", "dfrac", "tfrac", "cfrac"):
                up, i = _group(text, i)
                down, i = _group(text, i)
                up, down = _convert(up, depth + 1), _convert(down, depth + 1)
                # Tashqi kasr ustma-ust chiziladi; ichidagisi qator
                # ichida qoladi — ustma-ust kasr ichida yana ustma-ust
                # kasr PowerPointda o'qib bo'lmaydi.
                out.append(_fraction(up, down) if depth == 0
                           else f"{_wrap(up)}/{_wrap(down)}")
            elif name == "sqrt":
                index = ""
                j = i
                while j < n and text[j] == " ":
                    j += 1
                if j < n and text[j] == "[":
                    close = text.find("]", j)
                    if close > 0:
                        index, i = text[j + 1:close].strip(), close + 1
                body, i = _group(text, i)
                # Ildiz ostidagi yolg'iz kasr ham ustma-ust chiziladi.
                inner = _convert(body, depth)
                sign = {"3": "∛", "4": "∜"}.get(index, "√")
                alone = (inner.startswith('<span class="frac">')
                         and inner.count('class="frac"') == 1
                         and inner.endswith("</span></span>"))
                if "<" in inner and not alone:
                    inner = _convert(body, depth + 1)
                out.append(sign + (inner if alone or _SIMPLE.fullmatch(inner)
                                   else f"({inner})"))
            elif name in _BIG_OPS and depth == 0 and _has_limits(text, i):
                # ∑ va ∏ chegaralari bilan: pastki va yuqori chegara belgining ostida va ustida turadi.
                # Ilgari ular belgidan keyin mayda indeks bo'lib, "∑ᵢ₌₁ⁿ" qiyshiq chiqardi.
                lower = upper = ""
                for _ in range(2):
                    j = i
                    while j < n and text[j] == " ":
                        j += 1
                    if j < n and text[j] in "_^":
                        body, i = _group(text, j + 1)
                        if text[j] == "_":
                            lower = _convert(body, depth + 1)
                        else:
                            upper = _convert(body, depth + 1)
                out.append(_big_operator(_WORDS["\\" + name], lower, upper))
            elif name in _ACCENTS:
                body, i = _group(text, i)
                out.append(_accent(_convert(body, depth + 1), _ACCENTS[name]))
            elif name in _KEEP:
                body, i = _group(text, i)
                out.append(_convert(body, depth))
            elif name in _SKIP:
                if name in ("left", "right") and text[i:i + 1] == ".":
                    i += 1
            else:
                out.append(_WORDS.get("\\" + name, ""))
        elif char in "^_":
            body, i = _group(text, i + 1)
            out.append(_scripted(char, _convert(body, depth + 1)))
        elif char in "{}":
            i += 1
        else:
            out.append(char)
            i += 1
    return "".join(out)


_BIG_OPS = ("sum", "prod")


def _has_limits(text: str, i: int) -> bool:
    while i < len(text) and text[i] == " ":
        i += 1
    return i < len(text) and text[i] in "_^"


def _big_operator(sign: str, lower: str, upper: str) -> str:
    """Chegarali yig'indi/ko'paytma: yuqori chegara, belgi, pastki chegara — ustma-ust.

    Kasr kabi (`frac`) alohida elementlar: chizuvchi ularni PowerPointda ham ustma-ust qo'yadi.
    """
    return (f'<span class="frac op"><span class="up">{upper.strip()}</span>'
            f'<span class="mid">{sign}</span><span class="dn">{lower.strip()}</span></span>')


def _fraction(numerator: str, denominator: str) -> str:
    """Ustma-ust yoziladigan kasr.

    Surat va maxraj alohida element bo'ladi: chizuvchi ularni
    PowerPointda ham ustma-ust qo'yadi, oraliqdagi chiziq esa
    alohida tasma bo'lib chiqadi.
    """
    return (f'<span class="frac"><span class="up">{numerator.strip()}</span>'
            f'<span class="dn">{denominator.strip()}</span></span>')


# Model ba'zan teskari chiziqni ikki marta yozadi ("\\\\frac", "\\\\times"): JSON
# qochirishidan qolgan. LaTeX da "\\\\" + harf deyarli uchramaydi, shuning uchun
# buyruq deb o'qiladi; aks holda "\\\\frac" qator ko'chirish bo'lib, "fracDP times"
# yozuvi chiqardi.
_DOUBLED = re.compile(r"\\\\(?=[A-Za-z])")


def _undouble(text: str) -> str:
    return _DOUBLED.sub(lambda _: "\\", str(text or ""))


def formula(text: str) -> str:
    """Bitta formulani belgilarga o'giradi.

    Argumentlar ichma-ich qavslar bilan to'g'ri o'qiladi: ilgari
    `\\frac{\\sum_{i=1}^{n} x_i}{n}` kasr deb tanilmay, "∑ᵢ₌₁ⁿ xᵢn" bo'lib
    qolardi, `\\bar{x}` esa oddiy "x" ga aylanardi.
    """
    out = _convert(_undouble(text))
    # `\\prime` allaqachon yuqorida turadigan belgi — uning oldidagi
    # "^" ortiqcha.
    out = out.replace("^′", "′").replace("^'", "′").replace("^(′)", "′")
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def render(html_body: str) -> str:
    """Slayd matnidagi LaTeX bo'laklarini almashtiradi.

    Faqat teglar ORASIDAGI matn tegiladi — sinf nomlari va
    atributlarga tegilmaydi.
    """
    parts = _TAGS.split(_undouble(html_body))
    for index, part in enumerate(parts):
        if index % 2:
            continue
        if "$" in part or "\\" in part:
            parts[index] = _MATH.sub(
                lambda m: formula(next(g for g in m.groups() if g is not None)),
                part)
            # Chegarasiz yozilgan buyruqlar ham tuzatiladi.
            if "\\" in parts[index]:
                parts[index] = formula(parts[index])
    return "".join(parts)


def has_math(html_body: str) -> bool:
    return bool(_MATH.search(str(html_body or "")))
