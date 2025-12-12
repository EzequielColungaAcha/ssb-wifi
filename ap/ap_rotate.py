#!/usr/bin/env python3
"""
SSB WiFi Kiosk - AP Rotation Daemon

Manages rotating WiFi credentials for access point(s).
Supports single AP mode (wlan0) or dual AP mode (wlan0 + wlan1).

Triggers rotation based on:
1. Time elapsed (default: 5 minutes)
2. Client count threshold (default: >=5 clients AND >=2 minutes)

Author: SSB WiFi Kiosk Project
License: MIT
"""

import json
import logging
import os
import secrets
import signal
import string
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

# ===== Configuration =====

CONFIG_PATH = "/etc/ssb-ap/config.json"
DEFAULT_CONFIG = {
    "rotation_interval_sec": 300,
    "client_threshold": 5,
    "min_time_after_clients_sec": 120,
    "ssid_prefix": "ssb-",
    "ssid_length": 6,
    "password_length": 16,
    "wan_interface": "eth0",
    "country_code": "AR",
    "log_retention_count": 100,
    "manual_rotation_cooldown_sec": 30,
    "dual_ap_mode": False,
    "led_blink_threshold_sec": 60,
    "interfaces": {
        "wlan0": {
            "enabled": True,
            "ap_ip": "192.168.4.1",
            "ap_netmask": "255.255.255.0",
            "dhcp_range_start": "192.168.4.10",
            "dhcp_range_end": "192.168.4.100",
            "dhcp_lease_time": "4h",
            "channel": 6
        },
        "wlan1": {
            "enabled": False,
            "ap_ip": "192.168.5.1",
            "ap_netmask": "255.255.255.0",
            "dhcp_range_start": "192.168.5.10",
            "dhcp_range_end": "192.168.5.100",
            "dhcp_lease_time": "4h",
            "channel": 11
        }
    }
}

# Runtime paths
RUN_DIR = Path("/var/run/ssb-ap")
LOG_DIR = Path("/var/log/ssb-ap")
ROTATIONS_LOG_FILE = LOG_DIR / "rotations.json"

# Template paths
HOSTAPD_TEMPLATE_DIR = "/opt/ssb-wifi-kiosk/ap"
QR_GENERATOR = "/opt/ssb-wifi-kiosk/qr/make_qr.py"

# ===== Logging Setup =====

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ap-rotate")


@dataclass
class Credentials:
    """WiFi credentials for an interface"""
    interface: str
    ssid: str
    password: str
    created_at: float
    expires_at: float
    rotation_reason: str


@dataclass
class InterfaceStatus:
    """Status for a single interface"""
    interface: str
    enabled: bool
    state: str  # "ready", "rotating", "error", "disabled"
    ssid: str
    created_at: float
    expires_at: float
    time_remaining: int
    client_count: int
    last_rotation_reason: str
    last_error: Optional[str] = None


