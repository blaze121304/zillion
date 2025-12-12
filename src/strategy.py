import time
import pandas as pd
import config
import upbit_client as client
import database as db


def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def send_msg(bot_app, text):
    if config.TELEGRAM_CHAT_ID:
        bot_app.loop.create_task(bot_app.bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=text))


def run_strategy(bot_app):
    print(f"🚀 [전략 가동] {config.TICKER} 감시 시작 (목표수익: {config.TARGET_PROFIT_RATE}%)")

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

            # 내 잔고 조회 (코인 & 원화)
            my_avg, my_amt = client.get_balance(config.TICKER)
            my_krw = client.get_krw_balance()  # <--- [추가됨] 원화 잔고 가져오기

            # 모니터링 로그 출력 (KRW 추가됨)
            print(
                f"\r[Monitoring] Price: {curr_price:,.0f} | RSI: {curr_rsi:.1f} | KRW: {my_krw:,.0f}원 | Amt: {my_amt:.4f}",
                end="")

            # 2. 매수 로직
            if curr_rsi < config.RSI_BUY_THRESHOLD:
                # 위에서 조회한 my_krw를 바로 사용
                if my_krw >= config.BUY_AMOUNT_KRW:
                    print(f"\n🔥 [매수 신호] RSI {curr_rsi:.1f}")

                    client.buy_market(config.TICKER, config.BUY_AMOUNT_KRW)

                    # 로그 인입
                    amount = config.BUY_AMOUNT_KRW / curr_price
                    db.log_trade(
                        ticker=config.TICKER,
                        action="buy",
                        price=curr_price,
                        amount=amount,
                        profit_rate=0.0,
                        pnl=0.0,
                        mode="RSI",
                    )

                    # 텔레그램 알림에도 잔액 표시
                    send_msg(bot_app,
                             f"📈 [매수 체결]\n가격: {curr_price:,.0f}원\nRSI: {curr_rsi:.1f}\n남은돈: {int(my_krw - config.BUY_AMOUNT_KRW):,}원")

                    time.sleep(10)
                else:
                    # 잔액 부족하면 로그 한 번만 찍고 넘어가기
                    # (너무 자주 찍히지 않게 RSI 조건 안에서만 체크)
                    # print(f"\n⚠️ 잔액 부족 (보유: {my_krw:,.0f}원 / 필요: {config.BUY_AMOUNT_KRW:,.0f}원)")
                    pass

            # 3. 익절 로직
            if my_amt > 0:
                profit_rate = ((curr_price - my_avg) / my_avg) * 100
                if profit_rate >= config.TARGET_PROFIT_RATE:
                    print(f"\n💰 [익절 신호] 수익률 {profit_rate:.2f}%")

                    client.sell_market(config.TICKER, my_amt)

                    # 로그 인입
                    realized_pnl = (curr_price - my_avg) * my_amt  # 원 단위

                    db.log_trade(
                        ticker=config.TICKER,
                        action="sell",
                        price=curr_price,
                        amount=my_amt,
                        profit_rate=profit_rate,
                        pnl=realized_pnl,
                        mode="RSI",
                    )
                    

                    msg = f"🎉 [익절 완료] 수익률: +{profit_rate:.2f}%\n실현손익: {int((curr_price - my_avg) * my_amt):,}원"
                    send_msg(bot_app, msg)

                    time.sleep(10)

            time.sleep(1)

        except Exception as e:
            print(f"\n⚠️ 에러 발생: {e}")
            time.sleep(3)