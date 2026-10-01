"""Hisob-kitobni KOD bajaradi, AI emas.

Muammo. Model formulani to'g'ri yozadi, lekin natijani "o'ylab" chiqaradi:
arifmetikada xato qiladi, diagramma uchun raqamlarni uydirib qo'yadi.
Hisob-kitob taqdimotida (demografiya, moliya, fizika, statistika) bu eng
yomon nuqson: formula bir narsa deydi, jadval va diagramma boshqa narsa.

Endi model faqat MODELNI aytadi — formula va boshlang'ich qiymatlar —
raqamlarni esa shu modul hisoblaydi:

    <!-- diagramma: x o'qi yillar, qatorlar formuladan -->
    <div class="calc" data-kind="line" data-var="t" data-range="0:10:2"
         data-vars="P0=8.1;r=0.009"
         data-labels="2025,2027,2029,2031,2033,2035"
         data-series="Taxminiy o'sish: P0*(1+r)**t|Tez o'sish: P0*(1+2*r)**t"
         data-unit="mlrd kishi" data-xlabel="Yil"></div>

    <!-- bitta raqam: javob, ko'rsatkich -->
    <span data-calc="(T/A)*1000" data-vars="T=140;A=7800" data-fmt="1">?</span>

Formula xavfsiz tekshiriladi (`ast`): faqat son, amal, ma'lum funksiyalar.
`eval` ishlatilmaydi — model yozgan matn kodga aylanib qolmaydi.
"""

import ast
import html
import logging
import math
import re
from typing import Dict, List, Optional

log = logging.getLogger("deck_calc")

MAX_POINTS = 60
MAX_SERIES = 8
_MAX_NODES = 200

_CONSTANTS = {"pi": math.pi, "e": math.e}
_FUNCTIONS = {
    "exp": math.exp, "ln": math.log, "log": math.log10, "log10": math.log10,
    "log2": math.log2, "sqrt": math.sqrt, "abs": abs, "min": min, "max": max,
    "round": round, "floor": math.floor, "ceil": math.ceil, "sin": math.sin,
    "cos": math.cos, "tan": math.tan, "pow": pow,
}
_BINARY = {
    ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a ** b, ast.Mod: lambda a, b: a % b,
    ast.FloorDiv: lambda a, b: a // b,
}
_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


class CalcError(ValueError):
    """Formula noto'g'ri yoki hisoblab bo'lmaydi."""


