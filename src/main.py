import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# 우리가 만든 모듈들 임포트
import config
import database as db
import upbit_client as client
import strategy


# --------------------------
# 텔레그램 핸들러 함수들
# --------------------------
#region 시작
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 봇이 정상 작동 중입니다! /profit 명령어를 사용해보세요.")
#endregion

#region 현재가 정보
async def profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """수익률 조회 (/profit)"""
    avg, amt = client.get_balance(config.TICKER)
    curr = client.get_current_price(config.TICKER)
    krw = client.get_krw_balance()  # <--- [추가됨] 원화 잔고 조회

    # 에러 방어 코드
    if curr == 0:
        await update.message.reply_text("⛔ 현재가 정보를 불러오지 못했습니다.")
        return

    # 수익률 계산 (보유량이 없어도 원화 잔고는 보여주도록 수정)
    if amt == 0:
        msg = (
            f"📊 *{config.TICKER} 현황*\n"
            f"보유 코인 없음\n"
            f"💰 보유 원화: {krw:,.0f} 원"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
        return

    rate = ((curr - avg) / avg) * 100
    profit = (curr - avg) * amt

    msg = (
        f"📊 *{config.TICKER} 현황*\n"
        f"평단: {avg:,.0f}원\n"
        f"현재: {curr:,.0f}원\n"
        f"수익: {rate:.2f}% ({profit:+,.0f}원)\n"
        f"────────────────\n"
        f"💰 보유 원화: {krw:,.0f} 원"  # <--- 여기에 추가됨
    )
    await update.message.reply_text(msg, parse_mode='Markdown')
#endregion

#region 리포트
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = db.generate_daily_report()  # 오늘자
    msg = (
        f"📊 {report['date']} 데일리 리포트\n"
        f"총 트레이드: {report['total_trades']}건\n"
        f"승률: {report['win_rate']:.1f}%\n"
        f"총 손익: {report['total_pnl']:+,.0f}원\n"
    )
    await update.message.reply_text(msg)
#endregion

#region 메인 실행부
if __name__ == "__main__":
    # 1. DB 초기화
    db.init_db()
    print("✅ 데이터베이스 연결 완료")

    # 2. 텔레그램 봇 빌드
    # 토큰 에러 방지를 위해 config에서 확실히 가져옵니다.
    if not config.TELEGRAM_BOT_TOKEN:
        print("❌ 오류: .env 파일에서 TELEGRAM_BOT_TOKEN을 찾지 못했습니다.")
        exit()

    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # 핸들러 정의 (start/profit)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profit", profit))
    application.add_handler(CommandHandler("report", report))

    # 3. 전략 루프를 별도 쓰레드로 실행
    trade_thread = threading.Thread(
        target=strategy.run_strategy,
        args=(application,),
        daemon=True
    )
    trade_thread.start()

    # 4. 텔레그램 봇 폴링 시작
    print("✅ 봇 서비스 시작... (텔레그램에서 /start 또는 /profit 입력)")
    application.run_polling()
#endregion