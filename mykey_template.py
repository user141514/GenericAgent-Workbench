"""
Minimal GenericAgent config template.

Copy this file to mykey.py and replace the placeholder token before use.
"""

native_claude_config = {
    'name': 'glm-5',
    'apikey': 'REPLACE_WITH_YOUR_TOKEN',
    'apibase': 'https://coding.dashscope.aliyuncs.com/apps/anthropic',
    'model': 'glm-5',
    'max_retries': 3,
    'connect_timeout': 10,
    'read_timeout': 120,
}
