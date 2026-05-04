# 我把一个 AI Agent 改成了工程工作台——从聊聊天到真正能干活

## 五个标题备选

1. **从 Demo 到 Workbench：一个 AI 智能体的工程化改造记录**
2. **不聊天的智能体——把 LLM Agent 做成可控的工程工作台**
3. **6600 行核心代码，21 项已生效能力：一个 AI Workbench 的架构拆解**
4. **当 Agent 不只是聊天——路由、编排、执行、验证四层闭环**
5. **一个人对 AI 工程助手该长什么样的回答**

---

## 一、我为什么做这个项目

去年我开始用一个开源的 AI Agent 做日常开发。它能读文件、写代码、跑 shell 命令、操作浏览器——这些能力都是真实可用的，不是"AI 在聊天框里假装执行"。

但每天用，问题就来了。

**上下文漂移。** 三轮对话之后，Agent 已经忘了我们最开始要解决什么问题。它的 system prompt 里塞满了历史对话片段，越跑越散。就像一个在开会时走神的人，表面上还在点头，但说的东西跟议题已经没关系了。

**架构幻想。** 让它修改一个模块，它有时候会把相邻的三个文件一起改了，"顺手"重构了原本不需要动的地方。代码能跑，但架构边界被它悄悄推平了。等你发现的时候，已经不是一个 commit 能回得来的。

**假完成。** Agent 的 response 写得很漂亮——"已经完成了 X，验证了 Y，结果正常"——但实际上它只是读了个文件名或者跑了个空 shell。没有真实的 exit code 检查，没有 diff 验证，没有测试回归。

**缺少审计。** 每轮对话消耗多少 token？LLM 调用走了哪条路由？工具 schema 是不是每次都全量发给模型？这些问题在原始项目里没有答案。

这些都不是模型能力的问题，是**工程约束**的问题。

模型本身很强，但缺少一层"让模型在可控边界内工作"的工程基础设施。所以我决定在这个 Agent 内核上搭一层工作台——不重写执行器，而是给它加上编排、路由、观测、验证、记忆和 UI。

这就有了 **GenericAgent Workbench**。

> 【截图插入点 1】项目 Streamlit 主界面截图。展示 Sidebar 里的历史面板、记忆面板、模型切换、附件上传，以及主聊天的 warm atelier 风格。配文："主界面不是纯聊天框，而是一个有面板、有状态、可切换的工作台。"

---

## 二、项目解决的具体问题

这些问题不是"提升效率"这种空话能概括的。我拆成具体的：

**1. 聊天和执行不分流。** 用户问"快排是什么"和"帮我写个快排"是两个完全不同的事。前者应该走轻量级对话，后者需要进入完整的规划-执行-验证流程。原始项目没有这种路由，所有请求一律进入执行循环，简单问题被过度处理，复杂问题缺少规划。

**2. 多智能体编排缺失。** 当项目扩展时，单一 agent loop 承担了路由、规划、执行、验证所有职责。代码在 6000 行以上的单体模块里耦合。增加一个角色需要改动多处。

**3. 工具调用不受约束。** 每次 LLM 调用都发送全部工具 schema——几百行 JSON。大部分工具当前任务根本用不到，这既浪费 token 也降低模型的注意力密度。

**4. LLM 行为缺少审计。** 没有 profiler，没有 audit log，不知道每轮花了多少 token、走了哪条路由、用了哪些工具。出问题时只能靠感觉排查，无法回溯。

**5. 记忆系统没有写入边界。** 旧的 global memory 是纯文本追加，任何 Agent 响应都可能被写进去，没有内容门控，没有去重，没有来源标记。

**6. 会话恢复不够健壮。** 旧方式按纯文本日志恢复，工具调用结果和用户输入混在一起，恢复后容易出现消息角色错乱。

**7. 缺少回归测试。** 改一行代码，不知道会不会破坏现有能力。没有 baseline，没有 regression matrix，没有自动化验证。

每一个问题都不是"模型不够聪明"导致的。它们都是**软件工程问题**，需要的不是更大的模型，而是更好的架构。

> 【截图插入点 2】`docs/runtime_capability_matrix.md` 的表格截图。展示 A/B/C/D 四个层级的分类。配文："能力矩阵把已生效、开关控制、基础设施和概念设计四类严格分开，避免纸上谈兵时的夸大。"

---

## 三、整体架构

