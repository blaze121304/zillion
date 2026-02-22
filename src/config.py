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
TICKER         = "BTC/KRW"    # 실거래용 (ccxt)
TICKER_UPBIT   = "KRW-BTC"    # 데이터 수집용 (업비트 native)
TIMEFRAME      = "1h"

# ✅ 전략 선택
STRATEGY_MODE = "TURTLE_V1"

# ✅ 터틀 전략 설정
TURTLE_ENTRY_PERIOD  = 30       # 진입 기준 고점 기간 (20봉)
TURTLE_ATR_PERIOD    = 14       # ATR 계산 기간
TURTLE_RISK_RATE     = 2.0      # 총자산 대비 허용 손실 (1%)
TURTLE_MAX_UNITS     = 4        # 최대 피라미딩 유닛 수
REENTRY_COOLDOWN_SEC = 43200    # 쿨다운 시간(SEC) - 1시간봉 기준 1봉 대기 (최소 24시간 (1일) 정도는 쉬어야 연속 손절 막을수 있음)

# ✅ 청산 모드
TURTLE_EXIT_MODE = "TRAILING"   # "TRAILING" / "10DAY_LOW" / "20DAY_LOW"
TURTLE_TRAILING_MULTIPLIER = 2.0 # 가장 중요 (트레일링 스탑 승수 (높을수록 느슨, 낮을수록 빡빡)) 기본 2.0 / 1.5 / 2.5 ..

# ✅ (간단한) 거래 시간대 필터
#    - 예: 0~23이면 24시간 거래, 9~23이면 오전 9시~23시까지만 신규 진입 허용
ENTRY_START_HOUR = 0
ENTRY_END_HOUR   = 23

# ✅ 손실 한도 설정
MAX_DRAWDOWN_LIMIT = -25.0   # 계좌 -25% 도달 시 봇 중단

# ✅ 백테스트 실행 옵션
BACKTEST_SINGLE_RUN   = True   # 단일 백테스트 실행
BACKTEST_GRID_SEARCH  = False  # 그리드 서치 실행 (CSV 없을 때만 의미 있음)

# ✅ 백테스트 초기 자본
BACKTEST_INITIAL_CAPITAL = 3_000_000.0  # 백테스트 초기 자본

# ✅ 백테스트 옵션
BACKTEST_PRINT_ALL_TRADES   = False  # True: 매수/매도 전체 출력 (디버그용)
BACKTEST_PRINT_SELL_ONLY    = False   # True: 매도(청산)만 출력
BACKTEST_PRINT_MONTHLY      = True   # 월별/연도별 수익률 출력
BACKTEST_PRINT_CRASH        = False   # 폭락 구간 방어 분석 출력

