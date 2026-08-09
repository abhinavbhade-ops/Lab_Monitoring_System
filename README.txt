================================================================================
  College Lab Infrastructure Monitoring Dashboard
  Setup & Usage Guide
================================================================================

OVERVIEW
--------
A real-time monitoring system for college computer labs. Each lab PC runs a
lightweight Python agent that reports CPU, memory, and disk metrics every
5 seconds to a central Flask server. An admin dashboard shows live status
of all machines with charts, alerts, and sound notifications.


PREREQUISITES
-------------
- Python 3.8+ installed on the server and all lab PCs
- All machines must be on the same WiFi/LAN network


STEP 1: Install Dependencies
-----------------------------
On the HOST laptop (server):
    pip install flask psutil

On each LAB PC (agent):
    pip install psutil requests


STEP 2: Start the Server
--------------------------
On the host laptop, open a terminal in this folder and run:

    python server.py

You should see:
    ============================================================
      College Lab Infrastructure Monitoring — Server
    ============================================================
    [DB] Database initialized — all tables ready.
    [BG] Background offline checker started (every 30s)
    [SERVER] Starting on http://0.0.0.0:5000
    [SERVER] Dashboard at http://localhost:5000
    ============================================================

The server is now running. Do NOT close this terminal.


STEP 3: Find the Host Laptop IP Address
-----------------------------------------
Windows:    ipconfig        (look for "IPv4 Address" under your WiFi adapter)
Linux:      hostname -I
macOS:      ipconfig getifaddr en0

Example: 192.168.1.100


STEP 4: Configure the Agent
-----------------------------
Open agent.py and edit the top 2 lines:

    MACHINE_ID = "PC-01"                                    # Unique name for this PC
    SERVER_URL = "http://192.168.1.100:5000/api/metrics"    # Replace with host IP

For each lab PC, change MACHINE_ID to a unique name:
    PC-01, PC-02, PC-03, etc.

The SERVER_URL must use the host laptop's actual IP (not localhost).


STEP 5: Run the Agent on Each Lab PC
--------------------------------------
Normal mode (shows console output):
    python agent.py

Background mode (Windows):
    pythonw agent.py
    or: START /B python agent.py

Background mode (Linux):
    nohup python3 agent.py &


STEP 6: Open the Dashboard
----------------------------
On ANY device on the same network, open a browser and go to:

    http://<host-laptop-ip>:5000

Example: http://192.168.1.100:5000

The dashboard will show all connected machines with live-updating metrics.


HOW IT WORKS
------------
1. Each agent collects CPU, memory, and disk usage every 5 seconds
2. Agent sends metrics via HTTP POST to the server
3. Server stores data in SQLite and checks alert conditions:
   - CPU > 90% → Critical alert
   - CPU > 75% → Warning alert
   - Disk free < 5GB → Critical alert
   - Disk free < 10GB → Warning alert
   - No heartbeat for 30s → Machine marked offline
4. Dashboard auto-refreshes every 5 seconds
5. Alert sound plays when new critical alerts appear


DEMO TIP
--------
To see the dashboard in action quickly:
1. Start the server
2. Run agent.py on your own laptop (with SERVER_URL = "http://localhost:5000/api/metrics")
3. Open a web browser to http://localhost:5000
4. Open a CPU-heavy task (YouTube, video editing, etc.) to see metrics spike
5. Watch the dashboard update in real-time!


FILE STRUCTURE
--------------
lab-monitor/
  server.py          ← Flask backend (run this on the host laptop)
  agent.py           ← Metric collection agent (run on each lab PC)
  templates/
    index.html       ← Dashboard frontend (served automatically by server.py)
  lab_monitor.db     ← SQLite database (auto-created on first run)
  README.txt         ← This file


TROUBLESHOOTING
---------------
Q: Agent says "Connection failed — server unreachable"
A: Check that SERVER_URL has the correct IP and port. Make sure server.py is running.
   Verify both machines are on the same network. Check firewall settings.

Q: Dashboard shows "No machines connected yet"
A: Start agent.py on at least one computer. Wait 5 seconds for the first metric.

Q: Machine shows offline even though agent is running
A: Check the agent console for errors. Verify SERVER_URL is correct.

================================================================================
  College Lab Monitoring System
================================================================================
