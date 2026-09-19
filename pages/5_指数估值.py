# -*- coding: utf-8 -*-
"""指数估值分位页：宽基指数 PE / PB 历史分位(A 股惯例 红涨绿跌)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import storage
from ui_theme import apply_theme, color_pct

st.set_page_config(
    page_title="指数估值 · 工具台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
palette = apply_theme()

st.markdown(
    """
<div style="font-size:1.7rem;font-weight:800;letter-spacing:-0.02em;">📊 指数估值分位</div>
<div style="color:var(--muted);font-size:0.9rem;margin-bottom:1rem;">
  主要宽基指数的 <b>PE-TTM / PB</b> 历史分位,
  分位 = 当前值在过去所有月度数据中的百分位(A 股惯例 <span class="up">红涨</span> / <span class="down">绿跌</span>)
</div>
""",
    unsafe_allow_html=True,
)

storage.init_db()
df = storage.list_index_universe()

# 侧栏状态
_done = storage.get_index_valuation_done()
if _done:
    st.sidebar.caption(
        f"📅 指数估值更新于 {_done['finished_at']} "
        f"({_done['ok']} ok / {_done['skipped']} 暂无 / {_done['fail']} fail)"
    )

if df.empty:
    st.warning("暂无数据,请先运行 `python -m collector.index_valuation`")
    st.info(
        "**采集源说明**：\n"
        "- PE/PB 历史：legulegu（中证指数镜像,覆盖中证系 + 上证系）\n"
        "- 创业板 / 科创 50 / 深证成指：legulegu 暂无历史 PE/PB,标\"待补\"\n"
        "- 采集器限流 1.2s/只,首次约 1-2 分钟"
    )
    st.stop()

# 过滤掉无任何 PE/PB 数据的指数(legulegu 暂无的)
df_with_data = df[df["pe_ttm"].notna() | df["pb"].notna()].copy()
df_unavailable = df[df["pe_ttm"].isna() & df["pb"].isna()].copy()

# ========== 1. 总览表 ==========
st.markdown("### 🎯 估值分位总览")

# 分位颜色:数字越大(越贵)颜色越红(高估),越小(越便宜)颜色越绿(低估)
def _color_pct_cell(pct: float | None) -> str:
    if pct is None or pd.isna(pct):
        return ""
    if pct >= 80:
        return "background-color: #ffcccc; color: #b91c1c; font-weight: 700"  # 严重高估
    if pct >= 60:
        return "background-color: #ffe4cc; color: #c2410c"  # 偏高
    if pct >= 40:
        return "background-color: #fef3c7; color: #92400e"  # 中性
    if pct >= 20:
        return "background-color: #d1fae5; color: #047857"  # 偏低
    return "background-color: #a7f3d0; color: #065f46; font-weight: 700"  # 严重低估


def _fmt_pct(p: float | None) -> str:
    if p is None or pd.isna(p):
        return "—"
    return f"{p:.1f}%"


def _fmt_num(n: float | None, decimals: int = 2) -> str:
    if n is None or pd.isna(n):
        return "—"
    return f"{n:.{decimals}f}"


overview_cols = ["name", "last_date", "last_close", "pe_ttm", "pe_ttm_pct", "pb", "pb_pct", "history_rows"]
overview = df_with_data[overview_cols].copy()
overview.columns = ["指数", "日期", "点位", "PE-TTM", "PE 分位", "PB", "PB 分位", "历史月数"]
overview["点位"] = overview["点位"].apply(lambda x: _fmt_num(x, 0))
overview["PE-TTM"] = overview["PE-TTM"].apply(lambda x: _fmt_num(x, 1))
overview["PB"] = overview["PB"].apply(lambda x: _fmt_num(x, 2))
overview["PE 分位"] = overview["PE 分位"].apply(_fmt_pct)
overview["PB 分位"] = overview["PB 分位"].apply(_fmt_pct)

# 用 Styler 染色
styled = overview.style \
    .map(lambda v: _color_pct_cell(float(v.replace("%", ""))) if isinstance(v, str) and v.endswith("%") else "",
         subset=["PE 分位", "PB 分位"]) \
    .format({"历史月数": "{:.0f}"})

st.dataframe(styled, width="stretch", hide_index=True, height=320)

# 解读条
st.caption(
    "**分位颜色**："
    "<span style='background:#a7f3d0;padding:0 6px'>&nbsp;&lt;20%&nbsp;</span> 严重低估 · "
    "<span style='background:#d1fae5;padding:0 6px'>&nbsp;20-40%&nbsp;</span> 偏低 · "
    "<span style='background:#fef3c7;padding:0 6px'>&nbsp;40-60%&nbsp;</span> 中性 · "
    "<span style='background:#ffe4cc;padding:0 6px'>&nbsp;60-80%&nbsp;</span> 偏高 · "
    "<span style='background:#ffcccc;padding:0 6px'>&nbsp;&gt;80%&nbsp;</span> 严重高估"
    "　　⚠️ 分位仅反映历史位置,不构成投资建议"
)

# ========== 2. 单指数详情 ==========
st.markdown("---")
st.markdown("### 🔍 单指数详情")

# 排序:有数据的优先
name_to_code = {r["name"]: r["code"] for _, r in df.iterrows()}
options = list(name_to_code.keys())
c1, c2 = st.columns([3, 1])
with c1:
    sel_name = st.selectbox("选择指数", options, key="iv_select")
with c2:
    lookback_years = st.radio("回看区间", ["全部", "10 年", "5 年", "3 年"], horizontal=True, key="iv_lb")

code = name_to_code[sel_name]
hist = storage.get_index_history(code)

if hist.empty:
    st.info(f"{sel_name} 暂无 PE/PB 历史数据(legulegu 未收录)")
    st.stop()

# 区间裁剪
if lookback_years == "10 年":
    hist = hist[hist["trade_date"] >= hist["trade_date"].max() - pd.DateOffset(years=10)]
elif lookback_years == "5 年":
    hist = hist[hist["trade_date"] >= hist["trade_date"].max() - pd.DateOffset(years=5)]
elif lookback_years == "3 年":
    hist = hist[hist["trade_date"] >= hist["trade_date"].max() - pd.DateOffset(years=3)]

# 当前 KPI
last = hist.iloc[-1]
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("📅 数据日期", str(last["trade_date"].date()))
with c2:
    st.metric("📈 指数点位", f"{last['close']:,.0f}" if pd.notna(last["close"]) else "—")
with c3:
    pe_now = last["pe_ttm"]
    pe_pct = float((hist["pe_ttm"].dropna() <= pe_now).sum() / hist["pe_ttm"].dropna().notna().sum() * 100) if pd.notna(pe_now) else None
    st.metric("PE-TTM", f"{pe_now:.2f}" if pd.notna(pe_now) else "—",
              delta=f"分位 {pe_pct:.1f}%" if pe_pct is not None else None)
with c4:
    pb_now = last["pb"]
    pb_pct = float((hist["pb"].dropna() <= pb_now).sum() / hist["pb"].dropna().notna().sum() * 100) if pd.notna(pb_now) else None
    st.metric("PB", f"{pb_now:.2f}" if pd.notna(pb_now) else "—",
              delta=f"分位 {pb_pct:.1f}%" if pb_pct is not None else None)

# 双图：指数点位 + PE/PB 分位带
st.markdown(f"#### {sel_name} · 指数走势 vs PE/PB")

# 子图 1: 指数点位
chart_df = hist[["trade_date", "close"]].dropna().rename(columns={"trade_date": "日期", "close": "点位"})
st.line_chart(chart_df, x="日期", y="点位", height=240)

# 子图 2: PE 走势 + 0.25/0.5/0.75 分位参考线
pe_df = hist[["trade_date", "pe_ttm"]].dropna().rename(columns={"trade_date": "日期", "pe_ttm": "PE-TTM"})
if not pe_df.empty:
    st.line_chart(pe_df, x="日期", y="PE-TTM", height=240)

# 子图 3: PB 走势
pb_df = hist[["trade_date", "pb"]].dropna().rename(columns={"trade_date": "日期", "pb": "PB"})
if not pb_df.empty:
    st.line_chart(pb_df, x="日期", y="PB", height=240)

# 历史分位表(末 12 个月)
st.markdown("#### 近 12 个月分位走势")
hist_recent = hist.tail(12).copy()
hist_recent["PE 分位"] = hist_recent["pe_ttm"].apply(
    lambda x: (hist["pe_ttm"].dropna() <= x).sum() / hist["pe_ttm"].dropna().notna().sum() * 100
    if pd.notna(x) else None
)
hist_recent["PB 分位"] = hist_recent["pb"].apply(
    lambda x: (hist["pb"].dropna() <= x).sum() / hist["pb"].dropna().notna().sum() * 100
    if pd.notna(x) else None
)
disp = hist_recent[["trade_date", "close", "pe_ttm", "pe_ttm_pct" if "pe_ttm_pct" in hist_recent.columns else "PE 分位", "pb", "PB 分位"]].copy()
disp.columns = ["日期", "点位", "PE-TTM", "PE 分位", "PB", "PB 分位"]
disp["日期"] = disp["日期"].dt.strftime("%Y-%m")
disp["点位"] = disp["点位"].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "—")
disp["PE-TTM"] = disp["PE-TTM"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
disp["PB"] = disp["PB"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
disp["PE 分位"] = disp["PE 分位"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
disp["PB 分位"] = disp["PB 分位"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
st.dataframe(disp, width="stretch", hide_index=True, height=320)

# ========== 3. 暂无数据指数 ==========
if not df_unavailable.empty:
    st.markdown("---")
    with st.expander(f"📭 暂未收录的指数（{len(df_unavailable)} 只）", expanded=False):
        st.caption(
            "legulegu 当前没有这�"
            "些指数的历史 PE/PB 数据。"
            "后续会接中证指数官网 / 申万宏源 / 万得接口补齐。"
        )
        st.dataframe(
            df_unavailable[["name", "code", "last_date", "last_close"]].rename(
                columns={"name": "指数", "code": "代码", "last_date": "行情日期", "last_close": "最新点位"}
            ),
            width="stretch",
            hide_index=True,
        )

# ========== 4. 说明 ==========
st.markdown("---")
st.caption(
    "**数据源**：akshare.stock_index_pe_lg / stock_index_pb_lg (legulegu 镜像) · "
    "**采集命令**：`python -m collector.index_valuation` · "
    "**分位算法**：当前值在过去所有月度样本中的百分位(0-100%) · "
    "**⚠️ 本页输出仅供研究参考,不构成投资建议**"
)
