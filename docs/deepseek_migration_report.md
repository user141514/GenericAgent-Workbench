# DeepSeek API 迁移报告

## 1. 当前架构分析

### 1.1 当前配置 (`mykey.py`)

```python
native_claude_config = {
    'name': 'glm-5',
    'apikey': 'sk-YOUR_DEEPSEEK_API_KEY',
    'apibase': 'https://coding.dashscope.aliyuncs.com/apps/anthropic',
    'model': 'glm-5',
    'stream': False,
    'max_retries': 3,
    'connect_timeout': 10,
    'read_timeout': 120,
}
```

- 使用阿里云 DashScope 的 Anthropic 兼容中继端点
- Key 名 `native_claude_config` 包含 `native` + `claude` → 创建 `NativeToolClient(NativeClaudeSession)`
- 所有请求走 Anthropic Messages API 格式 (`/v1/messages`)
- 流式响应使用 Anthropic SSE 格式解析 (`_parse_claude_sse`)

### 1.2 Session 类型分发逻辑 (`core/agentmain.py:94-119`)

| Key 名包含 | Session 创建 | 工具调用方式 | API 格式 |
|-----------|-------------|------------|---------|
| `native` + `claude` | `NativeToolClient(NativeClaudeSession)` | Native | Anthropic Messages |
| `native` + `oai` | `NativeToolClient(NativeOAISession)` | Native | OpenAI Chat/Completions |
| `claude` (仅) | `ToolClient(ClaudeSession)` | 文本协议 | Anthropic Messages |
| `oai` (仅) | `ToolClient(LLMSession)` | 文本协议 | OpenAI Chat/Completions |
| `mixin` | `MixinSession` | 取决于链 | 混合 |

Key 名还必须包含 `api`、`config` 或 `cookie` 之一才会被加载（`agentmain.py:95`）。

### 1.3 工具调用完整流程

```
agent_runner_loop()
  → NativeToolClient.chat(messages, tools)
    → 提取 system prompt → set_system()
    → 构建 Claude content-block 格式的 merged 消息
    → backend.ask(merged)                    # NativeClaudeSession.ask()
      → 添加到 history, trim
      → 传入 raw_ask(messages)               # NativeOAISession.raw_ask()
        → _msgs_claude2oai(messages)         # Claude blocks → OpenAI messages
        → _openai_stream(api_base, api_key, msgs, model, ...)  # 实际的 HTTP 请求
          → POST {apibase}/v1/chat/completions
          → _parse_openai_sse(r.iter_lines())  # 解析 SSE，返回 content_blocks
      → 将 content_blocks 转换为 MockResponse(thinking, content, tool_calls, raw)
    → 返回 MockResponse 给 agent_runner_loop
  → agent_runner_loop 解析 response.tool_calls → dispatch 到 handler
```

### 1.4 消息格式转换 (`_msgs_claude2oai`, `core/llmcore.py:557-598`)

- Claude content-block 格式 (assistant with tool_use, user with tool_result) → OpenAI 标准格式 (assistant with tool_calls, tool role messages)
- 这是 DeepSeek 兼容的关键——DeepSeek 使用标准 OpenAI Chat/Completions 格式

---

## 2. 切换到 DeepSeek 的推荐方案

### 2.1 推荐配置：使用 `native_oai_config`

只需修改 `mykey.py` 为以下内容：

```python
native_oai_config = {
    'name': 'deepseek-chat',
    'apikey': 'sk-YOUR_DEEPSEEK_API_KEY',
    'apibase': 'https://api.deepseek.com',
    'model': 'deepseek-chat',
    'stream': True,
    'max_retries': 3,
    'connect_timeout': 10,
    'read_timeout': 120,
}
```

**为什么这个方案可行：**

- Key 名 `native_oai_config` 包含 `native` + `oai` + `config`
  - `native` + `oai` → 创建 `NativeToolClient(NativeOAISession(cfg))`
  - `config` → 通过 filter（`agentmain.py:95`）
- `NativeOAISession` 继承 `NativeClaudeSession`，但重写 `raw_ask()` 使用 OpenAI 兼容格式
- `auto_make_url("https://api.deepseek.com", "chat/completions")` → `https://api.deepseek.com/v1/chat/completions`
- 工具 schema (`assets/tools_schema.json`) 已经是 OpenAI function-calling 格式，无需修改
- `_parse_openai_sse()` 支持标准 `delta.tool_calls[]` 格式，DeepSeek 完全兼容

