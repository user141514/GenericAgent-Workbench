"""Generate Classic Agent Loop architecture diagram SVG."""
import os

lines = []
L = lines.append

# ── SVG header ──
L('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 820" width="960" height="820">')
L('<style>')
L('  text {')
L('    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",')
L('                 "Helvetica Neue", Helvetica, Arial,')
L('                 "PingFang SC", "Microsoft YaHei", "Microsoft JhengHei", "SimHei",')
L('                 sans-serif;')
L('  }')
L('  .title { font-size: 26px; font-weight: 700; fill: #111827; }')
L('  .subtitle { font-size: 13px; font-weight: 500; fill: #64748b; }')
L('  .section { font-size: 12px; font-weight: 700; letter-spacing: 0.08em; fill: #0b3d91; }')
L('  .node-title { font-size: 14px; font-weight: 700; fill: #111827; }')
L('  .node-title-invert { font-size: 14px; font-weight: 700; fill: #ffffff; }')
L('  .node-sub { font-size: 11px; font-weight: 500; fill: #475569; }')
L('  .node-sub-invert { font-size: 11px; font-weight: 500; fill: #dbeafe; }')
L('  .arrow-label { font-size: 10px; font-weight: 600; fill: #374151; }')
L('  .legend { font-size: 12px; font-weight: 500; fill: #475569; }')
L('  .small-label { font-size: 10px; font-weight: 500; fill: #64748b; }')
L('  .mono { font-family: "SF Mono", "Fira Code", "Cascadia Code", Consolas, monospace; font-size: 11px; fill: #e5e7eb; }')
L('  .mono-dark { font-family: "SF Mono", "Fira Code", "Cascadia Code", Consolas, monospace; font-size: 11px; fill: #374151; }')
L('</style>')

# ── defs: arrow markers ──
L('<defs>')
L('  <marker id="arrow-primary" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">')
L('    <polygon points="0 0, 10 3.5, 0 7" fill="#1266d6"/>')
L('  </marker>')
L('  <marker id="arrow-observe" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">')
L('    <polygon points="0 0, 10 3.5, 0 7" fill="#111827"/>')
L('  </marker>')
L('  <marker id="arrow-data" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">')
L('    <polygon points="0 0, 10 3.5, 0 7" fill="#0b3d91"/>')
L('  </marker>')
L('  <marker id="arrow-async" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">')
L('    <polygon points="0 0, 10 3.5, 0 7" fill="#64748b"/>')
L('  </marker>')
L('  <marker id="arrow-checkpoint" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">')
L('    <polygon points="0 0, 10 3.5, 0 7" fill="#f6d65b"/>')
L('  </marker>')
L('  <filter id="shadow-light" x="-8%" y="-8%" width="116%" height="116%">')
L('    <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#111827" flood-opacity="0.08"/>')
L('  </filter>')
L('</defs>')

# ── Background ──
L('<rect width="960" height="820" fill="#ffffff"/>')
L('<path d="M 0 100 L 960 20 L 960 90 L 0 170 Z" fill="#eaf3ff" opacity="0.6"/>')
L('<path d="M 0 640 L 960 580 L 960 660 L 0 720 Z" fill="#f8fbff" opacity="0.8"/>')

# ── Title ──
L('<text x="480" y="42" class="title" text-anchor="middle">GAgent-Multi Classic Agent Loop</text>')
L('<text x="480" y="62" class="subtitle" text-anchor="middle">agent_runner_loop() - single-link (classic) execution path with tool chain</text>')

# ═══════════════════════════════════════════
# SECTION 1: INPUT LAYER (y: 90-155)
# ═══════════════════════════════════════════
L('<text x="42" y="100" class="section">INPUT</text>')

# User Input box
L('<rect x="42" y="110" rx="10" ry="10" width="140" height="48" fill="#ffffff" stroke="#111827" stroke-width="1.4" filter="url(#shadow-light)"/>')
L('<text x="112" y="130" class="node-title" text-anchor="middle">User Input</text>')
L('<text x="112" y="147" class="node-sub" text-anchor="middle">raw_query</text>')

