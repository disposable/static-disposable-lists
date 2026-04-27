#!/usr/bin/env python3

import argparse
import json
import socket
import sys
import dns.resolver
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def resolve_a(hostname: str) -> list[str]:
    """Resolve A records for a hostname."""
    try:
        a_records = dns.resolver.resolve(hostname, 'A')
        return [str(rdata) for rdata in a_records]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return []
    except Exception as e:
        logging.debug(f"Failed to resolve A record for {hostname}: {e}")
        return []

def resolve_mx(hostname: str) -> list[tuple[str, int]]:
    """Resolve MX records for a hostname."""
    try:
        mx_records = dns.resolver.resolve(hostname, 'MX')
        return [(str(mx.exchange).rstrip('.'), mx.preference) for mx in mx_records]
    except dns.resolver.NoAnswer:
        return []
    except dns.resolver.NXDOMAIN:
        logging.warning(f"The domain {hostname} does not exist.")
        return []
    except Exception as e:
        logging.debug(f"Failed to resolve MX for {hostname}: {e}")
        return []


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


def get_mail_hosts(hostname: str, check_a_fallback: bool = True) -> tuple[list[str], bool]:
    """
    Get mail server hosts for a domain.
    Returns (hosts_list, from_mx) tuple where from_mx indicates if hosts came from MX records.
    """
    mx_records = resolve_mx(hostname)
    if mx_records:
        return [mx[0] for mx in mx_records], True

    if check_a_fallback:
        a_records = resolve_a(hostname)
        if a_records:
            logging.info(f"No MX found for {hostname}, using A record fallback: {a_records}")
            return [hostname], False  # False indicates not from MX records

    return [], False

def validate_freemailer(
    input_file: str,
    output_file: str | None = None,
    update: bool = False,
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
            logging.error("Host group {} is not a dictionary.".format(host_group))
            sys.exit(1)

        # Skip discontinued providers
        if host_options.get('discontinued', False):
            logging.info("Skipping discontinued provider: {}".format(host_group))
            continue

        hosts = host_options.get('hosts', [])
        if not hosts:
            logging.warning("No hosts found for group {}".format(host_group))
            continue

        # Filter to specific host if requested
        if host_filter:
            if host_filter not in hosts:
                logging.warning(f"Host '{host_filter}' not found in provider '{host_group}'")
                continue
            hosts = [host_filter]

        current_mx_hosts = host_options.get('mx_hosts', [])
        mx_list = set(current_mx_hosts)

        for host in hosts:
            mail_hosts, from_mx = get_mail_hosts(host, check_a_fallback=check_a_fallback)
            logging.info("{}: {}".format(host, mail_hosts if mail_hosts else "No mail hosts found"))

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
                        logging.warning("New mail host detected for {}: {}".format(host, mail_host))

        host_options['mx_hosts'] = sorted(h for h in mx_list if h and h.lower() != 'localhost')

    # Determine where to write output
    if update:
        write_path = input_file
    elif output_file:
        write_path = output_file
    else:
        write_path = None

    if write_path:
        with open(write_path, 'w') as f:
            json.dump(freemailer, f, indent=2)
            f.write('\n')
        logging.info("Updated data written to {}".format(write_path))
    else:
        logging.info("No output file specified - changes not saved. Use -o/--output or --update to save.")
        # Print summary of discovered hosts
        for host_group, host_options in freemailer.items():
            mx_hosts = host_options.get('mx_hosts', [])
            if mx_hosts:
                logging.info("{}: mx_hosts = {}".format(host_group, mx_hosts))


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

    args = parser.parse_args()

    # Prevent conflicting output options
    if args.output and args.update:
        parser.error("Cannot use both --output and --update")

    validate_freemailer(
        args.input_file,
        args.output,
        update=args.update,
        check_a_fallback=not args.no_a_fallback,
        check_smtp_port=args.check_smtp,
        smtp_timeout=args.smtp_timeout,
        provider=args.provider,
        host_filter=args.host_filter
    )


if __name__ == "__main__":
    main()
