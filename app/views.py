from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils import timezone
from .models import UploadedFile, Stock, LivePrice, BacktestStrategy, BacktestResult, BacktestTrade, TradeOrder
from .services import fetch_live_price, fetch_historical_data
from .backtest_engine import BacktestEngine
# from django.db.models import Sum
from .utils import parse_uploaded_file
import pytz
import json
import pandas as pd
import numpy as np
# from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
import csv
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
import os
import requests
from django.db.models import Sum
import google.generativeai as genai
from django.http import JsonResponse
from datetime import timedelta
from django.db.models import Q
from .models import Stock, LivePrice,UserProfile
# from .utils import fetch_live_price
import yfinance as yf


@login_required(login_url='login')
def broker_settings(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. GROWW LOGIC (Strict Check)
        if action == 'save_groww':
            g_api = request.POST.get('groww_api_key', '').strip()
            g_secret = request.POST.get('groww_secret_key', '').strip()
            if g_api and g_secret:  # Dono hone chahiye
                profile.groww_api_key = g_api
                profile.groww_secret_key = g_secret
                profile.save()
                messages.success(request, "✅ Groww API Credentials saved successfully!")
            else:
                messages.error(request, "❌ Error: Groww API Key aur Secret Key dono mandatory hain!")

        elif action == 'remove_groww':
            profile.groww_api_key = None
            profile.groww_secret_key = None
            profile.save()
            messages.warning(request, "🗑️ Groww API Credentials removed.")

        # 2. DHAN LOGIC (Strict Check)
        elif action == 'save_dhan':
            d_client = request.POST.get('dhan_client_id', '').strip()
            d_token = request.POST.get('dhan_access_token', '').strip()
            if d_client and d_token:  # Dono hone chahiye
                profile.dhan_client_id = d_client
                profile.dhan_access_token = d_token
                profile.save()
                messages.success(request, "✅ Dhan API Credentials saved successfully!")
            else:
                messages.error(request, "❌ Error: Dhan Client ID aur Access Token dono mandatory hain!")

        elif action == 'remove_dhan':
            profile.dhan_client_id = None
            profile.dhan_access_token = None
            profile.save()
            messages.warning(request, "🗑️ Dhan API Credentials removed.")

        # 3. GEMINI AI LOGIC (Strict Check)
        elif action == 'save_gemini':
            gemini_key = request.POST.get('gemini_api_key', '').strip()
            if gemini_key:
                profile.gemini_api_key = gemini_key
                profile.save()
                messages.success(request, "✅ Gemini API Key saved successfully!")
            else:
                messages.error(request, "❌ Error: Gemini API Key cannot be empty!")

        elif action == 'remove_gemini':
            profile.gemini_api_key = None
            profile.save()
            messages.warning(request, "🗑️ Gemini API Key removed.")

        return redirect('broker_settings')

    return render(request, 'broker_settings.html', {'profile': profile})


@login_required(login_url='login')
def pro_algo_dashboard(request):
    # 🔥 THE SDE FIX: User ki watchlist se DB wale stocks fetch karo
    user_stocks = Stock.objects.filter(user=request.user)
    context = {'user_stocks': user_stocks}

    if request.method == 'POST':
        # Text box ki jagah ab multiple Checkboxes se data aayega, isliye getlist() use kiya hai
        selected_stocks = request.POST.getlist('stocks')
        qty = int(request.POST.get('qty', 1))
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')

        # Stocks ki list banao aur '.NS' add karo
        stock_list = [s.strip().upper() for s in selected_stocks if s.strip()]
        stock_list = [s + '.NS' if not s.endswith('.NS') else s for s in stock_list]

        if stock_list and start_date and end_date:
            try:
                data = yf.download(stock_list, start=start_date, end=end_date)

                # MultiIndex fix (Tumhara Data Engineer wala fix)
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)

                if len(stock_list) == 1:
                    open_df = data[['Open']].rename(columns={'Open': stock_list[0]})
                    close_df = data[['Close']].rename(columns={'Close': stock_list[0]})
                else:
                    open_df = data['Open']
                    close_df = data['Close']

                open_melt = open_df.reset_index().melt(id_vars='Date', var_name='Symbol', value_name='Open')
                close_melt = close_df.reset_index().melt(id_vars='Date', var_name='Symbol', value_name='Close')
                report_df = pd.merge(open_melt, close_melt, on=['Date', 'Symbol'])

                report_df['Open'] = report_df['Open'].round(2)
                report_df['Close'] = report_df['Close'].round(2)

                # Django template compatibility ke liye underscore (_) lagaya hai
                report_df['Buy_Value'] = (report_df['Open'] * qty).round(2)
                report_df['Sell_Value'] = (report_df['Close'] * qty).round(2)
                report_df['Profit'] = (report_df['Sell_Value'] - report_df['Buy_Value']).round(2)
                report_df['Date'] = report_df['Date'].dt.strftime('%d %b %Y')

                clean_report = report_df.dropna().sort_values(by=['Date', 'Symbol'])

                context['results'] = clean_report.to_dict('records')
                context['qty'] = qty
                context['total_profit'] = clean_report['Profit'].sum().round(2)
                context['searched_stocks'] = selected_stocks  # Jo check the unko wapas bhejo

            except Exception as e:
                context['error'] = f"Data fetch error: {str(e)}"

    return render(request, 'pro_algo.html', context)


@login_required(login_url='login')
def stock_detail(request, symbol):
    period = request.GET.get('period', '1d')
    interval = request.GET.get('interval', '1m')

    # 🔥 THE SDE FIX: Smart Auto-Corrector for Yahoo Finance Limits
    # Agar 10m fasa ho toh 15m kar do
    if interval == '10m':
        interval = '15m'

    # Agar period lamba hai (1 month se 1 year tak)
    if period in ['1mo', '3mo', '6mo', '1y']:
        # Aur interval bohot chota hai (1m, 5m, 15m, 30m, 1h), toh usko 1-Day candle me badal do
        if interval in ['1m', '2m', '5m', '15m', '30m', '1h']:
            interval = '1d'

            # YFinance se data uthao
    ticker = symbol + ".NS" if not symbol.endswith(".NS") else symbol
    data = yf.download(ticker, period=period, interval=interval)

    # 🔥 THE SDE FIX: Yahoo Finance ke MultiIndex columns ko flatten/clean karo
    # Isse Pandas ka float() error hamesha ke liye chala jayega
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    clean_candle_data = []
    clean_line_data = []
    details = {"open": 0, "high": 0, "low": 0, "close": 0}

    if not data.empty:
        # 🔥 THE SDE FIX 1: Convert Yahoo's UTC time to Indian Standard Time (IST)
        ist_tz = pytz.timezone('Asia/Kolkata')
        if data.index.tzinfo is None:
            data.index = data.index.tz_localize('UTC').tz_convert(ist_tz)
        else:
            data.index = data.index.tz_convert(ist_tz)

        details = {
            "open": round(float(data['Open'].iloc[-1]), 2),
            "high": round(float(data['High'].max()), 2),
            "low": round(float(data['Low'].min()), 2),
            "close": round(float(data['Close'].iloc[-1]), 2)
        }

        for index, row in data.iterrows():
            o = round(float(row['Open']), 2)
            h = round(float(row['High']), 2)
            l = round(float(row['Low']), 2)
            c = round(float(row['Close']), 2)

            # 🔥 THE SDE FIX: Date ko standard format me bhejo taaki ApexCharts usko Time samajh sake
            date_str = index.strftime('%Y-%m-%d %H:%M:%S')

            clean_candle_data.append({'x': date_str, 'y': [o, h, l, c]})
            clean_line_data.append({'x': date_str, 'y': c})

    context = {
        'symbol': symbol,
        'details': details,
        'current_period': period,
        'current_interval': interval,
        'candlestick_data': json.dumps(clean_candle_data),
        'line_data': json.dumps(clean_line_data)
    }

    return render(request, 'stock_detail.html', context)
