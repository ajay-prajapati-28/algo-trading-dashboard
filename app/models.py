from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User
# from django.contrib.auth.models import User

class UploadedFile(models.Model):
    id = models.AutoField(primary_key=True)
    file = models.FileField(upload_to='uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    original_filename = models.CharField(max_length=255)

    def __str__(self):
        return self.original_filename


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    groww_api_key = models.CharField(max_length=500, blank=True, null=True)
    groww_secret_key = models.CharField(max_length=500, blank=True, null=True)
    dhan_client_id = models.CharField(max_length=100, blank=True, null=True)
    dhan_access_token = models.CharField(max_length=500, blank=True, null=True)
    gemini_api_key = models.CharField(max_length=500, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s API Keys"


class Stock(models.Model):

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    id = models.AutoField(primary_key=True)
    # symbol = models.CharField(max_length=50, unique=True)
    symbol = models.CharField(max_length=50)
    company_name = models.CharField(max_length=255)
    security_id = models.CharField(max_length=50, blank=True, null=True)
    symbol_id = models.CharField(max_length=255, blank=True)
    dhan_security_id = models.CharField(max_length=50, null=True, blank=True)
    is_selected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'symbol']
    def __str__(self):
        # unique_together = ['user', 'symbol']
        return f"{self.symbol} - {self.company_name}"


class TradeOrder(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    action = models.CharField(max_length=10) # 'BUY' ya 'SELL'
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.action} - {self.quantity} {self.stock.symbol} @ ₹{self.price}"



class LivePrice(models.Model):
    id = models.AutoField(primary_key=True)
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='prices')
    symbol = models.CharField(max_length=50)
    symbol_id = models.CharField(max_length=255, blank=True)
    # live_price = models.DecimalField(max_digits=12, decimal_places=2)
    live_price = models.CharField(max_length=50)
    fetched_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.symbol} - {self.live_price} at {self.fetched_at}"


class BacktestStrategy(models.Model):
    STRATEGY_CHOICES = [
        ('SMA_CROSSOVER', 'SMA Crossover'),
        ('EMA_CROSSOVER', 'EMA Crossover'),
        ('RSI', 'RSI Strategy'),
        ('MACD', 'MACD Strategy'),
        ('BOLLINGER_BANDS', 'Bollinger Bands'),
    ]
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    strategy_type = models.CharField(max_length=50, choices=STRATEGY_CHOICES)
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)

    param_fast_period = models.IntegerField(default=10)
    param_slow_period = models.IntegerField(default=30)
    param_signal_period = models.IntegerField(default=9)
    param_rsi_period = models.IntegerField(default=14)
    param_rsi_overbought = models.IntegerField(default=70)
    param_rsi_oversold = models.IntegerField(default=30)
    param_bb_period = models.IntegerField(default=20)
    param_bb_std = models.FloatField(default=2.0)

    initial_capital = models.DecimalField(max_digits=15, decimal_places=2, default=100000)
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.strategy_type} on {self.stock.symbol}"


class BacktestResult(models.Model):
    id = models.AutoField(primary_key=True)
    strategy = models.ForeignKey(BacktestStrategy, on_delete=models.CASCADE, related_name='results')
    total_trades = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)
    win_rate = models.FloatField(default=0.0)
    total_return_pct = models.FloatField(default=0.0)
    total_profit_loss = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    max_drawdown_pct = models.FloatField(default=0.0)
    sharpe_ratio = models.FloatField(default=0.0)
    initial_capital = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    final_capital = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    best_trade_pct = models.FloatField(default=0.0)
    worst_trade_pct = models.FloatField(default=0.0)
    avg_trade_pct = models.FloatField(default=0.0)
    equity_curve_json = models.TextField(default='[]')
    executed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Result for {self.strategy.name} - Return: {self.total_return_pct}%"


class BacktestTrade(models.Model):
    id = models.AutoField(primary_key=True)
    result = models.ForeignKey(BacktestResult, on_delete=models.CASCADE, related_name='trades')
    trade_type = models.CharField(max_length=20, default='BUY->SELL')
    entry_date = models.CharField(max_length=50)
    exit_date = models.CharField(max_length=50, blank=True)
    entry_price = models.DecimalField(max_digits=12, decimal_places=2)
    exit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quantity = models.IntegerField(default=0)
    profit_loss = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    profit_loss_pct = models.FloatField(null=True, blank=True)
    signal = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.trade_type} {self.entry_date} -> {self.exit_date} P&L: {self.profit_loss}"