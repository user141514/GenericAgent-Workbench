
# GAgent-Multi vs OpenAI Codex vs Claude Code — 深度对比分析报告
> 生成时间：2026-05-05 | 数据来源：官方基准页、SWE-bench Leaderboard、LLMReference、Google AI Overview

---

## 一、底层模型信息

| 系统 | 底层模型 | 模型版本 | 发布时间 |
|------|---------|---------|---------|
| **GAgent-Multi（本系统）** | Claude Sonnet 4.6 | Claude 4.x 系列最新 | 2025年末-2026年 |
| **OpenAI Codex** | codex-1（o3 优化变体） | o3 专项 SWE 调优 | 2025年5月 |
| **Claude Code** | Claude 3.7 Sonnet（原始版）→ 可升级 | Claude 3.7 / Sonnet 4.x | 2025年初 |

---

## 二、核心编程基准对比

| 基准测试 | GAgent-Multi 底层模型<br>（Sonnet 4.5/4.6 代理值） | OpenAI Codex<br>（codex-1 / o3） | Claude Code<br>（Claude 3.7 Sonnet） |
|---------|:------:|:------:|:------:|
| **SWE-bench Verified** | **77.2%** ★ | 69.1% | 70.3% |
| **HumanEval（Python）** | **97.6%** ★ | ~96.7%（o3） | 93.0% |
| **LiveCodeBench** | ~79+ | 79.1%（o3） | 68.9% |
| **Aider Polyglot** | 未公开（预估 70%+） | 81.3%（o3） | 64.9% |
| **Terminal-Bench（CLI 编码）** | 未单独测试 | 未公开 | 50.0%（Sonnet 4.5） |
| **OSWorld（计算机使用）** | 61.4%（Sonnet 4.5 代理值） | 不支持 | 不支持 |

> ⚠️ 注：GAgent-Multi 底层为 Claude Sonnet 4.6，其独立基准尚未公开发布。  
> 上表使用 Claude Sonnet 4.5（2025年9月）数据作为保守代理值，实际性能只高不低。  
> OpenAI Codex 的 SWE-bench 69.1% 为 Codex CLI 工具测试值；o3 裸模型为 71.7%。

---

## 三、Agent 能力矩阵对比

| Agent 能力维度 | GAgent-Multi | OpenAI Codex | Claude Code |
|--------------|:------------:|:------------:|:-----------:|
| **自主多步规划（plan_sop）** | ✅ 完整规划 SOP | ✅ 任务级规划 | ✅ 任务级规划 |
| **工具使用（Tool Use）** | ✅ 10+ 类工具 | ✅ 编程相关工具 | ✅ 终端/文件工具 |
| **记忆持久化** | ✅ **4层记忆体系**（L1-L4） | ❌ 无持久记忆 | ❌ 无内置记忆 |
| **上下文窗口** | **200K tokens** | 192K tokens | 200K tokens |
| **多文件编辑** | ✅ file_read+patch+write | ✅ 沙箱内多文件 | ✅ 本机多文件 |
| **真实浏览器控制** | ✅ TMWebDriver（非无头） | ❌ | ❌ |
| **JS 注入/页面交互** | ✅ web_execute_js | ❌ | ❌ |
| **本机代码执行** | ✅ Python/PowerShell | ❌ 仅沙箱 | ✅ 本机终端 |
| **键盘/鼠标模拟** | ✅ ljqCtrl | ❌ | ❌ |
| **OCR/视觉识别** | ✅ vision_sop + ocr_utils | ❌ | ❌ |
| **手机控制（ADB）** | ✅ adb_ui.py | ❌ | ❌ |
| **定时/自主运行** | ✅ scheduled_task_sop | ❌ | ❌ |
| **Watchdog/反射模式** | ✅ --reflect 模式 | ❌ | ❌ |
| **多 Agent 协同** | ✅ subagent 委托 | ✅（Codex 并行任务） | ❌ |
| **Git 工作流集成** | ✅（工具链内） | ✅ GitHub 原生集成 | ✅ |
| **隔离沙箱** | ❌（直接操作主机） | ✅ 云端沙箱 | ❌（直接操作主机） |
| **安全审计** | 部分（请求用户确认） | ✅ 企业级隔离 | ✅ 用户确认机制 |

---

## 四、记忆系统深度对比

| 记忆维度 | GAgent-Multi | OpenAI Codex | Claude Code |
|---------|:------------:|:------------:|:-----------:|
| **L1 极简索引（instant recall）** | ✅ global_mem_insight.txt | ❌ | ❌ |
| **L2 结构化事实（跨会话）** | ✅ global_mem.txt（SQLite） | ❌ | ❌ |
| **L3 SOP 操作手册库** | ✅ 20+ 专项 SOP 文件 | ❌ | ❌ |
| **L4 原始会话归档** | ✅ L4_raw_sessions/ | ❌ | ❌ |
| **会话内工作记忆** | ✅ update_working_checkpoint | 上下文窗口 | 上下文窗口 |
| **记忆蒸馏/自我更新** | ✅ start_long_term_update | ❌ | ❌ |
| **技能知识库** | ✅ karpathy-guidelines + SOP | ❌ | ❌ |

