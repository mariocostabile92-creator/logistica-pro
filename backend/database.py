"""
database.py
Gestione database PostgreSQL per Logistica Pro MVP
"""

import os
import json
import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL non trovata nel file .env")


pool = SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    dsn=DATABASE_URL
)


def get_conn():
    return pool.getconn()


def release_conn(conn):
    pool.putconn(conn)


def init_db():
    conn = get_conn()

    try:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                recovery_code TEXT NOT NULL,
                token TEXT,
                created_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS routes_history (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                data TEXT NOT NULL,
                depot TEXT NOT NULL,
                deliveries JSONB NOT NULL,
                route JSONB NOT NULL,
                totale_km REAL NOT NULL,
                totale_minuti REAL NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS delivery_reports (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                data TEXT NOT NULL,
                payload JSONB NOT NULL
            )
        """)

        conn.commit()

    finally:
        release_conn(conn)


# =========================
# USERS
# =========================

def get_user_by_email(email: str):
    conn = get_conn()

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT * FROM users
            WHERE email = %s
            LIMIT 1
        """, (email,))

        return cur.fetchone()

    finally:
        release_conn(conn)


def get_user_by_token(token: str):
    conn = get_conn()

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT * FROM users
            WHERE token = %s
            LIMIT 1
        """, (token,))

        return cur.fetchone()

    finally:
        release_conn(conn)


def create_user(user_id: str, email: str, password_hash: str, recovery_code: str, token: str):
    conn = get_conn()

    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO users (
                id, email, password_hash, recovery_code, token, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            email,
            password_hash,
            recovery_code,
            token,
            datetime.now().strftime("%d/%m/%Y %H:%M")
        ))

        conn.commit()

    finally:
        release_conn(conn)


def update_user_token(email: str, token: str):
    conn = get_conn()

    try:
        cur = conn.cursor()

        cur.execute("""
            UPDATE users
            SET token = %s
            WHERE email = %s
        """, (token, email))

        conn.commit()

    finally:
        release_conn(conn)


def update_user_password(email: str, password_hash: str, recovery_code: str, token: str):
    conn = get_conn()

    try:
        cur = conn.cursor()

        cur.execute("""
            UPDATE users
            SET password_hash = %s,
                recovery_code = %s,
                token = %s
            WHERE email = %s
        """, (
            password_hash,
            recovery_code,
            token,
            email
        ))

        conn.commit()

    finally:
        release_conn(conn)


# =========================
# ROUTES HISTORY
# =========================

def save_route_history(user_id: str, depot: str, deliveries: list, result: dict):
    conn = get_conn()

    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO routes_history (
                user_id,
                data,
                depot,
                deliveries,
                route,
                totale_km,
                totale_minuti
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            depot,
            json.dumps(deliveries, ensure_ascii=False),
            json.dumps(result.get("route", []), ensure_ascii=False),
            float(result.get("total_km", 0)),
            float(result.get("total_minutes", 0))
        ))

        conn.commit()

    finally:
        release_conn(conn)


def get_route_history(user_id: str):
    conn = get_conn()

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT *
            FROM routes_history
            WHERE user_id = %s
            ORDER BY id DESC
        """, (user_id,))

        return cur.fetchall()

    finally:
        release_conn(conn)


def delete_route_history(user_id: str):
    conn = get_conn()

    try:
        cur = conn.cursor()

        cur.execute("""
            DELETE FROM routes_history
            WHERE user_id = %s
        """, (user_id,))

        conn.commit()

    finally:
        release_conn(conn)


# =========================
# DELIVERY REPORTS
# =========================

def save_delivery_report(user_id: str, payload: dict):
    conn = get_conn()

    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO delivery_reports (
                user_id,
                data,
                payload
            )
            VALUES (%s, %s, %s)
        """, (
            user_id,
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            json.dumps(payload, ensure_ascii=False)
        ))

        conn.commit()

    finally:
        release_conn(conn)


def get_delivery_reports(user_id: str):
    conn = get_conn()

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT *
            FROM delivery_reports
            WHERE user_id = %s
            ORDER BY id DESC
        """, (user_id,))

        return cur.fetchall()

    finally:
        release_conn(conn)


def delete_delivery_reports(user_id: str):
    conn = get_conn()

    try:
        cur = conn.cursor()

        cur.execute("""
            DELETE FROM delivery_reports
            WHERE user_id = %s
        """, (user_id,))

        conn.commit()

    finally:
        release_conn(conn)


# =========================
# ANALYTICS
# =========================

def get_user_analytics(user_id: str):
    reports = get_delivery_reports(user_id)

    totale_report = len(reports)
    totale_consegne = 0

    consegnate = 0
    non_trovate = 0
    problemi = 0
    rimandate = 0

    for saved_report in reports:
        payload = saved_report.get("payload", {})

        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}

        report_items = payload.get("report", [])

        for item in report_items:
            totale_consegne += 1
            status = str(item.get("status", "")).lower()

            if status == "consegnato":
                consegnate += 1
            elif status == "non_trovato":
                non_trovate += 1
            elif status == "problema":
                problemi += 1
            elif status == "rimandato":
                rimandate += 1

    if totale_consegne > 0:
        percentuale_successo = round((consegnate / totale_consegne) * 100, 2)
        percentuale_problemi = round((problemi / totale_consegne) * 100, 2)
        percentuale_non_trovate = round((non_trovate / totale_consegne) * 100, 2)
        percentuale_rimandate = round((rimandate / totale_consegne) * 100, 2)
    else:
        percentuale_successo = 0
        percentuale_problemi = 0
        percentuale_non_trovate = 0
        percentuale_rimandate = 0

    if totale_consegne == 0:
        efficienza = "Nessun dato disponibile"
    elif percentuale_successo >= 90:
        efficienza = "Ottima"
    elif percentuale_successo >= 75:
        efficienza = "Buona"
    elif percentuale_successo >= 60:
        efficienza = "Da migliorare"
    else:
        efficienza = "Critica"

    return {
        "totale_report": totale_report,
        "totale_consegne": totale_consegne,
        "consegnate": consegnate,
        "non_trovate": non_trovate,
        "problemi": problemi,
        "rimandate": rimandate,
        "percentuale_successo": percentuale_successo,
        "percentuale_problemi": percentuale_problemi,
        "percentuale_non_trovate": percentuale_non_trovate,
        "percentuale_rimandate": percentuale_rimandate,
        "efficienza": efficienza
    }