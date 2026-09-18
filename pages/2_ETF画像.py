# -*- coding: utf-8 -*-
"""单 ETF 画像页：价格走势 + 均线 + 关键指标 + 折溢价"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import charts
import storage
from metrics.indicators import compute_metrics
from ui_theme import apply_theme, color_pct

st.set_page_config(
    page_title="ETF 画像 · 工具台",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)
palette = apply_theme()

st.markdown(
    """
<div style="font-size:1.7rem;font-weight:800;letter-spacing:-0.02em;">📈 单 ETF 画像</div>
<div style="color:var(--muted);font-size:0.9rem;margin-bottom:1rem;">
  价格走势 + 均线系统 + 折溢价快照 + 关键涨跌指标（A 股惯例 <span class="up">红涨</span><span class="muted"> / </span><span class="down">绿跌</span>）
</div>
""",
    unsafe_allow_html=True,
)

storage.init_db()
etf_list = storage.load_etf_list()
if etf_list.empty:
    st.warning("暂无数据，请先运行 `python collector/update.py`")
    st.stop()

# ---------- 选择标的 ----------
sorted_list = etf_list.sort_values("total_mv", ascending=False, na_position="last")
options = {f"{r['code']} {r['name']}": r["code"] for _, r in sorted_list.iterrows()}
c1, c2 = st.columns([3, 1])
with c1:
    sel = st.selectbox("选择 ETF（按规模降序）", sorted(options.keys()))
with c2:
    win = st.radio("走势图区间", ["全部", "近1年", "近6月", "近3月"], horizontal=True)
code = options[sel]

q = storage.load_quotes(code)
if q.empty:
    st.warning(f"{code} 无行情数据（可能未在采集范围内，可用 `python collector/update.py --all` 扩大范围）")
    st.stop()

m = compute_metrics(code, q)
info = etf_list[etf_list["code"] == code].iloc[0]

# ---------- 头部摘要：代码 + 名称 + 大字价格 ----------
price_color_cls = "up" if m["chg_1w"] > 0 else ("down" if m["chg_1w"] < 0 else "flat")
header = (
    f'<div style="background:var(--bg-card);border:1px solid var(--border);'
    f'border-radius:10px;padding:18px 20px;margin:0.5rem 0 1rem 0;">'
    f'<div style="display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;">'
    f'<div>'
    f'<div style="color:var(--muted);font-size:0.85rem;">{code}</div>'
    f'<div style="font-size:1.5rem;font-weight:800;color:var(--text);">{info["name"]}</div>'
    f'</div>'
    f'<div style="margin-left:auto;text-align:right;">'
    f'<div style="color:var(--muted);font-size:0.8rem;">最新收盘</div>'
    f'<div class="{price_color_cls}" style="font-size:2.2rem;font-weight:800;line-height:1.1;">{m["close"]:.3f}</div>'
    f'<div class="{price_color_cls}" style="font-size:0.95rem;">{m["chg_1w"]:+.2f}%（近 1 周）</div>'
    f'</div>'
    f'</div>'
    f'</div>'
)
st.markdown(header, unsafe_allow_html=True)

# ---------- 指标卡：10 个分两行 ----------
def kpi(label, value, sub=None, sub_cls="muted"):
    sub_html = f'<div class="{sub_cls}" style="font-size:0.75rem;margin-top:4px;">{sub}</div>' if sub else ""
    return (
        f'<div style="background:var(--bg-card);border:1px solid var(--border);'
        f'border-radius:10px;padding:12px 14px;">'
        f'<div style="color:var(--muted);font-size:0.8rem;font-weight:500;">{label}</div>'
        f'<div style="color:var(--text);font-size:1.3rem;font-weight:700;line-height:1.2;">{value}</div>'
        f"{sub_html}</div>"
    )


def pct_text(x):
    if x is None or (isinstance(x, float) and x != x):
        return ("-", "muted", "")
    cls = "up" if x > 0 else ("down" if x < 0 else "flat")
    sign = "+" if x > 0 else ""
    return (f"{sign}{x:.2f}%", cls, f"{sign}{x:.2f}%")


# 5 + 5 排布
row1 = st.columns(5)
chg_1m_v, chg_1m_c, chg_1m_s = pct_text(m["chg_1m"])
row1[0].markdown(kpi("近 1 月", chg_1m_v, chg_1m_s, chg_1m_c), unsafe_allow_html=True)
chg_3m_v, chg_3m_c, chg_3m_s = pct_text(m["chg_3m"])
row1[1].markdown(kpi("近 3 月", chg_3m_v, chg_3m_s, chg_3m_c), unsafe_allow_html=True)
ytd_v, ytd_c, ytd_s = pct_text(m["ytd"])
row1[2].markdown(kpi("年初至今", ytd_v, ytd_s, ytd_c), unsafe_allow_html=True)
prem_v = f'{info["premium_rate"]:.2f}%' if pd.notna(info["premium_rate"]) else "-"
prem_c = "up" if pd.notna(info["premium_rate"]) and info["premium_rate"] > 0 else ("down" if pd.notna(info["premium_rate"]) and info["premium_rate"] < 0 else "muted")
prem_s = "溢价" if pd.notna(info["premium_rate"]) and info["premium_rate"] > 0 else ("折价" if pd.notna(info["premium_rate"]) and info["premium_rate"] < 0 else "-")
row1[3].markdown(kpi("折溢价（快照）", prem_v, prem_s, prem_c), unsafe_allow_html=True)
mv_v = f'{info["total_mv"]/1e8:.1f} 亿' if pd.notna(info["total_mv"]) else "-"
row1[4].markdown(kpi("规模", mv_v, "总市值代理", "muted"), unsafe_allow_html=True)

row2 = st.columns(5)
ma20_sub = "价上" if m["above_ma20"] else ("价下" if m["above_ma20"] is False else "-")
ma20_sub_c = "up" if m["above_ma20"] else ("down" if m["above_ma20"] is False else "muted")
row2[0].markdown(kpi("MA20", f'{m["ma20"]:.3f}' if m["ma20"] == m["ma20"] else "-", ma20_sub, ma20_sub_c), unsafe_allow_html=True)
ma60_sub = "价上" if m["above_ma60"] else ("价下" if m["above_ma60"] is False else "-")
ma60_sub_c = "up" if m["above_ma60"] else ("down" if m["above_ma60"] is False else "muted")
row2[1].markdown(kpi("MA60", f'{m["ma60"]:.3f}' if m["ma60"] == m["ma60"] else "-", ma60_sub, ma60_sub_c), unsafe_allow_html=True)
ma200_sub = "价上" if m["above_ma200"] else ("价下" if m["above_ma200"] is False else "-")
ma200_sub_c = "up" if m["above_ma200"] else ("down" if m["above_ma200"] is False else "muted")
row2[2].markdown(kpi("MA200", f'{m["ma200"]:.3f}' if m["ma200"] == m["ma200"] else "-", ma200_sub, ma200_sub_c), unsafe_allow_html=True)
row2[3].markdown(kpi("IOPV（快照）", f'{info["iopv"]:.3f}' if pd.notna(info["iopv"]) else "-", "实时估值", "muted"), unsafe_allow_html=True)
row2[4].markdown(kpi("20 日均成交额", f'{m["avg_amount_20d"]/1e8:.2f} 亿' if m["avg_amount_20d"] == m["avg_amount_20d"] else "-", "流动性参考", "muted"), unsafe_allow_html=True)

st.markdown("&nbsp;", unsafe_allow_html=True)

# ---------- 日K线 ----------
st.markdown("##### 日 K 线（不复权）")
days = {"全部": len(q), "近1年": 250, "近6月": 120, "近3月": 60}[win]
_d = charts.prepare_kline(q, days=days)
_ch = charts.kline_chart(_d, palette, height=400, vol_height=100)
if _ch is not None:
    st.altair_chart(_ch, width="stretch")
    _first = _d["trade_date"].iloc[0].strftime("%Y-%m-%d")
    _last = _d["trade_date"].iloc[-1].strftime("%Y-%m-%d")
    st.caption(
        f"显示 {len(_d)} 个交易日（{_first} ~ {_last}） · "
        f"蜡烛<span class='up'>红=收≥开</span>/<span class='down'>绿=收&lt;开</span> · "
        f"均线 MA5/MA20/MA60 按完整历史滚动计算"
    )

# ---------- 近期明细表 ----------
st.markdown("##### 近期日线（最近 20 交易日）")
recent = q.tail(20)[["trade_date", "open", "high", "low", "close", "volume", "amount"]].copy()
recent["涨跌幅%"] = recent["close"].pct_change() * 100
recent = recent.iloc[::-1]  # 最新在上
st.dataframe(
    recent.set_index("trade_date"),
    width="stretch",
    height=400,
    column_config={
        "open": st.column_config.NumberColumn("开盘", format="%.3f"),
        "high": st.column_config.NumberColumn("最高", format="%.3f"),
        "low": st.column_config.NumberColumn("最低", format="%.3f"),
        "close": st.column_config.NumberColumn("收盘", format="%.3f"),
        "volume": st.column_config.NumberColumn("成交量", format="%d"),
        "amount": st.column_config.NumberColumn("成交额", format="%d"),
        "涨跌幅%": st.column_config.NumberColumn(format="%.2f%%"),
    },
)

st.caption(
    f"数据：{m['days']} 个交易日（{q['trade_date'].iloc[0]} ~ {q['trade_date'].iloc[-1]}），"
    f"不复权日频（新浪源）；快照字段时点 {info['snapshot_at']}。仅供研究参考，不构成投资建议。"
)
