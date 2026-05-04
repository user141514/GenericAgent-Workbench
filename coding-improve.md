# coding-improve.md
# 编码能力提升计划（详细版）

> 写于 2026-05-03 | 基于项目代码图分析(792节点/1824边)、历史蒸馏记录、karpathy准则及skill_best_practices
> **目标**：减少返工，提升首次正确率，让每次修改可验证、可追溯、可回归

---

## 一、问题诊断（基于真实历史数据）

### 1.1 高频返工模式（来自 history_memory_inbox.md）

| 返工事件 | 次数 | 根因 |
|---------|------|------|
| Streamlit弹窗逻辑 | **4次** | 动手前未查 `streamlit_pitfalls.md`；fragment作用域理解错误 |
| 前端改动方向错误 | 2次 | 需求确认不足，静默假设了需求 |
| state key冲突 | 2次 | 没有幂等性测试，改完即报告完成 |

### 1.2 架构风险（来自 graphify GRAPH_REPORT.md）

```
God Nodes（改动波及范围最广，最危险）:
- GeneraticAgent     → 37条边（核心执行器，牵一发动全身）
- TMWebDriver        → 31条边（浏览器层，变更影响巨大）
- MemoryStore        → 28条边（仅对Classic路径生效）
- GenericAgentHandler→ 28条边（工具分发枢纽）
```

**核心教训**：系统工具和基础设施已足够完善，问题在于**现有规则没有在每次行动中被强制执行**。

---

## 二、什么绝对不动（手术式修改原则）

> 来源：coding_karpathy_sop §3 "手术式修改"
> **原则：每一行修改都必须能追溯到用户的明确请求。**

### 2.1 绝对禁止的"顺手"行为

```
❌ 不顺手重构相邻代码（哪怕看起来更优雅）
❌ 不改注释格式（除非注释本身是任务目标）
❌ 不升级函数签名或返回值（除非明确被要求）
❌ 不删除"看起来没用"的死代码（提一下，但不删）
❌ 不在未被要求时添加日志/print/错误处理
❌ 不做"灵活性"抽象（单次使用的代码不抽象）
```

### 2.2 绝对不碰的核心文件（除非任务直接指向）

| 文件 | 原因 | 改动需要 |
|------|------|---------|
| `core/agent_loop.py` | God Node，28+条边，改动影响全局 | 用户明确指定 + 写测试验证 |
| `core/ga.py` | 核心执行器，所有工具分发在此 | 同上 |
| `memory/*.md` | 记忆系统，格式破坏会影响注入 | 必须用 `file_patch`，不能覆写 |
| `core/TMWebDriver.py` | 浏览器层，31条边 | 同上 |
| `agentmain.py` / `openai_agentmain.py` | 入口文件 | 明确需求 + 回归测试 |

### 2.3 安全的修改区域

```
✅ 可安全修改（相对隔离）：
- frontends/stapp.py（但必须查 streamlit_pitfalls 前置）
- memory/history_memory_inbox.md（仅追加，不覆写）
- tests/unit/*.py（新增测试不影响现有）
- tests/evaluation/benchmark_queries.py（新增query不影响现有）
- 任何 temp/ 下的实验性文件
```

### 2.4 改动孤儿处理规则

> 当我的修改导致某个 import/variable/function 成为孤儿（无调用者）时：
> - **必须删除**：我自己引入的孤儿代码
> - **不得删除**：已存在的孤儿代码（除非被明确要求清理）

---

## 三、编码前置流程（动手前的强制检查）

> 来源：coding_karpathy_sop §1 "动手前思考"

### 3.1 前置检查清单（每次编码任务开始时执行）

```
□ 1. 读现有代码，再改（禁止盲改）
     → 用 file_read 确认当前状态，不靠记忆
     
□ 2. 显式陈述假设
     → "我假设 X 是 Y，如果不是请告知"
     → 有多种理解时，全部呈现，不静默选择
     
□ 3. 场景前置查阅
     → 涉及 Streamlit 前端 → 必读 memory/streamlit_pitfalls.md
     → 涉及浏览器操作   → 必读 memory/tmwebdriver_sop.md
     → 涉及键鼠控制     → 必读 memory/ljqCtrl_sop.md
     → 涉及多步骤复杂任务→ 必读 memory/plan_sop.md
     
□ 4. 影响范围估计
     → 改动是否触及 God Nodes？（见2.2）
     → 改动是否跨越模块边界？
     → 改动是否会影响调用者？（grep确认调用点）
     
□ 5. 定义可验证的成功标准
     → ❌ "让它工作"（弱标准）
     → ✅ "按钮点击后显示X，state key为Y，不影响Z功能"（强标准）
```