# @login_required(login_url='login')
# def stock_detail(request, symbol):
#     # Dono parameters URL se aayenge
#     req_period = request.GET.get('period', '1mo')
#     req_interval = request.GET.get('interval', '1d')
#     yf_symbol = f"{symbol}.NS"
#
#     # 🔥 YFINANCE API RULES (Taaki chart crash na ho)
#     # 1 min candle sirf pichle 7 din ke data pe chalti hai
#     if req_interval == '1m' and req_period not in ['1d', '5d']:
#         req_period = '5d'
#         # 15 min aur 1 hour candle sirf pichle 60 din ke data pe chalti hai
#     elif req_interval in ['15m', '1h'] and req_period in ['6mo', '1y', '2y', '5y', 'max']:
#         req_period = '1mo'
#
#     try:
#         stock_data = yf.Ticker(yf_symbol)
#         hist = stock_data.history(period=req_period, interval=req_interval)
#
#         candlestick_data = []
#         line_data = []
#
#         if not hist.empty:
#             for date, row in hist.iterrows():
#                 # Agar interval chhota hai toh Date + Time dikhao, warna sirf Date
#                 if req_interval in ['1m', '15m', '1h']:
#                     date_str = date.strftime('%Y-%m-%d %H:%M')
#                 else:
#                     date_str = date.strftime('%Y-%m-%d')
#
#                 candlestick_data.append({
#                     'x': date_str,
#                     'y': [round(row['Open'], 2), round(row['High'], 2), round(row['Low'], 2), round(row['Close'], 2)]
#                 })
#                 line_data.append({
#                     'x': date_str,
#                     'y': round(row['Close'], 2)
#                 })
#
#             latest_details = {
#                 'open': round(hist['Open'].iloc[-1], 2),
#                 'high': round(hist['High'].iloc[-1], 2),
#                 'low': round(hist['Low'].iloc[-1], 2),
#                 'close': round(hist['Close'].iloc[-1], 2),
#                 'volume': int(hist['Volume'].iloc[-1]),
#             }
#         else:
#             raise ValueError("No data returned")
#
#     except Exception as e:
#         latest_details = {'open': 0, 'high': 0, 'low': 0, 'close': 0, 'volume': 0}
#         candlestick_data = []
#         line_data = []
#
#     context = {
#         'symbol': symbol,
#         'details': latest_details,
#         'candlestick_data': json.dumps(candlestick_data),
#         'line_data': json.dumps(line_data),
#         'current_period': req_period,  # UI ke liye
#         'current_interval': req_interval  # UI ke liye
#     }
#
#     return render(request, 'stock_detail.html', context)

def register_user(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('index')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})

def login_user(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('index')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})

