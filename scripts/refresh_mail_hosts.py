#!/usr/bin/env python3
"""Refresh ip_addresses in disposable-mail-hosts.json from live DNS.

For every provider entry the A records of all ``mx_hosts`` are resolved and
merged into ``ip_addresses``. ``ip_ranges`` is managed by hand and left
untouched; ``mx_suffixes`` entries are sanity-checked via NS resolution.

A provider whose MX hosts all fail to resolve keeps its stored addresses -
transient DNS failures must not silently drop fingerprints.
"""

import argparse
import json
import sys

import dns.resolver

logging = __import__("logging")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def resolve_a(hostname: str) -> list[str]:
    """Resolve A records for a hostname."""
    try:
        return [str(rdata) for rdata in dns.resolver.resolve(hostname, 'A')]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return []
    except Exception as e:
        logging.debug(f"Failed to resolve A record for {hostname}: {e}")
        return []


def resolve_ns(hostname: str) -> bool:
    """Return True when a domain has NS records."""
    try:
        return bool(dns.resolver.resolve(hostname, 'NS'))
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return False
    except Exception as e:
        logging.debug(f"Failed to resolve NS record for {hostname}: {e}")
        return False


def refresh(input_file: str, update: bool = False, output_file: str | None = None) -> bool:
    """Refresh ip_addresses; returns True when every provider verified clean."""
    with open(input_file) as f:
        hosts = json.load(f)

    ok = True
    for provider, options in sorted(hosts.items()):
        mx_hosts = options.get('mx_hosts', [])
        resolved_ips: set[str] = set()
        dead_mx: list[str] = []

        for mx in mx_hosts:
            ips = resolve_a(mx)
            if ips:
                resolved_ips.update(ips)
            else:
                dead_mx.append(mx)

        if dead_mx:
            logging.warning(f"{provider}: MX hosts not resolving: {dead_mx}")
            ok = False

        if resolved_ips:
            stored = set(options.get('ip_addresses', []))
            if stored != resolved_ips:
                logging.info(f"{provider}: ip_addresses {sorted(stored)} -> {sorted(resolved_ips)}")
                options['ip_addresses'] = sorted(resolved_ips)
        elif mx_hosts:
            logging.warning(f"{provider}: all MX hosts dead - keeping stored ip_addresses")
            ok = False

        for suffix in options.get('mx_suffixes', []):
            if not resolve_ns(suffix):
                logging.warning(f"{provider}: mx_suffix {suffix} has no NS records")
                ok = False

    write_path = input_file if update else output_file
    if write_path:
        with open(write_path, 'w') as f:
            json.dump(hosts, f, indent=2, sort_keys=True)
            f.write('\n')
        logging.info(f"Written to {write_path}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', default='disposable-mail-hosts.json')
    parser.add_argument('-o', '--output', help='write result to this file')
    parser.add_argument('-u', '--update', action='store_true', help='update the input file in place')
    parser.add_argument('--check', action='store_true', help='exit non-zero when refresh would change data')
    args = parser.parse_args()

    import tempfile, os
    if args.check:
        with open(args.input) as f:
            before = f.read()
        tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        tmp.close()
        ok = refresh(args.input, output_file=tmp.name)
        with open(tmp.name) as f:
            changed = f.read() != before
        os.unlink(tmp.name)
        if changed:
            logging.error("disposable-mail-hosts.json is stale (run with --update)")
        sys.exit(0 if ok and not changed else 1)

    ok = refresh(args.input, update=args.update, output_file=args.output)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
