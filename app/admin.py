from django.contrib import admin
from .models import UploadedFile, Stock, LivePrice, BacktestStrategy, BacktestResult, BacktestTrade

@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ['original_filename', 'uploaded_at']

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'company_name', 'is_selected', 'created_at']
    list_filter = ['is_selected']
    search_fields = ['symbol', 'company_name']

@admin.register(LivePrice)
class LivePriceAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'live_price', 'fetched_at']
    list_filter = ['symbol']
    ordering = ['-fetched_at']

@admin.register(BacktestStrategy)
class BacktestStrategyAdmin(admin.ModelAdmin):
    list_display = ['name', 'strategy_type', 'stock', 'start_date', 'end_date', 'created_at']

@admin.register(BacktestResult)
class BacktestResultAdmin(admin.ModelAdmin):
    list_display = ['strategy', 'total_trades', 'win_rate', 'total_return_pct', 'sharpe_ratio', 'executed_at']

@admin.register(BacktestTrade)
class BacktestTradeAdmin(admin.ModelAdmin):
    list_display = ['result', 'trade_type', 'entry_date', 'exit_date', 'profit_loss', 'profit_loss_pct']