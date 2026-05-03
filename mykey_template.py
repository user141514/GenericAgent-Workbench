"""
GenericAgent configuration template — triple-model + SMTP for mobile auth.

Copy this file to mykey.py and replace ALL placeholder values before use.
DO NOT commit mykey.py to version control — it is already in .gitignore.

Each key represents an independent model configuration.
The frontend sidebar will show all models for one-click switching.

Pattern:
  key1_<backend_type>_config  → Primary model
  key2_<backend_type>_config  → Secondary model
  key3_<backend_type>_config  → Tertiary model

Backend types:
  native_claude → Anthropic Messages API (Claude, GLM, DeepSeek in Claude mode)
  native_oai    → OpenAI Chat Completions API (GPT, DeepSeek, other OAI-compatible)
  claude        → Legacy text-protocol Claude
  oai           → Legacy text-protocol OpenAI
"""

# ── SMTP email config (for mobile email verification login) ──
# QQ email: Login QQ email → Settings → Account → Enable SMTP → Get auth code
# Fill in below (password is the SMTP auth code, NOT your QQ password)
smtp_email = "REPLACE_WITH_YOUR_EMAIL@qq.com"
smtp_password = "REPLACE_WITH_YOUR_SMTP_AUTH_CODE"
smtp_server = "smtp.qq.com"
smtp_port = 465
allowed_email = "REPLACE_WITH_YOUR_EMAIL@qq.com"    # Only allow this email to login
streamlit_password = "你的密码"                        # Streamlit remote access password

# ── Key1: Primary model (example: Claude via OpenAI-compatible API) ──
key1_native_oai_config = {
    'name': 'your-primary-model',
    'apikey': 'REPLACE_WITH_YOUR_KEY1_TOKEN',
    'apibase': 'https://your-api-endpoint.com',
    'model': 'your-model-name',
    'stream': False,
    'max_retries': 1,
    'connect_timeout': 10,
    'read_timeout': 300,
}

# ── Key2: Secondary model (example: stream mode for real-time output) ──
key2_native_oai_config = {
    'name': 'your-secondary-model',
    'apikey': 'REPLACE_WITH_YOUR_KEY2_TOKEN',
    'apibase': 'https://your-api-endpoint.com',
    'model': 'your-model-name',
    'stream': True,
    'max_retries': 1,
    'connect_timeout': 10,
    'read_timeout': 300,
}

# ── Key3: Tertiary model (example: powerful model for complex tasks) ──
key3_native_oai_config = {
    'name': 'your-tertiary-model',
    'apikey': 'REPLACE_WITH_YOUR_KEY3_TOKEN',
    'apibase': 'https://your-api-endpoint.com',
    'model': 'your-model-name',
    'stream': False,
    'max_retries': 1,
    'connect_timeout': 10,
    'read_timeout': 300,
}
