"""
AI 智能分析模块
调用 DeepSeek / OpenAI / 智谱 大语言模型
基于技术面和基本面数据生成 Markdown 格式的自然语言分析报告
（输出风格与 DeepSeek App 对话一致）
"""
import json
import config
from datetime import datetime

# 仅在需要 AI API 时导入 openai
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def generate_ai_analysis(stock_info: dict, technical: dict, fundamental: dict) -> dict:
    """
    使用 AI 生成综合分析报告
    返回: { score, signal, detail, ai_provider }
    """
    provider = config.AI_PROVIDER

    if provider == 'none':
        return _rule_based_analysis(stock_info, technical, fundamental)

    prompt = _build_analysis_prompt(stock_info, technical, fundamental)

    try:
        if provider == 'deepseek':
            return _call_llm(prompt, config.DEEPSEEK_API_KEY, config.DEEPSEEK_BASE_URL, config.DEEPSEEK_MODEL, 'DeepSeek')
        elif provider == 'openai':
            return _call_llm(prompt, config.OPENAI_API_KEY, 'https://api.openai.com/v1', config.OPENAI_MODEL, 'OpenAI')
        elif provider == 'zhipu':
            return _call_llm(prompt, config.ZHIPU_API_KEY, 'https://open.bigmodel.cn/api/paas/v4/', config.ZHIPU_MODEL, '智谱AI')
        else:
            return _rule_based_analysis(stock_info, technical, fundamental)
    except Exception as e:
        print(f"AI 分析失败，回退到规则引擎: {e}")
        return _rule_based_analysis(stock_info, technical, fundamental)


def _build_analysis_prompt(stock_info: dict, technical: dict, fundamental: dict) -> str:
    """构建提示词 —— 让 AI 像在 DeepSeek App 里回答一样"""
    today = datetime.now().strftime('%Y年%m月%d日')

    # 格式化市值
    mkt_cap = fundamental.get('market_cap', 0)
    if mkt_cap >= 1e12:
        mkt_str = f'{mkt_cap/1e12:.2f}万亿'
    elif mkt_cap >= 1e8:
        mkt_str = f'{mkt_cap/1e8:.2f}亿'
    else:
        mkt_str = f'{mkt_cap:.0f}元'

    return f"""今天是{today}，请帮我分析一下 {stock_info.get('name', '')}（{stock_info.get('code', '')}）这只股票，以下是最新的实时数据：

📊 **实时行情**
- 最新价: {stock_info.get('price', 0)} 元，涨跌幅: {stock_info.get('change_percent', 0)}%
- 今开: {stock_info.get('open', 0)}，最高: {stock_info.get('high', 0)}，最低: {stock_info.get('low', 0)}，昨收: {stock_info.get('prev_close', 0)}
- 成交量: {stock_info.get('volume', 0)} 手，成交额: {stock_info.get('amount', 0):.0f} 元，换手率: {stock_info.get('turnover_rate', 0)}%

📈 **技术指标**（近120个交易日）
- 均线: {json.dumps(technical.get('ma', []), ensure_ascii=False)}
- MACD: DIF={technical.get('macd', {}).get('dif', 0)}, DEA={technical.get('macd', {}).get('dea', 0)}, 柱状值={technical.get('macd', {}).get('histogram', 0)}, 信号: {technical.get('macd', {}).get('signal', '无')}
- RSI: RSI6={technical.get('rsi', {}).get('rsi6', 50)}, RSI12={technical.get('rsi', {}).get('rsi12', 50)}, RSI24={technical.get('rsi', {}).get('rsi24', 50)}
- KDJ: K={technical.get('kdj', {}).get('k', 50)}, D={technical.get('kdj', {}).get('d', 50)}, J={technical.get('kdj', {}).get('j', 50)}, 信号: {technical.get('kdj', {}).get('signal', '无')}
- 布林带: 上轨={technical.get('boll', {}).get('upper', 0)}, 中轨={technical.get('boll', {}).get('middle', 0)}, 下轨={technical.get('boll', {}).get('lower', 0)}
- 成交量分析: 量比={technical.get('volume', {}).get('ratio', 1)}, {technical.get('volume', {}).get('signal', '')}

📋 **基本面**
- 市盈率(PE): {fundamental.get('pe', 0)}，市净率(PB): {fundamental.get('pb', 0)}，总市值: {mkt_str}
- EPS: {fundamental.get('eps', 0)}，ROE: {fundamental.get('roe', 0)}%
- 毛利率: {fundamental.get('gross_margin', 0)}%，净利率: {fundamental.get('net_margin', 0)}%
- 营收增长: {fundamental.get('revenue_growth', 0)}%，净利润增长: {fundamental.get('profit_growth', 0)}%
- 资产负债率: {fundamental.get('debt_ratio', 0)}%
- 所属行业: {fundamental.get('industry', '--')}

请你像在 DeepSeek 对话中一样，用自然的中文 Markdown 格式给我一份完整的分析报告。要求：
1. 使用 Markdown 标题、加粗、列表等排版，让内容清晰易读
2. 涵盖：趋势研判、技术分析、基本面分析、资金面、操作建议、风险提示
3. 引用具体数据，不要空泛
4. 给出明确的综合评分（0-100）和操作信号（强烈买入/买入/中性/卖出/强烈卖出）
5. 最后加上免责声明"""


