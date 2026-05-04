# GAgent-Multi 项目提升计划
> 生成日期：2026-05-04  
> 基于：代码图分析（792节点/1824边）、git状态、eval报告、架构文档、历史蒸馏记录  
> **现有计划**：`coding-improve.md`（2026-05-03，聚焦编码过程规范）  
> **本计划**：聚焦项目健康度、架构演进、产品方向，与编码过程计划互补

---

## 🏥 一、项目体检报告（现状快照）

### 1.1 技术栈全景

| 层次 | 技术 | 状态 |
|---|---|---|
| **前端** | Streamlit 1305行 + Qt 1764行 + 桌面宠物 + 多Bot平台 | ✅ 可用，但文件巨大 |
| **编排层** | openai_agentmain.py (140KB！) | ⚠️ God File，亟需拆分 |
| **执行内核** | GenericAgent (ga.py 600行 + agent_loop.py 585行) | ✅ 稳定核心 |
| **LLM接入** | llmcore.py (71KB!) + OpenAI兼容API | ⚠️ 单文件过重 |
| **运行时观测** | profiler / direct_answer / read_shortcut / early_stop | ✅ 基础设施完整 |
| **技能系统** | skill_discovery / skill_registry / skill_effects | 🔴 多项仅dry-run |
| **记忆系统** | memory/*.md (旧) + core/memory/SQLite (新) | ⚠️ 双路径不互通 |
| **测试** | 215个测试（全部未提交）+ 路由评估100% | ⚠️ 未入版本控制 |

### 1.2 量化健康指标

```
✅ 路由精度：100% (12/12) — 但样本量仅12条
✅ 测试数量：215 个 pytest case（可采集但全部 untracked）
⚠️ Git 卫生：27个未提交文件（11测试 + 5文档 + 5记忆SOP + 6其他）
⚠️ 代码规模：openai_agentmain.py 140KB / llmcore.py 71KB（单文件过大）
⚠️ 集成测试：tests/integration/ 完全为空
🔴 未激活能力：ExecutionPolicy / SkillEffects / LLM Cache Reuse / read_prefetch 均仅dry-run
🔴 技术债清单：stapp.py有backup文件 + stapp2.py并存 + 大量demo_*.py散落core/
```

### 1.3 God Nodes 风险矩阵

| 节点 | 边数 | 风险 | 当前处理 |
|---|---|---|---|
| GeneraticAgent | 37 | 极高 | ✅ 已识别，有围栏规则 |
| TMWebDriver | 31 | 极高 | ✅ 已识别 |
| MemoryStore | 28 | 高 | ⚠️ 仅Classic路径使用 |
| GenericAgentHandler | 28 | 高 | ⚠️ 工具分发枢纽 |
| **openai_agentmain** | 估算 50+ | **极高** | 🔴 未识别/未拆分 |

---

## 🎯 二、提升优先级矩阵

```
         高紧迫性
             │
P0区域 ──────┼────── P1区域
(立即做)     │     (本月内)
             │
低影响力 ────┼──────────── 高影响力
             │
P3区域 ──────┼────── P2区域
(观察期)     │     (季度目标)
             │
         低紧迫性
```

---

## 🚨 三、P0：本周内必须完成（阻塞项）

### P0-1：Git 卫生紧急修复

**问题**：215个测试和多份关键文档处于未追踪状态，若环境损坏将丢失。

```bash
# 执行步骤
git add tests/unit/ tests/evaluation/ tests/fixtures/
git add docs/runtime_regression_runner.md docs/wechat_article_draft.md
git add memory/streamlit_pitfalls.md memory/graphify_usage.md
git add coding-improve.md
git commit -m "chore: add untracked test suite, docs, and memory SOPs (215 tests)"

# 验证
git status  # 应只剩 Modified 文件
```

**估时**：15分钟  
**验证标准**：`git status` 无 `??` 行

---

### P0-2：Modified 文件审查并提交

**问题**：6个已修改但未提交的文件（memory SOPs、conftest.py、docs）。

```bash
# 先 diff 确认修改内容
git diff memory/autonomous_operation_sop.md
git diff memory/coding_karpathy_sop.md
git diff tests/conftest.py

# 分批提交（按功能隔离）
git add memory/autonomous_operation_sop.md memory/coding_karpathy_sop.md \
    memory/ljqCtrl_sop.md memory/tmwebdriver_sop.md
git commit -m "docs(memory): update SOPs with learnings from recent sessions"

git add tests/conftest.py
git commit -m "test: update conftest with latest fixtures"

git add docs/deepseek_migration_report.md
git commit -m "docs: update deepseek migration report"
```

**估时**：30分钟  
**验证标准**：`git status` 仅显示 `mykey.py`（预期忽略）

---

### P0-3：运行 215 个单元测试，建立基准

**问题**：从未知道这些测试实际通过率是多少。

```bash
cd F:\GAgent-Multi
python -m pytest tests/unit/ -v --tb=short 2>&1 | tee temp/pytest_baseline_$(date +%Y%m%d).txt

# 期望看到
# PASSED: xxx / 215
# FAILED: 0（理想）或记录失败列表
```

**估时**：5分钟  
**验证标准**：有明确的 PASSED/FAILED 数字，存档为基准

---

## 📋 四、P1：本月内完成（架构健康）

### P1-1：拆分 openai_agentmain.py（140KB God File）

**问题**：140KB 的单文件是架构最大风险点，任何修改都可能引发连锁故障。

**拆分方案**：
```
core/openai_agentmain.py (140KB) →
├── core/orchestration/router.py        ← RouterRules + task_router
├── core/orchestration/planner.py       ← planner_executor + handoff逻辑  
├── core/orchestration/chat.py          ← chat_specialist + 对话管理
├── core/orchestration/context.py       ← planner-local context拼装
├── core/orchestration/audit.py         ← profiler / llm audit 汇总
└── core/openai_agentmain.py (保留)     ← 仅入口 + 组装，<100行
```

**执行原则**：
- 每次只移动一个类/函数，立即跑 pytest 验证
- 保持原入口不变（外部调用方无感知）
- 每小步做一个 commit

**估时**：2-3天  
**验证标准**：pytest 215/215 PASS，eval_runner 路由精度不低于100%

---

### P1-2：拆分 llmcore.py（71KB）

**当前状态**：LLM 调用核心 71KB，混合了模型调用、流式处理、工具schema、错误重试等逻辑。

**拆分方案**：
```
core/llmcore.py (71KB) →
├── core/llm/client.py      ← API 调用、重试、超时
├── core/llm/streaming.py   ← 流式处理、SSE解析
├── core/llm/schema.py      ← 工具 schema 生成和变换
└── core/llm/fallback.py    ← 降级和错误处理策略
```

**估时**：3天  
**验证标准**：功能回归测试 + 流式响应正常

---

### P1-3：清理 demo_*.py 文件

**问题**：core/runtime/ 和 core/skills/ 下散落 **16个 demo_\*.py** 文件，占据代码空间但不在生产路径。

```bash
# 统计
find core/ -name "demo_*.py" | wc -l  # 应为16

# 决策：移入 examples/ 目录（不删除）
mkdir -p examples/runtime examples/skills
git mv core/runtime/demo_*.py examples/runtime/
git mv core/skills/demo_*.py examples/skills/
git mv core/memory/demo_*.py examples/
git commit -m "refactor: move demo files to examples/ directory"
```

**估时**：1小时  
**验证标准**：core/ 下无 demo_ 前缀文件，pytest 不受影响

---

### P1-4：激活 LLM Cache（llm_cache.py）

**当前状态**：基础设施已完成（`core/runtime/llm_cache.py` 14KB），但 `get/set` 未启用。

**收益**：相同查询重复调用成本归零，开发调试提速显著。

**激活步骤**：
```python
# 在 core/llm/client.py（拆分后）或当前 llmcore.py 中：
# 1. 读取环境变量开关
CACHE_ENABLED = os.getenv('GENERIC_AGENT_LLM_CACHE', '0') == '1'

# 2. 在 LLM 调用前检查缓存
if CACHE_ENABLED:
    cached = llm_cache.get(prompt_hash)
    if cached:
        return cached

# 3. 调用后写入缓存
if CACHE_ENABLED:
    llm_cache.set(prompt_hash, response)
```

**验证**：相同 prompt 第二次调用延迟 <5ms（对比首次 500-2000ms）  
**估时**：半天

---

### P1-5：前端文件整理

**当前问题**：
- `frontends/stapp.py.backup_20260423_125602`：备份文件混入版本控制
- `frontends/stapp2.py`：另一个版本并存，用途不明
- 两者加起来约 91KB，维护成本翻倍

**处理方案**：
```bash
# 明确 stapp2.py 的定位
# 选项A：如果是实验版，移入 temp/ 
# 选项B：如果是重构版，作为 feat/stapp-v2 分支
# 无论如何：
git rm frontends/stapp.py.backup_20260423_125602
git commit -m "chore(frontend): remove stale backup file"
```

**估时**：30分钟决策 + 执行

---

### P1-6：扩充路由基准测试集（12条 → 50条）

**当前问题**：12条评估样本覆盖不足，100%精度存在虚高风险。

**补充维度**：
```python
# 在 tests/evaluation/benchmark_queries.py 追加：

# 边界场景（10条）
{"id": "edge-01", "query": "", "target": "chat"},              # 空输入
{"id": "edge-02", "query": "   ", "target": "chat"},           # 纯空格
{"id": "edge-03", "query": "a" * 5000, "target": "chat"},      # 超长输入

# 歧义场景（10条，最能暴露路由弱点）
{"id": "ambig-01", "query": "帮我看看这个代码", "target": "review"},
{"id": "ambig-02", "query": "分析一下", "target": "research"},   # 纯歧义词

# 多语言（5条）
{"id": "lang-01", "query": "Write a function", "target": "code"},
{"id": "lang-02", "query": "Please review my code", "target": "review"},

# 否定场景（5条）
{"id": "neg-01", "query": "不用帮我写代码，只要解释", "target": "chat"},
```

**估时**：半天  
**验证标准**：50条精度 ≥ 92%（允许少量歧义样本失败）

---

## 🏗️ 五、P2：季度目标（架构演进）

### P2-1：激活 read_prefetch 到实际上下文注入

**当前**：`read_prefetch.py` 仅做 observe-only（7.4KB），检测出需要预读的文件但不注入。  
**目标**：当检测到任务需要读某文件时，在 LLM 调用前自动预加载到上下文。

**预期收益**：减少 agent 的 "先读文件" 往返轮次，降低任务步骤数 20-30%。

**实施路径**：
```
Phase 1: 统计 read_prefetch 实际命中率（1周 observe 数据）
Phase 2: 在命中率 > 70% 的场景启用注入（A/B 测试）
Phase 3: 全场景启用，monitor 上下文窗口增长
```

---

### P2-2：统一记忆架构（消除双路径）

**当前**：
- Classic 路径：`memory/*.md` → `get_global_memory()` → system_prompt 注入
- OpenAI 路径：`instructions` 静态文本，无记忆调用，无蒸馏

**目标**：两条路径共享同一记忆读取层。

**实施方案**：
```python
# 新增 core/memory/reader.py
class MemoryReader:
    def get_context_for_session(self, session_id: str) -> str:
        """统一接口：Classic和OpenAI路径都调用这里"""
        # 1. 读 global_mem_insight.txt + global_mem.txt（现有Classic逻辑）
        # 2. 查 SQLite store（现有但未接入OpenAI路径）
        # 3. 返回融合结果
```

**估时**：1周  
**依赖**：P1-1（先拆分 openai_agentmain.py）

---

### P2-3：ExecutionPolicy 从 dry-run 到 enforcement

**当前**：`execution_policy.py`（7.8KB）只做 merge/preview，不影响实际执行。  
**目标**：针对高风险操作（文件删除、系统命令、网络请求）实施沙箱策略。

**分阶段激活**：
```
Phase 1: 只在 read-only 模式下限制写操作（最安全，影响范围小）
Phase 2: 文件操作白名单（只允许在 temp/ 和项目目录内）
Phase 3: 完整权限沙箱
```

---

### P2-4：SkillEffects 接入运行时

**当前**：`skill_effects.py`（3.8KB）只定义 metadata，不影响 runtime。  
**目标**：当技能被激活时，其 side effects（如"会修改文件"、"会调用网络"）应被纳入 ExecutionPolicy 决策。

**实施**：在 SkillActivation → ExecutionPolicy 之间建立数据流链路。

---

### P2-5：集成测试覆盖（tests/integration/ 当前为空）

**补充方向**：
```python
# tests/integration/test_e2e_router.py
def test_full_pipeline_chat():
    """端到端：chat 路由 → chat_specialist → 返回文本"""
    
def test_full_pipeline_code():
    """端到端：code 路由 → planner → classic executor → 代码输出"""

def test_handoff_classic():
    """OpenAI层 handoff → Classic执行内核 → 结果回传"""
    
# tests/integration/test_memory_persistence.py  
def test_memory_survives_session_restart():
    """记忆在会话重启后仍可检索"""
```

---

## 🌟 六、P3：长期方向（3个月+）

### P3-1：Skill 真正变成可执行 Runtime Policy

当前 Skill 系统（发现→加载→注入SOP文本）只停留在"提示词工程"层面。  
长期目标：Skill 可以定义工具集、权限边界、执行预算，真正约束 agent 行为。

```python
# 目标 API（概念）
@skill("code_review")
def review_task(agent: Agent, code: str):
    agent.tools = ["file_read", "web_search"]     # 限制工具
    agent.max_steps = 10                           # 限制步数
    agent.write_budget = 0                         # 禁止写文件
    return agent.run(f"Review: {code}")
```

---

### P3-2：多 Bot 平台统一适配层

**当前**：Telegram / 飞书 / 企业微信 / 钉钉 / QQ 各自实现，代码高度重复。  
**目标**：提取 `frontends/chatapp_common.py` 为正式的 Bot Platform Abstraction Layer。

```python
# 目标接口
class BotAdapter(ABC):
    async def send_message(self, chat_id: str, text: str): ...
    async def send_file(self, chat_id: str, file: bytes): ...
    async def on_message(self, handler: Callable): ...

class TelegramAdapter(BotAdapter): ...
class FeishuAdapter(BotAdapter): ...
class WeComAdapter(BotAdapter): ...
```

---

### P3-3：观测数据驱动的自动优化

基于已有的 `RuntimeProfiler` + `LLM Audit` 数据，建立自动报告：
- 哪些请求步骤数最多？（优化候选）
- 哪些工具调用最频繁？（工具优化）
- 哪些 read_prefetch 命中？（预读策略调整）

---

### P3-4：移动端支持

`README` 提到"前端密码锁暂时关闭（移动端还没上线）"。  
规划路径：Streamlit Cloud 部署 → 响应式 UI → PWA 缓存 → 轻量移动入口。

---

## 📊 七、成效追踪仪表盘

### 可测量指标

| 指标 | 当前值 | P0后目标 | P1后目标 | 测量命令 |
|---|---|---|---|---|
| Git未追踪文件数 | 27 | 0 | 0 | `git status --short \| grep "??" \| wc -l` |
| 单元测试通过率 | 未知 | 215/215 | 215/215 | `pytest tests/unit/` |
| 路由评估精度 | 100%/12条 | 100%/12条 | ≥92%/50条 | `python -m tests.evaluation.eval_runner` |
| openai_agentmain.py行数 | ~3000行 | ~3000行 | <200行(入口) | `wc -l core/openai_agentmain.py` |
| 返工次数（主观） | ~2次/任务 | — | ≤1次/任务 | history_memory_inbox统计 |
| LLM缓存命中率 | 0% | 0% | >30% | profiler输出 |

### 月度回顾 Checklist

```bash
# 每月第一个工作日执行
echo "=== 月度健康检查 $(date +%Y-%m) ===" 

# 1. Git 卫生
git status --short | grep "??" | wc -l  # 应为0

# 2. 测试基准
python -m pytest tests/unit/ -q 2>&1 | tail -5

# 3. 路由精度
python -m tests.evaluation.eval_runner 2>&1 | tail -3

# 4. 代码规模趋势
wc -l core/openai_agentmain.py core/llmcore.py core/ga.py

# 5. 未激活能力状态
grep -r "dry-run\|concept only" docs/current_architecture_status.md | wc -l
# 目标：这个数字每月递减
```

---

## 🗺️ 八、执行路线图

```
Week 1 (本周)
├── P0-1: Git 卫生修复 (27个untracked → 0)
├── P0-2: Modified文件分批提交
└── P0-3: 跑 215 个测试，建立基准

Week 2-3
├── P1-1: 开始拆分 openai_agentmain.py (140KB)
│         分步：router → planner → chat → context → audit
├── P1-3: 清理 demo_*.py 到 examples/
└── P1-5: 前端备份文件和 stapp2.py 决策

Week 4
├── P1-4: 激活 LLM Cache（GENERIC_AGENT_LLM_CACHE=1）
├── P1-6: 扩充路由基准测试（12条 → 50条）
└── P1-2: 开始拆分 llmcore.py (71KB)

Month 2
├── P2-1: read_prefetch A/B 实验
├── P2-5: 补充集成测试
└── P2-2: 记忆架构统一（需P1-1完成）

Month 3
├── P2-3: ExecutionPolicy Phase 1 激活
├── P2-4: SkillEffects 接入
└── 首次完整月度健康检查
```

---

## 🔑 九、与现有 coding-improve.md 的分工

| 维度 | coding-improve.md | 本计划 |
|---|---|---|
| **聚焦层次** | 编码过程规范（每次改动怎么做） | 项目健康度和架构演进（改什么） |
| **时间维度** | 每次编码任务即时执行 | 周/月/季度规划 |
| **核心输出** | 前置检查清单 + 验证铁律 | 优先级矩阵 + 执行路线图 |
| **God Node 处理** | 告诉你改 God Node 时怎么操作 | 告诉你应该先拆 God Node |
| **记忆系统** | 如何安全修改 memory/*.md | 如何统一双路径记忆架构 |
| **测试** | 每次改动后跑什么测试 | 整个测试基础设施如何建设 |

**两份计划的执行关系**：  
本计划定义**做什么**和**做的顺序** → `coding-improve.md` 定义**怎么做** → 共同指导每次编码行动。

---

## ⚡ 十、最小可行行动（今天就能做的3件事）

1. **`git add tests/unit/ tests/evaluation/ && git commit`** — 10分钟，消除最大数据丢失风险
2. **`python -m pytest tests/unit/ -q`** — 5分钟，第一次看到项目真实健康状态  
3. **读 `core/openai_agentmain.py` 前100行** — 了解 God File 的实际结构，为拆分做准备

---

> *计划是地图，行动是引擎。地图再好，不走也是白纸。*  
> 优先做 P0，哪怕 P1/P2/P3 一个都没做，完成 P0 也让项目安全了一个数量级。