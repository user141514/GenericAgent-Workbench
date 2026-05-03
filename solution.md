# GenericAgent Workbench — 问题清单与改进方案

> 生成时间: 2026-05-01
> 基于完整的项目代码分析、Git 状态审计、架构文档审查

---

## 一、项目现状概述

GenericAgent Workbench 是在经典 GenericAgent 内核之上的编排/观测/记忆/技能/产品层。

**核心指标**:
- 项目自身代码 ≈ 21,300 行（core/ 13,625行 + frontends/ 5,949行 + memory/ 1,535行）
- temp/ 目录含 389,670 行第三方代码（OpenHands, software-agent-sdk 等），非项目自身
- 双后端并行：classic executor（agentmain.py）+ OpenAI Agents（openai_agentmain.py）
- Git：仅 1 个 commit，branch 为 `codex/test-prev-version`
- 测试：**项目自身零测试**
- 文档：docs/ 有架构文档，无 API 文档/贡献指南

**当前阶段结论**（引自 docs/current_architecture_status.md）：
> 主路径已具备编排+执行+观测，部分 dry-run 底座已做好。**现在更需要封版、回归、清理和小重构，而不是继续扩 runtime 新能力。**

---

## 二、问题清单

### 🔴 高优先级（立即处理）

| # | 问题 | 描述 | 影响 |
|---|------|------|------|
| P1 | **API 密钥明文存储** | `mykey.py` 包含 DeepSeek v4 pro API key 明文 | 若误提交 Git 或共享工作区，密钥即刻泄露 |
| P2 | **零测试覆盖** | core/ 13,625 行代码无任何单元测试/集成测试 | 重构无安全网，回归风险极高 |
| P3 | **大量文件未纳入版本控制** | core/memory/, core/skills/, core/runtime/, core/quality/, core/tools/, docs/, ruff.toml, scripts/ 均为 untracked | 工作丢失风险，无法回溯 |
| P4 | **巨文件 openai_agentmain.py** | 113KB / 2,500+ 行，违反单一职责原则 | 维护困难，合并冲突频发，可读性差 |

### 🟡 中优先级（近期处理）

| # | 问题 | 描述 | 影响 |
|---|------|------|------|
| P5 | **Git 粒度太粗** | 仅 1 个 commit 覆盖所有模块变更 | 无法细粒度回滚，Code Review 无效 |
| P6 | **双后端一致性问题** | classic executor 与 OpenAI Agents 层并行，同步点不明确 | 功能重复，行为漂移风险 |
| P7 | **分支名不规范** | 分支名 `codex/test-prev-version` 含个人/测试标记，非标准命名 | 团队协作混乱 |
| P8 | **缺少贡献指南** | 无 CONTRIBUTING.md | 新人上手困难，贡献标准不一致 |
| P9 | **memory 双轨制** | memory/global_mem.txt（权威）+ core/memory/（辅助）并行 | 记忆来源不清晰，可能冲突 |

### 🟢 低优先级（持续改进）

| # | 问题 | 描述 | 影响 |
|---|------|------|------|
| P10 | **无 CI/CD 配置** | 无 GitHub Actions / GitLab CI 配置 | 测试无法自动运行 |
| P11 | **缺少版本号** | 项目无版本号定义（pyproject.toml 缺失 `version` 字段） | 无法发布/标记版本 |
| P12 | **tools_schema.json 外部依赖** | tools_schema 从 JSON 文件加载，修改不同步可导致运行时错误 | 模式与实现脱节风险 |
| P13 | **temp/ 目录未列入 .gitignore** | `.gitignore` 已排除 temp/，但大量第三方文件可能被误操作 | 仓库膨胀 |

---

## 三、改进方案（三阶段）

### Phase 1：安全止血 + Git 清理（1-2 天）

#### 1.1 API 密钥迁移

```bash
# 目标：将 mykey.py 的密钥移至环境变量 + .env.template
# 实施方案：
# 1. 创建 .env.template（无密钥值）
# 2. 修改 mykey.py 改为从 os.environ 读取
# 3. 将 .env 加入 .gitignore
# 4. 更新 README.md 添加环境变量说明
```

