# -*- coding: utf-8 -*-
"""A 股 ETF 工具台 V1.0.1 · 主页
运行：streamlit run app.py
"""
import sys
import json
import subprocess
import time
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import storage
from ui_theme import apply_theme, color_pct, color_money

st.set_page_config(
    page_title="A股 ETF 工具台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()

# ---------- 标题区 ----------
st.markdown(
    """
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">
  <div style="font-size:1.7rem;font-weight:800;letter-spacing:-0.02em;">📊 A 股 ETF 工具台</div>
</div>
<div style="color:var(--muted);font-size:0.9rem;margin-bottom:1.2rem;">
  V1.0.1 · 日频数据版 —— <b>筛选</b> · <b>画像</b> · <b>资金分配器</b>
</div>
""",
    unsafe_allow_html=True,
)

# ---------- 数据状态 ----------
storage.init_db()
list_updated = storage.get_meta("etf_list_updated_at", "未采集")
quotes_updated = storage.get_meta("quotes_updated_at", "未采集")

with st.sidebar:
    st.markdown("### 🗂 数据状态")
    st.markdown(
        f'<div style="font-size:0.85rem;line-height:1.7;">'
        f'<span class="muted">清单快照：</span><b>{list_updated}</b><br/>'
        f'<span class="muted">行情更新：</span><b>{quotes_updated}</b>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown("### ⏱ 数据更新")
    # ---- 一键更新：后台 subprocess + 实时日志回灌 ----
    _LOG = Path(config.DB_PATH).parent / "update.log"
    _LOCK = Path(config.DB_PATH).parent / "update.lock"
    _DONE = Path(config.DB_PATH).parent / "update_done.json"

    def _read_lock():
        """返回当前运行中的 job 信息；进程不在则清掉失效锁。"""
        if not _LOCK.exists():
            return None
        try:
            info = json.loads(_LOCK.read_text(encoding="utf-8"))
            pid = info.get("pid")
            if pid:
                out = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True, text=True, timeout=3,
                )
                if str(pid) in out.stdout:
                    return info
            _LOCK.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            try:
                _LOCK.unlink(missing_ok=True)
            except OSError:
                pass
        return None

    def _start_update(mode: str) -> None:
        _LOG.write_text(
            f"[{time.strftime('%H:%M:%S')}] 启动更新：{mode}\n", encoding="utf-8"
        )
        args = [
            sys.executable,
            str(Path(__file__).resolve().parent / "collector" / "update.py"),
        ]
        if mode == "all":
            args.append("--all")
        else:
            args += ["--top", "300"]
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        proc = subprocess.Popen(
            args,
            stdout=open(_LOG, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).resolve().parent),
            creationflags=creationflags,
        )
        _LOCK.write_text(
            json.dumps(
                {"pid": proc.pid, "mode": mode,
                 "started_at": time.strftime("%Y-%m-%d %H:%M:%S")},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        # 清理上次的 done 标记
        try:
            _DONE.unlink(missing_ok=True)
        except OSError:
            pass
        st.rerun()

    def _start_valuation() -> None:
        """启动指数估值采集(独立子进程)"""
        _LOG_VAL = Path(config.DB_PATH).parent / "valuation.log"
        _LOCK_VAL = Path(config.DB_PATH).parent / "valuation.lock"
        try:
            _LOCK_VAL.write_text(
                json.dumps({"pid": 0, "mode": "valuation",
                            "started_at": time.strftime("%Y-%m-%d %H:%M:%S")},
                           ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            pass
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0  # type: ignore[attr-defined]
        subprocess.Popen(
            [sys.executable, "-m", "collector.index_valuation"],
            stdout=open(_LOG_VAL, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).resolve().parent),
            creationflags=creationflags,
        )
        st.toast("📈 指数估值采集已启动,1-2 分钟后刷新页面", icon="📊")
        st.rerun()

    def _start_industry() -> None:
        """启动行业轮动采集(独立子进程)"""
        _LOG_IND = Path(config.DB_PATH).parent / "industry.log"
        subprocess.Popen(
            [sys.executable, "-m", "collector.industry_rotation"],
            stdout=open(_LOG_IND, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).resolve().parent),
        )
        st.toast("🌊 行业轮动计算中,5 秒后刷新页面", icon="⚡")
        st.rerun()

    _lock = _read_lock()
    if _lock:
        st.warning(
            f"🟡 更新进行中 · {_lock['mode']} · PID {_lock['pid']} · 启动于 {_lock['started_at']}"
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄 刷新日志", key="upd_refresh", width="stretch"):
                st.rerun()
        with c2:
            if st.button("⏹ 终止", key="upd_stop", type="secondary", width="stretch"):
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(_lock["pid"]), "/T", "/F"],
                        capture_output=True, text=True, timeout=5,
                    )
                    with open(_LOG, "a", encoding="utf-8") as f:
                        f.write(f"[{time.strftime('%H:%M:%S')}] 用户终止\n")
                except Exception as e:  # noqa: BLE001
                    st.error(f"终止失败: {e}")
                _LOCK.unlink(missing_ok=True)
                st.rerun()
        try:
            log_txt = _LOG.read_text(encoding="utf-8", errors="replace")
            tail = "\n".join(log_txt.splitlines()[-30:])
            st.code(tail or "(暂无输出)", language="bash")
        except Exception:  # noqa: BLE001
            st.caption("无法读取日志")
    else:
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "🚀 规模前 300",
                key="upd_top300", type="primary", width="stretch",
                help="清单 + 规模前 300 只近 3 年行情，约 5-7 分钟",
            ):
                _start_update("top300")
        with c2:
            if st.button(
                "📦 全量更新",
                key="upd_all", type="secondary", width="stretch",
                help="清单 + 全部 1600+ 只 ETF，约 15-20 分钟",
            ):
                st.session_state["upd_confirm_all"] = True
                st.rerun()

        if st.session_state.get("upd_confirm_all"):
            st.warning("⚠️ 全量更新会跑 15-20 分钟，期间不要关闭页面。")
            cc1, cc2 = st.columns(2)
            with cc1:
                if st.button("✅ 确认开始", key="upd_all_ok", type="primary", width="stretch"):
                    st.session_state.pop("upd_confirm_all", None)
                    _start_update("all")
            with cc2:
                if st.button("取消", key="upd_all_cancel", width="stretch"):
                    st.session_state.pop("upd_confirm_all", None)
                    st.rerun()

        # ---- V1.3 新增：指数估值 + 行业轮动（独立小任务）----
        st.markdown("##### 📊 估值/轮动(V1.3)")
        c3, c4 = st.columns(2)
        with c3:
            if st.button(
                "📈 指数估值",
                key="upd_valuation", type="secondary", width="stretch",
                help="拉主要宽基指数 PE/PB 历史,约 1-2 分钟(legulegu 限流)",
            ):
                _start_valuation()
        with c4:
            if st.button(
                "🌊 行业轮动",
                key="upd_industry", type="secondary", width="stretch",
                help="算 27 个行业 ETF 强弱得分,约 5 秒",
            ):
                _start_industry()

        # 显示 update.py 退出时写的完成标记
        if _DONE.exists():
            try:
                d = json.loads(_DONE.read_text(encoding="utf-8"))
                st.success(
                    f"✅ 上次完成 {d.get('finished_at','')} · "
                    f"模式 {d.get('mode','')} · "
                    f"成功 {d.get('ok',0)} / 空 {d.get('empty',0)} / 失败 {d.get('fail',0)} · "
                    f"耗时 {d.get('seconds',0)}s"
                )
                if st.button("清除完成提示", key="upd_clear_done", width="content"):
                    _DONE.unlink(missing_ok=True)
                    st.rerun()
            except Exception:  # noqa: BLE001
                pass

    st.caption("首次约 3-5 分钟（规模前 300），全量约 15 分钟")
    st.divider()
    st.caption(
        "数据来源：akshare（东方财富公开接口）；行情为不复权日频口径（新浪源）。"
        "仅供研究参考，不构成投资建议。"
    )