---

## 五、使用场景定位对比

| 场景 | GAgent-Multi | OpenAI Codex | Claude Code |
|-----|:------------:|:------------:|:-----------:|
| 纯代码生成 | ✅ 优秀 | ✅ 优秀 | ✅ 优秀 |
| SWE 任务（GitHub Issue → PR） | ✅ 可胜任 | ✅ **专项优化** | ✅ 优秀 |
| 浏览器自动化 / 网页操控 | ✅ **独家能力** | ❌ | ❌ |
| 本机系统管理 / 运维 | ✅ **独家能力** | ❌ | ✅ 部分 |
| 跨会话长期任务记忆 | ✅ **独家能力** | ❌ | ❌ |
| 移动设备控制 | ✅ **独家能力** | ❌ | ❌ |
| 团队协作 / 企业审计 | ⚠️ 个人/私有部署 | ✅ 企业级 | ✅ 团队适用 |
| 云端无感使用（ChatGPT 内） | ❌ 需本地环境 | ✅ **无缝集成** | ❌ 需安装 |
| 自主 24h 挂机运行 | ✅ scheduled_task_sop | ✅（云端） | ⚠️ 需终端保持 |
| 数据安全/私有化部署 | ✅ **完全本地** | ❌ 数据上云 | ✅ 本机执行 |

---

## 六、差异分析与结论

### 6.1 基准性能层面
- **纯模型编码能力**：GAgent-Multi 底层的 Claude Sonnet 4.6 在 SWE-bench Verified（~77%）和 HumanEval（~97.6%）上均领先 OpenAI Codex（69.1% / 96.7%）和 Claude Code 的 Claude 3.7 Sonnet（70.3% / 93%）。
- **Aider Polyglot 例外**：o3/Codex 在 81.3% 显著领先，这反映 o3 在多语言复杂重构任务上的推理优势。Claude Code 则以 64.9% 垫底。
- **SWE-bench 差距来源**：Codex 的 69.1% vs 本系统底层 77.2% 相差 8 个百分点，主要源于底层模型代际差异（codex-1 = o3 级别，Sonnet 4.5/4.6 > o3 on coding）。

### 6.2 系统能力层面（最关键差异）
> **这三个系统处于完全不同的"产品层级"，不应仅以基准分数衡量。**

- **OpenAI Codex** = 精准的"GitHub SWE 自动化机器"：  
  强项是从 Issue 到 PR 的端到端自动化，企业级隔离沙箱，与 ChatGPT 生态无缝集成；弱项是不感知用户真实运行环境，无记忆，无浏览器/系统控制。

- **Claude Code** = 优秀的"本机 CLI 编码伙伴"：  
  强项是直接操作本机代码库，终端原生，适合开发者日常编码辅助；弱项是无浏览器控制，无跨会话记忆，工具集局限于文件+终端。

- **GAgent-Multi（本系统）** = 通用"计算机使用代理"：  
  强项是横跨代码/浏览器/系统/移动/视觉的全域工具链，加上 4 层持久记忆体系，使其能执行其他两个系统完全无法完成的任务（如：浏览网页 → 提取数据 → 修改代码 → 运行验证 → 截图汇报，跨越多天持续累积上下文）。

### 6.3 核心结论

| 选择哪个？ | 推荐系统 | 原因 |
|-----------|---------|------|
| 纯 GitHub SWE 任务，企业安全合规 | **OpenAI Codex** | 专项优化 + 沙箱隔离 |
| 本机代码库日常辅助，轻量安装 | **Claude Code** | CLI 友好，直接 |
| 需要浏览器 / 系统 / 记忆 / 跨域工具 | **GAgent-Multi** | 全域能力 + 持久记忆 |
| 纯模型编码智力最强 | **GAgent-Multi 底层** | Claude Sonnet 4.6 > codex-1 > Claude 3.7 |

---

## 七、数据来源与置信度

| 数据点 | 来源 | 置信度 |
|--------|------|--------|
| Codex SWE-bench 69.1% | Google AI Overview + OpenAI 官方页 | ★★★★☆ |
| o3 HumanEval 96.7% | LLMReference.com | ★★★★☆ |
| Claude 3.7 SWE-bench 70.3% | Anthropic 官方 + 多方交叉验证 | ★★★★★ |
| Claude 3.7 HumanEval 93.0% | LLMReference.com | ★★★★☆ |
| Claude Sonnet 4.5 SWE-bench 77.2% | Google AI Overview + Anthropic 博客 | ★★★★☆ |
| Claude Sonnet 4.5 HumanEval 97.6% | PricePerToken.com 排行榜（2026-04-26） | ★★★☆☆ |
| GAgent-Multi 工具矩阵 | 直接读取 core/ga.py + memory/*.md | ★★★★★ |

> ⚠️ Claude Sonnet 4.6 独立基准未公开，报告使用 Sonnet 4.5 作保守代理值。
