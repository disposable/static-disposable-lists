#!/usr/bin/env python3

import argparse
import json
import socket
import sys

import dns.resolver

try:
    from validate_hostnames import is_valid_hostname
except ImportError:  # pragma: no cover
    from .validate_hostnames import is_valid_hostname

logging = __import__("logging")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def resolve_record(hostname: str, rtype: str):
    """Resolve DNS records of type *rtype* for a hostname."""
    try:
        return dns.resolver.resolve(hostname, rtype)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return []
    except Exception as e:
        logging.debug(f"Failed to resolve {rtype} record for {hostname}: {e}")
        return []


def resolve_a(hostname: str) -> list[str]:
    """Resolve A records for a hostname."""
    records = resolve_record(hostname, 'A')
    return [str(rdata) for rdata in records]


def resolve_mx(hostname: str) -> list[tuple[str, int]]:
    """Resolve MX records for a hostname, ignoring Null MX (".")."""
    records = resolve_record(hostname, 'MX')
    if not records:
        return []
    return [
        (host, mx.preference)
        for mx in records
        if (host := str(mx.exchange).rstrip('.'))
    ]


def resolve_ip(hostname: str) -> str | None:
    """Resolve hostname to first available IP address."""
    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if addr_info:
            return addr_info[0][4][0]
    except (socket.gaierror, OSError):
        pass
    return None


def check_smtp(host: str, port: int = 25, timeout: float = 5.0) -> tuple[bool, str | None]:
    """
    Check if a host responds on SMTP port.
    Returns (success, ip_address) tuple.
    """
    ip = resolve_ip(host)
    if not ip:
        return False, None
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True, ip
    except (socket.timeout, socket.error, OSError):
        return False, ip


def get_mail_hosts(hostname: str, check_a_fallback: bool = True) -> tuple[list[str], bool, bool]:
    """
    Get mail server hosts for a domain.

    Returns a (hosts_list, from_mx, resolved) tuple. *from_mx* is True when the
    hosts came from MX records, and *resolved* is True when the domain resolved
    at all (either via MX or A records).
    """
    mx_records = resolve_mx(hostname)
    if mx_records:
        return [mx[0] for mx in mx_records], True, True

    if check_a_fallback:
        a_records = resolve_a(hostname)
        if a_records:
            logging.info(f"No MX found for {hostname}, using A record fallback: {a_records}")
            return [hostname], False, True

    return [], False, False