**具体代码修改**（mykey.py 替换方案）：
```python
import os
from dotenv import load_dotenv  # 若需要则添加到 requirements.txt
load_dotenv()

API_KEY = os.environ.get("GA_API_KEY")
BASE_URL = os.environ.get("GA_API_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("GA_MODEL", "deepseek-chat")
```

#### 1.2 Git 分支重整

```bash
# 目标：将单 commit 拆分为逻辑清晰的多个 commit，untracked 文件入库

# 方案 A — 新仓库重新组织（推荐，干净的历史）
git init   # 新仓库
# 按模块分批 add + commit，每模块一个 commit

# 方案 B — 在当前仓库整理
git checkout --orphan main-new
# 分批 add + commit
# 最后替换主分支
```

**建议 commit 拆分**：
1. `chore: 初始化项目结构和配置（.gitignore, ruff.toml, pyproject.toml）`
2. `feat: 核心 LLM 会话管理（llmcore.py, mykey.py）`
3. `feat: Classic executor 主循环（agentmain.py, agent_loop.py, ga.py）`
4. `feat: OpenAI Agents 路由层（openai_agentmain.py）`
5. `feat: 运行时优化模块（core/runtime/）`
6. `feat: 工具选择系统（core/tools/）`
7. `feat: 结构化记忆系统（core/memory/）`
8. `feat: 技能系统（core/skills/）`
9. `feat: 质量保障模块（core/quality/）`
10. `feat: Streamlit 前端界面（frontends/, launch.pyw）`
11. `docs: 架构文档与能力矩阵（docs/）`
12. `chore: 回归脚本（scripts/）`

#### 1.3 .gitignore 加固

```
# 在现有 .gitignore 基础上补充：
.env
mykey_local.py
*.log
temp/*.py
temp/*.json
```

---

### Phase 2：代码健康 + 测试基座（3-5 天）

#### 2.1 建立测试基础设施

```
tests/
├── conftest.py              # pytest 全局 fixture
├── unit/
│   ├── test_llmcore.py      # LLM 会话测试
│   ├── test_agent_loop.py   # 工具分发测试
│   ├── test_ga.py           # 工具实现测试
│   └── test_runtime/
│       ├── test_profiler.py
│       └── test_shortcut.py
├── integration/
│   └── test_agent_flow.py   # 完整 Agent 流程测试
└── fixtures/
    └── sample_tool_result.json
```

**pytest 配置**（pyproject.toml 补充）：
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short --cov=core --cov-report=term --cov-report=html"
```

**覆盖率目标**：
- Phase 2 目标：core/ 核心工具函数 ≥ 60%
- Phase 3 目标：core/ 全模块 ≥ 80%

#### 2.2 openai_agentmain.py 拆分

建议拆分方案：
```
core/
├── openai_agentmain.py      # 精简为主入口（~200 行）
├── agents/
│   ├── __init__.py
│   ├── router.py            # 路由逻辑
│   ├── planner.py           # 计划器
│   └── handoff.py           # 交接逻辑
└── openai_tools/
    ├── __init__.py
    ├── registry.py          # 工具注册
    ├── file_tools.py
    ├── web_tools.py
    └── memory_tools.py
```

#### 2.3 ruff lint 修复

```bash
# 当前 ruff.toml 已启用 E/F/I/W/UP/B，需运行：
ruff check core/ --fix
# 预期修复数百条 lint 警告

# 后续集成到 pre-commit
```

---

### Phase 3：架构优化 + 文档完善（3-5 天）

#### 3.1 双后端统一

```
目标：明确 classic executor 与 OpenAI Agents 层的职责边界

方案：
- classic executor → 工具执行引擎（稳定、不经常改动）
- OpenAI Agents → 编排/路由/规划层（实验性、快速迭代）
- 共享层 → core/runtime/, core/memory/, core/skills/
- 接口契约 → 由 core/runtime/ 定义工具执行的统一返回格式
```

#### 3.2 文档完善清单

```
docs/
├── README.md                  # 已存在，需补充开发指南链接
├── current_architecture_status.md  # 已存在
├── runtime_capability_matrix.md    # 已存在
├── CONTRIBUTING.md            # 新增：贡献指南（含代码规范、PR流程）
├── adr/                       # 新增：架构决策记录
│   ├── 001-use-dual-backend.md
│   ├── 002-structured-memory.md
│   └── 003-tool-schema-slim.md
├── api/                       # 新增：API 文档
│   ├── core-api.md
│   └── frontend-api.md
└── CHANGELOG.md               # 新增：变更日志
```

#### 3.3 CI/CD 配置

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.10' }
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-cov ruff
      - run: ruff check core/
      - run: pytest tests/ --cov=core/
```

