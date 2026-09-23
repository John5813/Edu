---
name: Replit Chromium path
description: The system Chromium executable to prefer for Playwright rendering in Replit.
---

Prefer the Replit-provided Chromium executable when Playwright's downloaded headless shell closes unexpectedly. The stable system path is `/repl/tools/bin/chromium`, and it supports the project's no-sandbox launch arguments.

**Why:** Playwright can successfully download its headless shell but still fail to launch it in this environment, while the Replit Chromium binary launches correctly.

**How to apply:** Include the system path in browser discovery and verify with a real headless launch before relying on runtime downloads.