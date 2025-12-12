#!/bin/bash
# =========================================================
#  SSB WiFi Kiosk - Firewall and NAT Configuration
#  
#  Configures iptables for:
#  - NAT (internet sharing from eth0 to wlan0/wlan1)
#  - Basic traffic forwarding
#  
#  Supports both single AP and dual AP modes.
#  
#  Run with: sudo ./firewall.sh
# =========================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║  SSB WiFi Kiosk - Configuring Firewall                   ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must run as root${NC}"
    exit 1
fi

# Load config if available
CONFIG_FILE="/etc/ssb-ap/config.json"
WAN_INTERFACE="eth0"
DUAL_MODE=false
WLAN0_ENABLED=true
WLAN1_ENABLED=false

if [ -f "$CONFIG_FILE" ]; then
    WAN_INTERFACE=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('wan_interface', 'eth0'))" 2>/dev/null || echo "eth0")
    DUAL_MODE=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('dual_ap_mode', False))" 2>/dev/null || echo "False")
    WLAN0_ENABLED=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('interfaces', {}).get('wlan0', {}).get('enabled', True))" 2>/dev/null || echo "True")
    WLAN1_ENABLED=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('interfaces', {}).get('wlan1', {}).get('enabled', False))" 2>/dev/null || echo "False")
fi

echo -e "${YELLOW}WAN Interface: ${WAN_INTERFACE}${NC}"
echo -e "${YELLOW}Dual AP Mode: ${DUAL_MODE}${NC}"
echo ""

# ===== Clean existing rules =====
echo "Cleaning existing iptables rules..."

iptables -F
iptables -t nat -F
iptables -t mangle -F
iptables -X 2>/dev/null || true

# ===== Set default policies =====
echo "Setting default policies..."

iptables -P INPUT ACCEPT
iptables -P FORWARD ACCEPT
iptables -P OUTPUT ACCEPT

# ===== Enable IP forwarding =====
echo "Enabling IP forwarding..."

echo 1 > /proc/sys/net/ipv4/ip_forward

# Make persistent
if ! grep -q "^net.ipv4.ip_forward=1" /etc/sysctl.conf 2>/dev/null; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
fi

# ===== NAT (Masquerade) =====
echo "Configuring NAT..."

# Masquerade traffic going out on WAN interface
iptables -t nat -A POSTROUTING -o ${WAN_INTERFACE} -j MASQUERADE

# ===== Allow established connections =====
echo "Allowing established connections..."

iptables -A FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT

# ===== Configure wlan0 =====
if [ "$WLAN0_ENABLED" = "True" ]; then
    echo "Configuring firewall for wlan0..."
    
    # Allow forwarding from wlan0 to WAN
    iptables -A FORWARD -i wlan0 -o ${WAN_INTERFACE} -j ACCEPT
    
    # Allow DHCP on wlan0
    iptables -A INPUT -i wlan0 -p udp --dport 67:68 -j ACCEPT
    
    # Allow DNS on wlan0
    iptables -A INPUT -i wlan0 -p udp --dport 53 -j ACCEPT
    iptables -A INPUT -i wlan0 -p tcp --dport 53 -j ACCEPT
    
    # Allow web server on wlan0
    iptables -A INPUT -i wlan0 -p tcp --dport 8080 -j ACCEPT
    
    echo -e "${GREEN}  wlan0: configured${NC}"
fi

# ===== Configure wlan1 (if dual mode) =====
if [ "$DUAL_MODE" = "True" ] && [ "$WLAN1_ENABLED" = "True" ]; then
    echo "Configuring firewall for wlan1..."
    
    # Allow forwarding from wlan1 to WAN
    iptables -A FORWARD -i wlan1 -o ${WAN_INTERFACE} -j ACCEPT
    
    # Allow DHCP on wlan1
    iptables -A INPUT -i wlan1 -p udp --dport 67:68 -j ACCEPT
    
    # Allow DNS on wlan1
    iptables -A INPUT -i wlan1 -p udp --dport 53 -j ACCEPT
    iptables -A INPUT -i wlan1 -p tcp --dport 53 -j ACCEPT
    
    # Allow web server on wlan1
    iptables -A INPUT -i wlan1 -p tcp --dport 8080 -j ACCEPT
    
    echo -e "${GREEN}  wlan1: configured${NC}"
fi

# ===== Save rules =====
echo "Saving iptables rules..."

mkdir -p /etc/iptables
iptables-save > /etc/iptables/rules.v4

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗"
echo "║  Firewall configured successfully                        ║"
echo "╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Summary:"
echo "  - NAT enabled on ${WAN_INTERFACE}"
if [ "$WLAN0_ENABLED" = "True" ]; then
    echo "  - wlan0: forwarding, DHCP, DNS, web server"
fi
if [ "$DUAL_MODE" = "True" ] && [ "$WLAN1_ENABLED" = "True" ]; then
    echo "  - wlan1: forwarding, DHCP, DNS, web server"
fi
echo ""
