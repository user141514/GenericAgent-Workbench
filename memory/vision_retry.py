"""
Vision API 重试封装
解决vision_sop中"无重试机制"风险，提供带指数退避的可靠调用层
"""
import time
import functools
from typing import Union, Optional
from pathlib import Path

def retry_vision(
    ask_vision_func,
    image_input: Union[str, Path, object],
    prompt: Optional[str] = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    **kwargs
) -> str:
    """
    带指数退避的vision调用封装
    
    Args:
        ask_vision_func: 原始ask_vision函数
        image_input: 图片路径或PIL Image
        prompt: 提示词
        max_retries: 最大重试次数(默认3)
        base_delay: 初始延迟秒数(默认1.0)
        max_delay: 最大延迟秒数(默认30.0)
        **kwargs: 传递给ask_vision的其他参数
        
    Returns:
        str: 成功返回结果，失败返回"Error: ..."
    """
    for attempt in range(max_retries + 1):
        try:
            result = ask_vision_func(image_input, prompt=prompt, **kwargs)
            if not result.startswith("Error:"):
                return result
            # 非网络错误不重试
            if "503" not in result and "timeout" not in result.lower():
                return result
        except Exception as e:
            result = f"Error: {e}"
        
        if attempt < max_retries:
            delay = min(base_delay * (2 ** attempt), max_delay)
            time.sleep(delay)
    
    return result

# 装饰器版本
def with_retry(max_retries=3, base_delay=1.0, max_delay=30.0):
    """装饰器：为ask_vision添加重试能力"""
    def decorator(ask_vision_func):
        @functools.wraps(ask_vision_func)
        def wrapper(image_input, prompt=None, **kwargs):
            return retry_vision(
                ask_vision_func, image_input, prompt,
                max_retries, base_delay, max_delay, **kwargs
            )
        return wrapper
    return decorator

# 便捷函数
def ask_vision_retry(image_input, prompt=None, max_retries=3, **kwargs):
    """
    带重试的vision调用（自动导入ask_vision）
    用法: from vision_retry import ask_vision_retry
    """
    try:
        from vision_api import ask_vision
        return retry_vision(ask_vision, image_input, prompt, max_retries, **kwargs)
    except ImportError:
        return "Error: vision_api not found, check mykey.py exists"