class APInstance:
    """Manages a single AP interface"""
    
    def __init__(self, interface: str, config: dict, global_config: dict):
        self.interface = interface
        self.config = config
        self.global_config = global_config
        self.current_creds: Optional[Credentials] = None
        self.last_manual_rotation = 0.0
        self.rotation_lock = threading.Lock()
        
        # Per-interface paths
        self.status_file = RUN_DIR / f"status-{interface}.json"
        self.creds_file = RUN_DIR / f"current-{interface}.json"
        self.trigger_file = RUN_DIR / f"trigger-rotate-{interface}"
        self.hostapd_conf = Path(f"/etc/hostapd/hostapd-{interface}.conf")
        self.template_file = Path(f"{HOSTAPD_TEMPLATE_DIR}/hostapd-{interface}-template.conf")
        
        # Fallback to generic template if interface-specific doesn't exist
        if not self.template_file.exists():
            self.template_file = Path(f"{HOSTAPD_TEMPLATE_DIR}/hostapd-template.conf")
    
    def is_interface_available(self) -> bool:
        """Check if the physical interface exists"""
        try:
            result = subprocess.run(
                ["ip", "link", "show", self.interface],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def get_client_count(self) -> int:
        """Count connected clients using iw station dump"""
        try:
            result = subprocess.run(
                ["iw", "dev", self.interface, "station", "dump"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                count = sum(1 for line in result.stdout.split('\n')
                           if line.strip().startswith("Station"))
                return count
            return 0
        except Exception as e:
            logger.debug(f"Error getting client count for {self.interface}: {e}")
            return 0
    
    def generate_ssid(self) -> str:
        """Generate a random SSID"""
        prefix = self.global_config["ssid_prefix"]
        length = self.global_config["ssid_length"]
        chars = string.ascii_lowercase + string.digits
        random_part = ''.join(secrets.choice(chars) for _ in range(length))
        return f"{prefix}{random_part}"
    
    def generate_password(self) -> str:
        """Generate a secure random password"""
        length = self.global_config["password_length"]
        chars = string.ascii_letters + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))
    
    def write_hostapd_config(self, ssid: str, password: str) -> bool:
        """Write hostapd configuration from template"""
        try:
            if not self.template_file.exists():
                logger.error(f"hostapd template not found: {self.template_file}")
                return False
            
            with open(self.template_file, 'r') as f:
                template = f.read()
            
            # Replace placeholders
            config_content = template.replace("{{SSID}}", ssid)
            config_content = config_content.replace("{{PASSWORD}}", password)
            config_content = config_content.replace("{{CHANNEL}}", 
                                                    str(self.config.get("channel", 6)))
            config_content = config_content.replace("{{COUNTRY_CODE}}", 
                                                    self.global_config["country_code"])
            
            # Ensure directory exists
            self.hostapd_conf.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.hostapd_conf, 'w') as f:
                f.write(config_content)
            
            os.chmod(self.hostapd_conf, 0o600)
            logger.info(f"Wrote hostapd config for {self.interface}: SSID={ssid}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to write hostapd config for {self.interface}: {e}")
            return False
    
    def generate_qr(self, ssid: str, password: str) -> bool:
        """Generate QR code for this interface"""
        try:
            # Output path includes interface name for dual mode
            output_path = f"/opt/ssb-wifi-kiosk/web/static/qr-{self.interface}.png"
            
            result = subprocess.run(
                [sys.executable, QR_GENERATOR, ssid, password, output_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                logger.info(f"QR code generated for {self.interface}")
                
                # For backward compatibility, also update main qr.png for wlan0
                if self.interface == "wlan0":
                    main_qr = "/opt/ssb-wifi-kiosk/web/static/qr.png"
                    subprocess.run(
                        ["cp", output_path, main_qr],
                        capture_output=True,
                        timeout=5
                    )
                
                return True
            else:
                logger.error(f"QR generation failed for {self.interface}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error generating QR for {self.interface}: {e}")
            return False
    
    def restart_hostapd(self) -> bool:
        """Restart hostapd service for this interface"""
        try:
            # Determine correct service name based on mode
            dual_mode = self.global_config.get("dual_ap_mode", False)
            
            if dual_mode:
                # Dual mode: use template service per interface
                service_name = f"hostapd@{self.interface}"
            else:
                # Single mode: use standard hostapd service
                service_name = "hostapd"
            
            logger.debug(f"Restarting {service_name} for {self.interface}")
            
            result = subprocess.run(
                ["systemctl", "restart", service_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info(f"{service_name} restarted successfully")
                return True
            else:
                logger.error(f"{service_name} restart failed: {result.stderr.strip()}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout restarting hostapd for {self.interface}")
            return False
        except Exception as e:
            logger.error(f"Error restarting hostapd for {self.interface}: {e}")
            return False
    
    def save_credentials(self):
        """Save current credentials to file"""
        if not self.current_creds:
            return
        try:
            with open(self.creds_file, 'w') as f:
                json.dump(asdict(self.current_creds), f, indent=2)
            os.chmod(self.creds_file, 0o600)
        except Exception as e:
            logger.error(f"Failed to save credentials for {self.interface}: {e}")
    
    def update_status(self, state: str, error: Optional[str] = None):
        """Update status file for this interface"""
        try:
            now = time.time()
            time_remaining = 0
            if self.current_creds and self.current_creds.expires_at > now:
                time_remaining = int(self.current_creds.expires_at - now)
            
            status = InterfaceStatus(
                interface=self.interface,
                enabled=self.config.get("enabled", True),
                state=state,
                ssid=self.current_creds.ssid if self.current_creds else "",
                created_at=self.current_creds.created_at if self.current_creds else 0,
                expires_at=self.current_creds.expires_at if self.current_creds else 0,
                time_remaining=time_remaining,
                client_count=self.get_client_count(),
                last_rotation_reason=self.current_creds.rotation_reason if self.current_creds else "",
                last_error=error
            )
            
            with open(self.status_file, 'w') as f:
                json.dump(asdict(status), f, indent=2)
            os.chmod(self.status_file, 0o644)
            
        except Exception as e:
            logger.error(f"Failed to update status for {self.interface}: {e}")
    
    def rotate_credentials(self, reason: str) -> bool:
        """Perform credential rotation for this interface"""
        with self.rotation_lock:
            logger.info(f"Starting rotation for {self.interface}: {reason}")
            self.update_status("rotating")
            
            try:
                new_ssid = self.generate_ssid()
                new_password = self.generate_password()
                
                now = time.time()
                expires_at = now + self.global_config["rotation_interval_sec"]
                
                if not self.write_hostapd_config(new_ssid, new_password):
                    self.update_status("error", "Failed to write hostapd config")
                    return False
                
                if not self.generate_qr(new_ssid, new_password):
                    logger.warning(f"QR generation failed for {self.interface}, continuing")
                
                if not self.restart_hostapd():
                    self.update_status("error", "Failed to restart hostapd")
                    return False
                
                self.current_creds = Credentials(
                    interface=self.interface,
                    ssid=new_ssid,
                    password=new_password,
                    created_at=now,
                    expires_at=expires_at,
                    rotation_reason=reason
                )
                
                self.save_credentials()
                self.update_status("ready")
                
                logger.info(f"Rotation complete for {self.interface}: SSID={new_ssid}")
                return True
                
            except Exception as e:
                logger.error(f"Rotation failed for {self.interface}: {e}")
                self.update_status("error", str(e))
                return False
    
    def check_trigger_file(self) -> bool:
        """Check for manual rotation trigger"""
        if self.trigger_file.exists():
            try:
                self.trigger_file.unlink()
                
                now = time.time()
                cooldown = self.global_config["manual_rotation_cooldown_sec"]
                if now - self.last_manual_rotation < cooldown:
                    remaining = cooldown - (now - self.last_manual_rotation)
                    logger.warning(f"Manual rotation cooldown for {self.interface}: {remaining:.0f}s")
                    return False
                
                self.last_manual_rotation = now
                return True
            except Exception as e:
                logger.error(f"Error checking trigger for {self.interface}: {e}")
        return False
    
    def should_rotate(self) -> tuple:
        """Check if rotation should occur"""
        if not self.current_creds:
            return True, "initial"
        
        now = time.time()
        time_since_creation = now - self.current_creds.created_at
        time_until_expiry = self.current_creds.expires_at - now
        
        # Log current state for debugging
        client_count = self.get_client_count()
        logger.debug(f"[{self.interface}] Rotation check: "
                     f"age={time_since_creation:.0f}s, "
                     f"expires_in={time_until_expiry:.0f}s, "
                     f"clients={client_count}")
        
        if now >= self.current_creds.expires_at:
            logger.info(f"[{self.interface}] Rotation trigger: time_expired "
                        f"(age={time_since_creation:.0f}s)")
            return True, "time_expired"
        
        threshold = self.global_config["client_threshold"]
        min_time = self.global_config["min_time_after_clients_sec"]
        
        if client_count >= threshold and time_since_creation >= min_time:
            logger.info(f"[{self.interface}] Rotation trigger: client_threshold "
                        f"(clients={client_count}, age={time_since_creation:.0f}s)")
            return True, f"client_threshold_{client_count}"
        
        return False, ""


class APRotationDaemon:
    """Main daemon class managing all AP instances"""

    def __init__(self):
        self.config = self._load_config()
        self.running = True
        self.ap_instances: Dict[str, APInstance] = {}
        
        # Ensure directories exist
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(RUN_DIR, 0o755)  # Allow other services to read status files
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGHUP, self._handle_reload)
        
        # Initialize AP instances
        self._init_ap_instances()

    def _load_config(self) -> dict:
        """Load configuration from file"""
        config = DEFAULT_CONFIG.copy()
        
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    file_config = json.load(f)
                
                # Deep merge for interfaces
                if "interfaces" in file_config:
                    for iface, iface_config in file_config["interfaces"].items():
                        if iface in config["interfaces"]:
                            config["interfaces"][iface].update(iface_config)
                        else:
                            config["interfaces"][iface] = iface_config
                    del file_config["interfaces"]
                
                config.update(file_config)
                logger.info(f"Loaded config from {CONFIG_PATH}")
            except Exception as e:
                logger.warning(f"Failed to load config: {e}, using defaults")
        
        return config

    def _init_ap_instances(self):
        """Initialize AP instances based on config"""
        interfaces_config = self.config.get("interfaces", {})
        dual_mode = self.config.get("dual_ap_mode", False)
        
        for interface, iface_config in interfaces_config.items():
            # Skip wlan1 if not in dual mode
            if interface == "wlan1" and not dual_mode:
                logger.info(f"Skipping {interface} (dual_ap_mode disabled)")
                continue
            
            # Check if interface is enabled in config
            if not iface_config.get("enabled", True):
                logger.info(f"Skipping {interface} (disabled in config)")
                continue
            
            # Create AP instance
            ap = APInstance(interface, iface_config, self.config)
            
            # Check if physical interface exists
            if not ap.is_interface_available():
                logger.warning(f"Interface {interface} not available, skipping")
                # Write disabled status
                ap.update_status("disabled", "Interface not found")
                continue
            
            self.ap_instances[interface] = ap
            logger.info(f"Initialized AP instance for {interface}")
        
        if not self.ap_instances:
            logger.error("No AP interfaces available!")
            sys.exit(1)
        
        logger.info(f"Active interfaces: {list(self.ap_instances.keys())}")

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def _handle_reload(self, signum, frame):
        """Handle SIGHUP to reload config"""
        logger.info("Received SIGHUP, reloading configuration...")
        self.config = self._load_config()
        # Update global config in instances
        for ap in self.ap_instances.values():
            ap.global_config = self.config

    def log_rotation(self, creds: Credentials):
        """Log rotation event"""
        try:
            rotations = []
            if ROTATIONS_LOG_FILE.exists():
                with open(ROTATIONS_LOG_FILE, 'r') as f:
                    rotations = json.load(f)
            
            entry = {
                "timestamp": datetime.now().isoformat(),
                "interface": creds.interface,
                "ssid": creds.ssid,
                "reason": creds.rotation_reason,
                "created_at": creds.created_at,
            }
            rotations.append(entry)
            
            retention = self.config.get("log_retention_count", 100)
            if len(rotations) > retention:
                rotations = rotations[-retention:]
            
            with open(ROTATIONS_LOG_FILE, 'w') as f:
                json.dump(rotations, f, indent=2)
            os.chmod(ROTATIONS_LOG_FILE, 0o600)
            
        except Exception as e:
            logger.error(f"Failed to log rotation: {e}")

    def run(self):
        """Main daemon loop"""
        logger.info("AP Rotation Daemon starting...")
        logger.info(f"Dual AP mode: {self.config.get('dual_ap_mode', False)}")
        logger.info(f"Rotation interval: {self.config['rotation_interval_sec']}s")
        
        # Initial rotation for all interfaces
        for interface, ap in self.ap_instances.items():
            if not ap.rotate_credentials("startup"):
                logger.error(f"Initial rotation failed for {interface}, retrying...")
                time.sleep(5)
                if not ap.rotate_credentials("startup_retry"):
                    logger.error(f"Startup rotation failed for {interface}")
                    ap.update_status("error", "Startup rotation failed")
            else:
                self.log_rotation(ap.current_creds)
        
        # Main loop
        while self.running:
            try:
                for interface, ap in self.ap_instances.items():
                    # Check for manual trigger
                    if ap.check_trigger_file():
                        if ap.rotate_credentials("manual_trigger"):
                            self.log_rotation(ap.current_creds)
                        continue
                    
                    # Check rotation conditions
                    should_rotate, reason = ap.should_rotate()
                    if should_rotate:
                        if ap.rotate_credentials(reason):
                            self.log_rotation(ap.current_creds)
                        else:
                            logger.warning(f"Rotation failed for {interface}, will retry")
                    else:
                        # Just update status with current info
                        ap.update_status("ready")
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(5)
        
        logger.info("AP Rotation Daemon stopped")


def main():
    """Entry point"""
    if os.geteuid() != 0:
        print("ERROR: This daemon must run as root", file=sys.stderr)
        sys.exit(1)
    
    daemon = APRotationDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
