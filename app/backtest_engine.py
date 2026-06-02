import pandas as pd
import numpy as np


class BacktestEngine:
    def __init__(self, df, initial_capital, strategy_type, params):
        # 🔥 Yfinance ke NaN (holidays) data ko remove karna zaroori hai
        self.df = df.dropna().copy()
        self.initial_capital = initial_capital
        # Humne 'MIX' request ko backend se as 'MIX_STRATEGY' process karne ka setup kiya hai
        self.strategy_type = 'MIX_STRATEGY' if strategy_type == 'MIX' else strategy_type
        self.params = params
        self.trades = []
        self.equity_curve = []

    def run(self) -> dict:
        if self.df.empty:
            return {"error": "No valid data found for the selected dates."}

        # SDE Trick: Python match-case jaisa implementation for clean code
        if self.strategy_type == 'SMA':
            signals = self._sma_crossover()
        elif self.strategy_type == 'EMA':
            signals = self._ema_crossover()
        elif self.strategy_type == 'RSI':
            signals = self._rsi_strategy()
        elif self.strategy_type == 'MACD':
            signals = self._macd_strategy()
        elif self.strategy_type == 'BollingerBands':
            signals = self._bollinger_bands()
        elif self.strategy_type == 'MIX_STRATEGY':
            signals = self._mix_strategy()
        else:
            # Fallback agar views aur yahan naming mismatch ho
            # Upar wle names maine views.py ki list ke hisab se match kara diye hain!
            return {"error": f"Invalid strategy type: {self.strategy_type}"}

        self._simulate_trades(signals)
        return self._calculate_metrics()

    def _sma_crossover(self) -> pd.Series:
        fast = self.params.get('fast_period', 10)
        slow = self.params.get('slow_period', 30)
        fast_ma = self.df['close'].rolling(window=fast).mean()
        slow_ma = self.df['close'].rolling(window=slow).mean()

        signals = pd.Series(0, index=self.df.index)
        signals[fast_ma > slow_ma] = 1
        signals[fast_ma < slow_ma] = -1
        return signals

    def _ema_crossover(self) -> pd.Series:
        fast = self.params.get('fast_period', 10)
        slow = self.params.get('slow_period', 30)
        fast_ema = self.df['close'].ewm(span=fast, adjust=False).mean()
        slow_ema = self.df['close'].ewm(span=slow, adjust=False).mean()

        signals = pd.Series(0, index=self.df.index)
        signals[fast_ema > slow_ema] = 1
        signals[fast_ema < slow_ema] = -1
        return signals

    def _rsi_strategy(self) -> pd.Series:
        period = self.params.get('rsi_period', 14)
        overbought = self.params.get('rsi_overbought', 70)
        oversold = self.params.get('rsi_oversold', 30)

        delta = self.df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        signals = pd.Series(0, index=self.df.index)
        signals[rsi < oversold] = 1
        signals[rsi > overbought] = -1
        return signals

    def _macd_strategy(self) -> pd.Series:
        fast = self.params.get('fast_period', 12)
        slow = self.params.get('slow_period', 26)
        signal_period = self.params.get('signal_period', 9)

        ema_fast = self.df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = self.df['close'].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()

        signals = pd.Series(0, index=self.df.index)
        signals[macd_line > signal_line] = 1
        signals[macd_line < signal_line] = -1
        return signals

    def _bollinger_bands(self) -> pd.Series:
        period = self.params.get('bb_period', 20)
        std_dev = self.params.get('bb_std', 2.0)

        mid = self.df['close'].rolling(window=period).mean()
        rolling_std = self.df['close'].rolling(window=period).std()
        upper = mid + std_dev * rolling_std
        lower = mid - std_dev * rolling_std

        signals = pd.Series(0, index=self.df.index)
        signals[self.df['close'] < lower] = 1
        signals[self.df['close'] > upper] = -1
        return signals

    # 🔥 NAYA ADD KIYA HUA FUNCTION (MIX STRATEGY) 🔥
    def _mix_strategy(self) -> pd.Series:
        """
        Combine SMA, RSI, and MACD into a single robust strategy.
        Trade triggers only when multiple indicators align.
        """
        # 1. Calculate SMA
        fast_sma = self.params.get('fast_period', 10)
        slow_sma = self.params.get('slow_period', 30)
        sma_fast_line = self.df['close'].rolling(window=fast_sma).mean()
        sma_slow_line = self.df['close'].rolling(window=slow_sma).mean()

        # 2. Calculate RSI
        rsi_period = self.params.get('rsi_period', 14)
        delta = self.df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        rsi_line = 100 - (100 / (1 + rs))

        # 3. Calculate MACD
        macd_fast = self.df['close'].ewm(span=12, adjust=False).mean()
        macd_slow = self.df['close'].ewm(span=26, adjust=False).mean()
        macd_line = macd_fast - macd_slow
        signal_line = macd_line.ewm(span=9, adjust=False).mean()

        # Generate Signals based on Combined Conditions
        signals = pd.Series(0, index=self.df.index)

        # BUY Condition: Uptrend (SMA) AND Bullish Momentum (MACD) AND Not Overbought (RSI)
        buy_condition = (sma_fast_line > sma_slow_line) & (macd_line > signal_line) & (
                    rsi_line < self.params.get('rsi_overbought', 70))

        # SELL Condition: Downtrend (SMA) OR Bearish Momentum (MACD) OR Overbought (RSI)
        # SDE Logic: Buying requires all to agree, but selling happens if any indicator warns!
        sell_condition = (sma_fast_line < sma_slow_line) | (macd_line < signal_line) | (
                    rsi_line > self.params.get('rsi_overbought', 70))

        signals[buy_condition] = 1
        signals[sell_condition] = -1
        return signals

    def _simulate_trades(self, signals):
        capital = float(self.initial_capital)
        position = 0
        entry_price = 0
        entry_date = None

        for i in range(len(self.df)):
            price = float(self.df.iloc[i]['close'])
            date = str(self.df.iloc[i]['date'].date())
            signal = signals.iloc[i]

            if signal == 1 and position == 0:
                quantity = int(capital // price)
                if quantity > 0:
                    position = quantity
                    capital -= position * price
                    entry_price = price
                    entry_date = date

            elif signal == -1 and position > 0:
                proceeds = position * price
                capital += proceeds
                profit_loss = proceeds - (position * entry_price)
                profit_loss_pct = (price - entry_price) / entry_price * 100

                self.trades.append({
                    "trade_type": "BUY->SELL",
                    "entry_date": entry_date,
                    "exit_date": date,
                    "entry_price": entry_price,
                    "exit_price": price,
                    "quantity": position,
                    "profit_loss": round(profit_loss, 2),
                    "profit_loss_pct": round(profit_loss_pct, 2)
                })
                position = 0

            current_value = capital + (position * price)
            self.equity_curve.append({
                "date": date,
                "value": round(current_value, 2)
            })

        if position > 0:
            last_price = float(self.df.iloc[-1]['close'])
            last_date = str(self.df.iloc[-1]['date'].date())
            proceeds = position * last_price
            capital += proceeds
            profit_loss = proceeds - (position * entry_price)
            profit_loss_pct = (last_price - entry_price) / entry_price * 100

            self.trades.append({
                "trade_type": "BUY->SELL",
                "entry_date": entry_date,
                "exit_date": last_date,
                "entry_price": entry_price,
                "exit_price": last_price,
                "quantity": position,
                "profit_loss": round(profit_loss, 2),
                "profit_loss_pct": round(profit_loss_pct, 2)
            })
            self.equity_curve[-1]["value"] = round(capital, 2)

    def _calculate_metrics(self) -> dict:
        if not self.trades:
            # 🔥 Behtar error message
            return {
                "error": "No trades executed. Market conditions did not trigger any Buy/Sell signals."}

        winning_trades = [t for t in self.trades if t['profit_loss'] > 0]
        losing_trades = [t for t in self.trades if t['profit_loss'] <= 0]

        total_trades = len(self.trades)
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

        final_capital = self.equity_curve[-1]['value'] if self.equity_curve else self.initial_capital
        total_return_pct = ((final_capital - self.initial_capital) / self.initial_capital) * 100
        total_profit_loss = final_capital - self.initial_capital

        best_trade_pct = max([t['profit_loss_pct'] for t in self.trades], default=0.0)
        worst_trade_pct = min([t['profit_loss_pct'] for t in self.trades], default=0.0)
        avg_trade_pct = np.mean([t['profit_loss_pct'] for t in self.trades]) if total_trades > 0 else 0.0

        equity_df = pd.DataFrame(self.equity_curve)
        max_drawdown_pct = 0.0
        sharpe_ratio = 0.0

        if not equity_df.empty and len(equity_df) > 1:
            equity_df['peak'] = equity_df['value'].cummax()
            drawdowns = (equity_df['value'] - equity_df['peak']) / equity_df['peak']
            max_drawdown_pct = abs(drawdowns.min() * 100)

            equity_df['returns'] = equity_df['value'].pct_change().fillna(0)
            mean_ret = equity_df['returns'].mean()
            std_ret = equity_df['returns'].std()
            if std_ret > 0:
                sharpe_ratio = (mean_ret / std_ret) * np.sqrt(252)

        return {
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round(win_rate, 2),
            "total_return_pct": round(total_return_pct, 2),
            "total_profit_loss": round(total_profit_loss, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "final_capital": round(final_capital, 2),
            "best_trade_pct": round(best_trade_pct, 2),
            "worst_trade_pct": round(worst_trade_pct, 2),
            "avg_trade_pct": round(avg_trade_pct, 2),
            "trades": self.trades,
            "equity_curve": self.equity_curve
        }