def logout_user(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def index(request):
    # =========================================================================
    # 1. LIVE PRICE FETCHING LOGIC (🔥 UPDATED SDE LOGIC - SMART ROUTING & SELF-HEALING)
    # =========================================================================
    print("🚀🚀🚀 INDEX FUNCTION CHAL RAHA HAI! USER:", request.user)
    selected_stocks = Stock.objects.filter(user=request.user, is_selected=True)
    active_broker = request.session.get('active_broker', 'groww')
    profile = getattr(request.user, 'profile', None)

    # Key Validation check
    broker_error = None
    if active_broker == 'groww':
        if not profile or not profile.groww_api_key or not profile.groww_secret_key:
            broker_error = "Groww API Key Missing"
    elif active_broker == 'dhan':
        if not profile or not profile.dhan_client_id or not profile.dhan_access_token:
            broker_error = "Dhan API Key Missing"

    for stock in selected_stocks:
        exchange = stock.symbol_id if stock.symbol_id else 'NSE'

        # API Call with Smart Routing
        if broker_error:
            res = {'success': False, 'error': broker_error}
        else:
            if active_broker == 'dhan':
                # Dhan ko Security ID bhejo agar available hai
                if stock.security_id and str(stock.security_id).strip() != '-':
                    api_target = stock.security_id
                else:
                    api_target = stock.symbol
            else:
                # Groww/Others ko Symbol bhejo
                api_target = stock.symbol

            res = fetch_live_price(api_target, exchange, broker=active_broker)

        # Self-Healing Database Logic (Duplicate rows fix)
        if res.get('success'):
            price_val = str(res['ltp'])
        else:
            price_val = res.get('error', 'Not Found')

        try:
            LivePrice.objects.update_or_create(
                stock=stock,
                defaults={
                    'symbol': stock.symbol,
                    'symbol_id': stock.symbol_id,
                    'live_price': price_val
                }
            )
        except LivePrice.MultipleObjectsReturned:
            # Puraana duplicate kachra saaf karo
            LivePrice.objects.filter(stock=stock).delete()
            LivePrice.objects.create(
                stock=stock,
                symbol=stock.symbol,
                symbol_id=stock.symbol_id,
                live_price=price_val
            )

    # =========================================================================
    # 2. MAIN DASHBOARD STOCKS DATA (UNTOUCHED)
    # =========================================================================
    stocks_with_prices = []
    for stock in selected_stocks:
        latest_price = LivePrice.objects.filter(stock=stock).order_by('-fetched_at').first()
        formatted_time = "-"

        if latest_price:
            formatted_time = timezone.localtime(latest_price.fetched_at).strftime('%Y-%m-%d %I:%M:%S %p')
            if latest_price.live_price == "Not Found":
                latest_price.display_price = "Not Found"
            else:
                try:
                    latest_price.display_price = float(latest_price.live_price)
                except ValueError:
                    latest_price.display_price = latest_price.live_price
            latest_price.formatted_time = formatted_time

        stocks_with_prices.append({
            'stock': stock,
            'latest_price': latest_price
        })

    # =========================================================================
    # 3. ORDER HISTORY (TRADE BOOK) (UNTOUCHED)
    # =========================================================================
    my_orders = TradeOrder.objects.filter(user=request.user).order_by('-timestamp')

    # =========================================================================
    # 4. 🔥 ADVANCED PORTFOLIO & P&L CALCULATOR (UNTOUCHED)
    # =========================================================================
    traded_stocks = Stock.objects.filter(user=request.user, is_selected=True, tradeorder__isnull=False).distinct()
    my_holdings = []

    for stock in traded_stocks:
        orders = TradeOrder.objects.filter(stock=stock).order_by('timestamp')

        current_qty = 0
        total_cost = 0.0
        realized_pl = 0.0
        avg_price = 0.0

        for order in orders:
            qty = order.quantity
            price = float(order.price)

            if order.action == 'BUY':
                current_qty += qty
                total_cost += qty * price
                avg_price = total_cost / current_qty if current_qty > 0 else avg_price
            elif order.action == 'SELL':
                current_qty -= qty
                realized_pl += qty * (price - avg_price)
                total_cost -= qty * avg_price

                if current_qty <= 0:
                    total_cost = 0.0

        latest_price_obj = LivePrice.objects.filter(stock=stock).order_by('-fetched_at').first()
        live_price = 0.0
        unrealized_pl = 0.0

        if latest_price_obj and latest_price_obj.live_price != "Not Found":
            try:
                live_price = float(latest_price_obj.live_price)
                unrealized_pl = current_qty * (live_price - avg_price)
            except ValueError:
                pass

        total_pl = realized_pl + unrealized_pl

        r_pl = round(realized_pl, 2)
        ur_pl = round(unrealized_pl, 2)
        t_pl = round(total_pl, 2)

        if r_pl == 0: r_pl = abs(r_pl)
        if ur_pl == 0: ur_pl = abs(ur_pl)
        if t_pl == 0: t_pl = abs(t_pl)

        current_value = current_qty * live_price if current_qty > 0 else 0.0

        if current_qty > 0:
            my_holdings.append({
                'symbol': stock.symbol,
                'company_name': stock.company_name,
                'quantity': current_qty,
                'avg_price': round(avg_price, 2),
                'live_price': round(live_price, 2),
                'invested': round(current_qty * avg_price, 2) if current_qty > 0 else 0,
                'current_value': round(current_value, 2),
                'realized_pl': r_pl,
                'unrealized_pl': ur_pl,
                'total_pl': t_pl
            })

    return render(request, 'index.html', {
        'stocks_with_prices': stocks_with_prices,
        'my_orders': my_orders,
        'my_holdings': my_holdings
    })


def order_history(request):
    # Sirf order history ka data nikalenge
    my_orders = TradeOrder.objects.all().order_by('-timestamp')
    return render(request, 'order_history.html', {'my_orders': my_orders})


@login_required(login_url='login')
def ai_analyze_history(request, symbol):
    profile = getattr(request.user, 'profile', None)
    if not profile or not profile.gemini_api_key:
        return JsonResponse({"status": "error", "message": "Gemini API Key Missing! Please add it in Settings."})

    gemini_api_key = profile.gemini_api_key
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_api_key}"

    history_records = LivePrice.objects.filter(symbol=symbol).order_by('-fetched_at')[:30]

    if not history_records.exists():
        return JsonResponse({"status": "error", "message": f"No history found for {symbol}."})

    lines = ["Date/Time, Price"]
    for hr in history_records:
        time_str = timezone.localtime(hr.fetched_at).strftime('%Y-%m-%d %H:%M')
        lines.append(f"{time_str}, {hr.live_price}")
    recent_data = "\n".join(lines)

    prompt = f"""You are an expert stock market analyst. Analyze the following recent price history data for {symbol}.
    Recent Price Data:
    {recent_data}
    Please provide a comprehensive analysis strictly in HTML format (using <div>, <ul>, <li>, <strong>). DO NOT use Markdown formatting like ** or ```html.
    Include these 3 sections:
    1. 📰 Company Overview & Fundamentals
    2. 📈 Technical History Analysis
    3. 💡 Final Strategy/Verdict (Buy, Sell, or Hold)
    """

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        if response.status_code == 200:
            ai_text = data['candidates'][0]['content']['parts'][0]['text']

            # 🔥 FIX 2: Markdown tags ko remove (clean) kar rahe hain
            ai_text = ai_text.replace('```html', '').replace('```', '').strip()

            return JsonResponse({"status": "success", "analysis": ai_text})
        else:
            error_msg = data.get('error', {}).get('message', 'API Error')
            return JsonResponse({"status": "error", "message": error_msg})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)})


@csrf_exempt
@login_required(login_url='login')
def place_order(request):
    if request.method == 'POST':
        try:
            symbol = request.POST.get('symbol')
            action = request.POST.get('action')  # 'BUY' or 'SELL'
            quantity = int(request.POST.get('quantity', 1))

            # 🔥 FIX 1: get_object_or_404 ki jagah filter().first() (Duplicates se bachne ke liye)
            stock = Stock.objects.filter(symbol=symbol, user=request.user).first()
            if not stock:
                return JsonResponse({"status": "error", "message": f"Stock {symbol} not found in database."})

            # 1. Pata lagao current live price kya hai
            latest_price_obj = LivePrice.objects.filter(stock=stock).order_by('-fetched_at').first()
            if latest_price_obj and latest_price_obj.live_price != "Not Found":
                current_price = float(latest_price_obj.live_price)
            else:
                return JsonResponse({"status": "error", "message": "Live price not available. Please Fetch Live first."})

            # 🔥 🔥 NAYA LOGIC: HOLDINGS VALIDATION FOR SELL ORDER 🔥 🔥
            if action == 'SELL':
                total_bought = TradeOrder.objects.filter(stock=stock, action='BUY').aggregate(Sum('quantity'))['quantity__sum'] or 0
                total_sold = TradeOrder.objects.filter(stock=stock, action='SELL').aggregate(Sum('quantity'))['quantity__sum'] or 0
                current_holdings = total_bought - total_sold

                if quantity > current_holdings:
                    return JsonResponse({
                        "status": "error",
                        "message": f"❌ Insufficient Holdings! Aap {symbol} ke {quantity} shares nahi bech sakte. Aapke paas abhi sirf {current_holdings} shares hain."
                    })

            # 2. Agar BUY hai, ya SELL validation pass ho gayi, toh order save karo
            TradeOrder.objects.create(
                user=request.user,
                stock=stock,
                action=action,
                quantity=quantity,
                price=current_price
            )

            msg = f"✅ Successfully {action}ED {quantity} shares of {symbol} at ₹{current_price}"
            return JsonResponse({"status": "success", "message": msg})

        except Exception as e:
            # 🔥 FIX 2: Agar code fatega tab bhi JSON me hi frontend ko pata chalega
            print(f"ORDER ERROR: {str(e)}")
            return JsonResponse({"status": "error", "message": f"Server Error: {str(e)}"})

    return JsonResponse({"status": "error", "message": "Invalid Request"})


