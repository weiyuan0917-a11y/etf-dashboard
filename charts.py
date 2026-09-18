# -*- coding: utf-8 -*-
"""图表模块：Altair 日K线（A 股红涨绿跌）。

不依赖 plotly —— Altair 随 streamlit 内置，且能完全控制 A 股配色惯例。
"""
from __future__ import annotations

import altair as alt
import pandas as pd

# 均线配色（与涨跌色区分开）
MA_COLORS = {"MA5": "#f59e0b", "MA20": "#2563eb", "MA60": "#9333ea"}


def prepare_kline(
    df: pd.DataFrame,
    days: int = 120,
    ma_windows: tuple[int, ...] = (5, 20, 60),
) -> pd.DataFrame:
    """排序 → 在【完整序列】上算均线 → 截取最近 days 根。

    均线必须在截取前算，否则窗口前 days 根会因数据不足而缺失。
    """
    if df is None or df.empty:
        return pd.DataFrame()

    d = df.copy()
    d["trade_date"] = pd.to_datetime(d["trade_date"])
    d = d.sort_values("trade_date").reset_index(drop=True)

    for w in ma_windows:
        d[f"MA{w}"] = d["close"].rolling(w, min_periods=w).mean()
    d["chg"] = d["close"].pct_change() * 100
    d["amplitude"] = (d["high"] - d["low"]) / d["close"].shift(1) * 100

    return d.tail(days).reset_index(drop=True)


def _bar_size(n: int) -> float:
    """按可见根数自适应蜡烛实体宽度（像素）。"""
    return float(max(1.5, min(7.0, 620.0 / max(n, 1))))


def kline_chart(
    d: pd.DataFrame,
    palette: dict,
    height: int = 340,
    vol_height: int = 90,
    show_volume: bool = True,
    show_ma: bool = True,
    ma_cols: tuple[str, ...] = ("MA5", "MA20", "MA60"),
):
    """日K线图层：蜡烛（影线+实体）+ 均线 + 可选成交量副图。

    Args:
        d: 已由 prepare_kline() 处理过的 DataFrame
        palette: ui_theme.current_palette() 的返回，需含 UP/DOWN/BORDER/TEXT/MUTED
    """
    if d is None or d.empty:
        return None

    up_c = palette["UP"]
    down_c = palette["DOWN"]
    text_c = palette["TEXT"]
    muted_c = palette["MUTED"]
    border_c = palette["BORDER"]

    # A 股惯例：收 >= 开 = 涨 = 红；收 < 开 = 跌 = 绿
    updown = alt.condition(
        alt.datum.close >= alt.datum.open,
        alt.value(up_c),
        alt.value(down_c),
    )

    size = _bar_size(len(d))
    x_enc = alt.X(
        "trade_date:T",
        title=None,
        axis=alt.Axis(format="%m/%d", tickCount=8, labelAngle=0, labelColor=muted_c,
                      domainColor=border_c, tickColor=border_c),
    )
    y_enc = alt.Y(
        "close:Q",  # 占位，实际各层覆盖
        title="价格",
        scale=alt.Scale(zero=False),
        axis=alt.Axis(labelColor=muted_c, domainColor=border_c, tickColor=border_c,
                      titleColor=muted_c, gridColor=border_c, gridOpacity=0.35),
    )

    tooltip = [
        alt.Tooltip("trade_date:T", title="日期", format="%Y-%m-%d"),
        alt.Tooltip("open:Q", title="开", format=".3f"),
        alt.Tooltip("high:Q", title="高", format=".3f"),
        alt.Tooltip("low:Q", title="低", format=".3f"),
        alt.Tooltip("close:Q", title="收", format=".3f"),
        alt.Tooltip("chg:Q", title="涨跌%", format="+.2f"),
        alt.Tooltip("volume:Q", title="成交量", format=",.0f"),
    ]

    base = alt.Chart(d).encode(x=x_enc, tooltip=tooltip)

    # 影线（最低~最高）
    wick = base.mark_rule(strokeWidth=1.0).encode(
        y=alt.Y("low:Q", title="价格", scale=alt.Scale(zero=False),
                axis=alt.Axis(labelColor=muted_c, domainColor=border_c, tickColor=border_c,
                              titleColor=muted_c, gridColor=border_c, gridOpacity=0.35)),
        y2=alt.Y2("high:Q"),
        color=updown,
    )
    # 实体（开~收）
    body = base.mark_bar(size=size).encode(
        y=alt.Y("open:Q", scale=alt.Scale(zero=False)),
        y2=alt.Y2("close:Q"),
        color=updown,
        opacity=alt.value(0.92),
    )

    layers = [wick, body]

    if show_ma:
        ma_cols = [c for c in ma_cols if c in d.columns]
        if ma_cols:
            long_ma = (
                d.melt(id_vars=["trade_date"], value_vars=list(ma_cols),
                       var_name="均线", value_name="值")
                .dropna(subset=["值"])
            )
            ma_layer = alt.Chart(long_ma).mark_line(strokeWidth=1.3).encode(
                x=x_enc,
                y=alt.Y("值:Q", title="价格", scale=alt.Scale(zero=False)),
                color=alt.Color(
                    "均线:N",
                    scale=alt.Scale(
                        domain=[c for c in MA_COLORS],
                        range=[MA_COLORS[c] for c in MA_COLORS],
                    ),
                    legend=alt.Legend(title=None, orient="top", labelColor=muted_c,
                                      symbolStrokeWidth=2),
                ),
            )
            layers.append(ma_layer)

    price = alt.layer(*layers).properties(height=height)

    if not show_volume or "volume" not in d.columns:
        return price.configure_view(stroke=None).properties(background="transparent")

    vol = (
        alt.Chart(d)
        .mark_bar(size=size)
        .encode(
            x=alt.X("trade_date:T", title=None,
                    axis=alt.Axis(format="%m/%d", tickCount=8, labelAngle=0,
                                  labelColor=muted_c, domainColor=border_c, tickColor=border_c)),
            y=alt.Y("volume:Q", title="成交量",
                    axis=alt.Axis(format="~s", labelColor=muted_c, domainColor=border_c,
                                  tickColor=border_c, titleColor=muted_c)),
            color=updown,
            opacity=alt.value(0.6),
            tooltip=tooltip,
        )
        .properties(height=vol_height)
    )

    # 注意：Altair 6 不允许子图各自带 background，只能在最外层 VConcatChart 上设
    return (
        alt.vconcat(price, vol, spacing=4)
        .resolve_scale(x="shared")
        .properties(background="transparent")
        .configure_view(stroke=None)
    )


def mini_sparkline(d: pd.DataFrame, palette: dict, height: int = 60):
    """迷你走势线（暂无使用，预留给列表内嵌走势）。"""
    if d is None or d.empty:
        return None
    updown = alt.condition(
        alt.datum.close >= alt.datum.open,
        alt.value(palette["UP"]),
        alt.value(palette["DOWN"]),
    )
    return (
        alt.Chart(d)
        .mark_line(strokeWidth=1.5)
        .encode(
            x=alt.X("trade_date:T", title=None, axis=None),
            y=alt.Y("close:Q", title=None, axis=None, scale=alt.Scale(zero=False)),
            color=updown,
        )
        .properties(height=height, background="transparent")
    )
