"""
AI 智能分析模块
调用大语言模型，基于技术面和基本面数据生成自然语言分析报告
"""
import json
import config

# 仅在需要 AI API 时导入 openai
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def generate_ai_analysis(stock_info: dict, technical: dict, fundamental: dict) -> dict:
    """
    使用 AI 生成综合分析报告
    返回: { score, signal, summary, points, suggestion }
    """
    provider = config.AI_PROVIDER

    if provider == 'none':
        return _rule_based_analysis(stock_info, technical, fundamental)

    # 构建分析提示词
    prompt = _build_analysis_prompt(stock_info, technical, fundamental)

    try:
        if provider == 'deepseek':
            return _call_deepseek(prompt)
        elif provider == 'openai':
            return _call_openai(prompt)
        elif provider == 'zhipu':
            return _call_zhipu(prompt)
        else:
            return _rule_based_analysis(stock_info, technical, fundamental)
    except Exception as e:
        print(f"AI 分析失败，回退到规则引擎: {e}")
        return _rule_based_analysis(stock_info, technical, fundamental)


def _build_analysis_prompt(stock_info: dict, technical: dict, fundamental: dict) -> str:
    """构建 AI 分析提示词"""
    return f"""你是一位专业的 A 股股票分析师。请基于以下数据对该股票进行综合分析。

## 股票基本信息
- 名称: {stock_info.get('name', '未知')}
- 代码: {stock_info.get('code', '未知')}
- 当前价格: {stock_info.get('price', 0)}
- 今日涨跌幅: {stock_info.get('change_percent', 0)}%

## 技术指标数据
- 均线: {json.dumps(technical.get('ma', []), ensure_ascii=False)}
- MACD: DIF={technical.get('macd', {}).get('dif', 0)}, DEA={technical.get('macd', {}).get('dea', 0)}, 信号={technical.get('macd', {}).get('signal', '')}
- RSI(6): {technical.get('rsi', {}).get('rsi6', 50)}, RSI(12): {technical.get('rsi', {}).get('rsi12', 50)}
- KDJ: K={technical.get('kdj', {}).get('k', 50)}, D={technical.get('kdj', {}).get('d', 50)}, J={technical.get('kdj', {}).get('j', 50)}
- 布林带: 上轨={technical.get('boll', {}).get('upper', 0)}, 中轨={technical.get('boll', {}).get('middle', 0)}, 下轨={technical.get('boll', {}).get('lower', 0)}
- 量比: {technical.get('volume', {}).get('ratio', 1)}

## 基本面数据
- 市盈率(PE): {fundamental.get('pe', 0)}
- 市净率(PB): {fundamental.get('pb', 0)}
- ROE: {fundamental.get('roe', 0)}%
- 营收增长: {fundamental.get('revenue_growth', 0)}%
- 净利润增长: {fundamental.get('profit_growth', 0)}%
- 毛利率: {fundamental.get('gross_margin', 0)}%
- 资产负债率: {fundamental.get('debt_ratio', 0)}%

请以 JSON 格式输出分析结果，包含以下字段:
{{
  "score": 0-100 的综合评分,
  "signal": "强烈买入" | "买入" | "中性" | "卖出" | "强烈卖出",
  "summary": "一句话总结当前状态（30字以内）",
  "points": [
    {{"type": "positive|negative|neutral", "text": "分析要点"}},
    // 3-5 个要点
  ],
  "suggestion": "具体操作建议（50-100字）"
}}

注意：
1. 必须返回纯 JSON，不要有其他内容
2. 分析要客观专业，不要过度乐观或悲观
3. 操作建议要具体可执行，包含关键价位参考
4. 明确标注风险提示"""


def _call_deepseek(prompt: str) -> dict:
    """调用 DeepSeek API"""
    client = OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL
    )
    response = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": "你是专业的股票分析师，只输出 JSON 格式的分析结果。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=1000,
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


def _call_openai(prompt: str) -> dict:
    """调用 OpenAI API"""
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "你是专业的股票分析师，只输出 JSON 格式的分析结果。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=1000,
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


