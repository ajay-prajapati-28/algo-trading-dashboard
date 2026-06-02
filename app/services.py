import requests
import pandas as pd
from dhanhq import dhanhq,DhanContext
from datetime import datetime
import yfinance as yf
import os
from growwapi import GrowwAPI

GROWW_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://groww.in/",
    "Origin": "https://groww.in"
}

_groww_client = None


def get_groww_client():
    global _groww_client
    if _groww_client is None:

        grow_api_key = os.getenv('GROW_API_KEY')
        grow_secret_key = os.getenv('GROW_SECRET_KEY')
        try:
            access_token = GrowwAPI.get_access_token(api_key=grow_api_key, secret=grow_secret_key)
            _groww_client = GrowwAPI(access_token)
            print("✅ Groww API Connected")
        except Exception as e:
            print(f"❌ Groww Login Error: {e}")
            return None
    return _groww_client


import os
from datetime import datetime, timedelta


# Ensure DhanContext, dhanhq, get_groww_client are imported at the top of your services.py file

def fetch_live_price(symbol: str, exchange: str = 'NSE', broker: str = 'groww', security_id: str = None):
    broker = broker.lower()

    # ==================== DHAN LOGIC ====================
    if broker == 'dhan':
        try:
            print(f"🟣 [DHAN API] Requesting {symbol}...")

            # API Keys Initialization
            from django.contrib.auth.models import User

            # Database se pehle user ko uthao (Agar tumhara personal algo dashboard hai)
            first_user = User.objects.first()

            if not first_user or not hasattr(first_user, 'profile'):
                print("⚠️ User Profile nahi mili Database mein!")
                return {'success': False, 'error': "User Profile missing", 'symbol': symbol}

            dhan_client_id = first_user.profile.dhan_client_id
            dhan_access_token = first_user.profile.dhan_access_token

            if not dhan_client_id or not dhan_access_token:
                print("⚠️ Dhan API Keys Database mein empty hain!")
                return {'success': False, 'error': "Dhan API Keys missing in Profile", 'symbol': symbol}

            # Ab in DB wali keys se Dhan client initialize karo
            dhan_context = DhanContext(dhan_client_id, dhan_access_token)
            dhan = dhanhq(dhan_context)

            # 🔥 STEP 1: SMART ID ROUTING
            if str(symbol).isdigit():
                dhan_sec_id = str(symbol)
            else:
                from app.models import Stock
                stock_data = Stock.objects.filter(symbol=symbol).first()
                if stock_data and stock_data.security_id and str(stock_data.security_id).isdigit():
                    dhan_sec_id = str(stock_data.security_id)
                else:
                    return {'success': False, 'error': f"ID missing for {symbol}", 'symbol': symbol}

            exchange_segment = "NSE_EQ" if exchange.upper() == 'NSE' else "BSE_EQ"

            # 🔥 STEP 2: AGGRESSIVE LIVE/CLOSE PRICE EXTRACTION (ohlc_data)
            try:
                securities_data = {exchange_segment: [int(dhan_sec_id)]}
                response = dhan.ohlc_data(securities=securities_data)

                print(f"🚨 RAW DHAN RESPONSE: {response}")

                if response and response.get('status') == 'success':
                    segment_data = response.get('data', {}).get(exchange_segment, {})

                    # Double check format (string key vs int key)
                    stock_info = segment_data.get(str(dhan_sec_id)) or segment_data.get(int(dhan_sec_id)) or {}

                    ltp = stock_info.get('last_price')

                    # Agar market band hai (0.0 hai), toh previous close uthao
                    if not ltp or float(ltp) == 0.0:
                        ltp = stock_info.get('previous_close')
                        print(f"⚠️ Market Closed. Extracted Previous Close: ₹{ltp}")

                    if ltp and float(ltp) > 0:
                        return {"success": True, "ltp": float(ltp), "symbol": symbol}
            except Exception as live_e:
                print(f"⚠️ OHLC extraction failed for {symbol}: {live_e}")

            # 🔥 STEP 3: HISTORICAL DATA (ULTIMATE FALLBACK)
            print(f"⚠️ Fetching Historical Data for {dhan_sec_id}...")

            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')

            try:
                hist_data = dhan.historical_daily_data(
                    security_id=str(dhan_sec_id),
                    exchange_segment=exchange_segment,
                    instrument_type='EQUITY',
                    expiry_code=0,
                    from_date=from_date,
                    to_date=to_date
                )

                # 🔥 THE SDE DEBUGGER: Historical response yahan print hoga
                print(f"🚨 RAW HISTORICAL RESPONSE: {hist_data}")

                if hist_data and hist_data.get('status') == 'success':
                    close_prices = hist_data.get('data', {}).get('close', [])
                    if close_prices and len(close_prices) > 0:
                        last_traded_price = float(close_prices[-1])
                        print(f"✅ Got Historical Close Price: ₹{last_traded_price}")
                        return {"success": True, "ltp": last_traded_price, "symbol": symbol}
            except Exception as hist_e:
                print(f"⚠️ Historical Data error: {hist_e}")

            # Agar sab fail ho gaya
            return {"success": False, "error": "Price not available (Dhan returned blank)", "symbol": symbol}

        except Exception as e:
            print(f"❌ Dhan Live Price Error: {e}")
            return {'success': False, 'error': str(e), 'symbol': symbol}

    # ==================== GROWW LOGIC ====================
    else:
        groww = get_groww_client()
        if not groww:
            return {"success": False, "error": "Groww API authentication failed", "symbol": symbol}

        try:
            print(f"🟢 [GROWW API] Fetching Live Price for {symbol}...")
            exchange = exchange.upper().strip()
            if exchange not in ['NSE', 'BSE']:
                exchange = 'NSE'

            groww_symbol = f"{exchange}_{symbol}"

            response = groww.get_ltp(
                segment=groww.SEGMENT_CASH,
                exchange_trading_symbols=groww_symbol
            )

            ltp = None
            if isinstance(response, dict):
                if groww_symbol in response:
                    ltp = response[groww_symbol]
                else:
                    for key, val in response.items():
                        if isinstance(val, (float, int)):
                            ltp = val
                            break
            elif isinstance(response, (float, int)):
                ltp = float(response)

            if ltp is not None:
                return {"success": True, "ltp": float(ltp), "symbol": symbol}

            return {"success": False, "error": f"Price not found in response: {response}", "symbol": symbol}

        except Exception as e:
            return {"success": False, "error": str(e), "symbol": symbol}


