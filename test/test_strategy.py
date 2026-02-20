"""
전략 테스트용 스크립트

- 실거래 / 실제 DB / 실제 텔레그램 호출 없이
  매수/손절/익절 로직을 콘솔에서 확인하기 위한 간단한 테스트 러너.

디렉토리 구조 예:
    zillion/
      src/
        __init__.py
        config.py
        strategy.py
        upbit_client.py
        database.py
        main.py
      test/
        __init__.py
        test_strategy.py

실행 방법 (프로젝트 루트에서):
    cd zillion
    python -m test.test_strategy
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import strategy
import config
import upbit_client as client
import database as db

import time
import datetime
import pandas as pd

# ---------------------------------------
# 0. 공통 Mock (텔레그램 / DB / 주문)
# ---------------------------------------

def mock_send_msg(bot_app, text: str):
    """텔레그램 메시지를 실제로 보내지 않고 콘솔에 출력"""
    print(f"[MOCK TG] {text.replace(chr(10), ' | ')}")


def mock_log_trade(
    ticker: str,
    action: str,
    price: float,
    amount: float,
    profit_rate: float = 0.0,
    pnl: float = 0.0,
    mode: str | None = None,
    fee: float = 0.0,
):
    """DB 저장 대신 콘솔에 출력"""
    print(
        f"[MOCK DB] {ticker} | mode={mode} | {action} | "
        f"price={price:,.0f} | amt={amount:.6f} | pr={profit_rate:.2f}% | pnl={pnl:+,.0f}"
    )


def mock_buy_market(ticker: str, krw_amount: float):
    """실제 업비트 주문 대신 콘솔 로그"""
    print(f"[MOCK BUY] {ticker} | KRW={krw_amount:,.0f}")
    return {"status": "ok", "side": "buy", "ticker": ticker, "krw": krw_amount}


def mock_sell_market(ticker: str, amount: float):
    """실제 업비트 주문 대신 콘솔 로그"""
    print(f"[MOCK SELL] {ticker} | amount={amount}")
    return {"status": "ok", "side": "sell", "ticker": ticker, "amount": amount}


def mock_get_balance(ticker: str):
    """(평단가, 수량) — 기본은 0으로 두고, 필요하면 테스트 함수에서 오버라이드"""
    return 0.0, 0.0


def mock_get_krw_balance():
    """원화 잔고 — 테스트용으로 넉넉하게 100만원 잡기"""
    return 1_000_000.0


# ✅ 실제 모듈 함수들을 mock으로 덮어쓰기
strategy.send_msg = mock_send_msg
db.log_trade = mock_log_trade
client.buy_market = mock_buy_market
client.sell_market = mock_sell_market
client.get_balance = mock_get_balance
client.get_krw_balance = mock_get_krw_balance


# ---------------------------------------
# 1. OHLCV 가짜 데이터 생성 유틸
# ---------------------------------------

def make_box_breakout_df(
    base_price: float,
    n: int = 40,
    breakout_gap: float = 10.0,
    timeframe_sec: int = 60,
    volume_base: float = 100.0,
    volume_spike_mult: float = 2.0,
) -> pd.DataFrame:
    """
    단순 박스 + 마지막 캔들 돌파형 가짜 데이터 생성
    - 앞 n개: high = base_price, close = base_price - 1
    - 마지막 1개: high/close = base_price + breakout_gap (돌파)
    """
    now_ms = int(time.time()) * 1000
    rows = []

    # 박스 구간
    for i in range(n):
        ts = now_ms + i * timeframe_sec * 1000
        high = base_price
        low = base_price - 20
        close = base_price - 1
        open_ = base_price - 5
        vol = volume_base
        rows.append([ts, open_, high, low, close, vol])

    # 돌파 캔들
    ts = now_ms + n * timeframe_sec * 1000
    breakout_price = base_price + breakout_gap
    rows.append([
        ts,
        breakout_price - 5,
        breakout_price,
        breakout_price - 5,
        breakout_price,
        volume_base * volume_spike_mult,
    ])

    df = pd.DataFrame(
        rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    return df


def make_pullback_5m_df() -> pd.DataFrame:
    """
    5분봉 눌림목 테스트용 가짜 데이터
    - 초반 N개: 박스 구간
    - 그 다음 1개: 박스 상단 돌파 (breakout)
    - 마지막 1개: 박스 상단 근처로 되돌림 (pullback)
    """
    base_price = 100
    now_ms = int(time.time()) * 1000
    timeframe_sec = 300

    rows = []
    N = 35

    # 박스 구간
    for i in range(N):
        ts = now_ms + i * timeframe_sec * 1000
        rows.append([
            ts,
            base_price - 5,   # open
            base_price,       # high
            base_price - 10,  # low
            base_price - 2,   # close
            100.0,            # vol
        ])

    # breakout 캔들
    ts_break = now_ms + N * timeframe_sec * 1000
    breakout_price = base_price + 15
    rows.append([
        ts_break,
        breakout_price - 5,
        breakout_price,
        breakout_price - 10,
        breakout_price,
        150.0,
    ])

    # pullback 캔들 (박스 상단 근처로 되돌림)
    ts_pull = now_ms + (N + 1) * timeframe_sec * 1000
    pull_price = base_price + 1  # 박스 상단(base_price) 근처
    rows.append([
        ts_pull,
        pull_price - 3,
        pull_price + 2,
        pull_price - 5,
        pull_price,
        120.0,
    ])

    df = pd.DataFrame(
        rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    return df


def make_swing_1h_df() -> pd.DataFrame:
    """
    1시간봉 EMA20 > EMA50 상승 추세 + 현재가 EMA20 근처 눌림 시나리오
    """
    now_ms = int(time.time()) * 1000
    timeframe_sec = 3600

    rows = []
    price = 100.0
    for i in range(60):
        ts = now_ms + i * timeframe_sec * 1000
        if i < 50:
            price += 0.5
        else:
            price -= 0.3  # 마지막 10개는 하락 → EMA20 근처로 되돌림
        rows.append([
            ts,
            price - 3,
            price + 2,
            price - 5,
            price,
            100.0 + i,  # 조금씩 늘어나는 거래량
        ])

    df = pd.DataFrame(
        rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    return df

def make_turtle_df() -> pd.DataFrame:
    """
    터틀 전략 테스트용 가짜 1시간봉 데이터
    - 앞 25개: 박스 구간 (고점 = 100)
    - 마지막 1개: 20봉 고점 돌파 (close = 115)
    - ATR이 계산될 수 있도록 변동폭 부여
    """
    now_ms = int(time.time()) * 1000
    timeframe_sec = 3600
    rows = []

    base_price = 100.0

    # 박스 구간 25개
    for i in range(25):
        ts = now_ms + i * timeframe_sec * 1000
        rows.append([
            ts,
            base_price - 3,   # open
            base_price,       # high  ← 고점 고정
            base_price - 8,   # low   ← 변동폭 부여 (ATR 계산용)
            base_price - 1,   # close
            100.0,            # volume
        ])

    # 돌파 캔들 1개
    breakout_price = base_price + 15  # 115원
    ts = now_ms + 25 * timeframe_sec * 1000
    rows.append([
        ts,
        base_price + 2,
        breakout_price,
        base_price,
        breakout_price,
        200.0,  # 거래량 증가
    ])

    df = pd.DataFrame(
        rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    return df


# ---------------------------------------
# 2. 개별 전략 "매수" 테스트 함수들
# ---------------------------------------

def test_rsi_v1_buy():
    print("\n=== [TEST] RSI_V1 매수 테스트 ===")
    config.STRATEGY_MODE = "RSI_V1"

    curr_price = 500.0
    curr_rsi = 20.0    # 기준 30보다 낮게 만들어서 매수 신호 유도
    my_krw = 100_000.0

    strategy.purchase_buy(
        bot_app=None,
        curr_price=curr_price,
        curr_rsi=curr_rsi,
        my_krw=my_krw,
    )


def test_breakout_5m_v1_buy():
    print("\n=== [TEST] BREAKOUT_5M_V1 매수 테스트 ===")
    config.STRATEGY_MODE = "BREAKOUT_5M_V1"

    df_5m = make_box_breakout_df(
        base_price=100.0,
        breakout_gap=15.0,
        timeframe_sec=300,
    )

    def mock_get_ohlcv_5m(ticker: str, interval: str):
        if interval == "5m":
            return df_5m
        return pd.DataFrame()

    client.get_ohlcv = mock_get_ohlcv_5m

    curr_price = df_5m["close"].iloc[-1]
    curr_rsi = 50.0  # 돌파 전략에선 중요 X
    my_krw = 100_000.0

    strategy.purchase_buy(
        bot_app=None,
        curr_price=curr_price,
        curr_rsi=curr_rsi,
        my_krw=my_krw,
    )


def test_breakout_1m_v1_buy():
    print("\n=== [TEST] BREAKOUT_1M_V1 매수 테스트 ===")
    config.STRATEGY_MODE = "BREAKOUT_1M_V1"

    df_1m = make_box_breakout_df(
        base_price=200.0,
        breakout_gap=20.0,
        timeframe_sec=60,
    )

    def mock_get_ohlcv_1m(ticker: str, interval: str):
        if interval == "1m":
            return df_1m
        return pd.DataFrame()

    client.get_ohlcv = mock_get_ohlcv_1m

    curr_price = df_1m["close"].iloc[-1]
    curr_rsi = 40.0
    my_krw = 100_000.0

    strategy.purchase_buy(
        bot_app=None,
        curr_price=curr_price,
        curr_rsi=curr_rsi,
        my_krw=my_krw,
    )


def test_pullback_5m_v1_buy():
    print("\n=== [TEST] PULLBACK_5M_V1 매수 테스트 ===")
    config.STRATEGY_MODE = "PULLBACK_5M_V1"

    df_5m = make_pullback_5m_df()

    def mock_get_ohlcv_5m(ticker: str, interval: str):
        if interval == "5m":
            return df_5m
        return pd.DataFrame()

    client.get_ohlcv = mock_get_ohlcv_5m

    curr_price = df_5m["close"].iloc[-1]
    curr_rsi = 45.0
    my_krw = 100_000.0

    strategy.purchase_buy(
        bot_app=None,
        curr_price=curr_price,
        curr_rsi=curr_rsi,
        my_krw=my_krw,
    )


def test_swing_1h_v1_buy():
    print("\n=== [TEST] SWING_1H_V1 매수 테스트 ===")
    config.STRATEGY_MODE = "SWING_1H_V1"

    df_1h = make_swing_1h_df()

    def mock_get_ohlcv_1h(ticker: str, interval: str):
        if interval == "1h":
            return df_1h
        return pd.DataFrame()

    client.get_ohlcv = mock_get_ohlcv_1h

    curr_price = df_1h["close"].iloc[-1]
    curr_rsi = 50.0
    my_krw = 100_000.0

    strategy.purchase_buy(
        bot_app=None,
        curr_price=curr_price,
        curr_rsi=curr_rsi,
        my_krw=my_krw,
    )

def test_turtle_v1_buy():
    print("\n=== [TEST] TURTLE_V1 매수 테스트 ===")
    config.STRATEGY_MODE = "TURTLE_V1"

    df_1h = make_turtle_df()

    def mock_get_ohlcv_turtle(ticker: str, interval: str):
        if interval == "1h":
            return df_1h
        return pd.DataFrame()

    client.get_ohlcv = mock_get_ohlcv_turtle

    # 총자산 = 원화 100만원 (mock_get_krw_balance 기준)
    # 보유 코인 없음 (mock_get_balance 기준 0)
    curr_price = df_1h["close"].iloc[-1]   # 115원
    curr_rsi   = 55.0
    my_krw     = 1_000_000.0

    strategy.purchase_buy(
        bot_app=None,
        curr_price=curr_price,
        curr_rsi=curr_rsi,
        my_krw=my_krw,
    )


def test_turtle_v1_stop_loss():
    print("\n=== [TEST] TURTLE_V1 손절 테스트 ===")
    config.STRATEGY_MODE = "TURTLE_V1"

    df_1h = make_turtle_df()

    def mock_get_ohlcv_turtle(ticker: str, interval: str):
        if interval == "1h":
            return df_1h
        return pd.DataFrame()

    client.get_ohlcv = mock_get_ohlcv_turtle

    my_avg = 115.0   # 진입가
    my_amt = 50.0    # 보유 수량

    # ATR ≈ 8 → 손절가 ≈ 115 - (2 * 8) = 99
    # 현재가를 손절가 아래로 설정
    curr_price = 95.0

    strategy._turtle_exit(
        bot_app=None,
        curr_price=curr_price,
        my_amt=my_amt,
        my_avg=my_avg,
    )


def test_turtle_v1_take_profit():
    print("\n=== [TEST] TURTLE_V1 익절 테스트 ===")
    config.STRATEGY_MODE = "TURTLE_V1"

    df_1h = make_turtle_df()

    def mock_get_ohlcv_turtle(ticker: str, interval: str):
        if interval == "1h":
            return df_1h
        return pd.DataFrame()

    client.get_ohlcv = mock_get_ohlcv_turtle

    my_avg = 80.0   # 진입가
    my_amt = 50.0    # 보유 수량

    # 10봉 최저가 = 약 92 (박스low - 8)
    # 현재가를 10봉 최저가 아래로 설정 → 익절 트리거
    curr_price = 91.0

    strategy._turtle_exit(
        bot_app=None,
        curr_price=curr_price,
        my_amt=my_amt,
        my_avg=my_avg,
    )

# ---------------------------------------
# 3. 손절 / 익절 테스트
# ---------------------------------------

def test_take_profit_and_stop_loss():
    print("\n=== [TEST] 손절 / 익절 테스트 ===")

    # 전략 이름은 DB에 mode로 기록되는 값이니, 아무거나 하나 고정
    config.STRATEGY_MODE = "RSI_V1"

    my_avg = 100.0
    my_amt = 10.0

    # 익절 테스트: +10%
    curr_price_tp = 110.0

    print("\n--- 익절 테스트 (+10%) ---")
    strategy.loss_cut_take_profit(
        bot_app=None,
        curr_price=curr_price_tp,
        my_amt=my_amt,
        my_avg=my_avg,
    )

    # 손절 테스트: -5%
    curr_price_sl = 95.0

    print("\n--- 손절 테스트 (-5%) ---")
    strategy.loss_cut_take_profit(
        bot_app=None,
        curr_price=curr_price_sl,
        my_amt=my_amt,
        my_avg=my_avg,
    )


# ---------------------------------------
# main
# ---------------------------------------

if __name__ == "__main__":
    print("===== 전략 테스트 시작 =====")
    print(f"현재 시간: {datetime.datetime.now()}")

    # 각 전략 매수 테스트
    # test_rsi_v1_buy()
    # test_breakout_5m_v1_buy()
    # test_breakout_1m_v1_buy()
    # test_pullback_5m_v1_buy()
    # test_swing_1h_v1_buy()

    # 손절/익절 테스트
    # test_take_profit_and_stop_loss()

    test_turtle_v1_buy()
    test_turtle_v1_stop_loss()
    test_turtle_v1_take_profit()


    print("\n===== 전략 테스트 종료 =====")
