"""
ARP Handling in SDN Networks - Ryu Controller
==============================================
Project: SDN Mininet Simulation – Orange Problem
Course:  Computer Networks (UE24CS252B)

Description:
    This Ryu controller implements:
      1. ARP Interception     – catches all ARP packets via packet_in
      2. Proxy ARP            – replies directly on behalf of known hosts
      3. Host Discovery       – builds an IP→MAC→Port table dynamically
      4. Unicast Flow Install – installs L2 forwarding rules once hosts are known
      5. Flood Fallback       – floods ARP requests for yet-unknown hosts
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4
from ryu.lib.packet import ether_types
import logging

# ──────────────────────────────────────────────────────────────────────────────
# Controller App
# ──────────────────────────────────────────────────────────────────────────────

class ARPHandlerController(app_manager.RyuApp):
    """
    SDN Controller with Proxy-ARP and Learning-Switch capabilities.

    Data structures maintained per switch (dpid):
      mac_to_port  : { dpid -> { mac_addr -> out_port } }
      ip_to_mac    : { dpid -> { ip_addr  -> mac_addr } }
      ip_to_port   : { dpid -> { ip_addr  -> out_port } }
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ARPHandlerController, self).__init__(*args, **kwargs)

        # Per-switch ARP / MAC tables
        self.mac_to_port = {}   # dpid → { mac → port }
        self.ip_to_mac   = {}   # dpid → { ip  → mac  }
        self.ip_to_port  = {}   # dpid → { ip  → port }

        self.logger.setLevel(logging.DEBUG)
        self.logger.info("=== ARP Handler Controller started ===")

    # ──────────────────────────────────────────────────────────────────────────
    # Switch Handshake – install a table-miss flow entry
    # ──────────────────────────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        On switch connect: install a low-priority table-miss rule so that
        unmatched packets are sent to the controller via packet_in.
        """
        datapath = ev.msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser
        dpid     = datapath.id

        # Initialise per-switch tables
        self.mac_to_port.setdefault(dpid, {})
        self.ip_to_mac.setdefault(dpid, {})
        self.ip_to_port.setdefault(dpid, {})

        # Table-miss: match everything, lowest priority, send to controller
        match  = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, priority=0, match=match, actions=actions)
        self.logger.info("[SWITCH %016x] Connected – table-miss rule installed", dpid)

    # ──────────────────────────────────────────────────────────────────────────
    # Packet-In Handler
    # ──────────────────────────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
        Central handler for all packets sent to the controller.
        Dispatches ARP packets to _handle_arp() and IPv4 to _handle_ipv4().
        """
        msg      = ev.msg
        datapath = msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser
        in_port  = msg.match['in_port']
        dpid     = datapath.id

        pkt      = packet.Packet(msg.data)
        eth_pkt  = pkt.get_protocol(ethernet.ethernet)

        if eth_pkt is None:
            return

        eth_type = eth_pkt.ethertype
        src_mac  = eth_pkt.src
        dst_mac  = eth_pkt.dst

        # ── Learn MAC → port mapping ──────────────────────────────────────────
        self.mac_to_port[dpid][src_mac] = in_port
        self.logger.debug("[SWITCH %016x] Learned  MAC %s → port %s",
                          dpid, src_mac, in_port)

        # ── Dispatch by EtherType ─────────────────────────────────────────────
        arp_pkt  = pkt.get_protocol(arp.arp)
        ipv4_pkt = pkt.get_protocol(ipv4.ipv4)

        if arp_pkt:
            self._handle_arp(datapath, in_port, eth_pkt, arp_pkt, msg)
        elif ipv4_pkt:
            self._handle_ipv4(datapath, in_port, eth_pkt, ipv4_pkt, msg)
        else:
            # Unknown type – flood
            self._flood(datapath, msg, in_port)

    # ──────────────────────────────────────────────────────────────────────────
    # ARP Handler  (core requirement: intercept + proxy-reply + discovery)
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_arp(self, datapath, in_port, eth_pkt, arp_pkt, msg):
        """
        Handle an ARP packet:
          • Learn the sender's IP→MAC→port mapping.
          • If it is an ARP REQUEST and we know the target IP, send a
            Proxy-ARP reply directly from the controller (no flood needed).
          • If we do NOT know the target, flood the request out all ports.
        """
        dpid    = datapath.id
        src_ip  = arp_pkt.src_ip
        src_mac = arp_pkt.src_mac
        dst_ip  = arp_pkt.dst_ip

        # ── Learn sender ──────────────────────────────────────────────────────
        self.ip_to_mac[dpid][src_ip]  = src_mac
        self.ip_to_port[dpid][src_ip] = in_port
        self.logger.info("[ARP]   Learned  IP %-15s → MAC %s (port %s) on switch %016x",
                         src_ip, src_mac, in_port, dpid)

        if arp_pkt.opcode == arp.ARP_REQUEST:
            self.logger.info("[ARP]   REQUEST  Who has %s? (from %s / %s)",
                             dst_ip, src_ip, src_mac)

            if dst_ip in self.ip_to_mac[dpid]:
                # ── Proxy-ARP reply ───────────────────────────────────────────
                target_mac = self.ip_to_mac[dpid][dst_ip]
                self.logger.info("[ARP]   PROXY REPLY  %s is at %s  (sent to %s)",
                                 dst_ip, target_mac, src_ip)
                self._send_arp_reply(datapath, in_port,
                                     target_mac, dst_ip,
                                     src_mac, src_ip)
            else:
                # ── Unknown target – flood ────────────────────────────────────
                self.logger.info("[ARP]   Unknown target %s – flooding", dst_ip)
                self._flood(datapath, msg, in_port)

        elif arp_pkt.opcode == arp.ARP_REPLY:
            self.logger.info("[ARP]   REPLY    %s is at %s", src_ip, src_mac)
            # Forward the reply to the original requester if port is known
            if arp_pkt.dst_ip in self.ip_to_port[dpid]:
                out_port = self.ip_to_port[dpid][arp_pkt.dst_ip]
                self._send_packet_out(datapath, msg, out_port)
            else:
                self._flood(datapath, msg, in_port)

    # ──────────────────────────────────────────────────────────────────────────
    # IPv4 Handler  (install forwarding flow rules)
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_ipv4(self, datapath, in_port, eth_pkt, ipv4_pkt, msg):
        """
        Handle an IPv4 packet:
          • Determine output port from mac_to_port table.
          • Install a flow rule so future packets bypass the controller.
          • Forward the current packet.
        """
        dpid    = datapath.id
        parser  = datapath.ofproto_parser
        ofproto = datapath.ofproto
        src_mac = eth_pkt.src
        dst_mac = eth_pkt.dst

        if dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Install flow rule for this src→dst MAC pair (avoid repeated packet_in)
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port,
                                    eth_dst=dst_mac,
                                    eth_src=src_mac)
            self._add_flow(datapath,
                           priority=10,
                           match=match,
                           actions=actions,
                           idle_timeout=30,
                           hard_timeout=120)
            self.logger.info("[FLOW]  Installed  %s → %s out port %s on switch %016x",
                             src_mac, dst_mac, out_port, dpid)

        self._send_packet_out(datapath, msg, out_port)

    # ──────────────────────────────────────────────────────────────────────────
    # Helper – build & send a crafted ARP reply
    # ──────────────────────────────────────────────────────────────────────────

    def _send_arp_reply(self, datapath, out_port,
                        src_mac, src_ip,
                        dst_mac, dst_ip):
        """
        Craft an ARP REPLY and send it out the specified port.
        Parameters represent the *reply* perspective:
          src = the host being queried (we answer on its behalf)
          dst = the original requester
        """
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser

        # Build Ethernet + ARP reply
        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(
            ethertype=ether_types.ETH_TYPE_ARP,
            dst=dst_mac,
            src=src_mac))
        pkt.add_protocol(arp.arp(
            opcode=arp.ARP_REPLY,
            src_mac=src_mac,
            src_ip=src_ip,
            dst_mac=dst_mac,
            dst_ip=dst_ip))
        pkt.serialize()

        actions = [parser.OFPActionOutput(out_port)]
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=ofproto.OFPP_CONTROLLER,
            actions=actions,
            data=pkt.data)
        datapath.send_msg(out)

    # ──────────────────────────────────────────────────────────────────────────
    # Helper – flood a packet (excluding in_port)
    # ──────────────────────────────────────────────────────────────────────────

    def _flood(self, datapath, msg, in_port):
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser
        actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
        data    = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data)
        datapath.send_msg(out)

    # ──────────────────────────────────────────────────────────────────────────
    # Helper – send a raw packet out a specific port
    # ──────────────────────────────────────────────────────────────────────────

    def _send_packet_out(self, datapath, msg, out_port):
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser
        actions = [parser.OFPActionOutput(out_port)]
        data    = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=msg.match['in_port'],
            actions=actions,
            data=data)
        datapath.send_msg(out)

    # ──────────────────────────────────────────────────────────────────────────
    # Helper – add a flow rule to the switch flow table
    # ──────────────────────────────────────────────────────────────────────────

    def _add_flow(self, datapath, priority, match, actions,
                  idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod  = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout)
        datapath.send_msg(mod)
