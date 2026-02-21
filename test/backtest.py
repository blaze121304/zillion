# src/backtest.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import pandas as pd
import numpy as np
import config
import requests
import time


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')

# ============================================================
# 1. 과거 데이터 수집
# ============================================================

def fetch_ohlcv_full(ticker: str, timeframe: str = "60") -> pd.DataFrame:
    """
    업비트 REST API 직접 호출로 전체 과거 데이터 수집
    - ticker  : "KRW-XRP" 형식 (업비트 native)
    - timeframe: 분 단위 문자열 ("60" = 1시간봉, "240" = 4시간봉)
    - 상장일까지 전체 수집 가능
    """
    url = f"https://api.upbit.com/v1/candles/minutes/{timeframe}"
    all_ohlcv = []
    to = None  # None이면 현재 시각 기준 최근 200개

    print(f"📥 데이터 수집 중... ({ticker} {timeframe}분봉)")

    while True:
        params = {"market": ticker, "count": 200}
        if to:
            params["to"] = to

        resp = requests.get(url, params=params)
        data = resp.json()

        if not data or len(data) == 0:
            break

        all_ohlcv = data + all_ohlcv  # 오래된 데이터를 앞에 붙임

        # 가장 오래된 캔들의 시각을 다음 to로 설정
        oldest = data[-1]["candle_date_time_utc"]
        print(f"\r  수집: {len(all_ohlcv)}개 | 최초 캔들: {oldest}", end="")

        if len(data) < 200:
            break  # 더 이상 데이터 없음

        to = oldest  # 다음 루프: oldest 이전 데이터 요청
        time.sleep(0.11)  # API 제한: 초당 10회 → 0.1초 간격

    print(f"\n✅ 총 {len(all_ohlcv)}개 수집 완료")

    # DataFrame 변환
    rows = []
    for d in all_ohlcv:
        rows.append([
            d["timestamp"],
            d["opening_price"],
            d["high_price"],
            d["low_price"],
            d["trade_price"],
            d["candle_acc_trade_volume"],
        ])

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

    print(f"   기간: {df['datetime'].iloc[0]} ~ {df['datetime'].iloc[-1]}")
    return df

