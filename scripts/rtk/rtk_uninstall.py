#!/usr/bin/env python3
"""
rtk_uninstall.py — 干净移除 rtk 模块的所有项目级接入点

接入点：
  1. CLAUDE.md  → 移除 <!-- rtk-instructions v2 --> 开头到文件末尾的完整指令块
  2. .claude/settings.local.json → 移除 4 条 rtk/where-rtk Bash 白名单

不会动：
  - CLAUDE.md L12-25 的手动 "Token Optimization (RTK)" 摘要节（用户自主管理）
  - .claude/settings.json（Windows 下 rtk 从未修改此文件）
  - rtk.exe 本身（cargo 全局安装，与项目无关）

用法：
  python scripts/rtk/rtk_uninstall.py          # 实际卸载
  python scripts/rtk/rtk_uninstall.py --dry-run  # 只预览，不写文件
"""

import sys
import json
import re
import shutil
import hashlib
import pathlib
import datetime
import argparse

# Windows 控制台默认 GBK 无法显示 ▶ ✅ 等字符 — 强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PR = pathlib.Path(__file__).parent.parent.parent  # F:\GAgent-Multi
BACKUP_DIR = pathlib.Path(__file__).parent / "backup_preinit"

RTK_BLOCK_MARKER = "<!-- rtk-instructions v2 -->"

RTK_ALLOW_ENTRIES = {
    'Bash(where rtk *)',
    'Bash(rtk deps *)',
    'Bash(rtk init *)',
    'Bash(rtk pytest *)',
}

def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remove_rtk_block_from_claude_md(dry_run: bool) -> dict:
    """从 CLAUDE.md 移除 <!-- rtk-instructions v2 --> 到 EOF 的块"""
    p = PR / "CLAUDE.md"
    content = p.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    marker_line = None
    for i, line in enumerate(lines):
        if RTK_BLOCK_MARKER in line:
            marker_line = i
            break

    if marker_line is None:
        return {"status": "skip", "reason": "marker not found — block already removed or never added"}

    before = "".join(lines[:marker_line])
    removed_lines = len(lines) - marker_line
    removed_block = "".join(lines[marker_line:])

    result = {
        "status": "would_remove" if dry_run else "removed",
        "file": "CLAUDE.md",
        "marker_line": marker_line + 1,
        "lines_removed": removed_lines,
        "chars_removed": len(removed_block),
        "new_size": len(before.encode("utf-8")),
    }

    if not dry_run:
        # 写回（去掉末尾多余空行，保留一个换行）
        clean = before.rstrip("\n") + "\n"
        p.write_text(clean, encoding="utf-8")
        result["sha256_after"] = sha256(p)

    return result


def remove_rtk_entries_from_settings_local(dry_run: bool) -> dict:
    """从 .claude/settings.local.json 的 permissions.allow 移除 rtk 白名单条目"""
    p = PR / ".claude" / "settings.local.json"
    data = json.loads(p.read_text(encoding="utf-8"))

    allow = data.get("permissions", {}).get("allow", [])
    original_count = len(allow)
    filtered = [e for e in allow if e not in RTK_ALLOW_ENTRIES]
    removed = [e for e in allow if e in RTK_ALLOW_ENTRIES]

    result = {
        "status": "would_remove" if dry_run else "removed",
        "file": ".claude/settings.local.json",
        "entries_removed": removed,
        "count_before": original_count,
        "count_after": len(filtered),
    }

    if not dry_run:
        data["permissions"]["allow"] = filtered
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        result["sha256_after"] = sha256(p)

    return result


def create_removal_manifest(results: list, dry_run: bool):
    """写卸载记录（仅实际卸载时）"""
    if dry_run:
        return
    record = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "dry_run": False,
        "results": results,
        "restore_cmd": "python scripts/rtk/rtk_install.py",
    }
    out = pathlib.Path(__file__).parent / "uninstall_log.json"
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  📄 卸载日志: {out}")


def main():
    parser = argparse.ArgumentParser(description="rtk 模块干净卸载")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    args = parser.parse_args()
    dry = args.dry_run

    mode = "[DRY-RUN]" if dry else "[UNINSTALL]"
    print(f"\n{'='*55}")
    print(f"  rtk_uninstall.py  {mode}")
    print(f"  项目根: {PR}")
    print(f"{'='*55}\n")

    results = []

    # 1) CLAUDE.md rtk块
    print("▶ Step 1: 移除 CLAUDE.md rtk 指令块 ...")
    r1 = remove_rtk_block_from_claude_md(dry)
    results.append(r1)
    print(f"  → {r1['status']}")
    for k, v in r1.items():
        if k != "status":
            print(f"     {k}: {v}")

    # 2) settings.local.json rtk白名单
    print("\n▶ Step 2: 移除 .claude/settings.local.json rtk 白名单条目 ...")
    r2 = remove_rtk_entries_from_settings_local(dry)
    results.append(r2)
    print(f"  → {r2['status']}")
    for entry in r2.get("entries_removed", []):
        print(f"     - {entry}")
    print(f"     allow 条目: {r2['count_before']} → {r2['count_after']}")

    # 3) 写卸载日志
    create_removal_manifest(results, dry)

    print()
    if dry:
        print("✅ Dry-run 完成 — 未修改任何文件。去掉 --dry-run 执行真实卸载。")
    else:
        print("✅ rtk 模块已干净卸载。")
        print("   重新安装: python scripts/rtk/rtk_install.py")
        print("   备份恢复: scripts/rtk/backup_preinit/CLAUDE.md")
    print()


if __name__ == "__main__":
    main()