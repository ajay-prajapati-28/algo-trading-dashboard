import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

def fetch_live_price(symbol, exchange='NSE', broker='groww'):
    """
    100% Proper SDE Function: Auto-detects text vs ID, fetches live price,
    uses historical closing price as fallback, and auto-initializes API clients.
    """

    # ==========================================
    # 1. GROWW BROKER LOGIC
    # ==========================================
    if broker == 'groww':
        try:
            # NOTE: Yahan apna Groww wala purana live price ka logic daal dena.
            return {"success": False, "error": "Groww Logic Pending"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==========================================
    # 2. DHAN BROKER LOGIC (LIVE + FALLBACK)
    # ==========================================
    elif broker == 'dhan':
        try:
            # 🔥 STEP 1: Dhan Client Initialize Karo (IDE Error Fix)
            from dhanhq import dhanhq
            from django.contrib.auth.models import User

            # Database se main user ki API keys uthao
            first_user = User.objects.first()
            if not first_user or not hasattr(first_user, 'profile'):
                return {"success": False, "error": "User Profile not found"}

            client_id = first_user.profile.dhan_client_id
            access_token = first_user.profile.dhan_access_token

            if not client_id or not access_token:
                return {"success": False, "error": "Dhan API Keys missing in Profile"}

            # Yeh ban gaya tumhara 'dhan' object jiski wajah se error aa raha tha!
            dhan = dhanhq(client_id, access_token)

            # STEP 2: Symbol ko Security ID (1333) me convert karo
            if str(symbol).isdigit():
                dhan_sec_id = str(symbol)
            else:
                from app.models import Stock  # Apna app name ensure kar lena
                stock_data = Stock.objects.filter(symbol=symbol).first()
                if stock_data and stock_data.security_id and str(stock_data.security_id).isdigit():
                    dhan_sec_id = str(stock_data.security_id)
                else:
                    return {"success": False, "error": "Security ID missing in Database"}

            exch_segment = 'NSE_EQ' if exchange == 'NSE' else 'BSE_EQ'

            # STEP 3: PRIMARY SOURCE (Live Market Quote)
            live_data = dhan.get_market_quote(security_id=dhan_sec_id, exchange_segment=exch_segment)

            if live_data and live_data.get('status') == 'success':
                data_dict = live_data.get('data', {})
                ltp = data_dict.get('last_price', 0)

                if not ltp and 'LTP' in data_dict:
                    ltp = data_dict['LTP']

                if ltp:
                    return {"success": True, "ltp": ltp}

            # STEP 4: SECONDARY SOURCE (Historical Fallback for Weekends)
            print(f"⚠️ Dhan Live Failed for {symbol}. Fetching Last Closing Price...")

            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

            hist_data = dhan.historical_daily_data(
                security_id=dhan_sec_id,
                exchange_segment=exch_segment,
                instrument_type='EQUITY',
                expiry_code=0,
                from_date=from_date,
                to_date=to_date
            )

            if hist_data and hist_data.get('status') == 'success':
                close_prices = hist_data.get('data', {}).get('close', [])
                if close_prices and len(close_prices) > 0:
                    last_traded_price = float(close_prices[-1])
                    print(f"✅ Got Last Close Price for {symbol}: ₹{last_traded_price}")
                    return {"success": True, "ltp": last_traded_price}

            error_reason = live_data.get('remarks', 'Market Closed & Fallback Failed') if live_data else 'API Failure'
            return {"success": False, "error": error_reason}

        except Exception as e:
            print(f"❌ Dhan Live Price Exception: {str(e)}")
            return {"success": False, "error": str(e)}

    # ==========================================
    # 3. FALLBACK (Invalid Broker)
    # ==========================================
    return {"success": False, "error": "Invalid Broker Selected"}

def parse_uploaded_file(file_path: str) -> list:
    try:
        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.csv':
            df = pd.read_csv(file_path)
        elif ext in ['.xls', '.xlsx']:
            df = pd.read_excel(file_path)
        else:
            return []

        expected_cols = ['Stock Name', 'Symbol']
        for col in expected_cols:
            if col not in df.columns:
                return []

        parsed_data = []
        for _, row in df.iterrows():
            symbol = str(row.get('Symbol', '')).strip().upper()
            if not symbol or symbol == 'NAN':
                continue

            company_name = str(row.get('Stock Name', '')).strip()

            symbol_id = None
            if 'Symbol ID' in df.columns:
                val = row.get('Symbol ID')
                if pd.notna(val) and str(val).strip():
                    symbol_id = str(val).strip()

            if not symbol_id:
                symbol_id = symbol

            parsed_data.append({
                "company_name": company_name,
                "symbol": symbol,
                "symbol_id": symbol_id
            })

        return parsed_data
    except Exception as e:
        print(f"Error parsing file: {e}")
        return []