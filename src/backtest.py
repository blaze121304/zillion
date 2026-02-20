# src/backtest.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import ccxt
import config

# ============================================================
# 1. 과거 데이터 수집
# ============================================================

def fetch_ohlcv_full(ticker: str, timeframe: str, limit_per_request: int = 200) -> pd.DataFrame:
    upbit = ccxt.upbit()
    all_ohlcv = []

    print(f"📥 데이터 수집 중... ({ticker} {timeframe})")

    # 1. 가장 최근 200개 먼저 수집
    ohlcv = upbit.fetch_ohlcv(ticker, timeframe=timeframe, limit=limit_per_request)
    if not ohlcv:
        return pd.DataFrame()

    all_ohlcv = ohlcv
    oldest_ts = ohlcv[0][0]  # 현재 수집된 가장 오래된 타임스탬프

    print(f"  수집됨: {len(all_ohlcv)}개 | 최초 캔들: {pd.to_datetime(oldest_ts, unit='ms')}")

    # 2. 과거로 계속 거슬러 올라가기
    while True:
        # oldest_ts 이전 데이터 요청
        since = oldest_ts - (limit_per_request * _timeframe_to_ms(timeframe))

        ohlcv = upbit.fetch_ohlcv(
            ticker,
            timeframe=timeframe,
            limit=limit_per_request,
            since=since,
        )

        if not ohlcv or len(ohlcv) == 0:
            break

        # 중복 제거: all_ohlcv 중 oldest_ts 보다 오래된 것만 앞에 추가
        new_ohlcv = [c for c in ohlcv if c[0] < oldest_ts]
        if not new_ohlcv:
            break

        all_ohlcv = new_ohlcv + all_ohlcv
        oldest_ts = all_ohlcv[0][0]

        print(f"  수집됨: {len(all_ohlcv)}개 | 최초 캔들: {pd.to_datetime(oldest_ts, unit='ms')}")

        if len(new_ohlcv) < limit_per_request:
            break

    df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

    print(f"✅ 총 {len(df)}개 캔들 수집 완료")
    print(f"   기간: {df['datetime'].iloc[0]} ~ {df['datetime'].iloc[-1]}")
    return df


def _timeframe_to_ms(timeframe: str) -> int:
    """타임프레임 문자열을 밀리초로 변환"""
    unit  = timeframe[-1]
    value = int(timeframe[:-1])
    multipliers = {
        'm': 60 * 1000,
        'h': 60 * 60 * 1000,
        'd': 24 * 60 * 60 * 1000,
    }
    return value * multipliers.get(unit, 60 * 1000)


# ============================================================
# 2. 지표 계산
# ============================================================

def calculate_atr(df: pd.DataFrame, period: int = 20) -> pd.Series:
    high       = df['high']
    low        = df['low']
    prev_close = df['close'].shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.rolling(window=period).mean()


def prepare_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['atr'] = calculate_atr(df, config.TURTLE_ATR_PERIOD)
    df['entry_high'] = df['high'].shift(1).rolling(window=config.TURTLE_ENTRY_PERIOD).max()
    df['exit_low'] = df['low'].shift(1).rolling(window=config.TURTLE_EXIT_PERIOD).min()

    return df.dropna().reset_index(drop=True)


# ============================================================
# 3. 백테스트 엔진
# ============================================================

