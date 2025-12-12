import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 1. API 키 설정
UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 2. 전략 설정
#TICKER = "KRW-XRP"        # 거래 대상
TICKER = "XRP/KRW"
TIMEFRAME = "1m"          # 캔들 (1분봉)
RSI_PERIOD = 14           # RSI 기간
RSI_BUY_THRESHOLD = 30    # 매수 기준 (RSI 30 미만)
TARGET_PROFIT_RATE = 5.0  # 익절 기준 (+5.0%)
BUY_AMOUNT_KRW = 6000     # 1회 매수 금액 (원)