GenericAgent Workbench 的架构可以用六个字概括：**路由 → 编排 → 执行 → 观测**。每一层职责清晰，层之间通过明确的接口解耦。

### 第一层：前端/产品层（Frontend Layer）

入口在 `frontends/` 目录。主界面是 `stapp.py`——一个完整的 Streamlit 工作台，不是只有输入框的 demo。

它有：对话历史面板（可恢复、可提炼）、记忆面板（L1/L2/Inbox 三级结构）、附件处理管线（文本/PDF/DOCX 自动抽取和压缩）、多模型一键切换、助手回复折叠、自主行动模式。

除此之外，还有 Telegram、飞书、企业微信、钉钉、微信个人号五个 Bot 入口。所有前端共享同一套 `chatapp_common.py` 的恢复、提炼、删除逻辑。

桌面入口是 `launch.pyw`——一个 pywebview 窗口，内部嵌入 Streamlit 页面，带 idle 检测和自动任务注入。

### 第二层：编排层（Orchestration Layer）

核心在 `core/openai_agentmain.py`（3068 行）。这一层基于 OpenAI Agents SDK 构建了一个三智能体图：

- **task_router**：只做分流。快速判断这个请求是简单对话还是复杂任务。它有两条输入——RouterRules 的关键词快速匹配结果，以及 LLM 自身的判断。两者叠加做最终决策。
- **chat_specialist**：处理解释型、问答型、纯对话型请求。不接触工具，不接触文件系统，直接回答。
- **planner_executor**：处理复杂任务。它不自己执行，而是做规划、委派、验证。实际执行交给下一层。

编排层还负责组装 planner-local 上下文、汇总 runtime profiler 和 audit 数据、处理 handoff 信号。

### RouterRules：编排前的第一道关卡

在 LLM routing 前，`core/router_rules.py`（426 行）先做一层轻量判断。

它维护了 57 个 executor 关键词、26 个 chat 关键词、35 个 code 关键词、39 个 review 关键词、34 个 research 关键词，外加 10 个命令匹配模式和 5 个排除模式。用关键词命中计数 + 加权打分的方式，在 <1ms 内做出初步判断。

命中明确的直接分流转发；命不中的交给 task_router 做 LLM 判断。这意味着"帮我写个快排"永远不会先进入对话模型，而"什么是快排"也永远不会进入执行循环。

### 第三层：经典执行层（Classic Execution Kernel）

`core/agentmain.py` + `core/agent_loop.py` + `core/ga.py`。

这一层是 GenericAgent 的经典执行循环——实际做文件读写、代码修改、shell 命令、浏览器操作、ADB 控制。它不关心"这个任务是谁派来的"，只接收指令、执行、返回结果。

这一层也集成了运行时观测能力：
- **profiler**：记录真实的 span 和 event，不是事后推断
- **LLM audit**：记录 prompt 字符数、路由结果、工具 schema 等
- **direct answer**：对窄读取任务，跳过最后一轮经典 LLM 总结
- **read shortcut**：文件读取类任务的快路径，不进入完整执行循环
- **tool schema slimming**：按任务类型缩小工具 schema，减少 token 浪费

### 第四层：技能与治理层（Skills & Governance）

`core/skills/` 目录包含一套独立于执行循环的治理系统。

- **Skill Manifest & Taxonomy**：定义每个 skill 的元数据、适用阶段、触发条件
- **Skill Selector**：根据任务阶段动态筛选可用的 skills
- **Skill Prompt Injector**：将 SOP prompt block 注入 planner 的 task-local 上下文（不是全局 system prompt）
- **Skill Effects**：定义 skill 对工具、上下文、路由的潜在影响（目前 dry-run）
- **Execution Policy**：生成执行策略并 merge/preview（目前 dry-run，不做 enforcement）

### 第五层：记忆层（Memory Layer）

混合架构：旧的 `memory/` 目录下的 global_mem 文本文件仍是权威注入来源，新的 `core/memory/` 下的 SQLite ledger + FTS 索引用做结构化存储，附带 Write Gate 内容门控。

### 关键数据流

```
用户输入 → RouterRules 快速匹配 → task_router LLM 判断
                                         │
                    ┌─────────────────────┴──────────────────┐
                    ▼                                         ▼
            chat_specialist                          planner_executor
            （直接回答）                              （规划 + 委派）
                                                           │
                                                    ┌──────┴──────┐
                                                    ▼              ▼
                                          classic executor   直接返回
                                          （文件/代码/shell）  （简单查询）
                                                    │
                                                    ▼
                                              result verification
                                              （profiler + audit）
```

