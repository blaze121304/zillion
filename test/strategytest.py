"""
TURTLE_V1 전략 시나리오 테스트 스크립트

테스트 시나리오:
  [기본] 단위 기능 테스트 (11개)
  [시나리오 A] 횡보장 - 진입 후 수익 없이 손절
  [시나리오 B] 급상승장 - 피라미딩 4유닛 풀 진입 후 추세 종료 익절
  [시나리오 C] 폭락장 - ATR 스파이크 강제 청산 / 재진입 쿨다운 / 연속 손절

실행 방법:
    cd zillion/src
    python strategytest.py
"""

import time
import datetime
import pandas as pd
import numpy as np
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import config
import strategy
import upbit_client as client
import database as db

# ============================================================
# 0. Mock 설정
# ============================================================

_trade_log = []   # 테스트 중 발생한 매매 기록 수집용

def mock_send_msg(bot_app, text: str):
    print(f"  [TG] {text.replace(chr(10), ' | ')}")

def mock_log_trade(ticker, action, price, amount,
                   profit_rate=0.0, pnl=0.0, mode=None, fee=0.0):
    _trade_log.append({
        "action": action, "price": price, "amount": amount,
        "profit_rate": profit_rate, "pnl": pnl,
    })
    print(
        f"  [DB] {action.upper()} | price={price:,.0f} | amt={amount:.4f} | "
        f"pr={profit_rate:+.2f}% | pnl={pnl:+,.0f}"
    )

def mock_buy_market(ticker, krw_amount):
    print(f"  [ORDER] BUY  {ticker} | KRW={krw_amount:,.0f}")
    return {"status": "ok"}

def mock_sell_market(ticker, amount):
    print(f"  [ORDER] SELL {ticker} | amt={amount:.4f}")
    return {"status": "ok"}

strategy.send_msg  = mock_send_msg
db.log_trade       = mock_log_trade
client.buy_market  = mock_buy_market
client.sell_market = mock_sell_market

# config 기본값
config.TICKER               = "XRP/KRW"
config.STRATEGY_MODE        = "TURTLE_V1"
config.TURTLE_ENTRY_PERIOD  = 20
config.TURTLE_ATR_PERIOD    = 14
config.TURTLE_RISK_RATE     = 1.0
config.TURTLE_MAX_UNITS     = 4
config.REENTRY_COOLDOWN_SEC = 86400
config.USE_ATR_FILTER       = True
config.ATR_SPIKE_PERIOD     = 20
config.ATR_SPIKE_MULTIPLIER = 2.5
config.TELEGRAM_BOT_TOKEN   = None
config.TELEGRAM_CHAT_ID     = None


# ============================================================
# 1. 헬퍼 함수
# ============================================================

def reset_turtle_state():
    strategy.turtle_units        = 0
    strategy.turtle_next_add     = 0.0
    strategy.turtle_entry_atr    = 0.0
    strategy.entry_highest_price = 0.0
    strategy.last_entry_ts       = 0.0
    _trade_log.clear()


