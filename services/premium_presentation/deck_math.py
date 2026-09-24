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

_SCRIPT = re.compile(r"([\^_])\{([^{}]*)\}|([\^_])(\w)")
_FRAC = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_SQRT = re.compile(r"\\sqrt\s*\{([^{}]*)\}")
_MATH = re.compile(r"\$\$(.+?)\$\$|\$([^$]+)\$|\\\((.+?)\\\)|\\\[(.+?)\\\]",
                   re.DOTALL)
_TAGS = re.compile(r"(<[^>]+>)")
_LEFTOVER = re.compile(r"\\[a-zA-Z]+")


def _script(text: str) -> str:
    """`x^{n-1}` va `a_1` ni yuqori/quyi belgiga o'giradi."""

    def swap(match):
        mark = match.group(1) or match.group(3)
        body = match.group(2) if match.group(2) is not None else match.group(4)
        table = _SUP if mark == "^" else _SUB
        out = []
        for char in body:
            if char not in table:
                # Belgisi yo'q — qavs bilan yozamiz, aks holda
                # "x2" bo'lib, daraja yo'qolib qolardi.
                if mark == "^":
                    return "^(" + body + ")"
                return " (" + body + ")"
            out.append(table[char])
        return "".join(out)

    return _SCRIPT.sub(swap, text)


def _fraction(numerator: str, denominator: str) -> str:
    """Ustma-ust yoziladigan kasr.

    Surat va maxraj alohida element bo'ladi: chizuvchi ularni
    PowerPointda ham ustma-ust qo'yadi, oraliqdagi chiziq esa
    alohida tasma bo'lib chiqadi.
    """
    return (f'<span class="frac"><span class="up">{numerator.strip()}</span>'
            f'<span class="dn">{denominator.strip()}</span></span>')


def formula(text: str) -> str:
    """Bitta formulani belgilarga o'giradi."""
    out = str(text or "")
    for _ in range(3):
        new = _FRAC.sub(lambda m: _fraction(m.group(1), m.group(2)), out)
        if new == out:
            break
        out = new
    out = _SQRT.sub(lambda m: "√(" + m.group(1) + ")", out)
    for word in sorted(_WORDS, key=len, reverse=True):
        out = out.replace(word, _WORDS[word])
    out = _script(out)
    # `\prime` allaqachon yuqorida turadigan belgi — uning oldidagi
    # "^" ortiqcha.
    out = out.replace("^′", "′").replace("^'", "′").replace("^(′)", "′")
    # Qolgan buyruq va figurali qavslar ko'rinmasin.
    out = _LEFTOVER.sub("", out)
    out = out.replace("{", "").replace("}", "")
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def render(html_body: str) -> str:
    """Slayd matnidagi LaTeX bo'laklarini almashtiradi.

    Faqat teglar ORASIDAGI matn tegiladi — sinf nomlari va
    atributlarga tegilmaydi.
    """
    parts = _TAGS.split(str(html_body or ""))
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