def run_backtest(df: pd.DataFrame, initial_capital: float = 3_000_000.0) -> dict:
    """
    TURTLE_V1 백테스트 실행
    - 트레일링 스탑 방식 청산
    - 피라미딩 최대 4유닛
    """
    capital       = initial_capital
    position      = 0.0
    entry_price   = 0.0
    highest_price = 0.0    # 진입 후 최고가 (트레일링 스탑 기준)
    units         = 0      # 현재 보유 유닛 수
    next_add      = 0.0    # 다음 피라미딩 추가 기준가
    entry_atr     = 0.0    # 최초 진입 ATR (유닛 사이즈 고정용)
    last_exit_dt = None  # 마지막 청산 시각 (재진입 쿨다운 기준)
    trades        = []
    equity_curve  = []

    FEE_RATE = 0.0005      # 업비트 수수료 0.05%

    for i, row in df.iterrows():
        curr_price = float(row['close'])
        atr        = float(row['atr'])
        entry_high = float(row['entry_high'])
        dt         = row['datetime']

        # 현재 총자산 = 원화 + 보유 코인 평가액
        total_equity = capital + position * curr_price
        equity_curve.append({"datetime": dt, "equity": total_equity})

        # ── 포지션 없을 때: 신규 진입 체크 ──
        if position == 0:
            # 직전 봉 종가 (첫 봉이면 0)
            prev_close = float(df['close'].iloc[i - 1]) if i > 0 else 0.0

            # 재진입 쿨다운 체크
            # → 마지막 청산 후 REENTRY_COOLDOWN_SEC 이내면 진입 금지
            if last_exit_dt is not None:
                elapsed = (dt - last_exit_dt).total_seconds()
                if elapsed < config.REENTRY_COOLDOWN_SEC:
                    continue

            # 진입 조건:
            #   1) 이번 봉에서 처음으로 20봉 고점 돌파 (직전 봉은 고점 아래)
            #   2) ATR 유효값일 때만 진입
            if prev_close <= entry_high < curr_price and atr > 0:
                # 유닛 계산: 허용손실(총자산 1%) / 손절폭(2*ATR) * 현재가
                risk_krw     = total_equity * (config.TURTLE_RISK_RATE / 100)
                unit_krw     = risk_krw / (2 * atr) * curr_price

                # ATR이 너무 작을 때 매수금액 폭발 방지 (총자산 20% 상한)
                max_unit_krw = total_equity * 0.20
                unit_krw     = min(unit_krw, max_unit_krw)

                # 최소 주문금액 5,000원 보장
                if unit_krw < 5_000:
                    unit_krw = 5_000

                # 잔고 부족 시 스킵
                if unit_krw > capital:
                    continue

                # 매수 실행
                fee      = unit_krw * FEE_RATE
                position = (unit_krw - fee) / curr_price
                capital -= unit_krw

                # 피라미딩 상태 초기화
                entry_price   = curr_price
                highest_price = curr_price
                entry_atr     = atr                     # 최초 ATR 고정
                next_add      = curr_price + 0.5 * atr  # 다음 추가 기준가
                units         = 1

                trades.append({
                    "type"     : "buy",
                    "datetime" : dt,
                    "price"    : curr_price,
                    "amount"   : position,
                    "unit_krw" : unit_krw,
                    "units"    : units,
                    "atr"      : atr,
                })

        # ── 포지션 있을 때: 피라미딩 + 트레일링 스탑 체크 ──
        else:
            # 최고가 갱신 (트레일링 스탑 기준선)
            if curr_price > highest_price:
                highest_price = curr_price

            # entry_atr 방어 코드
            if entry_atr <= 0:
                continue

            # 트레일링 손절가 = 최고가 - 2 * 최초ATR
            # → 최초 ATR 고정: 피라미딩 중 ATR 변동 영향 방지
            trailing_stop = highest_price - 2 * entry_atr

            # 피라미딩 추가 진입 체크
            # → 최대 유닛 미만 + 다음 추가 기준가 돌파 시
            if units < config.TURTLE_MAX_UNITS and curr_price >= next_add:
                risk_krw     = total_equity * (config.TURTLE_RISK_RATE / 100)
                unit_krw     = risk_krw / (2 * entry_atr) * curr_price
                max_unit_krw = total_equity * 0.20
                unit_krw     = min(unit_krw, max_unit_krw)

                if unit_krw < 5_000:
                    unit_krw = 5_000

                if unit_krw <= capital:
                    fee       = unit_krw * FEE_RATE
                    add_amt   = (unit_krw - fee) / curr_price
                    position += add_amt
                    capital  -= unit_krw
                    units    += 1
                    next_add  = curr_price + 0.5 * entry_atr  # 다음 추가 기준가 갱신

                    trades.append({
                        "type"     : "buy",
                        "datetime" : dt,
                        "price"    : curr_price,
                        "amount"   : add_amt,
                        "unit_krw" : unit_krw,
                        "units"    : units,
                    })

            # 트레일링 손절가 이하로 하락 시 전량 청산
            if curr_price <= trailing_stop:
                sell_amount = position * curr_price
                fee         = sell_amount * FEE_RATE
                pnl         = sell_amount - fee - (position * entry_price)
                profit_rate = (curr_price - entry_price) / entry_price * 100

                capital      += sell_amount - fee
                position      = 0.0
                highest_price = 0.0
                units         = 0
                next_add      = 0.0
                entry_atr     = 0.0
                last_exit_dt = dt  # 청산 시각 기록 (재진입 쿨다운용)

                trades.append({
                    "type"        : "sell",
                    "datetime"    : dt,
                    "price"       : curr_price,
                    "exit_reason" : "profit" if pnl > 0 else "loss",
                    "pnl"         : pnl,
                    "profit_rate" : profit_rate,
                })

    # 마지막 포지션 강제 청산
    if position > 0:
        curr_price  = float(df['close'].iloc[-1])
        sell_amount = position * curr_price
        fee         = sell_amount * FEE_RATE
        pnl         = sell_amount - fee - (position * entry_price)
        profit_rate = (curr_price - entry_price) / entry_price * 100
        capital    += sell_amount - fee

        trades.append({
            "type"        : "sell",
            "datetime"    : df['datetime'].iloc[-1],
            "price"       : curr_price,
            "exit_reason" : "force_close",
            "pnl"         : pnl,
            "profit_rate" : profit_rate,
        })

    # ── 성과 계산 ──
    final_equity  = capital
    sell_trades   = [t for t in trades if t['type'] == 'sell']
    total_trades  = len(sell_trades)
    wins          = [t for t in sell_trades if t['pnl'] > 0]
    losses        = [t for t in sell_trades if t['pnl'] <= 0]
    total_pnl     = sum(t['pnl'] for t in sell_trades)
    win_rate      = len(wins) / total_trades * 100 if total_trades > 0 else 0
    avg_win       = np.mean([t['profit_rate'] for t in wins])   if wins   else 0
    avg_loss      = np.mean([t['profit_rate'] for t in losses]) if losses else 0
    profit_factor = (
        abs(sum(t['pnl'] for t in wins)) / abs(sum(t['pnl'] for t in losses))
        if losses and sum(t['pnl'] for t in losses) != 0 else float('inf')
    )

    # MDD 계산
    equity_df = pd.DataFrame(equity_curve)
    peak      = equity_df['equity'].cummax()
    drawdown  = (equity_df['equity'] - peak) / peak * 100
    mdd       = drawdown.min()

    stats = {
        "initial_capital" : initial_capital,
        "final_equity"    : final_equity,
        "total_return"    : (final_equity - initial_capital) / initial_capital * 100,
        "total_trades"    : total_trades,
        "wins"            : len(wins),
        "losses"          : len(losses),
        "win_rate"        : win_rate,
        "avg_win"         : avg_win,
        "avg_loss"        : avg_loss,
        "profit_factor"   : profit_factor,
        "mdd"             : mdd,
        "total_pnl"       : total_pnl,
    }

    return {
        "trades"       : trades,
        "equity_curve" : equity_curve,
        "stats"        : stats,
    }