def fetch_live_prices(request):
    # Sirf is user ke selected stocks uthao
    selected_stocks = Stock.objects.filter(user=request.user, is_selected=True)
    results = []

    # Active broker check karo (default 'groww' rakha hai)
    active_broker = request.session.get('active_broker', 'groww')
    profile = getattr(request.user, 'profile', None)

    # =========================================================
    # 🔥 SDE LOGIC: Broker Key Validation
    # =========================================================
    broker_error = None
    if active_broker == 'groww':
        if not profile or not profile.groww_api_key or not profile.groww_secret_key:
            broker_error = "Groww API Key Missing"
    elif active_broker == 'dhan':
        if not profile or not profile.dhan_client_id or not profile.dhan_access_token:
            broker_error = "Dhan API Key Missing"

    for stock in selected_stocks:
        exchange = stock.symbol_id if stock.symbol_id else 'NSE'

        # Agar API key missing hai toh sidha error throw karo, API call mat karo
        if broker_error:
            res = {'success': False, 'error': broker_error}
        else:
            # =========================================================
            # 🔥 THE SDE FIX: Smart Identifier Routing (Symbol vs ID)
            # =========================================================
            if active_broker == 'dhan':
                # Dhan ko strictly Security ID chahiye
                if stock.security_id and str(stock.security_id).strip() != '-':
                    api_target = stock.security_id
                    res = fetch_live_price(api_target, exchange, broker=active_broker)
                else:
                    res = {'success': False, 'error': 'Dhan Security ID Missing in DB'}
            else:
                # Groww (aur baaki sab) ko normal Symbol chahiye (e.g., 'RELIANCE')
                api_target = stock.symbol
                res = fetch_live_price(api_target, exchange, broker=active_broker)

        # =========================================================
        # 🔥 THE DATABASE EXPLODER FIX: Self-Healing Logic
        # =========================================================
        if res.get('success'):
            price_val = str(res['ltp'])
            display_price = float(price_val)
        else:
            price_val = res.get('error', 'Not Found')
            display_price = price_val

        try:
            # Normal tareeke se price update karne ki koshish
            lp, created = LivePrice.objects.update_or_create(
                stock=stock,
                defaults={
                    'symbol': stock.symbol,
                    'symbol_id': stock.symbol_id,
                    'live_price': price_val
                }
            )
        except LivePrice.MultipleObjectsReturned:
            # Agar purana duplicate kachra (5+ rows) fasa hua hai, toh sabko uda do
            LivePrice.objects.filter(stock=stock).delete()

            # Aur ek fresh, single clean row bana do
            lp = LivePrice.objects.create(
                stock=stock,
                symbol=stock.symbol,
                symbol_id=stock.symbol_id,
                live_price=price_val
            )

        # Time format set karo dashboard par dikhane ke liye
        display_time = timezone.localtime(lp.fetched_at).strftime('%Y-%m-%d %I:%M:%S %p')

        # Frontend bhejne ke liye list mein add karo
        results.append({
            "symbol": stock.symbol,
            "price": display_price,
            "fetched_at": display_time
        })

    # JSON response wapas bhej do
    return JsonResponse({"status": "success", "count": len(results), "prices": results})


@login_required(login_url='login')
def upload_excel(request):
    if request.method == 'POST':
        if 'file' not in request.FILES:
            messages.error(request, 'Please select a file to upload.')
            return redirect('upload_excel')

        excel_file = request.FILES['file']

        try:
            if excel_file.name.endswith('.csv'):
                df = pd.read_csv(excel_file)
            else:
                df = pd.read_excel(excel_file)

            # 🔥 THE SDE FIX: Poora table ekdam saaf karo taaki purane (blank ID) wale stocks screen par na aaye
            Stock.objects.all().delete()

            count = 0
            seen_symbols = set()

            for index, row in df.iterrows():
                stock_name = str(row.get('Stock Name', '')).strip()
                symbol = str(row.get('Symbol', '')).strip()
                symbol_id = str(row.get('Symbol ID', 'NSE')).strip()

                # Nayi ID nikalne ka solid logic
                raw_sec_id = row.get('SEM_SMST_SECURITY_ID', '')
                sec_id = ''

                # Check for NaN and empty strings
                if pd.notna(raw_sec_id) and str(raw_sec_id).strip() != '':
                    try:
                        sec_id = str(int(float(raw_sec_id)))
                    except ValueError:
                        sec_id = str(raw_sec_id).strip()

                if pd.isna(symbol) or symbol == 'nan' or not symbol:
                    continue

                if symbol in seen_symbols:
                    continue

                seen_symbols.add(symbol)

                # 🔥 TERMINAL DEBUG: Sirf pehle 5 stocks check karne ke liye print karo
                if count < 5:
                    print(f"👉 Stock: {symbol} | Extracted ID: {sec_id}")

                Stock.objects.create(
                    user=request.user,
                    symbol=symbol,
                    company_name=stock_name,
                    symbol_id=symbol_id,
                    security_id=sec_id
                )
                count += 1

            messages.success(request, f'✅ Database flushed. {count} new stocks with IDs uploaded successfully!')
            return redirect('select_stocks')

        except Exception as e:
            messages.error(request, f'❌ Error processing file: {str(e)}')
            return redirect('upload_excel')

    return render(request, 'upload.html')


