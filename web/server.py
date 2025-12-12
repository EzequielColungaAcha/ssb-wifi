#!/usr/bin/env python3
"""
SSB WiFi Kiosk - Web Server

Lightweight Flask server for the kiosk display.
Serves the 4-quadrant UI and provides status API.
Supports both single AP and dual AP modes.

Endpoints:
    GET /           - Main kiosk page
    GET /status     - JSON status for AJAX polling (all interfaces)
    GET /status/<interface> - JSON status for specific interface
    GET /static/*   - Static files (QR, CSS, JS, images)

Author: SSB WiFi Kiosk Project
License: MIT
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, jsonify, render_template, send_from_directory

# Configuration
CONFIG_PATH = "/etc/ssb-ap/config.json"
RUN_DIR = Path("/var/run/ssb-ap")
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATE_DIR = Path(__file__).parent / "templates"

# Create Flask app
app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    template_folder=str(TEMPLATE_DIR)
)

# Disable caching for dynamic content
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0


def load_config() -> dict:
    """Load configuration file"""
    default_config = {
        "web_port": 8080,
        "rotation_interval_sec": 300,
        "dual_ap_mode": False,
    }
    
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
            default_config.update(config)
        except Exception as e:
            print(f"Warning: Failed to load config: {e}")
    
    return default_config


def get_interface_status(interface: str) -> dict:
    """Get status for a specific interface"""
    default_status = {
        "interface": interface,
        "enabled": False,
        "state": "unknown",
        "ssid": "",
        "created_at": 0,
        "expires_at": 0,
        "time_remaining": 0,
        "client_count": 0,
        "last_rotation_reason": "",
        "last_error": None
    }
    
    # Try interface-specific status file first
    status_file = RUN_DIR / f"status-{interface}.json"
    
    # Fallback to legacy status file for backward compatibility
    if not status_file.exists() and interface == "wlan0":
        status_file = RUN_DIR / "status.json"
    
    try:
        if status_file.exists():
            with open(status_file, 'r') as f:
                status = json.load(f)
            default_status.update(status)
            default_status["enabled"] = True
    except Exception as e:
        default_status["last_error"] = str(e)
    
    # Add computed fields
    now = time.time()
    if default_status["expires_at"] > 0:
        default_status["time_remaining"] = max(0, int(default_status["expires_at"] - now))
        default_status["expires_at_iso"] = datetime.fromtimestamp(
            default_status["expires_at"]
        ).strftime("%H:%M:%S")
    else:
        default_status["time_remaining"] = 0
        default_status["expires_at_iso"] = ""
    
    if default_status["created_at"] > 0:
        default_status["created_at_iso"] = datetime.fromtimestamp(
            default_status["created_at"]
        ).strftime("%H:%M:%S")
    else:
        default_status["created_at_iso"] = ""
    
    return default_status


def get_active_interfaces() -> List[str]:
    """Get list of active AP interfaces"""
    interfaces = []
    
    # Check for interface-specific status files
    for f in RUN_DIR.glob("status-wlan*.json"):
        interface = f.stem.replace("status-", "")
        status = get_interface_status(interface)
        if status.get("enabled", False) and status.get("state") != "disabled":
            interfaces.append(interface)
    
    # Fallback for single AP mode
    if not interfaces:
        legacy_status = RUN_DIR / "status.json"
        if legacy_status.exists():
            interfaces = ["wlan0"]
    
    return sorted(interfaces)


def get_all_status() -> dict:
    """Get combined status for all interfaces"""
    config = load_config()
    interfaces = get_active_interfaces()
    dual_mode = len(interfaces) >= 2 or config.get("dual_ap_mode", False)
    
    result = {
        "dual_ap_mode": dual_mode,
        "interfaces": {},
        "active_interfaces": interfaces,
    }
    
    for interface in ["wlan0", "wlan1"]:
        status = get_interface_status(interface)
        
        # Add QR mtime for cache busting
        qr_path = STATIC_DIR / f"qr-{interface}.png"
        if not qr_path.exists() and interface == "wlan0":
            qr_path = STATIC_DIR / "qr.png"
        
        if qr_path.exists():
            status["qr_mtime"] = int(qr_path.stat().st_mtime)
            status["qr_url"] = f"/static/qr-{interface}.png"
        else:
            status["qr_mtime"] = 0
            status["qr_url"] = "/static/qr.png"
        
        result["interfaces"][interface] = status
    
    # For backward compatibility, include top-level fields from wlan0
    if "wlan0" in result["interfaces"]:
        wlan0 = result["interfaces"]["wlan0"]
        result.update({
            "state": wlan0.get("state", "unknown"),
            "ssid": wlan0.get("ssid", ""),
            "created_at": wlan0.get("created_at", 0),
            "expires_at": wlan0.get("expires_at", 0),
            "time_remaining": wlan0.get("time_remaining", 0),
            "client_count": wlan0.get("client_count", 0),
            "qr_mtime": wlan0.get("qr_mtime", 0),
        })
    
    return result


@app.route('/')
def index():
    """Serve the main kiosk page"""
    status = get_all_status()
    config = load_config()
    
    return render_template(
        'index.html',
        dual_ap_mode=status.get("dual_ap_mode", False),
        ssid=status.get("ssid", ""),
        state=status.get("state", "unknown"),
        time_remaining=status.get("time_remaining", 0),
        client_count=status.get("client_count", 0),
        rotation_interval=config.get("rotation_interval_sec", 300)
    )


@app.route('/status')
def status():
    """Return JSON status for AJAX polling (all interfaces)"""
    return jsonify(get_all_status())


@app.route('/status/<interface>')
def status_interface(interface: str):
    """Return JSON status for specific interface"""
    if interface not in ["wlan0", "wlan1"]:
        return jsonify({"error": "Invalid interface"}), 400
    
    status = get_interface_status(interface)
    
    # Add QR mtime
    qr_path = STATIC_DIR / f"qr-{interface}.png"
    if not qr_path.exists() and interface == "wlan0":
        qr_path = STATIC_DIR / "qr.png"
    
    if qr_path.exists():
        status["qr_mtime"] = int(qr_path.stat().st_mtime)
    else:
        status["qr_mtime"] = 0
    
    return jsonify(status)


@app.route('/static/qr.png')
def serve_qr():
    """Serve main QR code (wlan0) with no-cache headers"""
    response = send_from_directory(str(STATIC_DIR), 'qr.png')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/static/qr-<interface>.png')
def serve_qr_interface(interface: str):
    """Serve interface-specific QR code with no-cache headers"""
    filename = f'qr-{interface}.png'
    qr_path = STATIC_DIR / filename
    
    # Fallback to main qr.png for wlan0 if interface-specific doesn't exist
    if not qr_path.exists() and interface == "wlan0":
        filename = 'qr.png'
    
    response = send_from_directory(str(STATIC_DIR), filename)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "timestamp": time.time(),
        "interfaces": get_active_interfaces()
    })


@app.after_request
def add_header(response):
    """Add cache control headers"""
    if 'Cache-Control' not in response.headers:
        if response.content_type and 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


def main():
    """Entry point"""
    config = load_config()
    port = config.get("web_port", 8080)
    
    print(f"SSB WiFi Kiosk Web Server starting on port {port}")
    print(f"Dual AP mode: {config.get('dual_ap_mode', False)}")
    print(f"Static files: {STATIC_DIR}")
    print(f"Templates: {TEMPLATE_DIR}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,
        threaded=True
    )


if __name__ == "__main__":
    main()