# Frontend box
L('<rect x="240" y="110" rx="12" ry="12" width="150" height="48" fill="#ffffff" stroke="#111827" stroke-width="1.4"/>')
L('<rect x="240" y="110" rx="12" ry="12" width="150" height="18" fill="#eaf3ff" stroke="#111827" stroke-width="1.4"/>')
L('<circle cx="254" cy="119" r="3.5" fill="#f6d65b"/>')
L('<circle cx="266" cy="119" r="3.5" fill="#1266d6"/>')
L('<circle cx="278" cy="119" r="3.5" fill="#ffffff" stroke="#111827" stroke-width="0.6"/>')
L('<text x="315" y="136" class="node-title" text-anchor="middle">Frontend</text>')
L('<text x="315" y="151" class="node-sub" text-anchor="middle">stapp.py / dispatch</text>')

# RouterRules
L('<rect x="448" y="110" rx="10" ry="10" width="130" height="48" fill="#f8fbff" stroke="#d8e1ec" stroke-width="1.4"/>')
L('<text x="513" y="130" class="node-title" text-anchor="middle">RouterRules</text>')
L('<text x="513" y="147" class="node-sub" text-anchor="middle">classify intent</text>')

# GeneraticAgent
L('<rect x="640" y="106" rx="14" ry="14" width="180" height="56" fill="#1266d6" stroke="#111827" stroke-width="1.6" filter="url(#shadow-light)"/>')
L('<text x="730" y="130" class="node-title-invert" text-anchor="middle">GeneraticAgent</text>')
L('<text x="730" y="150" class="node-sub-invert" text-anchor="middle">.run() - task queue consumer</text>')

# Arrows: User - Frontend - Router - Agent
L('<path d="M 182 134 L 234 134" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#arrow-primary)"/>')
L('<path d="M 390 134 L 442 134" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#arrow-primary)"/>')
L('<path d="M 578 134 L 634 134" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#arrow-primary)"/>')

# ═══════════════════════════════════════════
# SECTION 2: PRE-LOOP SETUP (y: 180-395)
# ═══════════════════════════════════════════
L('<text x="42" y="200" class="section">PRE-LOOP SETUP</text>')

# Read Shortcut diamond
L('<polygon points="112,215 182,250 112,285 42,250" fill="#fff6c7" stroke="#eabf35" stroke-width="1.4"/>')
L('<text x="112" y="246" class="arrow-label" text-anchor="middle">Shortcut</text>')
L('<text x="112" y="258" class="small-label" text-anchor="middle">Hit?</text>')

# Arrow from Agent down to Shortcut
L('<path d="M 680 162 L 680 200 L 182 200 L 182 209" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#arrow-primary)"/>')

# Shortcut bypass (right arrow - yellow checkpoint)
L('<path d="M 182 250 L 448 250" stroke="#f6d65b" stroke-width="2" fill="none" marker-end="url(#arrow-checkpoint)"/>')
L('<g transform="translate(260, 237)">')
L('  <rect x="-4" y="-10" width="74" height="18" rx="4" fill="#ffffff" opacity="0.95"/>')
L('  <text x="0" y="3" class="arrow-label">YES: bypass</text>')
L('</g>')

# Direct Output (shortcut hit destination)
L('<rect x="454" y="232" rx="10" ry="10" width="140" height="36" fill="#fff6c7" stroke="#eabf35" stroke-width="1.4"/>')
L('<text x="524" y="248" class="node-title" text-anchor="middle">Direct Output</text>')
L('<text x="524" y="261" class="small-label" text-anchor="middle">read shortcut result</text>')

# Arrow from shortcut direct output to output section
L('<path d="M 524 268 L 524 640" stroke="#f6d65b" stroke-width="1.8" stroke-dasharray="5 4" fill="none" marker-end="url(#arrow-checkpoint)"/>')

