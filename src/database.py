# database.py

import os
import sqlite3
import datetime

# 프로젝트 루트 기준으로 trading.db 만들기
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "..", "trading.db")


def init_db():
    """DB 테이블 생성"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT,         -- 실제 체결 시각
            date         TEXT,         -- YYYY-MM-DD (데일리 리포트용)
            ticker       TEXT,
            mode         TEXT,         -- 전략 모드 (예: RSI / BREAKOUT / PULLBACK ...)
            action       TEXT,         -- buy / sell
            price        REAL,         -- 체결 가격
            amount       REAL,         -- 수량
            profit_rate  REAL DEFAULT 0,  -- 수익률(%) - 주로 sell에서 의미 있음
            pnl          REAL DEFAULT 0,  -- 실현 손익 금액(원)
            fee          REAL DEFAULT 0   -- 수수료(있으면 기록)
        )
        """
    )
    conn.commit()
    conn.close()


def log_trade(
    ticker: str,
    action: str,
    price: float,
    amount: float,
    profit_rate: float = 0.0,
    pnl: float = 0.0,
    mode: str | None = None,
    fee: float = 0.0,
):
    """
    매매 기록 저장

    - action: "buy" / "sell"
    - profit_rate, pnl: 보통 sell일 때 값이 의미 있음
    - mode: 어떤 전략에서 나온 트레이드인지 표시 (RSI / BREAKOUT 등)
    """
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()

    now = datetime.datetime.now()
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")

    cursor.execute(
        """
        INSERT INTO trades (
            timestamp, date, ticker, mode, action, price, amount,
            profit_rate, pnl, fee
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, date_str, ticker, mode, action, price, amount, profit_rate, pnl, fee),
    )

    conn.commit()
    conn.close()
    print(
        f"💾 [DB 저장] {ts} | {ticker} | {mode or '-'} | {action} | "
        f"{price:,.0f}원 | {amount}개 | pnl={pnl:+,.0f}"
    )


def get_recent_trades(limit: int = 5):
    """최근 거래 내역 조회"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, timestamp, ticker, mode, action, price, amount, profit_rate, pnl
        FROM trades
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

def generate_daily_report(date_str: str | None = None) -> dict:
    """
    특정 날짜(YYYY-MM-DD)의 데일리 리포트 생성
    - return: 지표들을 담은 dict
    """
    if date_str is None:
        date_str = datetime.date.today().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT timestamp, ticker, mode, action, price, amount, profit_rate, pnl
        FROM trades
        WHERE date = ?
        ORDER BY timestamp ASC
        """,
        (date_str,),
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print(f"📄 [{date_str}] 거래 내역이 없습니다.")
        return {
            "date": date_str,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
        }

    total_trades = len(rows)
    total_pnl = sum(r[7] for r in rows)  # pnl 합계

    wins = sum(1 for r in rows if r[7] > 0)
    losses = sum(1 for r in rows if r[7] < 0)
    win_rate = wins / total_trades * 100 if total_trades > 0 else 0.0

    # 평균 이익/손실
    win_pnls = [r[7] for r in rows if r[7] > 0]
    loss_pnls = [r[7] for r in rows if r[7] < 0]

    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0

    # 간단한 연속 승/패 계산
    max_win_streak = 0
    max_loss_streak = 0
    current_win_streak = 0
    current_loss_streak = 0

    for _, _, _, _, _, _, _, pnl in rows:
        if pnl > 0:
            current_win_streak += 1
            current_loss_streak = 0
        elif pnl < 0:
            current_loss_streak += 1
            current_win_streak = 0
        else:
            current_win_streak = 0
            current_loss_streak = 0

        max_win_streak = max(max_win_streak, current_win_streak)
        max_loss_streak = max(max_loss_streak, current_loss_streak)

    report = {
        "date": date_str,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
    }

    # 콘솔 출력 (예쁘게)
    print("\n========================")
    print(f"📊 Daily Report :: {date_str}")
    print("========================")
    print(f"총 트레이드 수   : {total_trades}")
    print(f"승/패             : {wins}승 / {losses}패 (승률 {win_rate:.1f}%)")
    print(f"총 PnL            : {total_pnl:+,.0f} 원")
    print(f"평균 이익(승리)   : {avg_win:+,.0f} 원")
    print(f"평균 손실(패배)   : {avg_loss:+,.0f} 원")
    print(f"최대 연속 승리    : {max_win_streak} 회")
    print(f"최대 연속 손실    : {max_loss_streak} 회")
    print("========================\n")

    return report

if __name__ == "__main__":
    init_db()
    generate_daily_report()  # 오늘자 리포트 출력