def fetch_historical_data(symbol: str, start_date: str, end_date: str, exchange: str = 'NSE') -> pd.DataFrame:
    groww = get_groww_client()

    if groww:
        exchange_val = groww.EXCHANGE_NSE if exchange.upper() == 'NSE' else groww.EXCHANGE_BSE
        interval_val = groww.CANDLE_INTERVAL_DAY

        # ATTEMPT 1: GROWW API
        try:
            print(f"Fetching Historical Data for {symbol} via Groww SDK...")
            response = groww.get_historical_candles(
                exchange=exchange_val,
                segment=groww.SEGMENT_CASH,
                groww_symbol=symbol,
                start_time=start_date,
                end_time=end_date,
                candle_interval=interval_val
            )

            if isinstance(response, dict) and response.get('candles'):
                df = pd.DataFrame(response['candles'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['date'] = pd.to_datetime(df['timestamp'], unit='ms' if df['timestamp'].iloc[0] > 1e11 else 's')
                return df[['date', 'open', 'high', 'low', 'close', 'volume']]

        except Exception as e:
            print(f"⚠️ Groww SDK API Error for {symbol}: {e}")
            print("🔄 Switching to Yahoo Finance fallback...")
    else:
        print(f"⚠️ Groww Client unavailable. Switching to Yahoo Finance fallback for {symbol}...")

    # ATTEMPT 2: YFINANCE (FALLBACK)
    try:
        yf_symbol = f"{symbol}.NS" if exchange.upper() == 'NSE' else f"{symbol}.BO"
        df = yf.download(yf_symbol, start=start_date, end=end_date, progress=False)

        if not df.empty:
            df.reset_index(inplace=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

            rename_map = {'Date': 'date', 'Datetime': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low',
                          'Close': 'close', 'Volume': 'volume'}
            df.rename(columns=rename_map, inplace=True)

            print(f"✅ Historical data fetched successfully via yfinance for {symbol}")
            return df[['date', 'open', 'high', 'low', 'close', 'volume']]

    except Exception as e:
        print(f"❌ Both Groww and yfinance failed for {symbol}: {e}")

    return pd.DataFrame()