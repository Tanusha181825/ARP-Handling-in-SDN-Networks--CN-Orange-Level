from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import Topo
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI
import argparse
import subprocess
import time


class StarTopology(Topo):
    """
    Simple star topology:
    1 switch + 4 hosts
    """

    def build(self):
        h1 = self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        h2 = self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        h3 = self.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
        h4 = self.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')

        s1 = self.addSwitch('s1', protocols='OpenFlow13')

        self.addLink(h1, s1, bw=100, delay='1ms')
        self.addLink(h2, s1, bw=100, delay='1ms')
        self.addLink(h3, s1, bw=100, delay='1ms')
        self.addLink(h4, s1, bw=100, delay='1ms')


def scenario_1_pingall(net):
    info('\n' + '=' * 60 + '\n')
    info('SCENARIO 1: Full Mesh Ping in Star Topology\n')
    info('=' * 60 + '\n')

    loss = net.pingAll()

    if loss == 0.0:
        info('>>> PASS - All hosts can communicate successfully\n')
    else:
        info(f'>>> FAIL - Packet loss detected: {loss}%\n')

    info('=' * 60 + '\n')


def scenario_2_specific_ping(net):
    info('\n' + '=' * 60 + '\n')
    info('SCENARIO 2: Specific Host-to-Host Ping\n')
    info('=' * 60 + '\n')

    h1 = net.get('h1')
    result = h1.cmd('ping -c 4 10.0.0.3')
    info(result + '\n')

    info('=' * 60 + '\n')


def scenario_3_iperf(net):
    info('\n' + '=' * 60 + '\n')
    info('SCENARIO 3: Throughput Test using iperf\n')
    info('=' * 60 + '\n')

    h1 = net.get('h1')
    h3 = net.get('h3')

    h3.cmd('iperf -s -u &')
    time.sleep(1)
    result = h1.cmd('iperf -c 10.0.0.3 -u -t 5 -b 100M')
    info(result + '\n')
    h3.cmd('pkill -f "iperf -s -u"')

    info('=' * 60 + '\n')


def show_flow_table():
    info('\nFlow table on s1:\n')
    result = subprocess.run(
        ['ovs-ofctl', '-O', 'OpenFlow13', 'dump-fl
