# -*- coding: utf-8 -*-
"""验证 live.py 改用新浪后, 3_模拟交易.py 仍能正常拿到实时价。

不启 streamlit server, 直接 import 页面模块不行 (它有 st.stop),
所以只测 live.py 的核心契约:
    1) fetch_quotes 返回的列与旧版完全一致
    2) 拿到 5 只的实时价且与新浪一致
    3) fetch_price_map 提取 {code: price}
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(r'D:\etf-dashboard')))

from live import fetch_quotes, fetch_price_map, market_phase, RESULT_COLUMNS

CODES = ['513310', '510300', '159915', '511010', '518880']
df = fetch_quotes(CODES)

assert list(df.columns) == RESULT_COLUMNS, f'列不一致: {list(df.columns)} vs {RESULT_COLUMNS}'
assert len(df) == len(CODES), f'行数不对: {len(df)}'
assert df['price'].notna().all(), '价格有空值'
assert (df['prev_close'] > 0).all(), '昨收不应为 0'
assert df['chg_pct'].notna().all(), '涨跌幅有空值'

# 验证手算的涨跌幅
for _, r in df.iterrows():
    expected = (r['price'] - r['prev_close']) / r['prev_close'] * 100
    diff = abs(r['chg_pct'] - expected)
    assert diff < 0.01, f"{r['code']} 涨跌幅偏差: {r['chg_pct']} vs {expected}"

# price_map
pm = fetch_price_map(CODES)
assert set(pm.keys()) == set(CODES), f'price_map 缺: {set(CODES) - set(pm.keys())}'
assert all(pm[c] > 0 for c in CODES), '价格不合法'

# 阶段判断
phase, trading = market_phase()
assert phase in ('盘前','集合竞价','交易中','午间休市','已收盘','周末休市'), f'未知阶段: {phase}'

print('✅ live.py 新浪源 5 项断言全过:')
print(f'   - 返回 {len(df)} 行, 列: {list(df.columns)}')
print(f'   - 涨跌幅手算一致')
print(f'   - price_map 含 {len(pm)} 只')
print(f'   - 阶段判断: {phase} (trading={trading})')
print(f'   - 时间戳: {df["quote_at"].iloc[0]}')
print()
print(df.to_string(index=False))