# NO path: Shortcut down to setup row
L('<path d="M 112 285 L 112 318" stroke="#111827" stroke-width="1.6" fill="none" marker-end="url(#arrow-observe)"/>')
L('<g transform="translate(20, 294)">')
L('  <rect x="-4" y="-10" width="38" height="18" rx="4" fill="#ffffff" opacity="0.95"/>')
L('  <text x="0" y="3" class="arrow-label">NO</text>')
L('</g>')

# Setup row: Memory Inject, Tool Select, Recent Context
# System Prompt + Memory
L('<rect x="42" y="324" rx="10" ry="10" width="160" height="52" fill="#f8fbff" stroke="#d8e1ec" stroke-width="1.4"/>')
L('<text x="122" y="344" class="node-title" text-anchor="middle">System Prompt</text>')
L('<text x="122" y="359" class="node-sub" text-anchor="middle">L1 + L2 memory injection</text>')
L('<text x="122" y="371" class="small-label" text-anchor="middle">60s cache</text>')

# Tool Schema Selector
L('<rect x="248" y="324" rx="10" ry="10" width="160" height="52" fill="#f8fbff" stroke="#d8e1ec" stroke-width="1.4"/>')
L('<text x="328" y="344" class="node-title" text-anchor="middle">Tool Selector</text>')
L('<text x="328" y="359" class="node-sub" text-anchor="middle">schema_selector.py</text>')
L('<text x="328" y="371" class="small-label" text-anchor="middle">gate: SLIM_TOOLS</text>')

# Recent Context Builder
L('<rect x="454" y="324" rx="10" ry="10" width="170" height="52" fill="#f8fbff" stroke="#d8e1ec" stroke-width="1.4"/>')
L('<text x="539" y="344" class="node-title" text-anchor="middle">Recent Context</text>')
L('<text x="539" y="359" class="node-sub" text-anchor="middle">build_recent_context()</text>')
L('<text x="539" y="371" class="small-label" text-anchor="middle">gate: RECENT_TURNS</text>')

# Handler creation
L('<rect x="670" y="324" rx="10" ry="10" width="170" height="52" fill="#0b3d91" stroke="#111827" stroke-width="1.6"/>')
L('<text x="755" y="344" class="node-title-invert" text-anchor="middle">GenericAgentHandler</text>')
L('<text x="755" y="359" class="node-sub-invert" text-anchor="middle">handler init + working state</text>')

# Horizontal arrows in setup row
L('<path d="M 202 350 L 242 350" stroke="#64748b" stroke-width="1.5" fill="none" marker-end="url(#arrow-async)"/>')
L('<path d="M 408 350 L 448 350" stroke="#64748b" stroke-width="1.5" fill="none" marker-end="url(#arrow-async)"/>')
L('<path d="M 624 350 L 664 350" stroke="#64748b" stroke-width="1.5" fill="none" marker-end="url(#arrow-async)"/>')

# ═══════════════════════════════════════════
# SECTION 3: THE MAIN LOOP (y: 405-660)
# ═══════════════════════════════════════════
L('<text x="42" y="420" class="section">AGENT RUNNER LOOP</text>')

# Loop container
L('<rect x="30" y="434" rx="18" ry="18" width="900" height="216" fill="none" stroke="#93c5fd" stroke-width="1.6" stroke-dasharray="8 5"/>')
L('<rect x="40" y="420" rx="6" ry="6" width="200" height="18" fill="#1266d6"/>')
L('<text x="140" y="433" class="small-label" text-anchor="middle" fill="#ffffff" font-weight="700">while turn &lt; max_turns (80)</text>')

# Node 1: LLM Call (central blue)
L('<rect x="70" y="460" rx="12" ry="12" width="220" height="68" fill="#1266d6" stroke="#111827" stroke-width="1.6" filter="url(#shadow-light)"/>')
L('<text x="180" y="484" class="node-title-invert" text-anchor="middle">LLM Call</text>')
L('<text x="180" y="502" class="mono" text-anchor="middle">client.chat(messages, tools)</text>')
L('<text x="180" y="518" class="node-sub-invert" text-anchor="middle">build prompt + stream response</text>')