def _call_zhipu(prompt: str) -> dict:
    """调用智谱 AI API"""
    client = OpenAI(
        api_key=config.ZHIPU_API_KEY,
        base_url="https://open.bigmodel.cn/api/paas/v4/"
    )
    response = client.chat.completions.create(
        model=config.ZHIPU_MODEL,
        messages=[
            {"role": "system", "content": "你是专业的股票分析师，只输出 JSON 格式的分析结果。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=1000
    )
    content = response.choices[0].message.content
    # 智谱可能返回 markdown 代码块
    if '```json' in content:
        content = content.split('```json')[1].split('```')[0]
    return json.loads(content)


def _rule_based_analysis(stock_info: dict, technical: dict, fundamental: dict) -> dict:
    """
    规则引擎分析（不依赖 AI API 的备用方案）
    基于技术指标和基本面数据，用规则打分
    """
    score = 50  # 基准分
    points = []

    # --- 技术面打分 ---

    # 均线分析
    ma_list = technical.get('ma', [])
    bullish_ma = sum(1 for m in ma_list if m.get('signal') == '多头')
    if bullish_ma >= 3:
        score += 10
        points.append({'type': 'positive', 'text': f'多头排列，{bullish_ma}条均线支撑'})
    elif bullish_ma <= 1:
        score -= 10
        points.append({'type': 'negative', 'text': f'空头排列，均线压制明显'})

    # MACD 分析
    macd = technical.get('macd', {})
    macd_signal = macd.get('signal', '')
    if '金叉' in macd_signal:
        score += 8
        points.append({'type': 'positive', 'text': f'MACD金叉，短期动能转强'})
    elif '死叉' in macd_signal:
        score -= 8
        points.append({'type': 'negative', 'text': f'MACD死叉，短期动能减弱'})
    elif '红柱放大' in macd_signal:
        score += 5
    elif '绿柱放大' in macd_signal:
        score -= 5

    # RSI 分析
    rsi = technical.get('rsi', {})
    rsi6 = rsi.get('rsi6', 50)
    if rsi6 >= 80:
        score -= 10
        points.append({'type': 'negative', 'text': f'RSI={rsi6}，严重超买，短期回调风险大'})
    elif rsi6 >= 70:
        score -= 5
    elif rsi6 <= 20:
        score += 10
        points.append({'type': 'positive', 'text': f'RSI={rsi6}，严重超卖，存在反弹机会'})
    elif rsi6 <= 30:
        score += 5

    # KDJ 分析
    kdj = technical.get('kdj', {})
    kdj_signal = kdj.get('signal', '')
    if '金叉' in kdj_signal:
        score += 5
    elif '死叉' in kdj_signal:
        score -= 5

    # 量能分析
    vol = technical.get('volume', {})
    vol_ratio = vol.get('ratio', 1)
    if vol_ratio > 2:
        points.append({'type': 'neutral', 'text': f'量比{vol_ratio}，资金交投活跃'})

    # --- 基本面打分 ---
    pe = fundamental.get('pe', 0)
    if 0 < pe < 15:
        score += 8
        points.append({'type': 'positive', 'text': f'PE={pe}，估值偏低，具有安全边际'})
    elif pe > 80:
        score -= 8
        points.append({'type': 'negative', 'text': f'PE={pe}，估值偏高，注意泡沫风险'})

    roe = fundamental.get('roe', 0)
    if roe > 15:
        score += 5
        points.append({'type': 'positive', 'text': f'ROE={roe}%，盈利能力优秀'})

    profit_growth = fundamental.get('profit_growth', 0)
    if profit_growth > 20:
        score += 5
        points.append({'type': 'positive', 'text': f'净利润增长{profit_growth}%，业绩高增长'})
    elif profit_growth < -20:
        score -= 5
        points.append({'type': 'negative', 'text': f'净利润下滑{profit_growth}%，业绩承压'})

    # 限制分数范围
    score = max(10, min(95, score))

    # 确定信号
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

    # 确保至少有 3 个要点
    if len(points) < 3:
        points.append({'type': 'neutral', 'text': f'当前涨跌幅 {stock_info.get("change_percent", 0)}%'})

    # 生成建议
    change = stock_info.get('change_percent', 0)
    price = stock_info.get('price', 0)
    boll = technical.get('boll', {})

    if score >= 65:
        suggestion = f'技术面和基本面综合偏多，可考虑适量布局。参考支撑位 {boll.get("lower", "--")}，压力位 {boll.get("upper", "--")}。建议分批买入，控制仓位。'
    elif score <= 35:
        suggestion = f'技术面和基本面综合偏空，建议观望或减仓。下方支撑位 {boll.get("lower", "--")}，如跌破需止损。'
    else:
        suggestion = f'当前处于震荡区间，建议观望等待方向明确。布林中轨 {boll.get("middle", "--")} 附近可做短线参考。'

    summary_map = {
        '强烈买入': '多重指标共振看多，机会突出',
        '买入': '技术面偏多，基本面配合',
        '中性': '多空分歧，等待方向确认',
        '卖出': '技术面走弱，注意风险',
        '强烈卖出': '多重指标共振看空，建议回避'
    }

    return {
        'score': score,
        'signal': signal,
        'summary': summary_map.get(signal, '综合分析中'),
        'points': points[:5],
        'suggestion': suggestion
    }