def _call_llm(prompt: str, api_key: str, base_url: str, model: str, provider_name: str) -> dict:
    """统一调用 LLM"""
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一位资深 A 股投资分析师。用户会给你最新的实时行情和技术指标数据，请基于这些数据撰写专业的分析报告。用 Markdown 格式输出，风格自然专业，就像你在和用户对话一样。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,
        max_tokens=3000,
    )
    content = response.choices[0].message.content

    # 从文本中提取评分和信号
    score = _extract_score(content)
    signal = _extract_signal(content, score)

    return {
        'score': score,
        'signal': signal,
        'summary': signal,
        'points': [],
        'suggestion': '',
        'detail': content,
        'ai_provider': provider_name,
    }


def _extract_score(text: str) -> int:
    """从 AI 输出文本中提取评分"""
    import re
    # 匹配 "综合评分：65" "评分：70/100" "综合评分: 55分" 等
    patterns = [
        r'综合评分[：:]\s*(\d{1,3})',
        r'评分[：:]\s*(\d{1,3})',
        r'(\d{1,3})\s*/\s*100',
        r'(\d{1,3})\s*分',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            s = int(m.group(1))
            if 0 <= s <= 100:
                return s
    return 50


def _extract_signal(text: str, score: int) -> str:
    """从 AI 输出文本中提取信号，或根据评分推断"""
    for sig in ['强烈买入', '强烈卖出', '买入', '卖出', '中性', '观望']:
        if sig in text:
            if sig == '观望':
                return '中性'
            return sig

    # 根据评分推断
    if score >= 80:
        return '强烈买入'
    elif score >= 65:
        return '买入'
    elif score >= 45:
        return '中性'
    elif score >= 30:
        return '卖出'
    else:
        return '强烈卖出'


def _rule_based_analysis(stock_info: dict, technical: dict, fundamental: dict) -> dict:
    """
    规则引擎分析（不依赖 AI API 的备用方案）
    """
    score = 50
    detail_parts = []

    name = stock_info.get('name', '未知')
    code = stock_info.get('code', '未知')
    price = stock_info.get('price', 0)
    change = stock_info.get('change_percent', 0)

    detail_parts.append(f"## {name}（{code}）技术分析报告\n")
    detail_parts.append(f"**最新价格**：{price} 元，今日涨跌幅 {change}%\n")

    # --- 技术面 ---
    detail_parts.append("### 📈 技术面分析\n")

    ma_list = technical.get('ma', [])
    bullish_ma = sum(1 for m in ma_list if m.get('signal') == '多头')
    if bullish_ma >= 3:
        score += 10
        detail_parts.append(f"**均线系统**：多头排列，{bullish_ma}条均线形成支撑，中短期趋势向好。\n")
    elif bullish_ma <= 1:
        score -= 10
        detail_parts.append("**均线系统**：空头排列，各周期均线形成压制，整体趋势偏弱。\n")
    else:
        detail_parts.append("**均线系统**：均线交织，趋势不明朗，多空力量相对均衡。\n")

    macd = technical.get('macd', {})
    macd_signal = macd.get('signal', '')
    dif = macd.get('dif', 0)
    dea = macd.get('dea', 0)
    if '金叉' in macd_signal:
        score += 8
        detail_parts.append(f"**MACD**：出现金叉信号，DIF({dif})上穿DEA({dea})，短期动能转强。\n")
    elif '死叉' in macd_signal:
        score -= 8
        detail_parts.append(f"**MACD**：出现死叉信号，DIF({dif})下穿DEA({dea})，短期动能减弱。\n")
    elif '红柱放大' in macd_signal:
        score += 5
        detail_parts.append(f"**MACD**：红柱持续放大，多头力量增强，DIF={dif}。\n")
    elif '绿柱放大' in macd_signal:
        score -= 5
        detail_parts.append(f"**MACD**：绿柱持续放大，空头力量占优，DIF={dif}。\n")

    rsi = technical.get('rsi', {})
    rsi6 = rsi.get('rsi6', 50)
    if rsi6 >= 80:
        score -= 10
        detail_parts.append(f"**RSI**：RSI(6)={rsi6}，已进入**严重超买区间**，短期回调风险较大。\n")
    elif rsi6 >= 70:
        score -= 5
        detail_parts.append(f"**RSI**：RSI(6)={rsi6}，接近超买区间，注意短期调整压力。\n")
    elif rsi6 <= 20:
        score += 10
        detail_parts.append(f"**RSI**：RSI(6)={rsi6}，处于**严重超卖区间**，技术性反弹需求强烈。\n")
    elif rsi6 <= 30:
        score += 5
        detail_parts.append(f"**RSI**：RSI(6)={rsi6}，接近超卖区间，存在反弹可能。\n")
    else:
        detail_parts.append(f"**RSI**：RSI(6)={rsi6}，处于中性区间。\n")

    kdj = technical.get('kdj', {})
    kdj_signal = kdj.get('signal', '')
    if '金叉' in kdj_signal:
        score += 5
        detail_parts.append(f"**KDJ**：出现金叉，K={kdj.get('k',0)}，D={kdj.get('d',0)}，J={kdj.get('j',0)}。\n")
    elif '死叉' in kdj_signal:
        score -= 5
        detail_parts.append(f"**KDJ**：出现死叉，K={kdj.get('k',0)}，D={kdj.get('d',0)}，J={kdj.get('j',0)}。\n")

    boll = technical.get('boll', {})
    detail_parts.append(f"**布林带**：上轨 {boll.get('upper','--')}，中轨 {boll.get('middle','--')}，下轨 {boll.get('lower','--')}。\n")

    vol = technical.get('volume', {})
    vol_ratio = vol.get('ratio', 1)
    if vol_ratio > 2:
        detail_parts.append(f"**成交量**：量比 {vol_ratio}，成交明显放大，资金交投活跃。\n")
    elif vol_ratio < 0.5:
        detail_parts.append(f"**成交量**：量比 {vol_ratio}，成交较为低迷。\n")

    # --- 基本面 ---
    detail_parts.append("\n### 📋 基本面分析\n")

    pe = fundamental.get('pe', 0)
    pb = fundamental.get('pb', 0)
    roe = fundamental.get('roe', 0)
    profit_growth = fundamental.get('profit_growth', 0)

    if 0 < pe < 15:
        score += 8
        detail_parts.append(f"- **估值**：PE={pe}，估值偏低，具有安全边际\n")
    elif pe > 80:
        score -= 8
        detail_parts.append(f"- **估值**：PE={pe}，估值偏高，需警惕泡沫风险\n")
    elif pe > 0:
        detail_parts.append(f"- **估值**：PE={pe}，PB={pb}，估值处于合理区间\n")

    if roe > 15:
        score += 5
        detail_parts.append(f"- **盈利能力**：ROE={roe}%，盈利能力优秀\n")
    elif roe > 0:
        detail_parts.append(f"- **盈利能力**：ROE={roe}%\n")

    if profit_growth > 20:
        score += 5
        detail_parts.append(f"- **成长性**：净利润增长 {profit_growth}%，业绩高增长\n")
    elif profit_growth < -20:
        score -= 5
        detail_parts.append(f"- **成长性**：净利润下滑 {abs(profit_growth)}%，业绩承压\n")
    elif profit_growth != 0:
        detail_parts.append(f"- **成长性**：净利润增长 {profit_growth}%\n")

    # 限制分数
    score = max(10, min(95, score))

    if score >= 80:
        signal = '强烈买入'
    elif score >= 65:
        signal = '买入'
    elif score >= 45:
        signal = '中性'
    elif score >= 30:
        signal = '卖出'
    else:
        signal = '强烈卖出'

    # --- 操作建议 ---
    detail_parts.append(f"\n### 🎯 操作建议\n")
    detail_parts.append(f"**综合评分：{score}/100 | 信号：{signal}**\n")

    if score >= 65:
        detail_parts.append(f"\n技术面和基本面综合偏多，可考虑适量布局。参考支撑位 {boll.get('lower', '--')}，压力位 {boll.get('upper', '--')}。建议分批买入，控制仓位。\n")
    elif score <= 35:
        detail_parts.append(f"\n技术面和基本面综合偏空，建议观望或减仓。下方支撑位 {boll.get('lower', '--')}，如跌破建议止损。\n")
    else:
        detail_parts.append(f"\n当前处于震荡区间，建议观望等待方向明确。布林中轨 {boll.get('middle', '--')} 附近可做短线参考。\n")

    detail_parts.append("\n---\n")
    detail_parts.append("*⚠️ 以上分析由规则引擎基于实时数据生成，仅供参考，不构成投资建议。投资有风险，入市需谨慎。*")

    return {
        'score': score,
        'signal': signal,
        'summary': signal,
        'points': [],
        'suggestion': '',
        'detail': '\n'.join(detail_parts),
        'ai_provider': '规则引擎',
    }