@login_required(login_url='login')
def fetch_single_live_price(request, symbol):
    stock = Stock.objects.filter(user=request.user, symbol=symbol).first()
    if not stock:
        return JsonResponse({"status": "error", "message": "Stock not found in your watchlist."})

    active_broker = request.session.get('active_broker', 'groww')
    profile = getattr(request.user, 'profile', None)

    # =========================================================
    # 🔥 SDE LOGIC: Broker Key Validation
    # =========================================================
    broker_error = None
    if active_broker == 'groww':
        if not profile or not profile.groww_api_key or not profile.groww_secret_key:
            broker_error = "Groww API Key Missing"
    elif active_broker == 'dhan':
        if not profile or not profile.dhan_client_id or not profile.dhan_access_token:
            broker_error = "Dhan API Key Missing"

    exchange = stock.symbol_id if stock.symbol_id else 'NSE'

    if broker_error:
        res = {'success': False, 'error': broker_error}
    else:
        # =========================================================
        # 🔥 THE SDE FIX: Smart Identifier Routing (Symbol vs ID)
        # =========================================================
        if active_broker == 'dhan':
            # Dhan ko strictly Security ID chahiye
            if stock.security_id and str(stock.security_id).strip() != '-':
                api_target = stock.security_id
                res = fetch_live_price(api_target, exchange, broker=active_broker)
            else:
                res = {'success': False, 'error': 'Dhan Security ID Missing in DB'}
        else:
            # Groww ko Symbol chahiye
            api_target = stock.symbol
            res = fetch_live_price(api_target, exchange, broker=active_broker)

    # =========================================================
    # 🔥 THE DATABASE EXPLODER FIX: Self-Healing Logic
    # =========================================================
    if res.get('success'):
        price_val = str(res['ltp'])
        display_price = float(price_val)
    else:
        price_val = res.get('error', 'Not Found')
        display_price = price_val

    try:
        # Puraana price update karne ki normal koshish
        lp, created = LivePrice.objects.update_or_create(
            stock=stock,
            defaults={
                'symbol': stock.symbol,
                'symbol_id': stock.symbol_id,
                'live_price': price_val
            }
        )
    except LivePrice.MultipleObjectsReturned:
        # Agar glitch ki wajah se duplicates ban gaye the, toh sab saaf kardo
        LivePrice.objects.filter(stock=stock).delete()

        # Aur ek fresh clean row bana do
        lp = LivePrice.objects.create(
            stock=stock,
            symbol=stock.symbol,
            symbol_id=stock.symbol_id,
            live_price=price_val
        )

    display_time = timezone.localtime(lp.fetched_at).strftime('%Y-%m-%d %I:%M:%S %p')

    return JsonResponse({
        "status": "success",
        "price": display_price,
        "fetched_at": display_time
    })
# @login_required(login_url='login')
# def upload_excel(request):
#     if request.method == 'POST':
#         # Check if file is in the request
#         if 'file' not in request.FILES:
#             messages.error(request, 'Please select a file to upload.')
#             return redirect('upload_excel')  # Yahan apne URL ka naam check kar lena
#
#         excel_file = request.FILES['file']
#
#         try:
#             # Pandas se file read karo (CSV ya Excel dono handle karega)
#             if excel_file.name.endswith('.csv'):
#                 df = pd.read_csv(excel_file)
#             else:
#                 df = pd.read_excel(excel_file)
#
#             count = 0
#             for index, row in df.iterrows():
#                 # DataFrame se data nikaalo
#                 stock_name = str(row.get('Stock Name', '')).strip()
#                 symbol = str(row.get('Symbol', '')).strip()
#                 symbol_id = str(row.get('Symbol ID', 'NSE')).strip()  # Default NSE
#
#                 # Agar symbol empty hai toh skip karo
#                 if pd.isna(symbol) or symbol == 'nan' or not symbol:
#                     continue
#
#                 # 🔥 THE SDE FIX: get() ki jagah filter().first() use kiya!
#                 stock = Stock.objects.filter(symbol=symbol, user=request.user).first()
#
#                 if stock:
#                     # Agar stock pehle se hai, toh usko update kar do
#                     stock.company_name = stock_name
#                     stock.symbol_id = symbol_id
#                     stock.save()
#                 else:
#                     # Agar stock nahi hai, toh naya create karo
#                     Stock.objects.create(
#                         user=request.user,
#                         symbol=symbol,
#                         company_name=stock_name,
#                         symbol_id=symbol_id
#                     )
#                 count += 1
#
#             messages.success(request, f'✅ Successfully processed {count} stocks!')
#             return redirect('select_stocks')  # Upload hone ke baad jahan bhejna ho wahan ka URL name
#
#         except Exception as e:
#             messages.error(request, f'❌ Error processing file: {str(e)}')
#             return redirect('upload_excel')
#
#     return render(request, 'upload.html')


@login_required(login_url='login')
def select_stocks(request):
    current_exchange = request.GET.get('exchange', 'ALL').upper()

    # ==========================================
    # 🔥 POST REQUEST (Saving Data)
    # ==========================================
    if request.method == 'POST':
        form_exchange = request.POST.get('exchange_filter', 'ALL').upper()

        # FIX 1: HTML se Symbols aayenge, IDs nahi!
        selected_symbols = request.POST.getlist('selected_stocks')

        # 1. Puraane selections hatao (Sirf current user ke account se)
        if form_exchange in ['NSE', 'BSE']:
            Stock.objects.filter(user=request.user, symbol_id__iexact=form_exchange).update(is_selected=False)
        else:
            Stock.objects.filter(user=request.user).update(is_selected=False)

        # 2. Jo Symbols select hue hain, unko Current User ke liye Save/Update karo
        if selected_symbols:
            for sym in selected_symbols:
                # get_or_create: Agar user ke paas ye stock pehle se hai toh utha lo, warna naya banao
                user_stock, created = Stock.objects.get_or_create(
                    user=request.user,
                    symbol=sym,
                    defaults={
                        'company_name': 'EQUITY',  # Default name
                        'symbol_id': 'NSE',
                        'is_selected': True
                    }
                )
                # Agar pehle se tha (created=False), toh bas flag True kar do
                if not created:
                    user_stock.is_selected = True
                    user_stock.save()

        # 3. Save hote hi live price fetch karo (Sirf is user ke liye)
        new_selected_stocks = Stock.objects.filter(user=request.user, is_selected=True)
        active_broker = request.session.get('active_broker', 'groww')

        for stock in new_selected_stocks:
            exchange = stock.symbol_id if stock.symbol_id else 'NSE'

            # Tumhara Live price fetch function
            res = fetch_live_price(stock.symbol, exchange, broker=active_broker)

            # Agar price mila toh price daalo, warna "Not Found"
            price_to_save = str(res['ltp']) if res.get('success') else "Not Found"

            # FIX 2: update_or_create -> Isse duplicate rows nahi banengi!
            LivePrice.objects.update_or_create(
                stock=stock,
                defaults={
                    'symbol': stock.symbol,
                    'symbol_id': stock.symbol_id,
                    'live_price': price_to_save
                }
            )

        messages.success(request, "Stock selection saved successfully.")
        return redirect('index')

    # ==========================================
    # 🔥 GET REQUEST: SMART UNIQUE STOCK FETCHER
    # ==========================================

    # Tumhara dedup logic ekdum sahi kaam karega
    all_stocks_query = Stock.objects.all().order_by('symbol')
    if current_exchange in ['NSE', 'BSE']:
        all_stocks_query = all_stocks_query.filter(symbol_id__iexact=current_exchange)

    # Duplicate hatane ka logic (taaki list me ek stock 2 baar na dikhe)
    unique_stocks = []
    seen_symbols = set()

    for stock in all_stocks_query:
        if stock.symbol not in seen_symbols:
            seen_symbols.add(stock.symbol)
            unique_stocks.append(stock)

    # Current user ne kaun se stocks tick kiye hue hain, unki list nikaalo
    user_selected_symbols = set(
        Stock.objects.filter(user=request.user, is_selected=True).values_list('symbol', flat=True)
    )

    # List mein checkmark (tick) set karo frontend ke liye
    for stock in unique_stocks:
        if stock.symbol in user_selected_symbols:
            stock.is_selected = True
        else:
            stock.is_selected = False

    selected_count = len(user_selected_symbols)

    return render(request, 'select_stocks.html', {
        'available_stocks': unique_stocks,  # Dhyan rakhna HTML me 'available_stocks' loop ho raha tha
        'selected_count': selected_count,
        'current_exchange': current_exchange
    })


