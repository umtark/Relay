#!/usr/bin/env python3
"""
Relay Memory System
===================
Kalıcı hafıza + sohbet geçmişi + görev takibi.
SQLite tabanlı, her sohbet arası bilgi taşır.
"""

import os
import json
import time
import sqlite3
import threading
from datetime import datetime

_DB_LOCK = threading.Lock()

# ══════════════════════════════════════════════════════════
# VERİTABANI
# ══════════════════════════════════════════════════════════

def _get_db_path():
    """DB dosyası proxy'nin yanında durur."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "relay_memory.db")


def _get_conn():
    """Thread-safe bağlantı."""
    conn = sqlite3.connect(_get_db_path(), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Tabloları oluştur (yoksa)."""
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.executescript("""
                -- Kalıcı notlar / kullanıcı tercihleri / öğrenilen bilgiler
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL DEFAULT 'general',
                    content TEXT NOT NULL,
                    tags TEXT DEFAULT '',
                    importance INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    updated_at TEXT DEFAULT (datetime('now','localtime'))
                );

                -- Sohbet özetleri — her sohbet kapanınca özet kaydedilir
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary TEXT NOT NULL,
                    topics TEXT DEFAULT '',
                    files_touched TEXT DEFAULT '',
                    decisions TEXT DEFAULT '',
                    message_count INTEGER DEFAULT 0,
                    started_at TEXT DEFAULT (datetime('now','localtime')),
                    ended_at TEXT DEFAULT (datetime('now','localtime'))
                );

                -- Görev takibi — aktif session için
                CREATE TABLE IF NOT EXISTS todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    status TEXT DEFAULT 'not-started',
                    session_id TEXT,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    completed_at TEXT
                );

                -- FTS (Full Text Search) — hafızada hızlı arama
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    content, tags, category,
                    content='memories',
                    content_rowid='id'
                );

                -- FTS trigger'ları
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, content, tags, category)
                    VALUES (new.id, new.content, new.tags, new.category);
                END;

                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, tags, category)
                    VALUES ('delete', old.id, old.content, old.tags, old.category);
                    INSERT INTO memories_fts(rowid, content, tags, category)
                    VALUES (new.id, new.content, new.tags, new.category);
                END;

                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, tags, category)
                    VALUES ('delete', old.id, old.content, old.tags, old.category);
                END;
            """)
            conn.commit()
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════
# HAFIZA İŞLEMLERİ
# ══════════════════════════════════════════════════════════

def memory_save(content: str, category: str = "general", tags: str = "", importance: int = 1) -> str:
    """Yeni hafıza kaydı oluştur."""
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO memories (content, category, tags, importance) VALUES (?, ?, ?, ?)",
                (content, category, tags, importance)
            )
            conn.commit()
            mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return f"✅ Hafıza kaydedildi (#{mid}, kategori: {category})"
        finally:
            conn.close()


