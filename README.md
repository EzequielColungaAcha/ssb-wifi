# SSB WiFi Kiosk

Rotating WiFi Access Point with QR Code Display for Raspberry Pi 3.

## Overview

This system turns a Raspberry Pi 3 into a WiFi access point with automatically rotating credentials, displayed as a scannable QR code on a kiosk screen. Perfect for restaurants, cafes, and retail locations where you want to provide temporary WiFi access.

### Features

- **Rotating Credentials**: SSID and password automatically change based on time or client count
- **QR Code Display**: Scannable QR code for easy WiFi connection
- **4-Quadrant Kiosk UI**: Customizable display with branding, menu, promotions, and QR code
- **Sense HAT Integration**: LED status indicators and joystick control
- **Secure by Default**: WPA2-PSK with strong random passwords
- **Automatic Recovery**: Systemd services with restart on failure
- **Dual AP Mode**: Optional second WiFi adapter for two independent access points

## Hardware Requirements

### Required

- Raspberry Pi 3 Model B (v1.2 or later)
- MicroSD card (8GB minimum, 16GB recommended)
- Ethernet cable (for Starlink/internet connection)
- Power supply (5V 2.5A)
- Display with HDMI input

### Optional

- Sense HAT (for LED status and joystick control)
- USB WiFi dongle (for dual AP mode - see below)

### Network Topology

```
[Starlink Mini] ──ethernet──> [Raspberry Pi 3] ~~WiFi AP~~> [Clients]
     (eth0)                         ↓
                              [Kiosk Display]
                              [Sense HAT LEDs]
```

## Installation

### 1. Prepare Raspberry Pi

Install Raspberry Pi OS Lite (64-bit or 32-bit) using Raspberry Pi Imager:

- Download: https://www.raspberrypi.com/software/
- Choose: Raspberry Pi OS Lite (Bookworm/Trixie)
- Enable SSH in imager settings
- Configure WiFi for initial setup (optional)

### 2. Initial Setup

Boot the Pi and connect via SSH or console:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Connect ethernet to Starlink
# Verify internet connectivity
ping 8.8.8.8
```

### 3. Copy Installation Files

From your computer:

```bash
scp -r ssb-wifi-kiosk/ pi@<PI_IP>:~/
```

### 4. Run Installer

```bash
ssh pi@<PI_IP>
cd ~/ssb-wifi-kiosk
sudo ./install.sh
```

The installer will:

1. Install required packages (hostapd, dnsmasq, chromium, etc.)
2. Create kiosk user for autologin
3. Configure network interfaces
4. Install and enable systemd services
5. Generate initial credentials and start services

### 5. Verify Installation

```bash
# Check service status
sudo systemctl status ssb-ap-rotate
sudo systemctl status ssb-webserver

# View current credentials
sudo ssb-show

# View kiosk UI
# Open browser to http://<PI_IP>:8080
```

### 6. Reboot

```bash
sudo reboot
```

After reboot, the Pi should:

- Auto-login as kiosk user
- Start X11 and Chromium in fullscreen
- Display the 4-quadrant kiosk UI with QR code

## Configuration

### Main Configuration

Edit `/etc/ssb-ap/config.json`:

```json
{
  "rotation_interval_sec": 300, // Rotate every 5 minutes
  "client_threshold": 5, // Rotate when 5+ clients connected
  "min_time_after_clients_sec": 120, // AND at least 2 minutes elapsed
  "ssid_prefix": "ssb-", // SSID pattern: ssb-xxxxxx
  "channel": 6, // WiFi channel
  "ap_interface": "wlan0", // WiFi interface
  "wan_interface": "eth0", // Internet interface
  "web_port": 8080 // Kiosk web server port
}
```

### Kiosk Content

Edit `/opt/ssb-wifi-kiosk/web/static/config.js`:

```javascript
const KIOSK_CONFIG = {
  quadrant1: {
    title: 'Your Business Name',
    subtitle: 'Your tagline here',
  },
  quadrant2: {
    title: 'Menu',
    items: [
      'Item 1 - $10',
      'Item 2 - $15',
      // ...
    ],
  },
  quadrant3: {
    title: 'Promotions',
    promos: [
      { icon: '🎉', text: 'Special offer!' },
      // ...
    ],
  },
};
```

### Custom Logo

Place your logo at:

```
/opt/ssb-wifi-kiosk/web/static/assets/logo.png
```

## Usage

### View Current Credentials

```bash
sudo ssb-show
```

Displays:

- Current SSID and password
- Number of connected clients
- Time until next rotation
- QR code (if qrencode installed)

### Force Credential Rotation

```bash
sudo touch /var/run/ssb-ap/trigger-rotate
```

Or press the Sense HAT joystick middle button.

### View Logs

```bash
# AP rotation daemon logs
journalctl -u ssb-ap-rotate -f

