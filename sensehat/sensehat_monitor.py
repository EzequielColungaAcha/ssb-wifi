#!/usr/bin/env python3
"""
SSB WiFi Kiosk - Sense HAT Monitor

Monitors network status and displays on Sense HAT LEDs.

Single AP Mode (default):
- Full 8x8 display shows status of wlan0
- GREEN: Internet reachable, AP ready
- YELLOW/ORANGE: Rotation in progress
- RED: No internet connectivity

Dual AP Mode:
- Display split vertically: left half (cols 0-3) = wlan0, right half (cols 4-7) = wlan1
- Each half shows "0" or "1" label at top
- When AP has <= 60 seconds remaining, that half blinks slowly

Joystick middle-click triggers immediate credential rotation.

Author: SSB WiFi Kiosk Project
License: MIT
"""

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional

# Try to import sense_hat
try:
    from sense_hat import SenseHat
    SENSE_HAT_AVAILABLE = True
except ImportError:
    SENSE_HAT_AVAILABLE = False
    print("WARNING: sense_hat module not available. Running in simulation mode.")

# Configuration
CONFIG_PATH = "/etc/ssb-ap/config.json"
RUN_DIR = Path("/var/run/ssb-ap")

# Default config values
DEFAULT_CONFIG = {
    "internet_check_host": "1.1.1.1",
    "internet_check_interval_sec": 5,
    "manual_rotation_cooldown_sec": 30,
    "dual_ap_mode": False,
    "led_blink_threshold_sec": 60,
}

# Colors (R, G, B)
COLOR_GREEN = (0, 255, 0)
COLOR_YELLOW = (255, 200, 0)
COLOR_ORANGE = (255, 140, 0)
COLOR_RED = (255, 0, 0)
COLOR_BLUE = (0, 100, 255)
COLOR_WHITE = (255, 255, 255)
COLOR_OFF = (0, 0, 0)

# Digit patterns for 3x5 pixels (used in top portion of each half)
# Each pattern is 5 rows x 3 cols
DIGIT_PATTERNS = {
    0: [
        [1, 1, 1],
        [1, 0, 1],
        [1, 0, 1],
        [1, 0, 1],
        [1, 1, 1],
    ],
    1: [
        [0, 1, 0],
        [1, 1, 0],
        [0, 1, 0],
        [0, 1, 0],
        [1, 1, 1],
    ],
}

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("sensehat-monitor")


class SenseHatSimulator:
    """Simulator for testing without actual Sense HAT hardware"""
    
    def __init__(self):
        self.pixels = [[COLOR_OFF for _ in range(8)] for _ in range(8)]
        self.rotation = 0
        self._joystick_callback = None
        self._joystick_thread = None
        self._running = True
    
    def set_pixels(self, pixel_list):
        """Set all 64 pixels"""
        for i, color in enumerate(pixel_list):
            row = i // 8
            col = i % 8
            self.pixels[row][col] = color
        # Log a summary
        colors = set(tuple(c) for c in pixel_list)
        logger.debug(f"[SIM] Display updated with {len(colors)} unique colors")
    
    def set_pixel(self, x, y, color):
        """Set a single pixel"""
        if 0 <= x < 8 and 0 <= y < 8:
            self.pixels[y][x] = color
    
    def clear(self, color=COLOR_OFF):
        """Clear display"""
        self.pixels = [[color for _ in range(8)] for _ in range(8)]
    
    def set_rotation(self, r):
        """Set display rotation"""
        self.rotation = r
    
    @property
    def stick(self):
        return self
    
    def direction_middle(self, callback):
        self._joystick_callback = callback
        logger.info("[SIM] Joystick callback registered")
    
    def _keyboard_listener(self):
        import select
        while self._running:
            if select.select([sys.stdin], [], [], 0.5)[0]:
                try:
                    line = sys.stdin.readline()
                    if line and self._joystick_callback:
                        logger.info("[SIM] Simulated joystick press")
                        class FakeEvent:
                            action = "pressed"
                        self._joystick_callback(FakeEvent())
                except:
                    pass
    
    def start_keyboard_listener(self):
        self._joystick_thread = threading.Thread(target=self._keyboard_listener, daemon=True)
        self._joystick_thread.start()
    
    def stop(self):
        self._running = False


