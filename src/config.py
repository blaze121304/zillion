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
TIMEFRAME = "1h"          # 캔들 (1시간봉)


# ✅ [추가] 시장 필터(폭락장/레짐 필터) 설정
USE_MARKET_FILTER = False          # ⬅️ 필요 없으면 False 로 끄면 됨
MARKET_FILTER_TICKER = "BTC/KRW"  # 시장 상태를 판단할 기준 코인 (BTC 현물)
# 1시간/24시간 수익률 기준 (예: -3% 이하, -7% 이하이면 신규 진입 OFF)
MARKET_1H_DROP_LIMIT = -3.0      # BTC 1시간 수익률이 -3% 이하면 위험
MARKET_24H_DROP_LIMIT = -7.0     # BTC 24시간 수익률이 -7% 이하면 위험
# 시장 필터 체크 주기 (초)
MARKET_FILTER_CHECK_INTERVAL = 60  # 60초마다 한 번씩 BTC 상태 재평가

# ✅ 전략 선택
#   - "RSI_V1"          : RSI 30 이하 매수
#   - "BREAKOUT_5M_V1"  : 5분봉 박스 상단 돌파
#   - "BREAKOUT_1M_V1"  : 1분봉 단기 박스 돌파
#   - "PULLBACK_5M_V1"  : 5분봉 눌림목 진입
#   - "SWING_1H_V1"     : 1시간봉 EMA 스윙
#   - "TURTLE_V1"       : 터틀 트레이딩
STRATEGY_MODE = "TURTLE_V1"

# 기존 전략 공통 설정
RSI_PERIOD               = 14
RSI_BUY_THRESHOLD        = 30
TARGET_PROFIT_RATE       = 5.0
STOP_LOSS_RATE           = -3.0
BUY_AMOUNT_KRW           = 5000
VOLUME_FILTER_MULTIPLIER = 1.5
REENTRY_COOLDOWN_SEC     = 300

# ✅ 터틀 전략 설정
TURTLE_ENTRY_PERIOD  = 20   # 진입 기준 고점 기간 (20봉)
TURTLE_EXIT_PERIOD   = 10   # 청산 기준 저점 기간 (10봉)
TURTLE_ATR_PERIOD    = 20   # ATR 계산 기간
TURTLE_RISK_RATE     = 1.0  # 총자산 대비 허용 손실 (1%)
TURTLE_MAX_UNITS     = 4    # 최대 피라미딩 유닛 수

# ✅ 폭락장 필터
USE_MARKET_FILTER            = False
MARKET_FILTER_TICKER         = "BTC/KRW"
MARKET_1H_DROP_LIMIT         = -3.0
MARKET_24H_DROP_LIMIT        = -7.0
MARKET_FILTER_CHECK_INTERVAL = 60

# ✅ (간단한) 거래 시간대 필터
#    - 예: 0~23이면 24시간 거래, 9~23이면 오전 9시~23시까지만 신규 진입 허용
ENTRY_START_HOUR = 0
ENTRY_END_HOUR   = 23

# ✅ 쿨다운 시간 - 1시간봉 기준 1봉 대기
REENTRY_COOLDOWN_SEC = 86400 # 최소 24시간 (1일) 정도는 쉬어야 연속 손절 막을수 있음
