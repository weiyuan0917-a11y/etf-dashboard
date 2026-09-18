# -*- coding: utf-8 -*-
"""全站视觉主题：A 股红涨绿跌、统一样式、自定义 CSS。
所有页面在 set_page_config 之后第一行调用 apply_theme() 即可。
"""
import streamlit as st

# A 股配色：涨=红，跌=绿（默认 light 主题；深色主题下取更高对比度）
LIGHT = {
    "UP": "#dc2626",         # 红 600
    "DOWN": "#16a34a",       # 绿 600
    "FLAT": "#64748b",       # 灰 500
    "PRIMARY": "#2563eb",    # 蓝 600
    "BG_SOFT": "#f8fafc",    # slate 50
    "BG_CARD": "#ffffff",
    "BORDER": "#e2e8f0",     # slate 200
    "TEXT": "#0f172a",       # slate 900
    "MUTED": "#64748b",      # slate 500
    "ACCENT": "#0ea5e9",     # sky 500
}
DARK = {
    "UP": "#f87171",         # red 400
    "DOWN": "#4ade80",       # green 400
    "FLAT": "#94a3b8",
    "PRIMARY": "#60a5fa",
    "BG_SOFT": "#0f172a",
    "BG_CARD": "#1e293b",
    "BORDER": "#334155",
    "TEXT": "#f1f5f9",
    "MUTED": "#94a3b8",
    "ACCENT": "#38bdf8",
}

_THEME_KEY = "__etf_theme__"


def _is_dark() -> bool:
    """通过 base 主题色亮度判断当前 streamlit 主题（light vs dark）。"""
    try:
        # streamlit 1.30+ 可读 theme；但跨版本差异大，最稳的是看背景色是否深
        cfg = st.get_option("theme.base")
        return cfg == "dark"
    except Exception:  # noqa: BLE001
        return False


def current_palette() -> dict:
    return DARK if _is_dark() else LIGHT


def apply_theme(page_title: str | None = None, page_icon: str = "📊") -> dict:
    """在 set_page_config 之后立刻调用。返回当前调色板。"""
    if not st.session_state.get(_THEME_KEY):
        pal = current_palette()
        st.markdown(
            f"""
<style>
:root {{
  --up: {pal['UP']};
  --down: {pal['DOWN']};
  --flat: {pal['FLAT']};
  --primary: {pal['PRIMARY']};
  --bg-soft: {pal['BG_SOFT']};
  --bg-card: {pal['BG_CARD']};
  --border: {pal['BORDER']};
  --text: {pal['TEXT']};
  --muted: {pal['MUTED']};
  --accent: {pal['ACCENT']};
}}

/* 整体：更舒展的留白 + 浅色背景 */
.stApp {{
  background: var(--bg-soft);
}}
.main .block-container {{
  padding-top: 2.2rem;
  padding-bottom: 3rem;
  max-width: 1280px;
}}

/* 标题：左色条 + 字重 */
h1, h2, h3 {{
  color: var(--text);
  font-weight: 700;
  letter-spacing: -0.01em;
}}
h1 {{
  border-left: 4px solid var(--primary);
  padding-left: 0.6rem;
  margin-bottom: 0.2rem;
}}
h2 {{
  border-left: 3px solid var(--accent);
  padding-left: 0.5rem;
  margin-top: 1.8rem;
  font-size: 1.25rem;
}}

/* caption：灰一点 */
.stCaption, [data-testid="stCaptionContainer"] {{
  color: var(--muted);
  font-size: 0.85rem;
}}

/* metric 卡：白底 + 边框 + 阴影 */
[data-testid="stMetric"] {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}}
[data-testid="stMetric"] label {{
  color: var(--muted);
  font-weight: 500;
}}
[data-testid="stMetricValue"] {{
  font-size: 1.55rem;
  font-weight: 700;
  color: var(--text);
}}

/* 容器 divider 调淡 */
hr {{
  border-color: var(--border);
  margin: 1.2rem 0;
}}

/* dataframe：行高 + 表头加底色 */
.stDataFrame {{
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}}
.stDataFrame thead th {{
  background: var(--bg-soft) !important;
  font-weight: 600 !important;
}}

/* sidebar 背景轻微区分 */
[data-testid="stSidebar"] > div:first-child {{
  background: var(--bg-card);
  border-right: 1px solid var(--border);
}}

/* radio/segmented 选中态用主色 */
[data-testid="stRadio"] label[data-checked="true"] {{
  color: var(--primary) !important;
}}

/* 数字着色工具类（用 markdown HTML 时复用） */
.up   {{ color: var(--up);   font-weight: 600; }}
.down {{ color: var(--down); font-weight: 600; }}
.flat {{ color: var(--flat); }}
.muted {{ color: var(--muted); }}

/* 按钮：圆角 + 主色 */
.stButton button, .stDownloadButton button {{
  border-radius: 8px;
  font-weight: 600;
}}

/* 隐藏 hamburger 与 footer（更干净） */
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
</style>
            """,
            unsafe_allow_html=True,
        )
        st.session_state[_THEME_KEY] = True
    return current_palette()


def color_pct(x: float, digits: int = 2, suffix: str = "%") -> str:
    """A 股红涨绿跌：返回带颜色的 span 字符串。"""
    if x is None or (isinstance(x, float) and x != x):
        return f'<span class="flat">-</span>'
    cls = "up" if x > 0 else ("down" if x < 0 else "flat")
    sign = "+" if x > 0 else ""
    return f'<span class="{cls}">{sign}{x:.{digits}f}{suffix}</span>'


def color_bool(b, yes: str = "是", no: str = "否") -> str:
    if b is True:
        return f'<span class="up">{yes}</span>'
    if b is False:
        return f'<span class="flat">{no}</span>'
    return f'<span class="muted">-</span>'


def color_money(x: float, prefix: str = "¥") -> str:
    if x is None or (isinstance(x, float) and x != x):
        return f'<span class="muted">-</span>'
    return f'<span class="flat">{prefix}{x:,.0f}</span>'


def header_kpi(label: str, value: str, delta: str | None = None, sub: str | None = None) -> str:
    """自绘 KPI 卡片（用 st.markdown 输出），与 stMetric 同效但更可控。"""
    delta_html = ""
    if delta:
        # 简单判断：含 +/0/无 = up；含 - = down
        try:
            d = float(delta.replace("%", "").replace("+", ""))
            cls = "up" if d > 0 else ("down" if d < 0 else "flat")
        except Exception:  # noqa: BLE001
            cls = "flat"
        delta_html = f'<div class="{cls}" style="font-size:0.8rem;margin-top:2px;">{delta}</div>'
    sub_html = f'<div class="muted" style="font-size:0.75rem;margin-top:4px;">{sub}</div>' if sub else ""
    return (
        f'<div style="background:var(--bg-card);border:1px solid var(--border);'
        f'border-radius:10px;padding:14px 16px;box-shadow:0 1px 2px rgba(15,23,42,0.04);">'
        f'<div style="color:var(--muted);font-size:0.85rem;font-weight:500;">{label}</div>'
        f'<div style="color:var(--text);font-size:1.55rem;font-weight:700;line-height:1.2;">{value}</div>'
        f"{delta_html}{sub_html}</div>"
    )
