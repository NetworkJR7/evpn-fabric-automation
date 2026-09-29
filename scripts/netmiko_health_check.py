from netmiko import ConnectHandler
from pathlib import Path
from datetime import datetime
import subprocess

DEVICES = {
    "leaf1": {
        "device_type": "linux",
        "host": "172.30.80.6",
        "username": "netops",
        "password": "netops123",
    },
    "spine": {
        "device_type": "linux",
        "host": "172.30.80.2",
        "username": "netops",
        "password": "netops123",
    },
    "leaf2": {
        "device_type": "linux",
        "host": "172.30.80.4",
        "username": "netops",
        "password": "netops123",
    },
}

VNI = "10100"
EXPECTED_RT = "65000:10100"

HOST1_CONTAINER = "clab-lab08-host1"
HOST2_IP = "192.168.100.20"

checks = []


def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    checks.append((name, status, detail))
    print(f"{name:<42} {status}")


def run_frr(conn, command):
    return conn.send_command(f'vtysh -c "{command}"')


print()
print("=" * 68)
print("         LAB08 - NETMIKO EVPN FABRIC HEALTH CHECK")
print("=" * 68)
print()

connections = {}

# Variables used later for diagnostics
leaf1_rt_ok = False
leaf2_rt_ok = False

try:

    # ---------------------------------------------------------
    # CONNECT
    # ---------------------------------------------------------

    for name, device in DEVICES.items():
        print(f"Connecting to {name} ({device['host']})...")
        connections[name] = ConnectHandler(**device)

    # ---------------------------------------------------------
    # UNDERLAY BGP
    # ---------------------------------------------------------

    print("\n[ UNDERLAY BGP ]")

    leaf1_bgp = run_frr(
        connections["leaf1"],
        "show bgp ipv4 unicast summary"
    )

    leaf2_bgp = run_frr(
        connections["leaf2"],
        "show bgp ipv4 unicast summary"
    )

    spine_bgp = run_frr(
        connections["spine"],
        "show bgp ipv4 unicast summary"
    )

    record(
        "Leaf1 -> Spine BGP",
        "10.10.18.2" in leaf1_bgp and "65000" in leaf1_bgp
    )

    record(
        "Leaf2 -> Spine BGP",
        "10.10.18.6" in leaf2_bgp and "65000" in leaf2_bgp
    )

    record(
        "Spine -> Leaf1/Leaf2 BGP",
        "10.10.18.1" in spine_bgp
        and "10.10.18.5" in spine_bgp
    )

    # ---------------------------------------------------------
    # EVPN CONTROL PLANE
    # ---------------------------------------------------------

    print("\n[ EVPN CONTROL PLANE ]")

    leaf1_evpn = run_frr(
        connections["leaf1"],
        "show bgp l2vpn evpn summary"
    )

    leaf2_evpn = run_frr(
        connections["leaf2"],
        "show bgp l2vpn evpn summary"
    )

    record(
        "Leaf1 EVPN peer",
        "10.255.0.2" in leaf1_evpn
    )

    record(
        "Leaf2 EVPN peer",
        "10.255.0.1" in leaf2_evpn
    )

    # ---------------------------------------------------------
    # SERVICE POLICY / ROUTE TARGET
    # ---------------------------------------------------------

    print("\n[ SERVICE POLICY ]")

    leaf1_run = run_frr(
        connections["leaf1"],
        "show running-config"
    )

    leaf2_run = run_frr(
        connections["leaf2"],
        "show running-config"
    )

    leaf1_rt_ok = (
        f"route-target import {EXPECTED_RT}" in leaf1_run
        and f"route-target export {EXPECTED_RT}" in leaf1_run
    )

    leaf2_rt_ok = (
        f"route-target import {EXPECTED_RT}" in leaf2_run
        and f"route-target export {EXPECTED_RT}" in leaf2_run
    )

    record(
        f"Leaf1 RT {EXPECTED_RT}",
        leaf1_rt_ok
    )

    record(
        f"Leaf2 RT {EXPECTED_RT}",
        leaf2_rt_ok
    )

    # ---------------------------------------------------------
    # VXLAN / VNI
    # ---------------------------------------------------------

    print("\n[ VXLAN / VNI ]")

    leaf1_vni = run_frr(
        connections["leaf1"],
        "show evpn vni"
    )

    leaf2_vni = run_frr(
        connections["leaf2"],
        "show evpn vni"
    )

    record(
        f"Leaf1 VNI {VNI}",
        VNI in leaf1_vni
        and "vxlan100" in leaf1_vni
    )

    record(
        f"Leaf2 VNI {VNI}",
        VNI in leaf2_vni
        and "vxlan100" in leaf2_vni
    )

    record(
        "Leaf1 remote VTEP",
        "1" in leaf1_vni.splitlines()[-1]
    )

    record(
        "Leaf2 remote VTEP",
        "1" in leaf2_vni.splitlines()[-1]
    )

    # ---------------------------------------------------------
    # DATA PLANE
    # ---------------------------------------------------------

    print("\n[ DATA PLANE ]")

    ping = subprocess.run(
        [
            "docker",
            "exec",
            HOST1_CONTAINER,
            "ping",
            "-c",
            "3",
            "-W",
            "1",
            HOST2_IP,
        ],
        text=True,
        capture_output=True,
    )

    ping_ok = (
        ping.returncode == 0
        and "0% packet loss" in ping.stdout
    )

    record(
        "Host1 -> Host2",
        ping_ok
    )

    # ---------------------------------------------------------
    # EVPN MAC LEARNING
    # ---------------------------------------------------------

    print("\n[ EVPN MAC LEARNING ]")

    leaf1_mac = run_frr(
        connections["leaf1"],
        f"show evpn mac vni {VNI}"
    )

    leaf2_mac = run_frr(
        connections["leaf2"],
        f"show evpn mac vni {VNI}"
    )

    record(
        "Leaf1 local MAC",
        "local" in leaf1_mac.lower()
    )

    record(
        "Leaf1 remote MAC",
        "remote" in leaf1_mac.lower()
    )

    record(
        "Leaf2 local MAC",
        "local" in leaf2_mac.lower()
    )

    record(
        "Leaf2 remote MAC",
        "remote" in leaf2_mac.lower()
    )

