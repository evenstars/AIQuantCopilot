import uuid
import os
import importlib.util
import backtrader as bt
import pandas as pd
import yfinance as yf
import sys

STRATEGY_DIR = "../strategies"


def save_strategy_code_to_file(python_code: str) -> str:
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
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "GeneratedStrategy"):
        raise ValueError("Strategy file does not contain GeneratedStrategy class")

    return module.GeneratedStrategy


def run_backtest_with_strategy(strategy_class, symbol="VOO", start="2015-01-01", end=None):
    cerebro = bt.Cerebro()
    cerebro.addstrategy(strategy_class)

    # --- Load data ---
    df = yf.download(symbol, start=start, end=end, auto_adjust=True)
    print(f"[DEBUG] yfinance downloaded {len(df)} rows for {symbol} ({start} to {end})")
    if len(df) == 0:
        raise RuntimeError(f"Downloaded zero rows of data for {symbol}. Check symbol or date range.")

    if hasattr(df.index, 'tz'):
        df.index = df.index.tz_localize(None)

    # flatten multi-index columns if needed
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    cerebro.broker.setcash(100000)
    cerebro.addsizer(bt.sizers.FixedSize, stake=10)

    start_val = cerebro.broker.getvalue()

    # --- Add analyzers ---
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='dd')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    result = cerebro.run()
    strat = result[0]

    # --- Extract analyzers ---
    dd = strat.analyzers.dd.get_analysis()
    ret = strat.analyzers.returns.get_analysis()
    sharpe = strat.analyzers.sharpe.get_analysis()
    trades = strat.analyzers.getbyname('trades').get_analysis()

    # --- Robust extract ---
    total_raw = trades.get('total', {})
    if not isinstance(total_raw, dict):
        total_closed_trade = 0
    else:
        total_closed_trade = total_raw.get('closed', 0)

    print("[DEBUG] total closed trades:", total_closed_trade)

    # --- Handle 0 trades as an agent-repair error ---
    if total_closed_trade == 0:
        raise RuntimeError(
            f"No trades were executed for symbol={symbol}. "
            f"The generated strategy likely never triggered any buy/sell signals."
        )

    end_val = cerebro.broker.getvalue()

    return {
        "symbol": symbol,
        "return_pct": ret.get('rtot', 0),
        "annual_return": ret.get('rnorm', 0),
        "max_drawdown": dd.get('max', {}).get('drawdown', 0),
        "sharpe": sharpe.get('sharperatio', None),
        "start_value": start_val,
        "end_value": end_val,
        "profit": end_val - start_val,
    }


def backtest_generated_code(python_code: str, symbol: str = "VOO", start="2015-01-01", end=None):
    file_path = save_strategy_code_to_file(python_code)
    strategy_class = dynamic_import_strategy(file_path)
    result = run_backtest_with_strategy(strategy_class, symbol=symbol, start=start, end=end)
    return result