def validate_freemailer(
    input_file: str,
    output_file: str | None = None,
    update: bool = False,
    prune: bool = False,
    check_a_fallback: bool = True,
    check_smtp_port: bool = False,
    smtp_timeout: float = 5.0,
    provider: str | None = None,
    host_filter: str | None = None
) -> None:
    freemailer = {}
    with open(input_file) as f:
        try:
            freemailer = json.load(f)
        except json.JSONDecodeError:
            logging.error("Failed to decode freemailer file.")
            sys.exit(1)

    if not isinstance(freemailer, dict):
        logging.error("Freemailer file is not a dictionary.")
        sys.exit(1)

    # Cache for SMTP check results by IP to avoid re-testing same server
    smtp_cache: dict[str, bool] = {}

    # Filter to specific provider if requested
    if provider:
        if provider not in freemailer:
            logging.error(f"Provider '{provider}' not found in {input_file}")
            sys.exit(1)
        providers_to_check = {provider: freemailer[provider]}
    else:
        providers_to_check = freemailer

    for host_group, host_options in providers_to_check.items():
        if not isinstance(host_options, dict):
            logging.error(f"Host group {host_group} is not a dictionary.")
            sys.exit(1)

        # Skip discontinued providers
        if host_options.get('discontinued', False):
            logging.info(f"Skipping discontinued provider: {host_group}")
            continue

        hosts = host_options.get('hosts', [])
        if not hosts:
            logging.warning(f"No hosts found for group {host_group}")
            continue

        # Filter to specific host if requested
        if host_filter:
            if host_filter not in hosts:
                logging.warning(f"Host '{host_filter}' not found in provider '{host_group}'")
                continue
            hosts = [host_filter]

        current_mx_hosts = host_options.get('mx_hosts', [])
        mx_list = set(current_mx_hosts)
        dead_hosts: list[str] = []

        for host in hosts:
            if not is_valid_hostname(host):
                logging.warning(f"Skipping invalid hostname '{host}' in provider '{host_group}'")
                if prune:
                    dead_hosts.append(host)
                continue

            mail_hosts, from_mx, resolved = get_mail_hosts(host, check_a_fallback=check_a_fallback)
            if not resolved:
                logging.warning(f"The domain {host} does not exist.")
            logging.info(f"{host}: {mail_hosts if mail_hosts else 'No mail hosts found'}")

            if prune and not resolved:
                dead_hosts.append(host)
                continue

            for mail_host in mail_hosts:
                # Validate SMTP connectivity if requested
                if check_smtp_port:
                    result, ip = check_smtp(mail_host, timeout=smtp_timeout)
                    if not ip:
                        logging.warning(f"  SMTP SKIP: {mail_host}:25 (could not resolve)")
                    elif ip in smtp_cache:
                        cached_result = smtp_cache[ip]
                        status = "OK (cached)" if cached_result else "FAIL (cached)"
                        log_func = logging.info if cached_result else logging.warning
                        log_func(f"  SMTP {status}: {mail_host}:25 ({ip})")
                    else:
                        smtp_cache[ip] = result
                        status = "OK" if result else "FAIL"
                        log_func = logging.info if result else logging.warning
                        log_func(f"  SMTP {status}: {mail_host}:25 ({ip})")

                # Only add to mx_hosts if it came from actual MX records (not A fallback)
                if from_mx:
                    mx_list.add(mail_host)
                    if current_mx_hosts and mail_host not in current_mx_hosts:
                        logging.warning(f"New mail host detected for {host}: {mail_host}")

        if prune and dead_hosts:
            for dead in dead_hosts:
                hosts.remove(dead)
                mx_list.discard(dead)
                old_hosts = host_options.setdefault('old_hosts', [])
                if dead not in old_hosts:
                    old_hosts.append(dead)
            host_options['old_hosts'] = sorted(host_options['old_hosts'])

            if not hosts:
                host_options['discontinued'] = True
                logging.warning(f"Marking {host_group} as discontinued (all hosts dead)")

            # Re-build hosts list without dead entries
            host_options['hosts'] = hosts

        host_options['mx_hosts'] = sorted(h for h in mx_list if h and h.lower() != 'localhost')

    # Determine where to write output
    write_path: str | None = input_file if update else output_file

    if write_path:
        with open(write_path, 'w') as f:
            json.dump(freemailer, f, indent=2)
            f.write('\n')
        logging.info(f"Updated data written to {write_path}")
    else:
        logging.info("No output file specified - changes not saved. Use -o/--output or --update to save.")
        # Print summary of discovered hosts
        for host_group, host_options in freemailer.items():
            mx_hosts = host_options.get('mx_hosts', [])
            if mx_hosts:
                logging.info(f"{host_group}: mx_hosts = {mx_hosts}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Validate MX records for mail services and update mx_hosts field.'
    )
    parser.add_argument(
        'input_file',
        help='Input JSON file (e.g., mailservices.json)'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output file (defaults to input file if not specified)'
    )
    parser.add_argument(
        '--no-a-fallback',
        action='store_true',
        help='Disable A record fallback when no MX records are found'
    )
    parser.add_argument(
        '--check-smtp',
        action='store_true',
        help='Validate that mail hosts respond on SMTP port 25'
    )
    parser.add_argument(
        '--smtp-timeout',
        type=float,
        default=5.0,
        help='Timeout for SMTP connection checks (default: 5.0 seconds)'
    )
    parser.add_argument(
        '--provider',
        help='Only check a specific provider (e.g., gmail.com)'
    )
    parser.add_argument(
        '--host',
        dest='host_filter',
        help='Only check a specific host within the provider'
    )
    parser.add_argument(
        '--update',
        action='store_true',
        help='Update the input file in place (alternative to -o)'
    )
    parser.add_argument(
        '--prune',
        action='store_true',
        help='Move unresolvable hosts to old_hosts and mark empty providers discontinued'
    )

    args = parser.parse_args()

    # Prevent conflicting output options
    if args.output and args.update:
        parser.error("Cannot use both --output and --update")

    validate_freemailer(
        args.input_file,
        args.output,
        update=args.update,
        prune=args.prune,
        check_a_fallback=not args.no_a_fallback,
        check_smtp_port=args.check_smtp,
        smtp_timeout=args.smtp_timeout,
        provider=args.provider,
        host_filter=args.host_filter
    )


if __name__ == "__main__":
    main()
