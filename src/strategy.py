import time
import datetime
import config
import upbit_client as client
import database as db

import requests

# 재진입 쿨다운용 타임스탬프
last_entry_ts: float = 0.0

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


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



def run_strategy(bot_app):
    print(f"🚀 [전략 가동] {config.TICKER} 감시 시작 (목표수익: {config.TARGET_PROFIT_RATE}%)")

    # ✅ [추가] 데일리 기준 정보 초기화
    # 오늘 날짜와 시작 잔고(원화 + 코인 평가액)를 기록

    today = datetime.date.today()
    # 현재 잔고 계산: 원화 + (보유 코인 * 현재가)
    init_avg, init_amt = client.get_balance(config.TICKER)
    init_krw = client.get_krw_balance()
    init_price = client.get_current_price(config.TICKER)
    start_equity = init_krw + init_amt * init_price  # 계좌 추정 총액

    daily_stop = False  # 데일리 TP/SL에 걸려서 오늘 매매 중단 상태인지 여부

    # ✅ [추가] 시장 필터 상태 초기화
    market_off = False          # True면 '폭락장 → 신규 진입 OFF'
    last_market_check = 0.0     # 마지막으로 BTC 상태를 체크한 시각 (epoch sec)

    print(f"📆 데일리 기준 설정 - 날짜: {today}, 시작 잔고: {int(start_equity):,}원")


    while True:
        try:
            # 1. 데이터 조회
            df = client.get_ohlcv(config.TICKER, config.TIMEFRAME)

            # 캔들 데이터 없는 경우 대기
            if df.empty:
                print("\n⚠️ 캔들 데이터 없음, 잠시 대기")
                time.sleep(3)
                continue
            
            df['rsi'] = calculate_rsi(df, config.RSI_PERIOD)
            curr_rsi = df['rsi'].iloc[-1]
            curr_price = df['close'].iloc[-1]

            # 2. 내 잔고 조회 (코인 & 원화)
            my_avg, my_amt = client.get_balance(config.TICKER)
            my_krw = client.get_krw_balance()

            # 3. 데일리 TP/SL 체크 (계좌 기준 수익률)
            print(
                f"\r[Monitoring] Price: {curr_price:,.0f} | RSI: {curr_rsi:.1f} | KRW: {my_krw:,.0f}원 | Amt: {my_amt:.4f}",
                end="")

            # 현재 계좌 총액 = 원화 + (보유 코인 * 현재가)
            current_equity = my_krw + my_amt * curr_price
            now_date = datetime.date.today()    # 날짜가 바뀌었으면 데일리 기준 리셋 (새로운 하루 시작)
            if now_date != today:
                today = now_date
                start_equity = current_equity
                daily_stop = False # 새 날이니까 다시 매매 허용
                print(
                    f"\n📆 새로운 거래일 시작 - 날짜: {today}, 기준 잔고: {int(start_equity):,}원"
                )
                send_msg(bot_app, "새 거래일 시작")

            # 시작 대비 오늘 수익률 (%) 계산
            if start_equity > 0:
                daily_return = (current_equity - start_equity) / start_equity * 100.0
            else:
                daily_return = 0.0

            # 데일리 상태 모니터링 출력 (간략 버전)
            print(
                f"\r[Monitoring] Price: {curr_price:,.0f} | RSI: {curr_rsi:.1f} | "
                f"KRW: {my_krw:,.0f}원 | Amt: {my_amt:.4f} | DailyPnL: {daily_return:.2f}%",
                end=""
            )

            # 이미 데일리 스톱 상태라면, 매수/손절/익절은 더 이상 실행하지 않고 관망만
            if daily_stop:
                # 그래도 기존 포지션이 있으면 손절/익절은 계속 관리
                loss_cut_take_profit(bot_app, curr_price, my_amt, my_avg)
                time.sleep(1)
                continue

            # ✅ 데일리 손실 한도 체크 (SL)
            if daily_return <= config.DAILY_SL_RATE:
                print(
                    f"\n⛔ [데일리 손실 한도 도달] 오늘 수익률 {daily_return:.2f}% "
                    f"(기준: {config.DAILY_SL_RATE}%)"
                )

                # 보유 포지션이 있으면 전량 강제 청산
                if my_amt > 0:
                    client.sell_market(config.TICKER, my_amt)
                    realized_pnl = (curr_price - my_avg) * my_amt
                    #db.log_trade(config.TICKER, "sell", curr_price, my_amt, daily_return)  # 일단 수익률 기록 - 수정
                    db.log_trade(
                        ticker=config.TICKER,
                        action="sell",
                        price=curr_price,
                        amount=my_amt,
                        profit_rate=daily_return,
                        pnl=realized_pnl,
                        mode=config.STRATEGY_MODE,
                    )

                    msg = (
                        f"⛔ [데일리 손실 손절]\n"
                        f"오늘 수익률: {daily_return:.2f}%\n"
                        f"강제 청산 손익: {int(realized_pnl):,}원"
                    )
                    send_msg(bot_app, msg)

                daily_stop = True  # 오늘 매매 종료
                time.sleep(3)
                continue  # 다음 루프로 (매수/손절/익절 실행 안 함)

            # ✅ 데일리 수익 한도 체크 (TP)
            if daily_return >= config.DAILY_TP_RATE:
                print(
                    f"\n✅ [데일리 목표 수익 도달] 오늘 수익률 {daily_return:.2f}% "
                    f"(기준: {config.DAILY_TP_RATE}%)"
                )

                # 보유 포지션이 있으면 여기서 전량 청산해서 수익 잠금
                if my_amt > 0:
                    client.sell_market(config.TICKER, my_amt)
                    realized_pnl = (curr_price - my_avg) * my_amt
                    #db.log_trade(config.TICKER, "sell", curr_price, my_amt, daily_return) - 수정
                    db.log_trade(
                        ticker=config.TICKER,
                        action="sell",
                        price=curr_price,
                        amount=my_amt,
                        profit_rate=daily_return,
                        pnl=realized_pnl,
                        mode=config.STRATEGY_MODE,
                    )

                    msg = (
                        f"✅ [데일리 목표 수익 청산]\n"
                        f"오늘 수익률: {daily_return:.2f}%\n"
                        f"실현손익: {int(realized_pnl):,}원"
                    )
                    send_msg(bot_app, msg)
                else:
                    # 포지션이 없어도 목표 수익 도달했으면 더 이상 매매 안 함
                    msg = (
                        f"✅ [데일리 목표 수익 도달]\n"
                        f"오늘 수익률: {daily_return:.2f}%\n"
                        f"오늘은 여기까지!"
                    )
                    send_msg(bot_app, msg)

                daily_stop = True
                time.sleep(3)
                continue

            if config.USE_MARKET_FILTER:
            # !!마켓 필터!!
                #market_filter(bot_app, last_market_check, market_off)
                market_off, last_market_check = market_filter(bot_app, last_market_check, market_off) #수정
            else:
                # 필터 OFF 상태면 항상 시장 ON 상태로 간주
                market_off = False

            # 재진입 쿨다운 로직
            now_ts = time.time()
            now_local = datetime.datetime.now()

            # 재진입 쿨다운 체크
            global last_entry_ts
            in_cooldown = (now_ts - last_entry_ts) < config.REENTRY_COOLDOWN_SEC

            # 거래 시간대 체크
            in_trade_hours = (
                    config.ENTRY_START_HOUR <= now_local.hour <= config.ENTRY_END_HOUR
            )

            # 4. 매수 로직 (시장 필터: 폭락장일 때 / 재진입 쿨다운때는 신규 진입 금지)
            if (not market_off) and (not in_cooldown) and in_trade_hours:
                purchase_buy(bot_app, curr_price, curr_rsi, my_krw)
            else:
                print("\n[시장 필터] 폭락장 감지로 신규 진입 중단 상태")
                pass

            # 5. 손/익절 로직 : 시장이 폭락장이더라도 기존 포지션은 손절/익절로 계속 관리
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

    else:
        print(f"\n⚠️ 알 수 없는 STRATEGY_MODE: {config.STRATEGY_MODE}")
        return


def loss_cut_take_profit(bot_app, curr_price, my_amt, my_avg):
    if my_amt <= 0 or my_avg <= 0:
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
