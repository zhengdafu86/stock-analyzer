"""
技术指标计算模块
计算各种技术分析指标：MA, MACD, RSI, KDJ, BOLL, 量能等
"""
import pandas as pd
import numpy as np


def calculate_all_indicators(df: pd.DataFrame) -> dict:
    """计算所有技术指标"""
    if df.empty or len(df) < 20:
        return _empty_indicators()

    close = df['close'].astype(float).values if 'close' in df.columns else df['收盘'].astype(float).values
    high = df['high'].astype(float).values if 'high' in df.columns else df['最高'].astype(float).values
    low = df['low'].astype(float).values if 'low' in df.columns else df['最低'].astype(float).values
    volume = df['volume'].astype(float).values if 'volume' in df.columns else df['成交量'].astype(float).values

    result = {}
    result['ma'] = calculate_ma(close)
    result['macd'] = calculate_macd(close)
    result['rsi'] = calculate_rsi(close)
    result['kdj'] = calculate_kdj(high, low, close)
    result['boll'] = calculate_boll(close)
    result['volume'] = calculate_volume_analysis(volume)

    return result


def calculate_ma(close: np.ndarray) -> list:
    """计算均线系统"""
    periods = [5, 10, 20, 60]
    names = ['MA5', 'MA10', 'MA20', 'MA60']
    mas = []

    current_price = close[-1]

    for period, name in zip(periods, names):
        if len(close) >= period:
            ma_value = np.mean(close[-period:])
            signal = '多头' if current_price > ma_value else '空头'
            mas.append({
                'name': name,
                'value': round(float(ma_value), 2),
                'signal': signal
            })
        else:
            mas.append({
                'name': name,
                'value': 0,
                'signal': '数据不足'
            })

    return mas


def calculate_macd(close: np.ndarray, fast=12, slow=26, signal=9) -> dict:
    """计算 MACD 指标"""
    if len(close) < slow + signal:
        return {'dif': 0, 'dea': 0, 'histogram': 0, 'signal': '数据不足'}

    # 计算 EMA
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)

    # DIF = 快线EMA - 慢线EMA
    dif = ema_fast - ema_slow

    # DEA = DIF 的 EMA
    dea = _ema(dif, signal)

    # MACD 柱 = 2 * (DIF - DEA)
    histogram = 2 * (dif - dea)

    current_dif = float(dif[-1])
    current_dea = float(dea[-1])
    current_hist = float(histogram[-1])
    prev_hist = float(histogram[-2]) if len(histogram) > 1 else 0

    # 判断信号
    if current_dif > current_dea and dif[-2] <= dea[-2]:
        macd_signal = 'MACD 金叉，短期看多'
    elif current_dif < current_dea and dif[-2] >= dea[-2]:
        macd_signal = 'MACD 死叉，短期看空'
    elif current_hist > 0 and current_hist > prev_hist:
        macd_signal = '红柱放大，多头增强'
    elif current_hist > 0 and current_hist < prev_hist:
        macd_signal = '红柱缩短，多头减弱'
    elif current_hist < 0 and abs(current_hist) > abs(prev_hist):
        macd_signal = '绿柱放大，空头增强'
    elif current_hist < 0 and abs(current_hist) < abs(prev_hist):
        macd_signal = '绿柱缩短，空头减弱'
    else:
        macd_signal = '中性震荡'

    return {
        'dif': round(current_dif, 4),
        'dea': round(current_dea, 4),
        'histogram': round(current_hist, 4),
        'signal': macd_signal
    }


