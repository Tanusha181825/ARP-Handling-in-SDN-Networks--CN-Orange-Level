# ARP Handling in SDN Networks

# DN Mininet Based Simulation Project  


## Project Overview

In a traditional network, when one host wants to communicate with another, it first needs to know the MAC address of the destination IP. This is done using **ARP (Address Resolution Protocol)**.

Normally, ARP requests are broadcasted to all devices in the network, which can lead to unnecessary traffic.

In this project, I have implemented **ARP request and reply handling using an SDN controller**.  
Instead of flooding ARP packets across the network, the controller intercepts ARP requests, processes them, and sends the required ARP reply.

This project is implemented using:

- **Mininet** for network topology simulation
- **Ryu Controller** for SDN logic
- **OpenFlow 1.3** for controller-switch communication

The main goal of this project is to understand how SDN controllers manage network traffic and how ARP can be handled centrally.


## Objective

The main objectives of this project are:

- Intercept ARP packets using the SDN controller
- Handle ARP request and reply packets
- Enable host discovery
- Validate communication between hosts
- Observe controller-switch interaction
- Install flow rules dynamically


## Topology Used

For simplicity, I used a **2-host 1-switch topology**.

```text
h1 -------- s1 -------- h2
               |
         SDN Controller
