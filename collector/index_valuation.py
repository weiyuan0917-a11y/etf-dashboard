# -*- coding: utf-8 -*-
"""指数估值采集（V1.3 新增）

数据源：
  - PE/PB 历史：akshare.stock_index_pe_lg / stock_index_pb_lg（中证系 legulegu 镜像）
  - 指数清单：akshare.stock_zh_index_spot_sina（新浪，覆盖广）

支持的指数（中证系 + 上证系，legulegu 覆盖）：
  上证50 / 沪深300 / 中证100 / 中证500 / 中证800 / 中证1000
  上证红利 / 上证180 / 上证380
  （创业板、科创 50、其它深证指数 legulegu 暂无历史 PE/PB，标 unavailable）
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import storage


# 指数清单：(name_for_display, legulegu_PE_name, sina_code)
# 留 None 表示 legulegu 无数据，UI 显示"待补"
INDEX_UNIVERSE: list[tuple[str, str, str]] = [
    ("上证50",      "上证50",   "sh000016"),
    ("沪深300",     "沪深300",  "sh000300"),
    ("中证100",     "中证100",  "sh000903"),
    ("中证500",     "中证500",  "sh000905"),
    ("中证800",     "中证800",  "sh000906"),
    ("中证1000",    "中证1000", "sh000852"),
    ("上证红利",    "上证红利", "sh000015"),
    ("上证180",     "上证180",  "sh000010"),
    ("上证380",     "上证380",  "sh000009"),
    # legulegu 暂无数据的指数，name_for_display 写一个，PE/PB 字段留空
    ("创业板指",    None,       "sz399006"),
    ("科创50",      None,       "sh000688"),
    ("上证指数",    None,       "sh000001"),
    ("深证成指",    None,       "sz399001"),
]


def _fetch_legulegu(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (pe_df, pb_df)，失败抛 RuntimeError。"""
    import akshare as ak
    pe = ak.stock_index_pe_lg(symbol=symbol)
    pb = ak.stock_index_pb_lg(symbol=symbol)
    if pe is None or len(pe) == 0:
        raise RuntimeError(f"legulegu {symbol} PE 空")
    if pb is None or len(pb) == 0:
        raise RuntimeError(f"legulegu {symbol} PB 空")
    return pe, pb


def _fetch_index_spot() -> pd.DataFrame:
    """拉指数实时行情（最新价、涨跌幅），用 sina。"""
    import akshare as ak
    return ak.stock_zh_index_spot_sina()


def _percentile(series: pd.Series, current: float) -> float | None:
    """当前值在 series 中的分位（0-100）。series 需去掉 NaN。"""
    if series is None or len(series) == 0 or pd.isna(current):
        return None
    s = series.dropna()
    if len(s) == 0:
        return None
    return float((s <= current).sum() / len(s) * 100)


def update_index_valuation(verbose: bool = True) -> dict:
    """主入口：拉所有指数的 PE/PB 历史，写入 index_valuation 表。

    Returns: {"ok": int, "skipped": int, "fail": int, "rows": int, "elapsed_s": float}
    """
    import akshare as ak
    _t0 = time.time()
    storage.init_db()

    # 1. 拉指数实时行情（最新点位 + 涨跌幅）
    try:
        spot = _fetch_index_spot()
        spot_map = spot.set_index("代码")[["最新价", "涨跌幅"]].to_dict("index")
    except Exception as e:  # noqa: BLE001
        if verbose: print(f"[warn] 拉指数实时行情失败（用 last close 替代）：{e}")
        spot_map = {}

    ok, skipped, fail, total_rows = 0, 0, 0, 0
    rows_to_insert: list[tuple] = []

    for name, lg_name, sina_code in INDEX_UNIVERSE:
        if verbose: print(f"[{name}] 拉取 ...")
        # 实时点位（用于补 close 字段）
        latest_close = None
        if sina_code in spot_map:
            latest_close = spot_map[sina_code].get("最新价")

        if lg_name is None:
            # 没有 legulegu 数据,只写一行占位
            skipped += 1
            if verbose: print(f"  → legulegu 暂无,跳过（仅占位）")
            continue

        try:
            time.sleep(1.2)  # legulegu 限流,1.2s/只
            pe_df, pb_df = _fetch_legulegu(lg_name)
        except Exception as e:  # noqa: BLE001
            fail += 1
            if verbose: print(f"  → 失败：{e}")
            continue

        # 合并 PE/PB (按日期),只需要 pe_ttm 和 pb 字段
        pe_short = pe_df[["日期", "指数", "滚动市盈率", "静态市盈率"]].copy()
        pe_short = pe_short.rename(columns={
            "滚动市盈率": "pe_ttm",
            "静态市盈率": "pe_static",
        })
        pb_short = pb_df[["日期", "市净率"]].copy()
        pb_short = pb_short.rename(columns={"市净率": "pb"})

        merged = pd.merge(pe_short, pb_short, on="日期", how="outer").sort_values("日期")
        # 指数点位：用 PE 表的"指数"列(同源同时间)
        merged = merged.rename(columns={"指数": "close"})

        # 写入
        n = 0
        for _, r in merged.iterrows():
            rows_to_insert.append((
                sina_code, name, str(r["日期"]),
                float(r["close"]) if pd.notna(r["close"]) else None,
                float(r["pe_ttm"]) if pd.notna(r["pe_ttm"]) else None,
                float(r["pe_static"]) if pd.notna(r["pe_static"]) else None,
                float(r["pb"]) if pd.notna(r["pb"]) else None,
                "legulegu",
            ))
            n += 1
        total_rows += n
        ok += 1
        if verbose: print(f"  → 写入 {n} 行（{merged['日期'].iloc[0]} ~ {merged['日期'].iloc[-1]}）")

    # 2. 批量写库
    if rows_to_insert:
        with storage.get_conn() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO index_valuation
                   (code, name, trade_date, close, pe_ttm, pe_static, pb, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                rows_to_insert,
            )

    elapsed = round(time.time() - _t0, 1)
    if verbose:
        print(f"=== 指数估值采集完成：{ok} ok / {skipped} 暂无 / {fail} fail，"
              f"共 {total_rows} 行，耗时 {elapsed}s ===")

    # 写完成标记(streamlit 侧栏读这个)
    try:
        import json as _json
        from datetime import datetime as _dt
        from pathlib import Path as _P
        _done = _P(storage.config.DB_PATH).parent / "index_valuation_done.json"
        _done.write_text(
            _json.dumps({
                "ok": ok, "skipped": skipped, "fail": fail, "rows": total_rows,
                "seconds": elapsed,
                "finished_at": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as _e:  # noqa: BLE001
        if verbose: print(f"完成标记写失败（不影响主流程）：{_e}")

    return {"ok": ok, "skipped": skipped, "fail": fail, "rows": total_rows, "elapsed_s": elapsed}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    print(update_index_valuation(verbose=True))
