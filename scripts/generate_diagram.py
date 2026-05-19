"""
Reusable diagram generator with text-fit validation + SVG→PNG export.

Usage:
    conda activate rag-env
    python scripts/generate_diagram.py

Output:
    docs/memory_pipeline_architecture.svg / .png
"""

import os
import sys
import xml.etree.ElementTree as ET

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── text width: conservative px estimate for English ─────────────
#   9px→5.0, 10px→5.5, 11px→6.0, 12px→6.5, 14px→7.5

def tw(text, fs):
    """Estimate text width in SVG pixels."""
    rate = {9: 5.0, 10: 5.5, 11: 6.0, 12: 6.5, 14: 7.5}.get(fs, fs * 0.55)
    return len(text) * rate


def check(text, fs, avail, label=""):
    """Return warning if text overflows available width."""
    w = tw(text, fs)
    if w > avail + 2:
        return f"OVERFLOW [{label}]: '{text[:60]}' ({w:.0f}px > {avail:.0f}px)"
    return ""


# ═══════════════════════════════════════════════════════════════
# SVG GENERATION
# ═══════════════════════════════════════════════════════════════

def build_svg():
    L = []
    a = L.append
    W = []  # warnings

    a('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 740">')
    a('  <style>')
    a('    text { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", Helvetica, Arial, "PingFang SC", "Microsoft YaHei", sans-serif; }')
    a('    .t  { font-size:26px; font-weight:700; fill:#111827; }')
    a('    .s  { font-size:12px; font-weight:700; letter-spacing:0.08em; fill:#0b3d91; }')
    a('    .nt { font-size:14px; font-weight:700; fill:#111827; }')
    a('    .nw { font-size:14px; font-weight:700; fill:#ffffff; }')
    a('    .ns { font-size:11px; font-weight:500; fill:#475569; }')
    a('    .nsw{ font-size:11px; font-weight:500; fill:#dbeafe; }')
    a('    .al { font-size:10px; font-weight:600; fill:#374151; }')
    a('    .lg { font-size:11px; font-weight:500; fill:#475569; }')
    a('    .mo { font-family:"SF Mono","Cascadia Code",Consolas,monospace; font-size:10px; fill:#e5e7eb; }')
    a('    .ms { font-family:"SF Mono","Cascadia Code",Consolas,monospace; font-size:9px; fill:#9ca3af; }')
    a('    .pl { font-size:10px; font-weight:600; fill:#111827; }')
    a('    .ps { font-size:9px; font-weight:400; fill:#64748b; }')
    a('  </style>')

    # defs
    a('  <defs>')
    for mid, clr in [("ap","#1266d6"),("ao","#111827"),("ad","#0b3d91"),("aa","#64748b"),("ac","#f6d65b")]:
        a(f'    <marker id="{mid}" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">')
        a(f'      <polygon points="0 0, 10 3.5, 0 7" fill="{clr}"/>')
        a(f'    </marker>')
    a('    <filter id="sh" x="-4%" y="-4%" width="108%" height="116%">')
    a('      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#111827" flood-opacity="0.08"/>')
    a('    </filter>')
    a('  </defs>')

    # bg
    a('  <rect width="960" height="740" fill="#ffffff"/>')
    a('  <path d="M 0 72 L 960 28 L 960 72 L 0 120 Z" fill="#eaf3ff" opacity="0.6"/>')
    a('  <text x="480" y="34" text-anchor="middle" class="t">GAgent-Multi Memory Pipeline (M6\u2013M8)</text>')

    # ── SECTION 1: WRITE ──
    a('  <rect x="24" y="56" width="436" height="126" rx="14" fill="none" stroke="#cbd5e1" stroke-width="1.2" stroke-dasharray="6 5"/>')
    a('  <text x="36" y="76" class="s">WRITE PATH \u2014 INGESTION &amp; GATE</text>')

    a('  <rect x="40" y="90" width="168" height="56" rx="12" fill="#1266d6" stroke="#111827" stroke-width="1.4" filter="url(#sh)"/>')
    a('  <text x="124" y="112" text-anchor="middle" class="nw">Agent Loop</text>')
    a('  <text x="124" y="131" text-anchor="middle" class="nsw">Tool calls \u00b7 Reasoning</text>')

    a('  <rect x="252" y="90" width="168" height="56" rx="8" fill="#111827" stroke="#374151" stroke-width="1.4"/>')
    a('  <circle cx="268" cy="104" r="4" fill="#f6d65b"/>')
    a('  <circle cx="282" cy="104" r="4" fill="#93c5fd"/>')
    a('  <circle cx="296" cy="104" r="4" fill="#ffffff"/>')
    a('  <text x="336" y="120" text-anchor="middle" class="nw">RuntimeEventLog</text>')
    a('  <text x="336" y="137" text-anchor="middle" class="mo">events.jsonl per session</text>')

    a('  <path d="M 208 118 L 252 118" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#ap)"/>')
    a('  <path d="M 420 118 L 464 118" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#ap)"/>')

    a('  <rect x="464" y="90" width="148" height="56" rx="8" fill="#fff6c7" stroke="#eabf35" stroke-width="1.4"/>')
    a('  <text x="538" y="111" text-anchor="middle" class="nt">MemoryWriteGate</text>')
    a('  <text x="538" y="130" text-anchor="middle" class="ns">source \u2192 target ACL</text>')

    # MemoryStore — widened cylinder
    a('  <path d="M 648 98 C 648 80, 872 80, 872 98 L 872 152 C 872 170, 648 170, 648 152 Z" fill="#ffffff" stroke="#111827" stroke-width="1.4" filter="url(#sh)"/>')
    a('  <ellipse cx="760" cy="98" rx="112" ry="18" fill="#eaf3ff" stroke="#111827" stroke-width="1.4"/>')
    a('  <text x="760" y="119" text-anchor="middle" class="nt">MemoryStore</text>')
    a('  <text x="760" y="139" text-anchor="middle" class="ns">SQLite \u00b7 FTS5 \u00b7 catalog.sqlite</text>')
    a('  <text x="760" y="162" text-anchor="middle" class="ms">memory_items \u00b7 memory_candidates</text>')
    a('  <text x="760" y="174" text-anchor="middle" class="ms">evidence_chunks \u00b7 memory_events</text>')
    W.append(check("memory_items · memory_candidates", 9, 200, "Store table L1"))
    W.append(check("evidence_chunks · memory_events", 9, 200, "Store table L2"))

    a('  <path d="M 612 118 L 648 118" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#ap)"/>')

    # ── SECTION 2: DISTILLATION ──
    a('  <rect x="24" y="196" width="912" height="146" rx="14" fill="none" stroke="#cbd5e1" stroke-width="1.2" stroke-dasharray="6 5"/>')
    a('  <text x="36" y="216" class="s">DISTILLATION &amp; MAINTENANCE \u2014 M6 Trigger \u2192 M7 Build \u2192 M8 Verify</text>')

    a('  <rect x="40" y="230" width="240" height="82" rx="10" fill="#f8fbff" stroke="#d8e1ec" stroke-width="1.4" filter="url(#sh)"/>')
    a('  <text x="160" y="252" text-anchor="middle" class="nt">Distillation Pipeline</text>')
    for bx, lbl, clr in [(52,"M6 Trigger","#1266d6"),(128,"M7 Build","#0b3d91"),(204,"M8 Verify","#f6d65b")]:
        stro = "#eabf35" if clr == "#f6d65b" else "#111827"
        txtc = "ns" if clr == "#f6d65b" else "nsw"
        a(f'  <rect x="{bx}" y="264" width="70" height="22" rx="6" fill="{clr}" stroke="{stro}" stroke-width="1"/>')
        a(f'  <text x="{bx+35}" y="279" text-anchor="middle" class="{txtc}">{lbl}</text>')
    a('  <text x="160" y="305" text-anchor="middle" class="ps">trigger \u2192 candidate \u2192 cross-ref \u2192 format</text>')

    # Inbox
    a('  <path d="M 324 230 L 484 230 L 504 250 L 504 306 L 324 306 Z" fill="#ffffff" stroke="#111827" stroke-width="1.4"/>')
    a('  <path d="M 484 230 L 484 250 L 504 250" fill="none" stroke="#111827" stroke-width="1.4"/>')
    a('  <text x="414" y="264" text-anchor="middle" class="nt">Inbox</text>')
    a('  <text x="414" y="283" text-anchor="middle" class="ns">history_memory_inbox.md</text>')
    W.append(check("history_memory_inbox.md", 11, 170, "Inbox sub"))

    # Maintenance
    a('  <rect x="548" y="230" width="200" height="82" rx="10" fill="#f8fbff" stroke="#d8e1ec" stroke-width="1.4" filter="url(#sh)"/>')
    a('  <text x="648" y="252" text-anchor="middle" class="nt">Maintenance</text>')
    for bx, lbl in [(562,"dedup"),(624,"score"),(686,"archive")]:
        a(f'  <rect x="{bx}" y="264" width="56" height="18" rx="5" fill="#eaf3ff" stroke="#93c5fd" stroke-width="1"/>')
        a(f'  <text x="{bx+28}" y="277" text-anchor="middle" class="ps">{lbl}</text>')
    a('  <text x="648" y="305" text-anchor="middle" class="ps">runs during agent idle / autonomous</text>')

    # L1/L2 — widened
    a('  <path d="M 792 230 L 928 230 L 948 250 L 948 306 L 792 306 Z" fill="#ffffff" stroke="#111827" stroke-width="1.4"/>')
    a('  <path d="M 928 230 L 928 250 L 948 250" fill="none" stroke="#111827" stroke-width="1.4"/>')
    a('  <text x="870" y="262" text-anchor="middle" class="nt">L1 / L2</text>')
    a('  <text x="870" y="280" text-anchor="middle" class="ns">global_mem_insight.txt</text>')
    a('  <text x="870" y="295" text-anchor="middle" class="ns">global_mem.txt</text>')
    W.append(check("global_mem_insight.txt", 11, 148, "L1/L2 sub1"))

    a('  <path d="M 280 271 L 324 271" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#ap)"/>')
    a('  <path d="M 504 271 L 548 271" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#ap)"/>')
    a('  <path d="M 748 271 L 792 271" stroke="#1266d6" stroke-width="2" fill="none" marker-end="url(#ap)"/>')

    # Cross arrows
    a('  <path d="M 700 170 L 700 196 L 160 196 L 160 230" stroke="#0b3d91" stroke-width="1.8" fill="none" marker-end="url(#ad)"/>')
    a('  <g transform="translate(430,183)"><rect x="-6" y="-11" width="86" height="18" rx="5" fill="#fff" opacity="0.95"/><text x="0" y="2" text-anchor="middle" class="al">read evidence</text></g>')

    a('  <path d="M 648 312 L 648 342 L 820 342 L 820 170" stroke="#64748b" stroke-width="1.5" stroke-dasharray="5 4" fill="none" marker-end="url(#aa)"/>')
    a('  <g transform="translate(738,338)"><rect x="-6" y="-11" width="72" height="18" rx="5" fill="#fff" opacity="0.95"/><text x="0" y="2" text-anchor="middle" class="al">archive back</text></g>')

    # ── SECTION 3: READ ──
    a('  <rect x="24" y="362" width="912" height="170" rx="14" fill="none" stroke="#cbd5e1" stroke-width="1.2" stroke-dasharray="6 5"/>')
    a('  <text x="36" y="382" class="s">READ PATH \u2014 UNIFIED RETRIEVAL &amp; CONTEXT ASSEMBLY</text>')

    a('  <rect x="40" y="396" width="200" height="62" rx="12" fill="#1266d6" stroke="#111827" stroke-width="1.4" filter="url(#sh)"/>')
    a('  <text x="140" y="421" text-anchor="middle" class="nw">MemoryReader</text>')
    a('  <text x="140" y="442" text-anchor="middle" class="nsw">Unified read-only facade</text>')

    a('  <rect x="284" y="396" width="176" height="62" rx="10" fill="#f8fbff" stroke="#d8e1ec" stroke-width="1.4" filter="url(#sh)"/>')
    a('  <text x="372" y="421" text-anchor="middle" class="nt">MemoryBundle</text>')
    a('  <text x="372" y="442" text-anchor="middle" class="ns">Sorted by priority</text>')

    # MemoryPlanes — 288px wide with shortened descriptions (fits 268px inner)
    a('  <rect x="504" y="390" width="288" height="134" rx="12" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>')
    a('  <text x="648" y="410" text-anchor="middle" class="nt">MemoryPlanes</text>')
    for i, (name, desc, clr) in enumerate([
        ("project_memory", "L1/L2 + structured", "#1266d6"),
        ("session_memory", "Snapshot + tasks", "#0b3d91"),
        ("run_memory",    "Recent turns + working", "#64748b"),
        ("collaboration", "Shared artifacts", "#111827"),
    ]):
        py = 420 + i * 24
        a(f'  <rect x="514" y="{py}" width="268" height="20" rx="4" fill="#f8fbff" stroke="#d8e1ec" stroke-width="0.8"/>')
        a(f'  <circle cx="524" cy="{py+10}" r="3" fill="{clr}"/>')
        a(f'  <text x="534" y="{py+14}" class="pl">{name}</text>')
        a(f'  <text x="650" y="{py+14}" class="ps">{desc}</text>')
        W.append(check(desc, 9, 268 - (650 - 514) - 4, f"plane {name}"))

    # ContextBuilder — compact
    a('  <rect x="826" y="402" width="98" height="56" rx="10" fill="#0b3d91" stroke="#111827" stroke-width="1.4" filter="url(#sh)"/>')
    a('  <text x="875" y="428" text-anchor="middle" class="nw">Context</text>')
    a('  <text x="875" y="446" text-anchor="middle" class="nsw">Builder</text>')

    a('  <path d="M 240 427 L 284 427" stroke="#0b3d91" stroke-width="1.8" fill="none" marker-end="url(#ad)"/>')
    a('  <path d="M 460 427 L 504 427" stroke="#0b3d91" stroke-width="1.8" fill="none" marker-end="url(#ad)"/>')
    a('  <path d="M 792 434 L 826 434" stroke="#0b3d91" stroke-width="1.8" fill="none" marker-end="url(#ad)"/>')

    a('  <path d="M 760 170 L 760 362 L 140 362 L 140 396" stroke="#0b3d91" stroke-width="1.8" fill="none" marker-end="url(#ad)"/>')
    a('  <g transform="translate(440,348)"><rect x="-6" y="-11" width="66" height="18" rx="5" fill="#fff" opacity="0.95"/><text x="0" y="2" text-anchor="middle" class="al">FTS5 search</text></g>')

    a('  <path d="M 870 306 L 870 352 L 340 352 L 340 396" stroke="#0b3d91" stroke-width="1.8" fill="none" marker-end="url(#ad)"/>')
    a('  <g transform="translate(590,348)"><rect x="-6" y="-11" width="78" height="18" rx="5" fill="#fff" opacity="0.95"/><text x="0" y="2" text-anchor="middle" class="al">file read L1/L2</text></g>')

    a('  <path d="M 538 146 L 538 196 L 340 196 L 340 230" stroke="#f6d65b" stroke-width="1.8" fill="none" marker-end="url(#ac)"/>')
    a('  <g transform="translate(440,192)"><rect x="-6" y="-11" width="78" height="18" rx="5" fill="#fff6c7" opacity="0.95"/><text x="0" y="2" text-anchor="middle" class="al">write decision</text></g>')

    a('  <path d="M 372 458 L 372 494 L 504 494" stroke="#111827" stroke-width="1.6" fill="none" marker-end="url(#ao)"/>')

    # ── Flow summary ──
    a('  <rect x="24" y="552" width="912" height="56" rx="10" fill="#f8fbff" stroke="#cbd5e1" stroke-width="1"/>')
    a('  <text x="44" y="574" class="ps" fill="#0b3d91" font-weight="700">PRIORITY ORDER:</text>')
    a('  <text x="44" y="592" class="ps">Primary (L1/L2, always available)</text>')
    a('  <text x="280" y="592" class="ps">\u2192 Supplementary (structured FTS5, gated)</text>')
    a('  <text x="520" y="592" class="ps">\u2192 Volatile (session/task state, gated)</text>')
    for lx, lbl in [(168,"write path"),(408,"read path"),(644,"async maint"),(844,"checkpoint")]:
        a(f'  <text x="{lx+8}" y="590" text-anchor="middle" class="ps">{lbl}</text>')
    a('  <line x1="168" y1="565" x2="216" y2="565" stroke="#1266d6" stroke-width="2"/>')
    a('  <line x1="408" y1="565" x2="456" y2="565" stroke="#0b3d91" stroke-width="1.8"/>')
    a('  <line x1="644" y1="565" x2="692" y2="565" stroke="#64748b" stroke-width="1.5" stroke-dasharray="5 4"/>')
    a('  <line x1="844" y1="565" x2="892" y2="565" stroke="#f6d65b" stroke-width="1.8"/>')

    # ── Legend ──
    a('  <rect x="24" y="626" width="500" height="100" rx="10" fill="#ffffff" stroke="#d8e1ec" stroke-width="1"/>')
    a('  <text x="44" y="648" class="s">LEGEND</text>')
    legend_colors = {"ap": "#1266d6", "ad": "#0b3d91", "aa": "#64748b"}
    for ly, mid, lbl in [
        (666,"ap","Primary execution / write flow"),
        (686,"ad","Data / memory movement (read &amp; store)"),
        (706,"aa","Async / maintenance background"),
    ]:
        sw = "2" if mid == "ap" else "1.5"
        sd = "5 4" if mid == "aa" else "none"
        a(f'  <line x1="44" y1="{ly}" x2="84" y2="{ly}" stroke="{legend_colors[mid]}" stroke-width="{sw}" stroke-dasharray="{sd}" marker-end="url(#{mid})"/>')
        a(f'  <text x="96" y="{ly+4}" class="lg">{lbl}</text>')
    a('  <line x1="280" y1="666" x2="320" y2="666" stroke="#111827" stroke-width="1.6" marker-end="url(#ao)"/>')
    a('  <text x="332" y="670" class="lg">Observation / review</text>')
    a('  <line x1="280" y1="686" x2="320" y2="686" stroke="#f6d65b" stroke-width="1.8" marker-end="url(#ac)"/>')
    a('  <text x="332" y="690" class="lg">Checkpoint / gate decision</text>')
    a('  <path d="M 280 702 C 280 697, 310 697, 310 702 L 310 710 C 310 715, 280 715, 280 710 Z" fill="#eaf3ff" stroke="#111827" stroke-width="1"/>')
    a('  <ellipse cx="295" cy="702" rx="15" ry="4" fill="#ffffff" stroke="#111827" stroke-width="1"/>')
    a('  <text x="322" y="710" class="lg">Persistent store (SQLite)</text>')

    a('</svg>')
    return L, W


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    svg_path = os.path.join(PROJECT_ROOT, "docs", "memory_pipeline_architecture.svg")
    png_path = os.path.join(PROJECT_ROOT, "docs", "memory_pipeline_architecture.png")

    print("Generating: memory_pipeline_architecture")
    lines, warnings = build_svg()

    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"  SVG: {svg_path}  ({os.path.getsize(svg_path)/1024:.0f} KB)")

    # Text-fit report
    real_warnings = [w for w in warnings if w]
    if real_warnings:
        print("\n  TEXT-FIT ({} issues):".format(len(real_warnings)))
        for w in real_warnings:
            print("    ! " + w)
    else:
        print("  Text-fit: ALL CLEAR")

    # XML validate
    try:
        ET.parse(svg_path)
        print("  XML: PASSED")
    except Exception as e:
        print("  XML: FAILED - {}".format(e))
        sys.exit(1)

    # PNG export
    try:
        import cairosvg
        cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=1920)
        print(f"  PNG: {png_path}  ({os.path.getsize(png_path)/1024:.0f} KB @ 1920px)")
    except Exception as e:
        print(f"  PNG: SKIPPED — {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
