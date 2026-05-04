# Runtime Regression Runner

> 生成时间: 2026-05-02
> 脚本路径: `scripts/runtime_regression_runner.py`

---

## 一、保护的能力

此 runner 覆盖 GenericAgent Workbench 的 **全部运行时 demo 模块**，用于在每次变更后快速验证以下能力没有退化：

| 能力领域 | 保护的模块 | 验证内容 |
|---------|-----------|---------|
| **Runtime Optimization** | `core.runtime.*` | Profiler 埋点、LLM 缓存审计、Early Stop 规则、Direct Answer 规则、Read Shortcut 检测、Read Prefetch 检测 |
| **Quality Guard** | `core.quality.*` | Answer Quality Context 构建正确性 |
| **Skill System** | `core.skills.*` | Skill Registry、Selector、Discovery、Manifest、Prompt Injector、Activation、Effects |
| **Memory Gate** | `core.memory.*` | Memory Indexer、Structured Store、Write Gate 源过滤 |
| **Tool System** | `core.tools.*` | Tool Schema 瘦身选择器 |

**核心原则**: 这些 demo 是 runtime 优化的最小可用验证。任何一个 [FAIL] 都意味着该领域的能力可能已经退化，应在继续开发前修复。

---

## 二、如何运行

### 基本运行

```bash
python scripts/runtime_regression_runner.py
```

### 运行前提

- 工作目录必须是仓库根目录 (`F:\GAgent-Multi`)
- Python 环境需安装项目依赖
- 不需要设置任何环境变量（demo 内部自行构造数据）

### 输出格式

```
[PASS] core.runtime.demo_profiler
[FAIL] core.memory.demo_write_gate
<stderr 最后 1000 字符>
[SKIP] core.xxx.demo_missing

passed:  17
failed:  1
skipped: 1
```

- **退出码**: `failed > 0` 时为 `1`，否则为 `0`

---

## 三、Demo 分类详解

### 3.1 Runtime Optimization（运行时优化）

| 模块 | 验证的 Runtime 能力 | 对应开关 |
|------|-------------------|---------|
| `core.runtime.demo_profiler` | `RuntimeProfiler` span/event 记录与 JSON 导出 | `GENERIC_AGENT_PROFILE=1` |
| `core.runtime.demo_llm_cache` | `LLMCallCache` 本地缓存审计、`is_cache_safe` 校验 | 缓存审计已激活，缓存复用未启用 |
| `core.runtime.demo_early_stop` | `should_stop_classic_executor` 经典执行器提前停止规则 | `GENERIC_AGENT_EARLY_STOP=1` |
| `core.runtime.demo_direct_answer` | `try_direct_answer_from_tool_result` 窄读取类直接回答规则 | `GENERIC_AGENT_DIRECT_ANSWER=1` |
| `core.runtime.demo_read_shortcut` | `detect_read_shortcut` 文件读取快捷路径检测 | `GENERIC_AGENT_READ_SHORTCUT=1` |
| `core.runtime.demo_read_prefetch` | `detect_read_prefetch` 分析型预取检测 | 始终激活 |

相关能力矩阵文档:
- `docs/runtime_capability_matrix.md` — 运行时能力矩阵
- `docs/runtime_optimization_summary.md` — 运行时优化总结
- `docs/read_shortcut_regression_set.md` — Read Shortcut 回归集
- `docs/read_prefetch_design.md` — Read Prefetch 设计
- `docs/read_prefetch_effectiveness.md` — Read Prefetch 效果评估

### 3.2 Quality Guard（质量守护）

| 模块 | 验证的 Quality 能力 | 对应开关 |
|------|-------------------|---------|
| `core.quality.demo_answer_quality_context` | `build_answer_quality_context` 答案质量上下文构建 | `GENERIC_AGENT_ANSWER_QUALITY=1` |

相关文档:
- `docs/answer_quality_policy.md` — 答案质量策略

