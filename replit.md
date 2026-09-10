# Edu Premium Taqdimot

Telegram bot ichida OpenAI yordamida professional `python-pptx` taqdimot kodini `.txt` sifatida yaratadi.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the API server (port 5000)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- Required env: `DATABASE_URL` — Postgres connection string

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)

## Where things live

- `bot/handlers/premium_presentation.py` — premium xizmatning Telegram dialogi, to‘lov oqimi va xato tuzatish tugmalari
- `services/premium_presentation/llm_client.py` — AI dan qat'iy JSON "brief" so'rash (5 slaydlik bo'laklarda)
- `services/premium_presentation/models.py` — brief pydantic sxemasi; noto'g'ri slaydni shu ushlaydi
- `services/premium_presentation/pipeline.py` — kanvas tekshiruvi, ustma-ustlikni tuzatish, minimal shrift, ixtiyoriy vizual QA
- `services/premium_presentation/renderer.py` va `layouts.py` — briefni deterministik ravishda PPTX ga chizadi
- `services/premium_presentation/config.py` — model, vizual QA va rasm sozlamalari
- `bot/states.py` — taqdimot yaratish va xato qayta aloqa holatlari
- `utils/heading_guard.py` — AI matni hujjatda allaqachon chop etilgan sarlavhani takrorlab yuborishining oldini oladi
- `services/project_work/specs.py` — loyiha ishi soha spetsifikatsiyalari: umumiy bo'limlar bir marta, har soha faqat o'ziga xos qismini beradi
- `services/project_work/content.py` — spetsifikatsiya bo'yicha matn, jadval va sxema promptlari
- `services/project_work/source.py` — mijoz bergan manbani (matn / DOCX / PDF / PPTX / sayt) matnga aylantiradi
- `services/project_work/charts.py` — byudjet diagrammasi, prognoz chizig'i, Gantt lentasi, risk matritsasi va formula tasviri
- `services/project_work/builder.py` — bitta umumiy DOCX quruvchi; yangi soha qo'shilganda o'zgarmaydi
- `services/document_source.py` — yuklangan PDF/DOCX/PPTX dan xavfsiz matn olish (betma-bet, chegara bilan, navbatda)
- `bot/handlers/project_work.py` — loyiha ishi dialogi

## Architecture decisions

- Premium oqim AI dan JSON brief oladi va uni o‘zi PPTX ga render qiladi. AI Python kodi yozmaydi va server AI yozgan kodni ishga tushirmaydi.
- Sifat modeldan emas, deterministik rendererdan keladi: pydantic sxemasi, matn ustma-ustligini tuzatish va minimal shrift dasturiy ravishda ta’minlanadi. Shuning uchun brief uchun arzon model yetarli.
- Vizual QA (har slaydni rasmga aylantirib vision modelga yuborish) — oqimdagi eng qimmat qadam, shuning uchun sukut bo‘yicha o‘chiq. `PREMIUM_VISUAL_QA=1` bilan yoqiladi.
- Taqdimotda rasm va diagramma borligi promptga emas, `pipeline.ensure_visuals` ga tayanadi: birinchi slaydda rasm majburiy, taqdimotda kamida 2 ta rasm va 2 ta diagramma. `TOGETHER_API_KEY` bo‘lmasa rasm o‘rniga rangli panel qo‘yiladi va ERROR yoziladi.
- Rasm promptlaridan matn so‘rovlari `utils.security.strip_text_requests` bilan olib tashlanadi — arzon modellar harflarni buzib chizadi.
- AI fayl tahririning narxini AI emas, `config.FILE_EDIT_*` bo‘yicha Python hisoblaydi — narx so‘ralgan amallar sonidan kelib chiqadi va tekshirib bo‘ladi.
- Balans faqat tahrirlangan fayl mijozga yetkazilgandan keyin yechiladi.
- Loyiha ishida yo‘nalishni ham, artefaktlarni ham mijoz tanlaydi; yangi soha qo‘shish — `FIELDS` ga bitta spetsifikatsiya, quruvchi kod emas.
- Uzun manba (qo‘llanma, sayt) har bo‘lim promptiga qo‘yilmaydi: bir marta siqiladi va shu xulosa ishlatiladi.
- Yuklangan fayl `file_size` bo‘yicha yuklashdan OLDIN rad etiladi; PDF `pdf2docx` orqali emas, PyMuPDF bilan betma-bet o‘qiladi va kerakli hajmga yetganda to‘xtaydi.
- Loyiha ishida har ma’lumot o‘z shaklini oladi: xarajat — ustunli diagramma, bosqichlar — Gantt, risklar — matritsa, natijalar — kartochka, prognoz — chiziq. Ranglar tekshirilgan palitradan; ordinal ramp validatordan o‘tkazilgan.

## Product

Foydalanuvchi til, mavzu, ism, uslub va slayd sonini tanlaydi; to‘lovdan keyin tayyor
16:9 `.pptx` faylni oladi. Generatsiya xato bersa, balans avtomatik qaytariladi.

## User preferences

- Premium taqdimot natijasi tayyor `.pptx` fayl bo‘lishi kerak — source code emas.

## Gotchas

- `OPENAI_API_KEY` Replit Secret sifatida kerak; kalitni kodga yoki chatga yozmang.
- `OPENAI_MODEL` berilmasa, `gpt-5.4` ishlatiladi.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
