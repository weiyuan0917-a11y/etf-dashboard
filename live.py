# -*- coding: utf-8 -*-
"""实时行情：新浪 hq.sinajs.cn（轻量、零门槛、本机当前可用）

历史：
- v1 走东方财富 ``push2.eastmoney.com/api/qt/ulist.np/get``，本机 IP 已被东财封禁
  （``RemoteDisconnected`` 整批返空），改用新浪。
- 新浪格式见 https://hq.sinajs.cn/list=sh513310,sz159915,...
  Referer 必须为 https://finance.sina.com.cn/ ，否则拿不到数据。

为什么不用 akshare 的全市场快照：
    ``ak.fund_etf_spot_em()`` 内部翻 16 页拉全市场 1600+ 只，实测 **18~20 秒**，
    做自动刷新时几乎持续占满网络，体验很差。
本模块只请求「当前需要的那几只」（持仓 + 网格 + 选中标的），
一次请求 **<1 秒**，50 只以内可合并成单个请求。
"""
from __future__ import annotations

import re
from datetime import datetime, time as dtime

import pandas as pd

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

_URL = "https://hq.sinajs.cn/list={symbols}"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn/",
}

CHUNK = 50          # 单请求最大只数（新浪单次 URL 长度安全阈值）
TIMEOUT = 5         # 单请求超时（秒）

RESULT_COLUMNS = ["code", "name", "price", "chg_pct", "chg", "prev_close", "quote_at"]

_SESSION: requests.Session | None = None


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update(_HEADERS)
    return _SESSION


def _to_sina_symbol(code: str) -> str:
    """6 位代码 → 新浪符号。5/6/9 开头 = 沪(sh)，1 开头 = 深(sz)。"""
    c = str(code).strip()
    if not c:
        raise ValueError("empty code")
    return ("sh" if c[0] in "569" else "sz") + c


def market_phase(dt: datetime | None = None) -> tuple[str, bool]:
    """判断当前交易阶段，返回 (文案, 是否连续竞价)。

    只按「星期 + 时间」判断，**不含节假日日历**。遇到法定节假日会误判为"交易中"，
    因此调用方应结合行情时间戳的新鲜度一起判断（见 ``is_quote_fresh``）。
    """
    dt = dt or datetime.now()
    if dt.weekday() >= 5:
        return "周末休市", False
    t = dt.time()
    if t < dtime(9, 15):
        return "盘前", False
    if t < dtime(9, 30):
        return "集合竞价", False
    if t <= dtime(11, 30):
        return "交易中", True
    if t < dtime(13, 0):
        return "午间休市", False
    if t <= dtime(15, 0):
        return "交易中", True
    return "已收盘", False


def is_quote_fresh(quote_at: pd.Timestamp | datetime | None, max_age_sec: int = 300) -> bool:
    """行情时间戳是否够新（用于识别节假日等"时间上是交易日、实际没行情"的情况）。"""
    if quote_at is None or (isinstance(quote_at, float) and pd.isna(quote_at)):
        return False
    try:
        ts = pd.Timestamp(quote_at)
    except Exception:  # noqa: BLE001
        return False
    if pd.isna(ts):
        return False
    age = (pd.Timestamp.now() - ts).total_seconds()
    return 0 <= age <= max_age_sec


def _parse_line(line: str) -> tuple[str | None, dict | None]:
    """解析一行 var hq_str_sh513310="...,...,...,"; 返回 (code, row)。"""
    m_sym = re.search(r"hq_str_(\w+?)=\"", line)
    m_val = re.search(r'hq_str_\w+="(.*?)";', line)
    if not m_sym or not m_val:
        return None, None
    symbol = m_sym.group(1)               # sh513310
    raw = m_val.group(1)
    if not raw:
        return None, None
    parts = raw.split(",")
    if len(parts) < 32:
        return None, None
    try:
        code = symbol[2:]                 # 去掉 sh/sz 前缀
        prev_close = float(parts[2])
        price = float(parts[3])
        quote_at = pd.to_datetime(f"{parts[30]} {parts[31]}", errors="coerce")
        return code, {
            "code": code,
            "name": parts[0],
            "price": price,
            "prev_close": prev_close,
            "chg": price - prev_close,
            "chg_pct": (price - prev_close) / prev_close * 100 if prev_close else 0.0,
            "quote_at": quote_at,
        }
    except (ValueError, IndexError):
        return None, None


def _fetch_chunk(codes: list[str]) -> list[dict]:
    """请求一批，返回原始 dict 列表。失败返回空列表（由调用方回退）。"""
    if requests is None or not codes:
        return []
    symbols = ",".join(_to_sina_symbol(c) for c in codes)
    url = _URL.format(symbols=symbols)
    sess = _session()
    try:
        resp = sess.get(url, timeout=TIMEOUT)
        if resp.status_code != 200 or "hq_str_" not in resp.text:
            return []
    except Exception:  # noqa: BLE001
        return []
    rows: list[dict] = []
    for line in resp.text.strip().splitlines():
        _, d = _parse_line(line)
        if d is not None:
            rows.append(d)
    return rows


def fetch_quotes(codes, chunk: int = CHUNK) -> pd.DataFrame:
    """批量取实时报价。

    返回 DataFrame（列见 RESULT_COLUMNS），拿不到的代码会被**丢弃**而不是报错，
    调用方应自行回退到库内收盘价。
    """
    uniq = [str(c).strip() for c in dict.fromkeys(codes) if str(c).strip()]
    if not uniq:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    rows: list[dict] = []
    for i in range(0, len(uniq), chunk):
        batch = uniq[i: i + chunk]
        diff = _fetch_chunk(batch)
        if not diff:
            # 整批失败 → 逐只回退，找出哪些代码被新浪拒绝
            for c in batch:
                rows.extend(_fetch_chunk([c]))
        else:
            rows.extend(diff)

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    df = pd.DataFrame(rows)
    return df.reset_index(drop=True)[RESULT_COLUMNS]


def fetch_price_map(codes) -> dict:
    """返回 {code: 最新价}，仅含有报价的代码。"""
    df = fetch_quotes(codes)
    if df.empty:
        return {}
    return dict(zip(df["code"], df["price"].astype(float)))


def latest_quote_time(df: pd.DataFrame) -> pd.Timestamp | None:
    """取这批报价里最新的行情时间。"""
    if df is None or df.empty or "quote_at" not in df.columns:
        return None
    ts = df["quote_at"].dropna()
    return ts.max() if len(ts) else None
