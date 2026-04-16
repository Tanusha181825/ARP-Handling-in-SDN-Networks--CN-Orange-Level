from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4
from ryu.lib.packet import ether_types
import logging


class ARPHandlerController(app_manager.RyuApp):
    """
    Simple SDN controller for ARP handling in a star topology.

    Features:
    - Intercepts ARP packets
    - Learns MAC -> port mapping
    - Learns IP -> MAC and IP -> port mapping
    - Sends proxy ARP replies when destination is known
    - Floods ARP requests when destination is unknown
    - Installs flow rules for IPv4 traffic
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ARPHandlerController, self).__init__(*args, **kwargs)

        self.mac_to_port = {}
        self.ip_to_mac = {}
        self.ip_to_port = {}

        self.logger.setLevel(logging.INFO)
        self.logger.info("=== ARP Handler Controller started ===")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.mac_to_port.setdefault(dpid, {})
        self.ip_to_mac.setdefault(dpid, {})
        self.ip_to_port.setdefault(dpid, {})

        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER
            )
        ]
        self.add_flow(datapath, 0, match, actions)
        self.logger.info("[SWITCH %016x] Connected - table-miss rule installed", dpid)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        dpid = datapath.id

        pkt = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocol(ethernet.ethernet)

        if eth_pkt is None:
            return

        if eth_pkt.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src_mac = eth_pkt.src
        dst_mac = eth_pkt.dst

        self.mac_to_port[dpid][src_mac] = in_port

        arp_pkt = pkt.get_protocol(arp.arp)
        ipv4_pkt = pkt.get_protocol(ipv4.ipv4)

        if arp_pkt:
            self.handle_arp(datapath, in_port, eth_pkt, arp_pkt, msg)
        elif ipv4_pkt:
            self.handle_ipv4(datapath, in_port, eth_pkt, ipv4_pkt, msg)
        else:
            self.flood(datapath, msg, in_port)

    def handle_arp(self, datapath, in_port, eth_pkt, arp_pkt, msg):
        dpid = datapath.id
        src_ip = arp_pkt.src_ip
        src_mac = arp_pkt.src_mac
        dst_ip = arp_pkt.dst_ip

        self.ip_to_mac[dpid][src_ip] = src_mac
        self.ip_to_port[dpid][src_ip] = in_port

        self.logger.info("[ARP] Learned %s -> %s on port %s", src_ip, src_mac, in_port)

        if arp_pkt.opcode == arp.ARP_REQUEST:
            self.logger.info("[ARP] REQUEST: Who has %s? (from %s)", dst_ip, src_ip)

            if dst_ip in self.ip_to_mac[dpid]:
                target_mac = self.ip_to_mac[dpid][dst_ip]
                self.logger.info("[ARP] PROXY REPLY: %s is at %s", dst_ip, target_mac)

                self.send_arp_reply(
                    datapath=datapath,
                    out_port=in_port,
                    src_mac=target_mac,
                    src_ip=dst_ip,
                    dst_mac=src_mac,
                    dst_ip=src_ip
                )
            else:
                self.logger.info("[ARP] Unknown target %s - flooding", dst_ip)
                self.flood(datapath, msg, in_port)

        elif arp_pkt.opcode == arp.ARP_REPLY:
            self.logger.info("[ARP] REPLY: %s is at %s", src_ip, src_mac)

            if arp_pkt.dst_ip in self.ip_to_port[dpid]:
                out_port = self.ip_to_port[dpid][arp_pkt.dst_ip]
                self.send_packet_out(datapath, msg, out_port)
            else:
                self.flood(datapath, msg, in_port)

    def handle_ipv4(self, datapath, in_port, eth_pkt, ipv4_pkt, msg):
        dpid = datapath.id
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        src_mac = eth_pkt.src
        dst_mac = eth_pkt.dst

        if dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_src=src_mac,
                eth_dst=dst_mac
            )

            self.add_flow(
                datapath=datapath,
                priority=10,
                match=match,
                actions=actions,
                idle_timeout=30,
                hard_timeout=120
            )

            self.logger.info("[FLOW] Installed %s -> %s on port %s", src_mac, dst_mac, out_port)

        self.send_packet_out(datapath, msg, out_port)

    def send_arp_reply(self, datapath, out_port, src_mac, src_ip, dst_mac, dst_ip):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(
            ethertype=ether_types.ETH_TYPE_ARP,
            dst=dst_mac,
            src=src_mac
        ))
        pkt.add_protocol(arp.arp(
            opcode=arp.ARP_REPLY,
            src_mac=src_mac,
            src_ip=src_ip,
            dst_mac=dst_mac,
            dst_ip=dst_ip
        ))
        pkt.serialize()

        actions = [parser.OFPActionOutput(out_port)]
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=ofproto.OFPP_CONTROLLER,
            actions=actions,
            data=pkt.data
        )
        datapath.send_msg(out)

    def flood(self, datapath, msg, in_port):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    def send_packet_out(self, datapath, msg, out_port):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        actions = [parser.OFPActionOutput(out_port)]
        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=msg.match['in_port'],
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )
        datapath.send_msg(mod)