### 2.2 各选项对比

| 方案 | Key 名示例 | 优点 | 缺点 |
|------|-----------|------|------|
| **推荐**: `native_oai` | `native_oai_config` | 原生 function calling，工具调用可靠 | — |
| 备选: `oai` | `oai_config` | 简单 | 文本协议，模型需学会 `<tool_use>` 标签，可靠性低 |
| 不可行: `native_claude` | `native_claude_config` | — | Anthropic 格式，DeepSeek 不支持 `/v1/messages` |

---

## 3. 不会报错的详细原因

### 3.1 API 端点兼容性

DeepSeek API 是标准 OpenAI 兼容接口：
- `POST https://api.deepseek.com/v1/chat/completions` ✅
- 认证头：`Authorization: Bearer sk-xxx` ✅
- 请求体格式：`{"model": "deepseek-chat", "messages": [...], "tools": [...], "stream": true}` ✅

### 3.2 工具调用格式

`_openai_stream()` 发送的工具格式（`llmcore.py:402`）：
```json
"tools": [{"type": "function", "function": {"name": "code_run", "description": "...", "parameters": {...}}}]
```
这正是 OpenAI/DeepSeek 标准 function calling 格式 ✅

### 3.3 流式响应解析

DeepSeek SSE 响应格式与 OpenAI 一致：
```json
{"choices":[{"delta":{"content":"..."}}]}
{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_xxx","function":{"name":"code_run","arguments":"{\"script\":\"...\"}"}}]}}]}
{"choices":[{"delta":{}}],"usage":{...}}
```

`_parse_openai_sse()` (`llmcore.py:281-311`) 正确解析：
- `delta.content` → text blocks ✅
- `delta.tool_calls[].index` + `function.name` + `function.arguments` → tool_use blocks ✅
- `[DONE]` 终止符（即使没有也可自然结束） ✅

### 3.4 非流式也兼容

如果设置 `stream: False`，走 `_parse_openai_json()` (`llmcore.py:313-352`)，解析 `choices[0].message.tool_calls[]`，DeepSeek 同样支持 ✅

### 3.5 消息格式转换

`_msgs_claude2oai()` 产生的格式：
```json
[
  {"role": "system", "content": "..."},
  {"role": "user", "content": [{"type": "text", "text": "用户输入"}]},
]
```
后续回合包含 tool 角色消息（`tool_call_id` + `content`）和 assistant 消息（含 `tool_calls`），全部是标准 OpenAI 格式 ✅

### 3.6 温度参数

`_openai_stream()` 中 `temperature != 1` 时才发送。DeepSeek 默认 temperature 为 1.0，不发送即使用默认值 ✅

### 3.7 DeepSeek 不会触发模型特殊处理

- `_stamp_oai_cache_markers()` 仅对 Claude/Anthropic 模型添加缓存标记 → DeepSeek 跳过 ✅
- `next_llm()` 中 GLM/MiniMax/Kimi 检测加载中文工具 schema → DeepSeek 不走此分支，加载英文 schema ✅
- `_openai_stream()` 中 Kimi/MiniMax/Moonshot 温度调整 → DeepSeek 不触发 ✅

---

## 4. 可选模型

| 模型 | `model` 值 | 适用场景 |
|------|-----------|---------|
| DeepSeek-V3 (最新) | `deepseek-chat` | 通用 agent 任务，性价比最高 |
| DeepSeek-R1 | `deepseek-reasoner` | 复杂推理任务（注意：可能不支持 function calling） |

**推荐使用 `deepseek-chat`**（DeepSeek-V3），它完全支持 function calling，适合 agent 场景。

---

## 5. 注意事项

### 5.1 `stream: True` 建议

当前 GLM-5 配置用了 `stream: False`，但推荐 DeepSeek 用 `stream: True`：
- Agent 对话体验更好（逐字输出）
- `_parse_openai_sse()` 已充分测试，稳定可靠

### 5.2 `max_tokens` 限制

DeepSeek-chat 最大输出为 8,192 tokens。当前默认 `max_tokens=8192` 已对齐。如需更长输出，可设置更大值（DeepSeek 文档中部分版本支持 32k）。

### 5.3 `reasoning_effort`

如果使用 `deepseek-reasoner`，可设置 `reasoning_effort`。但 `deepseek-chat` 不需要此参数，不设置即可。

### 5.4 系统提示中的 thinking 协议

