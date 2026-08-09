"""
=============================================================================
 College Lab Infrastructure Monitoring — Agent Script
=============================================================================
 This script runs on each lab computer and collects system metrics
 (CPU, memory, disk usage) every 5 seconds, then sends them to the
 central monitoring server via HTTP POST.

 CONFIGURATION:
   Change MACHINE_ID to a unique name for each lab computer (e.g. "PC-01").
   Change SERVER_URL to point to the host laptop's IP address and port.

 INSTALL DEPENDENCIES:
   pip install psutil requests

 HOW TO RUN:
   Normal:           python agent.py
   Background (Win): pythonw agent.py   OR   START /B python agent.py
   Background (Lin): nohup python3 agent.py &

 AUTO-START (Windows):
   Use Task Scheduler → Create Basic Task → Action: Start a program
   Program: python
   Arguments: C:/full/path/to/agent.py

 AUTO-START (Linux — systemd):
   Create /etc/systemd/system/lab-agent.service:
     [Unit]
     Description=Lab Monitor Agent
     After=network.target

     [Service]
     Type=simple
     User=your_username
     ExecStart=/usr/bin/python3 /full/path/to/agent.py
     Restart=always
     RestartSec=10

     [Install]
     WantedBy=multi-user.target

   Then: sudo systemctl enable lab-agent && sudo systemctl start lab-agent
=============================================================================
"""

import time
import json
import socket
import uuid
import platform

import psutil
import requests

# ============================================================================
# CONFIGURATION — Edit these for each lab computer
# ============================================================================
MACHINE_ID = "PC-03"                                    # Unique ID for this machine
SERVER_URL = "http://192.168.177.155:5000/api/metrics"    # Change to host laptop IP
SEND_INTERVAL = 5                                       # Seconds between each send

# ============================================================================
# STATIC MACHINE INFO (collected once at startup)
# ============================================================================
def get_local_ip():
    """Get the local LAN IP address (not 127.0.0.1)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"

def get_mac_address():
    """Get MAC address as a formatted string."""
    mac = uuid.getnode()
    return ':'.join(f'{(mac >> i) & 0xff:02x}' for i in range(40, -1, -8))

HOSTNAME = socket.gethostname()
IP_ADDRESS = get_local_ip()
MAC_ADDRESS = get_mac_address()
OS_INFO = platform.platform()

# ============================================================================
# METRIC COLLECTION
# ============================================================================
def collect_metrics():
    """Collect current system metrics using psutil."""
    cpu = psutil.cpu_percent(interval=1)

    mem = psutil.virtual_memory()
    mem_percent = mem.percent
    mem_used_gb = round(mem.used / (1024 ** 3), 2)
    mem_total_gb = round(mem.total / (1024 ** 3), 2)

    disk_path = 'C:\\' if platform.system() == 'Windows' else '/'
    disk = psutil.disk_usage(disk_path)
    disk_percent = disk.percent
    disk_used_gb = round(disk.used / (1024 ** 3), 2)
    disk_free_gb = round(disk.free / (1024 ** 3), 2)
    disk_total_gb = round(disk.total / (1024 ** 3), 2)

    # Disk I/O activity (matches Task Manager's disk activity %)
    try:
        io1 = psutil.disk_io_counters()
        time.sleep(0.5)
        io2 = psutil.disk_io_counters()
        # Calculate bytes/sec (over 0.5s window)
        read_bps = (io2.read_bytes - io1.read_bytes) * 2
        write_bps = (io2.write_bytes - io1.write_bytes) * 2
        total_bps = read_bps + write_bps
        # Approximate activity % (assuming ~200MB/s max throughput for typical disk)
        max_throughput = 200 * 1024 * 1024  # 200 MB/s
        disk_io_percent = min(round((total_bps / max_throughput) * 100, 1), 100.0)
    except Exception:
        disk_io_percent = 0.0

    return {
        "machine_id": MACHINE_ID,
        "hostname": HOSTNAME,
        "ip_address": IP_ADDRESS,
        "mac_address": MAC_ADDRESS,
        "os_info": OS_INFO,
        "cpu_percent": cpu,
        "memory_percent": mem_percent,
        "memory_used_gb": mem_used_gb,
        "memory_total_gb": mem_total_gb,
        "disk_percent": disk_percent,
        "disk_used_gb": disk_used_gb,
        "disk_free_gb": disk_free_gb,
        "disk_total_gb": disk_total_gb,
        "disk_io_percent": disk_io_percent
    }

# ============================================================================
# MAIN LOOP
# ============================================================================
def main():
    print("=" * 60)
    print(f"  Lab Monitor Agent — {MACHINE_ID}")
    print("=" * 60)
    print(f"  Hostname:    {HOSTNAME}")
    print(f"  IP Address:  {IP_ADDRESS}")
    print(f"  MAC Address: {MAC_ADDRESS}")
    print(f"  OS:          {OS_INFO}")
    print(f"  Server:      {SERVER_URL}")
    print(f"  Interval:    {SEND_INTERVAL}s")
    print("=" * 60)

    iteration = 0

    while True:
        try:
            metrics = collect_metrics()

            response = requests.post(
                SERVER_URL,
                json=metrics,
                timeout=10
            )

            iteration += 1

            # Print status every 10th iteration to avoid spam
            if iteration % 10 == 1:
                print(f"[{MACHINE_ID}] Sent metrics — "
                      f"CPU: {metrics['cpu_percent']:.1f}% | "
                      f"MEM: {metrics['memory_percent']:.1f}% | "
                      f"DISK: {metrics['disk_percent']:.1f}% | "
                      f"Server: {response.status_code}")

        except requests.exceptions.ConnectionError:
            if iteration % 10 == 1:
                print(f"[{MACHINE_ID}] Connection failed — server unreachable. Retrying...")
        except requests.exceptions.Timeout:
            if iteration % 10 == 1:
                print(f"[{MACHINE_ID}] Request timed out. Retrying...")
        except Exception as e:
            print(f"[{MACHINE_ID}] Error: {e}")

        time.sleep(SEND_INTERVAL)

if __name__ == '__main__':
    main()