# Parser box
L('<rect x="360" y="460" rx="10" ry="10" width="180" height="68" fill="#ffffff" stroke="#111827" stroke-width="1.4"/>')
L('<text x="450" y="484" class="node-title" text-anchor="middle">Parse Response</text>')
L('<text x="450" y="502" class="node-sub" text-anchor="middle">_parse_mixed_response()</text>')
L('<text x="450" y="518" class="small-label" text-anchor="middle">extract tool_calls list</text>')

# Tool Dispatch
L('<rect x="610" y="460" rx="10" ry="10" width="210" height="68" fill="#0b3d91" stroke="#111827" stroke-width="1.6"/>')
L('<text x="715" y="484" class="node-title-invert" text-anchor="middle">Tool Dispatch</text>')
L('<text x="715" y="502" class="mono" text-anchor="middle">handler.dispatch(name, args)</text>')
L('<text x="715" y="518" class="node-sub-invert" text-anchor="middle">read / code_run / patch / ask</text>')

# Arrows: LLM - Parse - Tools
L('<path d="M 290 494 L 354 494" stroke="#1266d6" stroke-width="2.2" fill="none" marker-end="url(#arrow-primary)"/>')
L('<path d="M 540 494 L 604 494" stroke="#1266d6" stroke-width="2.2" fill="none" marker-end="url(#arrow-primary)"/>')

# Tool Event Ledger (small box under tool dispatch)
L('<rect x="635" y="538" rx="6" ry="6" width="165" height="22" fill="#f8fbff" stroke="#cbd5e1" stroke-width="1"/>')
L('<text x="717" y="553" class="small-label" text-anchor="middle">ToolEventLedger (gate: TOOL_EVENT_LEDGER)</text>')

# Exit check diamond
L('<polygon points="460,560 520,590 460,620 400,590" fill="#fff6c7" stroke="#eabf35" stroke-width="1.4"/>')
L('<text x="460" y="586" class="arrow-label" text-anchor="middle">Exit?</text>')
L('<text x="460" y="598" class="small-label" text-anchor="middle">should_exit</text>')
L('<text x="460" y="609" class="small-label" text-anchor="middle">| !next_prompt</text>')

# Arrow from Tools down to exit check
L('<path d="M 715 528 L 715 545 L 520 545 L 520 554" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#arrow-primary)"/>')

# Direct Answer + Early Stop checks
L('<rect x="310" y="574" rx="8" ry="8" width="120" height="40" fill="#f8fbff" stroke="#cbd5e1" stroke-width="1.2"/>')
L('<text x="370" y="590" class="node-sub" text-anchor="middle">Direct Answer?</text>')
L('<text x="370" y="605" class="small-label" text-anchor="middle">file_read bypass</text>')

L('<rect x="500" y="574" rx="8" ry="8" width="120" height="40" fill="#f8fbff" stroke="#cbd5e1" stroke-width="1.2"/>')
L('<text x="560" y="590" class="node-sub" text-anchor="middle">Early Stop?</text>')
L('<text x="560" y="605" class="small-label" text-anchor="middle">completion signal</text>')

# NO path from exit check - Turn End
L('<path d="M 400 590 L 300 590 L 300 640" stroke="#111827" stroke-width="1.6" fill="none" marker-end="url(#arrow-observe)"/>')
L('<g transform="translate(345, 574)">')
L('  <rect x="-4" y="-10" width="38" height="18" rx="4" fill="#ffffff" opacity="0.95"/>')
L('  <text x="0" y="3" class="arrow-label">NO</text>')
L('</g>')

# YES path from exit check - break out
L('<path d="M 520 590 L 630 590 L 630 650" stroke="#f6d65b" stroke-width="2" fill="none" marker-end="url(#arrow-checkpoint)"/>')
L('<g transform="translate(565, 574)">')
L('  <rect x="-4" y="-10" width="38" height="18" rx="4" fill="#ffffff" opacity="0.95"/>')
L('  <text x="0" y="3" class="arrow-label">YES</text>')
L('</g>')

