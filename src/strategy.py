import time
import pandas as pd
import config
import upbit_client as client
import database as db
import requests

# 재진입 쿨다운용 타임스탬프
last_entry_ts: float = 0.0

# 진입 후 최고가 추적 (트레일링 스탑용)
entry_highest_price: float = 0.0

# 피라미딩 관련 전역 변수
turtle_units: int         = 0      # 현재 보유 유닛 수
turtle_next_add: float    = 0.0    # 다음 추가 진입 기준가
turtle_entry_atr: float   = 0.0    # 최초 진입 시 ATR (유닛 사이즈 고정용)

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=20):
    """ATR (Average True Range) 계산"""
    high = df['high']
    low  = df['low']
    prev_close = df['close'].shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.rolling(window=period).mean()

def calc_turtle_unit_size(total_equity: float, atr: float, curr_price: float) -> float:
    """
    터틀 유닛 사이즈 계산
    unit_krw = (총자산 × 1%) / (2 × ATR) × 현재가
    → ATR이 너무 작을 때 폭발 방지용 최대 20% 캡 적용
    """
    if atr <= 0:
        return 0.0
    risk_krw     = total_equity * (config.TURTLE_RISK_RATE / 100)
    unit_krw     = risk_krw / (2 * atr) * curr_price
    max_unit_krw = total_equity * 0.20
    return min(unit_krw, max_unit_krw)