class SenseHatMonitor:
    """Main monitor class for Sense HAT integration"""
    
    def __init__(self):
        self.config = self._load_config()
        self.running = True
        self.last_rotation_trigger: Dict[str, float] = {}
        
        # Blinking state
        self.blink_state = True
        self.last_blink_toggle = time.time()
        
        # Initialize Sense HAT
        if SENSE_HAT_AVAILABLE:
            self.sense = SenseHat()
            self.sense.set_rotation(0)
            self.sense.low_light = True
            logger.info("Sense HAT initialized")
        else:
            self.sense = SenseHatSimulator()
            self.sense.start_keyboard_listener()
            logger.info("Using Sense HAT simulator")
        
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
    
    def _load_config(self) -> dict:
        """Load configuration"""
        config = DEFAULT_CONFIG.copy()
        
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    file_config = json.load(f)
                config.update(file_config)
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
        
        return config
    
    def _handle_signal(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def check_internet(self) -> bool:
        """Check internet connectivity"""
        host = self.config.get("internet_check_host", "1.1.1.1")
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", host],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def get_interface_status(self, interface: str) -> Optional[dict]:
        """Get status for a specific interface"""
        status_file = RUN_DIR / f"status-{interface}.json"
        
        # Fallback to legacy status file for single AP mode
        if not status_file.exists() and interface == "wlan0":
            legacy_file = RUN_DIR / "status.json"
            if legacy_file.exists():
                status_file = legacy_file
                logger.debug(f"Using legacy status file for {interface}")
        
        if not status_file.exists():
            logger.warning(f"Status file not found: {status_file}")
            return None
        
        try:
            with open(status_file, 'r') as f:
                status = json.load(f)
                logger.debug(f"Loaded status for {interface}: state={status.get('state')}, "
                            f"time_remaining={status.get('time_remaining')}")
                return status
        except PermissionError:
            logger.error(f"Permission denied reading {status_file}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {status_file}: {e}")
        except Exception as e:
            logger.error(f"Failed to read status for {interface}: {e}")
        
        return None
    
    def get_active_interfaces(self) -> list:
        """Get list of active AP interfaces"""
        interfaces = []
        
        # Check for interface-specific status files
        for f in RUN_DIR.glob("status-wlan*.json"):
            interface = f.stem.replace("status-", "")
            status = self.get_interface_status(interface)
            if status and status.get("enabled", True) and status.get("state") != "disabled":
                interfaces.append(interface)
        
        # Fallback for single AP mode
        if not interfaces:
            legacy_status = RUN_DIR / "status.json"
            if legacy_status.exists():
                interfaces = ["wlan0"]
        
        return sorted(interfaces)
    
    def is_dual_mode(self) -> bool:
        """Check if running in dual AP mode"""
        interfaces = self.get_active_interfaces()
        return len(interfaces) >= 2 or self.config.get("dual_ap_mode", False)
    
    def should_blink(self, status: dict) -> bool:
        """Check if interface should blink (expiring soon)"""
        threshold = self.config.get("led_blink_threshold_sec", 60)
        time_remaining = status.get("time_remaining", 999)
        return time_remaining <= threshold and time_remaining > 0
    
    def get_status_color(self, status: dict, has_internet: bool) -> tuple:
        """Get color based on status"""
        state = status.get("state", "unknown")
        
        if state == "rotating":
            return COLOR_YELLOW
        elif state == "error":
            return COLOR_RED
        elif state == "disabled":
            return COLOR_OFF
        elif not has_internet:
            return COLOR_RED
        else:
            return COLOR_GREEN
    
    def draw_digit(self, pixels: list, digit: int, start_col: int, color: tuple):
        """Draw a digit pattern on the LED matrix"""
        pattern = DIGIT_PATTERNS.get(digit, DIGIT_PATTERNS[0])
        
        for row in range(5):
            for col in range(3):
                if pattern[row][col]:
                    x = start_col + col
                    y = row
                    if 0 <= x < 8 and 0 <= y < 8:
                        idx = y * 8 + x
                        pixels[idx] = color
    
    def draw_half(self, pixels: list, start_col: int, status: dict, digit: int, 
                  color: tuple, show: bool):
        """Draw status for one half of the display"""
        if not show:
            return
        
        # Draw digit label (rows 0-4, 3 cols wide, offset by 0.5 col for centering)
        self.draw_digit(pixels, digit, start_col, COLOR_WHITE)
        
        # Fill status color (rows 5-7, cols start_col to start_col+3)
        for row in range(5, 8):
            for col in range(start_col, start_col + 4):
                idx = row * 8 + col
                pixels[idx] = color
    
    def draw_full_display(self, pixels: list, status: dict, color: tuple, show: bool):
        """Draw full 8x8 display for single AP mode"""
        if not show:
            return
        
        for i in range(64):
            pixels[i] = color
    
    def update_blink_state(self):
        """Update blink toggle (0.5s interval)"""
        now = time.time()
        if now - self.last_blink_toggle >= 0.5:
            self.blink_state = not self.blink_state
            self.last_blink_toggle = now
    
    def update_display(self):
        """Main display update"""
        self.update_blink_state()
        has_internet = self.check_internet()
        
        pixels = [COLOR_OFF] * 64
        
        if self.is_dual_mode():
            # Dual AP mode - split display
            
            # Left half - wlan0
            status0 = self.get_interface_status("wlan0")
            if status0 and status0.get("state") != "disabled":
                color0 = self.get_status_color(status0, has_internet)
                should_blink0 = self.should_blink(status0)
                show0 = not should_blink0 or self.blink_state
                self.draw_half(pixels, 0, status0, 0, color0, show0)
            
            # Right half - wlan1
            status1 = self.get_interface_status("wlan1")
            if status1 and status1.get("state") != "disabled":
                color1 = self.get_status_color(status1, has_internet)
                should_blink1 = self.should_blink(status1)
                show1 = not should_blink1 or self.blink_state
                self.draw_half(pixels, 4, status1, 1, color1, show1)
        
        else:
            # Single AP mode - full display
            status = self.get_interface_status("wlan0")
            if status:
                color = self.get_status_color(status, has_internet)
                should_blink = self.should_blink(status)
                show = not should_blink or self.blink_state
                logger.debug(f"Single AP display: color={color}, blink={should_blink}, show={show}")
                self.draw_full_display(pixels, status, color, show)
            else:
                # No status available - show based on internet only
                logger.debug(f"No status file, falling back to internet check: {has_internet}")
                if has_internet:
                    self.draw_full_display(pixels, {}, COLOR_GREEN, True)
                else:
                    self.draw_full_display(pixels, {}, COLOR_RED, True)
        
        self.sense.set_pixels(pixels)
    
    def trigger_rotation(self, interface: str = "wlan0"):
        """Trigger manual rotation for an interface"""
        now = time.time()
        cooldown = self.config.get("manual_rotation_cooldown_sec", 30)
        last_trigger = self.last_rotation_trigger.get(interface, 0)
        
        if now - last_trigger < cooldown:
            remaining = cooldown - (now - last_trigger)
            logger.warning(f"Rotation cooldown for {interface}: {remaining:.0f}s")
            self._blink_error()
            return False
        
        try:
            # Ensure RUN_DIR exists
            RUN_DIR.mkdir(parents=True, exist_ok=True)
            
            trigger_file = RUN_DIR / f"trigger-rotate-{interface}"
            trigger_file.touch()
            
            # Make file readable by ap_rotate service
            os.chmod(trigger_file, 0o644)
            
            self.last_rotation_trigger[interface] = now
            logger.info(f"Manual rotation triggered for {interface}: created {trigger_file}")
            self._blink_confirm()
            return True
        except PermissionError as e:
            logger.error(f"Permission denied creating trigger file: {e}")
            self._blink_error()
            return False
        except Exception as e:
            logger.error(f"Failed to trigger rotation: {e}")
            self._blink_error()
            return False
    
    def _blink_error(self):
        """Flash red to indicate error"""
        for _ in range(2):
            self.sense.set_pixels([COLOR_RED] * 64)
            time.sleep(0.15)
            self.sense.set_pixels([COLOR_OFF] * 64)
            time.sleep(0.15)
    
    def _blink_confirm(self):
        """Flash yellow to confirm action"""
        for _ in range(2):
            self.sense.set_pixels([COLOR_YELLOW] * 64)
            time.sleep(0.15)
            self.sense.set_pixels([COLOR_OFF] * 64)
            time.sleep(0.15)
    
    def on_joystick_press(self, event):
        """Handle joystick middle button press"""
        logger.info(f"Joystick event received: direction={event.direction}, action={event.action}")
        
        if event.action == "pressed":
            logger.info("Joystick middle button pressed - triggering rotation")
            
            # In dual mode, trigger both interfaces
            if self.is_dual_mode():
                self.trigger_rotation("wlan0")
                self.trigger_rotation("wlan1")
            else:
                self.trigger_rotation("wlan0")
    
    def setup_joystick(self):
        """Setup joystick handler"""
        try:
            self.sense.stick.direction_middle = self.on_joystick_press
            logger.info("Joystick middle-click handler registered successfully")
        except AttributeError as e:
            logger.error(f"Joystick not available on this Sense HAT: {e}")
        except Exception as e:
            logger.warning(f"Failed to setup joystick: {e}")
    
    def run(self):
        """Main loop"""
        logger.info("Sense HAT Monitor starting...")
        logger.info(f"Dual AP mode: {self.is_dual_mode()}")
        
        self.setup_joystick()
        
        # Initial display
        self.sense.set_pixels([COLOR_YELLOW] * 64)
        time.sleep(1)
        
        # Use faster interval for responsive blinking
        check_interval = min(
            self.config.get("internet_check_interval_sec", 5),
            0.25  # Check at least 4 times per second for smooth blinking
        )
        
        while self.running:
            try:
                self.update_display()
                time.sleep(check_interval)
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                self.sense.set_pixels([COLOR_RED] * 64)
                time.sleep(5)
        
        logger.info("Shutting down Sense HAT Monitor...")
        self.sense.clear()
        
        if hasattr(self.sense, 'stop'):
            self.sense.stop()
        
        logger.info("Sense HAT Monitor stopped")


def main():
    """Entry point"""
    monitor = SenseHatMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