# Turn End Callback (bottom of loop)
L('<rect x="200" y="628" rx="10" ry="10" width="180" height="36" fill="#0b3d91" stroke="#111827" stroke-width="1.6"/>')
L('<text x="290" y="644" class="node-title-invert" text-anchor="middle">Turn End Callback</text>')
L('<text x="290" y="658" class="node-sub-invert" text-anchor="middle">build next_prompt for next turn</text>')

# Cycle arrow: Turn End back to LLM (left-side loop)
L('<path d="M 200 646 L 48 646 L 48 494 L 64 494" stroke="#111827" stroke-width="1.8" fill="none" marker-end="url(#arrow-observe)"/>')
L('<g transform="translate(28, 555)">')
L('  <rect x="-4" y="-10" width="72" height="20" rx="4" fill="#ffffff" opacity="0.95"/>')
L('  <text x="0" y="4" class="arrow-label">next turn</text>')
L('</g>')

# ═══════════════════════════════════════════
# SECTION 4: OUTPUT (y: 680-770)
# ═══════════════════════════════════════════
L('<text x="42" y="700" class="section">OUTPUT</text>')

# Display Queue
L('<rect x="110" y="710" rx="10" ry="10" width="180" height="52" fill="#ffffff" stroke="#111827" stroke-width="1.4" filter="url(#shadow-light)"/>')
L('<text x="200" y="732" class="node-title" text-anchor="middle">Display Queue</text>')
L('<text x="200" y="749" class="node-sub" text-anchor="middle">turn_delta / turn_start / done</text>')

# Frontend stream consumer
L('<rect x="380" y="710" rx="10" ry="10" width="190" height="52" fill="#0b3d91" stroke="#111827" stroke-width="1.6"/>')
L('<text x="475" y="732" class="node-title-invert" text-anchor="middle">Frontend Stream</text>')
L('<text x="475" y="749" class="node-sub-invert" text-anchor="middle">agent_backend_stream()</text>')

# Final answer
L('<rect x="660" y="710" rx="10" ry="10" width="180" height="52" fill="#ffffff" stroke="#111827" stroke-width="1.4"/>')
L('<text x="750" y="732" class="node-title" text-anchor="middle">Final Answer</text>')
L('<text x="750" y="749" class="node-sub" text-anchor="middle">full_resp to user</text>')

# Arrows in output
L('<path d="M 290 736 L 374 736" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#arrow-primary)"/>')
L('<path d="M 570 736 L 654 736" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#arrow-primary)"/>')

# Arrow from exit YES to display queue
L('<path d="M 630 670 L 630 700 L 200 700 L 200 704" stroke="#f6d65b" stroke-width="2" fill="none" marker-end="url(#arrow-checkpoint)"/>')

# Arrow from shortcut direct output to final answer
L('<path d="M 524 268 L 750 268 L 750 704" stroke="#f6d65b" stroke-width="1.8" stroke-dasharray="5 4" fill="none" marker-end="url(#arrow-checkpoint)"/>')

# ═══════════════════════════════════════════
# LEGEND
# ═══════════════════════════════════════════
L('<g transform="translate(30, 790)">')
L('  <rect x="-10" y="-10" width="370" height="36" rx="8" fill="#ffffff" stroke="#d8e1ec" stroke-width="1"/>')
L('  <line x1="0" y1="6" x2="24" y2="6" stroke="#1266d6" stroke-width="2" marker-end="url(#arrow-primary)"/>')
L('  <text x="32" y="10" class="legend">Primary path</text>')
L('  <line x1="120" y1="6" x2="144" y2="6" stroke="#111827" stroke-width="1.6" marker-end="url(#arrow-observe)"/>')
L('  <text x="152" y="10" class="legend">Loop back / control</text>')
L('  <line x1="268" y1="6" x2="292" y2="6" stroke="#f6d65b" stroke-width="2" marker-end="url(#arrow-checkpoint)"/>')
L('  <text x="300" y="10" class="legend">Checkpoint / bypass</text>')
L('</g>')

# ── Close ──
L('</svg>')

# Write file
out_path = 'docs/classic_agent_loop.svg'
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"SVG generated: {out_path}")
print(f"Total lines: {len(lines)}")
