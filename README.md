# 패키지 일람
zillion/
├── data
│   ├── KRW-XRP_60m.csv      ← XRP 1시간봉
│   ├── KRW-BTC_60m.csv      ← BTC 1시간봉 (추후 추가)
│   ├── KRW-ETH_60m.csv      ← ETH 1시간봉 (추후 추가)
│   └── KRW-XRP_240m.csv     ← XRP 4시간봉 (추후 추가)
├── src
│    ├── config.py            # [설정] 모든 설정값과 환경변수를 관리
│    ├── database.py          # [저장소] DB 생성 및 매매 기록 담당
│    ├── upbit_client.py      # [통신] 업비트 API와 대화(잔고조회, 주문)하는 담당
│    ├── strategy.py          # [두뇌] 언제 사고 팔지 결정하는 알고리즘 (쓰레드)
│    └── main.py              # [실행] 이 모든 것을 조립하고 실행하는 파일
├── test
│    ├── __init__.py         # ✅ 추가 (선택이지만 해두면 깔끔)
│    ├── backtest.py         # ✅ 백테스트 코드
│    └── strategytest.py     # ✅ 단일, 시나리오 통합 테스트 코드
├── .env                     #  API 키 및 설정값
├── .README.md               # README
└── .trading.db              # DB(임시)

# 실행방법 - 로컬과 맞출것
cd E:\intellij\zillion

# 가상환경 생성 (한 번만)
python -m venv .venv

# 활성화
.venv\Scripts\activate

# 의존성 설치
pip install -r require.txt

# 가상환경 신규 생성시 - 신규/로컬 소스 이관시
    # 파이썬 설치 및 python 환경변수 설정 확인 (Path) - 실행 후 인텔리제이 재시작 필요
    C:\Users\blaze\AppData\Local\Programs\Python\Python314
    C:\Users\blaze\AppData\Local\Programs\Python\Python314\Scripts

    # 1. 가상환경 비활성화
    deactivate
    
    # 2. 기존 .venv 삭제
    Remove-Item -Recurse -Force .venv
    
    # 3. 새로 생성
    python -m venv .venv
    
    # 4. 다시 활성화
    .venv\Scripts\activate
    
    # 5. 패키지 설치
    pip install -r require.txt

# 추가 Lib 설치시
pip installs something > pip freeze > require.txt

# test 실행시
python -m test.strategytest

# backtest 실행시
python -m test.backtest

# 메인 실행시
cd E:\intellij\zillion\src
python main.py