try:
    etf_list = storage.load_etf_list()
    quoted = storage.quoted_codes()
except Exception:  # noqa: BLE001
    etf_list = pd.DataFrame()
    quoted = set()

if etf_list.empty:
    st.warning(
        "数据库还是空的。请先运行数据采集：\n\n"
        "```\n"
        "cd /d/etf-dashboard\n"
        "python collector/update.py\n"
        "```\n"
        "默认采集规模前 300 只 ETF 的近 3 年日频行情，约需 3-5 分钟。"
    )
    st.stop()

# ---------- 概览指标 ----------
total = len(etf_list)
q_n = len(quoted)
up_n = int((etf_list["change_pct"] > 0).sum())
down_n = int((etf_list["change_pct"] < 0).sum())
flat_n = total - up_n - down_n
mv = etf_list["total_mv"].dropna()
median_mv = (mv.median() / 1e8) if not mv.empty else 0

st.markdown("##### 市场快照", help=None)
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        f'<div style="background:var(--bg-card);border:1px solid var(--border);'
        f'border-radius:10px;padding:14px 16px;">'
        f'<div style="color:var(--muted);font-size:0.85rem;">ETF 总数</div>'
        f'<div style="color:var(--text);font-size:1.6rem;font-weight:700;">{total:,}</div>'
        f'<div class="muted" style="font-size:0.75rem;">全市场场内</div></div>',
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        f'<div style="background:var(--bg-card);border:1px solid var(--border);'
        f'border-radius:10px;padding:14px 16px;">'
        f'<div style="color:var(--muted);font-size:0.85rem;">已采集行情</div>'
        f'<div style="color:var(--text);font-size:1.6rem;font-weight:700;">{q_n:,} <span style="font-size:0.9rem;font-weight:500;" class="muted">只</span></div>'
        f'<div class="muted" style="font-size:0.75rem;">覆盖率 {q_n/total*100:.1f}%</div></div>',
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        f'<div style="background:var(--bg-card);border:1px solid var(--border);'
        f'border-radius:10px;padding:14px 16px;">'
        f'<div style="color:var(--muted);font-size:0.85rem;">快照涨跌家数</div>'
        f'<div style="font-size:1.4rem;font-weight:700;line-height:1.2;">'
        f'<span class="up">{up_n}</span> / <span class="down">{down_n}</span> '
        f'<span class="muted" style="font-size:0.9rem;">/ {flat_n} 平</span></div>'
        f'<div class="muted" style="font-size:0.75rem;">涨/跌/平（快照口径）</div></div>',
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        f'<div style="background:var(--bg-card);border:1px solid var(--border);'
        f'border-radius:10px;padding:14px 16px;">'
        f'<div style="color:var(--muted);font-size:0.85rem;">规模中位数</div>'
        f'<div style="color:var(--text);font-size:1.6rem;font-weight:700;">{median_mv:.1f} <span style="font-size:0.9rem;font-weight:500;" class="muted">亿</span></div>'
        f'<div class="muted" style="font-size:0.75rem;">总市值代理口径</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("&nbsp;", unsafe_allow_html=True)