`NativeToolClient` 会自动注入 thinking/summary 协议：
```
### 行动规范（持续有效）
每次回复请遵循：
1. 在 <thinking></thinking> 标签中先分析现状和策略
2. 在 <summary></summary> 中输出极简单行物理快照
3. 然后才能输出工具调用
```
DeepSeek-V3 可以理解并遵循此协议（文本部分用标签，工具调用走原生 function calling），不影响工具调用行为。

### 5.5 网络代理

当前默认代理为 `http://127.0.0.1:2082` (`llmcore.py:68`)。如果 DeepSeek API 可直接访问，需在 `mykey.py` 中设置 `'proxy': None` 关闭代理：

```python
native_oai_config = {
    ...
    'proxy': None,
    ...
}
```

### 5.6 多 LLM 支持

如果需要同时保留原配置和 DeepSeek，可在 `mykey.py` 中同时定义多个 key：

```python
# 保留原 GLM-5 配置
native_claude_config = {
    'name': 'glm-5',
    'apikey': 'sk-YOUR_DEEPSEEK_API_KEY',
    'apibase': 'https://coding.dashscope.aliyuncs.com/apps/anthropic',
    'model': 'glm-5',
    'stream': False,
    'max_retries': 3,
    'connect_timeout': 10,
    'read_timeout': 120,
}

# 新增 DeepSeek 配置
native_oai_deepseek_config = {
    'name': 'deepseek-chat',
    'apikey': 'sk-YOUR_DEEPSEEK_API_KEY',
    'apibase': 'https://api.deepseek.com',
    'model': 'deepseek-chat',
    'stream': True,
    'max_retries': 3,
    'connect_timeout': 10,
    'read_timeout': 120,
}
```

然后通过 Streamlit 界面的 LLM 切换功能，或 `/llm` 命令在运行时切换。

---

## 6. 迁移步骤总结

1. **修改 `mykey.py`**：将 key 名改为 `native_oai_config`（或新增），填入 DeepSeek API key、base URL、model name
2. **（如需要）设置 `proxy: None`**：如果不用代理
3. **启动项目**：`python launch.pyw`（或 Streamlit / bot frontend）
4. **验证工具调用**：发送一个需要工具的请求（如 "读取 README.md"），确认模型能正常调用 `file_read` 工具
5. **验证多轮对话**：确认工具调用后 agent 能正常继续下一轮

---

## 7. 已修复：DeepSeek V4 Pro thinking mode 报错

### 问题

使用 DeepSeek V4 Pro 时遇到 HTTP 400 错误：

```
Error: HTTP 400 {"error":{"message":"The content[].thinking in the thinking mode must be passed back to the API.",...}}
```

**根因**：DeepSeek V4 Pro 默认启用 thinking mode，模型在流式响应的 `delta.reasoning_content` 中输出思考过程。该内容必须在下一次请求中通过 `reasoning_content` 字段原样传回。当前代码在三处丢弃了 thinking 内容：

1. `_parse_openai_sse()` — 流式解析时忽略 `delta.reasoning_content`
2. `_parse_openai_json()` — 非流式解析时忽略 `message.reasoning_content`
3. `_msgs_claude2oai()` — 转换 assistant 消息时丢弃 `type: "thinking"` 块

### 修复（已于 `core/llmcore.py` 实施）

| 函数 | 修改位置 | 修改内容 |
|------|---------|---------|
| `_parse_openai_sse()` | line 283, 294-295, 308 | 新增 `reasoning_text` 变量，从 `delta.reasoning_content` 累积，生成 `{"type":"thinking","thinking":...}` 块 |
| `_parse_openai_json()` | line 342, 351 | 提取 `message.reasoning_content`，生成 thinking 块 |
| `_msgs_claude2oai()` | line 572, 576-577, 587 | 识别 `type:"thinking"` 块，序列化为 OpenAI 消息的 `reasoning_content` 字段 |

### 数据流（修复后）

```
DeepSeek API 响应
  → _parse_openai_sse() 解析 delta.reasoning_content → thinking block
  → _openai_stream() 返回 blocks (含 thinking)
  → NativeClaudeSession.ask() 提取 thinking 到 MockResponse.thinking
  → 同时保存 content_blocks 到 history（含 thinking）
  → 下一轮 _msgs_claude2oai() 将 thinking 块转为 reasoning_content 字段
  → DeepSeek API 收到完整的 reasoning_content → 不再报错 ✅
```
