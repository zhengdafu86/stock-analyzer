"""
股票数据获取模块
- 东方财富 HTTP API：实时行情、搜索、K线、大盘指数
- BaoStock：财务基本面数据（利润表、资产负债表、财务指标）
"""
import requests
import pandas as pd
import numpy as np
import traceback
import time
from datetime import datetime, timedelta

# ============ 东方财富 HTTP 通用 ============

_SESSION = requests.Session()
_SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://quote.eastmoney.com/',
})

# 全量行情缓存
_spot_cache = {'data': None, 'time': 0}
SPOT_CACHE_TTL = 15  # 秒


def _code_to_secid(code: str) -> str:
    """股票代码 → 东方财富 secid（1.XXXXXX 沪 / 0.XXXXXX 深）"""
    code = str(code).strip()
    if code.startswith(('6', '9', '11')):
        return f'1.{code}'
    else:
        return f'0.{code}'


def _safe_float(val, default=0):
    """安全转换为浮点数"""
    try:
        v = float(val)
        return v if not (pd.isna(v) or v == float('inf')) else default
    except:
        return default


def _get_spot_df() -> pd.DataFrame:
    """东方财富：获取 A 股全量实时行情（带缓存）"""
    now = time.time()
    if _spot_cache['data'] is not None and now - _spot_cache['time'] < SPOT_CACHE_TTL:
        return _spot_cache['data']

    url = 'https://82.push2.eastmoney.com/api/qt/clist/get'
    params = {
        'pn': 1, 'pz': 6000, 'po': 1,
        'np': 1, 'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
        'fltt': 2, 'invt': 2, 'fid': 'f3',
        'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048',
        'fields': 'f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f23',
    }
    try:
        resp = _SESSION.get(url, params=params, timeout=10)
        data = resp.json()
        items = data.get('data', {}).get('diff', [])
        if not items:
            return _spot_cache.get('data') or pd.DataFrame()

        rows = []
        for it in items:
            rows.append({
                '代码': str(it.get('f12', '')),
                '名称': str(it.get('f14', '')),
                '最新价': it.get('f2'),
                '涨跌幅': it.get('f3'),
                '涨跌额': it.get('f4'),
                '成交量': it.get('f5'),
                '成交额': it.get('f6'),
                '振幅': it.get('f7'),
                '换手率': it.get('f8'),
                '市盈率-动态': it.get('f9'),
                '市净率': it.get('f23'),
                '最高': it.get('f15'),
                '最低': it.get('f16'),
                '今开': it.get('f17'),
                '昨收': it.get('f18'),
                '总市值': it.get('f20'),
                '流通市值': it.get('f21'),
            })

        df = pd.DataFrame(rows)
        _spot_cache['data'] = df
        _spot_cache['time'] = now
        return df
    except Exception as e:
        print(f"获取全量行情失败: {e}")
        return _spot_cache.get('data') or pd.DataFrame()


# ============ 搜索 ============

def search_stocks(keyword: str) -> list:
    """搜索 A 股股票，支持代码和名称模糊匹配"""
    try:
        df = _get_spot_df()
        if df.empty:
            return []

        mask = (
            df['代码'].astype(str).str.contains(keyword, na=False)
            | df['名称'].astype(str).str.contains(keyword, na=False)
        )
        results = df[mask].head(20)

        stocks = []
        for _, row in results.iterrows():
            code = str(row['代码'])
            name = str(row['名称'])
            if code.startswith('3'):
                market = '创业板'
            elif code.startswith('68'):
                market = '科创板'
            elif code.startswith('6'):
                market = '上海'
            else:
                market = '深圳'
            stocks.append({'code': code, 'name': name, 'market': market})
        return stocks
    except Exception as e:
        print(f"搜索股票失败: {e}")
        traceback.print_exc()
        return []


# ============ 实时行情 ============

def get_stock_quote(code: str) -> dict:
    """获取单只股票实时行情"""
    try:
        df = _get_spot_df()
        if df.empty:
            return {}

        row = df[df['代码'] == code]
        if row.empty:
            return {}

        row = row.iloc[0]
        return {
            'code': code,
            'name': str(row.get('名称', '')),
            'price': _safe_float(row.get('最新价')),
            'change_percent': _safe_float(row.get('涨跌幅')),
            'change_amount': _safe_float(row.get('涨跌额')),
            'volume': _safe_float(row.get('成交量')),
            'amount': _safe_float(row.get('成交额')),
            'open': _safe_float(row.get('今开')),
            'high': _safe_float(row.get('最高')),
            'low': _safe_float(row.get('最低')),
            'prev_close': _safe_float(row.get('昨收')),
            'turnover_rate': _safe_float(row.get('换手率')),
            'pe': _safe_float(row.get('市盈率-动态')),
            'pb': _safe_float(row.get('市净率')),
            'market_cap': _safe_float(row.get('总市值')),
            'float_market_cap': _safe_float(row.get('流通市值')),
        }
    except Exception as e:
        print(f"获取行情失败 {code}: {e}")
        traceback.print_exc()
        return {}


