"""AI yozgan python-pptx kodini tekshirib, tayyor PPTX faylga aylantiradi."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
import uuid

from pptx import Presentation


_ALLOWED_IMPORTS = {
    "pptx",
    "math",
    "statistics",
    "textwrap",
    "datetime",
    "os",
}
_BLOCKED_NAMES = {
    "__import__",
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "system",
    "popen",
    "run",
    "Popen",
    "check_output",
    "urlopen",
    "remove",
    "unlink",
    "rmtree",
}


def _validate_code(source: str) -> None:
    if not source.strip():
        raise ValueError("AI bo‘sh Python kod qaytardi")
    if len(source) > 250_000:
        raise ValueError("AI kodi ruxsat etilgan hajmdan katta")

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"AI kodi sintaksis xatosiga ega: {exc.msg}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported = [alias.name.split(".", 1)[0] for alias in node.names]
            if any(name not in _ALLOWED_IMPORTS for name in imported):
                raise ValueError("AI kodi ruxsat etilmagan modulni import qildi")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root not in _ALLOWED_IMPORTS:
                raise ValueError("AI kodi ruxsat etilmagan modulni import qildi")
        elif isinstance(node, ast.Call):
            called_name = None
            if isinstance(node.func, ast.Name):
                called_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                called_name = node.func.attr
            if called_name in _BLOCKED_NAMES:
                raise ValueError(f"AI kodidagi xavfli chaqiruv bloklandi: {called_name}")


def render_code_to_pptx(source: str, work_dir: str = "temp") -> str:
    """Source code'ni vaqtinchalik jarayonda ishga tushirib, PPTX yo'lini qaytaradi."""
    _validate_code(source)

    # `cwd=run_dir` bo‘lgani uchun script va output yo‘llari absolut bo‘lishi
    # kerak; aks holda nisbiy `temp/...` yo‘li ikki marta qo‘shilib ketadi.
    run_dir = Path(work_dir).resolve() / f"code_run_{uuid.uuid4().hex[:10]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    script_path = run_dir / "generate_presentation.py"
    output_path = run_dir / "presentation.pptx"
    script_path.write_text(source, encoding="utf-8")

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(run_dir),
        "PPTX_OUTPUT_PATH": str(output_path),
        "PYTHONNOUSERSITE": "1",
    }
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "noma’lum xato").strip()
        raise RuntimeError(f"AI kodi PPTX yarata olmadi: {detail[-1200:]}")

    candidates = [output_path, *sorted(run_dir.glob("*.pptx"))]
    generated = next((path for path in candidates if path.is_file() and path.stat().st_size), None)
    if generated is None:
        raise RuntimeError("AI kodi hech qanday .pptx fayl yaratmadi")

    try:
        presentation = Presentation(str(generated))
        slide_count = len(presentation.slides)
    except Exception as exc:
        raise RuntimeError(f"Yaratilgan fayl haqiqiy PPTX emas: {exc}") from exc
    if slide_count == 0:
        raise RuntimeError("Yaratilgan PPTX ichida slayd mavjud emas")

    return str(generated)