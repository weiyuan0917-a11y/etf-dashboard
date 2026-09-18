# -*- coding: utf-8 -*-
"""⚙️ 设置 · LLM API 配置

将 API key / provider / model 存到 settings 表。开启后，「📊 模拟交易」页面会多出
「🤖 AI 复盘」Tab；「🔍 ETF 筛选」会多出「🤖 自然语言选基」入口。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

import llm
import storage

st.set_page_config(
    page_title="设置 · 工具台",
    page_icon="⚙️",
    layout="centered",
)

from ui_theme import apply_theme

apply_theme()

st.markdown(
    """
<div style="font-size:1.5rem;font-weight:800;">⚙️ 设置</div>
<div style="color:var(--muted);font-size:0.9rem;margin-bottom:1.2rem;">
  LLM API 配置、连通性自检、当前状态总览
</div>
""",
    unsafe_allow_html=True,
)

cfg = llm.get_config()

# ---------- 状态卡片 ----------
_ready = llm.is_ready()
_status_color = "#2ea44f" if _ready else "#cf222e"
_status_text = "✅ 已就绪" if _ready else "⚠️ 未启用"

st.markdown(
    f"""
<div style="background:var(--bg-card);border:1px solid var(--border);border-left:4px solid {_status_color};
border-radius:10px;padding:14px 18px;margin-bottom:1.2rem;">
  <div style="font-size:1.05rem;font-weight:700;color:{_status_color};">{_status_text}</div>
  <div style="color:var(--muted);font-size:0.85rem;margin-top:6px;line-height:1.6;">
    provider: <b>{cfg['provider']}</b> · model: <b>{cfg['model']}</b><br/>
    base_url: <code style="font-size:0.8rem;">{cfg['base_url'] or '(默认)'}</code><br/>
    api_key: <code style="font-size:0.8rem;">{('*' * 8 + cfg['api_key'][-4:]) if cfg['api_key'] else '(未填)'}</code>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

st.divider()
st.markdown("##### LLM 提供方")

# ---------- 表单 ----------
with st.form("llm_form", clear_on_submit=False):
    provider = st.selectbox(
        "Provider",
        ["deepseek", "openai", "custom"],
        index=["deepseek", "openai", "custom"].index(cfg["provider"])
        if cfg["provider"] in ("deepseek", "openai", "custom") else 0,
        help="deepseek 国内访问快、价格低；openai 质量高；custom 走任何 OpenAI 兼容服务（如通义千问 / 月之暗面 / 自建）",
    )

    if provider == "deepseek":
        default_base = "https://api.deepseek.com"
        default_model = "deepseek-chat"
        hint = "在 https://platform.deepseek.com → API Keys 创建；首注册有赠额。**可用模型：deepseek-chat（V3，对话）、deepseek-reasoner（R1，强推理）、deepseek-flash（实验性的 flash 变体）**。推荐先用 `deepseek-chat`。"
    elif provider == "openai":
        default_base = "https://api.openai.com/v1"
        default_model = "gpt-4o-mini"
        hint = "在 https://platform.openai.com/api-keys 创建；需要海外网络"
    else:
        default_base = ""
        default_model = ""
        hint = "base_url 必填，例如 https://dashscope.aliyuncs.com/compatible-mode/v1 · model 必填"

    api_key = st.text_input(
        "API Key",
        value=cfg["api_key"],
        type="password",
        help=hint,
    )

    c1, c2 = st.columns(2)
    with c1:
        base_url = st.text_input(
            "Base URL（可留空）",
            value=cfg["base_url"] or default_base,
            placeholder=default_base or "https://your-llm.example.com/v1",
            help="OpenAI 兼容服务的根地址，留空用 provider 默认值",
        )
    with c2:
        model = st.text_input(
            "Model",
            value=cfg["model"] or default_model,
            placeholder=default_model or "your-model-name",
        )

    enabled = st.checkbox(
        "启用 LLM 增强功能",
        value=cfg["enabled"],
        help="关闭后所有 AI 相关入口会隐藏，配置仍保留",
    )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        saved_click = st.form_submit_button("💾 保存配置", type="primary", width="stretch")
    with col_b:
        test_click = st.form_submit_button("🔌 保存并测试连通", width="stretch")

    if saved_click or test_click:
        if not api_key.strip():
            st.error("请填写 API Key")
        elif provider == "custom" and (not base_url.strip() or not model.strip()):
            st.error("custom 模式下 Base URL 和 Model 都必填")
        else:
            llm.save_config(provider, api_key, base_url, model, enabled)
            st.success("配置已保存")
            if test_click:
                with st.spinner("测试连通中…"):
                    res = llm.ping()
                if res["ok"]:
                    st.success(
                        f"✅ 连通 · {res['latency_ms']}ms · "
                        f"模型 {res['model']} · 回复「{res['reply']}」"
                    )
                else:
                    st.error(
                        f"❌ 连通失败 · {res['latency_ms']}ms · {res['error']}"
                    )
                    st.caption("常见原因：key 错 / base_url 错 / 模型名错 / 网络封了域名")
                st.rerun()

st.divider()

# ---------- 文档/帮助 ----------
with st.expander("📖 怎么拿到 API Key？"):
    st.markdown(
        """
**DeepSeek（推荐）**：
1. 打开 https://platform.deepseek.com → 注册/登录
2. 左侧「API Keys」→ 「Create new secret key」→ 复制（只显示一次！）
3. 填到上面 → 保存 → 测试

**OpenAI**：
1. https://platform.openai.com/api-keys → Create new secret key
2. 你的网络要能访问 api.openai.com
3. 余额不足会报 429，去 Billing 充值

**国内其他（用 custom 模式）**：
- 通义千问：https://dashscope.aliyun.com → API-KEY，base_url 用 `https://dashscope.aliyuncs.com/compatible-mode/v1`，model 填 `qwen-plus` / `qwen-turbo`
- 月之暗面：https://platform.moonshot.cn → base_url `https://api.moonshot.cn/v1`，model 填 `moonshot-v1-8k`
- DeepSeek 也支持用国内第三方代理，base_url 改成代理地址即可
"""
    )

with st.expander("💡 启用后能干什么？"):
    st.markdown(
        """
- **🤖 持仓复盘**（在「模拟交易」页）：把当前持仓 + 网格 + 近期 K 线打包给 AI，让它讲人话指出问题（"这只网格档位过密"、"这只 ETF 偏离行业太远"）
- **🔍 自然语言选基**（在「ETF 筛选」页）：直接问 "我想要波动小、跟踪沪深 300、有分红的 ETF"，AI 帮你解析成筛选条件
- **📊 AI 看板日报**（规划中）：每日 17:00 自动生成 200 字市场总结

**数据完全在你本机**：本项目只把"持仓 / 网格 / 公开行情数据"作为 context 喂给 AI，**不会**上传你的账户密码、未公开信息。详见源码 llm.py。
"""
    )

# ---------- 配置导出/导入 ----------
st.divider()
st.markdown("##### 🗂 高级 · 导入/导出 settings")

with st.expander("查看 settings 表全部键值"):
    rows = []
    with storage.get_conn() as conn:
        for k, v in conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall():
            if "key" in k.lower() or "secret" in k.lower():
                v = "***" + (v[-4:] if v else "")
            rows.append({"key": k, "value": v})
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.caption("(空)")