def send_msg(bot_app, text: str):
    """
    텔레그램 메시지 전송 (동기 HTTP 방식)
    - bot_app은 더 이상 사용하지 않지만, 기존 시그니처 유지용으로 둠.
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return

    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            params={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": text,
            },
            timeout=5,
        )
        if resp.status_code != 200:
            print(f"\n⚠️ 텔레그램 전송 실패: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"\n⚠️ 텔레그램 전송 예외 발생: {e}")

#전략 설정

def run_strategy(bot_app):
    print(f"🚀 [전략 가동] {config.TICKER} | 전략: {config.STRATEGY_MODE}")

    global turtle_units, turtle_next_add, turtle_entry_atr, entry_highest_price

    # ✅ 시작 시 초기 자산 한 번만 계산
    init_avg, init_amt = client.get_balance(config.TICKER)
    init_krw = client.get_krw_balance()
    init_price = client.get_current_price(config.TICKER)
    initial_equity = init_krw + init_amt * init_price
    print(f"💰 초기 자산: {initial_equity:,.0f}원")

    # 시장 필터 상태 초기화
    market_off = False          # True면 '폭락장 → 신규 진입 OFF'
    last_market_check = 0.0     # 마지막으로 BTC 상태를 체크한 시각 (epoch sec)

    while True:
        try:
            # ✅ 계좌 손실 한도 체크 - 루프 제일 앞
            # 잔고 조회
            my_avg, my_amt = client.get_balance(config.TICKER)
            my_krw = client.get_krw_balance()
            curr_price_now = client.get_current_price(config.TICKER)
            total_equity = my_krw + my_amt * curr_price_now
            drawdown = (total_equity - initial_equity) / initial_equity * 100

            # 손실한도 체크
            if drawdown <= config.MAX_DRAWDOWN_LIMIT:
                print(f"\n🛑 [계좌 손실 한도] {drawdown:.2f}% (기준: {config.MAX_DRAWDOWN_LIMIT}%)")
                if my_amt > 0:
                    client.sell_market(config.TICKER, my_amt)
                    realized_pnl = (curr_price_now - my_avg) * my_amt
                    db.log_trade(config.TICKER, "sell", curr_price_now, my_amt,
                                 drawdown, realized_pnl, config.STRATEGY_MODE)
                    turtle_units = 0
                    turtle_next_add = 0.0
                    turtle_entry_atr = 0.0
                    entry_highest_price = 0.0

                send_msg(bot_app,
                         f"🛑 [계좌 손실 한도 도달]\n"
                         f"초기자산: {initial_equity:,.0f}원\n"
                         f"현재자산: {total_equity:,.0f}원\n"
                         f"손실률: {drawdown:.2f}%\n"
                         f"봇을 중단합니다."
                         )
                break

            # 1. 캔들 데이터 조회
            df = client.get_ohlcv(config.TICKER, config.TIMEFRAME)
            if df.empty:
                print("\n⚠️ 캔들 데이터 없음, 잠시 대기")
                time.sleep(3)
                continue

            curr_price = df['close'].iloc[-1]

            # 3. 모니터링 출력
            print(
                f"\r[Monitoring] Price: {curr_price:,.0f} | "
                f"KRW: {my_krw:,.0f}원 | Amt: {my_amt:.4f}",
                end=""
            )

            # 4. 시장 필터
            if config.USE_MARKET_FILTER:
                market_off, last_market_check = market_filter(
                    bot_app, last_market_check, market_off
                )
            else:
                market_off = False

            # 5. 재진입 쿨다운 / 거래 시간대 체크
            global last_entry_ts
            in_cooldown = (time.time() - last_entry_ts) < config.REENTRY_COOLDOWN_SEC
            in_trade_hours = config.ENTRY_START_HOUR <= time.localtime().tm_hour <= config.ENTRY_END_HOUR

            # 6. 매수 로직
            # ATR 급등 감지 필터
            df_1h = client.get_ohlcv(config.TICKER, "1h")
            atr_spike = is_atr_spike(df_1h)

            # 기존 매수 로직
            if atr_spike:
                # 기존 포지션 즉시 청산
                if my_amt > 0:
                    print(f"\n🚨 [ATR 급등 감지] 기존 포지션 즉시 청산")
                    client.sell_market(config.TICKER, my_amt)
                    realized_pnl = (curr_price - my_avg) * my_amt
                    profit_rate = (curr_price - my_avg) / my_avg * 100

                    db.log_trade(
                        config.TICKER, "sell", curr_price, my_amt,
                        profit_rate, realized_pnl, config.STRATEGY_MODE
                    )
                    send_msg(
                        bot_app,
                        f"🚨 [ATR 급등 감지 - 강제 청산]\n"
                        f"현재 ATR이 평균의 {config.ATR_SPIKE_MULTIPLIER}배 이상\n"
                        f"수익률: {profit_rate:.2f}%\n"
                        f"실현손익: {int(realized_pnl):,}원"
                    )
                    # 피라미딩 상태 초기화
                    turtle_units = 0
                    turtle_next_add = 0.0
                    turtle_entry_atr = 0.0
                    entry_highest_price = 0.0
                    time.sleep(10)

            elif (not market_off) and (not in_cooldown) and in_trade_hours:
                purchase_buy(bot_app, curr_price, my_krw, my_amt, df_1h)


            # 7. 손절 / 익절 로직
            loss_cut_take_profit(bot_app, curr_price, my_amt, my_avg)

            time.sleep(1)

        except Exception as e:
            print(f"\n⚠️ 에러 발생: {e}")
            time.sleep(3)


def market_filter(
    bot_app,
    last_market_check: float,
    market_off: bool,
) -> tuple[bool, float]:
    """
    시장 필터: BTC 1h/24h 수익률 기반으로 폭락장 여부 판단.
    반환값:
        (new_market_off, new_last_market_check)
    """
    now_ts = time.time()
    # 아직 체크 주기가 안 됐으면 상태 변경 없음
    if now_ts - last_market_check < config.MARKET_FILTER_CHECK_INTERVAL:
        return market_off, last_market_check

    last_market_check = now_ts

    btc_ret_1h, btc_ret_24h = client.get_btc_1h_24h_returns(config.MARKET_FILTER_TICKER)

    new_market_off = (
        btc_ret_1h <= config.MARKET_1H_DROP_LIMIT
        or btc_ret_24h <= config.MARKET_24H_DROP_LIMIT
    )

    if new_market_off and not market_off:
        print(
            f"\n⛔ [시장 필터 발동] {config.MARKET_FILTER_TICKER} "
            f"1h: {btc_ret_1h:.2f}%, 24h: {btc_ret_24h:.2f}%"
        )
        send_msg(
            bot_app,
            f"⛔ [시장 필터 발동]\n"
            f"{config.MARKET_FILTER_TICKER} 1h: {btc_ret_1h:.2f}% / 24h: {btc_ret_24h:.2f}%\n"
            f"신규 진입을 중단합니다.",
        )
    elif not new_market_off and market_off:
        print(
            f"\n✅ [시장 필터 해제] {config.MARKET_FILTER_TICKER} "
            f"1h: {btc_ret_1h:.2f}%, 24h: {btc_ret_24h:.2f}%"
        )
        send_msg(
            bot_app,
            f"✅ [시장 필터 해제]\n"
            f"{config.MARKET_FILTER_TICKER} 1h: {btc_ret_1h:.2f}% / 24h: {btc_ret_24h:.2f}%\n"
            f"신규 진입을 재개합니다.",
        )

    return new_market_off, last_market_check


def purchase_buy(bot_app, curr_price: float, my_krw: float, my_amt: float = 0.0, df_1h: pd.DataFrame | None = None,):
    """
    전략 선택에 따라 매수 로직을 수행하는 함수.
    """

    mode = config.STRATEGY_MODE.upper()

    # ---------------------------
    # 1) 터틀 트레이딩 V1
    # ---------------------------
    if mode == "TURTLE_V1":
        global last_entry_ts, entry_highest_price
        global turtle_units, turtle_next_add, turtle_entry_atr

        if df_1h is None or df_1h.empty:
            df_1h = client.get_ohlcv(config.TICKER, "1h")

        if df_1h.empty or len(df_1h) < config.TURTLE_ENTRY_PERIOD + 5:
            return

        df_1h['atr'] = calculate_atr(df_1h, config.TURTLE_ATR_PERIOD)
        atr = df_1h['atr'].iloc[-1]
        if atr <= 0 or pd.isna(atr):
            return

        # 20봉 최고가 (현재 캔들 제외)
        entry_high = df_1h['high'].iloc[-(config.TURTLE_ENTRY_PERIOD + 1):-1].max()
        prev_close = df_1h['close'].iloc[-2]

        # 총자산 계산
        total_equity = my_krw + (my_amt * curr_price)

        # ── 신규 진입 (유닛 0인 상태) ──
        if turtle_units == 0:
            # 이번 봉에서 처음 돌파한 경우만 진입
            if not (prev_close <= entry_high < curr_price):
                return

            unit_krw = calc_turtle_unit_size(total_equity, atr, curr_price)
            if unit_krw < 5_000:
                unit_krw = 5_000
            if unit_krw > my_krw:
                return

            client.buy_market(config.TICKER, unit_krw)
            amount = unit_krw / curr_price
            db.log_trade(
                ticker=config.TICKER,
                action="buy",
                price=curr_price,
                amount=amount,
                profit_rate=0.0,
                pnl=0.0,
                mode=config.STRATEGY_MODE,
            )

            # 피라미딩 상태 초기화
            turtle_units = 1
            turtle_entry_atr = atr  # 최초 ATR 고정
            turtle_next_add = curr_price + 0.5 * atr  # 다음 추가 진입 기준가
            entry_highest_price = curr_price
            last_entry_ts = time.time()

            stop_price = curr_price - 2 * atr
            print(
                f"\n🐢 [터틀 1유닛 진입] "
                f"가격: {curr_price:,.0f} | ATR: {atr:,.1f} | "
                f"손절가: {stop_price:,.0f} | 매수금액: {unit_krw:,.0f}원 | "
                f"다음추가: {turtle_next_add:,.0f}"
            )
            send_msg(
                bot_app,
                f"🐢 [터틀 1유닛 진입]\n"
                f"가격: {curr_price:,.0f}원\n"
                f"ATR: {atr:,.1f}\n"
                f"손절가: {stop_price:,.0f}원\n"
                f"매수금액: {unit_krw:,.0f}원\n"
                f"다음 추가진입: {turtle_next_add:,.0f}원",
            )

        # ── 피라미딩 추가 진입 (유닛 1~3인 상태) ──
        elif 0 < turtle_units < config.TURTLE_MAX_UNITS:
            # 다음 추가 기준가 돌파 시 추가 진입
            if curr_price < turtle_next_add:
                return

            # 최초 ATR 기준으로 유닛 사이즈 고정
            unit_krw = calc_turtle_unit_size(total_equity, turtle_entry_atr, curr_price)
            if unit_krw < 5_000:
                unit_krw = 5_000
            if unit_krw > my_krw:
                return

            client.buy_market(config.TICKER, unit_krw)
            amount = unit_krw / curr_price
            db.log_trade(
                ticker=config.TICKER,
                action="buy",
                price=curr_price,
                amount=amount,
                profit_rate=0.0,
                pnl=0.0,
                mode=config.STRATEGY_MODE,
            )

            turtle_units += 1
            turtle_next_add = curr_price + 0.5 * turtle_entry_atr  # 다음 추가 기준가 갱신
            last_entry_ts = time.time()

            stop_price = entry_highest_price - 2 * turtle_entry_atr
            print(
                f"\n🐢 [터틀 {turtle_units}유닛 추가] "
                f"가격: {curr_price:,.0f} | "
                f"매수금액: {unit_krw:,.0f}원 | "
                f"다음추가: {turtle_next_add:,.0f} | "
                f"현재손절가: {stop_price:,.0f}"
            )
            send_msg(
                bot_app,
                f"🐢 [터틀 {turtle_units}유닛 추가]\n"
                f"가격: {curr_price:,.0f}원\n"
                f"매수금액: {unit_krw:,.0f}원\n"
                f"다음 추가진입: {turtle_next_add:,.0f}원\n"
                f"현재 손절가: {stop_price:,.0f}원",
            )
    else:
        print(f"\n⚠️ 알 수 없는 STRATEGY_MODE: {config.STRATEGY_MODE}")
        return

def is_atr_spike(df: pd.DataFrame) -> bool:
    """
    ATR 급등 감지
    - 현재 ATR이 최근 ATR_SPIKE_PERIOD 평균의 ATR_SPIKE_MULTIPLIER배 이상이면 True
    """
    if not config.USE_ATR_FILTER:
        return False

    df = df.copy()
    df['atr'] = calculate_atr(df, config.TURTLE_ATR_PERIOD)

    # 데이터 부족 시 패스
    if len(df) < config.ATR_SPIKE_PERIOD + 1:
        return False

    current_atr = df['atr'].iloc[-1]
    avg_atr     = df['atr'].iloc[-(config.ATR_SPIKE_PERIOD + 1):-1].mean()

    if avg_atr <= 0:
        return False

    ratio = current_atr / avg_atr

    print(
        f"\r[ATR 필터] 현재 ATR: {current_atr:.2f} | "
        f"평균 ATR: {avg_atr:.2f} | "
        f"비율: {ratio:.2f}x (기준: {config.ATR_SPIKE_MULTIPLIER}x)",
        end=""
    )

    return ratio >= config.ATR_SPIKE_MULTIPLIER

def _turtle_exit(bot_app, curr_price, my_amt, my_avg):
    """
    터틀 청산 로직 - 트레일링 스탑 방식
    - 진입 후 최고가를 추적
    - 손절가 = 최고가 - 2 * ATR (최고가 갱신될수록 손절가도 올라감)
    - 손절가 아래로 내려오면 청산
    - 익절 고정선 없음 → 추세가 꺾일 때까지 보유
    """
    global entry_highest_price, turtle_units, turtle_next_add, turtle_entry_atr

    df_1h = client.get_ohlcv(config.TICKER, "1h")
    if df_1h.empty:
        return

    df_1h['atr'] = calculate_atr(df_1h, config.TURTLE_ATR_PERIOD)
    atr = df_1h['atr'].iloc[-1]
    if atr <= 0 or pd.isna(atr):
        return

    # 최고가 갱신
    if curr_price > entry_highest_price:
        entry_highest_price = curr_price

    # 트레일링 손절가 = 최고가 - 2 * ATR
    # → 최고가가 올라갈수록 손절가도 따라 올라감
    # → 손절가는 절대 내려가지 않음
    trailing_stop = entry_highest_price - 2 * atr

    # 진입가 기준 수익률 / 손익 계산
    profit_rate  = (curr_price - my_avg) / my_avg * 100
    realized_pnl = (curr_price - my_avg) * my_amt

    print(
        f"\r[Turtle] 현재가: {curr_price:,.0f} | "
        f"최고가: {entry_highest_price:,.0f} | "
        f"트레일링 손절가: {trailing_stop:,.0f} | "
        f"수익률: {profit_rate:.2f}%",
        end=""
    )

    # ✅ trailing_stop만 체크 (atr_spike는 run_strategy에서 이미 처리)
    if curr_price > trailing_stop:
        return

    exit_type = "익절" if profit_rate > 0 else "손절"
    print(
        f"\n🐢 [{exit_type}] 현재가 {curr_price:,.0f} | "
        f"트레일링 손절가 {trailing_stop:,.0f} | 수익률: {profit_rate:.2f}%"
    )

    client.sell_market(config.TICKER, my_amt)
    db.log_trade(
        ticker=config.TICKER,
        action="sell",
        price=curr_price,
        amount=my_amt,
        profit_rate=profit_rate,
        pnl=realized_pnl,
        mode=config.STRATEGY_MODE,
    )

    send_msg(
        bot_app,
        f"🐢 [터틀 {exit_type}]\n"
        f"현재가: {curr_price:,.0f}원\n"
        f"최고가: {entry_highest_price:,.0f}원\n"
        f"트레일링 손절가: {trailing_stop:,.0f}원\n"
        f"수익률: {profit_rate:.2f}%\n"
        f"실현손익: {int(realized_pnl):,}원"
    )

    # ✅ 전역 변수 초기화 (global 선언 포함)
    entry_highest_price = 0.0
    turtle_units = 0
    turtle_next_add = 0.0
    turtle_entry_atr = 0.0

    time.sleep(10)

def loss_cut_take_profit(bot_app, curr_price, my_amt, my_avg):
    if my_amt <= 0 or my_avg <= 0:
        return

    current_mode = config.STRATEGY_MODE.upper()

    # ✅ 터틀 전략은 별도 청산 로직 사용
    if current_mode == "TURTLE_V1":
        _turtle_exit(bot_app, curr_price, my_amt, my_avg)
        return

    # 3. 익절 로직
    # 보유량이 있을 때만 (my_amt > 0) 손익률 계산
    # profit_rate <= STOP_LOSS_RATE
    # → 손절 실행 (⚠️ 손절 신호 → 시장가 매도)
    # profit_rate >= TARGET_PROFIT_RATE
    # → 익절 실행 (🎉 익절 신호 → 시장가 매도)
    # 손절과 익절은 if ... elif ... 구조라 둘 중 하나만 실행됨

    profit_rate = ((curr_price - my_avg) / my_avg) * 100
    current_mode = config.STRATEGY_MODE

    # 손절
    if profit_rate <= config.STOP_LOSS_RATE:
        print(f"\n⚠️ [손절 신호] 수익률 {profit_rate:.2f}% (기준: {config.STOP_LOSS_RATE}%)")

        client.sell_market(config.TICKER, my_amt)
        realized_pnl = (curr_price - my_avg) * my_amt

        db.log_trade(
            ticker=config.TICKER,
            action="sell",
            price=curr_price,
            amount=my_amt,
            profit_rate=profit_rate,
            pnl=realized_pnl,
            mode=current_mode,
        )

        msg = (
            f"⚠️ [손절 실행]\n"
            f"수익률: {profit_rate:.2f}%\n"
            f"실현손익: {int(realized_pnl):,}원"
        )
        send_msg(bot_app, msg)

        time.sleep(10)
        return

    # 익절
    if profit_rate >= config.TARGET_PROFIT_RATE:
        print(f"\n💰 [익절 신호] 수익률 {profit_rate:.2f}% (기준: {config.TARGET_PROFIT_RATE}%)")

        client.sell_market(config.TICKER, my_amt)
        realized_pnl = (curr_price - my_avg) * my_amt

        db.log_trade(
            ticker=config.TICKER,
            action="sell",
            price=curr_price,
            amount=my_amt,
            profit_rate=profit_rate,
            pnl=realized_pnl,
            mode=current_mode,
        )

        msg = (
            f"🎉 [익절 완료]\n"
            f"수익률: +{profit_rate:.2f}%\n"
            f"실현손익: {int(realized_pnl):,}원"
        )
        send_msg(bot_app, msg)

        time.sleep(10)
        return
