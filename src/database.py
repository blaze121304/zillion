# src/database.py
import os
import sqlite3
import datetime

# 프로젝트 루트 기준 DB 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "..", "trading.db")


def init_db():
    """DB 테이블 생성 (없으면 생성)"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT,        -- 실제 체결 시각 (YYYY-MM-DD HH:MM:SS)
            date         TEXT,        -- YYYY-MM-DD (데일리 리포트용)
            ticker       TEXT,
            mode         TEXT,        -- 전략 모드 (RSI / BREAKOUT_5M_V1 / PULLBACK_5M_V1 ...)
            action       TEXT,        -- buy / sell
            price        REAL,        -- 체결 가격
            amount       REAL,        -- 수량
            profit_rate  REAL DEFAULT 0,  -- 수익률(%), 보통 sell에서 의미 있음
            pnl          REAL DEFAULT 0,  -- 실현 손익 (원)
            fee          REAL DEFAULT 0   -- 수수료 (있으면 기록)
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
    - mode: 어떤 전략에서 나온 트레이드인지 표시 (RSI / BREAKOUT_5M_V1 ...)
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
        SELECT id, timestamp, ticker, mode, action,
               price, amount, profit_rate, pnl
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
    특정 날짜(YYYY-MM-DD)의 데일리 리포트 생성 + 전략별 성과 분석
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

    if not rows:
        print(f"📄 [{date_str}] 거래 내역이 없습니다.")
        conn.close()
        return {
            "date": date_str,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "modes": [],
        }

    total_trades = len(rows)
    total_pnl = sum(r[7] for r in rows)

    wins = sum(1 for r in rows if r[7] > 0)
    losses = sum(1 for r in rows if r[7] < 0)
    win_rate = wins / total_trades * 100 if total_trades > 0 else 0.0

    # 전략별 성과 집계
    cursor.execute(
        """
        SELECT
            mode,
            COUNT(*) AS cnt,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losses,
            SUM(pnl) AS total_pnl
        FROM trades
        WHERE date = ?
        GROUP BY mode
        """,
        (date_str,),
    )
    mode_rows = cursor.fetchall()
    conn.close()

    mode_stats = []
    for mode, cnt, w, l, m_pnl in mode_rows:
        if cnt and w is not None and l is not None:
            wr = w / cnt * 100 if cnt > 0 else 0.0
        else:
            wr = 0.0
        mode_stats.append(
            {
                "mode": mode or "-",
                "trades": cnt or 0,
                "wins": w or 0,
                "losses": l or 0,
                "win_rate": wr,
                "total_pnl": m_pnl or 0.0,
            }
        )

    # 콘솔 출력
    print("\n========================")
    print(f"📊 Daily Report :: {date_str}")
    print("========================")
    print(f"총 트레이드 수   : {total_trades}")
    print(f"승/패             : {wins}승 / {losses}패 (승률 {win_rate:.1f}%)")
    print(f"총 PnL            : {total_pnl:+,.0f} 원")
    print("------------------------")
    print("전략별 성과:")
    for ms in mode_stats:
        print(
            f"  - {ms['mode']}: "
            f"{ms['trades']}건, "
            f"{ms['wins']}승/{ms['losses']}패 "
            f"(승률 {ms['win_rate']:.1f}%), "
            f"PnL {ms['total_pnl']:+,.0f}원"
        )
    print("========================\n")

    return {
        "date": date_str,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "modes": mode_stats,
    }


def get_strategy_summary(start_date: str | None = None, end_date: str | None = None):
    """
    전략(mode)별 성과 요약을 반환.
    - start_date, end_date: 'YYYY-MM-DD' 형식 문자열 (둘 다 None이면 전체 기간)
    반환 형식: [(mode, total_pnl, closed_trades, wins, losses, avg_profit_rate), ...]
    """
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()

    sql = """
        SELECT
            mode,
            SUM(CASE WHEN action = 'sell' THEN pnl ELSE 0 END)                AS total_pnl,
            SUM(CASE WHEN action = 'sell' THEN 1 ELSE 0 END)                  AS closed_trades,
            SUM(CASE WHEN action = 'sell' AND pnl > 0 THEN 1 ELSE 0 END)      AS wins,
            SUM(CASE WHEN action = 'sell' AND pnl <= 0 THEN 1 ELSE 0 END)     AS losses,
            AVG(CASE WHEN action = 'sell' THEN profit_rate END)               AS avg_profit_rate
        FROM trades
        WHERE 1=1
    """

    params: list = []

    if start_date:
        sql += " AND date >= ?"
        params.append(start_date)

    if end_date:
        sql += " AND date <= ?"
        params.append(end_date)

    sql += " GROUP BY mode ORDER BY total_pnl DESC"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    return rows


if __name__ == "__main__":
    init_db()
    generate_daily_report()
