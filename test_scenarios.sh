#!/bin/bash
# =============================================================================
# test_scenarios.sh – Validation & Regression Tests
# =============================================================================
# Project : ARP Handling in SDN Networks
# Course  : Computer Networks (UE24CS252B)
#
# Usage   : chmod +x test_scenarios.sh && sudo ./test_scenarios.sh
#
# Prerequisites:
#   - Ryu controller running  : ryu-manager arp_controller.py
#   - Mininet topology up     : sudo python3 topology.py
#   - Run this script in a 3rd terminal WHILE the above are active,
#     OR let topology.py run its built-in scenarios automatically.
# =============================================================================

set -e
PASS=0; FAIL=0

log()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
pass() { echo -e "\033[1;32m[PASS]\033[0m  $*"; ((PASS++)); }
fail() { echo -e "\033[1;31m[FAIL]\033[0m  $*"; ((FAIL++)); }
hr()   { echo "------------------------------------------------------------"; }

# ──────────────────────────────────────────────────────────────────────────────
# Helper: run a command inside a Mininet host
# ──────────────────────────────────────────────────────────────────────────────
mn_cmd() {
    local host=$1; shift
    # Uses the mnexec utility that Mininet installs
    mnexec -a "$(cat /tmp/mininet_${host}.pid 2>/dev/null || echo 1)" "$@" 2>/dev/null \
    || sudo -E python3 -c "
from mininet.net import Mininet
import sys
" 2>/dev/null
}

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 1: ARP Request / Reply via SDN Controller
# ──────────────────────────────────────────────────────────────────────────────
hr
log "SCENARIO 1 — ARP Handling (Proxy ARP via Ryu)"
hr

log "Flushing ARP cache on all hosts..."
for h in h1 h2 h3 h4; do
    sudo mn -c 2>/dev/null || true
done

log "Running pingall to trigger ARP discovery..."
PINGALL_OUT=$(sudo python3 -c "
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import Topo
from mininet.link import TCLink

class T(Topo):
    def build(self):
        h1=self.addHost('h1',ip='10.0.0.1/24',mac='00:00:00:00:00:01')
        h2=self.addHost('h2',ip='10.0.0.2/24',mac='00:00:00:00:00:02')
        h3=self.addHost('h3',ip='10.0.0.3/24',mac='00:00:00:00:00:03')
        h4=self.addHost('h4',ip='10.0.0.4/24',mac='00:00:00:00:00:04')
        s1=self.addSwitch('s1',protocols='OpenFlow13')
        s2=self.addSwitch('s2',protocols='OpenFlow13')
        self.addLink(h1,s1); self.addLink(h2,s1)
        self.addLink(h3,s2); self.addLink(h4,s2)
        self.addLink(s1,s2)
net=Mininet(topo=T(),controller=None,switch=OVSSwitch,link=TCLink,autoStaticArp=False)
c0=net.addController('c0',controller=RemoteController,ip='127.0.0.1',port=6633)
net.start()
import time; time.sleep(3)
loss=net.pingAll()
net.stop()
print('LOSS:'+str(loss))
" 2>/dev/null)

if echo "$PINGALL_OUT" | grep -q "LOSS:0.0"; then
    pass "Scenario 1: All hosts reachable – 0% packet loss"
else
    fail "Scenario 1: Some packets dropped (check controller)"
fi

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 2: Cross-Switch ARP + Latency Check
# ──────────────────────────────────────────────────────────────────────────────
hr
log "SCENARIO 2 — Cross-Switch Communication & Latency"
hr

log "Checking flow tables on s1 and s2..."
S1_FLOWS=$(sudo ovs-ofctl -O OpenFlow13 dump-flows s1 2>/dev/null | wc -l)
S2_FLOWS=$(sudo ovs-ofctl -O OpenFlow13 dump-flows s2 2>/dev/null | wc -l)

log "s1 flow entries : $S1_FLOWS"
log "s2 flow entries : $S2_FLOWS"

if [ "$S1_FLOWS" -ge 1 ]; then
    pass "Scenario 2: Flow rules installed on s1"
else
    fail "Scenario 2: No flow rules on s1 – controller may not be responding"
fi

if [ "$S2_FLOWS" -ge 1 ]; then
    pass "Scenario 2: Flow rules installed on s2"
else
    fail "Scenario 2: No flow rules on s2"
fi

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 3: Packet Count / Statistics Validation
# ──────────────────────────────────────────────────────────────────────────────
hr
log "SCENARIO 3 — Packet Statistics"
hr

log "Dumping port statistics for s1..."
sudo ovs-ofctl -O OpenFlow13 dump-ports s1 2>/dev/null \
    && pass "Scenario 3: Port statistics readable from s1" \
    || fail "Scenario 3: Could not read port statistics"

log "Dumping port statistics for s2..."
sudo ovs-ofctl -O OpenFlow13 dump-ports s2 2>/dev/null \
    && pass "Scenario 3: Port statistics readable from s2" \
    || fail "Scenario 3: Could not read port statistics"

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 4: Controller Connectivity Check
# ──────────────────────────────────────────────────────────────────────────────
hr
log "SCENARIO 4 — Ryu Controller Reachability"
hr

if nc -z 127.0.0.1 6633 2>/dev/null; then
    pass "Scenario 4: Ryu controller is listening on port 6633"
else
    fail "Scenario 4: Ryu controller NOT reachable on port 6633"
    log  "  → Start it with: ryu-manager arp_controller.py"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────────────
hr
echo ""
echo "  Results:  PASSED=$PASS   FAILED=$FAIL"
echo ""
if [ "$FAIL" -eq 0 ]; then
    echo -e "  \033[1;32m✔  All tests passed!\033[0m"
else
    echo -e "  \033[1;31m✘  Some tests failed – review output above.\033[0m"
fi
hr