# def fetch_live_prices(request):
#     selected_stocks = Stock.objects.filter(is_selected=True)
#     results = []
#
#     active_broker = request.session.get('active_broker', 'groww')
#
#     for stock in selected_stocks:
#         exchange = stock.symbol_id if stock.symbol_id else 'NSE'
#
#         # API call
#         res = fetch_live_price(stock.symbol, exchange, broker=active_broker)
#
#         print(f"[{stock.symbol}] API Response:", res)
#
#         if res.get('success'):
#             # Agar price mil gayi toh database me save karo aur real data bhejo
#             lp = LivePrice.objects.create(
#                 stock=stock,
#                 symbol=stock.symbol,
#                 symbol_id=stock.symbol_id,
#                 live_price=res['ltp']
#             )
#             results.append({
#                 "symbol": stock.symbol,
#                 "price": float(lp.live_price),
#                 'fetched_at': timezone.localtime(lp.fetched_at).strftime('%Y-%m-%d %I:%M:%S %p'),
#             })
#         else:
#             # 🔥 FIX: Agar API fail ho gayi toh purani price nahi, "Not Found" bhejo
#             print(f"❌ Failed to save {stock.symbol}:", res.get('error', 'API Error'))
#             results.append({
#                 "symbol": stock.symbol,
#                 "price": "Not Found",  # Frontend par 'Not Found' dikhega
#                 "fetched_at": "Failed"  # Time ki jagah 'Failed' dikhega
#             })
#
#     return JsonResponse({"status": "success", "count": len(results), "prices": results})

def get_latest_prices(request):
    selected_stocks = Stock.objects.filter(is_selected=True)
    prices = []
    for stock in selected_stocks:
        lp = LivePrice.objects.filter(stock=stock).order_by('-fetched_at').first()
        if lp:
            # 🔥 FIX: Agar convert ho sake to Number banao, warna Text hi rehne do
            try:
                price_val = float(lp.live_price)
            except ValueError:
                price_val = lp.live_price  # Ye seedha "Not Found" assign kar dega

            prices.append({
                "symbol": stock.symbol,
                "company_name": stock.company_name,
                "symbol_id": stock.symbol_id,
                "live_price": price_val,
                'fetched_at': timezone.localtime(lp.fetched_at).strftime('%Y-%m-%d %I:%M:%S %p'),
            })
    return JsonResponse(prices, safe=False)


@login_required(login_url='login')
def price_history(request, symbol):
    # 🔥 SDE FIX: get() ki jagah filter().first() use kiya
    # Taaki agar 3 SUZLON ho toh pehla wala utha le aur crash na ho
    stock = Stock.objects.filter(symbol=symbol, user=request.user).first()

    # Agar is user ka nahi mila, toh global database se pehla utha lo
    if not stock:
        stock = Stock.objects.filter(symbol=symbol).first()

    # LivePrice ko stock object ki jagah seedha symbol string se filter karo
    # Taaki saari history mil jaye, chahe kisi bhi duplicate stock se judi ho
    history = LivePrice.objects.filter(symbol=symbol).order_by('-fetched_at')[:100]

    return render(request, 'price_history.html', {'stock': stock, 'history': history})
# def price_history(request, symbol):
#     stock = get_object_or_404(Stock, symbol=symbol)
#     history = LivePrice.objects.filter(stock=stock).order_by('-fetched_at')[:100]
#     return render(request, 'price_history.html', {'stock': stock, 'history': history})


@login_required(login_url='login')
def ai_analyze_stocks_gemini(request):
    try:
        profile = getattr(request.user, 'profile', None)
        if not profile or not profile.gemini_api_key:
            return JsonResponse({"status": "error", "message": "Gemini API Key Missing! Please add it in Settings."})

        gemini_api_key = profile.gemini_api_key
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_api_key}"

        # 🔥 FIX 1: is_selected hataya (in case us wajah se DB error aa raha ho)
        # Ab sirf wahi stocks uthayega jo user ke hain aur jinka symbol valid hai
        stocks = Stock.objects.filter(user=request.user)
        unique_symbols = list(set([stock.symbol for stock in stocks if stock.symbol]))

        if not unique_symbols:
            return JsonResponse({"status": "error", "message": "No stocks in watchlist to analyze."})

        results = []
        for symbol in unique_symbols:
            history_records = LivePrice.objects.filter(symbol=symbol).order_by('-fetched_at')[:30]
            if not history_records.exists():
                continue

            lines = ["Date/Time, Price"]
            for hr in history_records:
                time_str = timezone.localtime(hr.fetched_at).strftime('%Y-%m-%d %H:%M')
                lines.append(f"{time_str}, {hr.live_price}")
            recent_data = "\n".join(lines)

            prompt = f"""You are an expert stock market analyst. Analyze the following recent price history data for {symbol}.
            Recent Price Data:
            {recent_data}
            Please provide a comprehensive analysis strictly in HTML format (using <div>, <ul>, <li>, <strong>). DO NOT use Markdown formatting like ** or ```html.
            Include these 3 sections:
            1. 📰 Company Overview & Fundamentals
            2. 📈 Technical History Analysis
            3. 💡 Final Strategy/Verdict (Buy, Sell, or Hold)
            """

            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            headers = {'Content-Type': 'application/json'}

            response = requests.post(url, json=payload, headers=headers)
            data = response.json()

            if response.status_code == 200:
                # Safe JSON parsing to prevent KeyError
                ai_text = data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                ai_text = ai_text.replace('```html', '').replace('```', '').strip()
                results.append({"symbol": symbol, "analysis": ai_text})
            else:
                error_msg = data.get('error', {}).get('message', 'Unknown API Error')
                results.append(
                    {"symbol": symbol, "analysis": f"<div class='alert alert-danger'>API Error: {error_msg}</div>"})

        return JsonResponse({"status": "success", "data": results})

    except Exception as e:
        # 🔥 FIX 2: Agar backend fategi toh ab JS ko pata chal jayega
        print(f"BULK AI ERROR: {str(e)}")
        return JsonResponse({"status": "error", "message": f"Backend Error: {str(e)}"})

