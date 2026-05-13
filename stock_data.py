"""
股票数据获取模块
- 腾讯财经 API (qt.gtimg.cn)：实时行情、搜索、K线、大盘指数
- BaoStock：财务基本面数据（利润表、资产负债表、财务指标）

腾讯行情数据格式 (v_shXXXXXX):
  0:未知 1:名称 2:代码 3:最新价 4:昨收 5:今开 6:成交量(手) 7:外盘 8:内盘
  9:买一价 10:买一量 11:买二价 ... 29:卖五量
  30:时间 31:涨跌额 32:涨跌幅% 33:最高 34:最低
  35:价格/成交量/成交额 36:成交量(手) 37:成交额(万)
  38:换手率 39:市盈率 41:最高 42:最低 43:振幅
  44:流通市值(亿) 45:总市值(亿) 46:市净率
"""
import requests
import pandas as pd
import numpy as np
import traceback
import re
import time
from datetime import datetime, timedelta

# ============ 腾讯财经 HTTP 通用 ============

_SESSION = requests.Session()
_SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://stockapp.finance.qq.com/',
})

# 全量行情缓存
_spot_cache = {'data': None, 'time': 0}
SPOT_CACHE_TTL = 15  # 秒


def _safe_float(val, default=0):
    """安全转换为浮点数"""
    try:
        v = float(val)
        return v if not (pd.isna(v) or v == float('inf')) else default
    except:
        return default


def _code_to_tencent(code: str) -> str:
    """股票代码 → 腾讯格式（sh600519 / sz000858）"""
    code = str(code).strip()
    if code.startswith(('6', '9', '11')):
        return f'sh{code}'
    else:
        return f'sz{code}'


def _parse_tencent_quote(text: str) -> list:
    """解析腾讯行情返回数据，返回列表 [{...}, ...]"""
    results = []
    # 匹配 v_shXXXXXX="..." 或 v_szXXXXXX="..."
    pattern = r'v_(\w+)="([^"]*)"'
    for match in re.finditer(pattern, text):
        symbol = match.group(1)
        data = match.group(2)
        if not data or data.count('~') < 30:
            continue

        parts = data.split('~')
        code = parts[2] if len(parts) > 2 else symbol[2:]
        name = parts[1] if len(parts) > 1 else ''

        results.append({
            'code': code,
            'name': name,
            'price': _safe_float(parts[3]) if len(parts) > 3 else 0,
            'prev_close': _safe_float(parts[4]) if len(parts) > 4 else 0,
            'open': _safe_float(parts[5]) if len(parts) > 5 else 0,
            'volume': _safe_float(parts[6]) if len(parts) > 6 else 0,  # 手
            'change_amount': _safe_float(parts[31]) if len(parts) > 31 else 0,
            'change_percent': _safe_float(parts[32]) if len(parts) > 32 else 0,
            'high': _safe_float(parts[33]) if len(parts) > 33 else 0,
            'low': _safe_float(parts[34]) if len(parts) > 34 else 0,
            'amount': _safe_float(parts[37]) * 10000 if len(parts) > 37 else 0,  # 万→元
            'turnover_rate': _safe_float(parts[38]) if len(parts) > 38 else 0,
            'pe': _safe_float(parts[39]) if len(parts) > 39 else 0,
            'pb': _safe_float(parts[46]) if len(parts) > 46 else 0,
            'float_market_cap': _safe_float(parts[44]) * 1e8 if len(parts) > 44 else 0,  # 亿→元
            'market_cap': _safe_float(parts[45]) * 1e8 if len(parts) > 45 else 0,  # 亿→元
        })

    return results


# A 股代码列表（用于搜索和批量获取）
_all_codes_cache = {'data': None, 'time': 0}
ALL_CODES_CACHE_TTL = 3600  # 1 小时


