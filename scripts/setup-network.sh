#!/bin/bash
# =========================================================
#  SSB WiFi Kiosk - Network Interface Setup
#  
#  Configures WiFi interface(s) for AP mode:
#  - Assigns static IP
#  - Disables power management
#  - Stops conflicting services
#  
#  Supports both single and dual AP modes.
#  
#  Run with: sudo ./setup-network.sh
# =========================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║  SSB WiFi Kiosk - Network Setup                          ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must run as root${NC}"
    exit 1
fi

# Load config if available
CONFIG_FILE="/etc/ssb-ap/config.json"
DUAL_MODE=false
WLAN0_IP="192.168.4.1"
WLAN1_IP="192.168.5.1"

if [ -f "$CONFIG_FILE" ]; then
    DUAL_MODE=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('dual_ap_mode', False))" 2>/dev/null || echo "False")
    WLAN0_IP=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('interfaces', {}).get('wlan0', {}).get('ap_ip', '192.168.4.1'))" 2>/dev/null || echo "192.168.4.1")
    WLAN1_IP=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('interfaces', {}).get('wlan1', {}).get('ap_ip', '192.168.5.1'))" 2>/dev/null || echo "192.168.5.1")
fi

echo -e "${YELLOW}Dual AP Mode: ${DUAL_MODE}${NC}"
echo ""

# ===== Stop conflicting services =====
echo "Stopping conflicting services..."

# Stop wpa_supplicant
systemctl stop wpa_supplicant 2>/dev/null || true
killall wpa_supplicant 2>/dev/null || true

# Unblock WiFi if blocked
rfkill unblock wlan 2>/dev/null || true

# ===== Configure wlan0 =====
configure_interface() {
    local IFACE="$1"
    local IP="$2"
    
    echo -e "${YELLOW}Configuring ${IFACE} (${IP})...${NC}"
    
    # Check if interface exists
    if ! ip link show "$IFACE" &>/dev/null; then
        echo -e "${YELLOW}  Interface ${IFACE} not found, skipping${NC}"
        return 1
    fi
    
    # Tell NetworkManager to not manage this interface
    if command -v nmcli &> /dev/null; then
        nmcli device set "$IFACE" managed no 2>/dev/null || true
    fi
    
    # Bring down interface
    ip link set "$IFACE" down 2>/dev/null || true
    
    # Flush existing IP configuration
    ip addr flush dev "$IFACE" 2>/dev/null || true
    
    # Assign static IP
    ip addr add "${IP}/24" dev "$IFACE"
    
    # Bring up interface
    ip link set "$IFACE" up
    
    # Disable power management
    iw dev "$IFACE" set power_save off 2>/dev/null || true
    
    echo -e "${GREEN}  ${IFACE}: configured with IP ${IP}${NC}"
    return 0
}

# Configure wlan0
configure_interface "wlan0" "$WLAN0_IP"

# Configure wlan1 if dual mode
if [ "$DUAL_MODE" = "True" ]; then
    configure_interface "wlan1" "$WLAN1_IP" || true
fi

# ===== Configure dhcpcd (if used) =====
DHCPCD_CONF="/etc/dhcpcd.conf"
if [ -f "$DHCPCD_CONF" ]; then
    echo "Configuring dhcpcd..."
    
    # Backup
    cp ${DHCPCD_CONF} ${DHCPCD_CONF}.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
    
    # Add wlan0 config if not exists
    if ! grep -q "# SSB WiFi Kiosk - wlan0" ${DHCPCD_CONF} 2>/dev/null; then
        cat >> ${DHCPCD_CONF} << EOF

# SSB WiFi Kiosk - wlan0
interface wlan0
    static ip_address=${WLAN0_IP}/24
    nohook wpa_supplicant
EOF
        echo -e "${GREEN}  dhcpcd: wlan0 configured${NC}"
    fi
    
    # Add wlan1 config if dual mode
    if [ "$DUAL_MODE" = "True" ]; then
        if ! grep -q "# SSB WiFi Kiosk - wlan1" ${DHCPCD_CONF} 2>/dev/null; then
            cat >> ${DHCPCD_CONF} << EOF

# SSB WiFi Kiosk - wlan1
interface wlan1
    static ip_address=${WLAN1_IP}/24
    nohook wpa_supplicant
EOF
            echo -e "${GREEN}  dhcpcd: wlan1 configured${NC}"
        fi
    fi
fi

# ===== Verify configuration =====
echo ""
echo -e "${BLUE}Interface status:${NC}"
ip -4 addr show wlan0 2>/dev/null | grep -E "(inet|state)" || echo "  wlan0: not configured"

if [ "$DUAL_MODE" = "True" ]; then
    ip -4 addr show wlan1 2>/dev/null | grep -E "(inet|state)" || echo "  wlan1: not configured"
fi

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗"
echo "║  Network setup complete                                   ║"
echo "╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
