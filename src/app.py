from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
import sys
from datetime import datetime

# 기존 백테스트 모듈 임포트를 위한 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

app = FastAPI(
    title="Trading Backtest API",
    version="1.0.0",
    description="암호화폐 터틀 트레이딩 백테스트 API 서버",
    docs_url="/api/docs",  # API 문서 경로
    redoc_url="/api/redoc"
)

# CORS 설정 - 모든 오리진 허용 (개발용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 요청/응답 모델
class BacktestConfig(BaseModel):
    # 기본 설정
    ticker: str = "XRP/KRW"
    timeframe: str = "1h"
    initial_capital: float = 3000000.0

    # 터틀 전략 설정
    turtle_entry_period: int = 20
    turtle_atr_period: int = 20
    turtle_risk_rate: float = 1.0
    turtle_max_units: int = 4
    turtle_trailing_multiplier: float = 2.0

    # 백테스트 기간
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    # 옵션
    print_all_trades: bool = False
    print_monthly: bool = True
    print_crash: bool = False


class BacktestResult(BaseModel):
    success: bool
    execution_time: float
    message: str
    chart_data: dict = {}
    metrics: dict = {}
    trades: list = []
    logs: list = []


# 헬스체크 엔드포인트
@app.get("/health")
async def health_check():
    """컨테이너 헬스체크용 엔드포인트"""
    return {
        "status": "healthy",
        "service": "trading-api",
        "timestamp": datetime.now().isoformat(),
        "port": 10002
    }


# API 정보
@app.get("/")
@app.get("/api")
async def api_info():
    """API 기본 정보"""
    return {
        "name": "Trading Backtest API",
        "version": "1.0.0",
        "description": "암호화폐 터틀 트레이딩 백테스트 API",
        "endpoints": {
            "health": "/health",
            "docs": "/api/docs",
            "default_config": "/api/default-config",
            "tickers": "/api/available-tickers",
            "backtest": "/api/backtest"
        },
        "port": 10002
    }


# 기본 설정 조회
@app.get("/api/default-config")
async def get_default_config():
    """백테스트 기본 설정값 반환"""
    return {
        "ticker": "XRP/KRW",
        "timeframe": "1h",
        "initial_capital": 3000000.0,
        "turtle_entry_period": 20,
        "turtle_atr_period": 20,
        "turtle_risk_rate": 1.0,
        "turtle_max_units": 4,
        "turtle_trailing_multiplier": 2.0,
        "start_date": None,
        "end_date": None,
        "print_monthly": True,
        "print_all_trades": False,
        "print_crash": False
    }


# 사용가능한 거래종목 조회
@app.get("/api/available-tickers")
async def get_tickers():
    """사용 가능한 거래 종목 목록"""
    try:
        # TODO: 실제 zillion/data 폴더에서 파일 목록 읽어오기
        tickers = ["XRP/KRW", "BTC/KRW", "ETH/KRW", "ADA/KRW", "DOT/KRW"]
        return {"tickers": tickers}
    except Exception as e:
        return {"tickers": ["XRP/KRW"]}  # 기본값


# 백테스트 실행
@app.post("/api/backtest", response_model=BacktestResult)
async def run_backtest(config: BacktestConfig):
    """백테스트 실행 및 결과 반환"""
    try:
        # TODO: 실제 백테스트 실행 로직 구현
        # 임시 응답 데이터
        result = BacktestResult(
            success=True,
            execution_time=15.43,
            message="백테스트가 성공적으로 실행되었습니다 (임시 응답)",
            chart_data={
                "dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "equity_curve": [3000000, 3015000, 3021000],
                "monthly_labels": ["2024-01"],
                "monthly_returns": [2.5]
            },
            metrics={
                "총수익률": 15.2,
                "연환산수익률": 18.5,
                "최대낙폭": -8.3,
                "샤프비율": 1.42,
                "승률": 68.5,
                "총거래횟수": 45
            },
            trades=[
                {
                    "date": "2024-01-01",
                    "action": "buy",
                    "price": 1000,
                    "amount": 100,
                    "profit_rate": 2.5,
                    "pnl": 25000
                }
            ],
            logs=[
                f"백테스트 설정: {config.ticker} {config.timeframe}",
                f"초기 자본: {config.initial_capital:,.0f}원",
                "백테스트 시작...",
                "백테스트 완료"
            ]
        )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"백테스트 실행 중 오류가 발생했습니다: {str(e)}"
        )


# 시스템 정보
@app.get("/api/system-info")
async def get_system_info():
    """시스템 정보 조회"""
    try:
        import platform
        return {
            "python_version": platform.python_version(),
            "system": platform.system(),
            "environment": os.getenv("ENVIRONMENT", "development"),
            "zillion_path_exists": os.path.exists("/app/zillion"),
            "data_path_exists": os.path.exists("/app/data")
        }
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=False
    )