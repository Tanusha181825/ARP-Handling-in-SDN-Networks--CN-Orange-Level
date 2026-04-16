# ARP Handling in SDN Networks

## DN Mininet Based Simulation Project  


## Project Overview

This project demonstrates how **ARP (Address Resolution Protocol)** can be handled using an **SDN controller** in a **star topology network**.

In a traditional network, ARP requests are broadcast to all devices to find the MAC address of the destination host. In this project, the **Ryu controller intercepts ARP requests**, learns the host information dynamically, and sends replies whenever possible.

The network is built using **Mininet**, where all four hosts are connected to a single central switch, forming a **star topology**.

The main objective of this project is to understand how **Software Defined Networking (SDN)** enables centralized control of packet handling and dynamic flow rule installation.


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

              Controller
                   |
                  s1
          /        |        |        \
        h1        h2       h3       h4
