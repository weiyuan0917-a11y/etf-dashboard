# -*- coding: utf-8 -*-
"""一键更新入口：
    python update.py                # 默认：清单 + 规模前 300 只的近 3 年行情
    python update.py --all          # 全量（约 1000+ 只，耗时较长）
    python update.py --top 100      # 规模前 100 只
"""
import argparse
import sys
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
try:  # Windows 控制台中文输出兜底
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import config
import storage
from collector.etf_list import update_etf_list
from collector.daily_quotes import update_quotes


def main() -> None:
    ap = argparse.ArgumentParser(description="ETF 工具台数据更新")
    ap.add_argument("--all", action="store_true", help="采集全部 ETF 行情（慢）")
    ap.add_argument("--top", type=int, default=300, help="按规模取前 N 只（默认 300）")
    args = ap.parse_args()
    _t0 = datetime.now()

    print(f"=== ETF 工具台数据更新 {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    storage.init_db()

    n_list = update_etf_list()
    if n_list == 0:
        print("清单为空，终止（可稍后重试，东财接口偶发限流）")
        return

    lst = storage.load_etf_list()
    lst = lst.dropna(subset=["total_mv"]).sort_values("total_mv", ascending=False)
    if args.all:
        codes = lst["code"].tolist()
    else:
        codes = lst.head(args.top)["code"].tolist()
    print(f"[2/2] 采集日频行情：{len(codes)} 只，回溯 {config.HISTORY_YEARS} 年 ...")

    start = (datetime.now() - timedelta(days=365 * config.HISTORY_YEARS)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    res = update_quotes(codes, start, end)
    print(
        f"完成：行情成功 {res['ok']} / 空数据 {res['empty']} / 失败 {res['fail']}。"
        f"数据文件：{config.DB_PATH}"
    )

    # 写一个完成标记文件（streamlit 侧栏会读这个来刷新时间戳 + 显示结果）
    try:
        import json as _json
        from pathlib import Path as _P
        _done = _P(config.DB_PATH).parent / "update_done.json"
        _done.write_text(
            _json.dumps({
                "ok": res["ok"], "empty": res["empty"], "fail": res["fail"],
                "seconds": int((datetime.now() - _t0).total_seconds()),
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "mode": ("all" if args.all else f"top{args.top}"),
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as _e:  # noqa: BLE001
        print(f"完成标记写失败（不影响主流程）：{_e}")


if __name__ == "__main__":
    main()
