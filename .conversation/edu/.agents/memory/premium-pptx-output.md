---
name: Premium PPTX output
description: Durable behavior and safety constraints for premium AI presentation generation.
---

The premium presentation flow must use AI-generated python-pptx source only as an internal intermediate and send the resulting `.pptx` to the user, never the source text.

**Why:** Users need a directly usable PowerPoint file; returning source code defeats the paid presentation workflow.

**How to apply:** Keep generation, validation, execution, PPTX integrity checking, and Telegram document delivery in the server-side flow. Any source-code validation should inspect actual dangerous calls, not merely reject harmless variable names.