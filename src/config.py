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
STOP_LOSS_RATE = -3.0     # 손절 기준 (-3.0% 이하에서 손절)

# ✅ [추가] 데일리 계좌 기준 TP / SL
DAILY_TP_RATE = 2.0       # 오늘 계좌 수익률 +2% 이상이면 그날 매매 종료
DAILY_SL_RATE = -1.0      # 오늘 계좌 수익률 -1% 이하이면 그날 손절 후 종료

BUY_AMOUNT_KRW = 5000     # 1회 매수 금액 (원)

# ✅ [추가] 시장 필터(폭락장/레짐 필터) 설정
USE_MARKET_FILTER = False          # ⬅️ 필요 없으면 False 로 끄면 됨
MARKET_FILTER_TICKER = "BTC/KRW"  # 시장 상태를 판단할 기준 코인 (BTC 현물)
# 1시간/24시간 수익률 기준 (예: -3% 이하, -7% 이하이면 신규 진입 OFF)
MARKET_1H_DROP_LIMIT = -3.0      # BTC 1시간 수익률이 -3% 이하면 위험
MARKET_24H_DROP_LIMIT = -7.0     # BTC 24시간 수익률이 -7% 이하면 위험
# 시장 필터 체크 주기 (초)
MARKET_FILTER_CHECK_INTERVAL = 60  # 60초마다 한 번씩 BTC 상태 재평가

# ✅ 전략 선택 옵션
#   - "RSI_V1"             : RSI 30 이하에서 분할 매수 전략
#   - "BREAKOUT_5M_V1"  : 5분봉 최근 박스 상단 돌파 시 진입
#   - "BREAKOUT_1M_V1"  : 1분봉 단기 박스 돌파 시 진입
#   - "PULLBACK_5M_V1"
#   - "SWING_1H_V1"
STRATEGY_MODE = "RSI_V1"


# ✅ 돌파/스윙 공통 필터
VOLUME_FILTER_MULTIPLIER = 1.5    # 거래량 필터: 현재 캔들 거래량이 최근 평균의 1.5배 이상일 때만 진입
REENTRY_COOLDOWN_SEC     = 300    # 재진입 쿨다운: 마지막 매수 후 300초(5분) 동안 재매수 금지

# ✅ (간단한) 거래 시간대 필터
#    - 예: 0~23이면 24시간 거래, 9~23이면 오전 9시~23시까지만 신규 진입 허용
ENTRY_START_HOUR = 0
ENTRY_END_HOUR   = 23

