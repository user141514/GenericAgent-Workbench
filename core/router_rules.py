"""
规则快速匹配层 - Router Rules
在LLM路由前进行快速关键词/模式匹配，降低路由延迟
"""
import re
from typing import Optional
from dataclasses import dataclass

@dataclass
class RouteResult:
    """路由结果"""
    target: str  # "chat" / "executor" / None
    matched_rule: str = ""  # 匹配的规则名称
    confidence: float = 1.0  # 置信度

class RouterRules:
    """规则快速匹配器"""
    
    # 执行器关键词 - 需要实际操作的任务
    EXECUTOR_KEYWORDS = [
        # 文件操作
        "读取", "读文件", "写文件", "修改文件", "删除文件", "创建文件",
        "打开文件", "保存文件", "文件内容", "查看文件",
        # 代码执行
        "运行", "执行", "运行代码", "执行代码", "跑一下", "试运行",
        "pip", "安装", "卸载", "import",
        # 浏览器操作
        "浏览", "网页", "网站", "搜索", "查找", "打开链接",
        "点击", "输入", "填写", "提交",
        # 系统操作
        "命令", "终端", "shell", "bash", "cmd", "powershell",
        "进程", "服务", "启动", "停止", "重启",
        # 开发操作
        "git", "commit", "push", "pull", "clone", "merge",
        "调试", "测试", "build", "编译",
        # 明确的动作动词
        "帮我", "请", "把", "将", "给", "让", "使",
    ]
    
    # 聊天关键词 - 纯对话/解释类
    CHAT_KEYWORDS = [
        # 问候
        "你好", "您好", "早上好", "晚上好", "hi", "hello", "hey",
        # 感谢
        "谢谢", "感谢", "thanks", "thank you",
        # 纯询问/解释
        "是什么", "什么是", "为什么", "怎么理解", "如何理解",
        "解释一下", "说明一下", "介绍一下", "讲一下",
        "你觉得", "你认为", "怎么看", "怎么看待",
        "有什么区别", "有什么相同", "比较一下",
        "优点", "缺点", "好处", "坏处",
        # 纯问题句式
        "吗？", "呢？", "如何？", "怎样？",
    ]
    
    # 命令模式 (正则) - 斜杠命令直接路由
    COMMAND_PATTERNS = [
        (r"^/(run|read|write|search|browse|open|exec)", "executor"),
        (r"^/(chat|ask|explain)", "chat"),
    ]
    
    # 排除模式 - 即使有关键词也不直接路由
    EXCLUDE_PATTERNS = [
        r"只是.*问一下",  # "只是想问一下..."
        r"想(了解|知道)",  # "想了解..."
        r"能(不能|否).*吗",  # 疑问句
    ]
    
    @classmethod
    def match(cls, query: str) -> RouteResult:
        """
        快速匹配查询，返回路由结果
        
        Args:
            query: 用户查询文本
            
        Returns:
            RouteResult: 包含目标路由和置信度
        """
        if not query or not query.strip():
            return RouteResult(target=None)
        
        query = query.strip()
        query_lower = query.lower()
        
        # 1. 检查排除模式 (优先级最高)
        for pattern in cls.EXCLUDE_PATTERNS:
            if re.search(pattern, query):
                return RouteResult(target=None, matched_rule="excluded")
        
        # 2. 检查命令模式
        for pattern, target in cls.COMMAND_PATTERNS:
            if re.match(pattern, query_lower):
                return RouteResult(
                    target=target,
                    matched_rule=f"command:{pattern}",
                    confidence=1.0
                )
        
        # 3. 统计关键词命中
        executor_hits = sum(1 for kw in cls.EXECUTOR_KEYWORDS if kw in query)
        chat_hits = sum(1 for kw in cls.CHAT_KEYWORDS if kw in query)
        
        # 4. 判断路由
        # 执行器关键词权重更高 (动作性更强)
        executor_score = executor_hits * 1.5
        chat_score = chat_hits * 1.0
        
        # 明确的动作动词开头 -> executor
        action_verbs = ["帮我", "请", "把", "将", "给", "让", "读取", "运行", "执行", "搜索", "浏览", "写", "改", "删", "创建", "打开"]
        for verb in action_verbs:
            if query.startswith(verb):
                return RouteResult(
                    target="executor",
                    matched_rule=f"action_start:{verb}",
                    confidence=0.95
                )
        
        # 根据得分判断
        if executor_score > chat_score and executor_hits > 0:
            return RouteResult(
                target="executor",
                matched_rule=f"keywords:executor({executor_hits})",
                confidence=min(0.9, 0.6 + executor_hits * 0.1)
            )
        
        if chat_score > executor_score and chat_hits > 0:
            return RouteResult(
                target="chat",
                matched_rule=f"keywords:chat({chat_hits})",
                confidence=min(0.9, 0.6 + chat_hits * 0.1)
            )
        
        # 5. 未命中规则，返回None走LLM路由
        return RouteResult(target=None, matched_rule="no_match")
    
    @classmethod
    def get_stats(cls) -> dict:
        """获取规则统计信息"""
        return {
            "executor_keywords": len(cls.EXECUTOR_KEYWORDS),
            "chat_keywords": len(cls.CHAT_KEYWORDS),
            "command_patterns": len(cls.COMMAND_PATTERNS),
            "exclude_patterns": len(cls.EXCLUDE_PATTERNS),
        }


