# -*- coding: utf-8 -*-
"""A 股 ETF 工具台：增量更新
- 清单全量刷新（覆盖式）
- 行情：仅对已存在标的拉取 last_trade_date 之后的数据（增量），新增标的拉近 3 年
- 输出日志到 logs/update_YYYYMMDD.log
- 退出码 0=成功 1=清单失败 2=行情整体失败
"""
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config
import storage
from collector.etf_list import update_etf_list
from collector.daily_quotes import fetch_hist

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"update_{datetime.now():%Y%m%d}.log"


def _log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _start_str(d: datetime) -> str:
    return d.strftime("%Y%m%d")


def main() -> int:
    _log("=== 增量更新开始 ===")
    storage.init_db()

    # 1) 清单快照
    n_list = update_etf_list()
    if n_list == 0:
        _log("[ERR] 清单采集失败，终止")
        return 1
    _log(f"清单 {n_list} 只已写入")

    # 2) 行情增量
    lst = storage.load_etf_list()
    lst = lst.dropna(subset=["total_mv"]).sort_values("total_mv", ascending=False)
    codes = lst["code"].tolist()

    # 已入库的最新交易日
    quoted = storage.quoted_codes()
    today = datetime.now()
    default_start = today - timedelta(days=365 * config.HISTORY_YEARS)
    end = today.strftime("%Y%m%d")
    # 增量窗口回退 3 个日历日，避免单日窗口新浪/东财返空
    OVERLAP_DAYS = 3

    ok = empty = fail = skipped = 0
    total = len(codes)
    for i, code in enumerate(codes, 1):
        # 增量起点：库内最后交易日 - OVERLAP_DAYS；无库则按全量回溯
        with storage.get_conn() as conn:
            row = conn.execute("SELECT MAX(trade_date) FROM quotes WHERE code=?", (code,)).fetchone()
        last_dt = row[0] if row else None
        if last_dt:
            start_dt = datetime.strptime(last_dt, "%Y-%m-%d") - timedelta(days=OVERLAP_DAYS)
            start = _start_str(start_dt)
            if start_dt >= today:
                skipped += 1
                if i % 50 == 0 or i == total:
                    _log(f"  行情进度 {i}/{total}（成功 {ok} / 跳过 {skipped} / 失败 {fail}）")
                continue
        else:
            start = _start_str(default_start)

        df = fetch_hist(code, start, end)
        if df is None or df.empty:
            empty += 1
        elif storage.upsert_quotes(code, df) > 0:
            ok += 1
        else:
            fail += 1

        if i % 50 == 0 or i == total:
            _log(f"  行情进度 {i}/{total}（成功 {ok} / 跳过 {skipped} / 空 {empty} / 失败 {fail}）")
        time.sleep(config.REQUEST_INTERVAL)

    storage.set_meta("quotes_updated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    _log(f"=== 完成：成功 {ok} / 跳过 {skipped} / 空 {empty} / 失败 {fail} ===")
    return 0 if (ok + skipped) > 0 else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        _log(f"[FATAL] {type(e).__name__}: {e}")
        sys.exit(3)
