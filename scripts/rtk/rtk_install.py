#!/usr/bin/env python3
"""
rtk_install.py — 重新将 rtk 模块注入项目

操作：
  1. 调用 `rtk init --auto-patch`（Windows下自动降级为--claude-md模式）
  2. 向 .claude/settings.local.json 补充 rtk Bash 白名单

用法：
  python scripts/rtk/rtk_install.py          # 实际安装
  python scripts/rtk/rtk_install.py --dry-run  # 只预览
"""

import sys
import json
import subprocess
import pathlib
import argparse

# Windows 控制台默认 GBK 无法显示 ▶ ✅ 等字符 — 强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PR = pathlib.Path(__file__).parent.parent.parent

RTK_ALLOW_ENTRIES = [
    'Bash(where rtk *)',
    'Bash(rtk deps *)',
    'Bash(rtk init *)',
    'Bash(rtk pytest *)',
]


def run_rtk_init(dry_run: bool):
    """运行 rtk init --auto-patch"""
    cmd = ["rtk", "init", "--auto-patch"]
    print(f"  $ {' '.join(cmd)}")
    if dry_run:
        print("  [DRY-RUN] 跳过实际执行")
        return True
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PR), timeout=90)
    print(r.stdout.strip())
    if r.stderr.strip():
        print("STDERR:", r.stderr.strip())
    return r.returncode == 0


def patch_settings_local(dry_run: bool):
    """确保 settings.local.json 包含 rtk Bash 白名单"""
    p = PR / ".claude" / "settings.local.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    allow: list = data.setdefault("permissions", {}).setdefault("allow", [])
    added = []
    for entry in RTK_ALLOW_ENTRIES:
        if entry not in allow:
            allow.append(entry)
            added.append(entry)
    if added:
        print(f"  → 新增 {len(added)} 条白名单")
        for e in added:
            print(f"     + {e}")
    else:
        print("  → 白名单已是最新，无需修改")
    if not dry_run and added:
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="rtk 模块安装/重新注入")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    args = parser.parse_args()
    dry = args.dry_run

    mode = "[DRY-RUN]" if dry else "[INSTALL]"
    print(f"\n{'='*55}")
    print(f"  rtk_install.py  {mode}")
    print(f"  项目根: {PR}")
    print(f"{'='*55}\n")

    print("▶ Step 1: rtk init --auto-patch ...")
    ok = run_rtk_init(dry)
    print(f"  → {'OK' if ok else 'FAILED'}")

    print("\n▶ Step 2: 补充 settings.local.json 白名单 ...")
    patch_settings_local(dry)

    print()
    if dry:
        print("✅ Dry-run 完成 — 未修改任何文件。")
    else:
        print("✅ rtk 模块安装完成。")
        print("   验证: rtk --show")
        print("   卸载: python scripts/rtk/rtk_uninstall.py")
    print()


if __name__ == "__main__":
    main()