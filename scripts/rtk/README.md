# rtk 模块接入与可干净清除

本目录是 **rtk** (Rust Token Killer) 在本项目的接入点管理模块，保证 rtk 的所有改动可被一键、干净地撤销。

## rtk 是什么

rtk 是命令行 Token 优化器，把 git/gh/pnpm/npm/docker/kubectl 等命令的输出压缩 60-90%，让 LLM Agent 上下文更省。  
全局可执行：`C:\Users\Administrator\.cargo\bin\rtk.exe`（cargo 全局安装，与本项目无关）。

## 接入点（详见 `MANIFEST.json`）

| 文件 | 改动 | 备份 |
|------|------|------|
| `ASSISTANT.md` | 末尾追加 `<!-- rtk-instructions v2 -->` 开头的 138 行指令块（L134-271）。L12-25 的 "Token Optimization (RTK)" 摘要节由用户手动维护，不属于本模块管理。 | `backup_preinit/ASSISTANT.md` |
| `.claude/settings.local.json` | `permissions.allow` 新增 4 条：`Bash(where rtk *)`、`Bash(rtk deps *)`、`Bash(rtk init *)`、`Bash(rtk pytest *)` | `backup_preinit/settings.local.json`（如有原始版） |
| `.claude/settings.json` | **未改动**。Windows 不支持 the assistant Hook，rtk 自动降级为 `--claude-md` 模式，全部指令注入 ASSISTANT.md。 | `backup_preinit/.claude__settings.json` |

## 安装

```bash
python scripts/rtk/rtk_install.py            # 重新注入 rtk 指令到 ASSISTANT.md + 补白名单
python scripts/rtk/rtk_install.py --dry-run  # 预览
rtk --show                                    # 验证：应看到 [ok] Local (./ASSISTANT.md): rtk enabled
```

## 干净卸载

```bash
python scripts/rtk/rtk_uninstall.py            # 实际卸载
python scripts/rtk/rtk_uninstall.py --dry-run  # 预览
```

执行后：
- ASSISTANT.md 自动截断到 `<!-- rtk-instructions v2 -->` 之前（移除约 138 行）
- settings.local.json 移除 4 条 rtk 白名单
- 写入 `uninstall_log.json` 记录此次卸载

L12-25 的 "Token Optimization (RTK)" 摘要节**不会被移除**，因为那是用户在手动总结，不是 rtk 自动注入的。如需彻底清空，手动 `git diff` 或参考 `backup_preinit/ASSISTANT.md`。

## 完全恢复到接入前

```bash
# 用 backup 完全覆盖（最彻底）
copy scripts\rtk\backup_preinit\ASSISTANT.md ..\ASSISTANT.md
copy scripts\rtk\backup_preinit\settings.local.json ..\..\.claude\settings.local.json
```

## 平台说明

| 平台 | rtk 模式 | hook | ASSISTANT.md |
|------|---------|------|------------|
| **Windows（本项目）** | `--claude-md` 全量注入 | ❌ 不支持 | ✅ 含完整指令块 |
| Linux/macOS | `hook` 模式 | ✅ `.claude/settings.json` 配置 PreToolUse | 仅含 `@RTK.md` 引用 |

## 验证 rtk 真的生效

```bash
rtk --show                       # 应显示 [ok] Local (./ASSISTANT.md): rtk enabled
rtk git status                   # 测试压缩输出
rtk gh pr list                   # GitHub 命令压缩
```

如果 the assistant 在本项目里实际调用 `rtk` 前缀的命令、或读了 ASSISTANT.md 的指令并主动改写命令，则接入生效。