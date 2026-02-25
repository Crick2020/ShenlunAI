import sqlite3
import os
from typing import List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats.db")

def _get_conn():
    # SQLite 默认支持并发读，但写操作需要锁。
    # 设置 timeout 可以避免一些被锁住的异常，默认 5 秒。
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submit_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submit_time TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            is_essay INTEGER,
            client_ip TEXT
        )
    ''')
    conn.commit()
    conn.close()

def record_submit(is_essay: bool, client_ip: str = None):
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO submit_records (is_essay, client_ip)
            VALUES (?, ?)
        ''', (1 if is_essay else 0, client_ip))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[统计] 数据库写入失败: {e}")

def get_stats() -> Dict[str, Any]:
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        
        # 获取按天统计数据
        cursor.execute('''
            SELECT 
                DATE(submit_time) as date,
                SUM(CASE WHEN is_essay = 0 THEN 1 ELSE 0 END) as small,
                SUM(CASE WHEN is_essay = 1 THEN 1 ELSE 0 END) as essay,
                COUNT(DISTINCT client_ip) as users
            FROM submit_records
            GROUP BY DATE(submit_time)
            ORDER BY date DESC
        ''')
        
        rows = cursor.fetchall()
        by_date_list = []
        total_small = 0
        total_essay = 0
        
        for row in rows:
            d = row['date']
            small = row['small'] or 0
            essay = row['essay'] or 0
            users = row['users'] or 0
            
            total_small += small
            total_essay += essay
            
            by_date_list.append({
                "date": d,
                "users": users,
                "small": small,
                "essay": essay,
            })
            
        conn.close()
        
        return {
            "by_date": by_date_list,
            "total_small": total_small,
            "total_essay": total_essay,
        }
    except Exception as e:
        print(f"[统计] 获取数据失败: {e}")
        return {"by_date": [], "total_small": 0, "total_essay": 0}

# 模块加载时初始化数据库
init_db()