---

## 四、优先级矩阵

```
                    影响大 ←——————————→ 影响小
                      │                    │
  紧急  ┌─────────────┼────────────────────┼─────────────┐
        │             │                    │             │
        │    🔴 P1 API密钥暴露            │             │
   ↑    │    🔴 P2 零测试覆盖             │             │
        │    🔴 P3 文件未入库             │             │
        │    🔴 P4 巨文件拆分             │             │
   ↓    ├─────────────┼────────────────────┼─────────────┤
        │             │                    │             │
        │             │   🟡 P5 Git粒度   │             │
  不紧   │             │   🟡 P6 双后端一致│             │
   急    │             │   🟡 P7 分支规范  │             │
        │             │   🟡 P8 贡献指南   │   🟢 P10 CI │
        │             │   🟡 P9 记忆双轨   │   🟢 P11 版本  │
        └─────────────┼────────────────────┼─────────────┘
                      │                    │
```

**执行顺序建议**：
1. **Phase 1** → P1（密钥迁移，立即执行）+ P3（untracked入库）可并行
2. **Phase 1** → P5/P7（Git重整）依赖 untracked 入库完成
3. **Phase 2** → P2（测试基座）+ P4（巨文件拆分）可并行
4. **Phase 2** → 运行 ruff --fix
5. **Phase 3** → P6/P8/P9/P10/P11 按需推进

---

## 五、预期效果

| 指标 | 当前 | Phase 1 后 | Phase 2 后 | Phase 3 后 |
|------|------|------------|------------|------------|
| 密钥安全 | ❌ 明文 | ✅ 环境变量 | ✅ 环境变量 | ✅ 环境变量 |
| 测试覆盖 | 0% | 0% | ≥60%（核心） | ≥80% |
| Git commits | 1 | 12+ 细分 | 12+ 细分 | 持续规范 |
| lint 通过率 | 未运行 | 未运行 | ✅ 零警告 | ✅ 零警告 |
| 文档完整性 | ⚠️ 基础 | ⚠️ 基础 | ✅ 有贡献指南 | ✅ 完整 |
| CI 自动运行 | ❌ | ❌ | ✅ 基础CI | ✅ 完整CI+CD |
| 巨文件 | 2,500+行 | 2,500+行 | ~200行入口 | ~200行入口 |

---

## 附录：快速修复脚本

### 密钥迁移脚本（save as scripts/migrate_env.py）

```python
#!/usr/bin/env python3
"""将 mykey.py 的配置迁移到 .env 文件"""
import os, sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
mykey_path = os.path.join(root, 'mykey.py')

if not os.path.exists(mykey_path):
    print("mykey.py not found, nothing to migrate")
    sys.exit(0)

# 读取 mykey.py
with open(mykey_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 提取键值对
import re
keys = {}
for m in re.finditer(r'^\s*(\w+)\s*=\s*["\'](.+?)["\']\s*$', content, re.MULTILINE):
    keys[m.group(1)] = m.group(2)

# 创建 .env
env_path = os.path.join(root, '.env')
with open(env_path, 'w', encoding='utf-8') as f:
    f.write("# GenericAgent Workbench API Configuration\n")
    f.write("# Copy this to .env and fill in your actual keys\n")
    f.write("# NEVER commit .env to git\n\n")
    for k, v in keys.items():
        f.write(f"{k}={v}\n")

# 备份 mykey.py
backup = mykey_path + '.bak'
os.rename(mykey_path, backup)
print(f"Migrated {len(keys)} keys from mykey.py to {env_path}")
print(f"Original backed up to {backup}")
print("Now modify core/llmcore.py to read from os.environ instead of mykey.py")
```