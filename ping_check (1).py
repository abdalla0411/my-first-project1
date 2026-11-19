#!/usr/bin/env python3
"""
ping_check.py - Basic network reachability checker.

Pings one or more hosts/IPs, prints UP/DOWN status with timestamps, and
finishes with a summary (total checked, reachable, unreachable).

Where the target hosts come from (in priority order):
  1. Hosts typed on the command line only        -> python ping_check.py 8.8.8.8
  2. A hosts file (-f path, or ./hosts.txt)      -> python ping_check.py -f hosts.txt
  3. A built-in default list, used as a fallback if the file is missing/empty.

Hosts file format: one host per line; '#' starts a comment. Example:
    8.8.8.8          # Google DNS
    192.168.1.1      # Home router
    github.com

Uses only the Python standard library and the system's `ping` command, so it
works on Windows, Linux, and macOS with no extra installs.

Examples:
    python ping_check.py                              # hosts.txt or defaults
    python ping_check.py 8.8.8.8 google.com           # specific hosts
    python ping_check.py -f lab_hosts.txt -c 3 -i 2   # 3 rounds, 2s apart
    python ping_check.py -c 0                         # run until Ctrl+C

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
# Configuration
# --------------------------------------------------------------------------
# Hosts file read when no hosts are given on the command line.
DEFAULT_HOSTS_FILE = "hosts.txt"

# Fallback targets, used only if the hosts file is missing, unreadable or empty.
DEFAULT_HOSTS = ["8.8.8.8", "1.1.1.1", "google.com"]


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
# Host loading
# --------------------------------------------------------------------------
def load_hosts_from_file(path: str) -> list[str]:
    """Read hosts from a text file (one per line; '#' starts a comment).

    Raises OSError (e.g. FileNotFoundError) if the file cannot be read.
    """
    hosts = []
    with open(path, encoding="utf-8") as file:
        for line in file:
            line = line.split("#", 1)[0].strip()  # drop comments and spaces
            if line:
                hosts.append(line)
    return hosts


def resolve_hosts(cli_hosts: list[str], file_path: str | None) -> list[str]:
    """Decide which hosts to check, falling back to defaults when needed."""
    # Hosts typed on the command line (and no -f) are used exactly as given.
    if cli_hosts and not file_path:
        return list(dict.fromkeys(cli_hosts))  # remove duplicates, keep order

    # Otherwise read from the hosts file (the given one, or the default name).
    path = file_path or DEFAULT_HOSTS_FILE
    hosts = list(cli_hosts)
    try:
        hosts += load_hosts_from_file(path)
    except OSError as error:
        print(f"Warning: could not read '{path}' ({error.strerror}).")

    # Fallback: nothing usable was found, so use the built-in default list.
    if not hosts:
        print(f"Using the built-in default hosts: {', '.join(DEFAULT_HOSTS)}\n")
        hosts = list(DEFAULT_HOSTS)

    return list(dict.fromkeys(hosts))  # remove duplicates, keep order


# --------------------------------------------------------------------------
# Output
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


def print_summary(results: list[dict]) -> None:
    """Print the final summary for the most recent round of checks."""
    reachable = [r["host"] for r in results if r["up"]]
    unreachable = [r["host"] for r in results if not r["up"]]

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total checked : {len(results)}")
    print(f"Reachable     : {len(reachable)}")
    print(f"Unreachable   : {len(unreachable)}")
    if unreachable:
        print(f"Down hosts    : {', '.join(unreachable)}")
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    """Define and parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Check network reachability of one or more hosts."
    )
    parser.add_argument("hosts", nargs="*", help="Hostnames or IP addresses to ping")
    parser.add_argument(
        "-f", "--file",
        help=f"Text file with one host per line (default: ./{DEFAULT_HOSTS_FILE})",
    )
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
    hosts = resolve_hosts(args.hosts, args.file)

    results: list[dict] = []  # results of the last completed round
    round_number = 0

    try:
        while True:
            round_number += 1
            results = [ping_host(host, args.timeout) for host in hosts]

            for result in results:
                print_result(result)

            # Stop after the requested number of rounds (0 = never stop).
            if args.count and round_number >= args.count:
                break

            print("-" * 60)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")

    # Summarize the last completed round (skipped if interrupted before any).
    if results:
        print_summary(results)

    return 0 if results and all(r["up"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