> 【截图插入点 3】`core/openai_agentmain.py` 中的 agent graph 构建代码截图。展示 `task_router / chat_specialist / planner_executor` 三个 agent 的定义和 handoff 关系。配文："三个 agent 各自有明确的 instructions 和 handoff 路径，不是一个大 prompt 里塞所有逻辑。"

---

## 四、核心工作流：一次完整执行

以"帮我重构这个文件的异常处理"为例，走一遍完整链路。

**Step 1: 关键词匹配。** RouterRules 扫描请求，命中"重构""文件""异常处理"三个 executor 关键词。executor_score > chat_score，预判为 executor 任务。

**Step 2: LLM 路由。** task_router 收到预判结果和原始请求，做最终路由判断。这里是"复杂代码修改 → planner_executor"。

**Step 3: 规划。** planner_executor 生成执行计划：读取目标文件 → 分析现有异常处理 → 生成重构方案 → 应用修改 → 验证。

**Step 4: 委派执行。** 规划中的每一步需要实际读写文件、运行测试。planner 通过 handoff 把这些真实操作交给 classic executor。executor 返回结果后，planner 检查：文件是不是真的改了？测试通过了没有？diff 合理吗？

**Step 5: 验证闭环。** 如果 plan 中要求"跑 pytest 验证"，executor 必须返回 pytest 的实际输出。如果测试失败，planner 不能声称完成——它会收到 profiler 的 failed 信号，然后进入修复 loop。

**Step 6: 结果交付。** 所有步骤完成后，planner 生成一份 summary，附带实际文件变更的 diff 和测试结果。这个 summary 不是"看起来完成了"，而是有证据的。

**为什么这样分步？**

- 每一步都有明确的输入和输出，方便审计
- planner 不直接操作文件——它只是"项目经理"，防止它瞎改
- executor 不判断任务是否完成——它只是"工程师"，返回事实
- profiler 记录每步的真实耗时和结果，不是事后回忆

**流式输出和停止机制。** 当 Agent 在执行时，Streamlit 前端通过 `display_queue` 轮询输出。用户点了"停止"按钮后，`stop_requested` 标志位会触发 agent.abort()。前端不是假停止——它真的发送中断信号到 agent loop，清理当前任务的 queue 项，保留已完成的回复。

> 【截图插入点 4】Agent 执行过程的 terminal log 或 Streamlit 中的 Turn 分段显示截图。展示分步推进的痕迹。配文："不是一次性生成答案。每一步有标记、可中断、有结果。"

---

## 五、技术实现细节

这部分挑几个值得展开的点说。

### 双后端与配置加载

GenericAgent Workbench 支持两种后端模式：
- `genericagent`（默认）：经典单体 agent loop
- `openai-agents`：OpenAI Agents SDK 多智能体编排

通过环境变量 `GA_AGENT_BACKEND` 切换。

配置加载有四条路径，按优先级排列：
1. 从 `mykey.py` 导入（Python 模块，gitignored）
2. 从 `mykey.json` 读取（JSON 文件，gitignored）
3. 从 `.env` 读取环境变量（通过 python-dotenv，gitignored）
4. 从 `~/.claude/settings.json` 读取

这是一个**防御性设计**：不管用户习惯哪种配置方式，系统都有一条路径能读到 key。模板文件 `mykey_template.py` 和 `.env.template` 提供完整的多 key 配置示例。

我们在这轮迭代中修了一个关键 bug：`_load_mykeys_from_env()` 返回的 key 名是 `key1_config`，但 agentmain 的路由 filter 要求 key 名包含 `native` 和 `oai` 子串。env var 配置路径之前是静默失效的——系统不会报错，只是找不到配置，用户收到的是泛化的 "No API key" 错误。对齐 key 名为 `key1_native_oai_config` 后，env var 路径才真正可用。

### 前端的 Streaming 与 Stop

Streamlit 本身是 request-response 模式，不适合长流式输出。当前实现是：

- `agent.put_task()` 返回一个 `queue.Queue`
- 前端用 `st.rerun()` + `time.sleep(0.2)` 做非阻塞轮询
- 每次从 queue 中 drain 最多 20 条消息
- 停止按钮通过 `agent.abort()` 中断 agent loop
- 已完成的消息被保存到 `session_state.messages`，不会丢失
- scroll 事件通过 MutationObserver + 自增的 data-scroll-event 属性实现自动滚动

