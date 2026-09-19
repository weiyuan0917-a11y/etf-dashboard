# -*- coding: utf-8 -*-
"""行业轮动信号采集（V1.3 新增）

按 ETF name 关键词聚合行业,计算各行业的：
  - 平均涨跌幅（1/5/20/60 日）
  - 总规模 / 活跃度
  - 平均溢价率
  - 综合得分（动量 50% + 活跃度 30% + 估值反向 20%）

输出：写入 industry_strength 表,供"行业轮动"页面读取。
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
import storage


# 行业关键词清单:每个行业用 1 个主关键词,>=5 只 ETF 才纳入
INDUSTRY_KEYWORDS: list[tuple[str, str]] = [
    ("消费", "消费"),
    ("人工智能", "人工智能"),
    ("芯片", "芯片"),
    ("新能源", "新能源"),
    ("医疗", "医疗"),
    ("互联网", "互联网"),
    ("证券", "证券"),
    ("有色", "有色"),
    ("汽车", "汽车"),
    ("医药", "医药"),
    ("电力", "电力"),
    ("金融", "金融"),
    ("通信", "通信"),
    ("光伏", "光伏"),
    ("软件", "软件"),
    ("机器人", "机器人"),
    ("半导体", "半导体"),
    ("食品", "食品"),
    ("银行", "银行"),
    ("化工", "化工"),
    ("家电", "家电"),
    ("材料", "材料"),
    ("地产", "地产"),
    ("消费电子", "消费电子"),
    ("数字经济", "数字经济"),
    ("军工", "军工"),
    ("农业", "农业"),
]


def _compute_industry_metrics(verbose: bool = True) -> pd.DataFrame:
    """核心计算:遍历每个行业关键词,从 ETF 清单+行情+实时行情 算指标。"""
    import requests
    from live import fetch_quotes, is_quote_fresh

    storage.init_db()
    etf_list = storage.load_etf_list()
    if etf_list.empty:
        if verbose: print("[warn] ETF 清单为空,先跑 collector/update.py")
        return pd.DataFrame()

    # 拉一次实时行情
    if verbose: print("[live] 拉实时行情 ...")
    live_quotes = fetch_quotes(etf_list["code"].tolist())
    if verbose: print(f"  → {len(live_quotes)} / {len(etf_list)} 只拿到实时价")

    # 转 dict 方便查(fix: 返回是 DataFrame)
    if hasattr(live_quotes, "set_index"):
        live_map = live_quotes.set_index("code").to_dict("index")
    else:
        live_map = {q["code"]: q for q in live_quotes}

    def _get(code: str, key: str, default=None):
        return live_map.get(code, {}).get(key, default)

    # 行业 ETF 池:每个行业的 amount 从本地最近一日行情取(优先有成交额的那天)
    # live.py 的新浪源目前没 amount 字段,只能用 daily_quotes 兜底
    daily_amount_map: dict[str, float] = {}
    try:
        for _code in etf_list["code"].tolist():
            _q = storage.load_quotes(_code)
            if _q is None or _q.empty or "amount" not in _q.columns:
                continue
            _last = _q.dropna(subset=["amount"]).tail(1)
            if not _last.empty:
                daily_amount_map[_code] = float(_last["amount"].iloc[0])
    except Exception:  # noqa: BLE001
        daily_amount_map = {}

    rows: list[dict] = []
    for ind_name, kw in INDUSTRY_KEYWORDS:
        # 1. 选行业 ETF
        members = etf_list[etf_list["name"].astype(str).str.contains(kw, na=False)].copy()
        if len(members) < 5:
            continue

        # 2. 拉近 60 个交易日行情,算 1/5/20/60 日收益
        codes = members["code"].tolist()
        with storage.get_conn() as conn:
            q_rows = conn.execute(
                "SELECT code, trade_date, close FROM quotes "
                "WHERE code IN ({}) ORDER BY code, trade_date".format(
                    ",".join(["?"] * len(codes))
                ),
                codes,
            ).fetchall()
        if not q_rows:
            continue
        qdf = pd.DataFrame(q_rows, columns=["code", "trade_date", "close"])
        qdf["trade_date"] = pd.to_datetime(qdf["trade_date"])
        qdf = qdf.sort_values(["code", "trade_date"])

        # 算每只 ETF 的 1/5/20/60 日涨幅
        per_etf: list[dict] = []
        for code, g in qdf.groupby("code"):
            g = g.sort_values("trade_date")
            closes = g["close"].values
            if len(closes) < 2:
                continue
            last = closes[-1]
            chg = {
                "code": code,
                "chg_1d": (last / closes[-2] - 1) * 100 if len(closes) >= 2 else None,
                "chg_5d": (last / closes[-5] - 1) * 100 if len(closes) >= 5 else None,
                "chg_20d": (last / closes[-20] - 1) * 100 if len(closes) >= 20 else None,
                "chg_60d": (last / closes[-60] - 1) * 100 if len(closes) >= 60 else None,
            }
            per_etf.append(chg)
        if not per_etf:
            continue
        chg_df = pd.DataFrame(per_etf)

        # 3. 加实时行情 + 规模
        members = members.merge(chg_df, on="code", how="left")
        members["live_chg"] = members["code"].map(lambda c: _get(c, "chg_pct"))
        members["live_amount"] = members["code"].map(lambda c: _get(c, "amount"))
        members["premium"] = members["code"].map(lambda c: _get(c, "premium_rate"))
        # 成交额兜底:新浪源无 amount 字段时用本地最近一日的 amount
        members["live_amount"] = members["live_amount"].fillna(members["code"].map(daily_amount_map))
        members["live_chg"] = members["live_chg"].fillna(members["chg_1d"])

        # 4. 行业聚合
        total_mv = members["total_mv"].sum() / 1e8  # 元 → 亿元
        avg_chg_1d = members["live_chg"].mean()
        avg_chg_5d = members["chg_5d"].mean()
        avg_chg_20d = members["chg_20d"].mean()
        avg_chg_60d = members["chg_60d"].mean()
        total_amount = members["live_amount"].sum() / 1e8 if members["live_amount"].notna().any() else 0
        # 活跃度 = 成交额 / 规模(高 = 资金关注)
        activity = (total_amount / total_mv) if total_mv > 0 else 0
        avg_premium = members["premium"].mean() if members["premium"].notna().any() else None

        rows.append({
            "industry": ind_name,
            "n_etf": len(members),
            "total_mv": round(total_mv, 2),
            "avg_chg_1d": round(avg_chg_1d, 2) if pd.notna(avg_chg_1d) else None,
            "avg_chg_5d": round(avg_chg_5d, 2) if pd.notna(avg_chg_5d) else None,
            "avg_chg_20d": round(avg_chg_20d, 2) if pd.notna(avg_chg_20d) else None,
            "avg_chg_60d": round(avg_chg_60d, 2) if pd.notna(avg_chg_60d) else None,
            "activity": round(activity, 4) if activity else None,
            "avg_premium": round(avg_premium, 2) if pd.notna(avg_premium) else None,
        })
        if verbose:
            prem_str = f"{avg_premium:+.2f}%" if avg_premium is not None else "—"
            print(f"  [{ind_name}] {len(members)} 只, 规模 {total_mv:.0f} 亿, 20日 {avg_chg_20d:+.2f}%, 溢价 {prem_str}")

    return pd.DataFrame(rows)


def _compute_scores(df: pd.DataFrame) -> pd.DataFrame:
    """对每行算综合得分(0-100),输出 signal。

    模型(经典加权):
      score = 0.5 * 动量分位 + 0.3 * 活跃度分位 + 0.2 * (100 - 溢价分位)
    信号:  score >= 65 → 做多
           score >= 40 → 观望
           否则        → 减仓
    """
    if df.empty:
        df["score"] = []
        df["signal"] = []
        return df

    def _rank_pct(s: pd.Series) -> pd.Series:
        """把值映射到 0-100 分位(越大分位越高)。"""
        s = s.dropna()
        if len(s) == 0:
            return pd.Series(dtype=float)
        ranks = s.rank(method="average", pct=True) * 100
        return ranks

    # 各维度分位
    mom_score = _rank_pct(df["avg_chg_20d"].fillna(0))
    act_score = _rank_pct(df["activity"].fillna(0))
    # 溢价反向(高溢价 = 过热 = 低分)
    prem_score = 100 - _rank_pct(df["avg_premium"].fillna(0))

    # 对齐 index
    df = df.copy()
    df["_mom"] = df["avg_chg_20d"].fillna(0).rank(method="average", pct=True) * 100
    df["_act"] = df["activity"].fillna(0).rank(method="average", pct=True) * 100
    df["_prem"] = 100 - df["avg_premium"].fillna(0).rank(method="average", pct=True) * 100
    df["score"] = (0.5 * df["_mom"] + 0.3 * df["_act"] + 0.2 * df["_prem"]).round(1)
    df.drop(columns=["_mom", "_act", "_prem"], inplace=True)

    df["signal"] = df["score"].apply(
        lambda s: "做多" if s >= 65 else ("观望" if s >= 40 else "减仓")
    )
    return df


def update_industry_strength(verbose: bool = True) -> dict:
    """主入口:算 + 入库 + 写完成标记。"""
    _t0 = time.time()
    df = _compute_industry_metrics(verbose=verbose)
    if df.empty:
        return {"ok": 0, "fail": 1, "elapsed_s": 0}
    df = _compute_scores(df)
    df["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 写库
    with storage.get_conn() as conn:
        conn.execute("DELETE FROM industry_strength")  # 每次全量刷新
        conn.executemany(
            """INSERT INTO industry_strength
               (industry, n_etf, total_mv, avg_chg_1d, avg_chg_5d, avg_chg_20d, avg_chg_60d,
                activity, avg_premium, score, signal, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            df[["industry", "n_etf", "total_mv", "avg_chg_1d", "avg_chg_5d", "avg_chg_20d", "avg_chg_60d",
                "activity", "avg_premium", "score", "signal", "updated_at"]].itertuples(index=False, name=None),
        )

    elapsed = round(time.time() - _t0, 1)
    if verbose:
        print(f"=== 行业轮动采集完成：{len(df)} 个行业, 耗时 {elapsed}s ===")
        # 打印 Top 5
        top = df.sort_values("score", ascending=False).head(5)
        print("\nTop 5 行业:")
        for _, r in top.iterrows():
            print(f"  {r['industry']:8} 得分 {r['score']:5.1f}  信号 {r['signal']}  20日 {r['avg_chg_20d']:+5.2f}%")

    # 完成标记
    try:
        import json as _json
        from pathlib import Path as _P
        _done = _P(storage.config.DB_PATH).parent / "industry_done.json"
        _done.write_text(
            _json.dumps({
                "n": len(df), "elapsed_s": elapsed,
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as _e:
        if verbose: print(f"完成标记写失败：{_e}")

    return {"ok": len(df), "fail": 0, "elapsed_s": elapsed}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    print(update_industry_strength(verbose=True))
