#!/usr/bin/env python3
"""
ping_check.py - Basic network reachability checker.

Pings one or more hosts/IPs and prints UP/DOWN status with a timestamp.
Uses only the Python standard library and the system's `ping` command,
so it works on Windows, Linux, and macOS with no extra installs.

Examples:
    python ping_check.py 8.8.8.8 google.com
    python ping_check.py -f hosts.txt
    python ping_check.py 192.168.1.1 -c 5 -i 2       # 5 rounds, 2s apart
    python ping_check.py 192.168.1.1 -c 0             # run until Ctrl+C

Exit code: 0 if every host was reachable in the last round, 1 otherwise.
(Useful when this script is called from other automation or schedulers.)
"""

import argparse
import platform
import re
import subprocess
import sys
import time
from datetime import datetime


# --------------------------------------------------------------------------
# Core logic
# --------------------------------------------------------------------------
def build_ping_command(host: str, timeout: int) -> list[str]:
    """Build the OS-specific ping command (1 packet, with a timeout).

    The flags differ per operating system:
      - Windows: -n <count>, -w <timeout in milliseconds>
      - Linux:   -c <count>, -W <timeout in seconds>
      - macOS:   -c <count>, -W <timeout in milliseconds>
    """
    system = platform.system().lower()
    if system == "windows":
        return ["ping", "-n", "1", "-w", str(timeout * 1000), host]
    if system == "darwin":  # macOS
        return ["ping", "-c", "1", "-W", str(timeout * 1000), host]
    return ["ping", "-c", "1", "-W", str(timeout), host]  # Linux and others


def extract_latency(output: str) -> str | None:
    """Pull the round-trip time (e.g. '23.4 ms') out of ping's output, if any."""
    # Matches "time=23.4 ms", "time<1ms", "time=23ms" (Windows/Linux/macOS)
    match = re.search(r"time[=<]\s*([\d.]+)\s*ms", output, re.IGNORECASE)
    return f"{match.group(1)} ms" if match else None


def ping_host(host: str, timeout: int = 2) -> dict:
    """Ping a single host once and return a result dictionary.

    Returns:
        {"host": str, "up": bool, "latency": str | None}
    """
    command = build_ping_command(host, timeout)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout + 3,  # safety net in case ping itself hangs
        )
        up = result.returncode == 0
        latency = extract_latency(result.stdout) if up else None
    except subprocess.TimeoutExpired:
        up, latency = False, None
    except FileNotFoundError:
        sys.exit("Error: the 'ping' command was not found on this system.")

    return {"host": host, "up": up, "latency": latency}


# --------------------------------------------------------------------------
# Output / helpers
# --------------------------------------------------------------------------
def print_result(result: dict) -> None:
    """Print one result line with a timestamp.

    Extension idea: replace/extend this function to also write to a CSV file,
    send an email/Telegram alert, or push to a monitoring dashboard.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "UP  " if result["up"] else "DOWN"
    latency = result["latency"] or "-"
    print(f"[{timestamp}] {status}  {result['host']:<25} {latency}")


def load_hosts_from_file(path: str) -> list[str]:
    """Read hosts from a text file (one per line; '#' starts a comment)."""
    hosts = []
    with open(path, encoding="utf-8") as file:
        for line in file:
            line = line.split("#", 1)[0].strip()
            if line:
                hosts.append(line)
    return hosts


def parse_args() -> argparse.Namespace:
    """Define and parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Check network reachability of one or more hosts."
    )
    parser.add_argument("hosts", nargs="*", help="Hostnames or IP addresses to ping")
    parser.add_argument("-f", "--file", help="Text file with one host per line")
    parser.add_argument(
        "-c", "--count", type=int, default=1,
        help="Number of rounds to run (0 = run until Ctrl+C). Default: 1",
    )
    parser.add_argument(
        "-i", "--interval", type=float, default=5,
        help="Seconds to wait between rounds. Default: 5",
    )
    parser.add_argument(
        "-t", "--timeout", type=int, default=2,
        help="Seconds to wait for each reply. Default: 2",
    )
    return parser.parse_args()


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> int:
    args = parse_args()

    # Combine hosts given on the command line with hosts from the file.
    hosts = list(args.hosts)
    if args.file:
        try:
            hosts += load_hosts_from_file(args.file)
        except OSError as error:
            sys.exit(f"Error: cannot read '{args.file}': {error}")

    if not hosts:
        sys.exit("Error: provide at least one host (or use -f hosts.txt).")

    all_up = True
    round_number = 0

    try:
        while True:
            round_number += 1
            results = [ping_host(host, args.timeout) for host in hosts]

            for result in results:
                print_result(result)
            all_up = all(result["up"] for result in results)

            # Stop after the requested number of rounds (0 = never stop).
            if args.count and round_number >= args.count:
                break

            print("-" * 60)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")

    return 0 if all_up else 1


if __name__ == "__main__":
    sys.exit(main())
