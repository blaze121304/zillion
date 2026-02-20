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

def get_turtle_stop_price(entry_price: float, atr: float) -> float:
    """터틀 손절가 = 진입가 - 2 * ATR"""
    return entry_price - 2 * atr

def calc_turtle_unit_size(total_equity: float, atr: float) -> float:
    """
    터틀 유닛 사이즈 계산
    1유닛 = (총자산 * 리스크율) / (2 * ATR)
    반환값: 매수할 KRW 금액
    """
    if atr <= 0:
        return 0.0
    risk_krw = total_equity * (config.TURTLE_RISK_RATE / 100)
    unit_krw  = risk_krw / (2 * atr) * 1  # ATR 단위가 가격이므로 KRW 환산
    return unit_krw

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

    # 시장 필터 상태 초기화
    market_off = False          # True면 '폭락장 → 신규 진입 OFF'
    last_market_check = 0.0     # 마지막으로 BTC 상태를 체크한 시각 (epoch sec)

    while True:
        try:
            # 1. 캔들 데이터 조회
            df = client.get_ohlcv(config.TICKER, config.TIMEFRAME)
            if df.empty:
                print("\n⚠️ 캔들 데이터 없음, 잠시 대기")
                time.sleep(3)
                continue

            df['rsi'] = calculate_rsi(df, config.RSI_PERIOD)
            curr_rsi = df['rsi'].iloc[-1]
            curr_price = df['close'].iloc[-1]

            # 2. 잔고 조회
            my_avg, my_amt = client.get_balance(config.TICKER)
            my_krw = client.get_krw_balance()

            # 3. 모니터링 출력
            print(
                f"\r[Monitoring] Price: {curr_price:,.0f} | RSI: {curr_rsi:.1f} | "
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
            if not market_off and not in_cooldown and in_trade_hours:
                purchase_buy(bot_app, curr_price, curr_rsi, my_krw)

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


def purchase_buy(bot_app, curr_price: float, curr_rsi: float, my_krw: float):
    """
    전략 선택에 따라 매수 로직을 수행하는 함수.

    STRATEGY_MODE:
      - "RSI"
      - "BREAKOUT_5M_V1"
      - "PULLBACK_5M_V1"
      - "SWING_1H_V1"
      - "BREAKOUT_1M_V2"
    """

    # 원화 잔고 부족하면 진입 X
    if my_krw < config.BUY_AMOUNT_KRW:
        return

    mode = config.STRATEGY_MODE.upper()

    # ---------------------------
    # 공통: 매수 실행 함수
    # ---------------------------
    def _execute_buy():
        global last_entry_ts

        client.buy_market(config.TICKER, config.BUY_AMOUNT_KRW)
        amount = config.BUY_AMOUNT_KRW / curr_price

        # DB 기록 (mode 포함)
        db.log_trade(
            ticker=config.TICKER,
            action="buy",
            price=curr_price,
            amount=amount,
            profit_rate=0.0,
            pnl=0.0,
            mode=config.STRATEGY_MODE,
        )

        last_entry_ts = time.time()  # 재진입 쿨다운용 타임스탬프 갱신

        # 트레일링 스탑용 최고가 초기화
        global entry_highest_price
        entry_highest_price = curr_price

        return amount

    # ---------------------------
    # 1) RSI 30 전략
    # ---------------------------
    if mode == "RSI_V1":
        if curr_rsi < config.RSI_BUY_THRESHOLD:
            print(f"\n🔥 [RSI 매수 신호] RSI {curr_rsi:.1f} (기준: {config.RSI_BUY_THRESHOLD})")

            _execute_buy()

            send_msg(
                bot_app,
                f"📈 [RSI 매수 체결]\n"
                f"전략: RSI\n"
                f"가격: {curr_price:,.0f}원\n"
                f"RSI: {curr_rsi:.1f}\n"
                f"사용금액: {config.BUY_AMOUNT_KRW:,}원",
            )

    # ---------------------------
    # 2) 5분봉 돌파형 V1 (BREAKOUT_5M_V1)
    # ---------------------------
    elif mode == "BREAKOUT_5M_V1":
        df_5m = client.get_ohlcv(config.TICKER, "5m")
        if df_5m.empty or len(df_5m) < 30:
            return

        n = 20
        recent = df_5m.tail(n + 1)  # 마지막 1개는 현재 캔들
        box_high = recent["high"].iloc[:-1].max()
        current_vol = recent["volume"].iloc[-1]
        avg_vol = recent["volume"].iloc[:-1].mean()

        # 거래량 증가 필터
        if avg_vol > 0 and current_vol < avg_vol * config.VOLUME_FILTER_MULTIPLIER:
            return

        if curr_price > box_high:
            print(
                f"\n🚀 [5분봉 돌파 매수 신호] "
                f"현재가 {curr_price:,.0f} > 박스상단 {box_high:,.0f}"
            )

            _execute_buy()

            send_msg(
                bot_app,
                f"📈 [5분봉 돌파 매수 체결]\n"
                f"전략: BREAKOUT_5M_V1\n"
                f"가격: {curr_price:,.0f}원\n"
                f"박스상단: {box_high:,.0f}원\n"
                f"사용금액: {config.BUY_AMOUNT_KRW:,}원",
            )

    # ---------------------------
    # 3) 5분봉 눌림목 진입 V1 (PULLBACK_5M_V1)
    #    - 최근 박스를 위로 돌파한 직후
    #    - 박스 상단 근처로 되돌림이 왔을 때 진입
    # ---------------------------
    elif mode == "PULLBACK_5M_V1":
        df_5m = client.get_ohlcv(config.TICKER, "5m")
        if df_5m.empty or len(df_5m) < 30:
            return

        n = 20
        recent = df_5m.tail(n + 2)  # 마지막 2개: 직전/현재 캔들
        box_high = recent["high"].iloc[:-2].max()

        prev_close = recent["close"].iloc[-2]
        current_close = recent["close"].iloc[-1]

        # 거래량 필터 (여기서는 완전 증가까진 아니고, 평균 이상인지만 체크해도 됨)
        current_vol = recent["volume"].iloc[-1]
        avg_vol = recent["volume"].iloc[:-1].mean()
        if avg_vol > 0 and current_vol < avg_vol:
            return

        # 조건:
        #  1) 이전 캔들이 박스 상단을 돌파 (breakout)
        #  2) 현재 가격이 breakout 가격보다 낮으면서, box_high 근처로 되돌림
        if prev_close > box_high and box_high * 0.99 <= current_close <= prev_close:
            print(
                f"\n📉 [5분봉 눌림목 매수 신호] "
                f"현재가 {current_close:,.0f}, 박스상단 {box_high:,.0f}, 직전종가 {prev_close:,.0f}"
            )

            _execute_buy()

            send_msg(
                bot_app,
                f"📈 [5분봉 눌림목 매수 체결]\n"
                f"전략: PULLBACK_5M_V1\n"
                f"가격: {current_close:,.0f}원\n"
                f"박스상단: {box_high:,.0f}원\n"
                f"직전종가: {prev_close:,.0f}원\n"
                f"사용금액: {config.BUY_AMOUNT_KRW:,}원",
            )

    # ---------------------------
    # 4) 1시간봉 스윙 V1 (SWING_1H_V1)
    #    - EMA20 > EMA50 (상승 추세)
    #    - 현재가가 EMA20 근처로 눌림 왔을 때 진입
    # ---------------------------
    elif mode == "SWING_1H_V1":
        df_1h = client.get_ohlcv(config.TICKER, "1h")
        if df_1h.empty or len(df_1h) < 60:
            return

        df_1h["ema20"] = df_1h["close"].ewm(span=20, adjust=False).mean()
        df_1h["ema50"] = df_1h["close"].ewm(span=50, adjust=False).mean()

        last = df_1h.iloc[-1]
        ema20 = last["ema20"]
        ema50 = last["ema50"]

        # 거래량 필터
        current_vol = df_1h["volume"].iloc[-1]
        avg_vol = df_1h["volume"].iloc[-20:].mean()
        if avg_vol > 0 and current_vol < avg_vol * config.VOLUME_FILTER_MULTIPLIER:
            return

        # 상승 추세 + EMA20 근처 눌림
        if ema20 > ema50 and ema20 * 0.99 <= curr_price <= ema20 * 1.01:
            print(
                f"\n🌊 [1시간봉 스윙 매수 신호] "
                f"현재가 {curr_price:,.0f}, EMA20 {ema20:,.0f}, EMA50 {ema50:,.0f}"
            )

            _execute_buy()

            send_msg(
                bot_app,
                f"📈 [1시간봉 스윙 매수 체결]\n"
                f"전략: SWING_1H_V1\n"
                f"가격: {curr_price:,.0f}원\n"
                f"EMA20: {ema20:,.0f}원 / EMA50: {ema50:,.0f}원\n"
                f"사용금액: {config.BUY_AMOUNT_KRW:,}원",
            )

    # ---------------------------
    # 5) 1분봉 돌파형 V2 (BREAKOUT_1M_V2)
    # ---------------------------
    elif mode == "BREAKOUT_1M_V1":
        df_1m = client.get_ohlcv(config.TICKER, "1m")
        if df_1m.empty or len(df_1m) < 40:
            return

        n = 30
        recent = df_1m.tail(n + 1)
        box_high = recent["high"].iloc[:-1].max()

        current_vol = recent["volume"].iloc[-1]
        avg_vol = recent["volume"].iloc[:-1].mean()
        if avg_vol > 0 and current_vol < avg_vol * config.VOLUME_FILTER_MULTIPLIER:
            return

        if curr_price > box_high:
            print(
                f"\n🚀 [1분봉 돌파 매수 신호] "
                f"현재가 {curr_price:,.0f} > 박스상단 {box_high:,.0f}"
            )

            _execute_buy()

            send_msg(
                bot_app,
                f"📈 [1분봉 돌파 매수 체결]\n"
                f"전략: BREAKOUT_1M_V2\n"
                f"가격: {curr_price:,.0f}원\n"
                f"박스상단: {box_high:,.0f}원\n"
                f"사용금액: {config.BUY_AMOUNT_KRW:,}원",
            )

    # ---------------------------
    # 6) 터틀 트레이딩 V1
    # ---------------------------
    elif mode == "TURTLE_V1":
        df_1h = client.get_ohlcv(config.TICKER, "1h")
        if df_1h.empty or len(df_1h) < config.TURTLE_ENTRY_PERIOD + 5:
            return

        # ATR 계산
        df_1h['atr'] = calculate_atr(df_1h, config.TURTLE_ATR_PERIOD)
        atr = df_1h['atr'].iloc[-1]
        if atr <= 0 or pd.isna(atr):
            return

        # 20봉 최고가 (현재 캔들 제외)
        entry_high = df_1h['high'].iloc[-(config.TURTLE_ENTRY_PERIOD + 1):-1].max()

        # 유닛 사이즈 계산 (총자산 기반)
        total_equity = my_krw + (client.get_balance(config.TICKER)[1] * curr_price)
        unit_krw = calc_turtle_unit_size(total_equity, atr)

        if unit_krw <= 0 or unit_krw > my_krw:
            return

        # 직전 봉 종가 조회
        # → 직전 봉이 20봉 고점 아래에 있었을 때만 진입
        # → 이미 며칠 전에 돌파한 신호는 무시 (고점 물림 방지)
        prev_close = df_1h['close'].iloc[-2]
        if curr_price > entry_high and prev_close <= entry_high:
            stop_price = get_turtle_stop_price(curr_price, atr)

            print(
                f"\n🐢 [터틀 진입 신호] "
                f"현재가 {curr_price:,.0f} > 20봉고점 {entry_high:,.0f} | "
                f"ATR {atr:,.1f} | 손절가 {stop_price:,.0f} | 매수금액 {unit_krw:,.0f}원"
            )

            # 매수 실행
            global last_entry_ts
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
            last_entry_ts = time.time()

            send_msg(
                bot_app,
                f"🐢 [터틀 매수 체결]\n"
                f"가격: {curr_price:,.0f}원\n"
                f"20봉 고점: {entry_high:,.0f}원\n"
                f"ATR: {atr:,.1f}\n"
                f"손절가: {stop_price:,.0f}원\n"
                f"매수금액: {unit_krw:,.0f}원",
            )
    else:
        print(f"\n⚠️ 알 수 없는 STRATEGY_MODE: {config.STRATEGY_MODE}")
        return

def _turtle_exit(bot_app, curr_price, my_amt, my_avg):
    """
    터틀 청산 로직 - 트레일링 스탑 방식
    - 진입 후 최고가를 추적
    - 손절가 = 최고가 - 2 * ATR (최고가 갱신될수록 손절가도 올라감)
    - 손절가 아래로 내려오면 청산
    - 익절 고정선 없음 → 추세가 꺾일 때까지 보유
    """
    global entry_highest_price

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

    # 트레일링 손절가 이하로 하락 시 청산
    if curr_price <= trailing_stop:
        exit_type = "익절" if profit_rate > 0 else "손절"
        print(
            f"\n🐢 [{exit_type}] 현재가 {curr_price:,.0f} <= "
            f"트레일링 손절가 {trailing_stop:,.0f} | "
            f"수익률: {profit_rate:.2f}%"
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

        # 최고가 초기화
        entry_highest_price = 0.0
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
