#!/bin/bash
# Open required ports for OMNI BRAIN V2
# Run as root on VPS

echo "Opening firewall ports..."

# Open required ports
ufw allow 3000/tcp comment "OMNI Pipeline API"
ufw allow 8080/tcp comment "OMNI Status Page"
ufw allow 8089/tcp comment "OMNI Status Dashboard"
ufw allow 3001/tcp comment "OMNI WebSocket"

# Reload firewall
ufw reload

# Show status
ufw status

echo "Ports opened successfully"