@login_required(login_url='login')
def backtest_dashboard(request):
    strategies = BacktestStrategy.objects.prefetch_related('results').all().order_by('-created_at')
    strategy_data = []
    for s in strategies:
        result = s.results.order_by('-executed_at').first()
        strategy_data.append({
            'strategy': s,
            'result': result
        })
    return render(request, 'backtest_dashboard.html', {'strategy_data': strategy_data})


@login_required(login_url='login')
def backtesting(request):
    context = {}

    # Dropdown ke liye user ke selected stocks bhejo
    user_stocks = Stock.objects.filter(user=request.user, is_selected=True)
    context['user_stocks'] = user_stocks

    if request.method == 'POST':
        symbol = request.POST.get('symbol')
        strategy_req = request.POST.get('strategy')
        period = request.POST.get('period', '1y')

        yf_symbol = f"{symbol}.NS"

        try:
            # 1. Market Data Fetch Karo
            df = yf.Ticker(yf_symbol).history(period=period)
            if df.empty:
                context['error'] = f"No data found for {symbol}."
                return render(request, 'backtesting.html', context)

            # Daily market return (Buy & Hold benchmark)
            df['Market_Return'] = df['Close'].pct_change()
            buy_hold_return = ((1 + df['Market_Return']).cumprod().iloc[-1] - 1) * 100

            # 2. Strategy Logic Functions (Vectorized for high speed)
            def run_sma_crossover(data):
                temp = data.copy()
                temp['SMA20'] = temp['Close'].rolling(20).mean()
                temp['SMA50'] = temp['Close'].rolling(50).mean()
                temp['Signal'] = np.where(temp['SMA20'] > temp['SMA50'], 1, 0)
                temp['Position'] = temp['Signal'].shift(1)
                temp['Strategy_Return'] = temp['Position'] * temp['Market_Return']
                net_return = ((1 + temp['Strategy_Return']).cumprod().iloc[-1] - 1) * 100
                return round(net_return, 2)

            def run_ema_crossover(data):
                temp = data.copy()
                temp['EMA9'] = temp['Close'].ewm(span=9, adjust=False).mean()
                temp['EMA21'] = temp['Close'].ewm(span=21, adjust=False).mean()
                temp['Signal'] = np.where(temp['EMA9'] > temp['EMA21'], 1, 0)
                temp['Position'] = temp['Signal'].shift(1)
                temp['Strategy_Return'] = temp['Position'] * temp['Market_Return']
                net_return = ((1 + temp['Strategy_Return']).cumprod().iloc[-1] - 1) * 100
                return round(net_return, 2)

            def run_momentum(data):
                temp = data.copy()
                temp['SMA20'] = temp['Close'].rolling(20).mean()
                temp['Signal'] = np.where(temp['Close'] > temp['SMA20'], 1, 0)
                temp['Position'] = temp['Signal'].shift(1)
                temp['Strategy_Return'] = temp['Position'] * temp['Market_Return']
                net_return = ((1 + temp['Strategy_Return']).cumprod().iloc[-1] - 1) * 100
                return round(net_return, 2)

            # 3. Execution Engine
            results = []
            buy_hold_return = round(buy_hold_return, 2)

            # Dictionary of all available strategies
            all_strategies = {
                'SMA_CROSS': {'name': 'SMA Crossover (20 vs 50)', 'func': run_sma_crossover},
                'EMA_CROSS': {'name': 'EMA Crossover (9 vs 21)', 'func': run_ema_crossover},
                'MOMENTUM': {'name': 'Price Momentum (Close > SMA20)', 'func': run_momentum},
            }

            # Agar user ne 'ALL' select kiya hai, toh loop chalao
            if strategy_req == 'ALL':
                for key, strat in all_strategies.items():
                    strat_return = strat['func'](df)
                    results.append({
                        'name': strat['name'],
                        'return': strat_return,
                        'beats_market': strat_return > buy_hold_return
                    })
            else:
                # Sirf ek strategy run karo
                if strategy_req in all_strategies:
                    strat = all_strategies[strategy_req]
                    strat_return = strat['func'](df)
                    results.append({
                        'name': strat['name'],
                        'return': strat_return,
                        'beats_market': strat_return > buy_hold_return
                    })

            # Highest return ke hisab se sort karo
            results = sorted(results, key=lambda x: x['return'], reverse=True)

            context.update({
                'symbol': symbol,
                'period': period,
                'buy_hold_return': buy_hold_return,
                'results': results,
                'is_all': strategy_req == 'ALL'
            })

        except Exception as e:
            context['error'] = f"Backtesting failed: {str(e)}"

    return render(request, 'backtesting.html', context)
