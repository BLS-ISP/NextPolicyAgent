# -------------------------------------------------------
# Netzwerk-/Firewall-Regeln
# -------------------------------------------------------
# IP-basierte Zugriffskontrolle mit CIDR-Bereichen.
# Zeigt die Nutzung von net.cidr_contains und
# Port-Validierung.
#
# Auswertung (CLI):
#   npa eval -d examples/network-firewall/ \
#            -i examples/network-firewall/input.json \
#            "data.network.firewall.allow"
#
# Auswertung (API):
#   POST /v1/data/network/firewall
#   Body: {"input": {"source_ip": "10.0.1.50", "dest_ip": "10.0.2.100", "dest_port": 443, "protocol": "tcp"}}
# -------------------------------------------------------
package network.firewall

import future.keywords.if
import future.keywords.in

default allow = false

# Intern-zu-intern auf erlaubtem Port
allow if {
    net.cidr_contains("10.0.0.0/8", input.source_ip)
    net.cidr_contains("10.0.0.0/8", input.dest_ip)
    input.protocol == "tcp"
    input.dest_port in [22, 80, 443, 8080, 8443]
}

allow if {
    net.cidr_contains("10.0.0.0/8", input.source_ip)
    net.cidr_contains("10.0.0.0/8", input.dest_ip)
    input.protocol == "udp"
    input.dest_port in [53, 123]
}

# Auch 172.16.0.0/12 intern
allow if {
    net.cidr_contains("172.16.0.0/12", input.source_ip)
    net.cidr_contains("172.16.0.0/12", input.dest_ip)
    input.protocol == "tcp"
    input.dest_port in [22, 80, 443, 8080, 8443]
}

# Auch 192.168.0.0/16 intern
allow if {
    net.cidr_contains("192.168.0.0/16", input.source_ip)
    net.cidr_contains("192.168.0.0/16", input.dest_ip)
    input.protocol == "tcp"
    input.dest_port in [22, 80, 443, 8080, 8443]
}

# Beschreibung der Entscheidung
decision = "internal-traffic-allowed" if {
    allow
} else = "denied"
