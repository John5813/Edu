---
name: Premium inline text extraction
description: Non-obvious constraint for converting generated HTML text with inline spans into editable PowerPoint elements.
---

The Premium HTML-to-PPTX converter must treat each direct DOM text node, split by its browser-measured visual line, as the unit of editable text. A parent element's bounding box must not also be emitted when it contains nested inline elements such as highlighted spans.

**Why:** HTML lays inline text out as one flow, but PowerPoint receives separate objects. Emitting the parent and its children duplicates fragments and causes visible text overlap, missing words, and broken sentence flow. PowerPoint text boxes also must not be widened after extraction or adjacent fragments can overlap again.

**How to apply:** Preserve browser coordinates for each visual text fragment, avoid extra width padding in the PPTX builder, and keep a regression case for wrapped paragraphs with inline spans.