"""
统计模块：小题/大作文提交次数按天统计，支持按 IP 去重用户数。

存储策略（优先级从高到低）：
1. 若设置了环境变量 STATS_DB_PATH，用该路径的 SQLite 文件（适合 Render 持久磁盘）
2. 否则用内存字典 + 旁写 JSON 文件（Render 免费套餐临时文件系统）
   - 服务重启后数据会丢失，但单次运行期间统计准确
"""

import json
import os
import sqlite3
import threading
from datetime import date, datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

# ── 环境变量配置 ────────────────────────────────────────────────────────────────
_SQLITE_PATH = (os.getenv("STATS_DB_PATH") or "").strip()
_JSON_FALLBACK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "submit_stats.json")

_lock = threading.Lock()

# ── 内存缓存（当无法持久化时兜底）────────────────────────────────────────────────
_mem_stats: Dict[str, Dict[str, Any]] = {}   # { "2026-02-25": {"small":1,"essay":2,"ips":["..."]}}


def _now_date() -> str:
    """返回当前北京时间的日期字符串 YYYY-MM-DD"""
    tz_cn = timezone(timedelta(hours=8))
    return datetime.now(tz=tz_cn).strftime("%Y-%m-%d")


# ── SQLite 后端 ────────────────────────────────────────────────────────────────
def _sqlite_init():
    conn = sqlite3.connect(_SQLITE_PATH, timeout=10.0)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submit_records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            submit_time TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', '+8 hours')),
            is_essay    INTEGER NOT NULL,
            client_ip   TEXT
        )
    """)
    conn.commit()
    conn.close()
    print(f"[统计] 使用 SQLite 持久化: {_SQLITE_PATH}")


def _sqlite_record(is_essay: bool, client_ip: Optional[str]):
    conn = sqlite3.connect(_SQLITE_PATH, timeout=10.0)
    conn.execute(
        "INSERT INTO submit_records (is_essay, client_ip) VALUES (?, ?)",
        (1 if is_essay else 0, client_ip),
    )
    conn.commit()
    conn.close()


def _sqlite_get_stats() -> Dict[str, Any]:
    conn = sqlite3.connect(_SQLITE_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT
            substr(submit_time, 1, 10) AS date,
            SUM(CASE WHEN is_essay = 0 THEN 1 ELSE 0 END) AS small,
            SUM(CASE WHEN is_essay = 1 THEN 1 ELSE 0 END) AS essay,
            COUNT(DISTINCT client_ip) AS users
        FROM submit_records
        GROUP BY substr(submit_time, 1, 10)
        ORDER BY date DESC
    """).fetchall()
    conn.close()

    total_small = total_essay = 0
    by_date = []
    for r in rows:
        s, e = r["small"] or 0, r["essay"] or 0
        total_small += s
        total_essay += e
        by_date.append({"date": r["date"], "users": r["users"] or 0, "small": s, "essay": e})

    return {"by_date": by_date, "total_small": total_small, "total_essay": total_essay}


# ── JSON/内存 后端 ──────────────────────────────────────────────────────────────
def _mem_load():
    """尝试从 JSON 文件加载历史数据到内存缓存"""
    global _mem_stats
    if not os.path.isfile(_JSON_FALLBACK_PATH):
        return
    try:
        with open(_JSON_FALLBACK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        by_date = data.get("by_date") or {}
        if isinstance(by_date, dict):
            _mem_stats = by_date
            print(f"[统计] 从 JSON 加载历史数据，共 {len(_mem_stats)} 天")
    except Exception as e:
        print(f"[统计] 加载历史数据失败（忽略）: {e}")


def _mem_save():
    """将内存缓存写回 JSON 文件（忽略失败）"""
    try:
        with open(_JSON_FALLBACK_PATH, "w", encoding="utf-8") as f:
            json.dump({"by_date": _mem_stats}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[统计] 写入 JSON 失败（忽略）: {e}")


def _mem_record(is_essay: bool, client_ip: Optional[str]):
    global _mem_stats
    today = _now_date()
    day = _mem_stats.setdefault(today, {"small": 0, "essay": 0, "ips": []})
    if is_essay:
        day["essay"] = day.get("essay", 0) + 1
    else:
        day["small"] = day.get("small", 0) + 1
    if client_ip:
        ips = day.setdefault("ips", [])
        if client_ip not in ips:
            ips.append(client_ip)
    _mem_save()


def _mem_get_stats() -> Dict[str, Any]:
    total_small = total_essay = 0
    by_date: List[Dict[str, Any]] = []
    for d in sorted(_mem_stats.keys(), reverse=True):
        day = _mem_stats[d]
        if not isinstance(day, dict):
            continue
        s = int(day.get("small", 0))
        e = int(day.get("essay", 0))
        ips = day.get("ips") or []
        total_small += s
        total_essay += e
        by_date.append({"date": d, "users": len(ips) if isinstance(ips, list) else 0, "small": s, "essay": e})
    return {"by_date": by_date, "total_small": total_small, "total_essay": total_essay}


# ── 公开接口 ────────────────────────────────────────────────────────────────────
def record_submit(is_essay: bool, client_ip: Optional[str] = None):
    with _lock:
        try:
            if _SQLITE_PATH:
                _sqlite_record(is_essay, client_ip)
            else:
                _mem_record(is_essay, client_ip)
            print(f"[统计] 记录提交: {'大作文' if is_essay else '小题'}, IP={client_ip}, 日期={_now_date()}")
        except Exception as e:
            print(f"[统计] 记录失败: {e}")


def get_stats() -> Dict[str, Any]:
    with _lock:
        try:
            if _SQLITE_PATH:
                return _sqlite_get_stats()
            else:
                return _mem_get_stats()
        except Exception as e:
            print(f"[统计] 获取失败: {e}")
            return {"by_date": [], "total_small": 0, "total_essay": 0}


# ── 模块初始化 ──────────────────────────────────────────────────────────────────
if _SQLITE_PATH:
    try:
        _sqlite_init()
    except Exception as e:
        print(f"[统计] SQLite 初始化失败，回退到内存模式: {e}")
        _SQLITE_PATH = ""
        _mem_load()
else:
    print(f"[统计] 未设置 STATS_DB_PATH，使用内存+JSON 模式（{_JSON_FALLBACK_PATH}）")
    _mem_load()
