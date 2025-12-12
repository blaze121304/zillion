import os
import sqlite3
import datetime

# DB 파일 이름 (프로젝트 폴더에 'trading.db'라는 파일이 생깁니다)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "..", "trading.db")

def init_db():
    """DB 테이블 생성"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS trades
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       timestamp
                       TEXT,
                       ticker
                       TEXT,
                       action
                       TEXT,
                       price
                       REAL,
                       amount
                       REAL,
                       profit_rate
                       REAL
                       DEFAULT
                       0
                   )
                   ''')
    conn.commit()
    conn.close()


def log_trade(ticker, action, price, amount, profit_rate=0):
    """매매 기록 저장"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute('''
                   INSERT INTO trades (timestamp, ticker, action, price, amount, profit_rate)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ''', (now, ticker, action, price, amount, profit_rate))

    conn.commit()
    conn.close()
    print(f"💾 [DB 저장] {action} | {price:,.0f}원 | {amount}개")


def get_recent_trades(limit=5):
    """최근 거래 내역을 조회하는 함수"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM trades ORDER BY id DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()

    conn.close()
    return rows


# 이 파일을 직접 실행하면 DB를 초기화합니다.
if __name__ == "__main__":
    init_db()