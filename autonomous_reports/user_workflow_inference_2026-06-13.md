# 用户工作流推断与个性化推荐

**日期**: 2026-06-13  
**数据来源**: dotfiles、Conda环境、Edge书签(587项)、PowerShell历史(24条)、Git仓库(12个)、桌面文件、下载记录

---

## 一、用户画像推断

### 核心身份：AI基础设施开发者
**置信度**: 高  
**证据链**:
- 12个Git仓库中6个直接涉及AI/LLM: LightRAG(图RAG)、mempalace(记忆系统)、nature-skills(技能库)、rig-agent-local-demo(Rust Agent)、open-design、GenericAgent(本仓库)
- PowerShell历史全为Claude Code运维: 配置deepseek模型、安装ruflo MCP、重装Git支持
- 桌面快捷方式: GenericAgent Desktop(本项目)
- 下载记录: Codex客户端、ChatGPT Installer

### 次要身份：公司方案开发工程师
**置信度**: 中高  
**证据链**:
- `E:\company_work\`下有 `1/3/demo/demo2/demo3/demo3-master` 迭代式开发
- 桌面文件: `月报.docx`（月度报告）
- 下载: `argument-comment-lint`（代码审查工具）

### 技能域覆盖
| 领域 | 环境/证据 | 深度 |
|------|----------|------|
| AI Agent开发 | GenericAgent, rig-agent-demo, Claude Code, ruflo MCP | ⭐⭐⭐⭐⭐ |
| LLM记忆/RAG | mempalace, LightRAG, nature-skills, history_memory_inbox | ⭐⭐⭐⭐ |
| Python数据科学 | 16个conda环境(ds_env, torch311, rag-env等) | ⭐⭐⭐⭐ |
| 化学信息学 | new_rdkit, Pocket2Mol | ⭐⭐⭐ |
| Rust | `rust学习\rig-agent-local-demo` | ⭐⭐ |
| C/C++ | VS Code g++/cmake/Ninja配置, msys64 | ⭐⭐ |
| Android自动化 | MuMu模拟器, ALAS | ⭐⭐ |
| 扩散模型 | diffusion_model conda环境 | ⭐⭐ |

---

## 二、日常Workflow推断

### 工作流A: «公司方案开发» (高频)
```
启动Edge → 打开项目文档 → VS Code编写demo → conda activate accfg_
→ Python测试 → Git提交 → 月报更新
```
- 工作目录: `E:\company_work\`
- 环境: `accfg_migrated` / `accfg` conda env
- 模式: 迭代demo (demo→demo2→demo3)

### 工作流B: «LLM Agent开发» (高频)
```
启动Streamlit前端(launch.pyw) → 浏览器交互 → agent执行 →
查看history/model_responses → 记忆蒸馏(start_long_term_update)
→ 分析结果 → 修改agent代码 → 重启测试
```
- 工作目录: `F:\GAgent-Multi`
- 环境: `rag-env` conda env (Streamlit 296MB运行时)

### 工作流C: «技术学习/探索» (中频)
```
Edge搜索 → 菜鸟教程/博客园 → VS Code实验 → Git记录
```
- 书签偏好: 菜鸟教程(C/C++/R/VBScript)、博客园、Google搜索技巧
- Rust实验: `E:\rust学习\`

### 工作流D: «运维/工具安装» (周期)
```
PowerShell → winget/npm → conda → 环境配置 → 测试
```
- 近期活动: 重装Git、卸载/重装Claude Code、配置ruflo MCP

---

## 三、环境熵点识别

### 🔴 高优先级清理

| 问题 | 详情 | 建议 |
|------|------|------|
| **3 Streamlit进程** | PID 17672/93644/104488 同时运行 | 终止冗余进程 (PID 104488)，统一启动入口 |
| **双conda路径** | D:\anaconda0 + E:\Anaconda3 并存 | 合并为单一路径，迁移env |
| **company_work碎片** | demo/demo2/demo3/demo3-master 迭代遗留 | 归档旧版本，保留最终版 |

### 🟡 中等关注

| 问题 | 建议 |
|------|------|
| `.bashrc`引用E:\Anaconda3但conda实际可能从D:\anaconda0启动 | 统一conda init路径 |
| PowerShell历史仅24条 | 可能清过或使用频率低；启用PSReadLine持久化 |

---

## 四、个性化自动化推荐

### 推荐1: 一键环境激活脚本 🥇
**目标**: 消除 `conda activate` + `cd` 的多步操作

```batch
@echo off
REM GAgent.bat — 一键启动GenericAgent工作环境
cd /d F:\GAgent-Multi
call conda activate rag-env
start python launch.pyw
```

### 推荐2: company_work归档整理 🥈
**目标**: 清理迭代demo碎片

```powershell
# 创建归档目录
mkdir E:\company_work\_archive
# 移动旧版本
Move-Item E:\company_work\demo E:\company_work\_archive\demo_v1
Move-Item E:\company_work\demo2 E:\company_work\_archive\demo_v2
```

### 推荐3: 月报模板自动化 🥉
**目标**: 减少月报.docx的手动编写

基于Git log自动生成月度活动摘要：
```bash
git log --since="last month" --pretty=format:"- %s (%ar)" > monthly_report.txt
```

### 推荐4: Edge书签去重整理
587条书签中存在大量失效链接和重复，建议用Edge内置"清理书签"功能去重。

### 推荐5: Conda环境快照
16个conda环境建议定期导出environment.yml：
```bash
conda env export -n rag-env > F:\GAgent-Multi\envs\rag-env.yml
```

---

## 五、风险提示

1. **进程泄漏**: 3个Streamlit进程长期运行可能导致系统资源耗尽
2. **环境漂移**: 双conda路径+不导出environment.yml → 环境不可复现
3. **书签通胀**: 587条书签未整理 → 信息检索效率下降
4. **数据散落**: company_work多版本 → 版本混乱风险
