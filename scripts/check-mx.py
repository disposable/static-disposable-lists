#!env python3

import json
import sys
import dns.resolver
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def resolve_mx(hostname):
    try:
        mx_records = dns.resolver.resolve(hostname, 'MX')
        if not mx_records:
            logging.error(f"No MX records found for domain {hostname}")
            return []
        return [(str(mx.exchange), mx.preference) for mx in mx_records]
    except dns.resolver.NoAnswer:
        logging.error(f"No MX records found for domain {hostname}")
        return []
    except dns.resolver.NXDOMAIN:
        logging.error(f"The domain {hostname} does not exist.")
        return []
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return []

def validate_freemailer(filename: str) -> None:
    freemailer = {}
    with open(filename) as f:
        try:
            freemailer = json.load(f)
        except json.JSONDecodeError:
            logging.error("Failed to decode freemailer file.")
            sys.exit(1)

    if type(freemailer) is not dict:
        logging.error("Freemailer file is not a dictionary.")
        sys.exit(1)

    for host_group, host_options in freemailer.items():
        if type(host_options) is not dict:
            logging.error("Host group {} is not a dictionary.".format(host_group))
            sys.exit(1)

        current_mx_hosts = host_options.get('mx_hosts', [])

        mx_list = set(host_options.get('mx_hosts', []))
        for host in host_options['hosts']:
            mx_hosts = resolve_mx(host)
            logging.info("{}: {}".format(host, mx_hosts))
            for mx in mx_hosts:
                mx_list.add(mx[0])
                if current_mx_hosts and mx[0] not in current_mx_hosts:
                    logging.warning("New MX host detected for {}: {}".format(host, mx[0]))

        host_options['mx_hosts'] = list(mx_list)



if __name__ == "__main__":
    validate_freemailer(sys.argv[1])
