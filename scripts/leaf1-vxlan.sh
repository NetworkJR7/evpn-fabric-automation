#!/bin/sh

ip link add br100 type bridge
ip link set br100 up

ip link set eth2 master br100
ip link set eth2 up

ip link add vxlan100 type vxlan \
    id 10100 \
    local 10.255.0.1 \
    dstport 4789 \
    nolearning

ip link set vxlan100 master br100
ip link set vxlan100 up
