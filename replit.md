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
- `webapp/` — browser editor and store pages
- `config.py` — environment-backed settings and service pricing

## Architecture decisions

- The Telegram bot and document editor run from the same Python process.
- User balances, orders, and generated-work metadata are stored in SQLite by default.
- Secrets are read only from environment variables; they are not stored in source files.
- Generated files are written to local working directories and cleaned up by background jobs.

## Product

Users select a language, work type, topic, length, and optional extras in Telegram. The bot generates educational documents and presentations, supports file conversion and translation, and can deliver generated files after payment or balance checks.

## User preferences

- Premium presentation output should be a ready-to-use `.pptx` file, not source code.

## Gotchas

- Do not put API keys in source files or chat; use project Secrets.
- Keep `BOT_TOKEN` configured before restarting the `Telegram Bot` workflow.
- The initial database migration runs at bot startup.
- Playwright Chromium is downloaded on first use if it is not already available.

## Pointers

- Source repository: `https://github.com/John5813/Edu`