def _get_all_stock_codes() -> list:
    """获取 A 股全部股票代码列表（用于搜索）"""
    now = time.time()
    if _all_codes_cache['data'] is not None and now - _all_codes_cache['time'] < ALL_CODES_CACHE_TTL:
        return _all_codes_cache['data']

    codes = []
    # 沪市主板 600000-605999, 科创板 688000-689999
    # 深市主板 000001-003999, 中小板 002001-004999, 创业板 300001-301999
    ranges = [
        ('sh', 600000, 606000),
        ('sh', 688000, 690000),
        ('sz', 0, 5000),
        ('sz', 300000, 302000),
    ]

    # 分批请求，每批 50 个
    batch_size = 80
    for prefix, start, end in ranges:
        # 生成所有候选代码
        candidates = [f'{prefix}{str(i).zfill(6)}' for i in range(start, end)]
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i + batch_size]
            query = ','.join(batch)
            try:
                resp = _SESSION.get(f'http://qt.gtimg.cn/q={query}', timeout=10)
                text = resp.text
                for match in re.finditer(r'v_(\w+)="([^"]*)"', text):
                    data = match.group(2)
                    parts = data.split('~')
                    if len(parts) > 3 and parts[1] and _safe_float(parts[3]) > 0:
                        codes.append({
                            'symbol': match.group(1),
                            'code': parts[2],
                            'name': parts[1],
                        })
            except:
                continue

    if codes:
        _all_codes_cache['data'] = codes
        _all_codes_cache['time'] = now

    return codes


def _get_spot_data(tencent_codes: list) -> list:
    """腾讯：批量获取实时行情"""
    if not tencent_codes:
        return []

    all_results = []
    batch_size = 50
    for i in range(0, len(tencent_codes), batch_size):
        batch = tencent_codes[i:i + batch_size]
        query = ','.join(batch)
        try:
            resp = _SESSION.get(f'http://qt.gtimg.cn/q={query}', timeout=10)
            results = _parse_tencent_quote(resp.text)
            all_results.extend(results)
        except Exception as e:
            print(f"获取行情失败: {e}")

    return all_results


# ============ 搜索（轻量方案：用腾讯 suggest 接口）============

def search_stocks(keyword: str) -> list:
    """搜索 A 股股票，支持代码和名称模糊匹配"""
    try:
        # 腾讯智能联想搜索接口
        url = 'https://smartbox.gtimg.cn/s3/'
        params = {'v': 2, 'q': keyword, 't': 'gp'}
        resp = _SESSION.get(url, params=params, timeout=5)
        text = resp.text

        # 格式: v_hint="gp~code~name~... \n gp~code~name~..."
        stocks = []
        # 提取引号内内容
        match = re.search(r'"([^"]*)"', text)
        if not match:
            return []

        content = match.group(1)
        for line in content.split('^'):
            parts = line.split('~')
            if len(parts) >= 3 and parts[0] == 'gp':
                code = parts[1]
                name = parts[2]
                # 只要 A 股（6/0/3 开头）
                if code and code[0] in ('6', '0', '3'):
                    if code.startswith('3'):
                        market = '创业板'
                    elif code.startswith('68'):
                        market = '科创板'
                    elif code.startswith('6'):
                        market = '上海'
                    else:
                        market = '深圳'
                    stocks.append({'code': code, 'name': name, 'market': market})

        return stocks[:20]
    except Exception as e:
        print(f"搜索股票失败: {e}")
        traceback.print_exc()
        return []


# ============ 实时行情 ============

def get_stock_quote(code: str) -> dict:
    """获取单只股票实时行情"""
    try:
        tc = _code_to_tencent(code)
        resp = _SESSION.get(f'http://qt.gtimg.cn/q={tc}', timeout=10)
        results = _parse_tencent_quote(resp.text)
        if results:
            return results[0]
        return {}
    except Exception as e:
        print(f"获取行情失败 {code}: {e}")
        traceback.print_exc()
        return {}


def get_batch_quotes(codes: list) -> dict:
    """批量获取实时行情"""
    try:
        tc_codes = [_code_to_tencent(c) for c in codes]
        results = _get_spot_data(tc_codes)

        output = {}
        for r in results:
            output[r['code']] = {
                'name': r['name'],
                'price': r['price'],
                'change_percent': r['change_percent'],
                'volume': r['volume'],
                'turnover_rate': r['turnover_rate'],
                'has_report': True,
            }
        return output
    except Exception as e:
        print(f"批量获取行情失败: {e}")
        traceback.print_exc()
        return {}


# ============ K 线数据（腾讯日K） ============

