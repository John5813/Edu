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
- Balance top-up on the site: receipt upload checked by the same rules as the bot (`services/receipts/web.py`). Click/Payme/Uzum are listed as "soon" in `receipts.web.methods()`.
- Presentations can be paged through in the browser before download (`#/job/<id>`): the final HTML pages and JPEG previews of a modern presentation are kept in `temp/web_jobs/decks/<job_id>/` (`services/web_decks.py`, removed with the order); ordinary template presentations are view-only (LibreOffice previews).
- Per-slide rewrite (modern presentation only): `POST /api/v1/jobs/<id>/rewrite` → `slide_rewrite` job (`config.SLIDE_REWRITE_PRICE`, default 900 so'm, refunded on failure). `services/premium_presentation/slide_edit.py` plans the page from the client's free-text request, researches chart data with the selected AI, writes the page with the other slides as context, rebuilds the plan slide when a title changes and re-assembles the PPTX. The "AI is working" animation (`aiw*` in `app.js`) is shown while any presentation is being written or rewritten.
- Sign-in: Google (authorization-code flow in `webapp/account_api.py`, enabled only when `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set; authorised redirect URI `https://<domain>/api/v1/auth/google/callback`) or Telegram. A first Google sign-in creates a Telegram-less account: a `users` row with a negative id `<= -WEB_ID_BASE` (`database/web_accounts.py`, `username` stays empty). Such accounts work on the site (receipts go to the admins in the bot, files are downloaded from the site; no Telegram delivery and no channel check). "Link Telegram" in the profile opens `/start weblink_<token>`; after an explicit "Yes" in the bot the web account is merged into the Telegram account (balance, payments, jobs, sessions). Broadcasts skip non-positive ids.
- Modern presentation prompts are written in the deck's language (`services/premium_presentation/prompts/`: `uz.py` is the source text, `ru.py`, `en.py`, `kk.py` are full translations with the same names and ⟨slots⟩; `uz-cyrl` uses the Uzbek prompt with the Cyrillic output rule). Every model call of the pipeline (outline, slide writing, block samples, repairs, leads, charts, site slide rewrite, today/year rule) takes its text from there; technical keys (categories, CSS classes, family keys) stay Latin. When a prompt changes, change all four files; `test_prompt_tillari.py` checks parity and that no Uzbek words leak into ru/en/kk prompts.
- Modern presentation has two text volumes instead of a colour choice (the colour comes from the topic, `themes.for_deck`): the bot asks "Matn hajmi" after the style, the site shows the same choice; the job param is `volume` (`kop` | `kam`, trial is always `kop`). `kop` keeps the block catalogue but with word budgets (slide ≤ 90 words, one idea per slide, coherent prose) and 4 photo slides per 10; `kam` (`services/premium_presentation/deck_compose.py`) writes every slide in a fixed composition (photo left/right/top/full-bleed card, quote, dark key figures, steps, timeline, two-half comparison, full-width chart, formula, worked example, cards, dark conclusion) chosen by code from the outline category, photo positions rotate, 6 photo slides per 10. Too-long slides are rewritten shorter (`html_slides.shorten_long`, limits in `deck_compose.WORD_LIMIT`) instead of shrinking the font. `test_kam_matn.py` covers both modes, real render and the bot/site choice.
- Free trial presentation (site): once per account (`database/free_trial.py`, table `free_trials`), 5 slides fixed, Gemini 2.5 Flash Lite only for that job (`llm_client.text_model` context, does not change the admin-selected model or other jobs), no images, not published to the store. The trial is claimed atomically on order and released if the job fails/is cancelled/the server restarts; account merge keeps it used. Slide rewrite stays paid. Tests: `test_bepul_sinov.py`.
- Store pages for search engines (`webapp/store.py`, `services/store_seo.py`): each work lives at `/shop/<CODE>/<slug>` (old `/shop/<CODE>` redirects 301), images at `/shop/img/<CODE>/<slug>-<n>.jpg`. Catalog sections are server-rendered: `/shop/tur/<type>`, `/shop/fan/<subject>`, `/shop/tur/<type>/<subject>` (old `?type=&category=` links redirect). The work page shows the outline and an excerpt taken from the file (`outline`/`excerpt` columns; filled on publish, and for older works by a background job that downloads the file from the vault once, `seo_state`). `sitemap.xml` lists sections and works with their images (Google Images); new works are announced to Yandex/Bing via IndexNow (key file `/<key>.txt`) when the site runs on a real https domain. `test_sayt_seo.py` covers it.
- Site languages uz / ru / en / kk (`static/i18n.js` + `static/i18n-dict.js`): UI texts are written in Uzbek and translated at runtime by dictionary (exact text, `{x}` patterns, `$words` units). New UI text needs an entry in the dictionary; `test_sayt_tillar.py` opens every screen in each language and fails on untranslated text. The language is stored in `users.language` (shared with the bot; Kazakh is `kk`).
- Not on the site yet: loyiha ishi and book translation (bot only; book upload page exists at `/book/upload/...`).

## User preferences

- Premium presentation output should be a ready-to-use `.pptx` file, not source code.

## Gotchas

- Do not put API keys in source files or chat; use project Secrets.
- Keep `BOT_TOKEN` configured before restarting the `Telegram Bot` workflow.
- The initial database migration runs at bot startup.
- Playwright Chromium is downloaded on first use if it is not already available.

## Pointers

- Source repository: `https://github.com/John5813/Edu`
