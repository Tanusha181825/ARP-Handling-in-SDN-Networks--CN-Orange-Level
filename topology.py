"""
Custom Mininet Topology – ARP Handling in SDN Networks
======================================================
Project: SDN Mininet Simulation – Orange Problem
Course:  Computer Networks (UE24CS252B)

Topology:
                    [Ryu Controller]
                          |
              +-----------+-----------+
              |                       |
           [s1]                    [s2]
          /    \                  /    \
        h1      h2              h3      h4
   10.0.0.1  10.0.0.2      10.0.0.3  10.0.0.4

  s1 ←──── trunk link ────→ s2

Usage:
    sudo python3 topology.py
    # or with external controller:
    sudo python3 topology.py --controller remote
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch, Host
from mininet.topo import Topo
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI
import argparse


# ──────────────────────────────────────────────────────────────────────────────
# Topology Definition
# ──────────────────────────────────────────────────────────────────────────────

class ARPHandlingTopo(Topo):
    """
    Two-switch topology with 4 hosts (2 per switch).
    Both switches connect to the same Ryu controller.

    Link parameters:
      host-switch  : 100 Mbps, 1 ms delay
      switch-switch: 1 Gbps,   2 ms delay
    """

    def build(self):
        # ── Hosts ──────────────────────────────────────────────────────────────
        h1 = self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        h2 = self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        h3 = self.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
        h4 = self.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')

        # ── Switches ───────────────────────────────────────────────────────────
        s1 = self.addSwitch('s1', protocols='OpenFlow13')
        s2 = self.addSwitch('s2', protocols='OpenFlow13')

        # ── Host → Switch links  (100 Mbps, 1 ms) ─────────────────────────────
        self.addLink(h1, s1, bw=100, delay='1ms')
        self.addLink(h2, s1, bw=100, delay='1ms')
        self.addLink(h3, s2, bw=100, delay='1ms')
        self.addLink(h4, s2, bw=100, delay='1ms')

        # ── Switch ↔ Switch trunk  (1 Gbps, 2 ms) ─────────────────────────────
        self.addLink(s1, s2, bw=1000, delay='2ms')


# ──────────────────────────────────────────────────────────────────────────────
# Network Runner
# ──────────────────────────────────────────────────────────────────────────────

def run_network(controller_ip='127.0.0.1', controller_port=6633):
    """
    Build and start the Mininet network with the remote Ryu controller,
    run validation tests, then open the interactive CLI.
    """
    setLogLevel('info')

    topo = ARPHandlingTopo()
    net  = Mininet(
        topo=topo,
        controller=None,          # we add it manually below
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=False,        # MACs are set explicitly in the topology
        autoStaticArp=False       # disable static ARP – let SDN handle it
    )

    # Attach external Ryu controller
    c0 = net.addController(
        'c0',
        controller=RemoteController,
        ip=controller_ip,
        port=controller_port
    )

    info('\n*** Starting network\n')
    net.start()

    # ── Configure OVS switches to use OpenFlow 1.3 ────────────────────────────
    for sw in net.switches:
        sw.cmd(f'ovs-vsctl set bridge {sw.name} protocols=OpenFlow13')

    info('\n*** Waiting for switches to connect to controller...\n')
    import time; time.sleep(3)

    # ── Run Scenario 1: Basic ARP + Ping ──────────────────────────────────────
    _scenario_1_basic_ping(net)

    # ── Run Scenario 2: Cross-switch ARP + iperf ──────────────────────────────
    _scenario_2_cross_switch(net)

    # ── Open interactive CLI ──────────────────────────────────────────────────
    info('\n*** Opening Mininet CLI  (type "exit" to quit)\n')
    CLI(net)

    info('\n*** Stopping network\n')
    net.stop()


# ──────────────────────────────────────────────────────────────────────────────
# Test Scenario 1 – ARP Discovery + Full Mesh Ping
# ──────────────────────────────────────────────────────────────────────────────

def _scenario_1_basic_ping(net):
    """
    Scenario 1: ARP Discovery & Ping Reachability
    -----------------------------------------------
    • Triggers ARP for every host pair.
    • Validates 0% packet loss using pingAll.
    Expected: all 4 hosts can reach each other.
    """
    info('\n' + '='*60 + '\n')
    info('SCENARIO 1: ARP Discovery + Full Mesh Ping\n')
    info('='*60 + '\n')

    loss = net.pingAll()

    if loss == 0.0:
        info('>>> PASS  – 0% packet loss, all hosts reachable\n')
    else:
        info(f'>>> FAIL  – {loss:.1f}% packet loss detected\n')

    info('='*60 + '\n')


# ──────────────────────────────────────────────────────────────────────────────
# Test Scenario 2 – Cross-Switch ARP + iperf Throughput
# ──────────────────────────────────────────────────────────────────────────────

def _scenario_2_cross_switch(net):
    """
    Scenario 2: Cross-Switch Traffic & Throughput Measurement
    -----------------------------------------------------------
    • h1 (s1) ↔ h3 (s2) – tests ARP + forwarding across the trunk.
    • iperf UDP test for throughput measurement.
    Expected: ARP replies proxied by controller, data flows at ~100 Mbps.
    """
    info('\n' + '='*60 + '\n')
    info('SCENARIO 2: Cross-Switch ARP + iperf Throughput\n')
    info('='*60 + '\n')

    h1 = net.get('h1')
    h3 = net.get('h3')

    # Ping h1 → h3  (triggers ARP)
    info('Ping h1 → h3 (cross-switch ARP test):\n')
    result = h1.cmd('ping -c 4 10.0.0.3')
    info(result + '\n')

    # iperf throughput h1 → h3
    info('iperf h1 ↔ h3 (UDP, 5 seconds):\n')
    h3.cmd('iperf -s -u &')           # start server on h3
    import time; time.sleep(1)
    result = h1.cmd('iperf -c 10.0.0.3 -u -t 5 -b 100M')
    info(result + '\n')
    h3.cmd('kill %iperf 2>/dev/null')

    # Show flow tables
    info('Flow table on s1:\n')
    import subprocess
    result = subprocess.run(['ovs-ofctl', '-O', 'OpenFlow13', 'dump-flows', 's1'],
                            capture_output=True, text=True)
    info(result.stdout + '\n')

    info('Flow table on s2:\n')
    result = subprocess.run(['ovs-ofctl', '-O', 'OpenFlow13', 'dump-flows', 's2'],
                            capture_output=True, text=True)
    info(result.stdout + '\n')

    info('='*60 + '\n')


# ──────────────────────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ARP SDN Topology')
    parser.add_argument('--controller', default='127.0.0.1',
                        help='Ryu controller IP (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=6633,
                        help='Controller port (default: 6633)')
    args = parser.parse_args()

    run_network(controller_ip=args.controller, controller_port=args.port)