def get_kline_data(code: str, period: str = 'daily', count: int = 120) -> pd.DataFrame:
    """腾讯财经：获取历史 K 线数据（前复权）"""
    try:
        tc = _code_to_tencent(code)
        period_map = {'daily': 'day', 'weekly': 'week', 'monthly': 'month'}
        klt = period_map.get(period, 'day')

        end_date = datetime.now().strftime('%Y-%m-%d')
        start_year = datetime.now().year - 1
        start_date = f'{start_year}-01-01'

        # 腾讯 K 线接口
        url = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
        params = {
            'param': f'{tc},{klt},{start_date},{end_date},{count},qfq',
        }

        resp = _SESSION.get(url, params=params, timeout=10)
        data = resp.json()

        # 提取 K 线数据
        stock_data = data.get('data', {}).get(tc, {})
        klines = stock_data.get(f'qfq{klt}', stock_data.get(klt, []))

        if not klines:
            return pd.DataFrame()

        rows = []
        for k in klines:
            if len(k) >= 6:
                rows.append({
                    'date': k[0],
                    'open': float(k[1]),
                    'close': float(k[2]),
                    'high': float(k[3]),
                    'low': float(k[4]),
                    'volume': float(k[5]),
                    'amount': 0,
                    'amplitude': 0,
                    'change_pct': 0,
                    'change_amt': 0,
                    'turnover_rate': 0,
                })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # 计算涨跌幅和振幅
        if len(df) > 1:
            df['change_pct'] = df['close'].pct_change() * 100
            df['change_amt'] = df['close'].diff()
            df['amplitude'] = (df['high'] - df['low']) / df['close'].shift(1) * 100
            df = df.fillna(0)

        return df.tail(count)
    except Exception as e:
        print(f"获取K线数据失败 {code}: {e}")
        traceback.print_exc()
        return pd.DataFrame()


# ============ 基本面数据（BaoStock 财务指标） ============

def _code_to_baostock(code: str) -> str:
    """股票代码 → BaoStock 格式（sh.600519 / sz.000858）"""
    code = str(code).strip()
    if code.startswith(('6', '9', '11')):
        return f'sh.{code}'
    else:
        return f'sz.{code}'


def _date_to_quarter(date_str: str) -> int:
    """报告日期 → 季度（1-4）"""
    month = int(date_str.split('-')[1])
    if month <= 3:
        return 1
    elif month <= 6:
        return 2
    elif month <= 9:
        return 3
    else:
        return 4


def _baostock_query(query_func, **kwargs) -> pd.DataFrame:
    """BaoStock 查询包装器：自动登录/登出"""
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != '0':
            print(f"BaoStock 登录失败: {lg.error_msg}")
            return pd.DataFrame()

        rs = query_func(**kwargs)
        rows = []
        while rs.error_code == '0' and rs.next():
            rows.append(rs.get_row_data())

        bs.logout()

        if rows:
            return pd.DataFrame(rows, columns=rs.fields)
        return pd.DataFrame()
    except ImportError:
        print("BaoStock 未安装，财务数据不可用")
        return pd.DataFrame()
    except Exception as e:
        print(f"BaoStock 查询失败: {e}")
        try:
            import baostock as bs
            bs.logout()
        except:
            pass
        return pd.DataFrame()


def _get_recent_report_dates():
    """返回最近几个可能的财报日期列表"""
    now = datetime.now()
    year = now.year
    month = now.month
    if month >= 10:
        return [f'{year}-09-30', f'{year}-06-30', f'{year}-03-31', f'{year-1}-12-31']
    elif month >= 7:
        return [f'{year}-06-30', f'{year}-03-31', f'{year-1}-12-31', f'{year-1}-09-30']
    elif month >= 4:
        return [f'{year}-03-31', f'{year-1}-12-31', f'{year-1}-09-30', f'{year-1}-06-30']
    else:
        return [f'{year-1}-12-31', f'{year-1}-09-30', f'{year-1}-06-30', f'{year-1}-03-31']


