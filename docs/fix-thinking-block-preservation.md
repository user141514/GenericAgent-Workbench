# Fix: DeepSeek v4 Thinking Block 丢失导致工具调用报错

## 日期

2026-05-01

## 问题描述

使用 DeepSeek v4 模型时，调用工具后第二回合报错：

```
Error: HTTP 400 {"error":{"message":"The content[].thinking in the thinking mode must be passed back to the API.","type":"invalid_request_error","param":null,"code":"invalid_request_error"}}
```

## 根因分析

DeepSeek v4 在 thinking mode 下，如果模型产生了 `reasoning_content`（thinking block），该内容必须在后续请求中原样传回给 API。但代码中有 **两个地方** 静默丢弃了 thinking 内容。

### 完整调用链

```
Turn 1: DeepSeek API 返回
  → reasoning_content + content + tool_calls
    → llmcore.py: _parse_openai_sse() 正确解析出 thinking/text/tool_use blocks
      → openai_agentmain.py: _content_blocks_to_output_items()
        ❌ thinking block 被丢弃（只处理 text 和 tool_use）
          → output items 中没有 reasoning 信息
            → Runner 存储到 conversation history

Turn 2: 带上工具结果请求 API
  → _prepare_request() → Converter.items_to_messages()
    → 因为 output items 中无 reasoning item
      → chat message 中没有 reasoning_content
        → _chat_messages_to_claude_messages()
          ❌ 没有 reasoning_content 可以转换为 thinking block
            → _msgs_claude2oai() 转换出的 OAI message 缺少 reasoning_content
              → DeepSeek API 报错 400
```

### 两个丢失点

| # | 文件 | 方法 | 行号 | 说明 |
|---|------|------|------|------|
| 1 | `core/openai_agentmain.py` | `_content_blocks_to_output_items()` | 759-803 | 只处理 `text` 和 `tool_use` 类型的 block，`thinking` 类型被静默跳过 |
| 2 | `core/openai_agentmain.py` | `_chat_messages_to_claude_messages()` | 561-592 | 只从 `message.content` 提取 content blocks，`message.reasoning_content` 在 message 级别被忽略 |

## 修复内容

### 修复 1: `_content_blocks_to_output_items()` (line 757)

在 `GenericAgentSDKModel._content_blocks_to_output_items()` 中增加对 `thinking` 类型 block 的处理：

```python
# 在 output_items 收集 text blocks 之前，先处理 thinking blocks
# 将 thinking block 转换为 reasoning item (dict 格式，因为 Converter 只接受 dict)
for block in content_blocks:
    if block.get("type") != "thinking":
        continue
    thinking_text = str(block.get("thinking") or "")
    if thinking_text:
        output_items.append({
            "id": FAKE_RESPONSES_ID,
            "type": "reasoning",
            "summary": [{"text": thinking_text, "type": "summary_text"}],
        })
```

**为什么用 dict 而非 Pydantic model？**

`Converter.maybe_reasoning_message()` 使用 `isinstance(item, dict)` 检查，不接受 Pydantic model 对象。虽然 Runner 内部会通过 `model_dump()` 序列化 Pydantic models，但 reasoning item 使用 dict 格式更安全、兼容性更好。

### 修复 2: `_chat_messages_to_claude_messages()` (line 565)

在处理 assistant role 消息时，从 `reasoning_content` 字段提取并转换为 `thinking` block：

```python
if role == "assistant":
    flush_tool_results()
    content_blocks = _message_content_to_claude_blocks(message.get("content"))

    # Preserve reasoning_content as a thinking block so it is passed
    # back to the API on subsequent turns (required by DeepSeek v4).
    reasoning = message.get("reasoning_content")
    if reasoning and isinstance(reasoning, str) and reasoning.strip():
        content_blocks.insert(0, {"type": "thinking", "thinking": reasoning})

    for tool_call in message.get("tool_calls") or []:
        ...
```

## 修复后的完整链路

```
Turn 1: DeepSeek API 返回
  → reasoning_content + content + tool_calls
    → _parse_openai_sse() 解析出 thinking/text/tool_use blocks
      → _content_blocks_to_output_items()
        ✅ thinking → reasoning item (dict with summary)
        ✅ text → ResponseOutputMessage
        ✅ tool_use → ResponseFunctionToolCall
          → output items 包含完整信息

Turn 2: 带上工具结果请求 API
  → _prepare_request() → Converter.items_to_messages()
    → reasoning item → pending_reasoning_content
      → apply_pending_reasoning_content() → reasoning_content on assistant msg
        ✅ chat message 包含 reasoning_content
          → _chat_messages_to_claude_messages()
            ✅ reasoning_content → thinking block in content
              → _msgs_claude2oai()
                ✅ thinking block → reasoning_content on OAI message
                  → DeepSeek API: thinking 内容完整保留 ✅
```

## 测试验证

### 单元测试 (5 个测试用例，全部通过)

1. **thinking + text + tool_use** → reasoning item 被正确创建，顺序正确
2. **无 thinking block** → 不创建 reasoning item
3. **thinking + tool_use（无 text）** → 正确输出 reasoning + function_call
4. **reasoning_content → thinking block** → `_chat_messages_to_claude_messages` 正确转换
5. **无 reasoning_content** → 不创建 thinking block

### 集成测试 (全部通过)

完整模拟了 2-turn agent 对话流程：
- `_content_blocks_to_output_items` → Runner 序列化 → `Converter.items_to_messages` → `_chat_messages_to_claude_messages` → `_msgs_claude2oai`
- 验证 thinking 内容在全链路中不丢失

### API 测试

直接调用 DeepSeek API 验证 tool result 消息可被正确接收（HTTP 200）。

## 影响范围

- **仅影响** `core/openai_agentmain.py`（OpenAI Orchestrated Agent 后端）
- **不影响** `core/agentmain.py`（Classic GenericAgent 后端）：classic 后端使用不同的消息管理方式，不经过 `_content_blocks_to_output_items`
- 对非 DeepSeek 模型无影响：当没有 thinking block 时不创建 reasoning item
