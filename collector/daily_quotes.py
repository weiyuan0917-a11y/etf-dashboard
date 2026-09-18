# -*- coding: utf-8 -*-
"""单只 ETF 日频行情采集。
主源：新浪（稳定，不复权口径）；备源：东方财富（前复权，本环境偶发拒连）。
"""
import time
from typing import Optional

import akshare as ak
import pandas as pd

import config
import storage

from .etf_list import time_sleep


def _sina_symbol(code: str) -> str:
    """5 开头为沪市 ETF，1 开头为深市 ETF"""
    return ("sh" if code.startswith("5") else "sz") + code


def _fetch_sina(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    raw = ak.fund_etf_hist_sina(symbol=_sina_symbol(code))
    if raw is None or raw.empty:
        return None
    df = raw.rename(columns={"date": "trade_date"})
    df = df[[c for c in ["trade_date", "open", "high", "low", "close", "volume", "amount"] if c in df.columns]].copy()
    df["trade_date"] = df["trade_date"].astype(str)
    s, e = f"{start[:4]}-{start[4:6]}-{start[6:]}", f"{end[:4]}-{end[4:6]}-{end[6:]}"
    df = df[(df["trade_date"] >= s) & (df["trade_date"] <= e)]
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df if len(df) else None


def _fetch_em(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    raw = ak.fund_etf_hist_em(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
    if raw is None or raw.empty:
        return None
    col_map = {"日期": "trade_date", "开盘": "open", "最高": "high", "最低": "low",
               "收盘": "close", "成交量": "volume", "成交额": "amount"}
    df = raw.rename(columns=col_map)
    df = df[[c for c in col_map.values() if c in df.columns]].copy()
    df["trade_date"] = df["trade_date"].astype(str)
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def fetch_hist(code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """抓取单只 ETF 日频行情；start/end 格式 YYYYMMDD。失败重试，双源切换。"""
    for i in range(config.MAX_RETRY):
        try:
            return _fetch_sina(code, start, end)
        except Exception as e:  # noqa: BLE001
            print(f"  [重试 {i + 1}/{config.MAX_RETRY}] {code} 新浪源失败: {e}")
            time_sleep()
    for i in range(config.MAX_RETRY):
        try:
            return _fetch_em(code, start, end)
        except Exception as e:  # noqa: BLE001
            print(f"  [备用东财源 {i + 1}/{config.MAX_RETRY}] {code} 失败: {e}")
            time_sleep()
    return None


def update_quotes(codes: list, start: str, end: str) -> dict:
    """批量采集日频行情。返回 {"ok": n, "empty": n, "fail": n}"""
    ok = empty = fail = 0
    total = len(codes)
    for i, code in enumerate(codes, 1):
        df = fetch_hist(code, start, end)
        if df is None or df.empty:
            empty += 1
        elif storage.upsert_quotes(code, df) > 0:
            ok += 1
        else:
            fail += 1
        if i % 20 == 0 or i == total:
            print(f"  行情进度 {i}/{total}（成功 {ok} / 空数据 {empty} / 失败 {fail}）")
        time.sleep(config.REQUEST_INTERVAL)
    storage.set_meta("quotes_updated_at", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))
    return {"ok": ok, "empty": empty, "fail": fail}
