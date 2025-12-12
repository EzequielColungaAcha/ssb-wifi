#!/bin/bash
# =========================================================
#  SSB WiFi Kiosk - Installer
#  
#  Installs and configures the rotating WiFi AP kiosk system
#  on Raspberry Pi 3 with Raspbian Lite (Trixie)
#  
#  Supports single AP (wlan0) and dual AP (wlan0 + wlan1) modes
#  
#  Usage: sudo ./install.sh
#         sudo ./install.sh --dual    # Enable dual AP mode
# =========================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Installation directory
INSTALL_DIR="/opt/ssb-wifi-kiosk"
CONFIG_DIR="/etc/ssb-ap"
RUN_DIR="/var/run/ssb-ap"
LOG_DIR="/var/log/ssb-ap"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Kiosk user
KIOSK_USER="kiosk"

# Check for dual AP mode flag
DUAL_AP_MODE=false
if [ "$1" = "--dual" ]; then
    DUAL_AP_MODE=true
fi

echo -e "${GREEN}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║   📶  SSB WiFi Kiosk - Installer                                 ║
║       Rotating WiFi AP with QR Display                           ║
║                                                                   ║
║   For Raspberry Pi 3 + Sense HAT                                 ║
║   Supports Single and Dual AP Modes                              ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# ===== VERIFICATION =====
echo -e "${CYAN}[1/11] Verifying requirements...${NC}"

# Check root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Error: This script must run as root${NC}"
    echo "   Usage: sudo ./install.sh"
    echo "   For dual AP: sudo ./install.sh --dual"
    exit 1
fi

# Check if Raspberry Pi
if [ -f /proc/device-tree/model ]; then
    MODEL=$(cat /proc/device-tree/model)
    echo -e "${GREEN}✅ Device: ${MODEL}${NC}"
else
    echo -e "${YELLOW}⚠️  Not detected as Raspberry Pi, continuing anyway...${NC}"
fi

# Check for wlan interfaces
echo -n "   Checking WiFi interfaces... "
WLAN0_AVAILABLE=false
WLAN1_AVAILABLE=false

if ip link show wlan0 &>/dev/null; then
    WLAN0_AVAILABLE=true
    echo -n "wlan0 "
fi

if ip link show wlan1 &>/dev/null; then
    WLAN1_AVAILABLE=true
    echo -n "wlan1 "
fi

if [ "$WLAN0_AVAILABLE" = true ]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo -e "${RED}❌ wlan0 not found. WiFi interface required.${NC}"
    exit 1
fi

# Auto-enable dual mode if wlan1 is present
if [ "$WLAN1_AVAILABLE" = true ] && [ "$DUAL_AP_MODE" = false ]; then
    echo -e "${YELLOW}   wlan1 detected. Enable dual AP mode? [y/N]: ${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        DUAL_AP_MODE=true
    fi
fi

if [ "$DUAL_AP_MODE" = true ]; then
    echo -e "${GREEN}   Dual AP mode: ENABLED${NC}"
else
    echo -e "${BLUE}   Single AP mode (wlan0 only)${NC}"
fi

# Check internet
echo -n "   Checking internet connection... "
if ping -c 1 8.8.8.8 &> /dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo -e "${YELLOW}⚠️  No internet. Package installation may fail.${NC}"
fi

# ===== SYSTEM UPDATE =====
echo ""
echo -e "${CYAN}[2/11] Updating system packages...${NC}"

apt-get update -qq

# ===== INSTALL DEPENDENCIES =====
echo ""
echo -e "${CYAN}[3/11] Installing dependencies...${NC}"

# Core packages
apt-get install -y -qq \
    hostapd \
    dnsmasq \
    iptables \
    iptables-persistent \
    python3 \
    python3-flask \
    python3-pip \
    python3-pil \
    net-tools \
    wireless-tools \
    iw \
    rfkill

# Install qrcode via apt if available, otherwise pip
if apt-get install -y -qq python3-qrcode 2>/dev/null; then
    echo "  - python3-qrcode installed via apt"
else
    pip3 install qrcode[pil] --break-system-packages 2>/dev/null || pip3 install qrcode[pil]
    echo "  - qrcode installed via pip"
fi

# Sense HAT (may not be available on all systems)
if apt-get install -y -qq sense-hat 2>/dev/null; then
    echo "  - sense-hat installed"
else
    echo -e "${YELLOW}  - sense-hat not available (optional)${NC}"