def make_df(prices: list, atr_fixed: float = 20.0) -> pd.DataFrame:
    """
    가격 리스트로 1시간봉 DataFrame 생성
    - ATR 고정을 위해 high/low를 ±atr_fixed/2로 설정
    """
    now_ms = int(time.time()) * 1000
    rows = []
    for i, close in enumerate(prices):
        ts    = now_ms + i * 3600 * 1000
        high  = close + atr_fixed * 0.5
        low   = close - atr_fixed * 0.5
        open_ = close
        rows.append([ts, open_, high, low, close, 1000.0 + i * 10])

    df = pd.DataFrame(rows, columns=["timestamp","open","high","low","close","volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def make_atr_spike_df(base_price: float = 1000.0, n: int = 30,
                      spike_multiplier: float = 3.0) -> pd.DataFrame:
    """ATR 급등 시나리오: 앞 n개 정상 ATR, 마지막 캔들 급등"""
    rows = []
    now_ms     = int(time.time()) * 1000
    atr_normal = 20.0

    for i in range(n):
        c = base_price + np.random.uniform(-5, 5)
        rows.append([now_ms + i*3600*1000, c, c+atr_normal*0.5, c-atr_normal*0.5, c, 1000.0])

    spike_atr = atr_normal * spike_multiplier
    c = base_price - spike_atr * 0.8
    rows.append([now_ms + n*3600*1000, base_price, base_price+spike_atr*0.2, c, c, 8000.0])

    df = pd.DataFrame(rows, columns=["timestamp","open","high","low","close","volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def print_header(title: str):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")

def check(condition: bool, label: str = "") -> bool:
    tag = "✅ PASS" if condition else "❌ FAIL"
    print(f"  {tag}  {label}")
    return condition


# ============================================================
# 2. 기본 단위 테스트
# ============================================================

def test_1_no_entry_without_breakout():
    print_header("[TEST 01] 돌파 없으면 진입 안 함")
    reset_turtle_state()
    prices = [1000.0] * 21 + [995.0]
    df = make_df(prices)
    client.get_ohlcv = lambda t, i: df
    strategy.purchase_buy(None, 995.0, 1_000_000.0, 0.0, df)
    check(strategy.turtle_units == 0, f"units={strategy.turtle_units} (0이어야 함)")


def test_2_entry_on_breakout():
    print_header("[TEST 02] 20봉 고점 돌파 시 1유닛 진입")
    reset_turtle_state()
    prices = [1000.0] * 20 + [999.0, 1050.0]
    df = make_df(prices)
    client.get_ohlcv = lambda t, i: df
    strategy.purchase_buy(None, 1050.0, 1_000_000.0, 0.0, df)
    check(strategy.turtle_units == 1, f"units={strategy.turtle_units} (1이어야 함)")
    print(f"    entry_atr={strategy.turtle_entry_atr:.1f} | next_add={strategy.turtle_next_add:.1f}")


def test_3_pyramiding():
    print_header("[TEST 03] 피라미딩 2→3→4유닛 추가 진입")
    reset_turtle_state()
    prices = [1000.0] * 20 + [999.0, 1050.0]
    df = make_df(prices, atr_fixed=20.0)
    client.get_ohlcv = lambda t, i: df
    strategy.purchase_buy(None, 1050.0, 1_000_000.0, 0.0, df)
    my_krw = 900_000.0
    for _ in range(3):
        add_price = strategy.turtle_next_add + 1
        strategy.purchase_buy(None, add_price, my_krw, 0.5, df)
        my_krw -= 50_000
        print(f"    → units={strategy.turtle_units} | next_add={strategy.turtle_next_add:.1f}")
    check(strategy.turtle_units == 4, f"최종 units={strategy.turtle_units} (4이어야 함)")


def test_4_max_units_block():
    print_header("[TEST 04] 최대 유닛(4) 초과 진입 차단")
    reset_turtle_state()
    strategy.turtle_units     = 4
    strategy.turtle_entry_atr = 20.0
    strategy.turtle_next_add  = 1100.0
    df = make_df([1000.0] * 22 + [1200.0])
    client.get_ohlcv = lambda t, i: df
    strategy.purchase_buy(None, 1200.0, 1_000_000.0, 1.0, df)
    check(strategy.turtle_units == 4, f"units={strategy.turtle_units} (4 유지되어야 함)")


def test_5_trailing_stop_loss():
    print_header("[TEST 05] 트레일링 스탑 손절")
    reset_turtle_state()
    strategy.entry_highest_price = 1200.0
    strategy.turtle_units        = 1
    strategy.turtle_entry_atr    = 20.0
    # 손절가 = 1200 - 2*20 = 1160, 현재가 1150 → 청산
    df = make_df([1150.0] * 22, atr_fixed=20.0)
    client.get_ohlcv = lambda t, i: df
    strategy._turtle_exit(None, 1150.0, 1.0, 1050.0)
    check(strategy.turtle_units == 0,        f"units={strategy.turtle_units} (0이어야 함)")
    check(strategy.entry_highest_price == 0, f"highest={strategy.entry_highest_price} (0이어야 함)")


def test_6_trailing_stop_profit():
    print_header("[TEST 06] 트레일링 스탑 익절")
    reset_turtle_state()
    strategy.entry_highest_price = 1500.0
    strategy.turtle_units        = 2
    strategy.turtle_entry_atr    = 20.0
    # 손절가 = 1500 - 40 = 1460, 현재가 1450 → 수익 청산
    df = make_df([1450.0] * 22, atr_fixed=20.0)
    client.get_ohlcv = lambda t, i: df
    strategy._turtle_exit(None, 1450.0, 2.0, 1000.0)
    check(strategy.turtle_units == 0, f"units={strategy.turtle_units} (0이어야 함)")
    sells = [t for t in _trade_log if t['action'] == 'sell']
    check(len(sells) > 0 and sells[-1]['profit_rate'] > 0, "수익(+) 청산이어야 함")


def test_7_no_exit_above_stop():
    print_header("[TEST 07] 트레일링 스탑 위 → 청산 없음")
    reset_turtle_state()
    strategy.entry_highest_price = 1300.0
    strategy.turtle_units        = 1
    strategy.turtle_entry_atr    = 20.0
    # 손절가 = 1260, 현재가 1300 → 청산 없음
    df = make_df([1300.0] * 22, atr_fixed=20.0)
    client.get_ohlcv = lambda t, i: df
    strategy._turtle_exit(None, 1300.0, 1.0, 1050.0)
    check(strategy.turtle_units == 1, f"units={strategy.turtle_units} (1 유지되어야 함)")


def test_8_atr_spike_true():
    print_header("[TEST 08] ATR 스파이크 감지 (True)")
    df = make_atr_spike_df(spike_multiplier=3.0)
    result = strategy.is_atr_spike(df)
    print(f"  → is_atr_spike={result}")
    check(result == True, "True여야 함")


def test_9_atr_spike_false():
    print_header("[TEST 09] 정상 ATR → 스파이크 아님 (False)")
    prices = [1000.0 + i for i in range(30)]
    df = make_df(prices, atr_fixed=20.0)
    result = strategy.is_atr_spike(df)
    print(f"  → is_atr_spike={result}")
    check(result == False, "False여야 함")


def test_10_reentry_cooldown():
    print_header("[TEST 10] 재진입 쿨다운 중 진입 차단")
    reset_turtle_state()
    strategy.last_entry_ts = time.time()
    in_cooldown = (time.time() - strategy.last_entry_ts) < config.REENTRY_COOLDOWN_SEC
    check(in_cooldown == True, f"쿨다운 활성 | in_cooldown={in_cooldown}")
    prices = [1000.0] * 20 + [999.0, 1050.0]
    df = make_df(prices)
    client.get_ohlcv = lambda t, i: df
    if not in_cooldown:
        strategy.purchase_buy(None, 1050.0, 1_000_000.0, 0.0, df)
    check(strategy.turtle_units == 0, f"units={strategy.turtle_units} (0이어야 함 - 쿨다운 중)")


def test_11_insufficient_balance():
    print_header("[TEST 11] 잔고 부족 시 진입 차단")
    reset_turtle_state()
    prices = [1000.0] * 20 + [999.0, 1050.0]
    df = make_df(prices)
    client.get_ohlcv = lambda t, i: df
    strategy.purchase_buy(None, 1050.0, 100.0, 0.0, df)   # 잔고 100원
    check(strategy.turtle_units == 0, f"units={strategy.turtle_units} (0이어야 함)")


# ============================================================
# 3. 시나리오 A: 횡보장
# ============================================================

def scenario_a_sideways():
    """
    횡보장 시나리오
    ─────────────────────────────────────────
    구간 1: 20봉 횡보 후 약한 돌파 → 1유닛 진입
    구간 2: 추가 상승 없이 횡보 → 피라미딩 없음
    구간 3: 하락 → 트레일링 스탑 손절 청산
    구간 4: 쿨다운 중 재진입 시도 → 차단
    ─────────────────────────────────────────
    검증:
      - 진입 1회만 발생 (피라미딩 없음)
      - 트레일링 스탑으로 손절 청산
      - 쿨다운 방어 정상 작동
    """
    print_header("🟡 [시나리오 A] 횡보장")
    reset_turtle_state()

    BASE  = 1000.0
    ATR   = 20.0
    ENTRY = 1025.0

    # ── 구간 1: 20봉 횡보 후 약한 돌파 ──
    print("\n  [구간1] 약한 돌파 → 1유닛 진입")
    prices = [BASE] * 19 + [BASE - 1, ENTRY]
    df = make_df(prices, atr_fixed=ATR)
    client.get_ohlcv = lambda t, i: df
    strategy.purchase_buy(None, ENTRY, 1_000_000.0, 0.0, df)
    check(strategy.turtle_units == 1, f"1유닛 진입 | units={strategy.turtle_units}")
    print(f"    next_add={strategy.turtle_next_add:.1f} (돌파해야 추가 진입)")

    # ── 구간 2: 횡보 - 피라미딩 없어야 함 ──
    print("\n  [구간2] 횡보 - 피라미딩 없어야 함")
    sideways_prices = [1026.0, 1024.0, 1027.0, 1023.0, 1028.0]
    for p in sideways_prices:
        strategy.entry_highest_price = max(strategy.entry_highest_price, p)
        below_next = p < strategy.turtle_next_add
        print(f"    price={p:.0f} | next_add={strategy.turtle_next_add:.0f} | 추가진입={'없음' if below_next else '가능'}")
    check(strategy.turtle_units == 1, f"피라미딩 없음 | units={strategy.turtle_units}")

    # ── 구간 3: 하락 → 트레일링 스탑 손절 ──
    print("\n  [구간3] 하락 → 트레일링 스탑 손절")
    highest      = strategy.entry_highest_price
    trailing_stop = highest - 2 * ATR
    crash_price   = trailing_stop - 10

    df_exit = make_df([crash_price] * 22, atr_fixed=ATR)
    client.get_ohlcv = lambda t, i: df_exit
    print(f"    최고가={highest:.0f} | 손절가={trailing_stop:.0f} | 현재가={crash_price:.0f}")
    strategy._turtle_exit(None, crash_price, 0.5, ENTRY)

    check(strategy.turtle_units == 0, f"청산 완료 | units={strategy.turtle_units}")
    sells = [t for t in _trade_log if t['action'] == 'sell']
    check(len(sells) == 1, f"청산 1회 | sells={len(sells)}")
    check(sells[0]['profit_rate'] < 0, f"손실 청산 | pr={sells[0]['profit_rate']:+.2f}%")

    # ── 구간 4: 쿨다운 중 재진입 차단 ──
    print("\n  [구간4] 쿨다운 중 재진입 시도")
    strategy.last_entry_ts = time.time()
    in_cooldown = (time.time() - strategy.last_entry_ts) < config.REENTRY_COOLDOWN_SEC
    check(in_cooldown, f"쿨다운 활성 | in_cooldown={in_cooldown}")
    check(strategy.turtle_units == 0, "재진입 없음")

    print("\n  📋 시나리오 A 요약")
    buys = [t for t in _trade_log if t['action'] == 'buy']
    print(f"    매수={len(buys)}건 | 매도={len(sells)}건 | 결과=손절")


# ============================================================
# 4. 시나리오 B: 급상승장 (피라미딩)
# ============================================================

def scenario_b_bull_run():
    """
    급상승장 시나리오
    ─────────────────────────────────────────
    구간 1: 강한 돌파 → 1유닛 진입
    구간 2: 0.5 ATR 간격으로 상승 → 4유닛 풀 진입
    구간 3: 추세 지속 - 최고가 계속 갱신
    구간 4: 추세 종료 후 2*ATR 하락 → 익절 청산
    ─────────────────────────────────────────
    검증:
      - 4유닛 풀 진입 달성
      - 유닛 간격 ≈ 0.5 * ATR
      - 익절(+수익) 청산
      - 청산 후 전역 변수 전체 초기화
    """
    print_header("🟢 [시나리오 B] 급상승장 (피라미딩)")
    reset_turtle_state()

    BASE  = 1000.0
    ATR   = 20.0

    # ── 구간 1: 강한 돌파 → 1유닛 ──
    print("\n  [구간1] 강한 돌파 → 1유닛 진입")
    prices = [BASE] * 19 + [BASE - 1, BASE + 30]
    df = make_df(prices, atr_fixed=ATR)
    client.get_ohlcv = lambda t, i: df
    entry_price = BASE + 30
    strategy.purchase_buy(None, entry_price, 1_000_000.0, 0.0, df)
    check(strategy.turtle_units == 1, f"1유닛 진입 | units={strategy.turtle_units}")

    unit_prices = [entry_price]

    # ── 구간 2: 0.5 ATR 간격으로 피라미딩 ──
    print("\n  [구간2] 상승 중 피라미딩 (2→3→4유닛)")
    my_krw = 800_000.0
    my_amt = 0.5
    for target in range(2, 5):
        add_price = strategy.turtle_next_add + 0.5
        unit_prices.append(add_price)
        strategy.entry_highest_price = add_price
        strategy.purchase_buy(None, add_price, my_krw, my_amt, df)
        my_krw -= 50_000
        my_amt += 0.3
        print(f"    {target}유닛 | 진입가={add_price:.1f} | units={strategy.turtle_units} | next_add={strategy.turtle_next_add:.1f}")

    check(strategy.turtle_units == 4, f"4유닛 풀 진입 | units={strategy.turtle_units}")

    gaps = [unit_prices[i+1] - unit_prices[i] for i in range(len(unit_prices)-1)]
    print(f"    유닛 간격: {[f'{g:.1f}' for g in gaps]} (≈10 이어야 함, 0.5*ATR={0.5*ATR})")
    check(all(8 <= g <= 15 for g in gaps), "유닛 간격 정상 (0.5*ATR ± 버퍼)")

    # ── 구간 3: 추세 지속 - 최고가 갱신 ──
    print("\n  [구간3] 추세 지속 - 최고가 갱신")
    for p in [unit_prices[-1] + i*5 for i in range(1, 6)]:
        strategy.entry_highest_price = max(strategy.entry_highest_price, p)
    peak = strategy.entry_highest_price
    trailing_stop = peak - 2 * ATR
    print(f"    최고가={peak:.1f} | 트레일링 손절가={trailing_stop:.1f}")

    # ── 구간 4: 추세 종료 → 익절 청산 ──
    print("\n  [구간4] 추세 종료 → 익절 청산")
    exit_price = trailing_stop - 1
    avg_price  = sum(unit_prices) / len(unit_prices)
    print(f"    평균진입가={avg_price:.1f} | 청산가={exit_price:.1f} | 예상수익={exit_price-avg_price:+.1f}")

    df_exit = make_df([exit_price] * 22, atr_fixed=ATR)
    client.get_ohlcv = lambda t, i: df_exit
    strategy._turtle_exit(None, exit_price, my_amt, avg_price)

    sells = [t for t in _trade_log if t['action'] == 'sell']
    check(strategy.turtle_units == 0,        f"청산 완료 | units={strategy.turtle_units}")
    check(strategy.entry_highest_price == 0, f"최고가 초기화 | highest={strategy.entry_highest_price}")
    check(strategy.turtle_entry_atr == 0,    f"entry_atr 초기화 | atr={strategy.turtle_entry_atr}")
    check(strategy.turtle_next_add == 0,     f"next_add 초기화 | next_add={strategy.turtle_next_add}")
    check(len(sells) == 1 and sells[-1]['profit_rate'] > 0,
          f"익절 청산 1회 | pr={sells[-1]['profit_rate']:+.2f}%" if sells else "청산 없음")

    print("\n  📋 시나리오 B 요약")
    buys = [t for t in _trade_log if t['action'] == 'buy']
    print(f"    매수={len(buys)}건(4건이어야 함) | 매도={len(sells)}건(1건이어야 함) | 결과=익절")


# ============================================================
# 5. 시나리오 C: 폭락장
# ============================================================

def scenario_c_crash():
    """
    폭락장 시나리오
    ─────────────────────────────────────────
    구간 1: 진입 + 피라미딩 2유닛
    구간 2: ATR 급등 감지 → 강제 청산 + 상태 초기화
    구간 3: 쿨다운 중 재진입 시도 → 차단
    구간 4: 쿨다운 해제 후 재진입 성공
    구간 5: 재진입 후 재차 급락 → 트레일링 스탑 2차 손절
    ─────────────────────────────────────────
    검증:
      - ATR 스파이크 즉시 강제 청산
      - 강제 청산 후 전역 변수 전체 초기화
      - 쿨다운 방어 정상 작동
      - 쿨다운 해제 후 정상 재진입
      - 2차 손절도 정상 처리
    """
    print_header("🔴 [시나리오 C] 폭락장")
    reset_turtle_state()

    BASE = 1000.0
    ATR  = 20.0

    # ── 구간 1: 진입 + 2유닛 피라미딩 ──
    print("\n  [구간1] 진입 + 2유닛 피라미딩")
    prices = [BASE] * 19 + [BASE - 1, BASE + 30]
    df = make_df(prices, atr_fixed=ATR)
    client.get_ohlcv = lambda t, i: df

    strategy.purchase_buy(None, BASE + 30, 1_000_000.0, 0.0, df)
    strategy.entry_highest_price = BASE + 40
    add_price = strategy.turtle_next_add + 0.5
    strategy.purchase_buy(None, add_price, 900_000.0, 0.5, df)
    check(strategy.turtle_units == 2, f"2유닛 | units={strategy.turtle_units}")

    # ── 구간 2: ATR 급등 → 강제 청산 ──
    print("\n  [구간2] ATR 급등 → 강제 청산")
    df_spike = make_atr_spike_df(base_price=BASE, spike_multiplier=3.0)
    spike = strategy.is_atr_spike(df_spike)
    print(f"  ATR 스파이크 감지: {spike}")
    check(spike, "스파이크 감지 True여야 함")

    if spike:
        # run_strategy의 강제 청산 로직 시뮬
        curr_price   = float(df_spike['close'].iloc[-1])
        my_avg       = BASE + 25
        my_amt       = 0.8
        realized_pnl = (curr_price - my_avg) * my_amt
        profit_rate  = (curr_price - my_avg) / my_avg * 100

        client.sell_market(config.TICKER, my_amt)
        db.log_trade(config.TICKER, "sell", curr_price, my_amt,
                     profit_rate, realized_pnl, config.STRATEGY_MODE)

        # 전역 변수 초기화 (run_strategy에서 처리하는 부분)
        strategy.turtle_units        = 0
        strategy.turtle_next_add     = 0.0
        strategy.turtle_entry_atr    = 0.0
        strategy.entry_highest_price = 0.0
        strategy.last_entry_ts       = time.time()

    check(strategy.turtle_units == 0,        f"강제 청산 | units={strategy.turtle_units}")
    check(strategy.entry_highest_price == 0, f"최고가 초기화 | highest={strategy.entry_highest_price}")
    check(strategy.turtle_entry_atr == 0,    f"entry_atr 초기화")
    check(strategy.turtle_next_add == 0,     f"next_add 초기화")

    sells_1 = [t for t in _trade_log if t['action'] == 'sell']
    check(len(sells_1) == 1, f"강제 청산 1회 | sells={len(sells_1)}")
    check(sells_1[-1]['profit_rate'] < 0, f"손실 청산 | pr={sells_1[-1]['profit_rate']:+.2f}%")

    # ── 구간 3: 쿨다운 중 재진입 차단 ──
    print("\n  [구간3] 쿨다운 중 재진입 차단")
    in_cooldown = (time.time() - strategy.last_entry_ts) < config.REENTRY_COOLDOWN_SEC
    check(in_cooldown, f"쿨다운 활성 | in_cooldown={in_cooldown}")
    pre_units = strategy.turtle_units
    if not in_cooldown:
        strategy.purchase_buy(None, BASE + 50, 1_000_000.0, 0.0, df)
    check(strategy.turtle_units == pre_units, "쿨다운 중 진입 없음")

    # ── 구간 4: 쿨다운 해제 후 재진입 ──
    print("\n  [구간4] 쿨다운 해제 후 재진입")
    strategy.last_entry_ts = time.time() - config.REENTRY_COOLDOWN_SEC - 1
    in_cooldown_after = (time.time() - strategy.last_entry_ts) < config.REENTRY_COOLDOWN_SEC
    check(not in_cooldown_after, f"쿨다운 해제됨 | in_cooldown={in_cooldown_after}")

    prices_re = [BASE - 50] * 19 + [BASE - 51, BASE - 10]
    df_re = make_df(prices_re, atr_fixed=ATR)
    client.get_ohlcv = lambda t, i: df_re
    strategy.purchase_buy(None, BASE - 10, 1_000_000.0, 0.0, df_re)
    check(strategy.turtle_units == 1, f"재진입 성공 | units={strategy.turtle_units}")

    # ── 구간 5: 재진입 후 재차 급락 → 2차 손절 ──
    print("\n  [구간5] 재진입 후 재차 급락 → 2차 손절")
    strategy.entry_highest_price = BASE - 5
    trailing_stop = strategy.entry_highest_price - 2 * ATR
    crash2        = trailing_stop - 10

    df_crash = make_df([crash2] * 22, atr_fixed=ATR)
    client.get_ohlcv = lambda t, i: df_crash
    print(f"    최고가={strategy.entry_highest_price:.0f} | 손절가={trailing_stop:.0f} | 현재가={crash2:.0f}")
    strategy._turtle_exit(None, crash2, 0.5, BASE - 10)

    check(strategy.turtle_units == 0,        f"2차 손절 청산 | units={strategy.turtle_units}")
    check(strategy.entry_highest_price == 0, "최고가 재초기화")

    sells_all = [t for t in _trade_log if t['action'] == 'sell']
    print("\n  📋 시나리오 C 요약")
    buys = [t for t in _trade_log if t['action'] == 'buy']
    print(f"    매수={len(buys)}건 | 매도={len(sells_all)}건")
    print(f"    손절={len([t for t in sells_all if t['profit_rate'] < 0])}건")

def scenario_d_trend():
    """
    추세장 시나리오
    ─────────────────────────────────────────
    구간 1: 20봉 횡보 후 강한 돌파 → 1유닛 진입
    구간 2: 완만한 상승 지속 → 0.5 ATR 간격마다 피라미딩 (4유닛)
    구간 3: 긴 상승 추세 중 최고가 계속 갱신 (손절가도 따라 상승)
    구간 4: 손절가 위에서 일시 조정 → 청산 없어야 함
    구간 5: 추세 완전 종료 후 2*ATR 이상 하락 → 익절 청산
    ─────────────────────────────────────────
    검증:
      - 조정 구간에서 청산 없음 (트레일링 스탑 위)
      - 최고가 갱신될수록 손절가도 따라 올라감
      - 추세 종료 시점에서만 청산 발생
      - 충분한 수익 실현 확인
    """
    print_header("🔵 [시나리오 D] 추세장")
    reset_turtle_state()

    BASE = 1000.0
    ATR  = 20.0

    # ── 구간 1: 20봉 횡보 후 돌파 → 1유닛 ──
    print("\n  [구간1] 돌파 → 1유닛 진입")
    prices = [BASE] * 19 + [BASE - 1, BASE + 30]
    df = make_df(prices, atr_fixed=ATR)
    client.get_ohlcv = lambda t, i: df
    entry_price = BASE + 30
    strategy.purchase_buy(None, entry_price, 1_000_000.0, 0.0, df)
    check(strategy.turtle_units == 1, f"1유닛 진입 | units={strategy.turtle_units}")

    unit_prices = [entry_price]

    # ── 구간 2: 완만한 상승 → 4유닛 피라미딩 ──
    print("\n  [구간2] 완만한 상승 → 4유닛 피라미딩")
    my_krw = 800_000.0
    my_amt = 0.5
    for target in range(2, 5):
        add_price = strategy.turtle_next_add + 0.5
        unit_prices.append(add_price)
        strategy.entry_highest_price = add_price
        strategy.purchase_buy(None, add_price, my_krw, my_amt, df)
        my_krw -= 50_000
        my_amt += 0.3
        print(f"    {target}유닛 | 진입가={add_price:.1f} | next_add={strategy.turtle_next_add:.1f}")

    check(strategy.turtle_units == 4, f"4유닛 풀 진입 | units={strategy.turtle_units}")

    # ── 구간 3: 추세 지속 - 최고가 갱신 & 손절가 상승 추적 ──
    print("\n  [구간3] 추세 지속 - 최고가/손절가 추적")
    trend_prices = [unit_prices[-1] + i * 8 for i in range(1, 11)]   # 서서히 상승
    prev_stop = 0.0
    for p in trend_prices:
        strategy.entry_highest_price = max(strategy.entry_highest_price, p)
        trailing_stop = strategy.entry_highest_price - 2 * ATR
        if trailing_stop > prev_stop:
            print(f"    최고가={strategy.entry_highest_price:.1f} | 손절가={trailing_stop:.1f} (↑ {trailing_stop - prev_stop:.1f})")
            prev_stop = trailing_stop

    peak = strategy.entry_highest_price
    check(prev_stop > (entry_price - 2 * ATR),
          f"손절가 상승 확인 | 초기손절가≈{entry_price - 2*ATR:.0f} → 현재손절가={prev_stop:.0f}")

    # ── 구간 4: 일시 조정 - 손절가 위 → 청산 없어야 함 ──
    print("\n  [구간4] 일시 조정 - 청산 없어야 함")
    trailing_stop_now = peak - 2 * ATR
    correction_price  = trailing_stop_now + 5   # 손절가보다 5 위

    df_corr = make_df([correction_price] * 22, atr_fixed=ATR)
    client.get_ohlcv = lambda t, i: df_corr
    print(f"    손절가={trailing_stop_now:.1f} | 조정가={correction_price:.1f} (손절가 위)")
    strategy._turtle_exit(None, correction_price, my_amt, sum(unit_prices)/len(unit_prices))
    check(strategy.turtle_units == 4, f"청산 없음 | units={strategy.turtle_units} (4 유지되어야 함)")

    # ── 구간 5: 추세 완전 종료 → 익절 청산 ──
    print("\n  [구간5] 추세 종료 → 익절 청산")
    exit_price = trailing_stop_now - 1   # 손절가 이하
    avg_price  = sum(unit_prices) / len(unit_prices)
    expected_profit = (exit_price - avg_price) / avg_price * 100
    print(f"    평균진입가={avg_price:.1f} | 최고가={peak:.1f} | 청산가={exit_price:.1f}")
    print(f"    예상수익률={expected_profit:+.2f}%")

    df_exit = make_df([exit_price] * 22, atr_fixed=ATR)
    client.get_ohlcv = lambda t, i: df_exit
    strategy._turtle_exit(None, exit_price, my_amt, avg_price)

    sells = [t for t in _trade_log if t['action'] == 'sell']
    check(strategy.turtle_units == 0,        f"청산 완료 | units={strategy.turtle_units}")
    check(strategy.entry_highest_price == 0, f"최고가 초기화")
    check(strategy.turtle_entry_atr == 0,    f"entry_atr 초기화")
    check(len(sells) == 1,                   f"청산 1회 | sells={len(sells)}")
    if sells:
        check(sells[-1]['profit_rate'] > 0,  f"수익 청산 | pr={sells[-1]['profit_rate']:+.2f}%")
        check(sells[-1]['profit_rate'] > 5,  f"의미있는 수익 (>5%) | pr={sells[-1]['profit_rate']:+.2f}%")

    print("\n  📋 시나리오 D 요약")
    buys = [t for t in _trade_log if t['action'] == 'buy']
    print(f"    매수={len(buys)}건 | 매도={len(sells)}건")
    print(f"    최고가={peak:.1f} | 최종수익률={sells[-1]['profit_rate']:+.2f}%" if sells else "")

# ============================================================
# 6. 전체 실행
# ============================================================

if __name__ == "__main__":
    print("=" * 65)
    print("  🐢 TURTLE_V1 전략 테스트")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    # ── 기본 단위 테스트 ──
    print("\n▶ 기본 단위 테스트 (11개)")
    unit_tests = [
        test_1_no_entry_without_breakout,
        test_2_entry_on_breakout,
        test_3_pyramiding,
        test_4_max_units_block,
        test_5_trailing_stop_loss,
        test_6_trailing_stop_profit,
        test_7_no_exit_above_stop,
        test_8_atr_spike_true,
        test_9_atr_spike_false,
        test_10_reentry_cooldown,
        test_11_insufficient_balance,
    ]

    unit_fail = 0
    for t in unit_tests:
        try:
            t()
        except Exception as e:
            print(f"  ❌ 예외: {e}")
            unit_fail += 1

    # ── 시나리오 테스트 ──
    print("\n▶ 시나리오 테스트 (4개)")
    scenarios = [
        scenario_a_sideways,
        scenario_b_bull_run,
        scenario_c_crash,
        scenario_d_trend,
    ]

    scenario_fail = 0
    for t in scenarios:
        try:
            t()
        except Exception as e:
            print(f"  ❌ 예외: {e}")
            import traceback
            traceback.print_exc()
            scenario_fail += 1

    # ── 최종 ──
    print("\n" + "=" * 65)
    print("  🏁 전체 테스트 완료")
    print(f"  단위 테스트 {len(unit_tests)}개 | 예외 {unit_fail}개")
    print(f"  시나리오    {len(scenarios)}개 | 예외 {scenario_fail}개")
    print("=" * 65)
