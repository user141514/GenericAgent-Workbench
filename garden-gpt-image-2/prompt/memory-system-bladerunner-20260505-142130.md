# Memory System Workflow — Blade Runner Style Architecture Diagram

> Mode C · Advisor-only prompt. Take this to GPT Image 2 / DALL·E 3 / Midjourney.

---

## Prompt

```
Technical system architecture diagram of a "Memory System Workflow" for an AI agent codebase. Blade Runner / cyberpunk visual aesthetic.

ASPECT RATIO: 16:9 landscape. Large, cinematic, detailed.

BACKGROUND:
Deep charcoal-black (#0C0D0F) with ultra-fine neon cyan grid lines (#00FFFF at 3% opacity, 40px spacing). Subtle atmospheric haze at the bottom (dark orange/amber glow #FF6B00 at 5% opacity, rising from bottom edge). Faint horizontal scanlines across the entire canvas (1px repeating, barely visible). In the corners, very subtle industrial texture — metallic grime, worn edges.

TITLE STRIP (top-left):
Title: "MEMORY SYSTEM WORKFLOW" in bold condensed monospace font (like OCR-A or Eurostile Extended), color neon cyan #00FFFF, with a subtle glow effect. Below it in smaller text: "CANONICAL CONTEXT PIPELINE · PHASE M0–M8" in amber #FFB000, no glow.

The diagram flows LEFT to RIGHT, TOP to BOTTOM, representing the data pipeline of an AI agent's memory and context system.

---

SECTION 1 — INPUT SOURCES (far left, vertical column):

Three input nodes stacked vertically, each connected by arrows flowing rightward into Section 2.

NODE "User Query" — rounded rectangle, dark fill with cyan #00FFFF border (1px, neon glow), label in cyan. Small icon: a terminal cursor glyph.

NODE "Uploaded Files" — same style but violet #A78BFA border, label in violet. Small icon: a document glyph.

NODE "Route Detection" — same style but amber #FFB000 border, label in amber. Small icon: a branching-arrow glyph. Below it small text: "→ chat / code / review / research / executor" in muted amber.

Arrows from all three nodes converge rightward into Section 2.

---

SECTION 2 — CONTEXT BUILDER (center-left, large zone):

A large dashed border rectangle enclosing the context assembly subsystem. Region label at top: "CONTEXT BUILDER (M4)" in cyan #00FFFF, mono font. The zone border is cyan dashed 1px with subtle glow.

Inside this zone, the Memory Reader sub-zone (smaller dashed box, label "MemoryReader (M3)" in cyan, top-left corner of the zone):

NODE "L1 · global_mem_insight.txt" — small rounded rect, cyan border, cyan label.
NODE "L2 · global_mem.txt" — small rounded rect, cyan border, cyan label.
NODE "L3 · *.md SOPs" — small rounded rect, cyan border, cyan label.
NODE "Structured · catalog.sqlite" — small rounded rect, cyan border, cyan label.

These four nodes feed upward into a larger node:

NODE "MemoryReader" — larger rounded rect, bright cyan #00FFFF fill at 15% opacity, solid cyan border 2px with glow, label "MemoryReader" in bold white mono font.

Also inside the ContextBuilder zone:

NODE "Recent Turns" — rounded rect, emerald #34D399 border, label in emerald. Positioned to the right of MemoryReader.

NODE "Working Memory" — rounded rect, blue #60A5FA border, label in blue. Below Recent Turns.

All internal nodes feed into a central node:

NODE "ContextPacket" — hexagon shape (unique, stands out), amber #FFB000 border 2px with glow, amber fill at 10%, label "ContextPacket" in bold amber mono font. Below it small text: "blocks[] · total_chars · source_breakdown" in muted amber.

A single thick arrow (cyan, 2px, solid, with filled arrowhead) exits the ContextBuilder zone rightward to Section 3.

---

SECTION 3 — ADAPTERS (center, narrow vertical strip):

Three adapter nodes stacked vertically, each receiving the ContextPacket arrow from the left.

NODE "Classic Adapter" — rounded rect, slate #94A3B8 border, label in slate. Small text below: "→ system prompt · messages[0]" in muted slate.

NODE "OpenAI Adapter (M5)" — rounded rect, emerald #34D399 border with subtle glow, label in emerald bold. Small text: "→ inputs list · with markers" in muted emerald. This node is visually prominent (slightly larger, brighter border).

NODE "Handoff Bridge (M6)" — rounded rect, blue #60A5FA border, label in blue. Small text: "→ agentmain · delegates to canonical" in muted blue.

Arrows exit right from all three adapters into Section 4.

---

SECTION 4 — AGENT EXECUTION (center-right, large zone):

A large dashed border rectangle, region label "AGENT EXECUTION" in amber #FFB000.

Inside, two side-by-side execution nodes:

NODE "Classic · agent_runner_loop()" — rounded rect, slate border, slate label.

NODE "OpenAI · Runner.run_streamed()" — rounded rect, emerald border, emerald label. Slightly larger.

Below them, a sub-zone:

NODE "Turn Loop" — dashed box containing a circular flow: "LLM Call" → "Tool Dispatch" → "Tool Event Recorded" → back to "LLM Call". Each node is a small rounded rect in cyan/amber/emerald respectively. The loop arrow curves around clockwise.

Arrow exits downward from Agent Execution to Section 5.

---

SECTION 5 — EVIDENCE & CLASSIFICATION (lower-right):

Three nodes in a horizontal row:

NODE "Tool Event Ledger (M7)" — rounded rect, emerald #34D399 border with glow, label in emerald. Small text: "executed facts ONLY evidence" in muted emerald.

NODE "Change Classifier (M7)" — rounded rect, amber #FFB000 border, label in amber. Small text: "proposed vs executed · verify_against_ledger()" in muted amber.

NODE "Assistant Output" — rounded rect, rose #FB7185 border with WARNING STYLE (double-line or dashed), label in rose. Below it a prominent warning label: "⚠ NOT execution evidence · NOT trusted fact" in rose-red, small mono font. A large red "X" or strike-through glyph next to the label.

Arrows from Tool Event Ledger and Change Classifier converge downward into Section 6. A dashed "cross-reference" arrow connects Assistant Output to the convergence point, labeled "verify (M8)" in rose.

---

SECTION 6 — DISTILLATION & LONG-TERM MEMORY (bottom):

A large dashed border zone spanning the bottom of the diagram, region label "DISTILLATION (M8) → LONG-TERM MEMORY" in amber #FFB000.

Inside, a flow:

NODE "distillation.py" — rounded rect, amber border.

Arrow downward to:

NODE "cross-reference gate" — diamond shape, amber border. Labels on exit arrows: "verified & executed → WRITE" (emerald) / "proposed or unverified → REFUSE" (rose).

Two exit paths:

PATH A (emerald, solid arrow):
  NODE "history_memory_inbox.md" → small rounded rect.
  Arrow continues to three memory tier nodes stacked:
  NODE "L1 · global_mem_insight.txt" — tiny rect, cyan.
  NODE "L2 · global_mem.txt" — tiny rect, cyan.
  NODE "L3 · SOPs *.md" — tiny rect, cyan.

PATH B (rose, dashed arrow terminating in a stop symbol):
  NODE "REFUSED" — small rect, rose border, label in rose.

---

LEGEND (bottom-right corner):
Small semi-transparent dark panel. Contains:
- Color swatches with labels: cyan="Memory/Read", emerald="Adapter/Evidence", amber="Route/Classify", violet="Files/Data", blue="Bridge/WorkingMem", rose="Assistant/Warning", slate="Classic/Legacy"
- Arrow styles: solid cyan="sync", dashed cyan="async", dashed rose="refused/warning"

---

GLOBAL CONSTRAINTS:

MUST KEEP:
- Blade Runner / cyberpunk aesthetic throughout: dark atmosphere, neon glow, industrial feel
- All node labels in mono condensed font (OCR-A / Eurostile Extended / JetBrains Mono)
- Color semantics consistent across the entire diagram
- Arrows are orthogonal (horizontal/vertical), never diagonal
- Edges do not cross nodes; labels do not overlap edges
- Region zone borders use dashed lines with subtle glow
- Scanlines and subtle haze across the background
- At least one cyan neon accent element (like a glowing data stream line or a holographic overlay effect)

MUST AVOID:
- Rainbow colors / high-saturation palette beyond the defined cyberpunk palette
- Emoji or cartoon icons — use minimal geometric glyphs only
- 3D perspective / bevels / glass effects — keep it flat cyberpunk
- Corporate "clean blue" aesthetic — this is BLADE RUNNER, not AWS console
- More than 25 total nodes (if too dense, merge sub-details)
- Fancy cursive/handwritten fonts
- Pure white elements — even "white" text should be slightly warm (like #E8E0D0, aged paper tone)
```

---

## Usage Notes

- **Copy the entire prompt** (including the ` ``` ` markers if your tool requires raw text)
- **Target model**: GPT Image 2 / DALL·E 3 / Midjourney v6+ / Stable Diffusion with ControlNet
- **Recommended size**: 1792×1024 (16:9) or larger for detail
- **Style reference**: Add a Blade Runner 2049 still or cyberpunk concept art as style reference if your tool supports it
- **Midjourney**: Add `--ar 16:9 --style raw --s 250 --v 6.1` at the end
- **DALL·E 3**: Use "vivid" quality for the neon effects to pop
