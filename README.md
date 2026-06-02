# 📈 Multi-Broker Algo Trading Dashboard

An enterprise-grade Algorithmic Trading Dashboard built with **Django** and **Python**. This system integrates multiple broker APIs (DhanHQ and Groww) to fetch real-time OHLC market data, manage active stock portfolios, and calculate live P&L. 

Designed with high reliability, it features intelligent data routing, a self-healing database mechanism, and automated historical data fallbacks for non-market hours.

## 🚀 Key Features

* **Multi-Broker API Integration:** Seamlessly connect and toggle between DhanHQ and Groww accounts dynamically via the UI.
* **Smart Identifier Routing:** Dynamically resolves text-based stock symbols (e.g., 'RELIANCE') to numeric Security IDs required by specific brokers, eliminating API rejection errors.
* **Aggressive Price Fetching & Fallback:** 
  * Attempts to fetch Live LTP.
  * Falls back to Previous Close if the market is closed.
  * Defaults to Historical Daily Data extraction (last 10 days) to ensure the UI never breaks during weekends or prolonged holidays.
* **Self-Healing Database Mechanism:** Utilizes Django ORM (`update_or_create`) to automatically detect, flush, and resolve duplicate "ghost data" conflicts during rapid async polling.
* **Advanced P&L Calculator:** Real-time calculation of Current Value, Invested Value, Realized P&L, Unrealized P&L, and Average Price tracking.

## 🛠️ Tech Stack

* **Backend:** Python 3.11, Django >= 4.2
* **Data Processing:** Pandas, Pytz
* **APIs & Networking:** DhanHQ SDK, Requests, Custom Groww API Logic
* **Database:** SQLite / MySQL
* **Frontend:** HTML, CSS, JavaScript, Bootstrap

## ⚙️ Local Setup & Installation

**1. Clone the repository**
```bash
git clone https://github.com/ajay-prajapati-28/algo-trading-dashboard.git
cd algo-trading-dashboard


python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate

pip install -r requirements.txt

python manage.py makemigrations
python manage.py migrate
python manage.py runserver

👨‍💻 Author
Ajay Prajapati

Python Developer
