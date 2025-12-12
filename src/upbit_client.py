import ccxt
import pandas as pd
import config

# 업비트 객체 생성
upbit = ccxt.upbit({
    'apiKey': config.UPBIT_ACCESS_KEY,
    'secret': config.UPBIT_SECRET_KEY,
    'options': {'defaultType': 'spot'}
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
    """시장가 매수 주문"""
    try:
        price = get_current_price(ticker)                       #구매 코인 현재 가격
        qty = krw_amount / price                                #살려는 금액에서 나눔 = 몇개살거?
        return upbit.create_market_buy_order(ticker, qty)       #2개살거                         
        # return upbit.create_market_buy_order(ticker, krw_amount)
    except Exception as e:
        print(f"❌ 매수 주문 실패: {e}")


def sell_market(ticker, amount):
    """시장가 매도 주문"""
    try:
        return upbit.create_market_sell_order(ticker, amount)
    except Exception as e:
        print(f"❌ 매도 주문 실패: {e}")