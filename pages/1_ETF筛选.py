# -*- coding: utf-8 -*-
"""ETF 筛选页：多维过滤 + 排序 + 点选看日K线"""
import sys
import zlib
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import charts
import storage
from metrics.indicators import build_metrics_table
from ui_theme import apply_theme, current_palette

st.set_page_config(
    page_title="ETF 筛选 · 工具台",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)
palette = apply_theme()

st.markdown(
    """
<div style="font-size:1.7rem;font-weight:800;letter-spacing:-0.02em;">🔍 ETF 筛选与对比</div>
<div style="color:var(--muted);font-size:0.9rem;margin-bottom:1rem;">
  多维度过滤 + 排序；指标基于日频行情（不复权）计算，A 股惯例 <span class="up">红涨</span><span class="muted"> / </span><span class="down">绿跌</span> · <b>勾选表格行左侧复选框即可查看日K线</b>
</div>
""",
    unsafe_allow_html=True,
)

storage.init_db()


# ---------- 缓存：避免每次 rerun 重算 1600+ 只 ----------
@st.cache_data(ttl=900, show_spinner="正在计算全市场指标…")
def _load_metrics() -> pd.DataFrame:
    return build_metrics_table()


@st.cache_data(ttl=900, show_spinner=False)
def _load_kline(code: str) -> pd.DataFrame:
    return storage.load_quotes(code)


m = _load_metrics()
if m.empty:
    st.warning("暂无行情数据，请先运行 `python collector/update.py`")
    st.stop()

_known_codes = set(m["code"].astype(str))

# ---------- 过滤器 ----------
with st.sidebar:
    st.markdown("### 🎛 过滤条件")
    kw = st.text_input("名称关键词", placeholder="如：红利、黄金、纳指")
    min_mv = st.number_input("规模下限（亿元）", 0.0, 500.0, 2.0, 0.5)
    min_amt = st.number_input("近 20 日日均成交额下限（千万元）", 0.0, 50.0, 2.0, 0.5)
    min_days = st.selectbox("上市数据长度（交易日）", [60, 120, 250, 500], index=1)
    st.divider()
    sort_col = st.selectbox(
        "排序依据",
        ["规模(亿)", "chg_1w", "chg_1m", "chg_3m", "ytd", "日均成交额(千万)"],
        index=3,
        format_func=lambda x: {
            "规模(亿)": "规模", "chg_1w": "近1周 %", "chg_1m": "近1月 %", "chg_3m": "近3月 %",
            "ytd": "年初至今 %", "日均成交额(千万)": "日均成交额",
        }[x],
    )
    asc = st.toggle("升序排列", False)

flt = m.copy()
flt["规模(亿)"] = (flt["total_mv"] / 1e8).round(2)
flt["日均成交额(千万)"] = (flt["avg_amount_20d"] / 1e7).round(2)
if kw:
    flt = flt[flt["name"].str.contains(kw, case=False, na=False)]
flt = flt[flt["规模(亿)"] >= min_mv]
flt = flt[flt["日均成交额(千万)"] >= min_amt]
flt = flt[flt["days"] >= min_days]

# 头部摘要带颜色
n = len(flt)
total = len(m)
hit_pct = (n / total * 100) if total else 0
st.markdown(
    f'<div style="background:var(--bg-card);border:1px solid var(--border);'
    f'border-radius:10px;padding:12px 16px;margin:0.5rem 0 1rem 0;">'
    f'<div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap;">'
    f'<div><span class="muted">命中：</span><b style="font-size:1.2rem;">{n}</b> <span class="muted">只</span></div>'
    f'<div><span class="muted">库内：</span><b>{total}</b> <span class="muted">只</span></div>'
    f'<div><span class="muted">命中率：</span><b>{hit_pct:.1f}%</span></div>'
    f'<div style="margin-left:auto;"><span class="muted">排序：</span><b>{sort_col}</b> '
    f'<span class="muted">·</span> {"升序" if asc else "降序"}</div>'
    f"</div></div>",
    unsafe_allow_html=True,
)

cols = {
    "code": "代码", "name": "名称", "close": "收盘价", "chg_1w": "近1周%", "chg_1m": "近1月%",
    "chg_3m": "近3月%", "ytd": "年初至今%", "ma20": "MA20", "ma60": "MA60",
    "above_ma60": "站上MA60", "above_ma200": "站上MA200", "premium_rate": "折溢价%",
    "规模(亿)": "规模(亿)", "日均成交额(千万)": "日均成交额(千万)",
}
view = flt.sort_values(sort_col, ascending=asc)[list(cols)].rename(columns=cols)
for b in ["站上MA60", "站上MA200"]:
    view[b] = view[b].map({True: "是", False: "否", None: "-"})

# ⚠️ 关键：上面的布尔筛选会让 index 保留原始行标签（不是 0..n-1）。
# 而 st.dataframe 的 selection.rows 返回的是【显示行位置】，
# 必须重置索引，才能用 row_codes[pos] 正确反查代码。
view = view.reset_index(drop=True)
display = view.set_index("代码")
row_codes = display.index.tolist()          # 行位置 -> 代码 的稳定映射
_row_code_set = set(row_codes)

# 筛选条件变化时更换表格 key，避免旧的行选中状态被错误映射到新结果集
_sig = f"{kw}|{min_mv}|{min_amt}|{min_days}|{sort_col}|{asc}"
_table_key = f"screener_{zlib.crc32(_sig.encode())}"

