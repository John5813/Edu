# Edu Telegram Bot

Telegram bot in Uzbek and Russian for generating educational documents, presentations, translations, and media with AI-assisted services.

## Run & Operate

- `python main.py` — run the Telegram bot and its document editor web server
- The `Telegram Bot` workflow is the primary application workflow and listens on port 5000.
- `python -m compileall bot database services utils webapp` — quick Python syntax check
- `python -m pytest` — run the repository's Python tests when test dependencies are available

Required secret:

- `BOT_TOKEN`

Optional secrets used by feature areas:

- `OPENROUTER_API_KEY` — text generation and premium presentation briefs
- `TOGETHER_API_KEY` — image generation
- `BRAVE_API_KEY` (yoki `BRAVE_SEARCH_API_KEY`) — taqdimot rasmlari avval internetdan (Brave Image Search) qidiriladi: mavzuga bitta so'rov, topilmagan slaydni AI chizadi. `PHOTO_SEARCH=0` — o'chirish
- `FAL_API_KEY` — media and infographic generation
- `OPENAI_API_KEY` — selected media and presentation helpers

The bot defaults to a local SQLite database (`bot.db`) unless `DATABASE_URL` is configured for another supported database.

## Stack

- Python 3.11
- aiogram Telegram bot framework
- aiosqlite persistence
- python-pptx, python-docx, PDF/DOCX conversion and Playwright-based rendering
- OpenRouter, Together, FAL, and OpenAI integrations

## Where things live

- `main.py` — bot bootstrap, polling, background jobs, and the editor web server
- `bot/handlers/` — Telegram feature flows
- `services/` — AI, document, media, presentation, translation, and store services
- `database/` — SQLite schema and migrations
- `webapp/` — site (`site/`: home page and cabinet), `/api/v1` (`api.py`), browser editor and store pages
- `services/web_jobs.py`, `services/web_kinds.py` — site orders: price check, atomic balance charge, background job, refund on failure
- `config.py` — environment-backed settings and service pricing

## Architecture decisions

- The Telegram bot and document editor run from the same Python process.
- User balances, orders, and generated-work metadata are stored in SQLite by default.
- Secrets are read only from environment variables; they are not stored in source files.
- Generated files are written to local working directories and cleaned up by background jobs.

## Product

Users select a language, work type, topic, length, and optional extras in Telegram. The bot generates educational documents and presentations, supports file conversion and translation, and can deliver generated files after payment or balance checks.

## Site (edufayl.org)