def get_batch_quotes(codes: list) -> dict:
    """批量获取实时行情"""
    try:
        df = _get_spot_df()
        if df.empty:
            return {}

        result = {}
        for code in codes:
            row = df[df['代码'] == code]
            if not row.empty:
                row = row.iloc[0]
                result[code] = {
                    'name': str(row.get('名称', '')),
                    'price': _safe_float(row.get('最新价')),
                    'change_percent': _safe_float(row.get('涨跌幅')),
                    'volume': _safe_float(row.get('成交量')),
                    'turnover_rate': _safe_float(row.get('换手率')),
                    'has_report': True,
                }
        return result
    except Exception as e:
        print(f"批量获取行情失败: {e}")
        traceback.print_exc()
        return {}


# ============ K 线数据（东方财富） ============

def get_kline_data(code: str, period: str = 'daily', count: int = 120) -> pd.DataFrame:
    """东方财富：获取历史 K 线数据（前复权）"""
    try:
        secid = _code_to_secid(code)
        klt_map = {'daily': '101', 'weekly': '102', 'monthly': '103'}
        klt = klt_map.get(period, '101')

        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=count * 3)).strftime('%Y%m%d')

        url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
        params = {
            'secid': secid,
            'ut': 'fa5fd1943c7b386f172d6893dbbd4dc0',
            'fields1': 'f1,f2,f3,f4,f5,f6',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'klt': klt,
            'fqt': 1,  # 前复权
            'beg': start_date,
            'end': end_date,
            'lmt': count,
        }

        resp = _SESSION.get(url, params=params, timeout=10)
        data = resp.json()
        klines = data.get('data', {}).get('klines', [])
        if not klines:
            return pd.DataFrame()

        rows = []
        for line in klines:
            parts = line.split(',')
            if len(parts) >= 11:
                rows.append({
                    'date': parts[0],
                    'open': float(parts[1]),
                    'close': float(parts[2]),
                    'high': float(parts[3]),
                    'low': float(parts[4]),
                    'volume': float(parts[5]),
                    'amount': float(parts[6]),
                    'amplitude': float(parts[7]),
                    'change_pct': float(parts[8]),
                    'change_amt': float(parts[9]),
                    'turnover_rate': float(parts[10]),
                })

        df = pd.DataFrame(rows)
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
    """获取基本面数据：估值来自东方财富实时行情，财务指标来自 BaoStock"""
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

    # ---------- 3. 行业信息（东方财富个股详情） ----------
    try:
        secid = _code_to_secid(code)
        url = 'https://push2.eastmoney.com/api/qt/stock/get'
        params = {
            'secid': secid,
            'ut': 'fa5fd1943c7b386f172d6893dbbd4dc0',
            'fields': 'f57,f58,f127,f128,f129,f130,f131,f132,f133,f134,f135',
            'invt': 2,
        }
        resp = _SESSION.get(url, params=params, timeout=5)
        info = resp.json().get('data', {})
        if info:
            result['industry'] = info.get('f127', '--')
    except:
        pass

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


# ============ 大盘指数（东方财富） ============

def get_market_overview() -> dict:
    """获取大盘指数概览（上证/深证/创业板）"""
    try:
        url = 'https://push2.eastmoney.com/api/qt/ulist.np/get'
        params = {
            'fltt': 2,
            'fields': 'f2,f3,f4,f12,f14',
            'secids': '1.000001,0.399001,0.399006',
        }
        resp = _SESSION.get(url, params=params, timeout=5)
        data = resp.json()
        items = data.get('data', {}).get('diff', [])

        result = {}
        name_map = {
            '000001': ('sh_index', 'sh_change'),
            '399001': ('sz_index', 'sz_change'),
            '399006': ('cyb_index', 'cyb_change'),
        }
        for it in items:
            code = str(it.get('f12', ''))
            if code in name_map:
                idx_key, chg_key = name_map[code]
                result[idx_key] = _safe_float(it.get('f2'))
                result[chg_key] = _safe_float(it.get('f3'))

        return result
    except Exception as e:
        print(f"获取大盘数据失败: {e}")
        traceback.print_exc()
        return {}