fi

# X11 and kiosk packages
apt-get install -y -qq \
    xserver-xorg \
    x11-xserver-utils \
    xinit \
    chromium \
    unclutter \
    fonts-dejavu

echo -e "${GREEN}✅ Dependencies installed${NC}"

# ===== CREATE KIOSK USER =====
echo ""
echo -e "${CYAN}[4/11] Creating kiosk user...${NC}"

if id "$KIOSK_USER" &>/dev/null; then
    echo "  - User '$KIOSK_USER' already exists"
else
    useradd -m -s /bin/bash "$KIOSK_USER"
    echo "  - User '$KIOSK_USER' created"
fi

# Add to necessary groups
usermod -aG video,audio,input,tty "$KIOSK_USER"

# ===== CREATE DIRECTORIES =====
echo ""
echo -e "${CYAN}[5/11] Creating directories...${NC}"

mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$RUN_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$INSTALL_DIR/web/static/assets"

# Set permissions
chmod 755 "$INSTALL_DIR"
chmod 700 "$CONFIG_DIR"
chmod 700 "$RUN_DIR"
chmod 700 "$LOG_DIR"

echo "  - $INSTALL_DIR"
echo "  - $CONFIG_DIR"
echo "  - $RUN_DIR"
echo "  - $LOG_DIR"

# ===== COPY FILES =====
echo ""
echo -e "${CYAN}[6/11] Installing application files...${NC}"

# Copy all application files
cp -r "$SCRIPT_DIR/ap" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/qr" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/web" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/sensehat" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/scripts" "$INSTALL_DIR/"

# Copy config and update dual_ap_mode setting
cp "$SCRIPT_DIR/config/ssb-ap.json" "$CONFIG_DIR/config.json"

if [ "$DUAL_AP_MODE" = true ]; then
    # Enable dual AP mode in config
    python3 -c "
import json
with open('$CONFIG_DIR/config.json', 'r') as f:
    config = json.load(f)
config['dual_ap_mode'] = True
config['interfaces']['wlan1']['enabled'] = True
with open('$CONFIG_DIR/config.json', 'w') as f:
    json.dump(config, f, indent=2)
"
    echo "  - Dual AP mode enabled in config"
fi

chmod 600 "$CONFIG_DIR/config.json"

# Make scripts executable
chmod +x "$INSTALL_DIR/scripts/"*.sh
chmod +x "$INSTALL_DIR/scripts/ssb-show"
chmod +x "$INSTALL_DIR/ap/ap_rotate.py"
chmod +x "$INSTALL_DIR/qr/make_qr.py"
chmod +x "$INSTALL_DIR/web/server.py"
chmod +x "$INSTALL_DIR/sensehat/sensehat_monitor.py"

# Install ssb-show command
ln -sf "$INSTALL_DIR/scripts/ssb-show" /usr/local/bin/ssb-show

echo -e "${GREEN}✅ Files installed${NC}"

# ===== CONFIGURE HOSTAPD =====
echo ""
echo -e "${CYAN}[7/11] Configuring hostapd and dnsmasq...${NC}"

# Stop services
systemctl stop hostapd 2>/dev/null || true
systemctl stop "hostapd@wlan0" 2>/dev/null || true
systemctl stop "hostapd@wlan1" 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true

# Backup existing configs
BACKUP_DIR="/etc/backup_ssb_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
[ -f /etc/hostapd/hostapd.conf ] && cp /etc/hostapd/hostapd.conf "$BACKUP_DIR/"
[ -f /etc/dnsmasq.conf ] && cp /etc/dnsmasq.conf "$BACKUP_DIR/"
echo -e "${BLUE}  - Backups saved to $BACKUP_DIR${NC}"

# Create hostapd directory
mkdir -p /etc/hostapd

# Install hostapd template service for dual mode
cp "$SCRIPT_DIR/systemd/hostapd@.service" /etc/systemd/system/

# Install dnsmasq configs
mkdir -p /etc/dnsmasq.d

if [ "$DUAL_AP_MODE" = true ]; then
    # Dual mode: use per-interface configs
    cp "$INSTALL_DIR/ap/dnsmasq-wlan0.conf" /etc/dnsmasq.d/ssb-wlan0.conf
    cp "$INSTALL_DIR/ap/dnsmasq-wlan1.conf" /etc/dnsmasq.d/ssb-wlan1.conf
    echo "  - Per-interface dnsmasq configs installed"
