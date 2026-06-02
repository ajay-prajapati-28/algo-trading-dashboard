"""
URL configuration for algo_trading_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# from django.contrib import admin
# from django.urls import path,include
# from app import views
# urlpatterns = [
#     path('admin/', admin.site.urls),
#     # path('',views.index,name='index'),
#     path('', views.upload_excel, name='upload_page'),
#     path('save_selected_stocks/', views.save_selected_stocks, name='save_selected_stocks'),
#     path('calculate-price/', views.calculate_price, name='calculate_price'),
#     path('update-master/', views.update_groww_master, name='update_groww_master'),
# ]
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
# path('', views.index, name='index'),
#     path('place_order/', views.place_order, name='place_order'),
    path('register/', views.register_user, name='register'),
    path('login/', views.login_user, name='login'),
    path('logout/', views.logout_user, name='logout'),
    path('backtest/bulk-delete/', views.backtest_bulk_delete, name='backtest_bulk_delete'),
    path('settings/broker/', views.broker_settings, name='broker_settings'),
    path('', views.index, name='index'),
    path('upload/', views.upload_excel, name='upload_excel'),
    path('select/', views.select_stocks, name='select_stocks'),
    path('fetch-prices/', views.fetch_live_prices, name='fetch_live_prices'),
    path('api/latest-prices/', views.get_latest_prices, name='latest_prices'),
    path('fetch_live_prices/', views.fetch_live_prices, name='fetch_live_prices'),
    # path('ai_analyze/', views.ai_analyze_stocks, name='ai_analyze'),
    path('ai_analyze_gemini/', views.ai_analyze_stocks_gemini, name='ai_analyze_gemini'),
    # path('ai/analyze-all/', views.ai_analyze_stocks_gemini, name='ai_analyze_stocks_gemini'),
    path('ai/analyze-all/', views.ai_analyze_stocks_gemini, name='ai_analyze_stocks_gemini'),
    path('order_history/', views.order_history, name='order_history'),
    path('place_order/', views.place_order, name='place_order'),
    path('backtest/', views.backtest_dashboard, name='backtest_dashboard'),
    path('backtest/create/', views.backtest_create, name='backtest_create'),
    path('backtest/result/<int:pk>/', views.backtest_result, name='backtest_result'),
    path('backtest/delete/<int:pk>/', views.backtest_delete, name='backtest_delete'),
    path('backtest/compare/', views.backtest_compare, name='backtest_compare'),
    path('pro-algo/', views.pro_algo_dashboard, name='pro_algo_dashboard'),
    path('backtest/download/<int:pk>/', views.download_trades_csv, name='download_trades_csv'),
    path('history/<str:symbol>/', views.price_history, name='price_history'),
    path('remove/<int:stock_id>/', views.remove_stock, name='remove_stock'),
    path('set-broker/<str:broker>/', views.set_broker, name='set_broker'),
    path('<str:symbol>/', views.stock_detail, name='stock_detail'),
    path('stock/<str:symbol>/', views.stock_detail, name='stock_detail'),
    path('fetch-single-price/<str:symbol>/', views.fetch_single_live_price, name='fetch_single_price'),
    path('ai_analyze_history/<str:symbol>/', views.ai_analyze_history, name='ai_analyze_history'),
]
