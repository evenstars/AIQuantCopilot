import uuid
import os
import importlib.util
import backtrader as bt
import pandas as pd
import yfinance as yf
import sys
from datetime import datetime

STRATEGY_DIR = "../strategies"


def save_strategy_code_to_file(python_code: str) -> str:
    """
    Save the generated strategy python code to a .py file and return the file path.
    """
    if not os.path.exists(STRATEGY_DIR):
        os.makedirs(STRATEGY_DIR)
    file_id = str(uuid.uuid4()).replace("-", "")
    file_path = os.path.join(STRATEGY_DIR, f"strategy_{file_id}.py")
    with open(file_path, "w") as f:
        f.write(python_code)

    return file_path


def dynamic_import_strategy(file_path: str):
    module_name = os.path.splitext(os.path.basename(file_path))[0]

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)

    # --- FIX: register before exec_module ---
    sys.modules[module_name] = module

    spec.loader.exec_module(module)

    if not hasattr(module, "GeneratedStrategy"):
        raise ValueError("Strategy file does not contain GeneratedStrategy class")
    return module.GeneratedStrategy


def run_backtest_with_strategy(strategy_class, symbol="VOO", start="2015-01-01", end=None):
    """
    Run Backtrader backtest with a dynamically imported strategy class.
    """
    print(type(strategy_class))
    cerebro = bt.Cerebro()
    cerebro.addstrategy(strategy_class)
    # Fetch data from yfinance
    df = yf.download(symbol, start=start, end=end, auto_adjust=True)
    if hasattr(df.index, 'tz'):
        df.index = df.index.tz_localize(None)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    else:
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    cerebro.broker.setcash(100000)
    cerebro.addsizer(bt.sizers.FixedSize, stake=10)
    start_val = cerebro.broker.getvalue()
    cerebro.run()
    end_val = cerebro.broker.getvalue()
    return {
        "symbol": symbol,
        "start_value": start_val,
        "end_value": end_val,
        "profit": end_val - start_val,
        "return_pct": (end_val - start_val) / start_val * 100,
        "trades": [],  # 可未来扩展 trade list
    }