# ── 데이터 경로 동적 생성 ──
def get_data_path(ticker: str, timeframe: str) -> str:
    """
    ticker, timeframe 기반으로 데이터 파일 경로 생성
    예: KRW-XRP, 60 → data/KRW-XRP_60m.csv
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, f"{ticker}_{timeframe}m.csv")

def save_ohlcv(df: pd.DataFrame, ticker: str, timeframe: str):
    """수집한 데이터를 CSV로 저장"""
    path = get_data_path(ticker, timeframe)
    df.to_csv(path, index=False)
    print(f"💾 데이터 저장 완료: {path} ({len(df)}개)")

def load_ohlcv(ticker: str, timeframe: str) -> pd.DataFrame:
    """저장된 CSV에서 데이터 로드"""
    path = get_data_path(ticker, timeframe)
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.dropna(subset=["datetime"]).reset_index(drop=True)  # ← 추가
    print(f"📂 데이터 로드 완료: {path} ({len(df)}개)")
    print(f"   기간: {df['datetime'].iloc[0]} ~ {df['datetime'].iloc[-1]}")
    return df

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
    df['exit_low_10'] = df['low'].rolling(10).min().shift(1)
    df['exit_low_20'] = df['low'].rolling(20).min().shift(1)

    return df.dropna().reset_index(drop=True)


# ============================================================
# 3. 백테스트 엔진
# ============================================================

def run_backtest(df: pd.DataFrame, initial_capital: float = config.BACKTEST_INITIAL_CAPITAL) -> dict:
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
    entry_cost   = 0.0     # 실제 총 투입 원가 추적
    last_exit_dt = None    # 마지막 청산 시각 (재진입 쿨다운 기준)
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

            # ATR 급등 시 진입 차단
            avg_atr = df['atr'].iloc[max(0, i - config.ATR_SPIKE_PERIOD):i].mean()
            atr_spike = (avg_atr > 0) and (atr / avg_atr >= config.ATR_SPIKE_MULTIPLIER)

            if atr_spike:
                continue  # 진입 차단

            # 진입 조건:
            #   1) 이번 봉에서 처음으로 20봉 고점 돌파 (직전 봉은 고점 아래)
            #   2) ATR 유효값일 때만 진입
            if curr_price > entry_high and prev_close <= entry_high and atr > 0:
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
                entry_cost = unit_krw - fee  # ← [수정] 1유닛 원가 초기화
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
                # 1. 최고가 갱신
                if curr_price > highest_price:
                    highest_price = curr_price

                # 2. entry_atr 방어 코드
                if entry_atr <= 0:
                    continue

                # 3. trailing_stop 계산
                trailing_stop = highest_price - 2 * entry_atr

                # 4. ATR 급등 체크
                avg_atr = df['atr'].iloc[max(0, i - config.ATR_SPIKE_PERIOD):i].mean()
                atr_spike = (avg_atr > 0) and (atr / avg_atr >= config.ATR_SPIKE_MULTIPLIER)

                # 5. 청산 조건 체크
                # if atr_spike:
                #     exit_reason = "atr_spike"
                # elif curr_price <= trailing_stop:
                #     exit_reason = "trailing_stop"
                # else:
                #     exit_reason = None

                # 5. 청산 조건 체크
                exit_mode = config.TURTLE_EXIT_MODE.upper()

                if atr_spike:
                    exit_reason = "atr_spike"

                elif exit_mode == "TRAILING":
                    if curr_price <= trailing_stop:
                        exit_reason = "trailing_stop"
                    else:
                        exit_reason = None

                elif exit_mode == "10DAY_LOW":
                    exit_low = float(row.get('exit_low_10', 0) or 0)
                    if exit_low > 0 and curr_price <= exit_low:
                        exit_reason = "10day_low"
                    else:
                        exit_reason = None

                elif exit_mode == "20DAY_LOW":
                    exit_low = float(row.get('exit_low_20', 0) or 0)
                    if exit_low > 0 and curr_price <= exit_low:
                        exit_reason = "20day_low"
                    else:
                        exit_reason = None

                else:
                    # 알 수 없는 모드 → TRAILING 폴백
                    if curr_price <= trailing_stop:
                        exit_reason = "trailing_stop"
                    else:
                        exit_reason = None

                # 6. 청산 실행 (exit_reason 있으면 피라미딩 스킵하고 바로 청산)
                if exit_reason:
                    sell_amount = position * curr_price
                    fee = sell_amount * FEE_RATE

                    # ✅ [수정] 가중평균 진입가 기반 pnl 계산
                    weighted_avg = entry_cost / position
                    pnl = sell_amount - fee - entry_cost
                    profit_rate = (curr_price - weighted_avg) / weighted_avg * 100

                    capital += sell_amount - fee

                    # ✅ [수정] entry_cost 리셋 추가
                    position = 0.0
                    highest_price = 0.0
                    units = 0
                    next_add = 0.0
                    entry_atr = 0.0
                    entry_cost = 0.0
                    last_exit_dt = dt

                    trades.append({
                        "type": "sell",
                        "datetime": dt,
                        "price": curr_price,
                        "exit_reason": exit_reason,  # ← atr_spike / trailing_stop 구분
                        "pnl": pnl,
                        "profit_rate": profit_rate,
                    })
                    continue  # ← 청산 후 피라미딩 스킵

                # 7. 피라미딩 추가 진입 체크 (청산 없을 때만 실행)
                if units < config.TURTLE_MAX_UNITS and curr_price >= next_add:
                    risk_krw = total_equity * (config.TURTLE_RISK_RATE / 100)
                    unit_krw = risk_krw / (2 * entry_atr) * curr_price
                    max_unit_krw = total_equity * 0.20
                    unit_krw = min(unit_krw, max_unit_krw)

                    if unit_krw < 5_000:
                        unit_krw = 5_000

                    if unit_krw <= capital:
                        fee = unit_krw * FEE_RATE
                        add_amt = (unit_krw - fee) / curr_price
                        position += add_amt
                        capital -= unit_krw
                        entry_cost += unit_krw - fee  # 수수료 제외 실투입금 누적
                        units += 1
                        next_add = curr_price + 0.5 * entry_atr

                        trades.append({
                            "type": "buy",
                            "datetime": dt,
                            "price": curr_price,
                            "amount": add_amt,
                            "unit_krw": unit_krw,
                            "units": units,
                        })


    # 마지막 포지션 강제 청산
    if position > 0:
        curr_price  = float(df['close'].iloc[-1])
        sell_amount = position * curr_price
        fee         = sell_amount * FEE_RATE

        # ✅ [수정] 가중평균 진입가 기반 pnl 계산
        weighted_avg = entry_cost / position  # 가중평균 진입가
        pnl = sell_amount - fee - entry_cost
        profit_rate = (curr_price - weighted_avg) / weighted_avg * 100
        capital    += sell_amount - fee

        position = 0.0
        highest_price = 0.0
        units = 0
        next_add = 0.0
        entry_atr = 0.0
        entry_cost = 0.0  # ← 추가

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

    # ✅ 매도(청산)만 출력
    if config.BACKTEST_PRINT_SELL_ONLY:
        print("\n📋 트레이드 내역 (매도)")
        print("-" * 70)
        sell_trades = [t for t in result['trades'] if t['type'] == 'sell']
        for i, t in enumerate(sell_trades, 1):
            reason = t.get('exit_reason', '')
            icon = "💰" if t['pnl'] > 0 else "⚠️"
            print(
                f"{i:>3}. {icon} {str(t['datetime'])[:16]} | "
                f"{reason:<12} | "
                f"가격: {t['price']:>8,.1f} | "
                f"수익률: {t['profit_rate']:>+7.2f}% | "
                f"손익: {t['pnl']:>+10,.0f}원"
            )

    #✅ 매수/매도 전체 출력 (디버그용)
    elif config.BACKTEST_PRINT_ALL_TRADES:
        print("\n📋 트레이드 내역 (매수/매도 전체 - 디버그용)")
        print("-" * 70)
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

    if config.BACKTEST_PRINT_MONTHLY:
        print_monthly_yearly(result)

    if config.BACKTEST_PRINT_CRASH:
        print_crash_analysis(result)

# ──────────────────────────────────────────────────────────
# 1. 월별 / 연도별 수익률 출력
# ──────────────────────────────────────────────────────────
def print_monthly_yearly(result: dict):
    trades = result['trades']
    stats  = result.get('stats', {})
    initial_capital = stats.get('initial_capital', 3_000_000.0)

    sells = [t for t in trades if t['type'] == 'sell']
    if not sells:
        return

    # 월별/연도별 집계
    monthly = {}
    yearly  = {}
    for t in sells:
        mo = str(t['datetime'])[:7]   # 'YYYY-MM'
        yr = str(t['datetime'])[:4]   # 'YYYY'
        for d, key in [(monthly, mo), (yearly, yr)]:
            if key not in d:
                d[key] = {'pnl': 0.0, 'wins': 0, 'losses': 0}
            d[key]['pnl'] += t['pnl']
            if t['pnl'] > 0:
                d[key]['wins'] += 1
            else:
                d[key]['losses'] += 1

    # 누적 equity 추적으로 수익률 계산
    equity      = initial_capital
    cur_year    = None;  year_start  = initial_capital
    cur_month   = None;  month_start = initial_capital
    year_ret    = {}
    month_ret   = {}

    for t in sells:
        yr = str(t['datetime'])[:4]
        mo = str(t['datetime'])[:7]

        if yr != cur_year:
            if cur_year is not None:
                year_ret[cur_year] = (equity - year_start) / year_start * 100 if year_start else 0.0
            cur_year   = yr
            year_start = equity

        if mo != cur_month:
            if cur_month is not None:
                month_ret[cur_month] = (equity - month_start) / month_start * 100 if month_start else 0.0
            cur_month   = mo
            month_start = equity

        equity += t['pnl']

    # 마지막 연/월 처리
    if cur_year:
        year_ret[cur_year]   = (equity - year_start)  / year_start  * 100 if year_start  else 0.0
    if cur_month:
        month_ret[cur_month] = (equity - month_start) / month_start * 100 if month_start else 0.0

    # 월별 출력
    print("\n" + "=" * 64)
    print("📅 월별 수익률")
    print("=" * 64)
    for mo in sorted(monthly.keys()):
        pnl = monthly[mo]['pnl']
        ret = month_ret.get(mo, 0.0)
        bar = '█' * min(int(abs(ret) / 2), 28)
        icon = '💰' if pnl >= 0 else '📉'
        print(f"{icon} {mo}  {ret:>+7.2f}%  {bar:<28}  손익: {pnl:>+12,.0f}원")

    # 연도별 출력
    print("\n" + "=" * 64)
    print("📆 연도별 수익률")
    print("=" * 64)
    print(f"{'연도':<6}  {'수익률':>8}  {'손익':>16}  {'트레이드':>8}  승/패")
    print("-" * 64)
    for yr in sorted(yearly.keys()):
        pnl    = yearly[yr]['pnl']
        wins   = yearly[yr]['wins']
        losses = yearly[yr]['losses']
        total  = wins + losses
        ret    = year_ret.get(yr, 0.0)
        icon   = '💰' if pnl >= 0 else '📉'
        print(f"{icon} {yr}  {ret:>+8.2f}%  {pnl:>+16,.0f}원  {total:>8}건  {wins}승/{losses}패")


# ──────────────────────────────────────────────────────────
# 2. 폭락 구간 방어 분석 출력
# ──────────────────────────────────────────────────────────
CRASH_PERIODS = [
    {
        "name":   "2018 코인 대폭락",
        "period": "2018.01 ~ 2018.12",
        "start":  "2018-01-01",
        "end":    "2018-12-31",
        "factor": "BTC -85%, XRP -95% 장기 하락장",
    },
    {
        "name":   "2020.03 코로나 쇼크",
        "period": "2020.03.01 ~ 2020.03.31",
        "start":  "2020-03-01",
        "end":    "2020-03-31",
        "factor": "코로나 팬데믹 공포, 전 자산군 동반 급락",
    },
    {
        "name":   "2021.05 중국 채굴 금지",
        "period": "2021.05.01 ~ 2021.05.31",
        "start":  "2021-05-01",
        "end":    "2021-05-31",
        "factor": "중국 암호화폐 채굴 전면 금지",
    },
    {
        "name":   "2022.05 루나 사태",
        "period": "2022.05.01 ~ 2022.05.31",
        "start":  "2022-05-01",
        "end":    "2022-05-31",
        "factor": "테라/루나 붕괴, 시가총액 40조 증발",
    },
    {
        "name":   "2022.11 FTX 붕괴",
        "period": "2022.11.01 ~ 2022.11.30",
        "start":  "2022-11-01",
        "end":    "2022-11-30",
        "factor": "FTX 거래소 파산, 연쇄 신뢰 붕괴",
    },
    {
        "name":   "2024.08 엔캐리 청산",
        "period": "2024.08.01 ~ 2024.08.31",
        "start":  "2024-08-01",
        "end":    "2024-08-31",
        "factor": "일본 금리 인상, 엔캐리 트레이드 급청산",
    },
    {
        "name":   "2024.12 계엄령",
        "period": "2024.12.01 ~ 2024.12.10",
        "start":  "2024-12-01",
        "end":    "2024-12-10",
        "factor": "한국 계엄령 선포, XRP 2시간 내 -28% 급락",
    },
]


def print_crash_analysis(result: dict):
    sells = [t for t in result['trades'] if t['type'] == 'sell']

    print("\n" + "=" * 64)
    print("🚨 주요 폭락 구간 방어 분석")
    print("=" * 64)

    for i, cp in enumerate(CRASH_PERIODS, 1):
        ps = [t for t in sells
              if cp['start'] <= str(t['datetime'])[:10] <= cp['end']]

        print(f"\n[{i}] {cp['name']} ({cp['period']})")

        if not ps:
            print(f"    해당 기간 트레이드 없음")
            continue

        pnl_sum    = sum(t['pnl'] for t in ps)
        wins       = [t for t in ps if t['pnl'] > 0]
        losses     = [t for t in ps if t['pnl'] <= 0]
        max_loss_t = min(ps, key=lambda x: x['profit_rate'])
        max_loss   = max_loss_t['profit_rate']
        atr_cnt    = sum(1 for t in ps if t.get('exit_reason') == 'atr_spike')

        result_icon = "✅" if pnl_sum >= 0 else "❌"
        result_text = "플러스 방어 성공" if pnl_sum >= 0 else "방어 실패"

        # 방어 이유 자동 생성
        defense = []
        if atr_cnt > 0:
            defense.append(f"ATR 스파이크 {atr_cnt}회 발동 → 변동성 급등 시 조기 청산")
        if wins and losses:
            avg_win_pnl  = sum(t['pnl'] for t in wins)  / len(wins)
            avg_loss_pnl = abs(sum(t['pnl'] for t in losses) / len(losses))
            if avg_win_pnl > avg_loss_pnl * 1.5:
                defense.append(
                    f"수익 트레이드 규모 우세 "
                    f"(평균 +{avg_win_pnl:,.0f}원 vs -{avg_loss_pnl:,.0f}원)"
                )
        if max_loss > -5.0:
            defense.append(
                f"트레일링 스탑으로 손실 제한 (최대 손실 {max_loss:.2f}%)"
            )
        if not defense:
            defense.append("유닛 분산으로 포지션 리스크 분산")

        print(f"    A. 폭락요인  : {cp['factor']}")
        print(f"    B. 손실율    : 최대 단일 손실 {max_loss:+.2f}%  ({str(max_loss_t['datetime'])[:16]})")
        print(f"    C. 방어결과  : {result_icon} {result_text} ({pnl_sum:+,.0f}원 | {len(wins)}승 {len(losses)}패)")
        for d in defense:
            print(f"                   - {d}")

    print("\n" + "=" * 64)
# ============================================================
# 6. 그리드 서치 (파라미터 최적화)
# ============================================================

def run_grid_search(df_raw: pd.DataFrame, initial_capital: float = config.BACKTEST_INITIAL_CAPITAL):
    """
    파라미터 조합을 자동 순회하며 최적 조합 탐색
    - 각 조합마다 백테스트 실행 후 성과 비교
    - 최종적으로 수익률 기준 상위 10개 출력
    """

    # ── 탐색할 파라미터 범위 정의 ──
    param_grid = {
        "TURTLE_ENTRY_PERIOD" : [10, 15, 20, 25, 30],
        "TURTLE_ATR_PERIOD"   : [10, 14, 20],
        "TURTLE_RISK_RATE"    : [0.5, 1.0, 1.5, 2.0],
        "TURTLE_MAX_UNITS"    : [1, 2, 3, 4],
        "REENTRY_COOLDOWN_SEC": [43200, 86400, 172800, 259200],  # 12h, 24h, 48h, 72h
    }

    # 전체 조합 수 계산
    total = 1
    for v in param_grid.values():
        total *= len(v)
    print(f"\n🔍 그리드 서치 시작 | 총 {total}개 조합\n")

    results = []
    count   = 0

    # ── 파라미터 조합 순회 ──
    for entry_period in param_grid["TURTLE_ENTRY_PERIOD"]:
        for atr_period in param_grid["TURTLE_ATR_PERIOD"]:
            for risk_rate in param_grid["TURTLE_RISK_RATE"]:
                for max_units in param_grid["TURTLE_MAX_UNITS"]:
                    for cooldown in param_grid["REENTRY_COOLDOWN_SEC"]:
                        count += 1

                        # config 파라미터 임시 변경
                        # → 각 조합마다 config 값을 덮어써서 백테스트에 반영
                        config.TURTLE_ENTRY_PERIOD  = entry_period
                        config.TURTLE_ATR_PERIOD    = atr_period
                        config.TURTLE_RISK_RATE     = risk_rate
                        config.TURTLE_MAX_UNITS     = max_units
                        config.REENTRY_COOLDOWN_SEC = cooldown

                        # 지표 재계산 (ENTRY_PERIOD, ATR_PERIOD가 바뀌므로 필수)
                        df = prepare_indicators(df_raw)

                        # 백테스트 실행
                        result = run_backtest(df, initial_capital=initial_capital)
                        s      = result['stats']

                        # 진행 상황 출력
                        print(
                            f"\r[{count:>4}/{total}] "
                            f"EP={entry_period:>2} ATR={atr_period:>2} "
                            f"RISK={risk_rate:.1f} UNIT={max_units} "
                            f"CD={cooldown//3600:>2}h | "
                            f"수익률={s['total_return']:>+7.2f}% "
                            f"PF={s['profit_factor']:>5.2f} "
                            f"MDD={s['mdd']:>+6.2f}%",
                            end=""
                        )

                        results.append({
                            "entry_period" : entry_period,
                            "atr_period"   : atr_period,
                            "risk_rate"    : risk_rate,
                            "max_units"    : max_units,
                            "cooldown_h"   : cooldown // 3600,
                            "total_return" : s['total_return'],
                            "win_rate"     : s['win_rate'],
                            "profit_factor": s['profit_factor'],
                            "mdd"          : s['mdd'],
                            "total_trades" : s['total_trades'],
                            "total_pnl"    : s['total_pnl'],
                        })

    print(f"\n\n✅ 그리드 서치 완료 | {total}개 조합 탐색")

    # ── 결과 정렬 및 상위 출력 ──
    # 정렬 기준: 수익률 내림차순 (같으면 MDD 오름차순)
    results.sort(key=lambda x: (-x['total_return'], x['mdd']))

    for rank, r in enumerate(results[:10], 1):
        print(
            f"{rank:>4} | "
            f"{r['entry_period']:>4} {r['atr_period']:>4} "
            f"{r['risk_rate']:>5.1f} {r['max_units']:>5} {r['cooldown_h']:>3}h | "
            f"{r['total_return']:>+8.2f}% "
            f"{r['win_rate']:>6.1f}% "
            f"{r['profit_factor']:>6.2f} "
            f"{r['mdd']:>+8.2f}% "
            f"{r['total_trades']:>7}건"
        )

    print("=" * 80)

    # 1위 조합을 config에 반영
    best = results[0]
    print(f"\n✅ 🏆 TOP 10 파라미터 조합 (1위 기준):")
    print(f"   TURTLE_ENTRY_PERIOD  = {best['entry_period']}")
    print(f"   TURTLE_ATR_PERIOD    = {best['atr_period']}")
    print(f"   TURTLE_RISK_RATE     = {best['risk_rate']}")
    print(f"   TURTLE_MAX_UNITS     = {best['max_units']}")
    print(f"   REENTRY_COOLDOWN_SEC = {best['cooldown_h'] * 3600}  # {best['cooldown_h']}h")

    # ── 전체 결과 CSV 저장 ──
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(
        by=["total_return", "mdd"],
        ascending=[False, False]  # 수익률 내림차순, MDD 오름차순
    ).reset_index(drop=True)
    results_df.index += 1  # 순위 1부터 시작
    results_df.index.name = "rank"

    os.makedirs(DATA_DIR, exist_ok=True)
    csv_path = os.path.join(DATA_DIR, f"grid_search_{config.TICKER_UPBIT}_{config.TIMEFRAME}m.csv")
    results_df.to_csv(csv_path)
    print(f"\n💾 전체 결과 저장 완료: {csv_path} ({len(results_df)}개 조합)")

    # ── TOP 10 콘솔 출력 ──
    print("\n" + "=" * 80)
    print("🏆 TOP 10 파라미터 조합 (수익률 기준)")
    print("=" * 80)
    print(
        f"{'순위':>4} | {'EP':>4} {'ATR':>4} {'RISK':>5} {'UNIT':>5} {'CD':>4} | "
        f"{'수익률':>8} {'승률':>7} {'PF':>6} {'MDD':>8} {'트레이드':>7}"
    )
    print("-" * 80)

    for rank, r in results_df.head(10).iterrows():
        print(
            f"{rank:>4} | "
            f"{r['entry_period']:>4} {r['atr_period']:>4} "
            f"{r['risk_rate']:>5.1f} {r['max_units']:>5} {r['cooldown_h']:>3}h | "
            f"{r['total_return']:>+8.2f}% "
            f"{r['win_rate']:>6.1f}% "
            f"{r['profit_factor']:>6.2f} "
            f"{r['mdd']:>+8.2f}% "
            f"{r['total_trades']:>7}건"
        )
    print("=" * 80)

    # ── 1위 조합 출력 ──
    best = results_df.iloc[0]
    print(f"\n✅ 최적 파라미터 (1위 기준):")
    print(f"   TURTLE_ENTRY_PERIOD  = {int(best['entry_period'])}")
    print(f"   TURTLE_ATR_PERIOD    = {int(best['atr_period'])}")
    print(f"   TURTLE_RISK_RATE     = {best['risk_rate']}")
    print(f"   TURTLE_MAX_UNITS     = {int(best['max_units'])}")
    print(f"   REENTRY_COOLDOWN_SEC = {int(best['cooldown_h']) * 3600}  # {int(best['cooldown_h'])}h")

    return results_df

# ============================================================
# 파일 저장
# ============================================================

def save_trades_csv(result: dict, ticker: str, timeframe: str):
    """전체 트레이드 내역을 CSV로 저장"""
    trades = result['trades']
    rows = []

    for t in trades:
        rows.append({
            "type"        : t.get("type"),
            "datetime"    : t.get("datetime"),
            "price"       : t.get("price"),
            "units"       : t.get("units", ""),
            "unit_krw"    : t.get("unit_krw", ""),
            "amount"      : t.get("amount", ""),
            "exit_reason" : t.get("exit_reason", ""),
            "profit_rate" : t.get("profit_rate", ""),
            "pnl"         : t.get("pnl", ""),
        })

    df = pd.DataFrame(rows)
    path = os.path.join(DATA_DIR, f"trades_{ticker}_{timeframe}m.csv")
    df.to_csv(path, index=False)
    print(f"💾 트레이드 내역 저장: {path} ({len(df)}건)")


# ============================================================
# 7. 실행
# ============================================================

if __name__ == "__main__":
    # 1. 데이터 로드
    df_raw = load_ohlcv(config.TICKER_UPBIT, config.TIMEFRAME)
    if df_raw.empty:
        print("📥 저장된 데이터 없음 → API에서 수집")
        df_raw = fetch_ohlcv_full(ticker=config.TICKER_UPBIT, timeframe=config.TIMEFRAME)
        save_ohlcv(df_raw, config.TICKER_UPBIT, config.TIMEFRAME)

    # 2. 그리드 서치
    if config.BACKTEST_GRID_SEARCH:
        grid_csv = os.path.join(DATA_DIR, f"grid_search_{config.TICKER_UPBIT}_{config.TIMEFRAME}m.csv")
        if os.path.exists(grid_csv):
            print(f"📂 그리드 서치 결과 로드: {grid_csv}")
            results_df = pd.read_csv(grid_csv, index_col="rank")
            print(results_df.head(10).to_string())
        else:
            run_grid_search(df_raw, initial_capital=config.BACKTEST_INITIAL_CAPITAL)

    # 3. 단일 백테스트
    if config.BACKTEST_SINGLE_RUN:
        df = prepare_indicators(df_raw)
        result = run_backtest(df, initial_capital=config.BACKTEST_INITIAL_CAPITAL)
        print_result(result)
        #save_trades_csv(result, config.TICKER_UPBIT, config.TIMEFRAME)  # ← 추가
