# stapp.py 性能深度审计报告

**日期**: 2026-06-13  
**审计方法**: 静态代码分析 + 运行时进程采样 (10s窗口)  
**审计对象**: `frontends/stapp.py` (893行)  
**运行时环境**: 3进程 Streamlit 实例 (PID 17672/93644/104488, 共447MB)

---

## 一、执行摘要

stapp.py存在**一个关键性能缺陷**(P0级)和**四个中等/低优先级问题**。P0——基于轮询的流式渲染循环——是导致rag-env进程空载时仍消耗37-45% CPU的根本原因。修复P0预估可将空载CPU从~40%降至<5%，内存从447MB降至<200MB(合并冗余进程)。

---

## 二、静态分析发现

### P0: 轮询式流式渲染循环 (L885-886)

```python
# 每200ms触发一次完整脚本重执行
time.sleep(0.2)
st.rerun()
```

**影响链**:
1. `st.rerun()` → 893行脚本全量重执行
2. 每次重跑: CSS文件I/O(L82-84) + 消息st.empty()重建(L631-648) + Session state检查 + 所有import
3. 空闲时 5 reruns/sec × 893 lines = ~4400 lines/sec 无效执行
4. 实测: PID 93644主线程 user_time=102.6s, 空载CPU 37-45%

### P1: st.empty()在消息循环中 (L631-648)

每轮渲染为每条历史消息创建新 st.empty() 占位符。有st.chat_message()容器保护，视觉低风险，但CPU开销随消息数线性增长。

### P2: 缓存严重不足 (仅1处 @st.cache_resource)

**未缓存的昂贵操作**: CSS文件读取(L82-84)、get_history_files()(L316)、ensure_stapp_session_state()

### P3: 模块级阻塞I/O (L82-85)

CSS文件在每次脚本加载时同步读取，包括每次st.rerun()。

### P4: FIN_WAIT2连接泄漏

PID 93644 port 18569存在FIN_WAIT2状态的连接。

---

## 三、运行时分析

### 3.1 三进程架构 (共447MB)

| PID | 镜像 | 内存 | 线程 | 空载CPU | 角色 |
|-----|------|------|------|---------|------|
| 17672 | streamlit.exe | 35MB | 1 | 0% | Streamlit wrapper |
| 93644 | rag-env python | 321MB | 13 | 37-45% | 实际server |
| 104488 | anaconda0 python | 91MB | 5 | ~0% | 冗余实例 |

**关键发现**:
- 3个进程同时运行——PID 104488/17672是重复启动产物
- PID 93644空载37-45% CPU, 主线程user_time=102.6s+system_time=44.7s
- 密集Python字节码执行 + 频繁系统调用

### 3.2 线程详情 (PID 93644)

| TID | user_time | system_time | 状态 |
|-----|-----------|-------------|------|
| 97308 | 102.6s | 44.7s | 主线程, 极高CPU |
| 104716 | 3.3s | 17.8s | 活跃 |
| 105364 | 3.5s | 0.8s | 活跃 |
| 其余10线程 | <2s | <1s | 空闲 |

---

## 四、修复建议(按ROI排序)

### P0修复: 流式渲染退避 (预估CPU: 40%→5%)

```python
# 方案A — 最小改动: 空闲退避
if st.session_state.get("partial_response", "") == _last_partial:
    time.sleep(0.5)  # 空闲→2Hz
else:
    time.sleep(0.1)  # 活跃→10Hz
_last_partial = st.session_state.get("partial_response", "")
st.rerun()
```

### P1修复: 消息容器缓存
对已渲染消息跳过st.empty()重建，用session_state跟踪已渲染ID集合。

### P2修复: 增加缓存装饰器
- CSS内容 → @st.cache_resource
- get_history_files() → @st.cache_data(ttl=30)

### 进程清理
终止冗余PID 104488(91MB)，确保单server实例。

---

## 五、与 streamlit_pitfalls.md 交叉验证

| 已知陷阱 | 当前状态 |
|----------|---------|
| st.dialog弹窗乱跳 | ✅ 已修复 |
| turn_end_callback时序 | ✅ 已修复 |
| 对话删除状态残留 | ✅ 已修复 |
| st.empty()重渲染 | ⚠️ L634仍在使用(低风险) |
| 轮询循环CPU浪费 | ❌ **新发现** — 不在原清单 |

---

## 六、下一步

1. [ ] 实施P0修复: 空闲退避方案(~3行代码)
2. [ ] 清理冗余进程: 终止PID 104488
3. [ ] 实施P2修复: CSS+history_files缓存
4. [ ] 回归测试: 修复后重新采样CPU/MEM
