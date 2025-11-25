import backtrader as bt

class GeneratedStrategy(bt.Strategy):
    def __init__(self):
        self.ma5 = bt.indicators.SimpleMovingAverage(self.data.close, period=5)
        self.ma20 = bt.indicators.SimpleMovingAverage(self.data.close, period=20)

    def next(self):
        if self.ma5[0] > self.ma20[0] and not self.position:
            self.buy()
        elif self.ma5[0] < self.ma20[0] and self.position:
            self.sell()