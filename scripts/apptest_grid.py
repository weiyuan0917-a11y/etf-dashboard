"""AppTest 冒烟：pages/3_模拟交易.py 渲染、tab 切换、fragment 不抛错。

策略：
- 关闭实时行情（use_live=False），跳过外网请求
- 注入一个 grid 让「我的网格」非空
- streamlit 1.64 的 st.tabs 在 AppTest 里会跑全部 tab 的代码（只在渲染时隐藏非激活）
- 注入 session_state["gsel"] 触发单网格详情
- 验证页面没有 Exception，dataframe/radio/number_input 数量合理
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, r"D:\etf-dashboard")

from streamlit.testing.v1 import AppTest

import storage


def main() -> None:
    storage.init_db()
    elist = storage.load_etf_list()
    if elist.empty:
        print("FAIL: etf_list 为空")
        sys.exit(1)
    code = elist["code"].iloc[0]
    name = elist["name"].iloc[0]
    gid = storage.create_grid(
        code=code, name=name,
        center=1.000, upper=1.100, lower=0.900,
        step_pct=2.0, per_grid_shares=100, note="apptest",
    )
    print(f"已创建 grid #{gid} code={code}")

    at = AppTest.from_file(r"D:\etf-dashboard\pages\3_模拟交易.py")
    at.session_state["use_live"] = False
    at.session_state["live_every"] = 0
    at.session_state["init_amt"] = 100000.0
    at.session_state["fee_rate"] = 0.0001
    at.session_state["min_lot"] = 100

    at.run()
    if at.exception:
        print("EXCEPTION 初始:", at.exception[0].value)
        for ex in at.exception:
            print("   -", ex.value)
        sys.exit(1)
    print("初始渲染 OK")
    print("   dataframes =", len(at.dataframe))
    print("   radios =", len(at.radio))
    print("   number_input 数 =", len(at.number_input))
    print("   selectbox 数 =", len(at.selectbox))
    print("   buttons =", len(at.button))

    at.session_state["gsel"] = gid
    at.run()
    if at.exception:
        print("EXCEPTION gsel:", at.exception[0].value)
        for ex in at.exception:
            print("   -", ex.value)
        sys.exit(1)
    print(f"选中 grid #{gid} 渲染 OK")
    print("   dataframes =", len(at.dataframe))

    # 切 SELL
    at.session_state[f"ms_{gid}"] = "SELL"
    at.run()
    if at.exception:
        print("EXCEPTION side=SELL:", at.exception[0].value)
        sys.exit(1)
    print("切 SELL OK")

    # 切回 BUY
    at.session_state[f"ms_{gid}"] = "BUY"
    at.run()
    if at.exception:
        print("EXCEPTION side=BUY:", at.exception[0].value)
        sys.exit(1)
    print("切回 BUY OK")

    print("全部通过")


if __name__ == "__main__":
    try:
        main()
    finally:
        # 清理本次测试创建的 grid（id 是已知的）
        try:
            import sqlite3
            conn = sqlite3.connect(r"D:\etf-dashboard\data\etf.db")
            conn.execute("DELETE FROM grids WHERE note='apptest'")
            conn.execute("DELETE FROM grid_trades WHERE grid_id NOT IN (SELECT id FROM grids)")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"清理失败（可忽略）: {e}")
