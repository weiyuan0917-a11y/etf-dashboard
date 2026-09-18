"""AppTest 验证：一键更新按钮渲染、确认态切换、空闲态→跑态不会崩。"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\etf-dashboard")

from streamlit.testing.v1 import AppTest


def main() -> None:
    # 1) 初始渲染（无锁 → 看到两个按钮）
    at = AppTest.from_file(r"D:\etf-dashboard\app.py", default_timeout=15)
    at.run()
    if at.exception:
        print("EXCEPTION 初始:", at.exception[0].value)
        for ex in at.exception:
            print("   -", ex.value)
        sys.exit(1)
    print("初始渲染 OK (空闲态)")
    btn_labels = [b.label for b in at.button]
    print(f"   buttons = {btn_labels}")
    assert "🚀 规模前 300" in btn_labels, "缺规模前 300 按钮"
    assert "📦 全量更新" in btn_labels, "缺全量更新按钮"
    print("   ✅ 两个更新按钮都在")

    # 2) 点全量 → 进入确认态
    at.session_state["upd_confirm_all"] = True
    at.run()
    if at.exception:
        print("EXCEPTION 确认态:", at.exception[0].value)
        sys.exit(1)
    btn_labels2 = [b.label for b in at.button]
    print(f"   确认态 buttons = {btn_labels2}")
    assert "✅ 确认开始" in btn_labels2, "确认态缺确认按钮"
    print("   ✅ 全量二次确认态正确")

    # 3) 模拟跑态：写一个 lock 文件（PID 用一个明显不存在的）
    from pathlib import Path
    import json
    import os
    lock_path = Path(r"D:\etf-dashboard\data\update.lock")
    # 沙箱不让你 unlink 现有数据文件 — 用 try/except 兜底
    try:
        lock_path.write_text(
            json.dumps({"pid": 999999, "mode": "test", "started_at": "2026-09-18 12:00:00"}),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"无法写 lock，跳过跑态测试: {e}")
        print("全部通过（跳过跑态）")
        sys.exit(0)
    # AppTest session_state 没有 pop，用 [] = 模拟
    at.session_state["upd_confirm_all"] = False
    at.run()
    if at.exception:
        print("EXCEPTION 跑态:", at.exception[0].value)
        sys.exit(1)
    # 999999 进程不存在 → _read_lock 应该清掉锁并返回 None → 回到空闲态
    btn_labels3 = [b.label for b in at.button]
    print(f"   失效锁后 buttons = {btn_labels3[:6]}")
    assert "🚀 规模前 300" in btn_labels3, "失效锁没清掉，应回到空闲态"
    print("   ✅ 失效锁自动清理，回到空闲态")

    print("全部通过")


if __name__ == "__main__":
    main()