# Web server logs
journalctl -u ssb-webserver -f

# Sense HAT monitor logs
journalctl -u ssb-sensehat -f

# All SSB logs
journalctl -u "ssb-*" -f
```

### Restart Services

```bash
# Restart all SSB services
sudo systemctl restart ssb-ap-rotate ssb-webserver ssb-sensehat

# Restart just the AP daemon
sudo systemctl restart ssb-ap-rotate
```

## Sense HAT LED Status

| Color            | Meaning                         |
| ---------------- | ------------------------------- |
| 🟢 Green         | Internet connected, AP ready    |
| 🟡 Yellow/Orange | Credential rotation in progress |
| 🔴 Red           | No internet connectivity        |

### Joystick

- **Middle click**: Trigger immediate credential rotation (rate-limited to once per 30 seconds)

## Dual AP Mode

Dual AP mode allows you to run two independent WiFi access points simultaneously (wlan0 + wlan1), each with its own credentials and rotation schedule.

### Requirements

- USB WiFi dongle with AP mode support (nl80211 driver)
- The dongle will appear as `wlan1`

### Installation with Dual AP

```bash
# Install with dual AP mode enabled
sudo ./install.sh --dual

# Or, if wlan1 is detected, the installer will prompt you
sudo ./install.sh
```

### Manual Configuration

To enable dual AP mode after installation:

1. Edit `/etc/ssb-ap/config.json`:

```json
{
  "dual_ap_mode": true,
  "interfaces": {
    "wlan0": { "enabled": true, ... },
    "wlan1": { "enabled": true, ... }
  }
}
```

2. Install wlan1 dnsmasq config:

```bash
sudo cp /opt/ssb-wifi-kiosk/ap/dnsmasq-wlan1.conf /etc/dnsmasq.d/
```

3. Enable and start hostapd for wlan1:

```bash
sudo systemctl enable hostapd@wlan1
sudo systemctl restart ssb-ap-rotate
sudo systemctl restart dnsmasq
```

### Network Subnets

| Interface | Subnet      | Gateway IP  |
| --------- | ----------- | ----------- |
| wlan0     | 192.168.4.x | 192.168.4.1 |
| wlan1     | 192.168.5.x | 192.168.5.1 |

### Sense HAT Display in Dual Mode

In dual AP mode, the Sense HAT 8x8 LED display splits vertically:

```
+----+----+----+----+----+----+----+----+
| 0  | 0  | 0  | 0  | 1  | 1  | 1  | 1  |
+----+----+----+----+----+----+----+----+
|         |         |         |         |
|  wlan0  |         |  wlan1  |         |
|  status |         |  status |         |
+----+----+----+----+----+----+----+----+
```

- Left half (cols 0-3): wlan0 status with "0" label
- Right half (cols 4-7): wlan1 status with "1" label
- When an AP has less than 60 seconds until rotation, that half blinks slowly

### Web UI in Dual Mode

The kiosk web UI automatically shows both QR codes side-by-side when dual AP mode is active.

### Force Rotation (Dual Mode)

```bash
# Rotate wlan0
sudo touch /var/run/ssb-ap/trigger-rotate-wlan0

# Rotate wlan1
sudo touch /var/run/ssb-ap/trigger-rotate-wlan1

# Or press the Sense HAT joystick to rotate both
```

## Rotation Rules

Credentials rotate when EITHER condition is met:

1. **Time-based**: 5 minutes elapsed since last rotation
2. **Client-based**: 5 or more clients connected AND at least 2 minutes elapsed

Both thresholds are configurable in `/etc/ssb-ap/config.json`.

## Security

### Implemented Security Measures

- WPA2-PSK encryption with 16-character random passwords
- Credentials file readable only by root (`/var/run/ssb-ap/current.json`)
- No captive portal or login page (reduces attack surface)
- Automatic credential rotation limits exposure time
- `ssb-show` command requires sudo

### Recommendations

- Keep Raspberry Pi OS updated
- Use a strong password for the Pi user
- Consider firewall rules to limit management access
- Review rotation logs periodically

## Troubleshooting

### WiFi AP Not Starting

```bash
# Check hostapd status
sudo systemctl status hostapd

