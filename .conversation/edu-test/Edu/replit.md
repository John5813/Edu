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
- `services/premium_presentation/code_generator.py` — OpenAI prompti va toza Python source code generatsiyasi
- `services/premium_presentation/config.py` — OpenAI model/kalit sozlamalari
- `bot/states.py` — taqdimot yaratish va xato qayta aloqa holatlari

## Architecture decisions

- Premium oqim `python-pptx` kodini qaytaradi; bot kodni ishga tushirmaydi, PPTX yaratmaydi va vizual QA qilmaydi.
- Xato tuzatish uchun oxirgi kod va ko‘pi bilan beshta xato holat ma’lumotlari foydalanuvchi FSM holatida vaqtincha saqlanadi.
- Muvaffaqiyat tugmasi bosilganda FSM tozalanadi va xato konteksti o‘chiriladi.

## Product

Foydalanuvchi til, mavzu, ism, uslub va slayd sonini tanlaydi; to‘lovdan keyin OpenAI’dan
16:9, ko‘k-yashil, oq professional dizayndagi to‘liq Python kodini oladi. Kod ishga
tushirish foydalanuvchining o‘zida qoladi. Ishga tushirish xatosi yuborilsa, aynan o‘sha
kod kontekst bilan qayta tuzatiladi.

## User preferences

- Premium taqdimot natijasi faqat `.txt` ko‘rinishida beriladi.

## Gotchas

- `OPENAI_API_KEY` Replit Secret sifatida kerak; kalitni kodga yoki chatga yozmang.
- `OPENAI_MODEL` berilmasa, `gpt-5.4` ishlatiladi.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
