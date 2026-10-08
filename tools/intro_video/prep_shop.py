import os, sys, warnings
warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BOT_TOKEN", "1:x")
from services.premium_presentation import html_slides, themes
import demo_content as dc
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shop_html")
for code, title, wt, price, style, colour, n in dc.SHOP:
    theme = themes.with_style(themes.get(colour), style)
    pages = html_slides.build_pages(dc.shop_slides(title), theme, "uz")
    os.makedirs(os.path.join(out, code), exist_ok=True)
    for i, page in enumerate(pages, 1):
        open(os.path.join(out, code, f"{i}.html"), "w", encoding="utf-8").write(page)
print("ok")
