# -*- coding: utf-8 -*-
"""指标计算：涨跌幅、动量、均线距离、日均成交额。基于库内日频行情（不复权，新浪源）。"""
import numpy as np
import pandas as pd

import config
import storage


def _pct(df: pd.DataFrame, n: int) -> float:
    """近 n 个交易日涨跌幅 %；数据不足返回 NaN"""
    if len(df) < n + 1:
        return np.nan
    return (df["close"].iloc[-1] / df["close"].iloc[-n - 1] - 1) * 100


def _ytd(df: pd.DataFrame) -> float:
    year = df["trade_date"].iloc[-1][:4]
    base = df[df["trade_date"].str.startswith(year)]
    if base.empty:
        return np.nan
    prev_year = df[df["trade_date"] < base["trade_date"].iloc[0]]
    if prev_year.empty:
        return np.nan
    return (df["close"].iloc[-1] / prev_year["close"].iloc[-1] - 1) * 100


def compute_metrics(code: str, df: pd.DataFrame) -> dict:
    """单只 ETF 的指标字典"""
    close = df["close"]
    out = {
        "code": code,
        "close": float(close.iloc[-1]) if len(close) else np.nan,
        "chg_1w": _pct(df, 5),
        "chg_1m": _pct(df, 20),
        "chg_3m": _pct(df, 60),
        "ytd": _ytd(df),
        "avg_amount_20d": float(df["amount"].tail(20).mean()) if len(df) else np.nan,
        "days": len(df),
    }
    for w in config.MA_WINDOWS:
        out[f"ma{w}"] = float(close.tail(w).mean()) if len(close) >= w else np.nan
        if len(close) >= w and out["ma" + str(w)] == out["ma" + str(w)]:
            out[f"above_ma{w}"] = (out["close"] > out[f"ma{w}"])
        else:
            out[f"above_ma{w}"] = None
    return out


def build_metrics_table() -> pd.DataFrame:
    """对库内所有有行情的 ETF 计算指标，合并清单信息"""
    codes = sorted(storage.quoted_codes())
    rows = []
    for code in codes:
        q = storage.load_quotes(code)
        if q is None or q.empty:
            continue
        rows.append(compute_metrics(code, q))
    if not rows:
        return pd.DataFrame()
    m = pd.DataFrame(rows)
    lst = storage.load_etf_list()
    m = m.merge(lst, on="code", how="left", suffixes=("", "_snap"))
    return m


if __name__ == "__main__":
    storage.init_db()
    t = build_metrics_table()
    print(t.head(10).to_string())