# @login_required(login_url='login')
def backtest_create(request):
    stocks = Stock.objects.filter(is_selected=True).order_by('symbol')

    if request.method == 'POST':
        stock_id = request.POST.get('stock_id')
        strategy_type = request.POST.get('strategy_type')
        name = request.POST.get('name')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        initial_capital = request.POST.get('initial_capital', 100000)

        stock = get_object_or_404(Stock, id=stock_id)

        # 1. Data Fetch Karo
        df = fetch_historical_data(stock.symbol, start_date, end_date)
        if df.empty:
            messages.error(request, f"Failed to fetch historical data for {stock.symbol}.")
            return redirect('backtest_create')

        # 2. 🔥 1-MONTH FRIENDLY SHORT-TERM PARAMETERS FORCING
        # Data chhota hai, isliye periods ko chhota rakhna padega taaki crash na ho
        params = {
            'fast_period': 3,  # 3-day Fast EMA/SMA
            'slow_period': 10,  # 10-day Slow EMA/SMA (1 mahine me aaram se chalega)
            'signal_period': 5,
            'rsi_period': 7,  # 7-day Short RSI
            'rsi_overbought': 70,
            'rsi_oversold': 30,
            'bb_period': 10,  # 10-day Bollinger Bands
            'bb_std': 2.0
        }

        # 3. 🔥 STRATEGIES LIST DEFINITIONS
        # Agar user ne 'ALL' select kiya hai, toh individual short-term bhi chalenge aur ek MIX bhi chalega
        if strategy_type == 'ALL':
            strategies_to_run = ['SMA', 'EMA', 'RSI', 'MACD', 'BollingerBands', 'MIX']
        else:
            strategies_to_run = [strategy_type]

        last_result_pk = None
        successful_runs = 0

        # 4. ENGINE LOOP
        for strat_name in strategies_to_run:
            display_name = f"{name} - {strat_name}" if strategy_type == 'ALL' else name
            if strat_name == 'MIX':
                display_name = f"ALL MIX STRATEGY"

            # Database entry banao
            strategy = BacktestStrategy.objects.create(
                name=display_name,
                strategy_type=strat_name,
                stock=stock,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                param_fast_period=params['fast_period'],
                param_slow_period=params['slow_period'],
                param_signal_period=params['signal_period'],
                param_rsi_period=params['rsi_period'],
                param_rsi_overbought=params['rsi_overbought'],
                param_rsi_oversold=params['rsi_oversold'],
                param_bb_period=params['bb_period'],
                param_bb_std=params['bb_std']
            )

            # 🔥 SDE TWEAK FOR MIXED STRATEGY:
            # Agar tumhare backtest_engine.py me 'MIX' written nahi hai, toh hum engine chalane se pehle
            # engine ko bolenge ki wo 'EMA' ya 'SMA' ka calculation kare, ya jo bhi default engine handle kar sake.
            # (Agar tumne engine me MIX ka logic likha hai toh ye seedha strat_name pass karega)
            engine_strat = strat_name
            if strat_name == 'MIX':
                # Agar custom MIX logic engine me nahi hai, toh temporary base strategy set kar sakte ho
                # Ya fir custom calculations vector use kar sakte ho. Let's pass it to engine.
                engine_strat = 'MIX'

                # Engine Execution
            try:
                engine = BacktestEngine(df, float(initial_capital), engine_strat, params)
                metrics = engine.run()
            except Exception as engine_err:
                metrics = {"error": str(engine_err)}

            # Agar crash ho jaye toh entry delete karke aage badho
            if "error" in metrics:
                strategy.delete()
                print(f"❌ Strategy {strat_name} failed: {metrics['error']}")
                continue

            # Result save karo
            result = BacktestResult.objects.create(
                strategy=strategy,
                total_trades=metrics['total_trades'],
                winning_trades=metrics['winning_trades'],
                losing_trades=metrics['losing_trades'],
                win_rate=metrics['win_rate'],
                total_return_pct=metrics['total_return_pct'],
                total_profit_loss=metrics['total_profit_loss'],
                max_drawdown_pct=metrics['max_drawdown_pct'],
                sharpe_ratio=metrics['sharpe_ratio'],
                initial_capital=initial_capital,
                final_capital=metrics['final_capital'],
                best_trade_pct=metrics['best_trade_pct'],
                worst_trade_pct=metrics['worst_trade_pct'],
                avg_trade_pct=metrics['avg_trade_pct'],
                equity_curve_json=json.dumps(metrics['equity_curve'])
            )

            # Trades save karo
            for t in metrics['trades']:
                BacktestTrade.objects.create(
                    result=result,
                    trade_type=t['trade_type'],
                    entry_date=t['entry_date'],
                    exit_date=t['exit_date'],
                    entry_price=t['entry_price'],
                    exit_price=t['exit_price'],
                    quantity=t['quantity'],
                    profit_loss=t['profit_loss'],
                    profit_loss_pct=t['profit_loss_pct']
                )

            last_result_pk = result.pk
            successful_runs += 1

        # Response handling
        if successful_runs == 0:
            messages.error(request,
                           "Backtest failed! 1 Month data is too short for these periods. Try lowering values.")
            return redirect('backtest_create')

        elif strategy_type == 'ALL':
            messages.success(request,
                             f"Successfully generated {successful_runs} strategies on 1-Month Data including ALL MIX!")
            return redirect('backtest_dashboard')
        else:
            messages.success(request, "Backtest completed successfully.")
            return redirect('backtest_result', pk=last_result_pk)

    return render(request, 'backtest_create.html', {'stocks': stocks})


def backtest_result(request, pk):
    result = get_object_or_404(BacktestResult.objects.select_related('strategy__stock'), pk=pk)
    trades = BacktestTrade.objects.filter(result=result).order_by('entry_date')
    return render(request, 'backtest_result.html', {
        'result': result,
        'trades': trades,
        'equity_curve_json': result.equity_curve_json
    })


def backtest_delete(request, pk):
    strategy = get_object_or_404(BacktestStrategy, pk=pk)
    strategy.delete()
    messages.success(request, "Backtest strategy deleted successfully.")
    return redirect('backtest_dashboard')


def backtest_compare(request):
    ids_str = request.GET.get('ids', '')
    if not ids_str:
        messages.error(request, "No backtests selected for comparison.")
        return redirect('backtest_dashboard')

    try:
        ids = [int(i) for i in ids_str.split(',')]
        results = BacktestResult.objects.filter(id__in=ids).select_related('strategy__stock')
    except ValueError:
        messages.error(request, "Invalid comparison IDs.")
        return redirect('backtest_dashboard')

    return render(request, 'backtest_compare.html', {'results': results})


@login_required(login_url='login')
def backtest_bulk_delete(request):
    if request.method == 'POST':
        ids_str = request.POST.get('ids', '')
        if ids_str:
            ids_list = [int(i) for i in ids_str.split(',') if i.isdigit()]

            # 🔥 SDE FIX: Hum Django ka default Cascade count nahi dikhayenge
            # Hum wahi count dikhayenge jitni strategies user ne select ki thi
            actual_count = len(ids_list)

            # Database se delete maro
            BacktestStrategy.objects.filter(id__in=ids_list).delete()

            messages.success(request, f"Successfully deleted {actual_count} backtest strategies!")
        else:
            messages.error(request, "No backtests selected for deletion.")

    return redirect('backtest_dashboard')

def download_trades_csv(request, pk):
    result = get_object_or_404(BacktestResult, pk=pk)
    trades = BacktestTrade.objects.filter(result=result).order_by('entry_date')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="trades_{pk}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Trade Type', 'Entry Date', 'Exit Date', 'Entry Price', 'Exit Price', 'Quantity', 'P&L', 'P&L%'])

    for t in trades:
        writer.writerow([
            t.trade_type,
            t.entry_date,
            t.exit_date,
            t.entry_price,
            t.exit_price,
            t.quantity,
            t.profit_loss,
            t.profit_loss_pct
        ])

    return response


def set_broker(request, broker):
    if broker.lower() in ['groww', 'dhan']:
        request.session['active_broker'] = broker.lower()
        messages.success(request, f"Broker successfully switched to {broker.upper()}!")
    return redirect(request.META.get('HTTP_REFERER', 'index'))


def remove_stock(request, stock_id):
    stock = get_object_or_404(Stock, id=stock_id)
    stock.is_selected = False
    stock.save()
    messages.info(request, f"{stock.symbol} removed from dashboard.")
    return redirect('index')