- Login is through the bot: the browser gets a one-time token, the bot confirms it with `/start weblogin_<token>`, the browser receives a session cookie. Balance and users are the same as in the bot.
- Every service the site offers is registered as a `Kind` in `services/web_kinds.py` (price comes from `config.py`, so it always matches the bot). Heavy documents go through the same single queue as the bot (`bot/queue_service.py`).
- Finished files are kept for 72 hours and then deleted (the bot keeps no documents either). Orders are removed with them.
- Balance top-up on the site: receipt upload checked by the same rules as the bot (`services/receipts/web.py`). Click/Payme/Uzum buttons appear in `receipts.web.methods()` when available.
- Uzum Bank Merchant API (`services/uzum_pay.py`, `database/uzum_orders.py`): Uzum calls `POST /uzum/webhook/{check,create,confirm,reverse,status}` with Basic auth (`UZUM_LOGIN`/`UZUM_PASSWORD`) and `serviceId` (`UZUM_SERVICE_ID`). The customer's Telegram ID is the account (`params.user_id`); the bot/site button is a deeplink `https://uzumbank.uz/open-service?serviceId=..&user_id=<Telegram ID>&amount=<tiyin>`, hidden while `UZUM_TEST=1` and toggled in admin «Funksiyalar» (`uzum_pay`). Amounts in tiyin; errors are HTTP 400 + `errorCode`. `UZUM_TEST=1` confirms without crediting balance. Postman collection: `docs/uzum_postman_collection.json`; tests: `test_uzum.py`.
- Receipt checks (`services/receipts/`): AI reads the receipt, `rules.py` decides. Full-auto mode (`RECEIPT_FULL_AUTO=1`, default; admin panel toggle «🤖 To'liq avto to'lov») approves good receipts and rejects flawed ones under the customer's receipt with the list of problems, a resend button and an admin contact button. Only cases the customer cannot fix (`rules.ADMIN_ONLY`: over limit, possible duplicate, receiver matched by name only, second read failed) go to the admin. Rejected payments stay `rejected`; the admin card has «✅ Baribir tasdiqlash». Duplicates are caught without AI by the file SHA-256 and the Telegram `file_unique_id`; the file's own timestamp (screenshot file name or EXIF) is compared with the receipt time. Customers are never blocked.
- Presentations can be paged through in the browser before download (`#/job/<id>`): the final HTML pages and JPEG previews of a modern presentation are kept in `temp/web_jobs/decks/<job_id>/` (`services/web_decks.py`, removed with the order); ordinary template presentations are view-only (LibreOffice previews).
- Per-slide rewrite (modern presentation only): `POST /api/v1/jobs/<id>/rewrite` → `slide_rewrite` job (`config.SLIDE_REWRITE_PRICE`, default 900 so'm, refunded on failure). `services/premium_presentation/slide_edit.py` plans the page from the client's free-text request, researches chart data with the selected AI, writes the page with the other slides as context, rebuilds the plan slide when a title changes and re-assembles the PPTX. The "AI is working" animation (`aiw*` in `app.js`) is shown while any presentation is being written or rewritten.
- Sign-in: Google (authorization-code flow in `webapp/account_api.py`, enabled only when `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set; authorised redirect URI `https://<domain>/api/v1/auth/google/callback`) or Telegram. A first Google sign-in creates a Telegram-less account: a `users` row with a negative id `<= -WEB_ID_BASE` (`database/web_accounts.py`, `username` stays empty). Such accounts work on the site (receipts go to the admins in the bot, files are downloaded from the site; no Telegram delivery and no channel check). "Link Telegram" in the profile opens `/start weblink_<token>`; after an explicit "Yes" in the bot the web account is merged into the Telegram account (balance, payments, jobs, sessions). Broadcasts skip non-positive ids.
- Modern presentation prompts are written in the deck's language (`services/premium_presentation/prompts/`: `uz.py` is the source text, `ru.py`, `en.py`, `kk.py` are full translations with the same names and ⟨slots⟩; `uz-cyrl` uses the Uzbek prompt with the Cyrillic output rule). Every model call of the pipeline (outline, slide writing, block samples, repairs, leads, charts, site slide rewrite, today/year rule) takes its text from there; technical keys (categories, CSS classes, family keys) stay Latin. When a prompt changes, change all four files; `test_prompt_tillari.py` checks parity and that no Uzbek words leak into ru/en/kk prompts.
- Modern presentation has two text volumes instead of a colour choice (the colour comes from the topic, `themes.for_deck`): the bot asks "Matn hajmi" after the style, the site shows the same choice; the job param is `volume` (`kop` | `kam`, trial is always `kop`). On the site «Taqdimot» first shows 4 type cards like the bot (`#ptypes` in `studio.js`): 🎨 Infografik (`volume=kam`), 📝 Zamonaviy (`volume=kop`), 📄 Klassik (`simple_presentation`: template, 10/15/20 slides, plan slide, icons), 🧊 3D (coming soon). Infografik/Zamonaviy also take `theme` (the bot's 6 colours, `web_kinds.COLOR_KEYS`, empty = by topic) and `photos` (`mix`/`web`/`ai`); trial forces no colour and web photos. Tests: `test_sayt_taqdimot_turlari.py`. `kop` keeps the block catalogue but with word budgets (slide ≤ 90 words, one idea per slide, coherent prose) and 4 photo slides per 10; `kam` (`services/premium_presentation/deck_compose.py`) writes every slide in a fixed composition (photo left/right/top/full-bleed card, quote, dark key figures, steps, timeline, two-half comparison, full-width chart, formula, worked example, cards, dark conclusion) chosen by code from the outline category, photo positions rotate, 6 photo slides per 10. Too-long slides are rewritten shorter (`html_slides.shorten_long`, limits in `deck_compose.WORD_LIMIT`) instead of shrinking the font. `test_kam_matn.py` covers both modes, real render and the bot/site choice.
- Free trial presentation (site): once per account (`database/free_trial.py`, table `free_trials`), 5 slides fixed, Gemini 2.5 Flash Lite only for that job (`llm_client.text_model` context, does not change the admin-selected model or other jobs), photos from internet search only (`photo_source="web"`, no paid AI drawing), not published to the store. The trial is claimed atomically on order and released if the job fails/is cancelled/the server restarts; account merge keeps it used. Slide rewrite stays paid. Tests: `test_bepul_sinov.py`.
- Store pages for search engines (`webapp/store.py`, `services/store_seo.py`): each work lives at `/shop/<CODE>/<slug>` (old `/shop/<CODE>` redirects 301), images at `/shop/img/<CODE>/<slug>-<n>.jpg`. Catalog sections are server-rendered: `/shop/tur/<type>`, `/shop/fan/<subject>`, `/shop/tur/<type>/<subject>` (old `?type=&category=` links redirect). The work page shows the outline and an excerpt taken from the file (`outline`/`excerpt` columns; filled on publish, and for older works by a background job that downloads the file from the vault once, `seo_state`). `sitemap.xml` lists sections and works with their images (Google Images); new works are announced to Yandex/Bing via IndexNow (key file `/<key>.txt`) when the site runs on a real https domain. `test_sayt_seo.py` covers it.
- Site languages uz / ru / en / kk (`static/i18n.js` + `static/i18n-dict.js`): UI texts are written in Uzbek and translated at runtime by dictionary (exact text, `{x}` patterns, `$words` units). New UI text needs an entry in the dictionary; `test_sayt_tillar.py` opens every screen in each language and fails on untranslated text. The language is stored in `users.language` (shared with the bot; Kazakh is `kk`).
- Not on the site yet: loyiha ishi and book translation (bot only; book upload page exists at `/book/upload/...`).
- «Sayt rejimi» (`services/site_mode.py`, `bot/handlers/site_mode.py`): admin «🎛 Funksiyalar boshqaruvi» → «🌐 Sayt rejimi». Default OFF — the bot works as before (orders and payments in the bot). ON: main-menu and «Boshqa xizmatlar» buttons answer with a button that opens the service on the site (`/go?t=<one-time token>&to=<kind>`, 15 min, single use; `SITE_LOGIN_URL=1` uses Telegram «Login URL» buttons via `/go/tg` after BotFather `/setdomain`); services not on the site say «tez orada saytda»; «To'lov qilish»/«Mening hisobim» become «🌐 Kabinetim»; the bot sends no payment messages and reengage bonus broadcasts stop. Nothing in the bot flows is deleted — switching OFF restores everything. Tests: `test_sayt_rejimi.py`.
- `/go` login: the GET page never consumes the token (link previewers), `POST /api/v1/auth/go` does; the old session is always replaced; a previous Google-only session in the same browser is kept 10 min in `edu_prev` and the client is asked to merge (`/api/v1/auth/merge`).
- Finished site files go to the client's bot (`web_jobs.deliver_to_telegram`): client language, > 49 MB → «Saytda ochish» button instead of the file, 3 retries, blocked bot stops at once; result stored in `web_jobs.tg_sent` and shown on the site. Failed orders also get a bot message. `golink:<place>` callback always issues a fresh one-time link. Tests: `test_fayl_yetkazish.py`.
- Not enough balance on the site: `POST /api/v1/pending` stores the order (one per account, 6 h) and the wallet shows only the missing amount; every balance credit (`credit_approved_payment`: Click, Payme, Uzum, receipts) calls `web_jobs.start_pending`, so the order starts even if the client never returns to the site (claimed atomically — one job). Unfinished studio choices are also kept server-side (`/api/v1/draft`, 7 days) so a new browser window opened from the bot restores them. Tests: `test_kutayotgan_buyurtma.py`.

## User preferences

- Premium presentation output should be a ready-to-use `.pptx` file, not source code.

## Server memory (2 GB droplet)

- Every memory-heavy step (Chromium render, LibreOffice, 3D model conversion, ONNX cutout, pdf2docx, 3D deck assembly) goes through `services/heavy_gate.py`: at most `HEAVY_PARALLEL` at once (1 on 2 GB) and only when `MemAvailable` covers the step plus a reserve. Extra load waits instead of filling RAM; the wait is not counted in step timeouts. Customers never see the queue — status messages keep rotating facts (`bot/waiting.py`, `bot/queue_service.py`).
- Paid bot orders are recorded in `bot_orders` (`database/bot_orders.py`); after a crash/restart the money is refunded and the customer gets an apology (documents: only the message, nothing was charged yet).
- `services/memory_watch.py` alerts admins when free memory < 300 MB or disk < 2 GB, and marks browser/node/LibreOffice children `oom_score_adj=1000`.
- Server setup (systemd with auto-restart, earlyoom, swap): `deploy/README.md`, `sudo bash deploy/sozlash.sh`.

## Gotchas

- Do not put API keys in source files or chat; use project Secrets.
- Keep `BOT_TOKEN` configured before restarting the `Telegram Bot` workflow.
- The initial database migration runs at bot startup.
- Playwright Chromium is downloaded on first use if it is not already available.

## Pointers

- Source repository: `https://github.com/John5813/Edu`
