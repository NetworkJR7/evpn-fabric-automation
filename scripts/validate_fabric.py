#!/usr/bin/env python3

import json
import subprocess
from pathlib import Path
from datetime import datetime


# ============================================================
# LAB08 - EVPN FABRIC AUTOMATED VALIDATION
# ============================================================

NODES = {
    "leaf1": "clab-lab08-leaf1",
    "spine": "clab-lab08-spine",
    "leaf2": "clab-lab08-leaf2",
    "host1": "clab-lab08-host1",
    "host2": "clab-lab08-host2",
}

VNI = "10100"
HOST2_IP = "192.168.100.20"

results = []
details = []


def run(command):
    """Execute a local shell command and return rc/stdout/stderr."""
    process = subprocess.run(
        command,
        shell=True,
        text=True,
        capture_output=True,
    )

    return (
        process.returncode,
        process.stdout.strip(),
        process.stderr.strip(),
    )


def vtysh(node, command):
    """Execute one FRR command inside a container."""
    container = NODES[node]

    return run(
        f'docker exec {container} '
        f'vtysh -c "{command}"'
    )


def check(name, passed, info=""):
    """Store and print one validation result."""
    status = "PASS" if passed else "FAIL"

    results.append((name, status, info))

    print(f"{name:<40} {status}")

    if info:
        details.append(f"{name}: {info}")


def established_peers(data):
    """Return established BGP peers from FRR JSON."""
    peers = data.get("peers", {})

    return {
        ip: peer
        for ip, peer in peers.items()
        if peer.get("state") == "Established"
    }


print()
print("=" * 62)
print("        LAB08 - EVPN FABRIC AUTOMATED VALIDATION")
print("=" * 62)
print()


# ============================================================
# 1. UNDERLAY BGP
# ============================================================

print("[ UNDERLAY BGP ]")

for node in ("leaf1", "leaf2", "spine"):

    rc, output, error = vtysh(
        node,
        "show bgp ipv4 unicast summary json"
    )

    try:
        data = json.loads(output) if rc == 0 else {}
        peers = established_peers(data)

        if node == "leaf1":
            expected = any(
                peer.get("hostname") == "spine"
                for peer in peers.values()
            )

        elif node == "leaf2":
            expected = any(
                peer.get("hostname") == "spine"
                for peer in peers.values()
            )

        else:
            hostnames = {
                peer.get("hostname")
                for peer in peers.values()
            }

            expected = (
                "leaf1" in hostnames
                and "leaf2" in hostnames
            )

        check(
            f"{node.upper()} underlay BGP",
            expected,
            f"Established peers: {len(peers)}",
        )

    except json.JSONDecodeError:
        check(
            f"{node.upper()} underlay BGP",
            False,
            "Invalid JSON returned by FRR",
        )


print()


# ============================================================
# 2. EVPN OVERLAY
# ============================================================

print("[ EVPN CONTROL PLANE ]")

for node in ("leaf1", "leaf2"):

    rc, output, error = vtysh(
        node,
        "show bgp l2vpn evpn summary json"
    )

    try:
        data = json.loads(output) if rc == 0 else {}
        peers = established_peers(data)

        check(
            f"{node.upper()} EVPN peer",
            len(peers) >= 1,
            f"Established EVPN peers: {len(peers)}",
        )

    except json.JSONDecodeError:
        check(
            f"{node.upper()} EVPN peer",
            False,
            "Invalid JSON returned by FRR",
        )


print()


# ============================================================
# 3. VXLAN / VNI
# ============================================================

print("[ VXLAN / VNI ]")

for node in ("leaf1", "leaf2"):

    rc, output, error = vtysh(
        node,
        "show evpn vni"
    )

    vni_present = (
        rc == 0
        and VNI in output
        and "vxlan100" in output
    )

    remote_vtep = (
        vni_present
        and "10100" in output
    )

    check(
        f"{node.upper()} VNI {VNI}",
        vni_present,
        "vxlan100 detected" if vni_present else "VNI missing",
    )

    # Linux-side VXLAN verification
    rc2, vxlan_output, error2 = run(
        f"docker exec {NODES[node]} "
        f"ip -d link show vxlan100"
    )

    check(
        f"{node.upper()} vxlan100 interface",
        rc2 == 0 and "vxlan id 10100" in vxlan_output,
        "Linux VXLAN interface",
    )


print()


# ============================================================
# 4. DATA PLANE / TRAFFIC GENERATION
# ============================================================

print("[ DATA PLANE ]")

rc, output, error = run(
    f"docker exec {NODES['host1']} "
    f"ping -c 3 -W 1 {HOST2_IP}"
)

ping_ok = (
    rc == 0
    and "0% packet loss" in output
)

check(
    "HOST1 -> HOST2",
    ping_ok,
    f"{HOST2_IP} reachable" if ping_ok else "Ping failed",
)

print()


# ============================================================
# 5. EVPN MAC LEARNING
# ============================================================

print("[ EVPN MAC LEARNING ]")

for node in ("leaf1", "leaf2"):

    rc, output, error = vtysh(
        node,
        f"show evpn mac vni {VNI}"
    )

    output_lower = output.lower()

    has_local = " local " in output_lower
    has_remote = " remote " in output_lower

    check(
        f"{node.upper()} local MAC",
        has_local,
    )

    check(
        f"{node.upper()} remote MAC",
        has_remote,
    )

print()

# ============================================================
# FINAL STATUS
# ============================================================

failed = [
    item
    for item in results
    if item[1] == "FAIL"
]

fabric_status = (
    "HEALTHY"
    if not failed
    else "DEGRADED"
)

print("=" * 62)
print(f"FABRIC STATUS: {fabric_status}")
print("=" * 62)


# ============================================================
# REPORT
# ============================================================

report_dir = Path(__file__).parent / "reports"
report_dir.mkdir(exist_ok=True)

report_file = report_dir / "evpn_health_report.txt"

with report_file.open("w") as f:

    f.write("LAB08 - EVPN FABRIC HEALTH REPORT\n")
    f.write("=" * 45 + "\n\n")

    f.write(
        f"Generated: "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )

    for name, status, info in results:
        f.write(f"{name:<40} {status}")

        if info:
            f.write(f"   {info}")

        f.write("\n")

    f.write("\n")
    f.write("=" * 45 + "\n")
    f.write(f"FABRIC STATUS: {fabric_status}\n")
    f.write("=" * 45 + "\n")


print()
print(f"Report saved to: {report_file}")