### 3.3 Skill System（技能系统）

| 模块 | 验证的 Skill 能力 |
|------|------------------|
| `core.skills.demo_skill_registry` | `SkillRegistry` 注册与 `SkillSelector` 选择 |
| `core.skills.demo_skill_selector` | `SkillSelector` 按查询类型（plan/verify/performance/test/debug）选择 |
| `core.skills.demo_skill_prompt_injector` | `SkillPromptInjector` SOP 块与环境变量检查 |
| `core.skills.demo_skill_manifest` | `SkillManifest` 与 `SkillSelector` 协作 |
| `core.skills.demo_skill_discovery` | `SkillDiscovery` → `to_manifest_entry` → `SkillRegistry` → `SkillSelector` |
| `core.skills.demo_skill_effects` | `SkillEffects` 与 `build_execution_policy_from_skills` |
| `core.skills.demo_skill_activation` | `build_skill_activation` / `export_skill_activation` / `build_optional_sop_context` |

当前状态（来自 `docs/runtime_capability_matrix.md`）:
- `SkillRegistry` + `SkillSelector` — **活跃在主流程中**
- `SkillPromptInjector` — **`GENERIC_AGENT_SKILL_SOP=1` 开关控制**
- `SkillEffects` / `SkillActivation` — **dry-run 阶段，未影响运行时行为**
- `SkillDiscovery` — **infra 就绪，未自动启用**

### 3.4 Memory Gate（记忆门控）

| 模块 | 验证的 Memory 能力 |
|------|------------------|
| `core.memory.demo_memory_indexer` | `MemoryIndexer` + `MemoryStore` 历史记忆索引 |
| `core.memory.demo_memory_store` | `MemoryStore` 结构化记忆存储 (SQLite) |
| `core.memory.demo_write_gate` | `MemoryStore` 写入门控（source-gated 过滤） |

当前状态:
- `MemoryStore` + `MemoryIndexer` — **infra 就绪，不驱动 prompt 检索**
- `WriteGate` — **活跃在内存存储中**

### 3.5 Tool System（工具系统）

| 模块 | 验证的 Tool 能力 |
|------|-----------------|
| `core.tools.demo_schema_selector` | `ToolSchemaSelector` 基于规则的工具 schema 瘦身 |

当前状态: `GENERIC_AGENT_SLIM_TOOLS=1` 开关控制

---

## 四、上传 Git 前必须运行

### 强制检查清单

在每次 `git push` 或创建 PR 之前:

```bash
# 1. 运行 runtime 回归
python scripts/runtime_regression_runner.py

# 2. 检查退出码
echo $?   # 必须为 0
```

### 失败处理

如果 runner 报告 `[FAIL]`，按以下顺序排查：

1. **确认运行环境正确**: 工作目录是仓库根目录，Python 环境有项目依赖
2. **查看 stderr 输出**: runner 会显示最后 1000 字符
3. **单独运行失败的 demo**: `python -m core.xxx.demo_yyy` 获取完整错误
4. **检查最近的改动**: 是否修改了该 demo 依赖的模块
5. **禁止在失败时提交**: 修复回归或更新 demo 后再提交

### 与 `scripts/run_runtime_regression.py` 的关系

| 文件 | 覆盖模块数 | 用途 |
|------|----------|------|
| `scripts/run_runtime_regression.py` | 9 | 原有的轻量回归（仅在 4 个类别中选择核心 demo） |
| `scripts/runtime_regression_runner.py` | 18 | **全量回归** — 覆盖 5 个类别的全部 demo，是本文件的推荐替代 |

建议: 日常开发用 `runtime_regression_runner.py` 做完整检查；CI 中也使用完整版。

---

## 五、预期结果

当前（2026-05-02）在 `chore/phase1-security` 分支上，预期全部 18 个模块返回 `[PASS]`。

如果任一模块返回 `[FAIL]`，该领域可能在最近的改动中被意外破坏，需要立即排查。
