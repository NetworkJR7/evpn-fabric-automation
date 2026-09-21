from netmiko import ConnectHandler
from pathlib import Path

devices = {
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

commands = {
    "leaf1": [
        'vtysh -c "show bgp ipv4 unicast summary"',
        'vtysh -c "show bgp l2vpn evpn summary"',
        'vtysh -c "show evpn vni"',
    ],
    "spine": [
        'vtysh -c "show bgp ipv4 unicast summary"',
    ],
    "leaf2": [
        'vtysh -c "show bgp ipv4 unicast summary"',
        'vtysh -c "show bgp l2vpn evpn summary"',
        'vtysh -c "show evpn vni"',
    ],
}

output_dir = Path("scripts/outputs")
output_dir.mkdir(exist_ok=True)

for name, device in devices.items():
    print(f"\n{'=' * 20} {name.upper()} {'=' * 20}")

    conn = ConnectHandler(**device)

    all_output = []

    for command in commands[name]:
        print(f"\n>>> {command}")
        output = conn.send_command(command)
        print(output)

        all_output.append(
            f"\n>>> {command}\n{output}\n"
        )

    conn.disconnect()

    output_file = output_dir / f"{name}_show_commands.txt"

    with output_file.open("w") as f:
        f.write("".join(all_output))

    print(f"\nOutput saved to: {output_file}")
