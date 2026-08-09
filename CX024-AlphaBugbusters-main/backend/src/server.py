"""
=============================================================================
 College Lab Infrastructure Monitoring Dashboard — Backend Server
=============================================================================
 ARCHITECTURE:
   Agent script (agent.py) runs on each lab PC
     → HTTP POST every 5 seconds
     → Flask backend (this file) on host laptop port 5000
     → SQLite database (lab_monitor.db)
   Frontend dashboard (templates/index.html) runs in browser
     → HTTP GET → Flask backend → JSON responses
   Backend AND frontend both served from the same Flask server.

 HOW TO INSTALL:
   pip install flask psutil

 HOW TO RUN:
   python server.py

 The server will start on http://0.0.0.0:5000
 Open http://localhost:5000 in your browser to see the dashboard.
=============================================================================
"""

import sqlite3
import os
import threading
import time
import json
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, render_template

# ============================================================================
# APP CONFIGURATION
# ============================================================================
app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lab_monitor.db')

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================
def get_db():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS machines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT UNIQUE NOT NULL,
                hostname TEXT,
                ip_address TEXT,
                mac_address TEXT,
                os_info TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP,
                status TEXT DEFAULT 'online'
            );

            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cpu_percent REAL,
                memory_percent REAL,
                memory_used_gb REAL,
                memory_total_gb REAL,
                disk_percent REAL,
                disk_used_gb REAL,
                disk_free_gb REAL,
                disk_total_gb REAL,
                FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                alert_type TEXT,
                message TEXT,
                severity TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                acknowledged INTEGER DEFAULT 0,
                FOREIGN KEY (machine_id) REFERENCES machines(machine_id)
            );

            CREATE INDEX IF NOT EXISTS idx_metrics_machine_ts
                ON metrics(machine_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_alerts_machine_type
                ON alerts(machine_id, alert_type, acknowledged);
        """)
    conn.close()
    print("[DB] Database initialized — all tables ready.")

def cleanup_old_metrics():
    """Delete metrics older than 7 days."""
    conn = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    with conn:
        cursor = conn.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,))
        deleted = cursor.rowcount
    conn.close()
    if deleted > 0:
        print(f"[DB] Cleaned up {deleted} metric records older than 7 days.")

# ============================================================================
# ALERT HELPER
# ============================================================================
def check_and_create_alert(conn, machine_id, alert_type, severity, message):
    """Create an alert if no unacknowledged duplicate exists in last 60 seconds."""
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).strftime('%Y-%m-%d %H:%M:%S')
    existing = conn.execute(
        """SELECT id FROM alerts
           WHERE machine_id = ? AND alert_type = ? AND acknowledged = 0
             AND timestamp > ?""",
        (machine_id, alert_type, cutoff)
    ).fetchone()

    if not existing:
        conn.execute(
            """INSERT INTO alerts (machine_id, alert_type, message, severity)
               VALUES (?, ?, ?, ?)""",
            (machine_id, alert_type, message, severity)
        )
        print(f"[ALERT] {severity.upper()}: {message}")

# ============================================================================
# API ENDPOINTS
# ============================================================================

# --- Serve Frontend ---
@app.route('/')
def index():
    return render_template('index.html')

# --- POST /api/metrics ---
@app.route('/api/metrics', methods=['POST'])
def receive_metrics():
    """Receive metrics from an agent, upsert machine, insert metric, check alerts."""
    try:
        data = request.get_json()
        if not data or 'machine_id' not in data:
            return jsonify({"status": "error", "message": "machine_id is required"}), 400

        machine_id = data['machine_id']
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        conn = get_db()
        with conn:
            # Upsert machine
            existing = conn.execute(
                "SELECT id FROM machines WHERE machine_id = ?", (machine_id,)
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE machines SET hostname=?, ip_address=?, mac_address=?,
                       os_info=?, last_seen=?, status='online'
                       WHERE machine_id=?""",
                    (data.get('hostname'), data.get('ip_address'),
                     data.get('mac_address'), data.get('os_info'), now, machine_id)
                )
            else:
                conn.execute(
                    """INSERT INTO machines
                       (machine_id, hostname, ip_address, mac_address, os_info, last_seen, status)
                       VALUES (?, ?, ?, ?, ?, ?, 'online')""",
                    (machine_id, data.get('hostname'), data.get('ip_address'),
                     data.get('mac_address'), data.get('os_info'), now)
                )
                print(f"[NEW] Machine registered: {machine_id}")

            # Insert metric
            conn.execute(
                """INSERT INTO metrics
                   (machine_id, cpu_percent, memory_percent, memory_used_gb,
                    memory_total_gb, disk_percent, disk_used_gb, disk_free_gb, disk_total_gb)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (machine_id,
                 data.get('cpu_percent', 0), data.get('memory_percent', 0),
                 data.get('memory_used_gb', 0), data.get('memory_total_gb', 0),
                 data.get('disk_percent', 0), data.get('disk_used_gb', 0),
                 data.get('disk_free_gb', 0), data.get('disk_total_gb', 0))
            )

            # Check alert conditions
            cpu = data.get('cpu_percent', 0)
            disk_free = data.get('disk_free_gb', 999)

            if cpu > 90:
                check_and_create_alert(conn, machine_id, 'high_cpu', 'critical',
                    f"CPU usage at {cpu:.1f}% on {machine_id}")
            elif cpu > 75:
                check_and_create_alert(conn, machine_id, 'high_cpu', 'warning',
                    f"CPU usage at {cpu:.1f}% on {machine_id}")

            if disk_free < 5:
                check_and_create_alert(conn, machine_id, 'low_disk', 'critical',
                    f"Disk space critically low: {disk_free:.1f}GB free on {machine_id}")
            elif disk_free < 10:
                check_and_create_alert(conn, machine_id, 'low_disk', 'warning',
                    f"Disk space low: {disk_free:.1f}GB free on {machine_id}")

        conn.close()
        return jsonify({"status": "ok"})

    except Exception as e:
        print(f"[ERROR] POST /api/metrics: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- GET /api/machines ---
@app.route('/api/machines', methods=['GET'])
def get_machines():
    """Return all machines with their latest metric values."""
    try:
        conn = get_db()
        machines = conn.execute("""
            SELECT m.*,
                   mt.cpu_percent, mt.memory_percent,
                   mt.disk_percent, mt.disk_free_gb
            FROM machines m
            LEFT JOIN (
                SELECT machine_id, cpu_percent, memory_percent,
                       disk_percent, disk_free_gb,
                       ROW_NUMBER() OVER (PARTITION BY machine_id ORDER BY timestamp DESC) as rn
                FROM metrics
            ) mt ON m.machine_id = mt.machine_id AND mt.rn = 1
            ORDER BY m.machine_id
        """).fetchall()
        conn.close()

        result = []
        for row in machines:
            result.append({
                "machine_id": row["machine_id"],
                "hostname": row["hostname"],
                "ip_address": row["ip_address"],
                "os_info": row["os_info"],
                "status": row["status"],
                "last_seen": row["last_seen"],
                "cpu_percent": row["cpu_percent"] or 0,
                "memory_percent": row["memory_percent"] or 0,
                "disk_percent": row["disk_percent"] or 0,
                "disk_free_gb": row["disk_free_gb"] or 0
            })

        return jsonify({"machines": result})

    except Exception as e:
        print(f"[ERROR] GET /api/machines: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- GET /api/machines/<machine_id> ---
@app.route('/api/machines/<machine_id>', methods=['GET'])
def get_machine_detail(machine_id):
    """Return full detail for one machine including latest metrics."""
    try:
        conn = get_db()
        machine = conn.execute(
            "SELECT * FROM machines WHERE machine_id = ?", (machine_id,)
        ).fetchone()

        if not machine:
            conn.close()
            return jsonify({"status": "error", "message": "Machine not found"}), 404

        latest = conn.execute(
            """SELECT * FROM metrics WHERE machine_id = ?
               ORDER BY timestamp DESC LIMIT 1""",
            (machine_id,)
        ).fetchone()
        conn.close()

        result = dict(machine)
        if latest:
            result.update({
                "cpu_percent": latest["cpu_percent"],
                "memory_percent": latest["memory_percent"],
                "memory_used_gb": latest["memory_used_gb"],
                "memory_total_gb": latest["memory_total_gb"],
                "disk_percent": latest["disk_percent"],
                "disk_used_gb": latest["disk_used_gb"],
                "disk_free_gb": latest["disk_free_gb"],
                "disk_total_gb": latest["disk_total_gb"],
            })

        return jsonify(result)

    except Exception as e:
        print(f"[ERROR] GET /api/machines/{machine_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- GET /api/machines/<machine_id>/metrics ---
@app.route('/api/machines/<machine_id>/metrics', methods=['GET'])
def get_machine_metrics(machine_id):
    """Return metrics history for a machine. ?hours=1 (max 24)."""
    try:
        hours = min(int(request.args.get('hours', 1)), 24)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')

        conn = get_db()
        rows = conn.execute(
            """SELECT timestamp, cpu_percent, memory_percent,
                      disk_percent, disk_free_gb
               FROM metrics
               WHERE machine_id = ? AND timestamp > ?
               ORDER BY timestamp ASC""",
            (machine_id, cutoff)
        ).fetchall()
        conn.close()

        metrics = [dict(r) for r in rows]
        return jsonify({"machine_id": machine_id, "metrics": metrics})

    except Exception as e:
        print(f"[ERROR] GET /api/machines/{machine_id}/metrics: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- GET /api/alerts ---
@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Return alerts filtered by acknowledged parameter."""
    try:
        ack_param = request.args.get('acknowledged', 'false')
        conn = get_db()

        if ack_param == 'all':
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 100"
            ).fetchall()
        else:
            ack_value = 1 if ack_param == 'true' else 0
            rows = conn.execute(
                """SELECT * FROM alerts WHERE acknowledged = ?
                   ORDER BY timestamp DESC LIMIT 100""",
                (ack_value,)
            ).fetchall()
        conn.close()

        alerts = [dict(r) for r in rows]
        return jsonify({"alerts": alerts})

    except Exception as e:
        print(f"[ERROR] GET /api/alerts: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- POST /api/alerts/<alert_id>/acknowledge ---
@app.route('/api/alerts/<int:alert_id>/acknowledge', methods=['POST'])
def acknowledge_alert(alert_id):
    """Set acknowledged=1 for an alert."""
    try:
        conn = get_db()
        with conn:
            cursor = conn.execute(
                "UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,)
            )
            if cursor.rowcount == 0:
                conn.close()
                return jsonify({"status": "error", "message": "Alert not found"}), 404
        conn.close()
        return jsonify({"status": "ok"})

    except Exception as e:
        print(f"[ERROR] POST /api/alerts/{alert_id}/acknowledge: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- GET /api/dashboard/summary ---
@app.route('/api/dashboard/summary', methods=['GET'])
def dashboard_summary():
    """Return aggregate stats."""
    try:
        conn = get_db()

        total = conn.execute("SELECT COUNT(*) as c FROM machines").fetchone()["c"]
        online = conn.execute(
            "SELECT COUNT(*) as c FROM machines WHERE status = 'online'"
        ).fetchone()["c"]
        offline = total - online
        active_alerts = conn.execute(
            "SELECT COUNT(*) as c FROM alerts WHERE acknowledged = 0"
        ).fetchone()["c"]

        # Average CPU and memory across online machines (latest metric per machine)
        avgs = conn.execute("""
            SELECT AVG(mt.cpu_percent) as avg_cpu, AVG(mt.memory_percent) as avg_mem
            FROM machines m
            JOIN (
                SELECT machine_id, cpu_percent, memory_percent,
                       ROW_NUMBER() OVER (PARTITION BY machine_id ORDER BY timestamp DESC) as rn
                FROM metrics
            ) mt ON m.machine_id = mt.machine_id AND mt.rn = 1
            WHERE m.status = 'online'
        """).fetchone()
        conn.close()

        return jsonify({
            "total_machines": total,
            "online": online,
            "offline": offline,
            "avg_cpu": round(avgs["avg_cpu"] or 0, 1),
            "avg_memory": round(avgs["avg_mem"] or 0, 1),
            "active_alerts": active_alerts
        })

    except Exception as e:
        print(f"[ERROR] GET /api/dashboard/summary: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- POST /api/machines/check-offline ---
@app.route('/api/machines/check-offline', methods=['POST'])
def check_offline():
    """Mark machines as offline if last_seen > 30 seconds ago."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=30)).strftime('%Y-%m-%d %H:%M:%S')
        conn = get_db()
        newly_offline = []

        with conn:
            stale = conn.execute(
                """SELECT machine_id FROM machines
                   WHERE status = 'online' AND last_seen < ?""",
                (cutoff,)
            ).fetchall()

            for row in stale:
                mid = row["machine_id"]
                conn.execute(
                    "UPDATE machines SET status = 'offline' WHERE machine_id = ?",
                    (mid,)
                )
                # Create offline alert (avoid duplicate)
                check_and_create_alert(conn, mid, 'offline', 'critical',
                    f"{mid} has gone offline — no heartbeat received")
                newly_offline.append(mid)

        conn.close()

        if newly_offline:
            print(f"[OFFLINE] Machines went offline: {', '.join(newly_offline)}")

        return jsonify({"status": "ok", "newly_offline": newly_offline})

    except Exception as e:
        print(f"[ERROR] POST /api/machines/check-offline: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ============================================================================
# BACKGROUND THREAD — Offline Check
# ============================================================================
def background_offline_checker():
    """Run offline check every 30 seconds in a background thread."""
    while True:
        time.sleep(30)
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=30)).strftime('%Y-%m-%d %H:%M:%S')
            conn = get_db()
            with conn:
                stale = conn.execute(
                    """SELECT machine_id FROM machines
                       WHERE status = 'online' AND last_seen < ?""",
                    (cutoff,)
                ).fetchall()
                for row in stale:
                    mid = row["machine_id"]
                    conn.execute(
                        "UPDATE machines SET status = 'offline' WHERE machine_id = ?",
                        (mid,)
                    )
                    check_and_create_alert(conn, mid, 'offline', 'critical',
                        f"{mid} has gone offline — no heartbeat received")
                    print(f"[OFFLINE] {mid} marked offline (background check)")
            conn.close()
        except Exception as e:
            print(f"[ERROR] Background offline check: {e}")

# ============================================================================
# MAIN
# ============================================================================
if __name__ == '__main__':
    print("=" * 60)
    print("  College Lab Infrastructure Monitoring — Server")
    print("=" * 60)

    # Initialize database
    init_db()
    cleanup_old_metrics()

    # Start background offline checker
    checker_thread = threading.Thread(target=background_offline_checker, daemon=True)
    checker_thread.start()
    print("[BG] Background offline checker started (every 30s)")

    print(f"[SERVER] Starting on http://0.0.0.0:5000")
    print(f"[SERVER] Dashboard at http://localhost:5000")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=False)
