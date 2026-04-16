#!/bin/bash
# =============================================================================
# test_scenarios.sh – Validation Tests for Star Topology
# =============================================================================
# Project : ARP Handling in SDN Networks (Star Topology)
# Usage   : chmod +x test_scenarios.sh && sudo ./test_scenarios.sh
# =============================================================================

set -e
PASS=0
FAIL=0

log()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
pass() { echo -e "\033[1;32m[PASS]\033[0m  $*"; ((PASS++)); }
fail() { echo -e "\033[1;31m[FAIL]\033[0m  $*"; ((FAIL++)); }
hr()   { echo "------------------------------------------------------------"; }

# -----------------------------------------------------------------------------
# SCENARIO 1: Controller Connectivity
# -----------------------------------------------------------------------------
hr
log "SCENARIO 1 — Ryu Controller Reachability"
hr

if nc -z 127.0.0.1 6633 2>/dev/null; then
    pass "Ryu controller is listening on port 6633"
else
    fail "Ryu controller NOT reachable on port 6633"
    log "Start it using: ryu-manager arp_controller.py"
fi

# -----------------------------------------------------------------------------
# SCENARIO 2: Ping All Hosts
# -----------------------------------------------------------------------------
hr
log "SCENARIO 2 — Full Mesh Ping Test"
hr

PING_RESULT=$(sudo python3 - <<EOF
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import Topo
from mininet.link import TCLink

class StarTopo(Topo):
    def build(self):
        h1=self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        h2=self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        h3=self.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
        h4=self.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')
        s1=self.addSwitch('s1', protocols='OpenFlow13')

        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s1)
        self.addLink(h4, s1)

net = Mininet(
    topo=StarTopo(),
    controller=None,
    switch=OVSSwitch,
    link=TCLink,
    autoStaticArp=False
)

c0 = net.addController(
    'c0',
    controller=RemoteController,
    ip='127.0.0.1',
    port=6633
)

net.start()
loss = net.pingAll()
net.stop()
print(loss)
EOF
)

if [[ "$PING_RESULT" == "0.0" ]]; then
    pass "All hosts reachable – 0% packet loss"
else
    fail "Ping test failed – packet loss detected"
fi

# -----------------------------------------------------------------------------
# SCENARIO 3: Flow Table Validation
# -----------------------------------------------------------------------------
hr
log "SCENARIO 3 — Flow Rule Check"
hr

FLOW_COUNT=$(sudo ovs-ofctl -O OpenFlow13 dump-flows s1 2>/dev/null | wc -l)

if [ "$FLOW_COUNT" -gt 1 ]; then
    pass "Flow rules successfully installed on s1"
else
    fail "No flow rules found on s1"
fi

# -----------------------------------------------------------------------------
# SCENARIO 4: ARP Table Check
# -----------------------------------------------------------------------------
hr
log "SCENARIO 4 — ARP Learning Check"
hr

ARP_RESULT=$(sudo mn --topo single,4 --controller remote --test pingall 2>/dev/null)

if echo "$ARP_RESULT" | grep -q "0% dropped"; then
    pass "ARP learning successful"
else
    fail "ARP table may not be populated correctly"
fi

# -----------------------------------------------------------------------------
# SCENARIO 5: Port Statistics
# -----------------------------------------------------------------------------
hr
log "SCENARIO 5 — Port Statistics"
hr

if sudo ovs-ofctl -O OpenFlow13 dump-ports s1 >/dev/null 2>&1; then
    pass "Port statistics readable from s1"
else
    fail "Could not read port statistics"
fi

# -----------------------------------------------------------------------------
# FINAL SUMMARY
# -----------------------------------------------------------------------------
hr
echo ""
echo "RESULTS: PASSED=$PASS   FAILED=$FAIL"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo -e "\033[1;32m✔ All tests passed successfully!\033[0m"
else
    echo -e "\033[1;31m✘ Some tests failed. Please check above output.\033[0m"
fi
hr
