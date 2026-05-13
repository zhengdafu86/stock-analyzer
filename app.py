"""
智能股票分析 PWA - 后端 API + 前端静态文件 一体化服务

启动方式:
  python app.py

然后:
  电脑浏览器打开: http://localhost:5000
  iPhone (同WiFi): http://你电脑的IP:5000
"""
from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
from datetime import datetime
import os
import traceback

import config
from stock_data import (
    search_stocks, get_stock_quote, get_batch_quotes,
    get_kline_data, get_fundamentals, get_market_overview
)
from technical import calculate_all_indicators
from ai_analysis import generate_ai_analysis

app = Flask(__name__, static_folder='static')
CORS(app)

_cache = {}

def get_cached(key, ttl=60):
    if key in _cache:
        data, ts = _cache[key]
        if (datetime.now() - ts).seconds < ttl:
            return data
    return None

def set_cache(key, data):
    _cache[key] = (data, datetime.now())


# ============ 前端页面 ============

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)


# ============ API 路由 ============

@app.route('/api/stocks/search')
def api_search():
    keyword = request.args.get('keyword', '')
    if not keyword:
        return jsonify([])
    cache_key = f'search:{keyword}'
    cached = get_cached(cache_key, ttl=300)
    if cached:
        return jsonify(cached)
    results = search_stocks(keyword)
    set_cache(cache_key, results)
    return jsonify(results)

@app.route('/api/stocks/<code>/quote')
def api_quote(code):
    cache_key = f'quote:{code}'
    cached = get_cached(cache_key, ttl=config.QUOTE_CACHE_TTL)
    if cached:
        return jsonify(cached)
    quote = get_stock_quote(code)
    if quote:
        set_cache(cache_key, quote)
    return jsonify(quote)

@app.route('/api/stocks/batch-quotes', methods=['POST'])
def api_batch_quotes():
    data = request.get_json()
    codes = data.get('codes', [])
    if not codes:
        return jsonify({})
    cache_key = f'batch:{",".join(sorted(codes))}'
    cached = get_cached(cache_key, ttl=config.QUOTE_CACHE_TTL)
    if cached:
        return jsonify(cached)
    quotes = get_batch_quotes(codes)
    set_cache(cache_key, quotes)
    return jsonify(quotes)

@app.route('/api/stocks/<code>/report', methods=['GET', 'POST'])
def api_report(code):
    # POST 请求支持自定义 prompt
    user_prompt = ''
    if request.method == 'POST':
        data = request.get_json() or {}
        user_prompt = data.get('prompt', '')

    # 有自定义 prompt 时不使用缓存
    if not user_prompt:
        cache_key = f'report:{code}'
        cached = get_cached(cache_key, ttl=config.REPORT_CACHE_TTL)
        if cached:
            return jsonify(cached)

    try:
        quote = get_stock_quote(code)
        if not quote:
            return jsonify({'error': f'未找到股票 {code}'}), 404
        kline = get_kline_data(code, period='daily', count=120)
        technical = calculate_all_indicators(kline)
        fundamental = get_fundamentals(code)
        ai_analysis = generate_ai_analysis(quote, technical, fundamental, user_prompt)
        report = {
            **quote,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'technical': technical,
            'fundamental': fundamental,
            'ai_analysis': ai_analysis
        }
        if not user_prompt:
            set_cache(f'report:{code}', report)
        return jsonify(report)
    except Exception as e:
        print(f"生成报告失败 {code}: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/stocks/<code>/technical')
def api_technical(code):
    kline = get_kline_data(code)
    technical = calculate_all_indicators(kline)
    return jsonify(technical)

@app.route('/api/stocks/<code>/fundamentals')
def api_fundamentals(code):
    fundamental = get_fundamentals(code)
    return jsonify(fundamental)

@app.route('/api/stocks/<code>/ai-analysis')
def api_ai_analysis(code):
    quote = get_stock_quote(code)
    kline = get_kline_data(code)
    technical = calculate_all_indicators(kline)
    fundamental = get_fundamentals(code)
    analysis = generate_ai_analysis(quote, technical, fundamental)
    return jsonify(analysis)

@app.route('/api/stocks/<code>/kline')
def api_kline(code):
    period = request.args.get('period', 'daily')
    count = int(request.args.get('count', 60))
    kline = get_kline_data(code, period, count)
    if kline.empty:
        return jsonify([])
    return jsonify(kline.to_dict('records'))

@app.route('/api/market/overview')
def api_market_overview():
    cache_key = 'market:overview'
    cached = get_cached(cache_key, ttl=60)
    if cached:
        return jsonify(cached)
    overview = get_market_overview()
    set_cache(cache_key, overview)
    return jsonify(overview)

@app.route('/api/health')
def api_health():
    return jsonify({
        'status': 'ok',
        'time': datetime.now().isoformat(),
        'ai_provider': config.AI_PROVIDER
    })


# ============ 启动 ============

if __name__ == '__main__':
    import socket
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except:
        local_ip = '未知'

    print(f"""
╔══════════════════════════════════════════════╗
║       智能股票分析 PWA 服务已启动            ║
╠══════════════════════════════════════════════╣
║                                              ║
║  电脑访问:  http://localhost:{config.PORT}            ║
║  手机访问:  http://{local_ip}:{config.PORT}       ║
║                                              ║
║  AI 模式:   {config.AI_PROVIDER:<20}             ║
║                                              ║
║  iPhone 添加到主屏幕:                        ║
║  Safari 打开上方手机地址                     ║
║  → 点击分享按钮 → 添加到主屏幕              ║
║                                              ║
╚══════════════════════════════════════════════╝
    """)

    app.run(host='0.0.0.0', port=config.PORT, debug=config.DEBUG)
