import sqlite3         # SQLite 資料庫模組，用於本地資料儲存

DB_NAME = "places.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    #設定 row_factory 為 sqlite3.Row，讓查詢結果可以用欄位名稱存取（如 row['place_name']）
    #conn.row_factory = sqlite3.Row
    return conn

conn = get_db_connection()
conn.execute("ALTER TABLE favorite_places ADD COLUMN revisit_rating INTEGER DEFAULT 0")
conn.commit()   # 提交交易
conn.close()    # 關閉連線

