#!/usr/bin/env python3
"""
SSB WiFi Kiosk - QR Code Generator

Generates WiFi QR codes in the standard format:
WIFI:T:WPA;S:<SSID>;P:<PASSWORD>;;

Usage:
    python3 make_qr.py <SSID> <PASSWORD>
    
Output:
    - PNG file: /opt/ssb-wifi-kiosk/web/static/qr.png
    - JSON file: /var/run/ssb-ap/current.json (if not exists)

Author: SSB WiFi Kiosk Project
License: MIT
"""

import json
import os
import sys
from pathlib import Path

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H
except ImportError:
    print("ERROR: qrcode module not found. Install with: pip3 install qrcode[pil]")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("ERROR: PIL module not found. Install with: pip3 install Pillow")
    sys.exit(1)

# Output paths
QR_OUTPUT_PATH = Path("/opt/ssb-wifi-kiosk/web/static/qr.png")
CURRENT_JSON_PATH = Path("/var/run/ssb-ap/current.json")

# QR code settings
QR_SIZE = 400  # pixels
QR_BORDER = 2  # modules
QR_BOX_SIZE = 10  # pixels per module


def escape_wifi_string(s: str) -> str:
    r"""
    Escape special characters in WiFi QR code strings.
    Characters that need escaping: \ ; , " :
    """
    result = s
    # Backslash must be escaped first
    result = result.replace('\\', '\\\\')
    result = result.replace(';', '\\;')
    result = result.replace(',', '\\,')
    result = result.replace('"', '\\"')
    result = result.replace(':', '\\:')
    return result


def generate_wifi_qr_string(ssid: str, password: str, security: str = "WPA") -> str:
    """
    Generate the WiFi QR code string.
    
    Format: WIFI:T:<security>;S:<ssid>;P:<password>;;
    
    Security types: WPA, WEP, nopass
    """
    escaped_ssid = escape_wifi_string(ssid)
    escaped_password = escape_wifi_string(password)
    
    return f"WIFI:T:{security};S:{escaped_ssid};P:{escaped_password};;"


def generate_qr_code(ssid: str, password: str, output_path: Path) -> bool:
    """
    Generate a QR code image for WiFi connection.
    
    Args:
        ssid: WiFi network name
        password: WiFi password
        output_path: Path to save the PNG file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Generate WiFi QR string
        wifi_string = generate_wifi_qr_string(ssid, password)
        
        # Create QR code
        qr = qrcode.QRCode(
            version=None,  # Auto-determine size
            error_correction=ERROR_CORRECT_H,  # High error correction
            box_size=QR_BOX_SIZE,
            border=QR_BORDER,
        )
        
        qr.add_data(wifi_string)
        qr.make(fit=True)
        
        # Generate image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save image
        img.save(str(output_path))
        
        # Set permissions (world-readable for web server)
        os.chmod(output_path, 0o644)
        
        print(f"QR code saved to: {output_path}")
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to generate QR code: {e}", file=sys.stderr)
        return False


def update_current_json(ssid: str, password: str) -> bool:
    """
    Update the current credentials JSON file.
    Only updates if file doesn't exist (ap_rotate.py manages it normally).
    """
    try:
        import time
        
        CURRENT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        # Create basic credentials file
        data = {
            "ssid": ssid,
            "password": password,
            "created_at": time.time(),
            "expires_at": time.time() + 300,  # 5 minutes default
            "rotation_reason": "qr_generator"
        }
        
        with open(CURRENT_JSON_PATH, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Secure permissions - root only
        os.chmod(CURRENT_JSON_PATH, 0o600)
        
        return True
        
    except Exception as e:
        print(f"WARNING: Failed to update current.json: {e}", file=sys.stderr)
        return False


def main():
    """Main entry point"""
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <SSID> <PASSWORD>")
        print(f"       {sys.argv[0]} <SSID> <PASSWORD> <OUTPUT_PATH>")
        sys.exit(1)
    
    ssid = sys.argv[1]
    password = sys.argv[2]
    
    # Optional custom output path
    if len(sys.argv) >= 4:
        output_path = Path(sys.argv[3])
    else:
        output_path = QR_OUTPUT_PATH
    
    # Validate inputs
    if not ssid:
        print("ERROR: SSID cannot be empty", file=sys.stderr)
        sys.exit(1)
    
    if not password:
        print("ERROR: Password cannot be empty", file=sys.stderr)
        sys.exit(1)
    
    if len(password) < 8:
        print("WARNING: WPA2 passwords should be at least 8 characters", file=sys.stderr)
    
    # Generate QR code
    if not generate_qr_code(ssid, password, output_path):
        sys.exit(1)
    
    # Update current.json (only if file doesn't exist or is very old)
    if not CURRENT_JSON_PATH.exists():
        update_current_json(ssid, password)
    
    print(f"WiFi QR code generated successfully!")
    print(f"  SSID: {ssid}")
    print(f"  Output: {output_path}")


if __name__ == "__main__":
    main()