def _normalise(expr: str) -> str:
    text = str(expr or "").strip()
    for old, new in (("×", "*"), ("·", "*"), ("÷", "/"), ("−", "-"), ("–", "-"),
                     ("^", "**"), ("√", "sqrt")):
        text = text.replace(old, new)
    # "5%" → (5/100); "1 000" kabi bo'shliqli minglik ham yig'iladi.
    text = re.sub(r"(?<=\d)\s(?=\d{3}\b)", "", text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", text)
    return text


def evaluate(expr: str, variables: Optional[Dict[str, float]] = None) -> float:
    """Formulani xavfsiz hisoblaydi. Xato bo'lsa `CalcError`."""
    variables = variables or {}
    try:
        tree = ast.parse(_normalise(expr), mode="eval")
    except SyntaxError as exc:
        raise CalcError(f"formula tushunarsiz: {expr!r}") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_NODES:
        raise CalcError("formula juda uzun")

    def walk(node) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id in variables:
                return float(variables[node.id])
            if node.id in _CONSTANTS:
                return _CONSTANTS[node.id]
            raise CalcError(f"noma'lum o'zgaruvchi: {node.id}")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = walk(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise CalcError("daraja juda katta")
            try:
                return float(_BINARY[type(node.op)](left, right))
            except (ZeroDivisionError, OverflowError, ValueError) as exc:
                raise CalcError("hisoblab bo'lmadi") from exc
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in _FUNCTIONS and not node.keywords:
            args = [walk(arg) for arg in node.args]
            try:
                return float(_FUNCTIONS[node.func.id](*args))
            except (ValueError, OverflowError, TypeError, ZeroDivisionError) as exc:
                raise CalcError(f"{node.func.id}() hisoblab bo'lmadi") from exc
        raise CalcError("formulada ruxsat etilmagan belgi bor")

    value = walk(tree)
    if isinstance(value, complex) or math.isnan(value) or math.isinf(value):
        raise CalcError("natija son emas")
    return value


def parse_vars(text: str) -> Dict[str, float]:
    """`P0=8.1;r=0.009` → {...}. Keyingisi oldingisiga tayanishi mumkin."""
    out: Dict[str, float] = {}
    raw = str(text or "")
    pieces = re.split(r"[;\n]", raw) if (";" in raw or "\n" in raw) else raw.split(",")
    for piece in pieces:
        if "=" not in piece:
            continue
        name, _, expr = piece.partition("=")
        name = name.strip()
        if not _NAME.fullmatch(name) or name in _FUNCTIONS or name in _CONSTANTS:
            raise CalcError(f"o'zgaruvchi nomi yaroqsiz: {name!r}")
        out[name] = evaluate(expr, out)
    return out


def _xs(data: Dict[str, str], variables: Dict[str, float]) -> List[float]:
    """x qiymatlari: `data-x="0,2,4"` yoki `data-range="0:10:2"` (oxiri kiradi)."""
    if data.get("range"):
        parts = [p.strip() for p in data["range"].split(":")]
        if len(parts) not in (2, 3):
            raise CalcError("range: boshi:oxiri[:qadam]")
        start, stop = evaluate(parts[0], variables), evaluate(parts[1], variables)
        step = evaluate(parts[2], variables) if len(parts) == 3 else 1.0
        if step == 0 or (stop - start) * step < 0:
            raise CalcError("range qadami noto'g'ri")
        count = int(math.floor((stop - start) / step + 1e-9)) + 1
        if count > MAX_POINTS:
            raise CalcError("nuqta juda ko'p")
        return [start + step * i for i in range(count)]
    if data.get("x"):
        values = [evaluate(p, variables) for p in re.split(r"[;,]", data["x"]) if p.strip()]
        if len(values) > MAX_POINTS:
            raise CalcError("nuqta juda ko'p")
        return values
    raise CalcError("x qiymatlari yo'q")


def format_number(value: float, decimals: Optional[int] = None) -> str:
    """O'zbekcha yozuv: o'nlik vergul, minglik bo'shliq."""
    if decimals is not None:
        text = f"{value:,.{max(0, int(decimals))}f}"
    elif abs(value) >= 1000 or abs(value - round(value)) < 0.005:
        text = f"{value:,.0f}"
    else:
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return text.replace(",", "\u00a0").replace(".", ",")


def _plain_number(value: float) -> str:
    """Diagramma uchun: nuqtali, minglik ajratkichsiz (chizuvchi shuni o'qiydi)."""
    if abs(value) >= 100:
        return f"{value:.0f}" if abs(value - round(value)) < 0.05 else f"{value:.1f}"
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


_ATTR = re.compile(r'\bdata-([a-z\-]+)\s*=\s*(["\'])(.*?)\2', re.IGNORECASE | re.DOTALL)
_CALC_CHART = re.compile(
    r'<div\b[^>]*\bclass\s*=\s*(["\'])[^"\']*\bcalc\b[^"\']*\1[^>]*>\s*</div>',
    re.IGNORECASE | re.DOTALL)
_CALC_VALUE = re.compile(
    r'<(?P<tag>[A-Za-z][A-Za-z0-9]*)\b(?P<attrs>[^>]*\bdata-calc\s*=\s*(["\'])(?P<expr>.*?)\3[^>]*)>'
    r'(?P<inner>[^<]*)</(?P=tag)>', re.IGNORECASE | re.DOTALL)
_CALC_ATTRS = re.compile(r'\s+data-(?:calc|vars|fmt|suffix|prefix)\s*=\s*(["\']).*?\1',
                         re.IGNORECASE | re.DOTALL)


def _attrs(tag: str) -> Dict[str, str]:
    return {key.lower(): html.unescape(value) for key, _, value in _ATTR.findall(tag)}


def _series_names(raw: str) -> List[tuple]:
    """`Nomi: formula|Nomi2: formula2` → [(nom, formula)]. Formulada `:` bo'lmaydi."""
    rows = []
    for part in str(raw or "").split("|"):
        part = part.strip()
        if not part:
            continue
        name, sep, expr = part.partition(":")
        rows.append((name.strip(), expr.strip()) if sep else ("", part))
    return rows


def _chart(match) -> str:
    data = _attrs(match.group(0))
    try:
        variables = parse_vars(data.get("vars", ""))
        kind = (data.get("kind") or "line").strip().lower()
        rows = _series_names(data.get("series"))[:MAX_SERIES]
        if not rows:
            raise CalcError("series yo'q")
        extra = ""
        for key in ("unit", "xlabel", "ylabel"):
            if data.get(key):
                extra += f' data-{key}="{html.escape(data[key], quote=True)}"'

        scalar_bar = kind in ("bar", "ustun", "column") and not (data.get("range") or data.get("x"))
        if kind in ("donut", "pie", "halqa"):
            parts = [f"{name or f'Qism {i + 1}'}: {_plain_number(evaluate(expr, variables))}"
                     for i, (name, expr) in enumerate(rows)]
            labels = ""
            series = "|".join(parts)
        elif scalar_bar:
            # Har ustun o'z formulasidan: "Tug'ilish: (T/A)*1000|O'lim: (O/A)*1000".
            values = [evaluate(expr, variables) for _, expr in rows]
            series = ",".join(_plain_number(v) for v in values)
            labels = ",".join(name or f"{i + 1}" for i, (name, _) in enumerate(rows))
        else:
            var = (data.get("var") or "t").strip()
            if not _NAME.fullmatch(var):
                raise CalcError("o'zgaruvchi nomi yaroqsiz")
            xs = _xs(data, variables)
            computed = []
            for name, expr in rows:
                values = [evaluate(expr, {**variables, var: x}) for x in xs]
                computed.append(f"{name}: " + ",".join(_plain_number(v) for v in values)
                                if name else ",".join(_plain_number(v) for v in values))
            series = "|".join(computed)
            labels_raw = data.get("labels", "")
            labels_list = [p.strip() for p in labels_raw.split(",") if p.strip()]
            if len(labels_list) != len(xs):
                labels_list = [_plain_number(x) for x in xs]
            labels = ",".join(labels_list)
        return (f'<div class="chart" data-kind="{html.escape(kind, quote=True)}"'
                + (f' data-labels="{html.escape(labels, quote=True)}"' if labels else "")
                + f' data-series="{html.escape(series, quote=True)}"{extra}></div>')
    except CalcError as exc:
        log.warning("Hisob diagrammasi tashlandi: %s", exc)
        return ""


def _value(match) -> str:
    tag, attrs = match.group("tag"), match.group("attrs")
    data = _attrs("<x " + attrs + ">")
    cleaned = _CALC_ATTRS.sub("", attrs)
    try:
        value = evaluate(data["calc"], parse_vars(data.get("vars", "")))
        digits = data.get("fmt")
        text = format_number(value, int(digits) if digits not in (None, "") else None)
        text = f'{data.get("prefix", "")}{text}{data.get("suffix", "")}'
    except (CalcError, ValueError) as exc:
        log.warning("Hisob qiymati o'zgarishsiz qoldi: %s", exc)
        text = match.group("inner")
    return f"<{tag}{cleaned}>{html.escape(text)}</{tag}>"


def apply(body: str) -> str:
    """Slayddagi hamma `.calc` diagramma va `data-calc` qiymatlarni hisoblab chiqadi."""
    if "calc" not in body:
        return body
    body = _CALC_CHART.sub(_chart, body)
    return _CALC_VALUE.sub(_value, body)


def count(body: str) -> int:
    return len(_CALC_CHART.findall(body)) + len(_CALC_VALUE.findall(body))
