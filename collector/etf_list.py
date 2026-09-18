# -*- coding: utf-8 -*-
"""ETF 清单快照采集：全市场场内 ETF 的名称/价格/规模/折溢价（东方财富源）"""
from typing import Optional

import akshare as ak
import pandas as pd

import config
import storage


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """把 spot 接口原始列映射为库表结构"""
    col_map = {
        "代码": "code", "名称": "name", "最新价": "latest_price", "涨跌幅": "change_pct",
        "IOPV实时估值": "iopv", "基金折价率": "premium_rate", "总市值": "total_mv",
        "成交量": "volume", "成交额": "amount",
    }
    df = df.rename(columns=col_map)
    keep = list(col_map.values())
    df = df[[c for c in keep if c in df.columns]].copy()
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["snapshot_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    for c in ["latest_price", "change_pct", "iopv", "premium_rate", "total_mv", "volume", "amount"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def fetch_etf_list() -> Optional[pd.DataFrame]:
    """抓取全市场 ETF 实时快照清单，失败重试，返回清洗后的 DataFrame"""
    last_err = None
    for i in range(config.MAX_RETRY):
        try:
            raw = ak.fund_etf_spot_em()
            return _clean(raw)
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  [重试 {i + 1}/{config.MAX_RETRY}] 清单接口失败: {e}")
            time_sleep()
    print(f"  [放弃] 清单采集失败: {last_err}")
    return None


def time_sleep() -> None:
    import time
    time.sleep(config.RETRY_WAIT)


def update_etf_list() -> int:
    print("[1/2] 采集 ETF 清单快照 ...")
    df = fetch_etf_list()
    if df is None:
        return 0
    n = storage.upsert_etf_list(df)
    storage.set_meta("etf_list_updated_at", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))
    print(f"  清单写入 {n} 只（含名称/最新价/IOPV/折溢价/规模代理）")
    return n