# ---------- 板块导航卡 ----------
st.markdown("##### 功能导航")
# V1.3 改为 5 个,两行布局(3 + 2)
n1, n2, n3 = st.columns(3)
nav_row1 = [
    ("🔍 ETF 筛选", "按关键词/规模/成交额过滤，6 个维度排序", "pages/1_ETF筛选.py"),
    ("📈 ETF 画像", "单只走势 + MA + 关键指标 + 折溢价", "pages/2_ETF画像.py"),
    ("💼 模拟交易", "分配器 · 模拟下单 · 网格 · 持仓 · 流水", "pages/3_模拟交易.py"),
]
for col, (title, sub, _path) in zip([n1, n2, n3], nav_row1):
    with col:
        st.markdown(
            f'<div style="background:var(--bg-card);border:1px solid var(--border);'
            f'border-radius:10px;padding:16px 18px;height:96px;">'
            f'<div style="font-size:1.05rem;font-weight:700;color:var(--text);">{title}</div>'
            f'<div style="color:var(--muted);font-size:0.85rem;margin-top:6px;">{sub}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

# V1.3 第二行
n4, n5, _ = st.columns(3)
nav_row2 = [
    ("📊 指数估值", "宽基指数 PE/PB 历史分位,5 档色块", "pages/5_指数估值.py"),
    ("🌊 行业轮动", "27 个行业 ETF 强弱 + 做多/观望/减仓信号", "pages/6_行业轮动.py"),
]
for col, (title, sub, _path) in zip([n4, n5], nav_row2):
    with col:
        st.markdown(
            f'<div style="background:var(--bg-card);border:1px solid var(--border);'
            f'border-radius:10px;padding:16px 18px;height:96px;">'
            f'<div style="font-size:1.05rem;font-weight:700;color:var(--text);">{title}</div>'
            f'<div style="color:var(--muted);font-size:0.85rem;margin-top:6px;">{sub}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

st.markdown("&nbsp;", unsafe_allow_html=True)

# ---------- 快照总览表 ----------
st.markdown("##### 全市场 ETF 快照 · 规模前 50")
top = etf_list.dropna(subset=["total_mv"]).sort_values("total_mv", ascending=False).head(50)
show = top[["code", "name", "latest_price", "change_pct", "iopv", "premium_rate", "total_mv", "amount"]].rename(
    columns={
        "code": "代码", "name": "名称", "latest_price": "最新价", "change_pct": "涨跌幅%",
        "iopv": "IOPV", "premium_rate": "折溢价%", "total_mv": "规模(亿元)", "amount": "成交额(亿元)",
    }
)
show["规模(亿元)"] = (show["规模(亿元)"] / 1e8).round(2)
show["成交额(亿元)"] = (show["成交额(亿元)"] / 1e8).round(2)
# 涨跌幅/折溢价 着色（用 to_html + format，避免 column_config 复杂度）
def _fmt_pct(v):
    return color_pct(v, digits=2)

st.dataframe(
    show.set_index("代码"),
    width="stretch",
    height=480,
    column_config={
        "涨跌幅%": st.column_config.NumberColumn(format="%.2f%%"),
        "折溢价%": st.column_config.NumberColumn(format="%.2f%%"),
        "最新价": st.column_config.NumberColumn(format="%.3f"),
        "IOPV": st.column_config.NumberColumn(format="%.3f"),
    },
)

st.caption(f"来源与口径：东方财富 ETF 快照（{list_updated}），规模为总市值代理口径。涨/跌按 A 股惯例着色。")
