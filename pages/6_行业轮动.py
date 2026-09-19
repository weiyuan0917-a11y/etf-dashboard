# -*- coding: utf-8 -*-
"""行业轮动信号页:基于 ETF 关键词聚合,经典加权打分"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import storage
from ui_theme import apply_theme, color_pct

st.set_page_config(
    page_title="行业轮动 · 工具台",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)
palette = apply_theme()

st.markdown(
    """
<div style="font-size:1.7rem;font-weight:800;letter-spacing:-0.02em;">🌊 行业轮动信号</div>
<div style="color:var(--muted);font-size:0.9rem;margin-bottom:1rem;">
  按 ETF 名称关键词聚合 27 个行业,经典加权打分 = <b>动量 50% + 活跃度 30% + 估值反向 20%</b>
</div>
""",
    unsafe_allow_html=True,
)

storage.init_db()

# 完成时间
_done = storage.get_industry_done()
if _done:
    st.sidebar.caption(
        f"📅 行业轮动更新于 {_done['finished_at']} "
        f"({_done['n']} 个行业, {_done['elapsed_s']}s)"
    )

with storage.get_conn() as conn:
    rows = conn.execute(
        "SELECT industry, n_etf, total_mv, avg_chg_1d, avg_chg_5d, avg_chg_20d, avg_chg_60d,"
        " activity, avg_premium, score, signal, updated_at "
        "FROM industry_strength ORDER BY score DESC"
    ).fetchall()
    cols = ["industry", "n_etf", "total_mv", "avg_chg_1d", "avg_chg_5d", "avg_chg_20d", "avg_chg_60d",
            "activity", "avg_premium", "score", "signal", "updated_at"]
df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

if df.empty:
    st.warning("暂无数据,请先运行 `python -m collector.industry_rotation`")
    st.info("**首次需要 ~5 秒**(拉实时行情 + 算 27 个行业指标),之后可重复跑做日度刷新。")
    st.stop()


def _signal_badge(s: str) -> str:
    if s == "做多":
        return "🟢 做多"
    if s == "观望":
        return "🟡 观望"
    if s == "减仓":
        return "🔴 减仓"
    return s


def _color_chg(v):
    """涨跌幅染色:涨红跌绿(A 股惯例)"""
    if pd.isna(v):
        return ""
    if v >= 3: return "color: #b91c1c; font-weight: 700"
    if v >= 0: return "color: #dc2626"
    if v >= -3: return "color: #059669"
    return "color: #047857; font-weight: 700"


def _color_score(s):
    if pd.isna(s): return ""
    if s >= 65: return "background-color: #a7f3d0; color: #065f46; font-weight: 700"
    if s >= 40: return "background-color: #fef3c7; color: #92400e"
    return "background-color: #fee2e2; color: #b91c1c"


# ========== 1. Top 3 速览 ==========
st.markdown("### 🏆 当前 Top 3 行业")
top3 = df.head(3)
c1, c2, c3 = st.columns(3)
for col, (_, r) in zip([c1, c2, c3], top3.iterrows()):
    with col:
        delta_color = "normal"
        chg_str = f"{r['avg_chg_20d']:+.2f}%" if pd.notna(r['avg_chg_20d']) else "—"
        col.metric(
            f"{_signal_badge(r['signal'])} {r['industry']}",
            f"得分 {r['score']:.1f}",
            delta=f"20日 {chg_str}",
        )
        # 容错 None
        chg60 = f"{r['avg_chg_60d']:+.2f}%" if pd.notna(r['avg_chg_60d']) else "—"
        act = f"{r['activity']:.3f}" if pd.notna(r['activity']) else "—"
        st.caption(
            f"📊 {int(r['n_etf'])} 只 ETF · 规模 {r['total_mv']:.0f} 亿 · "
            f"60日 {chg60} · 活跃度 {act}"
        )

st.markdown("---")

# ========== 2. 完整行业表 ==========
st.markdown("### 📋 27 个行业强弱全表")

disp = df.copy()
disp = disp.rename(columns={
    "industry": "行业",
    "n_etf": "ETF数",
    "total_mv": "规模(亿)",
    "avg_chg_1d": "1日%",
    "avg_chg_5d": "5日%",
    "avg_chg_20d": "20日%",
    "avg_chg_60d": "60日%",
    "activity": "活跃度",
    "avg_premium": "溢价%",
    "score": "得分",
    "signal": "信号",
})

# 格式化
disp["规模(亿)"] = disp["规模(亿)"].apply(lambda x: f"{x:.0f}")
for c in ["1日%", "5日%", "20日%", "60日%", "溢价%"]:
    disp[c] = disp[c].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "—")
disp["活跃度"] = disp["活跃度"].apply(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
disp["信号"] = disp["信号"].apply(_signal_badge)
disp["得分"] = disp["得分"].apply(lambda x: f"{x:.1f}")
disp["ETF数"] = disp["ETF数"].astype(int)

# 染色
styled = disp.style \
    .map(_color_chg, subset=["1日%", "5日%", "20日%", "60日%"]) \
    .map(_color_score, subset=["得分"])

st.dataframe(styled, width="stretch", hide_index=True, height=600)

# ========== 3. 模型说明 ==========
st.markdown("---")
with st.expander("📐 打分模型说明", expanded=False):
    st.markdown(
        """
**综合得分(0-100) = 动量 50% + 活跃度 30% + 估值反向 20%**

| 维度 | 权重 | 含义 | 越高表示 |
|---|---|---|---|
| 动量(20日%) | 50% | 行业 ETF 池子平均 20 日涨幅 | 趋势越强 |
| 活跃度 | 30% | 行业总成交额 / 总规模 | 资金越关注 |
| 估值反向(溢价%) | 20% | 行业 ETF 平均折溢价(分位取反) | 越不被炒作 |

**信号分级**:
- 得分 ≥ 65: 🟢 **做多**（趋势 + 资金 + 估值都健康）
- 得分 40-65: 🟡 **观望**（中性）
- 得分 < 40: 🔴 **减仓**（弱势 + 资金冷 + 高估）

**注意**：
- "活跃度"用成交额/规模做代理,不是真正的资金流
- "溢价"分位是反向加权(高溢价 = 过热 = 减分),引导避开炒作
- 模型是**对历史数据做横截面排序**,不做时间序列预测
- 行业用 ETF 名称关键词聚合,样本数 ≥ 5 只 ETF 才纳入
"""
    )

# ========== 4. 免责 + 提示 ==========
st.caption(
    "**⚠️ 本页输出仅供研究参考,不构成投资建议** · "
    "**数据源**:本地 ETF 行情 + 实时行情(新浪) · "
    "**采集命令**:`python -m collector.industry_rotation` · "
    f"**最后更新**:{df['updated_at'].iloc[0] if len(df) > 0 else '-'}"
)