def calculate_rsi(close: np.ndarray, periods=(6, 12, 24)) -> dict:
    """计算 RSI 相对强弱指标"""
    result = {}

    for period in periods:
        if len(close) < period + 1:
            result[f'rsi{period}'] = 50
            continue

        deltas = np.diff(close[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains) if len(gains) > 0 else 0
        avg_loss = np.mean(losses) if len(losses) > 0 else 0

        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        result[f'rsi{period}'] = round(float(rsi), 2)

    # RSI 信号判断（基于 RSI6）
    rsi6 = result.get('rsi6', 50)
    if rsi6 >= 80:
        signal = '严重超买，注意回调风险'
    elif rsi6 >= 70:
        signal = '超买区间，谨慎追高'
    elif rsi6 <= 20:
        signal = '严重超卖，关注反弹机会'
    elif rsi6 <= 30:
        signal = '超卖区间，可关注买入机会'
    elif 40 <= rsi6 <= 60:
        signal = '中性区间，观望为主'
    else:
        signal = '正常区间'

    result['signal'] = signal
    result['value'] = rsi6  # 用于进度条显示

    return result


def calculate_kdj(high: np.ndarray, low: np.ndarray, close: np.ndarray, n=9) -> dict:
    """计算 KDJ 随机指标"""
    if len(close) < n:
        return {'k': 50, 'd': 50, 'j': 50, 'signal': '数据不足'}

    # 计算 RSV
    low_n = pd.Series(low).rolling(n).min().values
    high_n = pd.Series(high).rolling(n).max().values

    rsv = np.where(
        high_n - low_n > 0,
        (close - low_n) / (high_n - low_n) * 100,
        50
    )

    # 计算 K, D, J（平滑处理）
    k = np.zeros_like(rsv)
    d = np.zeros_like(rsv)
    k[0] = 50
    d[0] = 50

    for i in range(1, len(rsv)):
        if np.isnan(rsv[i]):
            k[i] = k[i - 1]
            d[i] = d[i - 1]
        else:
            k[i] = 2 / 3 * k[i - 1] + 1 / 3 * rsv[i]
            d[i] = 2 / 3 * d[i - 1] + 1 / 3 * k[i]

    j = 3 * k - 2 * d

    current_k = round(float(k[-1]), 2)
    current_d = round(float(d[-1]), 2)
    current_j = round(float(j[-1]), 2)

    # 信号判断
    if current_k > current_d and k[-2] <= d[-2]:
        signal = 'KDJ 金叉，买入信号'
    elif current_k < current_d and k[-2] >= d[-2]:
        signal = 'KDJ 死叉，卖出信号'
    elif current_j > 100:
        signal = 'J 值超买，注意风险'
    elif current_j < 0:
        signal = 'J 值超卖，关注机会'
    else:
        signal = '中性震荡'

    return {
        'k': current_k,
        'd': current_d,
        'j': current_j,
        'signal': signal
    }


def calculate_boll(close: np.ndarray, n=20, k=2) -> dict:
    """计算布林带指标"""
    if len(close) < n:
        return {'upper': 0, 'middle': 0, 'lower': 0, 'signal': '数据不足'}

    middle = np.mean(close[-n:])
    std = np.std(close[-n:])
    upper = middle + k * std
    lower = middle - k * std

    current_price = close[-1]

    # 信号判断
    bandwidth = (upper - lower) / middle * 100

    if current_price > upper:
        signal = '突破上轨，超强势但注意回调'
    elif current_price < lower:
        signal = '跌破下轨，超弱势但关注反弹'
    elif current_price > middle and (current_price - middle) / (upper - middle) > 0.8:
        signal = '接近上轨，短期压力较大'
    elif current_price < middle and (middle - current_price) / (middle - lower) > 0.8:
        signal = '接近下轨，短期支撑较强'
    elif bandwidth < 5:
        signal = '布林带收窄，即将选择方向'
    else:
        signal = '运行在布林通道中，趋势正常'

    return {
        'upper': round(float(upper), 2),
        'middle': round(float(middle), 2),
        'lower': round(float(lower), 2),
        'signal': signal
    }


def calculate_volume_analysis(volume: np.ndarray) -> dict:
    """量能分析"""
    if len(volume) < 5:
        return {'today': 0, 'avg5': 0, 'ratio': 1, 'signal': '数据不足'}

    today_vol = float(volume[-1])
    avg5_vol = float(np.mean(volume[-5:]))
    ratio = today_vol / avg5_vol if avg5_vol > 0 else 1

    if ratio > 3:
        signal = '巨量异动，密切关注'
    elif ratio > 2:
        signal = '显著放量，资金活跃'
    elif ratio > 1.5:
        signal = '温和放量，交投增加'
    elif ratio > 0.8:
        signal = '量能正常'
    elif ratio > 0.5:
        signal = '轻度缩量，观望情绪浓'
    else:
        signal = '严重缩量，交投清淡'

    return {
        'today': today_vol,
        'avg5': avg5_vol,
        'ratio': round(ratio, 2),
        'signal': signal
    }


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """计算指数移动平均"""
    alpha = 2 / (period + 1)
    ema = np.zeros_like(data, dtype=float)
    ema[0] = data[0]
    for i in range(1, len(data)):
        ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
    return ema


def _empty_indicators() -> dict:
    """返回空指标数据"""
    return {
        'ma': [],
        'macd': {'dif': 0, 'dea': 0, 'histogram': 0, 'signal': '数据不足'},
        'rsi': {'rsi6': 50, 'rsi12': 50, 'rsi24': 50, 'value': 50, 'signal': '数据不足'},
        'kdj': {'k': 50, 'd': 50, 'j': 50, 'signal': '数据不足'},
        'boll': {'upper': 0, 'middle': 0, 'lower': 0, 'signal': '数据不足'},
        'volume': {'today': 0, 'avg5': 0, 'ratio': 1, 'signal': '数据不足'}
    }