else
    # Single mode: use legacy config
    cp "$INSTALL_DIR/ap/dnsmasq.conf" /etc/dnsmasq.d/ssb-wifi-kiosk.conf
    echo "  - Single dnsmasq config installed"
fi

# Unmask hostapd (it's often masked by default)
systemctl unmask hostapd

# Disable default hostapd in dual mode (we use template units)
if [ "$DUAL_AP_MODE" = true ]; then
    systemctl disable hostapd 2>/dev/null || true
fi

echo -e "${GREEN}✅ Network services configured${NC}"

# ===== INSTALL SYSTEMD SERVICES =====
echo ""
echo -e "${CYAN}[8/11] Installing systemd services...${NC}"

# Copy service files
for svc in "$SCRIPT_DIR/systemd/"*.service; do
    cp "$svc" /etc/systemd/system/
done

# Reload systemd
systemctl daemon-reload

# Enable services
systemctl enable ssb-firewall
systemctl enable ssb-ap-rotate
systemctl enable ssb-webserver
systemctl enable ssb-sensehat
systemctl enable dnsmasq

if [ "$DUAL_AP_MODE" = true ]; then
    # Enable hostapd template units
    systemctl enable "hostapd@wlan0"
    systemctl enable "hostapd@wlan1"
    echo "  - hostapd@wlan0"
    echo "  - hostapd@wlan1"
else
    systemctl enable hostapd
    # Also configure for legacy mode
    echo 'DAEMON_CONF="/etc/hostapd/hostapd-wlan0.conf"' > /etc/default/hostapd
    echo "  - hostapd"
fi

echo "  - ssb-firewall"
echo "  - ssb-ap-rotate"
echo "  - ssb-webserver"
echo "  - ssb-sensehat"
echo "  - dnsmasq"

echo -e "${GREEN}✅ Services installed and enabled${NC}"

# ===== CONFIGURE NETWORK INTERFACES =====
echo ""
echo -e "${CYAN}[9/11] Configuring network interfaces...${NC}"

# Configure wlan0
"$INSTALL_DIR/scripts/setup-network.sh"

# Configure wlan1 if dual mode
if [ "$DUAL_AP_MODE" = true ] && [ "$WLAN1_AVAILABLE" = true ]; then
    echo "  Configuring wlan1..."
    
    # Set static IP for wlan1
    ip addr flush dev wlan1 2>/dev/null || true
    ip addr add 192.168.5.1/24 dev wlan1 2>/dev/null || true
    ip link set wlan1 up 2>/dev/null || true
    
    # Disable power saving on wlan1
    iw dev wlan1 set power_save off 2>/dev/null || true
    
    echo -e "${GREEN}  - wlan1 configured (192.168.5.1)${NC}"
fi

# Configure firewall (now handles both interfaces)
"$INSTALL_DIR/scripts/firewall.sh"

echo -e "${GREEN}✅ Network configured${NC}"

# ===== CONFIGURE KIOSK AUTOLOGIN =====
echo ""
echo -e "${CYAN}[10/11] Configuring kiosk autologin...${NC}"

# Create autologin config for getty
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $KIOSK_USER --noclear %I \$TERM
EOF

# Create .bash_profile for kiosk user to start X
KIOSK_HOME="/home/$KIOSK_USER"
cat > "$KIOSK_HOME/.bash_profile" << 'EOF'
# SSB WiFi Kiosk - Auto-start X on login
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    exec startx -- -nocursor
fi
EOF
chown "$KIOSK_USER:$KIOSK_USER" "$KIOSK_HOME/.bash_profile"

# Create .xinitrc for kiosk user
cat > "$KIOSK_HOME/.xinitrc" << 'EOF'
#!/bin/bash
# SSB WiFi Kiosk - X Session

# Log for debugging
exec > /tmp/kiosk-xinit.log 2>&1
echo "Starting X session at $(date)"

# Disable screen saver and power management
xset s off
xset -dpms
xset s noblank

# Hide cursor
unclutter -idle 0.1 -root &

# Wait for web server to be fully ready
echo "Waiting for web server..."
for i in {1..30}; do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        echo "Web server ready after $i seconds"
        break
    fi
    sleep 1
done

# Start Chromium in kiosk mode
echo "Starting Chromium..."
exec chromium \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-restore-session-state \
    --disable-features=TranslateUI \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --incognito \
    --check-for-update-interval=31536000 \
    --disable-component-update \
    --disable-background-networking \
    --disable-sync \
    --no-first-run \
    --start-fullscreen \
    --window-position=0,0 \
    http://localhost:8080