if "picked_code" not in st.session_state:
    st.session_state["picked_code"] = None

table_event = st.dataframe(
    display,
    width="stretch",
    height=430,
    on_select="rerun",
    selection_mode="single-row",
    key=_table_key,
    column_config={
        "近1周%": st.column_config.NumberColumn(format="%.2f%%"),
        "近1月%": st.column_config.NumberColumn(format="%.2f%%"),
        "近3月%": st.column_config.NumberColumn(format="%.2f%%"),
        "年初至今%": st.column_config.NumberColumn(format="%.2f%%"),
        "折溢价%": st.column_config.NumberColumn(format="%.2f%%"),
        "收盘价": st.column_config.NumberColumn(format="%.3f"),
        "MA20": st.column_config.NumberColumn(format="%.3f"),
        "MA60": st.column_config.NumberColumn(format="%.3f"),
        "规模(亿)": st.column_config.NumberColumn(format="%.2f"),
        "日均成交额(千万)": st.column_config.NumberColumn(format="%.2f"),
    },
)

# 点选 → 记住标的代码（用代码而非行号，避免排序/筛选变化后错位）
_sel_rows: list = []
if table_event is not None:
    try:
        _sel_rows = list(table_event.selection.rows)
    except (AttributeError, KeyError, TypeError):
        _sel_rows = []

if _sel_rows:
    _pos = int(_sel_rows[0])
    if 0 <= _pos < len(row_codes):
        st.session_state["picked_code"] = str(row_codes[_pos])

picked = st.session_state["picked_code"]
# 校验：清掉历史遗留或异常写入的值，避免把非代码字符串当标的
if picked and picked not in _known_codes:
    picked = None
    st.session_state["picked_code"] = None

# ---------- 日 K 线 ----------
st.markdown("&nbsp;")
st.markdown("##### 📈 日 K 线")

if not picked:
    st.info(
        "👆 **勾选上方表格最左侧的复选框**（或点击行内复选框），这里会立即显示该标的的日K线。\n\n"
        "图表包含：蜡烛（红涨绿跌）+ MA5/MA20/MA60 均线 + 成交量副图；悬停可见每日开高低收。"
    )
else:
    row_meta = m[m["code"] == picked]
    name = str(row_meta["name"].iloc[0]) if not row_meta.empty else picked
    in_filter = picked in _row_code_set
    suffix = "" if in_filter else ' <span class="muted">（不在当前筛选结果中）</span>'

    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:12px;margin:4px 0 10px 0;">'
        f'<span style="font-size:1.3rem;font-weight:800;color:var(--text);">{picked}</span>'
        f'<span style="font-size:1.05rem;color:var(--text);">{name}</span>{suffix}'
        f"</div>",
        unsafe_allow_html=True,
    )

    _q = _load_kline(picked)
    if _q.empty:
        st.warning(f"{picked} 库内无行情数据")
    else:
        # 控制项
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        with c1:
            kdays = st.select_slider(
                "显示区间（交易日）",
                options=[60, 120, 250, 500, 1000],
                value=120,
                key="kline_days",
            )
        with c2:
            show_ma = st.toggle("均线", True, key="kline_ma")
        with c3:
            show_vol = st.toggle("成交量", True, key="kline_vol")
        with c4:
            st.caption("")  # 占位对齐

        _d = charts.prepare_kline(_q, days=kdays)
        _ch = charts.kline_chart(
            _d, palette, show_volume=show_vol, show_ma=show_ma,
            height=340, vol_height=88,
        )
        if _ch is not None:
            st.altair_chart(_ch, width="stretch")

        # 该标的关键指标
        if not row_meta.empty:
            r = row_meta.iloc[0]
            k1, k2, k3, k4, k5, k6 = st.columns(6)

            def _fmt(v, fmt="+.2f", suffix="%"):
                return "-" if pd.isna(v) else f"{v:{fmt}}{suffix}"

            with k1:
                st.metric("收盘价", f"{r['close']:.3f}" if not pd.isna(r["close"]) else "-")
            with k2:
                st.metric("近1月", _fmt(r["chg_1m"]), delta_color="off")
            with k3:
                st.metric("近3月", _fmt(r["chg_3m"]), delta_color="off")
            with k4:
                st.metric("年初至今", _fmt(r["ytd"]), delta_color="off")
            with k5:
                st.metric("MA20", f"{r['ma20']:.3f}" if not pd.isna(r["ma20"]) else "-")
            with k6:
                st.metric("MA60", f"{r['ma60']:.3f}" if not pd.isna(r["ma60"]) else "-")

            # 数据区间说明
            _first = _d["trade_date"].iloc[0].strftime("%Y-%m-%d")
            _last = _d["trade_date"].iloc[-1].strftime("%Y-%m-%d")
            st.caption(
                f"显示 {len(_d)} 个交易日（{_first} ~ {_last}）"
                f" · 蜡烛<span class='up'>红=收≥开</span>/<span class='down'>绿=收&lt;开</span>"
                f" · 均线 MA5/MA20/MA60 基于不复权收盘价，滚动窗口按完整历史计算"
            )

st.caption("折溢价为采集时点快照；动量/均线基于不复权日频收盘价。仅供研究参考，不构成投资建议。")