# ============================================================
# 4. 결과 출력
# ============================================================

def print_result(result: dict):
    s = result['stats']

    print("\n" + "=" * 50)
    print("📊 TURTLE_V1 백테스트 결과")
    print("=" * 50)
    print(f"초기 자본    : {s['initial_capital']:>12,.0f} 원")
    print(f"최종 자산    : {s['final_equity']:>12,.0f} 원")
    print(f"총 수익률    : {s['total_return']:>11.2f} %")
    print(f"총 손익      : {s['total_pnl']:>+12,.0f} 원")
    print("-" * 50)
    print(f"총 트레이드  : {s['total_trades']:>12} 건")
    print(f"승률         : {s['win_rate']:>11.1f} %  ({s['wins']}승 / {s['losses']}패)")
    print(f"평균 수익률  : {s['avg_win']:>+11.2f} %")
    print(f"평균 손실률  : {s['avg_loss']:>+11.2f} %")
    print(f"손익비(PF)   : {s['profit_factor']:>12.2f}")
    print(f"최대 낙폭    : {s['mdd']:>11.2f} %")
    print("=" * 50)

    # 트레이드 내역 상세 출력
    print("\n📋 트레이드 내역")
    print("-" * 70)
    # sell_trades = [t for t in result['trades'] if t['type'] == 'sell']
    # for i, t in enumerate(sell_trades, 1):
        # reason = t.get('exit_reason', '')
        # icon   = "💰" if t['pnl'] > 0 else "⚠️"
        # print(
        #     f"{i:>3}. {icon} {str(t['datetime'])[:16]} | "
        #     f"{reason:<12} | "
        #     f"가격: {t['price']:>8,.1f} | "
        #     f"수익률: {t['profit_rate']:>+7.2f}% | "
        #     f"손익: {t['pnl']:>+10,.0f}원"
        # )

    # 매수/매도 전체 출력 (디버그용)
    for i, t in enumerate(result['trades'], 1):
        if t['type'] == 'buy':
            print(
                f"{i:>3}. 🟢 BUY  {str(t['datetime'])[:16]} | "
                f"가격: {t['price']:>8,.1f} | "
                f"유닛: {t.get('units', '-')} | "
                f"금액: {t.get('unit_krw', 0):>10,.0f}원"
            )
        else:
            icon = "💰" if t['pnl'] > 0 else "⚠️"
            print(
                f"{i:>3}. {icon} SELL {str(t['datetime'])[:16]} | "
                f"{t.get('exit_reason', ''):<12} | "
                f"가격: {t['price']:>8,.1f} | "
                f"수익률: {t['profit_rate']:>+7.2f}% | "
                f"손익: {t['pnl']:>+10,.0f}원"
            )


    print("-" * 70)


# ============================================================
# 5. 실행
# ============================================================

if __name__ == "__main__":
    # 1. 데이터 수집
    df_raw = fetch_ohlcv_full(
        ticker    = config.TICKER,
        timeframe = "1h",
    )

    # 2. 지표 계산
    df = prepare_indicators(df_raw)

    # 3. 백테스트 실행
    result = run_backtest(df, initial_capital=3_000_000.0)

    # 4. 결과 출력
    print_result(result)