# 便捷函数
def quick_route(query: str) -> Optional[str]:
    """
    快速路由函数
    
    Args:
        query: 用户查询
        
    Returns:
        "chat" / "executor" / None
    """
    result = RouterRules.match(query)
    return result.target


class RouterStats:
    """路由统计 - 记录命中率用于优化"""
    
    _stats = {
        "total_queries": 0,
        "chat_hits": 0,
        "executor_hits": 0,
        "no_match": 0,
        "rule_breakdown": {},  # {rule_name: count}
        "unmatched_queries": [],  # 未匹配的查询样本
    }
    _max_unmatched_samples = 100  # 最大未匹配样本数
    
    @classmethod
    def record(cls, result: RouteResult, query: str = ""):
        """记录路由结果"""
        cls._stats["total_queries"] += 1
        
        if result.target == "chat":
            cls._stats["chat_hits"] += 1
        elif result.target == "executor":
            cls._stats["executor_hits"] += 1
        else:
            cls._stats["no_match"] += 1
            # 记录未匹配查询样本
            if query and len(cls._stats["unmatched_queries"]) < cls._max_unmatched_samples:
                cls._stats["unmatched_queries"].append(query[:100])
        
        # 记录规则命中分布
        if result.matched_rule:
            cls._stats["rule_breakdown"][result.matched_rule] = \
                cls._stats["rule_breakdown"].get(result.matched_rule, 0) + 1
    
    @classmethod
    def get_stats(cls) -> dict:
        """获取统计信息"""
        total = cls._stats["total_queries"]
        if total == 0:
            return {"message": "暂无统计数据"}
        
        return {
            "total_queries": total,
            "hit_rate": f"{(cls._stats['chat_hits'] + cls._stats['executor_hits']) / total * 100:.1f}%",
            "chat_rate": f"{cls._stats['chat_hits'] / total * 100:.1f}%",
            "executor_rate": f"{cls._stats['executor_hits'] / total * 100:.1f}%",
            "no_match_rate": f"{cls._stats['no_match'] / total * 100:.1f}%",
            "top_rules": sorted(
                cls._stats["rule_breakdown"].items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10],
            "unmatched_samples": cls._stats["unmatched_queries"][-10:],
        }
    
    @classmethod
    def reset(cls):
        """重置统计"""
        cls._stats = {
            "total_queries": 0,
            "chat_hits": 0,
            "executor_hits": 0,
            "no_match": 0,
            "rule_breakdown": {},
            "unmatched_queries": [],
        }