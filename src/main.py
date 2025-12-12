import threading
from telegram import Update
from telegram.ext import (
    CallbackContext,
)
from telegram.ext import ApplicationBuilder, CommandHandler

# 모듈들 임포트
import config
import database as db
import upbit_client as client
import strategy
import database as db

# --------------------------
# 텔레그램 핸들러 함수들
# --------------------------
#region 시작
async def start(update: Update, _context: CallbackContext):
    await update.message.reply_text("🤖 삐리삐리 돈 많이벌자 삐리삐리 /profit /report /chat 명령어를 쓸수있어 삐리삐리 ")
#endregion

#region 소개
async def chat(update: Update, _context: CallbackContext):
    await update.message.reply_text("🤖 삐리삐리 나는 돈버는 로보트야 지우야 💰💰💰")
#endregion

#region 현재가 정보
async def profit(update: Update, _context: CallbackContext):
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
            f"보유 코인이 없다.. 삐리삐리\n"
            f"💰 보유 원화: {krw:,.0f} 원"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
        return

    rate = ((curr - avg) / avg) * 100
    profit_late = (curr - avg) * amt

    msg = (
        f"📊 *{config.TICKER} 현황*\n"
        f"평단: {avg:,.0f}원\n"
        f"현재: {curr:,.0f}원\n"
        f"수익: {rate:.2f}% ({profit_late:+,.0f}원)\n"
        f"────────────────\n"
        f"💰 보유 원화: {krw:,.0f} 원"  # <--- 여기에 추가됨
    )
    await update.message.reply_text(msg, parse_mode='Markdown')
#endregion

#region 리포트
async def report(update: Update, _context: CallbackContext):
    report_db = db.generate_daily_report()  # 오늘자
    msg = (
        f"📊 {report_db['date']} 데일리 리포트\n"
        f"총 트레이드: {report_db['total_trades']}건\n"
        f"승률: {report_db['win_rate']:.1f}%\n"
        f"총 손익: {report_db['total_pnl']:+,.0f}원\n"
    )
    await update.message.reply_text(msg)
#endregion

#region 전략 성과 요약
async def stats(update: Update, _context: CallbackContext):
    """
    전략별 성과 요약 (/stats)
    기본: 오늘 날짜 기준 (localtime)
    """
    # 오늘 하루만 보고 싶으면:
    # today = datetime.date.today().strftime("%Y-%m-%d")
    # rows = db.get_strategy_summary(start_date=today, end_date=today)

    # 지금은 테스트용으로 2025-12-01 ~ 2025-12-12 구간을 사용 (네가 준 예시 그대로)
    rows = db.get_strategy_summary(start_date="2025-12-01", end_date="2025-12-12")

    if not rows:
        await update.message.reply_text("📊 아직 매도(trade close) 기록이 없어서 전략 성과를 집계할 수 없습니다.")
        return

    lines: list[str] = []
    lines.append("📈 *전략별 성과 요약*\n")

    for mode, total_pnl, closed_trades, wins, losses, avg_profit_rate in rows:
        # avg_profit_rate가 None일 수 있으니 방어
        avg_pr = avg_profit_rate if avg_profit_rate is not None else 0.0
        total_pnl_int = int(total_pnl) if total_pnl is not None else 0

        lines.append(
            f"• {mode}\n"
            f"  - PnL: {total_pnl_int:+,}원\n"
            f"  - 트레이드: {closed_trades}회 (승 {wins} / 패 {losses})\n"
            f"  - 평균 수익률: {avg_pr:.2f}%\n"
        )

    msg = "\n".join(lines)
    await update.message.reply_text(msg, parse_mode="Markdown")
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
    application.add_handler(CommandHandler("chat", chat))
    application.add_handler(CommandHandler("stats", stats))

    # 3. 전략 루프를 별도 쓰레드로 실행
    trade_thread = threading.Thread(
        target=strategy.run_strategy,
        args=(application,),
        daemon=True
    )
    trade_thread.start()

    # 4. 텔레그램 봇 폴링 시작
    print("✅ 봇 서비스 시작... (텔레그램에서 /start /profit /report /chat 입력)")
    application.run_polling()
#endregion