def get_fundamentals(code: str) -> dict:
    """获取基本面数据：估值来自腾讯实时行情，财务指标来自 BaoStock"""
    result = {}

    # ---------- 1. 从实时行情获取估值 ----------
    try:
        quote = get_stock_quote(code)
        result['pe'] = quote.get('pe', 0)
        result['pb'] = quote.get('pb', 0)
        result['market_cap'] = quote.get('market_cap', 0)
    except:
        quote = {}

    # ---------- 2. BaoStock 财务指标 ----------
    bs_code = _code_to_baostock(code)
    report_dates = _get_recent_report_dates()

    try:
        import baostock as bs

        # ---- 盈利能力 ----
        for rdate in report_dates:
            yr, qtr = int(rdate[:4]), _date_to_quarter(rdate)
            df_profit = _baostock_query(
                bs.query_profit_data, code=bs_code, year=yr, quarter=qtr
            )
            if not df_profit.empty:
                latest = df_profit.iloc[-1]
                result['roe'] = _safe_float(latest.get('roeAvg', 0)) * 100
                result['net_margin'] = _safe_float(latest.get('netProfit', 0)) * 100
                result['gross_margin'] = _safe_float(latest.get('gpMargin', 0)) * 100
                result['eps'] = _safe_float(latest.get('epsTTM', 0))
                result['net_profit'] = _safe_float(latest.get('netProfit', 0))
                break

        # ---- 成长能力 ----
        for rdate in report_dates:
            yr, qtr = int(rdate[:4]), _date_to_quarter(rdate)
            df_growth = _baostock_query(
                bs.query_growth_data, code=bs_code, year=yr, quarter=qtr
            )
            if not df_growth.empty:
                latest = df_growth.iloc[-1]
                result['revenue_growth'] = _safe_float(latest.get('YOYEquity', 0)) * 100
                result['profit_growth'] = _safe_float(latest.get('YOYNI', 0)) * 100
                break

        # ---- 偿债能力 ----
        for rdate in report_dates:
            yr, qtr = int(rdate[:4]), _date_to_quarter(rdate)
            df_balance = _baostock_query(
                bs.query_balance_data, code=bs_code, year=yr, quarter=qtr
            )
            if not df_balance.empty:
                latest = df_balance.iloc[-1]
                result['debt_ratio'] = _safe_float(latest.get('liabilityToAsset', 0)) * 100
                result['current_ratio'] = _safe_float(latest.get('currentRatio', 0))
                break

        # 每股净资产（通过 PB 反算）
        price = quote.get('price', 0) if quote else 0
        pb = result.get('pb', 0)
        if pb > 0 and price > 0:
            result['bvps'] = round(price / pb, 2)

    except ImportError:
        print("BaoStock 未安装，跳过财务指标获取")
    except Exception as e:
        print(f"获取财务指标失败 {code}: {e}")
        traceback.print_exc()

    # ---------- 默认值填充 ----------
    defaults = {
        'pe': 0, 'pb': 0, 'ps': 0, 'market_cap': 0,
        'industry': '--', 'eps': 0, 'bvps': 0, 'roe': 0,
        'gross_margin': 0, 'net_margin': 0, 'debt_ratio': 0,
        'revenue': 0, 'net_profit': 0,
        'revenue_growth': 0, 'profit_growth': 0,
        'industry_pe': 0, 'industry_pb': 0, 'dividend_yield': 0,
        'current_ratio': 0,
    }
    for k, v in defaults.items():
        result.setdefault(k, v)

    return result


# ============ 大盘指数（腾讯） ============

def get_market_overview() -> dict:
    """获取大盘指数概览（上证/深证/创业板）"""
    try:
        resp = _SESSION.get('http://qt.gtimg.cn/q=sh000001,sz399001,sz399006', timeout=10)
        text = resp.text

        result = {}
        name_map = {
            '000001': ('sh_index', 'sh_change'),
            '399001': ('sz_index', 'sz_change'),
            '399006': ('cyb_index', 'cyb_change'),
        }

        for match in re.finditer(r'v_(\w+)="([^"]*)"', text):
            data = match.group(2)
            parts = data.split('~')
            if len(parts) > 32:
                code = parts[2]
                if code in name_map:
                    idx_key, chg_key = name_map[code]
                    result[idx_key] = _safe_float(parts[3])
                    result[chg_key] = _safe_float(parts[32])

        return result
    except Exception as e:
        print(f"获取大盘数据失败: {e}")
        traceback.print_exc()
        return {}