finally:

    for conn in connections.values():
        conn.disconnect()


# -------------------------------------------------------------
# GLOBAL STATUS
# -------------------------------------------------------------

failed = [
    check
    for check in checks
    if check[1] == "FAIL"
]

print()
print("=" * 68)

if not failed:
    status = "HEALTHY"
    print("FABRIC STATUS: HEALTHY")
else:
    status = "DEGRADED"
    print("FABRIC STATUS: DEGRADED")

print("=" * 68)


# -------------------------------------------------------------
# TROUBLESHOOTING LOGIC
# -------------------------------------------------------------

if failed:

    print("\nLikely fault domains:")

    names = [
        check[0]
        for check in failed
    ]

    if any("BGP" in name for name in names):
        print("- Underlay BGP / reachability")

    if any("EVPN peer" in name for name in names):
        print("- EVPN control plane")

    if any("RT " in name for name in names):
        print(
            "- Route Target mismatch / "
            "EVPN service-policy import-export"
        )

    if any(
        "VNI" in name or "VTEP" in name
        for name in names
    ):
        print(
            "- VXLAN/VNI service import "
            "or dataplane programming"
        )

    if any("MAC" in name for name in names):
        print(
            "- EVPN MAC learning / "
            "Type-2 advertisement"
        )

    if any(
        "Host1 -> Host2" in name
        for name in names
    ):
        print(
            "- End-to-end VXLAN dataplane connectivity"
        )

    # ---------------------------------------------------------
    # ROOT CAUSE HINT
    # ---------------------------------------------------------

    if not leaf1_rt_ok or not leaf2_rt_ok:

        print("\nROOT-CAUSE HINT:")
        print(
            f"Expected Route Target: {EXPECTED_RT}"
        )

        if not leaf1_rt_ok:
            print(
                "- Leaf1 Route Target mismatch"
            )

        if not leaf2_rt_ok:
            print(
                "- Leaf2 Route Target mismatch"
            )


# -------------------------------------------------------------
# REPORT
# -------------------------------------------------------------

report_dir = Path("reports")
report_dir.mkdir(exist_ok=True)

report = (
    report_dir
    / "netmiko_health_report.txt"
)

with report.open("w") as f:

    f.write(
        "LAB08 - NETMIKO EVPN FABRIC HEALTH REPORT\n"
    )

    f.write("=" * 50 + "\n\n")

    f.write(
        f"Generated: {datetime.now()}\n\n"
    )

    for name, result, detail in checks:
        f.write(
            f"{name:<42} {result}\n"
        )

    f.write("\n")

    f.write(
        f"FABRIC STATUS: {status}\n"
    )

print(
    f"\nReport saved to: {report}"
)

