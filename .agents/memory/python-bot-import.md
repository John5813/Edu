---
name: Python bot import and startup
description: Importing a Python bot into the generated workspace and avoiding uv project-sync permission failures.
---

Use the workspace-managed Python environment for imported bots. When dependencies are already installed into `.pythonlibs`, run the bot with `python main.py` rather than `uv run`, because `uv` may try to sync into an immutable Nix store path and fail before application startup.

**Why:** The imported Edu project declares Python dependencies in `pyproject.toml`, but the generated workspace's package installation places them in `.pythonlibs`; `uv` project synchronization is not compatible with that layout here.

**How to apply:** Keep the long-running workflow on the plain Python command after installing `requirements.txt` packages through the package-management flow.