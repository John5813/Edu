---
name: GitHub source sync
description: Project-specific rule for replacing the bot source with the upstream GitHub main branch.
---

When the user explicitly requests a force update from GitHub, treat the latest `github/main` commit as the authoritative bot source instead of merging old local feature work for compatibility. Keep only environment adaptations required for the Replit workflow to start, such as the system Chromium executable path.

**Why:** The local repository contains many Replit snapshots and local-only history. Mixing those changes into an upstream force update is slower and can leave the bot in an ambiguous source state.

**How to apply:** Verify the remote `main` SHA, replace the bot and Premium source from that commit, compile and run the upstream tests, restart `Telegram Bot`, and confirm polling plus Premium browser readiness in the workflow logs.