# -*- coding: utf-8 -*-
"""模拟交易模块：分配器 / 模拟下单 / 持仓 / 网格交易 / 流水"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import live
import llm
import storage
from ui_theme import apply_theme

st.set_page_config(
    page_title="模拟交易 · 工具台",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()

st.markdown(
    """
<div style="font-size:1.7rem;font-weight:800;letter-spacing:-0.02em;">💼 模拟交易</div>
<div style="color:var(--muted);font-size:0.9rem;margin-bottom:1rem;">
  资金分配器 · 模拟下单 · 持仓跟踪 · 网格策略 · 流水记录（全部落库，刷新/重启不丢）
</div>
""",
    unsafe_allow_html=True,
)

storage.init_db()
etf_list = storage.load_etf_list()
if etf_list.empty:
    st.warning("暂无 ETF 数据，请先运行 `python collector/update.py`")
    st.stop()

name_map = dict(zip(etf_list["code"], etf_list["name"]))

# 库内收盘价（兜底基线）
_latest = storage.load_all_latest_quotes(etf_list["code"].tolist())
_db_price_map = dict(zip(_latest["code"], _latest["close"])) if not _latest.empty else {}

LIVE_TTL = 8          # 实时报价缓存秒数（下限，实际刷新由 fragment 定时器驱动）
DB_CLOSE_DATE = storage.get_meta("quotes_updated_at", "")[:10] or "-"

# ---------- 实时行情 ----------
if "use_live" not in st.session_state:
    st.session_state["use_live"] = True
if "live_every" not in st.session_state:
    st.session_state["live_every"] = 15


def _relevant_codes() -> list[str]:
    """需要实时价的代码：持仓 + 网格 + 表单当前选中。

    只取这几只而不是全市场 1621 只——全市场快照要 18~20 秒，这些通常不到 10 只，1 秒内返回。
    """
    codes: set[str] = set()
    h = storage.load_holdings()
    if not h.empty:
        codes |= set(h["code"].astype(str))
    g = storage.load_grids()
    if not g.empty:
        codes |= set(g["code"].astype(str))
    for k in ("buy_code", "sell_code", "g_code"):
        v = st.session_state.get(k)
        if v:
            codes.add(str(v))
    return sorted(codes)


@st.cache_data(ttl=LIVE_TTL, show_spinner=False)
def _live_quotes(codes: tuple[str, ...]) -> pd.DataFrame:
    return live.fetch_quotes(codes)


def _price_ctx() -> tuple[dict, pd.DataFrame]:
    """返回 (price_map, live_df)。

    price_map 优先用实时价，拿不到的代码回落到库内收盘价，保证界面永远有价可用。
    """
    pm = dict(_db_price_map)
    if not st.session_state.get("use_live", True):
        return pm, pd.DataFrame(columns=live.RESULT_COLUMNS)
    codes = tuple(_relevant_codes())
    if not codes:
        return pm, pd.DataFrame(columns=live.RESULT_COLUMNS)
    ldf = _live_quotes(codes)
    if not ldf.empty:
        pm.update(dict(zip(ldf["code"], ldf["price"].astype(float))))
    return pm, ldf


def _quote_info(code: str) -> dict | None:
    """取单只标的的实时报价（含涨跌幅），无实时数据返回 None。"""
    _, ldf = _price_ctx()
    if ldf.empty:
        return None
    row = ldf[ldf["code"] == str(code)]
    return row.iloc[0].to_dict() if not row.empty else None


price_map, live_df = _price_ctx()

# ---------- 实时行情控制条 ----------
_phase_text, _is_trading_now = live.market_phase()
_quote_ts = live.latest_quote_time(live_df)
_market_open = st.session_state.get("use_live", True)
_fresh = live.is_quote_fresh(_quote_ts, max_age_sec=300)

st.markdown("##### 📡 行情源")
lb1, lb2, lb3, lb4 = st.columns([1, 1, 1, 1.4])
with lb1:
    st.toggle(
        "实时行情", key="use_live",
        help="开启后盘中价格自动刷新；关闭则使用库内最近收盘价",
    )
with lb2:
    st.selectbox(
        "自动刷新间隔", [15, 30, 60, 0], key="live_every",
        format_func=lambda x: "关闭" if x == 0 else f"{x} 秒",
        help="仅刷新只读区域（账户快照 / 持仓 / 网格档位），下单表单不会被重置",
    )
with lb3:
    st.write("")
    if st.button("🔄 立即刷新", width="content"):
        _live_quotes.clear()
        st.rerun()
with lb4:
    if not _market_open:
        _dot, _txt, _tone = "#94a3b8", f"库内收盘价（{DB_CLOSE_DATE}）", "muted"
    elif _fresh:
        _dot, _txt, _tone = "#16a34a", f"实时 · {_quote_ts:%H:%M:%S}", "up"
    elif _quote_ts is not None:
        _dot, _txt, _tone = "#f59e0b", f"行情停更 · {_quote_ts:%m-%d %H:%M}", "flat"
    else:
        _dot, _txt, _tone = "#dc2626", "实时行情获取失败，已回落收盘价", "down"

    st.markdown(
        f'<div style="background:var(--bg-card);border:1px solid var(--border);'
        f'border-radius:8px;padding:8px 12px;margin-top:2px;display:flex;'
        f'align-items:center;gap:10px;white-space:nowrap;">'
        f'<span style="width:8px;height:8px;border-radius:50%;background:{_dot};'
        f'flex:0 0 8px;"></span>'
        f'<span style="color:var(--muted);font-size:0.85rem;">{_phase_text}</span>'
        f'<span class="{_tone}" style="font-size:0.85rem;font-weight:600;">{_txt}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

# 自动刷新间隔：0 = 关闭，None 让 fragment 不挂定时器
_REFRESH_EVERY = None
if _market_open and st.session_state.get("live_every"):
    _REFRESH_EVERY = f"{st.session_state['live_every']}s"

# ---------- 账户设置 ----------
if "init_amt" not in st.session_state:
    st.session_state["init_amt"] = float(storage.get_setting("init_amount", "100000") or 100000)
if "fee_rate" not in st.session_state:
    st.session_state["fee_rate"] = float(storage.get_setting("fee_rate", "0.0001") or 0.0001)
if "min_lot" not in st.session_state:
    st.session_state["min_lot"] = int(float(storage.get_setting("min_lot", "100") or 100))

st.markdown("##### ⚙️ 账户设置")
sa, sb, sc = st.columns(3)
with sa:
    init_amt = st.number_input(
        "虚拟资金池（元）", min_value=1000.0,
        value=st.session_state["init_amt"], step=10000.0,
    )
with sb:
    fee_rate = st.number_input(
        "佣金率（双边）", min_value=0.0, max_value=0.01,
        value=st.session_state["fee_rate"], step=0.0001, format="%.4f",
    )
with sc:
    min_lot = st.number_input(
        "最小取整份数", min_value=1,
        value=st.session_state["min_lot"], step=100,
    )

if st.button("💾 保存设置", width="content"):
    storage.set_setting("init_amount", str(init_amt))
    storage.set_setting("fee_rate", str(fee_rate))
    storage.set_setting("min_lot", str(min_lot))
    st.session_state["init_amt"] = init_amt
    st.session_state["fee_rate"] = fee_rate
    st.session_state["min_lot"] = min_lot
    st.toast("已保存", icon="✅")

# ---------- 持仓概览 ----------
def _compute_overview(pm: dict, base_capital: float) -> tuple[pd.DataFrame, dict]:
    """按给定价格表重算持仓明细与账户汇总。

    抽成函数是为了让自动刷新区域能用自己的（更新的）价格表重算，
    而不依赖页面级那份可能已过时的 price_map。
    """
    h = storage.load_holdings()
    if h.empty:
        return pd.DataFrame(), {
            "total_mv": 0.0, "total_cost": 0.0, "total_unrealized": 0.0,
            "total_realized": 0.0, "cash_left": base_capital,
            "total_equity": base_capital, "total_pnl": 0.0,
        }

    v = h.copy()
    v["last_price"] = v["code"].map(pm).fillna(v["avg_cost"])
    v["market_value"] = v["shares"] * v["last_price"]
    v["cost_value"] = v["shares"] * v["avg_cost"]
    v["unrealized"] = v["shares"] * (v["last_price"] - v["avg_cost"])
    v["unrealized_pct"] = (
        v["unrealized"] / v["cost_value"].replace(0, pd.NA) * 100
    ).fillna(0)

    t_mv = float(v["market_value"].sum())
    t_cost = float(v["cost_value"].sum())
    t_unreal = float(v["unrealized"].sum())
    t_real = float(h["realized_pnl"].sum())
    cash = max(base_capital - t_cost, 0.0)
    return v, {
        "total_mv": t_mv, "total_cost": t_cost, "total_unrealized": t_unreal,
        "total_realized": t_real, "cash_left": cash,
        "total_equity": cash + t_mv, "total_pnl": t_unreal + t_real,
    }


holdings = storage.load_holdings()
tx_count = len(storage.load_transactions(limit=10000))
hv, _ov = _compute_overview(price_map, init_amt)
total_mv = _ov["total_mv"]
total_cost = _ov["total_cost"]
total_unrealized = _ov["total_unrealized"]
total_realized = _ov["total_realized"]
cash_left = _ov["cash_left"]
total_equity = _ov["total_equity"]
total_pnl = _ov["total_pnl"]


def _kpi(label, value, sub=None, tone="text"):
    sub_html = (
        f'<div style="color:var(--muted);font-size:0.75rem;margin-top:4px;">{sub}</div>'
        if sub else ""
    )
    return (
        f'<div style="background:var(--bg-card);border:1px solid var(--border);'
        f'border-radius:10px;padding:14px 16px;height:96px;">'
        f'<div style="color:var(--muted);font-size:0.85rem;">{label}</div>'
        f'<div style="color:var(--{tone});font-size:1.5rem;font-weight:700;line-height:1.2;">{value}</div>'
        f"{sub_html}</div>"
    )


tab_overview, tab_trade, tab_grid, tab_log, tab_ai = st.tabs([
    "📊 总览", "🛒 模拟下单", "📐 网格交易", "📜 流水", "🤖 AI 复盘",
])

@st.fragment(run_every=_REFRESH_EVERY)
def _overview_fragment() -> None:
    """账户快照 + 持仓表（自动刷新区域）。

    这里自行调用 ``_price_ctx()`` 取最新价，而不是复用页面级 price_map——
    因为 fragment 定时重跑时，页面级代码不会重新执行，那份价格是旧的。
    """
    pm, ldf = _price_ctx()
    h_now = storage.load_holdings()
    v_now, ov = _compute_overview(pm, init_amt)
    n_tx = len(storage.load_transactions(limit=10000))

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            _kpi("总资产", f"¥{ov['total_equity']:,.0f}", f"现金 ¥{ov['cash_left']:,.0f}"),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            _kpi("持仓市值", f"¥{ov['total_mv']:,.0f}", f"成本 ¥{ov['total_cost']:,.0f}"),
            unsafe_allow_html=True,
        )
    tone = "up" if ov["total_pnl"] >= 0 else "down"
    sign = "+" if ov["total_pnl"] >= 0 else ""
    with k3:
        st.markdown(
            _kpi("累计盈亏", f"{sign}¥{ov['total_pnl']:,.0f}",
                 f"已实现 {sign}¥{ov['total_realized']:,.0f}", tone),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            _kpi("持仓数 / 成交笔数", f"{len(h_now)} / {n_tx}"),
            unsafe_allow_html=True,
        )

    st.markdown("&nbsp;")
    st.markdown("##### 当前持仓")

    if v_now.empty:
        st.info("暂无持仓，去 **🛒 模拟下单** 开仓。")
    else:
        show = v_now[[
            "code", "name", "shares", "avg_cost", "last_price",
            "market_value", "cost_value", "unrealized", "unrealized_pct",
            "realized_pnl",
        ]].copy()
        show.columns = [
            "代码", "名称", "持仓份额", "成本价", "现价",
            "市值¥", "成本¥", "浮动盈亏¥", "浮动盈亏%", "已实现盈亏¥",
        ]
        st.dataframe(
            show.set_index("代码"), width="stretch",
            column_config={
                "持仓份额": st.column_config.NumberColumn(format="%d"),
                "成本价": st.column_config.NumberColumn(format="%.4f"),
                "现价": st.column_config.NumberColumn(format="%.4f"),
                "市值¥": st.column_config.NumberColumn(format="¥%d"),
                "成本¥": st.column_config.NumberColumn(format="¥%d"),
                "浮动盈亏¥": st.column_config.NumberColumn(format="%+.2f"),
                "浮动盈亏%": st.column_config.NumberColumn(format="%+.2f%%"),
                "已实现盈亏¥": st.column_config.NumberColumn(format="%+.2f"),
            },
        )
        csv = show.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 导出持仓 CSV", data=csv,
            file_name=f"holdings_{pd.Timestamp.now():%Y%m%d}.csv",
            mime="text/csv",
        )

    # 现价来源 + 更新时间（让用户一眼看出是不是实时）
    _ts = live.latest_quote_time(ldf)
    if not ldf.empty and _ts is not None:
        st.caption(f"现价：**实时行情** · 数据时间 {_ts:%H:%M:%S} · 自动刷新 {st.session_state.get('live_every') or '关'} 秒")
    elif st.session_state.get("use_live", True):
        st.caption(f"现价：实时行情暂不可用，回落至**库内收盘价**（{DB_CLOSE_DATE}）")
    else:
        st.caption(f"现价：**库内收盘价**（{DB_CLOSE_DATE}）· 实时行情已关闭")


# ====================== 总览 ======================
with tab_overview:
    _overview_fragment()

    # 删除持仓放在 fragment 外：这是写操作，不需要（也不应）被定时刷新打扰
    if not holdings.empty:
        with st.expander("🗑️ 删除某标的的全部记录（清空持仓+成交）"):
            del_code = st.selectbox(
                "选择 ETF", sorted(holdings["code"].tolist()),
                key="del_holding_code",
                format_func=lambda c: f"{c} {name_map.get(c, '')}",
            )
            if st.button("⚠️ 确认删除（不可恢复）", type="primary", key="btn_del_holding"):
                storage.delete_holding(del_code)
                st.toast(f"已删除 {del_code} 全部记录", icon="✅")
                st.rerun()

# ====================== 资金分配器 ======================
# --- 资金分配器（原 tab_alloc 合并进来）---
with tab_trade:
    st.markdown("##### ① 输入参数")
    c1, c2 = st.columns([1, 2])
    with c1:
        total = st.number_input(
            "本次配置金额（元）", min_value=1000.0, value=10000.0,
            step=500.0, key="alloc_total",
        )
    with c2:
        codes = st.multiselect(
            "选择 ETF（建议 2-4 只）",
            sorted(etf_list["code"].tolist()), default=[],
            format_func=lambda c: f"{c} {name_map.get(c, '')}",
            key="alloc_codes",
        )

    if not codes:
        st.info("👆 先从上方选择要配置的 ETF（2-4 只为佳）")
    else:
        st.markdown("##### ② 权重设置")
        mode = st.radio("策略", ["等权", "手动调整"], horizontal=True,
                        key="alloc_mode", label_visibility="collapsed")
        weights = {}
        if mode == "等权":
            w = 1.0 / len(codes)
            for c in codes:
                weights[c] = w
            chips = " ".join(
                f'<span style="background:var(--bg-soft);border:1px solid var(--border);'
                f'padding:4px 10px;border-radius:6px;font-size:0.85rem;margin-right:6px;">'
                f'{name_map.get(c, c)} <b>{w*100:.1f}%</b></span>'
                for c in codes
            )
            st.markdown(f'<div style="margin:8px 0 4px 0;">{chips}</div>',
                        unsafe_allow_html=True)
        else:
            cols = st.columns(len(codes))
            for i, c in enumerate(codes):
                with cols[i]:
                    weights[c] = st.slider(
                        f"{name_map.get(c, c)}", 0, 100,
                        int(100 / len(codes)), 5, key=f"alloc_w_{c}",
                    ) / 100
            s = sum(weights.values())
            if s <= 0:
                st.warning("权重全为 0")
            elif abs(s - 1.0) > 0.001:
                st.warning(f"权重合计 {s*100:.0f}%，将按比例归一化")
                weights = {c: v / s for c, v in weights.items()}

        rows = []
        for c in codes:
            p = price_map.get(c)
            if p is None or pd.isna(p):
                rows.append({"code": c, "name": name_map.get(c, c), "price": None})
                continue
            target_amt = total * weights[c]
            lots = math.floor(target_amt / p / min_lot) * min_lot
            rows.append({
                "code": c, "name": name_map.get(c, c), "price": p,
                "weight": weights[c], "target_amt": target_amt,
                "lots": lots, "actual_amt": lots * p,
            })
        df = pd.DataFrame(rows)
        missing = df[df["price"].isna()]
        if not missing.empty:
            st.warning("以下标的缺少收盘价，已跳过：" + "、".join(missing["code"]))
            df = df[df["price"].notna()]

        if df.empty:
            st.info("没有可计算的标的")
        else:
            invested = df["actual_amt"].sum()
            cash_left_a = total - invested
            df["actual_weight"] = df["actual_amt"] / (total if total else 1)
            df["drift"] = df["actual_weight"] - df["weight"]
            max_drift = df["drift"].abs().max()
            drift_ok = max_drift <= config.DRIFT_ALERT

            st.markdown("##### ③ 执行摘要")
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.markdown(_kpi("本次金额", f"¥{total:,.0f}"), unsafe_allow_html=True)
            with m2:
                st.markdown(
                    _kpi("投入金额", f"¥{invested:,.0f}",
                         f"动用率 {invested/total*100:.1f}%"),
                    unsafe_allow_html=True,
                )
            with m3:
                tone = "down" if cash_left_a > total * 0.1 else "text"
                st.markdown(
                    _kpi("剩余零钱", f"¥{cash_left_a:,.0f}", "未取整", tone),
                    unsafe_allow_html=True,
                )
            with m4:
                tone = "up" if drift_ok else "down"
                st.markdown(
                    _kpi("最大权重偏离", f"{max_drift*100:.1f}%",
                         "达标" if drift_ok else f"超 {config.DRIFT_ALERT*100:.0f}% 阈值", tone),
                    unsafe_allow_html=True,
                )

            st.markdown("&nbsp;")
            st.markdown(f"##### ④ 买入清单（按 {min_lot} 份/手取整）")
            show = df.rename(columns={
                "code": "代码", "name": "名称", "price": "收盘价",
                "weight": "目标权重", "target_amt": "目标金额",
                "lots": "买入份额", "actual_amt": "实际金额",
                "actual_weight": "实际权重", "drift": "偏离",
            })
            show["目标权重%"] = (show["目标权重"] * 100).round(2)
            show["实际权重%"] = (show["实际权重"] * 100).round(2)
            show["偏离%"] = (show["偏离"] * 100).round(2)
            show["目标金额¥"] = show["目标金额"].round(0)
            show["实际金额¥"] = show["实际金额"].round(0)
            st.dataframe(
                show[["代码", "名称", "收盘价", "目标权重%", "目标金额¥",
                      "买入份额", "实际金额¥", "实际权重%", "偏离%"]].set_index("代码"),
                width="stretch",
                column_config={
                    "收盘价": st.column_config.NumberColumn(format="%.4f"),
                    "目标权重%": st.column_config.NumberColumn(format="%.2f%%"),
                    "实际权重%": st.column_config.NumberColumn(format="%.2f%%"),
                    "偏离%": st.column_config.NumberColumn(format="%+.2f%%"),
                    "目标金额¥": st.column_config.NumberColumn(format="¥%d"),
                    "实际金额¥": st.column_config.NumberColumn(format="¥%d"),
                    "买入份额": st.column_config.NumberColumn(format=f"%d 份"),
                },
            )

            st.markdown("&nbsp;")
            st.markdown("##### ⑤ 一键模拟买入")
            ac1, ac2 = st.columns([1, 3])
            with ac1:
                confirm = st.checkbox("确认按上述清单成交（不可撤销）", key="alloc_confirm")
            with ac2:
                if st.button(
                    "⚡ 一键模拟买入", type="primary",
                    disabled=not confirm or df.empty, width="stretch",
                ):
                    ok, fail = 0, 0
                    for _, r in df.iterrows():
                        if r["lots"] <= 0 or pd.isna(r["price"]):
                            continue
                        try:
                            storage.record_trade(
                                code=r["code"], name=r["name"], side="BUY",
                                price=float(r["price"]), shares=int(r["lots"]),
                                fee=0.0, note="资金分配器一键下单",
                            )
                            ok += 1
                        except Exception as e:
                            fail += 1
                            st.error(f"{r['code']} 失败：{e}")
                    st.toast(f"买入完成：成功 {ok} / 失败 {fail}", icon="✅")
                    st.rerun()

            csv = show[["代码", "名称", "收盘价", "目标权重%", "目标金额¥",
                        "买入份额", "实际金额¥", "实际权重%", "偏离%"]].to_csv(
                index=False).encode("utf-8-sig")
            st.download_button(
                "📥 导出清单 CSV", data=csv,
                file_name=f"etf_allocation_{pd.Timestamp.now():%Y%m%d}.csv",
                mime="text/csv",
            )

# ====================== 模拟下单 ======================

# === 单笔模拟成交（tab_trade 原有内容）===
with tab_trade:
    st.markdown("##### 🛒 单笔模拟成交")
    st.caption("上方是「资金分配器」批量配置 → 下方是单笔 BUY/SELL")
    bcol, scol = st.columns(2)
    with bcol:
        st.markdown("**🟥 买入**")
        bc1, bc2 = st.columns([2, 1])
        with bc1:
            buy_code = st.selectbox(
                "ETF", sorted(etf_list["code"].tolist()),
                key="buy_code",
                format_func=lambda c: f"{c} {name_map.get(c, '')}",
            )
        with bc2:
            cp_raw = price_map.get(buy_code)
            cp = None if cp_raw is None or pd.isna(cp_raw) else float(cp_raw)
            _qi = _quote_info(buy_code)
            if _qi is not None:
                # A 股惯例：涨=红。st.metric 默认「涨绿」，所以要 inverse
                st.metric(
                    "最新价", f"¥{_qi['price']:.4f}",
                    delta=f"{_qi['chg_pct']:+.2f}%", delta_color="inverse",
                )
            else:
                st.metric("最新价（收盘）", f"¥{cp:.4f}" if cp else "—")

        bp1, bp2, bp3 = st.columns(3)
        with bp1:
            # key 绑定标的代码：切换 ETF 时控件重建，成交价自动填入该标的最新价
            # 「待生效」标记：button 回调里只能设标记，下次 rerun 时推给 widget
            _buy_pending = st.session_state.pop(f"_next_buy_price_{buy_code}", None)
            if _buy_pending is not None:
                st.session_state[f"buy_price_{buy_code}"] = _buy_pending
            buy_price = st.number_input(
                "成交价（自动取最新价）", min_value=0.0,
                value=cp if cp else 1.0,
                step=0.001, format="%.4f",
                key=f"buy_price_{buy_code}",
            )
            if st.button("↻ 填入最新价", key="btn_fill_buy", width="content",
                         disabled=cp is None,
                         help="把上方最新价填入成交价（成交价默认只在切换标的时自动更新）"):
                st.session_state[f"_next_buy_price_{buy_code}"] = float(cp)
                st.rerun()
        with bp2:
            raw = st.number_input(
                "份数（≥100）", min_value=0, value=100, step=100, key="buy_shares_raw",
            )
            buy_shares = int(raw // min_lot) * min_lot
        with bp3:
            buy_amt = buy_price * buy_shares
            buy_fee = buy_amt * fee_rate
            st.metric("金额", f"¥{buy_amt:,.2f}", delta=f"费 ¥{buy_fee:.2f}", delta_color="off")

        buy_note = st.text_input("备注（可选）", key="buy_note")
        if st.button("🟥 确认买入", type="primary", key="btn_buy",
                     disabled=buy_shares <= 0 or buy_price <= 0,
                     width="stretch"):
            try:
                storage.record_trade(
                    code=buy_code, name=name_map.get(buy_code, buy_code),
                    side="BUY", price=buy_price, shares=buy_shares,
                    fee=buy_amt * fee_rate, note=buy_note,
                )
                st.toast(f"已买入 {buy_code} × {buy_shares}", icon="✅")
                st.rerun()
            except Exception as e:
                st.error(f"失败：{e}")

    with scol:
        st.markdown("**🟩 卖出**")
        hold_codes = holdings["code"].tolist() if not holdings.empty else []
        if not hold_codes:
            st.info("暂无可卖出的持仓")
        else:
            sc1, sc2 = st.columns([2, 1])
            with sc1:
                sell_code = st.selectbox(
                    "ETF", hold_codes, key="sell_code",
                    format_func=lambda c: f"{c} {name_map.get(c, '')}",
                )
            with sc2:
                cur_hold = holdings[holdings["code"] == sell_code].iloc[0]
                sp_raw = price_map.get(sell_code)
                cur_price_sell = (
                    None if sp_raw is None or pd.isna(sp_raw) else float(sp_raw)
                )
                # 无最新价时退回持仓成本价，保证有合理默认值
                if cur_price_sell is None:
                    cur_price_sell = float(cur_hold["avg_cost"])
                _qi_s = _quote_info(sell_code)
                if _qi_s is not None:
                    _pnl = (float(_qi_s["price"]) - float(cur_hold["avg_cost"])) * float(cur_hold["shares"])
                    st.metric(
                        "最新价", f"¥{_qi_s['price']:.4f}",
                        delta=f"{_qi_s['chg_pct']:+.2f}%", delta_color="inverse",
                        help=f"持仓浮动盈亏 ¥{_pnl:+,.0f}",
                    )
                else:
                    st.metric("最新价（收盘）", f"¥{cur_price_sell:.4f}")

            sp1, sp2, sp3 = st.columns(3)
            with sp1:
                # key 绑定标的代码：切换持仓标的时自动填入该标的最新价
                _sell_pending = st.session_state.pop(f"_next_sell_price_{sell_code}", None)
                if _sell_pending is not None:
                    st.session_state[f"sell_price_{sell_code}"] = _sell_pending
                sell_price = st.number_input(
                    "成交价（自动取最新价）", min_value=0.0,
                    value=cur_price_sell,
                    step=0.001, format="%.4f",
                    key=f"sell_price_{sell_code}",
                )
                if st.button("↻ 填入最新价", key="btn_fill_sell", width="content",
                             disabled=cur_price_sell is None,
                             help="把上方最新价填入成交价"):
                    st.session_state[f"_next_sell_price_{sell_code}"] = float(cur_price_sell)
                    st.rerun()
            with sp2:
                # 默认全额卖出该标的持仓，且随标的切换重置
                sraw = st.number_input(
                    "份数", min_value=0, value=int(cur_hold["shares"]),
                    step=min_lot, key=f"sell_shares_raw_{sell_code}",
                )
                sell_shares = int(sraw // min_lot) * min_lot
            with sp3:
                sell_amt = sell_price * sell_shares
                sell_fee = sell_amt * fee_rate
                st.metric("金额", f"¥{sell_amt:,.2f}",
                          delta=f"费 ¥{sell_fee:.2f}", delta_color="off")

            sell_note = st.text_input("备注（可选）", key="sell_note")
            if st.button("🟩 确认卖出", key="btn_sell",
                         disabled=sell_shares <= 0 or sell_price <= 0,
                         width="stretch"):
                try:
                    storage.record_trade(
                        code=sell_code, name=name_map.get(sell_code, sell_code),
                        side="SELL", price=sell_price, shares=sell_shares,
                        fee=sell_amt * fee_rate, note=sell_note,
                    )
                    st.toast(f"已卖出 {sell_code} × {sell_shares}", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"失败：{e}")

# ====================== 网格交易 ======================
with tab_grid:
    st.markdown("##### 📐 什么是网格交易？")
    st.markdown(
        '<div style="background:var(--bg-card);border:1px solid var(--border);'
        'border-radius:10px;padding:14px 18px;color:var(--muted);font-size:0.9rem;">'
        '设定一个 <b>中心价</b> 和 <b>上下边界</b>，按等比步长（如 2%）拆成多档：<br>'
        '• 下跌触及档位 → 自动按该价<b>买入</b>一份<br>'
        '• 上涨触及档位 → 自动按该价<b>卖出</b>一份（赚一格差价）<br>'
        '低吸高抛，反复收割波动，适合震荡市。'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("&nbsp;")
    st.markdown("##### ① 创建网格")
    gc1, gc2, gc3 = st.columns(3)
    with gc1:
        g_code = st.selectbox(
            "ETF", sorted(etf_list["code"].tolist()),
            key="g_code",
            format_func=lambda c: f"{c} {name_map.get(c, '')}",
        )
        gc_raw = price_map.get(g_code)
        g_cp = 0.0 if gc_raw is None or pd.isna(gc_raw) else float(gc_raw)
        # key 绑定标的代码：切换 ETF 时中心价自动填入该标的最新价
        g_center = st.number_input(
            "中心价（自动取最新价）", min_value=0.0,
            value=g_cp if g_cp else 1.0,
            step=0.001, format="%.4f",
            key=f"g_center_{g_code}",
        )
    with gc2:
        g_step = st.number_input(
            "网格步长 %", min_value=0.1, max_value=20.0, value=2.0, step=0.1, key="g_step",
        )
        g_per = st.number_input(
            "每格份数", min_value=min_lot, value=min_lot,
            step=min_lot, key="g_per",
        )
    with gc3:
        half = g_center * 0.20
        # 上下界同样绑定标的：切换 ETF 时按新中心价 ±20% 重置
        g_upper = st.number_input(
            "上界价", min_value=0.0,
            value=float(round(g_center + half, 4)), step=0.01, format="%.4f",
            key=f"g_upper_{g_code}",
        )
        g_lower = st.number_input(
            "下界价", min_value=0.0,
            value=float(round(g_center - half, 4)), step=0.01, format="%.4f",
            key=f"g_lower_{g_code}",
        )

    g_note = st.text_input("备注（可选）", key="g_note")
    if st.button("📐 创建网格", type="primary", width="content"):
        if g_upper <= g_center or g_lower >= g_center or g_upper <= g_lower:
            st.error("价格区间必须：下界 < 中心 < 上界")
        else:
            gid = storage.create_grid(
                code=g_code, name=name_map.get(g_code, g_code),
                center=g_center, upper=g_upper, lower=g_lower,
                step_pct=g_step, per_grid_shares=int(g_per), note=g_note,
            )
            st.toast(f"网格已创建 #{gid}", icon="✅")
            st.rerun()

    st.markdown("&nbsp;")
    st.markdown("##### ② 我的网格")
    grids = storage.load_grids()

    @st.fragment(run_every=_REFRESH_EVERY)
    def _grids_overview() -> None:
        """网格概览表 + 现价/浮动盈亏（自动刷新区）。

        与账户总览一样，fragment 内自取一份新鲜 price_map，
        不复用页面级那份以避免显示陈旧价格。
        """
        pm, ldf = _price_ctx()
        g2 = storage.load_grids()
        if g2.empty:
            st.info("还没有网格")
            return
        view = g2.copy()
        view["last_price"] = view["code"].map(pm)
        view["position"] = view["total_invested"] - view["total_shares"] * view["center_price"]
        view["unrealized"] = view["total_shares"] * (
            view["last_price"].fillna(view["center_price"]) - view["center_price"]
        )
        st.dataframe(
            view[[
                "id", "code", "name", "center_price", "upper_price", "lower_price",
                "grid_step_pct", "per_grid_shares", "status",
                "total_invested", "total_shares", "realized_pnl", "unrealized", "created_at",
            ]].rename(columns={
                "id": "#", "code": "代码", "name": "名称",
                "center_price": "中心价", "upper_price": "上界", "lower_price": "下界",
                "grid_step_pct": "步长%", "per_grid_shares": "每格份数",
                "status": "状态", "total_invested": "累计投入", "total_shares": "持仓份数",
                "realized_pnl": "已实现", "unrealized": "浮动盈亏", "created_at": "创建于",
            }).set_index("#"),
            width="stretch",
            column_config={
                "中心价": st.column_config.NumberColumn(format="%.4f"),
                "上界": st.column_config.NumberColumn(format="%.4f"),
                "下界": st.column_config.NumberColumn(format="%.4f"),
                "步长%": st.column_config.NumberColumn(format="%.1f%%"),
                "累计投入": st.column_config.NumberColumn(format="¥%.2f"),
                "已实现": st.column_config.NumberColumn(format="%+.2f"),
                "浮动盈亏": st.column_config.NumberColumn(format="%+.2f"),
                "创建于": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
            },
        )
        _ts = live.latest_quote_time(ldf)
        if not ldf.empty and _ts is not None:
            st.caption(f"现价：**实时行情** · 数据时间 {_ts:%H:%M:%S}")
        elif st.session_state.get("use_live", True):
            st.caption(f"现价：实时行情暂不可用，回落至**库内收盘价**（{DB_CLOSE_DATE}）")
        else:
            st.caption(f"现价：**库内收盘价**（{DB_CLOSE_DATE}）· 实时行情已关闭")

    _grids_overview()

    if not grids.empty:
        st.markdown("&nbsp;")
        st.markdown("##### ③ 查看 / 操作单个网格")
        gsel = st.selectbox(
            "选择网格", grids["id"].tolist(), key="gsel",
            format_func=lambda i: (
                f"#{i} · {grids[grids['id']==i].iloc[0]['code']} "
                f"{grids[grids['id']==i].iloc[0]['name']} · "
                f"中心 {grids[grids['id']==i].iloc[0]['center_price']:.4f} · "
                f"{grids[grids['id']==i].iloc[0]['status']}"
            ),
        )
    else:
        gsel = None

    if gsel:
        @st.fragment(run_every=_REFRESH_EVERY)
        def _grid_detail(gsel_id: int) -> None:
            """单网格详情：KPI / 档位判断 / 手动成交价默认 = 实时价。

            这部分是网格 tab 的"实时行情核心"——档位的买/卖/持标号
            必须在每次 fragment 重跑时根据最新实时价重算。
            """
            pm, _ldf = _price_ctx()
            g = storage.get_grid(gsel_id)
            cols_grid = storage.grid_grid_columns(gsel_id)
            gtr = storage.load_grid_trades(gsel_id)

            gcol1, gcol2, gcol3, gcol4 = st.columns(4)
            with gcol1:
                st.metric("中心价", f"¥{g['center_price']:.4f}")
            with gcol2:
                lp = pm.get(g["code"], g["center_price"])
                st.metric("最新价", f"¥{lp:.4f}" if lp else "—")
            with gcol3:
                st.metric("累计投入", f"¥{g['total_invested']:.2f}")
            with gcol4:
                st.metric("已实现盈亏", f"¥{g['realized_pnl']:+.2f}")

            st.markdown("&nbsp;")
            st.markdown("**网格档位**（按现价判断该买还是该卖）")
            if not cols_grid:
                st.info("步长过大或区间太窄，未生成档位")
            else:
                lp = pm.get(g["code"])
                action_rows = []
                for r in cols_grid:
                    if lp:
                        if lp <= r["buy_price"]:
                            sigil = "🟥 买"
                        elif lp >= r["sell_price"]:
                            sigil = "🟩 卖"
                        else:
                            sigil = "➖ 持"
                    else:
                        sigil = "—"
                    action_rows.append({
                        "档位": r["level"],
                        "方向": sigil,
                        "买入价": r["buy_price"],
                        "卖出价": r["sell_price"],
                        "份数": g["per_grid_shares"],
                    })
                a_df = pd.DataFrame(action_rows)
                st.dataframe(
                    a_df, width="stretch",
                    column_config={
                        "档位": st.column_config.NumberColumn(format="%+d"),
                        "买入价": st.column_config.NumberColumn(format="%.4f"),
                        "卖出价": st.column_config.NumberColumn(format="%.4f"),
                    },
                )

                # 把当前方向的档位价写进 session_state，
                # 用户切 BUY/SELL 时（下方 radio 块）会推回 number_input。
                if not a_df.empty:
                    if st.session_state.get(f"ms_{gsel_id}", "BUY") == "BUY":
                        _suggested = float(a_df.iloc[0]["买入价"])
                    else:
                        _suggested = float(a_df.iloc[-1]["卖出价"])
                else:
                    _suggested = float(g["center_price"])
                st.session_state[f"_suggested_p_{gsel_id}"] = _suggested

            # 网格成交流水（只读，可放 fragment 内随刷）
            st.markdown("&nbsp;")
            st.markdown("**网格成交记录**")
            if gtr.empty:
                st.info("暂无成交")
            else:
                show = gtr.copy()
                show.columns = ["ID", "网格", "代码", "名称", "方向", "价", "份数", "金额", "档位", "时间"]
                st.dataframe(
                    show.set_index("ID"), width="stretch",
                    column_config={
                        "价": st.column_config.NumberColumn(format="%.4f"),
                        "金额": st.column_config.NumberColumn(format="¥%.2f"),
                        "档位": st.column_config.NumberColumn(format="%+d"),
                        "时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                    },
                )

        _grid_detail(gsel)

        # 手动成交 / 网格管理：写操作，不放进 fragment
        # 关键：通过"切换方向 radio"时立刻用 session_state 里的 _suggested_p_
        # 把建议价推回 number_input，否则用户切了方向后默认价不会更新。
        st.markdown("&nbsp;")
        st.markdown("**手动模拟成交一格**")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            # 切换 BUY/SELL 时只在 _next_mp_ 写「待生效」标记，
            # 真正的 mp_{gsel} 覆写放到 number_input 创建之后。
            _prev_side = st.session_state.get(f"_prev_side_{gsel}")
            manual_side = st.radio("方向", ["BUY", "SELL"], horizontal=True, key=f"ms_{gsel}")
            if _prev_side is not None and _prev_side != manual_side:
                _s = st.session_state.get(f"_suggested_p_{gsel}")
                if _s is not None:
                    st.session_state[f"_next_mp_{gsel}"] = float(_s)
            st.session_state[f"_prev_side_{gsel}"] = manual_side
        with m2:
            _g_now = storage.get_grid(gsel)
            _cols_now = storage.grid_grid_columns(gsel)
            if _cols_now:
                if manual_side == "BUY":
                    _dflt = float(_cols_now[0]["buy_price"])
                else:
                    _dflt = float(_cols_now[-1]["sell_price"])
            else:
                _dflt = float(_g_now["center_price"])
            # 用「待生效」标记实现方向切换时的默认价同步
            _pending = st.session_state.pop(f"_next_mp_{gsel}", None)
            if _pending is not None:
                st.session_state[f"mp_{gsel}"] = _pending
            # 兜底：首次创建时给 _dflt（仅在 session_state 没有 mp_{gsel} 时）
            if f"mp_{gsel}" not in st.session_state:
                st.session_state[f"mp_{gsel}"] = _dflt
            manual_p = st.number_input(
                "成交价", min_value=0.0,
                step=0.001, format="%.4f", key=f"mp_{gsel}",
            )
            if st.button("↻ 填入档位价", key=f"fill_{gsel}", width="content",
                         help="把当前方向的档位价填入成交价"):
                st.session_state[f"_next_mp_{gsel}"] = _dflt
                st.rerun()
        with m3:
            _g_now = storage.get_grid(gsel)
            manual_s = st.number_input(
                "份数", min_value=min_lot, value=int(_g_now["per_grid_shares"]),
                step=min_lot, key=f"msh_{gsel}",
            )
        with m4:
            st.write("")
            if st.button("📥 记录", key=f"mbtn_{gsel}", type="primary"):
                _g_now = storage.get_grid(gsel)
                _cols_now = storage.grid_grid_columns(gsel)
                level = 0
                if _cols_now:
                    for r in _cols_now:
                        if abs(manual_p - r["buy_price"]) < 0.001:
                            level = r["level"]
                            break
                        if abs(manual_p - r["sell_price"]) < 0.001:
                            level = r["level"]
                            break
                storage.record_grid_trade(
                    grid_id=gsel, code=_g_now["code"], name=_g_now["name"],
                    side=manual_side, price=manual_p, shares=int(manual_s),
                    level=level,
                )
                st.toast(f"已记录 {manual_side}", icon="✅")
                st.rerun()

        # 网格管理
        st.markdown("&nbsp;")
        st.markdown("**管理**")
        _g_now = storage.get_grid(gsel)
        mcol1, mcol2, mcol3 = st.columns(3)
        with mcol1:
            if _g_now["status"] == "active":
                if st.button("⏸ 暂停网格", key=f"pause_{gsel}"):
                    storage.update_grid_status(gsel, "paused")
                    st.rerun()
            else:
                if st.button("▶ 恢复网格", key=f"resume_{gsel}"):
                    storage.update_grid_status(gsel, "active")
                    st.rerun()
        with mcol2:
            if st.button("⏹ 关闭网格", key=f"close_{gsel}"):
                storage.update_grid_status(gsel, "closed")
                st.rerun()
        with mcol3:
            if st.button("🗑 删除网格", key=f"delg_{gsel}", type="primary"):
                storage.delete_grid(gsel)
                st.rerun()

# ====================== 流水 ======================
with tab_log:
    st.markdown("##### 全部成交记录")
    fc1, fc2, fc3 = st.columns([2, 1, 1])
    with fc1:
        f_code = st.selectbox(
            "筛选标的", ["全部"] + sorted(holdings["code"].tolist() if not holdings.empty else []),
            key="flt_code", format_func=lambda c: "全部" if c == "全部" else f"{c} {name_map.get(c, '')}",
        )
    with fc2:
        f_type = st.selectbox("方向", ["全部", "BUY", "SELL"], key="flt_type")
    with fc3:
        f_limit = st.selectbox("条数", [50, 100, 200, 500], index=1, key="flt_limit")

    txs = storage.load_transactions(
        code=None if f_code == "全部" else f_code, limit=f_limit
    )
    if txs.empty:
        st.info("暂无成交记录")
    else:
        if f_type != "全部":
            txs = txs[txs["type"] == f_type]
        if txs.empty:
            st.info("该筛选下无记录")
        else:
            txs["amount"] = txs["amount"].round(2)
            txs["fee"] = txs["fee"].round(2)
            show = txs[[
                "id", "ts", "code", "name", "type", "price", "shares", "amount", "fee", "note"
            ]].rename(columns={
                "id": "#", "ts": "时间", "code": "代码", "name": "名称",
                "type": "方向", "price": "价", "shares": "份数",
                "amount": "金额", "fee": "佣金", "note": "备注",
            })
            st.dataframe(
                show.set_index("#"), width="stretch",
                column_config={
                    "时间": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                    "价": st.column_config.NumberColumn(format="%.4f"),
                    "金额": st.column_config.NumberColumn(format="¥%.2f"),
                    "佣金": st.column_config.NumberColumn(format="¥%.2f"),
                },
            )
            st.download_button(
                "📥 导出流水 CSV",
                data=show.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"transactions_{pd.Timestamp.now():%Y%m%d}.csv",
                mime="text/csv",
            )

# ============================================================
# 🤖 AI 复盘 Tab
# ============================================================
def _build_holdings_context() -> str:
    """组装给 LLM 的 context：当前持仓 + 网格 + 近期 K 线。"""
    parts: list[str] = []

    # 1) 持仓
    holdings = storage.load_holdings()
    if not holdings.empty:
        parts.append("## 当前持仓\n" + holdings.to_string(index=False))
    else:
        parts.append("## 当前持仓\n(暂无持仓)")

    # 2) 网格
    grids = storage.load_grids()
    if not grids.empty:
        parts.append("\n## 活跃/暂停网格\n" + grids.to_string(index=False))
    else:
        parts.append("\n## 网格\n(暂无)")

    # 3) 近期流水(最近 10 笔)
    tx = storage.load_transactions(limit=10)
    if not tx.empty:
        parts.append("\n## 最近 10 笔成交\n" + tx.to_string(index=False))

    # 4) 每只持仓 ETF 的近期 K 线(20 日)
    if not holdings.empty:
        for _, h in holdings.iterrows():
            code = h["code"]
            q = storage.load_quotes(code)
            if not q.empty:
                tail = q.tail(20)[["trade_date", "open", "close", "volume"]]
                parts.append(f"\n## {code} 近期 20 日 K 线\n" + tail.to_string(index=False))

    return "\n".join(parts)


with tab_ai:
    st.markdown("##### 🤖 AI 持仓复盘")
    if not llm.is_ready():
        st.warning(
            "⚠️ LLM 未配置或未启用。\n\n"
            "请先到 **⚙️ 设置** 页配置 DeepSeek / OpenAI / 其他 OpenAI 兼容服务。"
        )
        st.markdown(
            '<a href="./设置" target="_self" style="font-size:0.95rem;">→ 打开设置页</a>',
            unsafe_allow_html=True,
        )
    else:
        st.caption(f"模型：{llm.get_config()['model']} · 上下文：持仓 + 网格 + 最近 10 笔成交 + 持仓 ETF 近期 20 日 K 线")
        c1, c2 = st.columns([1, 4])
        with c1:
            run_click = st.button(
                "🚀 生成复盘",
                type="primary", width="stretch", key="ai_run",
            )
        with c2:
            extra_q = st.text_input(
                "（可选）想问的具体问题",
                placeholder="例如：网格档位是不是太密了？",
                key="ai_extra_q",
            )

        # 状态占位区：用户能看到「正在调用 / 成功 / 失败」三种明确状态
        status_box = st.empty()

        ctx = st.session_state.get("ai_ctx")
        last_q = st.session_state.get("ai_last_q", "")

        if run_click or st.session_state.get("ai_auto_run"):
            status_box.info("⏳ AI 思考中…（首次调用需 5-15 秒）")
            st.toast("AI 思考中…", icon="⏳")
            system_prompt = (
                "你是一位严谨的量化投研助手。用户会给你他的模拟持仓、网格配置、"
                "近期成交和近 20 日 K 线。请用中文给出 200-400 字的复盘：\n"
                "1) 持仓结构是否集中（哪只占比过重）\n"
                "2) 网格档位设计是否合理（步长、上界下界）\n"
                "3) 近期操作节奏（最近 10 笔是追涨还是低吸）\n"
                "4) 风险提示（哪些 ETF 近 20 日跌幅大、波动大）\n"
                "5) 给出 2-3 条**可执行**的调整建议\n"
                "风格：直白、不夸大、不预测涨跌。结尾用「——以上仅基于给定数据，不构成投资建议」收尾。"
            )
            user_msg = "以下是我的最新模拟数据，请做复盘：\n\n" + _build_holdings_context()
            if extra_q and extra_q.strip():
                user_msg += f"\n\n我还想问：{extra_q.strip()}"

            _ok = False
            try:
                reply = llm.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.4,
                    max_tokens=1500,
                )
                _used_fallback = False
            except llm._RetryableEmptyResponse:
                # 推理型模型（deepseek-flash/reasoner）把 max_tokens 全花在 reasoning 上、
                # content 0 字 —— 自动用 deepseek-chat 重试一次
                from openai import OpenAI as _OAI
                _cfg = llm.get_config()
                _chat_client = _OAI(api_key=_cfg["api_key"], base_url=_cfg["base_url"])
                _resp = _chat_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.4,
                    max_tokens=1500,
                )
                reply = _resp.choices[0].message.content or ""
                _used_fallback = True
                _ok = bool(reply)
                if not reply:
                    status_box.error(
                        f"❌ 原模型 {_cfg['model']} 把 max_tokens 全部花在 reasoning 上，"
                        f"自动切到 deepseek-chat 后仍返回空内容。请稍后重试或换模型。"
                    )
                    st.toast("AI 复盘失败", icon="❌")
            except Exception as e:  # noqa: BLE001
                import traceback as _tb
                _tb_str = _tb.format_exc()
                status_box.error(f"❌ 调用失败：{e}")
                st.toast("AI 复盘失败", icon="❌")
                with st.expander("🔧 详细错误（点击展开）", expanded=True):
                    st.code(_tb_str, language="python")
                st.session_state["ai_last_error"] = _tb_str
            if _ok:
                st.session_state["ai_last_reply"] = reply
                st.session_state["ai_last_q"] = extra_q
                st.session_state["ai_ctx"] = _build_holdings_context()  # 缓存便于用户看原文
                _hint = "（已自动切到 deepseek-chat）" if _used_fallback else ""
                status_box.success(f"✅ 复盘完成（{len(reply)} 字）{_hint}")
                st.toast("AI 复盘已生成", icon="✅")

        reply = st.session_state.get("ai_last_reply")
        if reply:
            st.markdown("###### 复盘结果")
            st.markdown(
                f"""
<div style="background:var(--bg-card);border:1px solid var(--border);
border-radius:10px;padding:16px 18px;line-height:1.7;white-space:pre-wrap;">
{reply}
</div>
""",
                unsafe_allow_html=True,
            )
            with st.expander("🔍 查看喂给 AI 的原始数据"):
                st.code(st.session_state.get("ai_ctx", ""), language="markdown")
        else:
            # 如果上次调用失败，提示用户，方便排查
            last_err = st.session_state.get("ai_last_error")
            if last_err:
                with st.expander("⚠️ 上次调用失败（点击查看错误）", expanded=False):
                    st.code(last_err, language="python")
                    if st.button("🗑 清除错误", key="ai_clear_err"):
                        st.session_state.pop("ai_last_error", None)
                        st.rerun()
            st.info("👆 点 **🚀 生成复盘** 按钮开始。第一次调用需 5-15 秒（取决于网络和模型）。")

st.caption("⚠️ 本模块为**模拟交易**，所有数据存于 `data/etf.db`（holdings / transactions / grids / grid_trades），刷新或重启均保留。**不构成投资建议**。")
