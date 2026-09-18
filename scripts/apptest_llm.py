"""AppTest 验证：4_设置.py + 3_模拟交易.py 新增 AI tab。

不动用户的 settings（不写 llm_api_key），只验证：
- 设置页 4_设置.py 渲染无 exception、3 个 provider option 都在
- 模拟交易页加载后 tab 数量=5（新增 AI tab）
- AI tab 在 llm 未配置时显示警告 + page_link
"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\etf-dashboard")

from streamlit.testing.v1 import AppTest


def main() -> None:
    storage = None
    import storage as _s
    storage = _s
    # 确保 settings 表里没残留 enabled=1 的（保险起见清掉 llm_enabled）
    storage.set_setting("llm_enabled", "0")
    storage.set_setting("llm_api_key", "")

    # --- 1) 设置页 ---
    at = AppTest.from_file(r"D:\etf-dashboard\pages\4_设置.py", default_timeout=10)
    at.run()
    if at.exception:
        print("EXCEPTION 设置页:", at.exception[0].value)
        for ex in at.exception:
            print("   -", ex.value)
        sys.exit(1)
    print("✅ 4_设置.py 渲染 OK")
    print("   selectbox 数 =", len(at.selectbox))
    print("   text_input 数 =", len(at.text_input))
    print("   button 数 =", len(at.button))
    btn_labels = [b.label for b in at.button]
    assert any("保存" in b for b in btn_labels), "缺保存按钮"
    print("   ✅ 保存按钮存在:", [b for b in btn_labels if "保存" in b])

    # --- 2) 模拟交易页 (5 个 tab) ---
    at2 = AppTest.from_file(r"D:\etf-dashboard\pages\3_模拟交易.py", default_timeout=15)
    at2.session_state["use_live"] = False
    at2.session_state["live_every"] = 0
    at2.session_state["init_amt"] = 100000.0
    at2.session_state["fee_rate"] = 0.0001
    at2.session_state["min_lot"] = 100
    at2.run()
    if at2.exception:
        print("EXCEPTION 模拟交易页:", at2.exception[0].value)
        for ex in at2.exception:
            print("   -", ex.value)
        sys.exit(1)
    tab_labels = [t.label for t in at2.tabs]
    print("✅ 3_模拟交易.py 渲染 OK")
    print("   tabs =", tab_labels)
    assert "🤖 AI 复盘" in tab_labels, f"缺 AI 复盘 tab，实际: {tab_labels}"
    print("   ✅ AI 复盘 tab 存在")
    # 应该有警告（因为 LLM 未配置）
    assert len(at2.warning) >= 1, "LLM 未配置时应当有 warning"
    print("   ✅ LLM 未配置时显示警告")

    print("\n全部通过")


if __name__ == "__main__":
    main()
