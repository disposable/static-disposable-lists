#!env python3

import json
import sys


ALLOWED_TYPES = ['free', 'paid']
ALLOWED_VERIFICATIONS = ['none', 'email', 'mobile', 'payment', 'other']


def validate_mailservices(filename: str):
    freemailer = {}
    errors = []
    with open(filename) as f:
        try:
            freemailer = json.load(f)
        except json.JSONDecodeError:
            print("Failed to decode freemailer file.")
            sys.exit(1)

    if not type(freemailer) is dict:
        print("Freemailer file is not a dictionary.")
        sys.exit(1)

    all_hosts = set()
    for host_group, host_options in freemailer.items():
        if not type(host_options) is dict:
            errors.append("Host group {} is not a dictionary.".format(host_group))
            continue

        if not type(host_options.get('hosts')) is list:
            errors.append("Host group {} has no hosts.".format(host_group))
            continue

        for host in host_options['hosts']:
            if not type(host) is str:
                errors.append("Host {} is not a string.".format(host))
                continue

            if host in all_hosts:
                errors.append("Duplicate host {} in host group {}.".format(host, host_group))
                continue

            all_hosts.add(host)

        if host_options.get('type') and host_options['type'] not in ALLOWED_TYPES:
            errors.append("Type {} for host group {} is not allowed.".format(host_options['type'], host_group))

        if host_options.get('signup_verification') and host_options['signup_verification'] not in ALLOWED_VERIFICATIONS:
            errors.append("Verification {} for host group {} is not allowed.".format(host_options['signup_verification'], host_group))

        if host_options.get('mx_hosts') and type(host_options['mx_hosts']) is not list:
            errors.append("MX hosts for host group {} are not a list.".format(host_group))

    if len(errors) > 0:
        for error in errors:
            print(error)
        sys.exit(1)


if __name__ == "__main__":
    filename = "mailservices.json"
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    validate_mailservices(filename)