EOF
chmod +x "$KIOSK_HOME/.xinitrc"
chown "$KIOSK_USER:$KIOSK_USER" "$KIOSK_HOME/.xinitrc"

echo -e "${GREEN}✅ Kiosk autologin configured${NC}"

# ===== START SERVICES =====
echo ""
echo -e "${CYAN}[11/11] Starting services...${NC}"

# Start services
systemctl start ssb-firewall

if [ "$DUAL_AP_MODE" = true ]; then
    systemctl start "hostapd@wlan0" || echo -e "${YELLOW}  hostapd@wlan0 will start after first rotation${NC}"
    systemctl start "hostapd@wlan1" || echo -e "${YELLOW}  hostapd@wlan1 will start after first rotation${NC}"
else
    systemctl start hostapd || echo -e "${YELLOW}  hostapd will start after first rotation${NC}"
fi

sleep 2
systemctl start dnsmasq
sleep 2
systemctl start ssb-ap-rotate
sleep 3
systemctl start ssb-webserver
systemctl start ssb-sensehat

echo -e "${GREEN}✅ Services started${NC}"

# ===== VERIFICATION =====
echo ""
echo -e "${CYAN}Verifying installation...${NC}"

check_service() {
    if systemctl is-active --quiet "$1"; then
        echo -e "  $1: ${GREEN}✅ Running${NC}"
        return 0
    else
        echo -e "  $1: ${YELLOW}⚠️  Starting...${NC}"
        return 1
    fi
}

echo ""
if [ "$DUAL_AP_MODE" = true ]; then
    check_service "hostapd@wlan0"
    check_service "hostapd@wlan1"
else
    check_service hostapd
fi
check_service dnsmasq
check_service ssb-ap-rotate
check_service ssb-webserver
check_service ssb-sensehat

# ===== COMPLETE =====
echo ""
echo -e "${GREEN}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║   🎉  INSTALLATION COMPLETE!                                     ║
║                                                                   ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║   📶 WiFi AP is running with rotating credentials               ║
║   🖥️  Kiosk UI: http://localhost:8080                            ║
║   🔑 Show credentials: sudo ssb-show                            ║
║                                                                   ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║   🔧 USEFUL COMMANDS                                             ║
║                                                                   ║
║   View credentials:   sudo ssb-show                              ║
║   View logs:          journalctl -u ssb-ap-rotate -f             ║
║   Restart AP:         sudo systemctl restart ssb-ap-rotate       ║
EOF

if [ "$DUAL_AP_MODE" = true ]; then
cat << "EOF"
║   Force rotation:                                                ║
║     wlan0: sudo touch /var/run/ssb-ap/trigger-rotate-wlan0      ║
║     wlan1: sudo touch /var/run/ssb-ap/trigger-rotate-wlan1      ║
EOF
else
cat << "EOF"
║   Force rotation:     sudo touch /var/run/ssb-ap/trigger-rotate-wlan0 ║
EOF
fi

cat << "EOF"
║                                                                   ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║   📁 CONFIGURATION                                               ║
║                                                                   ║
║   Main config:        /etc/ssb-ap/config.json                    ║
║   Kiosk content:      /opt/ssb-wifi-kiosk/web/static/config.js   ║
║   Rotation logs:      /var/log/ssb-ap/rotations.json             ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

if [ "$DUAL_AP_MODE" = true ]; then
    echo -e "${CYAN}Dual AP Mode: ENABLED${NC}"
    echo -e "  wlan0: 192.168.4.x subnet"
    echo -e "  wlan1: 192.168.5.x subnet"
    echo ""
fi

# Show current credentials
echo -e "${YELLOW}Current WiFi Credentials:${NC}"
sleep 2  # Give time for first rotation
if [ -f "/var/run/ssb-ap/current-wlan0.json" ]; then
    ssb-show 2>/dev/null || echo "Run 'sudo ssb-show' to see credentials"
elif [ -f "/var/run/ssb-ap/current.json" ]; then
    ssb-show 2>/dev/null || echo "Run 'sudo ssb-show' to see credentials"
else
    echo "  Credentials will be generated shortly..."
fi

echo ""
echo -e "${BLUE}💡 Reboot recommended to verify autologin: sudo reboot${NC}"
echo ""