这是一个**在 Streamlit 限制下的实用解法**。它不是 WebSocket，是 polling loop；它不是真正的实时流，但用户感知到的是连续输出。

### 历史恢复的多格式兼容

这个项目同时支持两种后端，它们的历史格式不同。`chatapp_common.py` 中的 `format_restore()` 能自动检测格式类型：

- 旧格式：文本行，以 `[USER]:` / `[ASSISTANT]:` 等前缀标记
- 新格式：结构化的 `INPUT_ITEMS`，包含完整的 role/content 对

恢复时自动处理消息角色、工具结果过滤、附件引用重建。后端切换后，旧历史仍然可以恢复。

### 隐私保护的工程实践

`.gitignore` 不是随便写的几条。它覆盖了：
- 密钥文件（`mykey.py`, `mykey.json`, `*.env`, `*_key*`, `*secret*`, `*token*`）
- 运行时数据（`temp/`, `records.jsonl`, `skill_activations.jsonl`）
- 记忆状态（`memory/chat_history.json`, `memory/global_mem*.txt`, `memory/history_memory_inbox.md`）
- 数据库和缓存（`*.db`, `*.sqlite`, `*sqlite3`, `core/graphify-out/`）
- 本地脚本（`*.bat`, `start_streamlit_public.py`）
- Claude Code 状态（`.claude/`）

有正向规则（`!core/**`, `!memory/*.py`）和反向覆盖（重新排除 graphify-out 和 inbox.md），确保运行时文件不会意外进 git。

### 环境可见性与开关设计

项目里有 7 个能力通过环境变量开关控制：

```
GENERIC_AGENT_SKILL_SOP=1          # skill SOP 注入
GENERIC_AGENT_ANSWER_QUALITY=1     # Answer Quality Guard
GENERIC_AGENT_SLIM_TOOLS=1         # 工具 schema 瘦身
GENERIC_AGENT_DIRECT_ANSWER=1      # 窄读取直接回答
GENERIC_AGENT_READ_SHORTCUT=1      # 文件读取快路径
GENERIC_AGENT_EARLY_STOP=1         # 提前终止
GENERIC_AGENT_PROFILE=1            # profiler 导出
```

这不是功能开关的随意堆砌——每个开关对应一个明确的优化策略，各自独立，默认关闭。关闭时走完整路径（更安全但更慢），开启时走优化路径（更快但有适用范围）。这种设计让用户可以根据任务类型选择性开启，而不是全有或全无。

> 【截图插入点 5】`.gitignore` 和 `mykey_template.py` 并排截图。展示隐私保护的分层设计。配文："gitignore 不是随便写的，有正向规则、反向覆盖、明确的分层。"

---

## 六、我重点解决的 AI 工程问题

### 问题 1：AI 编程的"架构侵蚀"

这是最让我头疼的问题。Agent 在修改代码时经常会"顺带"改相邻文件。它不是在恶意破坏——它只是觉得"既然改到这里了，顺手优化一下吧"。但两次"顺手"之后，原本清晰的模块边界就模糊了。

我的解决方式是**严格执行层分离**。planner_executor 只能做规划和委派，不允许它自己操作文件。所有文件操作必须经过 classic executor。executor 会返回真实的执行结果，planner 据此判断下一步。如果规划里没有"修改文件 B"，executor 就不会碰文件 B。

这很基本，但有效。管住权限比写好 prompt 更重要。

### 问题 2：能力矩阵的诚实分类

在这个项目里，我把所有能力分成了四个等级：

- **A 级（Active In Main Flow）**：真正在运行时生效的能力，有代码路径可验证
- **B 级（Switch-Gated）**：已集成但通过开关控制，默认关闭
- **C 级（Infrastructure Only）**：底座代码已完成，但还没接入运行时
- **D 级（Concept Only）**：只在设计文档里，没有代码路径

这种分类方式很"无聊"，但比"我们支持了某某功能"诚实地多。写文档的时候说"支持了 XX"，但实际上只是 C 级或 D 级——这种情况在 AI 项目里太常见了。

### 问题 3：调参地狱防御

有几个设计是专门防止陷入调参地狱的：

- **LLM audit**：每次调用的 prompt/response 统计自动记录，不用事后回忆
- **profiler 真正跑在运行时**：不是手动计时，不是事后推断
- **read shortcut**：读文件不需要完整 agent loop，直接走快路径——减少不必要的 LLM 调用
- **tool schema slimming**：按需发送工具描述，不浪费 token，也减少模型的"选择困难"

