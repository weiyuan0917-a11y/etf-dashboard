# -*- coding: utf-8 -*-
"""全局配置：路径、更新窗口、指标参数"""
from pathlib import Path

# 路径
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "etf.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 采集设置
HISTORY_YEARS = 3          # 日频行情回溯年数
MAX_RETRY = 3              # 单接口重试次数
RETRY_WAIT = 2             # 重试间隔（秒）
REQUEST_INTERVAL = 0.3     # 逐只采集时的请求间隔（秒），避免被限流

# 指标参数
MA_WINDOWS = [20, 60, 200]          # 均线窗口
MOMENTUM_WINDOWS = [20, 60]         # 动量窗口（交易日）
VALUATION_LOOKBACK = 5              # 预留：估值分位回溯年数（V2 接入指数估值）

# 资金分配器
LOT_SIZE = 100              # 场内 ETF 最小交易单位（份）
DRIFT_ALERT = 0.05          # 权重偏离告警阈值（5%）

# 数据来源标注（用于看板页脚）
DATA_SOURCE = "akshare（东方财富/新浪公开接口），采集时点见 etf_list.meta_updated_at / quotes 表内 trade_date"
