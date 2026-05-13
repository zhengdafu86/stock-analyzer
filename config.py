"""
配置文件 - 请根据你的实际情况修改
"""
import os

# Flask 配置
DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
PORT = int(os.getenv('PORT', 5000))
HOST = os.getenv('HOST', '0.0.0.0')

# AI 分析配置 - 支持多种 LLM 提供商
# 选项: "openai", "deepseek", "zhipu", "none"
AI_PROVIDER = os.getenv('AI_PROVIDER', 'deepseek')

# DeepSeek API (推荐，便宜好用)
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', 'your-deepseek-api-key')
DEEPSEEK_BASE_URL = 'https://api.deepseek.com'
DEEPSEEK_MODEL = 'deepseek-chat'

# OpenAI API
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'your-openai-api-key')
OPENAI_MODEL = 'gpt-4o-mini'

# 智谱 AI (国产，免费额度多)
ZHIPU_API_KEY = os.getenv('ZHIPU_API_KEY', 'your-zhipu-api-key')
ZHIPU_MODEL = 'glm-4-flash'

# 定时任务配置
# 每天几点生成报告（24小时制）
REPORT_HOUR = int(os.getenv('REPORT_HOUR', 8))
REPORT_MINUTE = int(os.getenv('REPORT_MINUTE', 30))

# 缓存配置（秒）
QUOTE_CACHE_TTL = 30        # 行情缓存 30 秒
REPORT_CACHE_TTL = 3600     # 报告缓存 1 小时