### 问题 4：本地优先，隐私可控

所有 key 通过本地文件加载，不依赖云端配置服务。`.gitignore` 确保敏感文件不会进入版本控制。即使 push 到公开仓库，clone 下来的人拿到的只有模板文件。

> 【截图插入点 6】`docs/current_architecture_status.md` 中的分层示意图或 `core/` 目录结构截图。配文："六层架构对应六个明确的职责边界，不是功能目录的随意划分。"

---

## 七、当前效果与验证

### 已生效能力

根据 `docs/runtime_capability_matrix.md` 的记录：

**A 级（已生效）：21 项**
包括：RouterRules 快速路由、三智能体编排图、classic executor handoff、RuntimeProfiler、LLM audit、tool schema slimming、direct answer、read shortcut、SOP planner 注入、Answer Quality Guard、Memory Write Gate 等。

**B 级（开关控制）：7 项**
通过环境变量选择性启用。

**C 级（底座已完成）：5 项**
structured memory store、evidence FTS index、LLM cache 复用、skill discovery、read_prefetch 分析。

**D 级（概念设计）：6 项**
包括动态 agent spawning、workflow skill runtime、reviewer phase injection 等。

### 验证方式

- **Runtime regression matrix**：`docs/runtime_regression_matrix.md` 记录了各能力模块的回归测试状态
- **Read shortcut regression set**：`docs/read_shortcut_regression_set.md` 针对读取快路径的测试用例
- **pytest 单测**：`tests/unit/` 下有 agent graph、router rules、pipeline、shared store、tool permissions 等专项测试
- **Baseline fixtures**：JSON 格式的 expected output，用于比较测试

### 已知限制

1. 大部分 C 级能力（structured memory, LLM cache 复用）还处于底座完成但未接入 runtime 的状态
2. `ExecutionPolicy` 和 `SkillEffects` 目前只是 dry-run，不做真正的强制执行
3. read_prefetch 目前只是 observe-only，没有做上下文注入
4. 测试覆盖不完整——主要靠 regression matrix 的手动验证
5. 前端密码锁暂时关闭（移动端未上线）
6. 多 Bot 前端共享核心逻辑但各自有独立的认证和连接代码

---

## 八、下一步要做什么

诚实地说，现在这个项目需要的不是加更多 feature，而是**封版和巩固**。

1. **补测试**。regression matrix 里还有很多空白格。在加新能力之前，先让已有能力有可靠的回归保护。

2. **C 级底座接入 runtime**。structured memory store 和 LLM cache 复用已经有完整代码，接入 runtime 不是大工程，但需要仔细处理边界条件。

3. **ExecutionPolicy 从 dry-run 升级到 enforcement**。这是把"技能治理"从纸面概念变成实际约束的关键一步。

4. **前端体验打磨**。Streamlit 有它的限制，但 CSS 和组件状态的精细度还可以提升。当前的 warm atelier 主题是一次方向性尝试。

5. **多智能体编排的稳定性**。三 agent 图已经跑通，但在边缘 case（并发请求、异常 handoff、长时间 idle）下的行为还需要更多验证。

6. **文档体系**。workflow.md 和 CONTRIBUTING.md 已经有基础，但面向外部读者的技术文档还不够。

不要急于加 D 级的概念能力。C → B → A 的推进比 D → C 更有价值。

---

## 九、总结

GenericAgent Workbench 不是又一个"跟 AI 聊天"的项目。它解决的是 AI 在工程任务里的可控性问题。

核心设计原则很朴素：

- **分层**：不要让一个模块承担所有职责
- **可观测**：所有 LLM 调用和工具执行都要有审计记录
- **可验证**：Agent 说"完成了"不算，要有真实的执行结果和测试通过
- **可恢复**：对话历史不是日志文件，是结构化的可恢复状态
- **有边界**：Skills 和 memory 的写入要有门控，runtime 的能力要有明确的开关

如果你也在做自己的 AI 工程工具——不管是 agent、RAG pipeline、还是 coding assistant——希望这篇文章能给你一些参考。不是参考"怎么做 AI"，而是参考"怎么给 AI 加工程约束"。

毕竟，LLM 的能力已经很好了。缺的不是更大的模型，是更好的工程。

---

*项目地址：github.com/user141514/GenericAgent-Workbench*
*当前分支：chore/phase1-security（封版 + 安全加固 + 前端重构）*