def memory_search(query: str, limit: int = 10) -> str:
    """Hafızada arama yap (FTS + LIKE fallback)."""
    with _DB_LOCK:
        conn = _get_conn()
        try:
            # Önce FTS dene
            try:
                rows = conn.execute(
                    """SELECT m.id, m.category, m.content, m.tags, m.importance, m.created_at
                       FROM memories_fts fts
                       JOIN memories m ON m.id = fts.rowid
                       WHERE memories_fts MATCH ?
                       ORDER BY m.importance DESC, m.created_at DESC
                       LIMIT ?""",
                    (query, limit)
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []

            # FTS sonuç yoksa LIKE ile dene
            if not rows:
                rows = conn.execute(
                    """SELECT id, category, content, tags, importance, created_at
                       FROM memories
                       WHERE content LIKE ? OR tags LIKE ? OR category LIKE ?
                       ORDER BY importance DESC, created_at DESC
                       LIMIT ?""",
                    (f"%{query}%", f"%{query}%", f"%{query}%", limit)
                ).fetchall()

            if not rows:
                return "Hafızada eşleşen kayıt bulunamadı."

            lines = []
            for r in rows:
                lines.append(f"[#{r['id']}] ({r['category']}) {r['content']} [önem:{r['importance']}, {r['created_at']}]")
            return "\n".join(lines)
        finally:
            conn.close()


def memory_list(category: str = None, limit: int = 20) -> str:
    """Hafıza kayıtlarını listele."""
    with _DB_LOCK:
        conn = _get_conn()
        try:
            if category:
                rows = conn.execute(
                    "SELECT id, category, content, tags, importance, created_at FROM memories WHERE category = ? ORDER BY created_at DESC LIMIT ?",
                    (category, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, category, content, tags, importance, created_at FROM memories ORDER BY importance DESC, created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()

            if not rows:
                return "Hafızada kayıt yok."

            lines = []
            for r in rows:
                tags = f" [{r['tags']}]" if r['tags'] else ""
                lines.append(f"#{r['id']} ({r['category']}) {r['content']}{tags} [önem:{r['importance']}]")
            return f"Toplam {len(lines)} kayıt:\n" + "\n".join(lines)
        finally:
            conn.close()


def memory_delete(memory_id: int) -> str:
    """Hafıza kaydını sil."""
    with _DB_LOCK:
        conn = _get_conn()
        try:
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            if cursor.rowcount > 0:
                return f"✅ Hafıza #{memory_id} silindi."
            return f"⚠️ Hafıza #{memory_id} bulunamadı."
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════
# SOHBET GEÇMİŞİ
# ══════════════════════════════════════════════════════════

def save_conversation_summary(summary: str, topics: str = "", files_touched: str = "",
                               decisions: str = "", message_count: int = 0) -> str:
    """Sohbet özetini kaydet."""
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO conversation_history 
                   (summary, topics, files_touched, decisions, message_count) 
                   VALUES (?, ?, ?, ?, ?)""",
                (summary, topics, files_touched, decisions, message_count)
            )
            conn.commit()
            return "✅ Sohbet özeti kaydedildi."
        finally:
            conn.close()


def get_recent_conversations(limit: int = 5) -> str:
    """Son N sohbet özetini getir."""
    with _DB_LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT id, summary, topics, files_touched, decisions, message_count, started_at
                   FROM conversation_history
                   ORDER BY started_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()

            if not rows:
                return ""

            lines = []
            for r in rows:
                topics = f" | Konular: {r['topics']}" if r['topics'] else ""
                lines.append(f"[{r['started_at']}] {r['summary']}{topics}")
            return "\n".join(lines)
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════
# GÖREV TAKİBİ (TODO)
# ══════════════════════════════════════════════════════════

_current_session_id = None

def get_session_id():
    global _current_session_id
    if _current_session_id is None:
        _current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _current_session_id


def todo_add(title: str) -> str:
    """Yeni görev ekle."""
    sid = get_session_id()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO todos (title, status, session_id) VALUES (?, 'not-started', ?)",
                (title, sid)
            )
            conn.commit()
            tid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return f"✅ Görev #{tid} eklendi: {title}"
        finally:
            conn.close()


def todo_update(todo_id: int, status: str) -> str:
    """Görev durumunu güncelle (not-started, in-progress, completed)."""
    valid = {'not-started', 'in-progress', 'completed'}
    if status not in valid:
        return f"⚠️ Geçersiz durum: {status}. Geçerli: {', '.join(valid)}"
    with _DB_LOCK:
        conn = _get_conn()
        try:
            completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status == "completed" else None
            cursor = conn.execute(
                "UPDATE todos SET status = ?, completed_at = ? WHERE id = ?",
                (status, completed_at, todo_id)
            )
            conn.commit()
            if cursor.rowcount > 0:
                icon = {"not-started": "⬜", "in-progress": "🔄", "completed": "✅"}[status]
                return f"{icon} Görev #{todo_id} → {status}"
            return f"⚠️ Görev #{todo_id} bulunamadı."
        finally:
            conn.close()


def todo_list(show_all: bool = False) -> str:
    """Aktif görevleri listele."""
    sid = get_session_id()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            if show_all:
                rows = conn.execute(
                    "SELECT id, title, status, created_at, completed_at FROM todos ORDER BY id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, title, status, created_at, completed_at FROM todos WHERE session_id = ? ORDER BY id",
                    (sid,)
                ).fetchall()

            if not rows:
                return "Aktif görev yok."

            icons = {"not-started": "⬜", "in-progress": "🔄", "completed": "✅"}
            lines = []
            for r in rows:
                icon = icons.get(r['status'], "❓")
                lines.append(f"{icon} #{r['id']} {r['title']}")
            return "\n".join(lines)
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════
# BAĞLAM YÜKLEYİCİ — Sohbet başında enjekte edilir
# ══════════════════════════════════════════════════════════

def load_context_for_prompt() -> str:
    """Sohbet başında system prompt'a enjekte edilecek bağlam."""
    parts = []

    # 1. Önemli hafıza notları (importance >= 2)
    with _DB_LOCK:
        conn = _get_conn()
        try:
            important = conn.execute(
                "SELECT content, category FROM memories WHERE importance >= 2 ORDER BY importance DESC, created_at DESC LIMIT 15"
            ).fetchall()
            if important:
                mem_lines = [f"- ({r['category']}) {r['content']}" for r in important]
                parts.append("🧠 HAFIZA (önceki sohbetlerden öğrendiklerin):\n" + "\n".join(mem_lines))

            # 2. Son sohbet özetleri
            recent = conn.execute(
                "SELECT summary, topics FROM conversation_history ORDER BY started_at DESC LIMIT 3"
            ).fetchall()
            if recent:
                conv_lines = [f"- {r['summary']}" for r in recent]
                parts.append("📋 SON SOHBETLER:\n" + "\n".join(conv_lines))

            # 3. Aktif görevler
            sid = get_session_id()
            active_todos = conn.execute(
                "SELECT id, title, status FROM todos WHERE session_id = ? AND status != 'completed' ORDER BY id",
                (sid,)
            ).fetchall()
            if active_todos:
                icons = {"not-started": "⬜", "in-progress": "🔄"}
                todo_lines = [f"{icons.get(r['status'], '❓')} #{r['id']} {r['title']}" for r in active_todos]
                parts.append("📌 AKTİF GÖREVLER:\n" + "\n".join(todo_lines))
        finally:
            conn.close()

    return "\n\n".join(parts) if parts else ""


# Modül yüklenince DB'yi hazırla
init_db()