# Check for errors
journalctl -u hostapd -n 50

# Verify interface
iw dev wlan0 info

# Check if interface is blocked
rfkill list
sudo rfkill unblock wlan
```

### No Internet for Clients

```bash
# Verify ethernet connection
ip link show eth0
ping 8.8.8.8

# Check NAT rules
sudo iptables -t nat -L -n -v

# Re-run firewall setup
sudo /opt/ssb-wifi-kiosk/scripts/firewall.sh
```

### Kiosk Not Starting

```bash
# Check if X is running
ps aux | grep X

# Check kiosk service
sudo systemctl status ssb-kiosk

# View Xorg logs
cat /var/log/Xorg.0.log

# Test manually
sudo -u kiosk DISPLAY=:0 chromium-browser --kiosk http://localhost:8080
```

### QR Code Not Updating

```bash
# Check web server
curl http://localhost:8080/status

# Verify QR file exists
ls -la /opt/ssb-wifi-kiosk/web/static/qr.png

# Check AP daemon logs
journalctl -u ssb-ap-rotate -n 20
```

### Sense HAT Not Working

```bash
# Check if Sense HAT is detected
i2cdetect -y 1

# Test Sense HAT manually
python3 -c "from sense_hat import SenseHat; s = SenseHat(); s.clear(255,0,0)"

# Check service
sudo systemctl status ssb-sensehat
```

## File Locations

| Path                             | Description                     |
| -------------------------------- | ------------------------------- |
| `/opt/ssb-wifi-kiosk/`           | Application files               |
| `/etc/ssb-ap/config.json`        | Main configuration              |
| `/var/run/ssb-ap/current.json`   | Current credentials (root only) |
| `/var/run/ssb-ap/status.json`    | Daemon status                   |
| `/var/log/ssb-ap/rotations.json` | Rotation history                |
| `/etc/hostapd/hostapd.conf`      | Active hostapd config           |

## Hot-Swap Second WiFi Dongle (Future)

The system is designed to support seamless credential rotation using a second USB WiFi dongle:

### Concept

1. Plug in USB WiFi dongle (detected as `wlan1`)
2. Configure in `/etc/ssb-ap/config.json`:
   ```json
   {
     "backup_interface": "wlan1"
   }
   ```
3. Rotation process:
   - Generate new credentials
   - Bring up new AP on `wlan1`
   - Update QR code to show new network
   - Wait for clients to switch (30 seconds)
   - Bring down old AP on `wlan0`
   - Swap interfaces

### Requirements

- USB WiFi dongle with AP mode support
- Same chipset family recommended (nl80211 driver)
- Test with: `iw list | grep "AP"`

### Implementation Status

Currently planned for future release. The infrastructure is in place:

- `backup_interface` config option exists
- Rotation daemon designed for atomic switching
- QR update mechanism supports instant refresh

## Service Dependencies

```
ssb-firewall.service
    ↓
hostapd.service ←→ dnsmasq.service
    ↓
ssb-ap-rotate.service
    ↓
ssb-webserver.service    ssb-sensehat.service
    ↓
ssb-kiosk.service (graphical.target)
```

## Uninstall

```bash
# Stop and disable services
sudo systemctl stop ssb-ap-rotate ssb-webserver ssb-sensehat ssb-kiosk
sudo systemctl disable ssb-ap-rotate ssb-webserver ssb-sensehat ssb-kiosk ssb-firewall

# Remove service files
sudo rm /etc/systemd/system/ssb-*.service
sudo systemctl daemon-reload

# Remove application files
sudo rm -rf /opt/ssb-wifi-kiosk
sudo rm -rf /etc/ssb-ap
sudo rm -rf /var/run/ssb-ap
sudo rm -rf /var/log/ssb-ap
sudo rm /usr/local/bin/ssb-show

# Remove kiosk user (optional)
sudo userdel -r kiosk

# Remove autologin config
sudo rm /etc/systemd/system/getty@tty1.service.d/autologin.conf
```

## License

MIT License - Free for commercial and personal use.

## Support

For issues and feature requests, please open a GitHub issue.

---

Made with 🍔 for Super Smash Burger