### 3.2 接口变更强制规则

```python
# 改函数签名或返回值前，必须先 grep 所有调用点
# 示例：修改前确认
grep -r "function_name(" --include="*.py" ../
# 然后决定：同步修改所有调用点，或提供兼容层
```

---

## 四、验证铁律（分层验证体系）

> 来源：coding_karpathy_sop §5 "验证铁律"
> **核心原则：无工具输出的PASS = SKIP。读代码不是验证。**

### 4.1 验证分层

```
Level 1：语法验证（最快，1秒内）
    → python -c "import ast; ast.parse(open('file.py').read())"
    → 用于：所有 .py 文件修改后

Level 2：功能验证（快速，执行关键路径）
    → 直接运行被改动的函数/模块
    → 看 stdout/stderr/exit code
    → 用于：所有逻辑修改

Level 3：对抗性探测（中速，边界场景）
    → 边界值（空/None/超长/unicode/特殊字符）
    → 幂等性（同一操作执行两次结果一致）
    → 缺失依赖（文件不存在/API不可达）
    → 用于：核心工具函数、数据处理逻辑

Level 4：回归测试（较慢，防止破坏现有功能）
    → pytest tests/unit/  （单元测试套件）
    → python -m tests.evaluation.eval_runner （路由精度评估）
    → 用于：任何改动 core/ 下文件之后
```

### 4.2 验证自检清单（编码后执行）

```
□ 每一步都有命令的实际输出？（不是代码读着对就算）
□ 执行了语法验证？
□ 执行了功能验证？（看到了真实的 stdout）
□ 跑了至少一个对抗性探测？
□ 幂等性：同一操作两次结果一致？
□ 没有破坏现有功能？（关联路径测试）
```

### 4.3 场景专项验证规范

#### 前端（Streamlit）修改后
```python
# 验证1：语法检查
python -c "import ast; ast.parse(open('../frontends/stapp.py').read()); print('OK')"

# 验证2：导入检查（不需要启动完整前端）
cd ../ && python -c "import frontends.stapp" 2>&1

# 验证3：fragment/state key 检查（人工）
# → 搜索所有 st.dialog 定义位置，确认在 @st.fragment 内且在 for 循环之前
# → 搜索所有 session_state 的 key，确认无重复前缀冲突
```

#### 核心逻辑（core/）修改后
```bash
# 验证1：单元测试
cd ../ && python -m pytest tests/unit/ -v --tb=short 2>&1

# 验证2：路由精度评估
cd ../ && python -m tests.evaluation.eval_runner 2>&1

# 验证3：agent_loop 基础功能
cd ../ && python -c "from core.agent_loop import BaseHandler, StepOutcome; print('agent_loop OK')"
```

#### 记忆系统（memory/）修改后
```bash
# 验证1：L1 Insight 与 L2 同步检查（人工核对）
# → 读 global_mem_insight.txt，确认索引与 global_mem.txt 实际内容一致
# → 任何新增 SOP 文件必须在 L1 中有对应索引条目

# 验证2：格式检查（SOP文件）
python -c "
content = open('../memory/xxx_sop.md', encoding='utf-8').read()
assert '##' in content, 'Missing section headers'
print('Format OK')
"
```

---

## 五、测试策略

### 5.1 现有测试资产盘点

```
tests/unit/
├── test_agent_comparison.py   ← baseline vs refined 路由对比
├── test_agent_graph.py        ← Agent图结构测试
├── test_dynamic_graph.py      ← 动态图测试
├── test_parallel.py           ← 并行执行测试
├── test_pipeline.py           ← 流水线测试
├── test_protocol_compat.py    ← 协议兼容性测试
├── test_router_rules.py       ← 路由规则测试
└── test_shared_store.py       ← 共享存储测试

tests/evaluation/
├── eval_runner.py             ← 路由精度 + LLM端到端评估
├── benchmark_queries.py       ← 标准测试用例集（4类：code/review/research/chat）
└── eval_report.json           ← 当前评估快照
```

