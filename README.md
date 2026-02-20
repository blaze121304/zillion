1. 패키지 일람
zillion/
├── src
│    ├── config.py            # [설정] 모든 설정값과 환경변수를 관리
│    ├── database.py          # [저장소] DB 생성 및 매매 기록 담당
│    ├── upbit_client.py      # [통신] 업비트 API와 대화(잔고조회, 주문)하는 담당
│    ├── strategy.py          # [두뇌] 언제 사고 팔지 결정하는 알고리즘 (쓰레드)
│    └── main.py              # [실행] 이 모든 것을 조립하고 실행하는 파일
├── test
│    ├── __init__.py         # ✅ 추가 (선택이지만 해두면 깔끔)
│    └── test_strategy.py    # ✅ 테스트 코드
├── .env                     #  API 키 및 설정값
├── .README.md               # README
└── .trading.db              # DB(임시)

2. 실행방법
cd D:\git-python\zillion

# 가상환경 생성 (한 번만)
python -m venv venv

# 활성화
venv\Scripts\activate

# 의존성 설치
pip install -r require.txt

# 추가 Lib 설치시
pip installs something > pip freeze > require.txt

# test 실행시
python -m test.test_strategy