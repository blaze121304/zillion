import ccxt
import pandas as pd
import config

# 업비트 객체 생성
upbit = ccxt.upbit({
    'apiKey': config.UPBIT_ACCESS_KEY,
    'secret': config.UPBIT_SECRET_KEY,
    'options': {'defaultType': 'spot',
                'createMarketBuyOrderRequiresPrice': False,
                }
})

def get_balance(ticker):
    """(평단가, 보유수량) 반환"""
    try:
        balances = upbit.fetch_balance()
        #currency = ticker.split('-')[1]  # KRW-BTC -> BTC
        currency = ticker.split('/')[0]  # BTC/KRW -> BTC

        for b in balances['info']:
            if b['currency'] == currency:
                avg_price = float(b['avg_buy_price'])
                amount = float(b['balance'])
                return avg_price, amount
        return 0, 0
    except Exception as e:
        # 잔고 조회 에러는 자주 발생할 수 있으니 로그만 남기고 0 처리
        print(f"❌ 잔고 조회 실패: {e}")
        return 0, 0


def get_krw_balance():
    """원화 잔고 반환"""
    try:
        return upbit.fetch_balance()['total']['KRW']
    except:
        return 0


def get_current_price(ticker):
    """현재가 반환 (에러 발생 시 0 반환)"""
    try:
        ticker_data = upbit.fetch_ticker(ticker)
        # 데이터가 None이거나 비어있으면 0 반환
        if not ticker_data or 'close' not in ticker_data:
            return 0
        return ticker_data['close']
    except Exception as e:
        print(f"⚠️ 현재가 조회 실패: {e}")

        return 0


def get_ohlcv(ticker, interval):
    """캔들 데이터 반환"""
    try:
        ohlcv = upbit.fetch_ohlcv(ticker, timeframe=interval, limit=200)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception as e:
        print(f"⚠️ 캔들 조회 실패: {e}")
        return pd.DataFrame()  # 빈 데이터프레임 반환


def buy_market(ticker, krw_amount):
    """시장가 매수 주문 (KRW 금액 기준으로 매수)"""
    try:
        # 현재가 조회
        price = get_current_price(ticker)
        if price <= 0:
            raise Exception("현재가 조회 실패로 매수 불가")
        # createMarketBuyOrderRequiresPrice = False 이므로
        # amount 자리에 '쓸 KRW 금액'을 넣어주면 됨
        return upbit.create_market_buy_order(ticker, krw_amount)
    except Exception as e:
        print(f"❌ 매수 주문 실패: {e}")


def sell_market(ticker, amount):
    """시장가 매도 주문"""
    try:
        return upbit.create_market_sell_order(ticker, amount)
    except Exception as e:
        print(f"❌ 매도 주문 실패: {e}")


def get_btc_1h_24h_returns(ticker: str):
    """
    지정한 ticker(예: 'BTC/KRW')에 대해
    - 1시간 수익률(%)
    - 24시간 수익률(%)
    을 튜플(float, float)로 반환.

    데이터가 부족하거나 에러가 나면 (0.0, 0.0) 반환.
    """
    try:
        # 1시간봉 기준으로 최근 25개 캔들을 가져온다.
        # - 마지막 캔들: 현재 close
        # - 마지막 바로 전 캔들: 1시간 전 close
        # - 24개 전 캔들: 24시간 전 close 근사
        ohlcv = upbit.fetch_ohlcv(ticker, timeframe="1h", limit=25)
        if not ohlcv or len(ohlcv) < 2:
            return 0.0, 0.0

        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )

        last_close = df["close"].iloc[-1]    # 현재 종가
        prev_1h_close = df["close"].iloc[-2] # 1시간 전 종가

        # 24시간 전 종가: 데이터가 충분하면 맨 앞 캔들 사용
        prev_24h_close = df["close"].iloc[0]

        # 1시간 수익률 (%)
        if prev_1h_close > 0:
            ret_1h = (last_close - prev_1h_close) / prev_1h_close * 100.0
        else:
            ret_1h = 0.0

        # 24시간 수익률 (%)
        if prev_24h_close > 0:
            ret_24h = (last_close - prev_24h_close) / prev_24h_close * 100.0
        else:
            ret_24h = 0.0

        return ret_1h, ret_24h

    except Exception as e:
        print(f"⚠️ BTC 1h/24h 수익률 조회 실패: {e}")
        return 0.0, 0.0