### 5.2 测试运行规范

#### 日常快速验证（<30秒）
```bash
# 仅跑路由规则相关（最快）
cd ../ && python -m pytest tests/unit/test_router_rules.py tests/unit/test_agent_comparison.py -v

# 路由精度评估（无需LLM，快速）
cd ../ && python -m tests.evaluation.eval_runner
```

#### 改动 core/ 后必跑（<2分钟）
```bash
# 全部单元测试
cd ../ && python -m pytest tests/unit/ -v --tb=short

# 顺便跑评估对比，留存结果
cd ../ && python -m tests.evaluation.eval_runner > temp/eval_$(date +%Y%m%d_%H%M%S).txt 2>&1
```

#### 重大架构改动后（完整回归）
```bash
# 含 LLM 端到端（需要 API Key，慢）
cd ../ && python -m tests.evaluation.eval_runner --llm
```

### 5.3 缺失测试的补充策略

> 当前 benchmark_queries 缺失以下维度，遇到对应场景时应**先写测试再改代码**：

| 缺失维度 | 补充到哪 | 优先级 |
|---------|---------|-------|
| 幂等性测试（同操作两次） | `tests/unit/test_idempotency.py` | P1 |
| 边界输入（空/超长/unicode） | 追加到 `benchmark_queries.py` | P1 |
| 多轮对话记忆连续性 | `tests/unit/test_memory_continuity.py` | P2 |
| 工具权限边界（不该用的工具被拒绝） | `tests/unit/test_tool_permissions.py` | P2 |

**原则：新写测试时，只追加新 case，不修改已有 case。**

### 5.4 评估结果时序存档（防止退化）

```bash
# 每次重大改动后，存档评估结果用于对比
# 当前 eval_report.json 是单次快照，应改为时序存档

# 临时方案（不改eval_runner代码）：
cd ../ && python -m tests.evaluation.eval_runner
cp tests/evaluation/eval_report.json tests/evaluation/eval_report_$(date +%Y%m%d).json

# 对比两次结果：
python -c "
import json
old = json.load(open('tests/evaluation/eval_report_20260503.json'))
new = json.load(open('tests/evaluation/eval_report.json'))
print(f'Route accuracy: {old[\"route_accuracy\"]:.2%} → {new[\"route_accuracy\"]:.2%}')
print(f'Avg latency: {old[\"avg_latency_ms\"]:.1f}ms → {new[\"avg_latency_ms\"]:.1f}ms')
"
```

---

## 六、高频场景的操作规范

### 场景A：修改 Streamlit 前端

```
Step 1: file_read streamlit_pitfalls.md          ← 必读，不可跳过
Step 2: file_read frontends/stapp.py (相关区域)  ← 了解现状
Step 3: 显式确认：这次改动是否涉及 dialog/fragment/session_state？
Step 4: 手术式修改（只改目标区域）
Step 5: python -c "import ast; ast.parse(...)"   ← 语法验证
Step 6: 搜索受影响的 state key，确认无冲突      ← 幂等性验证
Step 7: 如有 dialog：确认定义在 @fragment 内、for循环之前
```

### 场景B：修改 core/ 下的逻辑

```
Step 1: 用 graphify 确认改动节点的边数（边数>20即为 God Node，需谨慎）
Step 2: grep 所有调用点（接口变更必做）
Step 3: 先写测试（描述预期行为），再改代码
Step 4: 最小化改动（只改目标，不顺手优化周边）
Step 5: pytest tests/unit/ -v                   ← 全量单元测试
Step 6: python -m tests.evaluation.eval_runner  ← 路由精度不退化
Step 7: 存档评估结果
```

### 场景C：更新记忆系统（memory/）

