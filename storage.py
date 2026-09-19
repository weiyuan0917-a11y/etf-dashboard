# -*- coding: utf-8 -*-
"""SQLite 存储层：建表、写入、查询。所有数据落地 data/etf.db"""
from __future__ import annotations

import sqlite3
from typing import Iterable

import pandas as pd

import config


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS etf_list (
                code           TEXT PRIMARY KEY,   -- 6位代码，如 510300
                name           TEXT NOT NULL,
                latest_price   REAL,               -- 快照最新价
                change_pct     REAL,               -- 快照涨跌幅 %
                iopv           REAL,               -- IOPV 实时估值（快照时点）
                premium_rate   REAL,               -- 基金折价率 %（正=溢价）
                total_mv       REAL,               -- 总市值（元），作为规模代理
                volume         REAL,
                amount         REAL,               -- 成交额（元）
                snapshot_at    TEXT                -- 快照时间
            );
            CREATE TABLE IF NOT EXISTS quotes (
                code       TEXT NOT NULL,
                trade_date TEXT NOT NULL,          -- YYYY-MM-DD
                open       REAL, high REAL, low REAL, close REAL,
                volume     REAL, amount REAL,
                PRIMARY KEY (code, trade_date)
            );
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_quotes_code ON quotes(code);
            CREATE INDEX IF NOT EXISTS idx_quotes_date ON quotes(trade_date);

            -- ============ 指数估值（V1.3 新增）============
            CREATE TABLE IF NOT EXISTS index_valuation (
                code        TEXT NOT NULL,           -- 指数简称键，如 sh000300
                name        TEXT NOT NULL,           -- 显示名，如 沪深300
                trade_date  TEXT NOT NULL,            -- 月末日期
                close       REAL,                     -- 指数收盘点位
                pe_ttm      REAL,                     -- 滚动市盈率
                pe_static   REAL,                     -- 静态市盈率
                pb          REAL,                     -- 市净率
                source      TEXT NOT NULL,            -- legulegu / sina
                PRIMARY KEY (code, trade_date)
            );
            CREATE INDEX IF NOT EXISTS idx_iv_code ON index_valuation(code);
            CREATE INDEX IF NOT EXISTS idx_iv_date ON index_valuation(trade_date);

            -- ============ 行业轮动（V1.3 新增）============
            -- 行业强弱指标(按 ETF 关键词聚合),从行情实时算
            CREATE TABLE IF NOT EXISTS industry_strength (
                industry   TEXT PRIMARY KEY,           -- 行业关键词
                n_etf      INTEGER,                    -- 样本 ETF 数
                total_mv   REAL,                       -- 总规模(亿元)
                avg_chg_1d REAL,                       -- 1日平均涨跌 %
                avg_chg_5d REAL,                       -- 5日
                avg_chg_20d REAL,                      -- 20日
                avg_chg_60d REAL,                      -- 60日
                activity   REAL,                       -- 活跃度 = 成交额/规模
                avg_premium REAL,                      -- 平均溢价率 %
                score      REAL,                       -- 综合得分(0-100)
                signal     TEXT,                       -- 做多/观望/减仓
                updated_at TEXT
            );
            """
        )
        _init_trade_tables(conn)


def _init_trade_tables(conn: sqlite3.Connection) -> None:
    """模拟交易相关表：持仓、成交、网格、网格成交流水"""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS holdings (
            code          TEXT PRIMARY KEY,
            name          TEXT,
            shares        REAL NOT NULL DEFAULT 0,
            avg_cost      REAL NOT NULL DEFAULT 0,
            realized_pnl  REAL NOT NULL DEFAULT 0,
            first_buy_at  TEXT,
            last_buy_at   TEXT,
            last_sell_at  TEXT,
            note          TEXT
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            code    TEXT NOT NULL,
            name    TEXT,
            type    TEXT NOT NULL,
            price   REAL NOT NULL,
            shares  REAL NOT NULL,
            amount  REAL NOT NULL,
            fee     REAL NOT NULL DEFAULT 0,
            ts      TEXT NOT NULL,
            note    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tx_code_ts ON transactions(code, ts);
        CREATE INDEX IF NOT EXISTS idx_tx_ts ON transactions(ts);

        CREATE TABLE IF NOT EXISTS grids (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            code            TEXT NOT NULL,
            name            TEXT,
            center_price    REAL NOT NULL,
            upper_price     REAL NOT NULL,
            lower_price     REAL NOT NULL,
            grid_step_pct   REAL NOT NULL,
            per_grid_shares INTEGER NOT NULL,
            total_invested  REAL NOT NULL DEFAULT 0,
            total_shares    REAL NOT NULL DEFAULT 0,
            realized_pnl    REAL NOT NULL DEFAULT 0,
            status          TEXT NOT NULL DEFAULT 'active',
            created_at      TEXT,
            closed_at       TEXT,
            note            TEXT
        );

        CREATE TABLE IF NOT EXISTS grid_trades (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            grid_id   INTEGER NOT NULL,
            code      TEXT NOT NULL,
            name      TEXT,
            side      TEXT NOT NULL,
            price     REAL NOT NULL,
            shares    REAL NOT NULL,
            amount    REAL NOT NULL,
            level     INTEGER NOT NULL DEFAULT 0,
            ts        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gtk_grid ON grid_trades(grid_id, ts);

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )


def set_meta(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_meta(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def upsert_etf_list(df: pd.DataFrame) -> int:
    """写入 ETF 快照清单（全量覆盖式 upsert），返回行数"""
    if df is None or df.empty:
        return 0
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO etf_list VALUES(?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET name=excluded.name, latest_price=excluded.latest_price, "
            "change_pct=excluded.change_pct, iopv=excluded.iopv, premium_rate=excluded.premium_rate, "
            "total_mv=excluded.total_mv, volume=excluded.volume, amount=excluded.amount, "
            "snapshot_at=excluded.snapshot_at",
            df.itertuples(index=False),
        )
    return len(df)


def upsert_quotes(code: str, df: pd.DataFrame) -> int:
    """写入单只 ETF 日频行情，返回输入行数（含覆盖更新的历史日期）。"""
    if df is None or df.empty:
        return 0
    rows = [
        (code, r["trade_date"], r["open"], r["high"], r["low"], r["close"], r["volume"], r["amount"])
        for _, r in df.iterrows()
    ]
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(code, trade_date) DO UPDATE SET open=excluded.open, high=excluded.high, "
            "low=excluded.low, close=excluded.close, volume=excluded.volume, amount=excluded.amount",
            rows,
        )
    return len(rows)


def load_etf_list() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM etf_list", conn)


def load_quotes(code: str) -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql(
            "SELECT * FROM quotes WHERE code=? ORDER BY trade_date", conn, params=(code,)
        )


def load_all_latest_quotes(codes: Iterable[str]) -> pd.DataFrame:
    """取每只 ETF 最近一条行情（用于看板展示最新收盘口径）"""
    codes = list(codes)
    if not codes:
        return pd.DataFrame()
    ph = ",".join("?" * len(codes))
    with get_conn() as conn:
        return pd.read_sql(
            f"SELECT q.* FROM quotes q JOIN (SELECT code, MAX(trade_date) d FROM quotes "
            f"WHERE code IN ({ph}) GROUP BY code) t ON q.code=t.code AND q.trade_date=t.d",
            conn,
            params=codes,
        )


def quoted_codes() -> set:
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT code FROM quotes").fetchall()
    return {r[0] for r in rows}


# =====================================================================
#  模拟交易 / 网格 / 设置
# =====================================================================

def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def _now() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- 成交 + 持仓 ----------

def record_trade(
    code: str, name: str, side: str, price: float, shares: int, fee: float = 0.0, note: str = ""
) -> int:
    """记一笔 BUY/SELL 成交，同步更新 holdings 均价、累计已实现盈亏。返回 tx.id。"""
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    if shares <= 0 or price <= 0:
        raise ValueError("shares/price must be positive")
    amount = round(price * shares, 2)
    ts = _now()

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO transactions(code, name, type, price, shares, amount, fee, ts, note) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (code, name, side, price, shares, amount, fee, ts, note),
        )
        tx_id = cur.lastrowid

        row = conn.execute(
            "SELECT code, name, shares, avg_cost, realized_pnl, first_buy_at, last_buy_at, last_sell_at "
            "FROM holdings WHERE code=?",
            (code,),
        ).fetchone()
        if row is None:
            cur_shares = 0.0
            cur_avg = 0.0
            realized = 0.0
            first_buy = None
            last_buy = None
            last_sell = None
        else:
            _, _, cur_shares, cur_avg, realized, first_buy, last_buy, last_sell = row

        if side == "BUY":
            new_shares = cur_shares + shares
            new_avg = (cur_shares * cur_avg + price * shares) / new_shares if new_shares > 0 else 0
            new_first = first_buy or ts
            new_last_buy = ts
            new_last_sell = last_sell
        else:  # SELL
            if shares > cur_shares:
                raise ValueError(f"卖出份数 {shares} 超过当前持仓 {cur_shares}")
            realized += (price - cur_avg) * shares - fee
            new_shares = cur_shares - shares
            new_avg = cur_avg if new_shares > 0 else 0
            new_first = first_buy
            new_last_buy = last_buy
            new_last_sell = ts

        if new_shares > 0:
            conn.execute(
                "INSERT INTO holdings(code, name, shares, avg_cost, realized_pnl, "
                "first_buy_at, last_buy_at, last_sell_at) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(code) DO UPDATE SET name=excluded.name, shares=excluded.shares, "
                "avg_cost=excluded.avg_cost, realized_pnl=excluded.realized_pnl, "
                "first_buy_at=COALESCE(holdings.first_buy_at, excluded.first_buy_at), "
                "last_buy_at=excluded.last_buy_at, last_sell_at=excluded.last_sell_at",
                (code, name, new_shares, new_avg, realized, new_first, new_last_buy, new_last_sell),
            )
        else:
            # 清仓：保留 realized_pnl 记录
            conn.execute(
                "INSERT INTO holdings(code, name, shares, avg_cost, realized_pnl, "
                "first_buy_at, last_buy_at, last_sell_at) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(code) DO UPDATE SET name=excluded.name, shares=0, avg_cost=0, "
                "realized_pnl=excluded.realized_pnl, "
                "first_buy_at=COALESCE(holdings.first_buy_at, excluded.first_buy_at), "
                "last_buy_at=excluded.last_buy_at, last_sell_at=excluded.last_sell_at",
                (code, name, 0, 0, realized, new_first, new_last_buy, new_last_sell),
            )
    return int(tx_id)


def load_holdings() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM holdings WHERE shares > 0 ORDER BY code", conn)


def load_all_holdings() -> pd.DataFrame:
    """包含已清仓记录（便于看历史盈亏）"""
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM holdings ORDER BY code", conn)


def update_holding_note(code: str, note: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE holdings SET note=? WHERE code=?", (note, code))


def delete_holding(code: str) -> None:
    """从持仓中删除该标的（含其全部成交记录）"""
    with get_conn() as conn:
        conn.execute("DELETE FROM transactions WHERE code=?", (code,))
        conn.execute("DELETE FROM holdings WHERE code=?", (code,))


def load_transactions(code: str | None = None, limit: int = 500) -> pd.DataFrame:
    with get_conn() as conn:
        if code:
            return pd.read_sql(
                "SELECT * FROM transactions WHERE code=? ORDER BY ts DESC LIMIT ?",
                conn, params=(code, limit),
            )
        return pd.read_sql(
            "SELECT * FROM transactions ORDER BY ts DESC LIMIT ?", conn, params=(limit,)
        )


# ---------- 网格交易 ----------

def create_grid(
    code: str, name: str, center: float, upper: float, lower: float,
    step_pct: float, per_grid_shares: int, note: str = "",
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO grids(code, name, center_price, upper_price, lower_price, "
            "grid_step_pct, per_grid_shares, created_at, note) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (code, name, center, upper, lower, step_pct, per_grid_shares, _now(), note),
        )
    return int(cur.lastrowid)


def load_grids(status: str | None = None) -> pd.DataFrame:
    with get_conn() as conn:
        if status:
            return pd.read_sql(
                "SELECT * FROM grids WHERE status=? ORDER BY created_at DESC", conn, params=(status,)
            )
        return pd.read_sql("SELECT * FROM grids ORDER BY created_at DESC", conn)


def get_grid(grid_id: int) -> dict | None:
    with get_conn() as conn:
        cols = [d[0] for d in conn.execute("SELECT * FROM grids LIMIT 0").description]
        row = conn.execute("SELECT * FROM grids WHERE id=?", (grid_id,)).fetchone()
    if not row:
        return None
    return dict(zip(cols, row))


def grid_grid_columns(grid_id: int) -> list[dict]:
    """按 grid_step_pct 拆上下档位，返回 [{level, buy_price, sell_price}, ...]"""
    g = get_grid(grid_id)
    if not g:
        return []
    step = g["grid_step_pct"] / 100.0
    rows = []
    # 中心以下每档 = 中心 × (1 - step)^k，中心以上 = 中心 × (1 + step)^k
    k = 1
    while True:
        buy = g["center_price"] * ((1 - step) ** k)
        if buy < g["lower_price"] * 0.999:
            break
        if buy >= g["center_price"]:
            break
        prev_buy = g["center_price"] * ((1 - step) ** (k - 1))
        rows.append({
            "level": -k,
            "buy_price": round(buy, 4),
            "sell_price": round(prev_buy, 4),
        })
        k += 1
        if k > 50:
            break
    k = 1
    while True:
        sell = g["center_price"] * ((1 + step) ** k)
        if sell > g["upper_price"] * 1.001:
            break
        if sell <= g["center_price"]:
            break
        prev_sell = g["center_price"] * ((1 + step) ** (k - 1))
        rows.append({
            "level": k,
            "buy_price": round(prev_sell, 4),
            "sell_price": round(sell, 4),
        })
        k += 1
        if k > 50:
            break
    rows.sort(key=lambda r: r["level"])
    return rows


def record_grid_trade(
    grid_id: int, code: str, name: str, side: str, price: float, shares: int, level: int = 0
) -> int:
    """记一笔网格成交：写 grid_trades + 同步 grids 合计"""
    side = side.upper()
    amount = round(price * shares, 2)
    ts = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO grid_trades(grid_id, code, name, side, price, shares, amount, level, ts) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (grid_id, code, name, side, price, shares, amount, level, ts),
        )
        if side == "BUY":
            conn.execute(
                "UPDATE grids SET total_invested=total_invested+?, total_shares=total_shares+? WHERE id=?",
                (amount, shares, grid_id),
            )
        else:
            # 卖出：用 amount 折算一笔对冲
            conn.execute(
                "UPDATE grids SET total_shares=total_shares-?, realized_pnl=realized_pnl+? WHERE id=?",
                (shares, amount, grid_id),
            )
    return int(cur.lastrowid)


def load_grid_trades(grid_id: int) -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql(
            "SELECT * FROM grid_trades WHERE grid_id=? ORDER BY ts DESC", conn, params=(grid_id,)
        )


def update_grid_status(grid_id: int, status: str) -> None:
    with get_conn() as conn:
        if status == "closed":
            conn.execute(
                "UPDATE grids SET status=?, closed_at=? WHERE id=?", (status, _now(), grid_id)
            )
        else:
            conn.execute("UPDATE grids SET status=? WHERE id=?", (status, grid_id))


def delete_grid(grid_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM grid_trades WHERE grid_id=?", (grid_id,))
        conn.execute("DELETE FROM grids WHERE id=?", (grid_id,))


# ============================================================
#  指数估值（V1.3 新增）
# ============================================================

def list_index_universe() -> pd.DataFrame:
    """返回指数清单 + 各指数最新一行 PE/PB + 历史分位。

    列: code, name, last_date, last_close, pe_ttm, pe_static, pb,
        pe_ttm_pct, pb_pct, pe_static_pct, history_rows, source
    """
    with get_conn() as conn:
        # 全部历史
        all_rows = conn.execute(
            "SELECT code, name, trade_date, close, pe_ttm, pe_static, pb, source "
            "FROM index_valuation ORDER BY code, trade_date"
        ).fetchall()
        cols = ["code", "name", "trade_date", "close", "pe_ttm", "pe_static", "pb", "source"]
        df = pd.DataFrame(all_rows, columns=cols) if all_rows else pd.DataFrame(columns=cols)

    if df.empty:
        return df

    out_rows = []
    for code, grp in df.groupby("code", sort=False):
        name = grp["name"].iloc[-1]
        grp = grp.sort_values("trade_date")
        last = grp.iloc[-1]
        hist = grp.dropna(subset=["pe_ttm"])["pe_ttm"] if grp["pe_ttm"].notna().any() else pd.Series([], dtype=float)
        hist_pb = grp.dropna(subset=["pb"])["pb"] if grp["pb"].notna().any() else pd.Series([], dtype=float)

        def pct(series: pd.Series, current: float | None) -> float | None:
            if current is None or pd.isna(current) or len(series) == 0:
                return None
            return round(float((series <= current).sum() / len(series) * 100), 1)

        out_rows.append({
            "code": code,
            "name": name,
            "last_date": str(last["trade_date"]),
            "last_close": float(last["close"]) if pd.notna(last["close"]) else None,
            "pe_ttm": float(last["pe_ttm"]) if pd.notna(last["pe_ttm"]) else None,
            "pe_static": float(last["pe_static"]) if pd.notna(last["pe_static"]) else None,
            "pb": float(last["pb"]) if pd.notna(last["pb"]) else None,
            "pe_ttm_pct": pct(hist, last["pe_ttm"]),
            "pb_pct": pct(hist_pb, last["pb"]),
            "pe_static_pct": pct(grp.dropna(subset=["pe_static"])["pe_static"], last["pe_static"]),
            "history_rows": len(grp),
            "source": last["source"],
        })
    return pd.DataFrame(out_rows)


def get_index_history(code: str) -> pd.DataFrame:
    """返回单只指数的全部历史,空表返回空 DataFrame。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT trade_date, close, pe_ttm, pe_static, pb "
            "FROM index_valuation WHERE code=? ORDER BY trade_date",
            (code,),
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["trade_date", "close", "pe_ttm", "pe_static", "pb"])
    df = pd.DataFrame(rows, columns=["trade_date", "close", "pe_ttm", "pe_static", "pb"])
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


def get_index_valuation_done() -> dict | None:
    """读取最近一次指数估值采集的完成标记(用于侧栏显示时间)。"""
    import json
    from pathlib import Path
    p = Path(config.DB_PATH).parent / "index_valuation_done.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def get_industry_done() -> dict | None:
    """读取最近一次行业轮动采集的完成标记(用于侧栏显示时间)。"""
    import json
    from pathlib import Path
    p = Path(config.DB_PATH).parent / "industry_done.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