```
Step 1: file_read memory_management_sop.md       ← 必读META-SOP
Step 2: 判断是 L2（环境事实）还是 L3（SOP）变更
Step 3: 只用 file_patch 修改（禁止覆写整个文件）
Step 4: L2/L3 变更后，同步更新 L1 Insight
Step 5: 验证：file_read 变更文件，确认格式正确
Step 6: 验证：L1 Insight 索引与实际内容一致
```

### 场景D：新增功能（而非修改现有）

```
Step 1: 自问"200行能写成50行吗？" → 简化方案优先
Step 2: 自问"这个功能被明确要求了吗？" → 没有则不写
Step 3: 确认新代码放置位置不破坏现有模块边界
Step 4: 新增代码的 import 路径验证
Step 5: 手动验证新功能的关键路径
Step 6: 如果是工具/技能：补充对应的 SOP 或 Learnings
```

---

## 七、进化机制（Learnings 自动积累）

> 来源：skill_best_practices.md §"Self-Evolution 机制"

### 7.1 Learnings 触发条件

```
以下情况发生后，必须更新对应 SOP 的 Learnings 章节：

触发条件                        → 更新目标
────────────────────────────────────────────────
任何需要第2次以上尝试的问题      → 对应场景的 SOP
用户明确指出错误（特别是愤怒时） → 对应场景的 SOP + streamlit_pitfalls
发现新的环境事实或路径           → global_mem.txt (L2)
发现新的反复踩坑模式             → 对应 SOP 的 Gotchas 章节
```

### 7.2 Learnings 写法规范

```markdown
## Learnings
- 2026-05-03: [具体坑点描述，一句话，包含触发条件和正确做法]
  示例：Streamlit @fragment 内的 st.dialog 必须在 for 循环之前定义，
        否则 state 同步失败导致弹窗不响应按钮
```

### 7.3 现有 SOP 需要补充 Learnings 的清单

```
优先级 P0（已有明确踩坑记录的）：
□ memory/streamlit_pitfalls.md   → 补充 fragment/state/dialog 的完整规则
□ memory/coding_karpathy_sop.md  → 补充项目特有的验证坑点

优先级 P1（高频使用，应有自演化能力）：
□ memory/tmwebdriver_sop.md      → 加 Learnings 章节
□ memory/autonomous_operation_sop.md → 加任务完成后触发蒸馏的步骤
□ memory/ljqCtrl_sop.md          → 加 Learnings 章节
```

---

## 八、本计划的验证方式

> 计划本身也需要验证标准，否则就是弱目标

### 成效可观测指标

| 指标 | 当前状态 | 目标 | 测量方式 |
|------|---------|------|---------|
| 单任务平均返工次数 | ~2次（基于历史蒸馏） | ≤1次 | history_memory_inbox 统计 |
| 前端改动首次成功率 | ~50%（4次返工说明） | ≥80% | 主观但可追踪 |
| 核心单元测试通过率 | 需跑基准 | 100% | pytest 输出 |
| 路由精度 | 需跑基准 | ≥95% | eval_runner 输出 |
| 验证铁律遵守率 | 未追踪 | 每次编码必有工具输出 | 主观检查 |

### 月度回顾动作

```bash
# 1. 跑完整评估，与上月对比
python -m tests.evaluation.eval_runner
diff tests/evaluation/eval_report_prev.json tests/evaluation/eval_report.json

# 2. 统计 history_memory_inbox 中的返工次数趋势
grep -c "次数" memory/history_memory_inbox.md  # 粗略统计

# 3. 检查 Learnings 是否在各 SOP 中持续更新
ls -la memory/*.md  # 看修改时间
```

---

## 附录：快速参考卡

```
改前三问：
1. 我读了当前代码了吗？（禁止盲改）
2. 这行改动有对应的用户请求吗？（手术式）
3. 我的成功标准是什么？（可验证）

改后三查：
1. 有工具执行输出吗？（非目视检查）
2. 跑了边界/幂等测试吗？
3. 现有功能还好吗？（pytest / eval_runner）

改 core/ 时：
→ 先查边数（God Node > 20边需谨慎）
→ 先 grep 调用点
→ 先写测试，再改代码

改前端时：
→ 先读 streamlit_pitfalls.md
→ dialog 必须在 @fragment 内、for循环前定义
→ state key 必须按功能隔离
```