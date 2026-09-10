#!/usr/bin/env python3
"""Add or update entries in mailservices.json."""

import argparse
import json
import os
import sys

try:
    from validate_hostnames import is_valid_hostname
except ImportError:  # pragma: no cover
    from .validate_hostnames import is_valid_hostname


def load_json(file_path: str) -> dict:
    """Load JSON file or return an empty dict if it doesn't exist."""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(file_path: str, data: dict) -> None:
    """Save data to a JSON file with a trailing newline."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def load_schema(schema_path: str) -> dict:
    """Load a JSON schema file."""
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_allowed_values(schema_path: str = "schemas/mailservices.schema.json") -> tuple[list[str], list[str]]:
    """Return (types, verifications) allowed by the schema."""
    schema = load_schema(schema_path)
    pattern_props = schema.get("patternProperties", {})

    types: list[str] = []
    verifications: set[str] = set()

    for prop_schema in pattern_props.values():
        props = prop_schema.get("properties", {})

        type_prop = props.get("type", {})
        types = type_prop.get("enum", [])

        verify_prop = props.get("signup_verification", {})
        if "enum" in verify_prop:
            verifications.update(verify_prop["enum"])
        elif "oneOf" in verify_prop:
            for sub in verify_prop["oneOf"]:
                verifications.update(sub.get("enum", []))

    return types, sorted(verifications)


def _validate_and_normalize(
    service: str,
    hosts: list[str] | None,
    mx_hosts: list[str] | None,
    account_type: str | None,
    signup_verification: str | None,
    allowed_types: list[str],
    allowed_verifications: list[str],
) -> tuple[list[str] | None, list[str] | None]:
    """Validate arguments and return normalized host/mx lists."""
    if hosts:
        invalid = [h for h in hosts if not is_valid_hostname(h)]
        if invalid:
            print(f"Invalid hostnames for {service}: {invalid}")
            sys.exit(1)
        hosts = sorted(set(hosts))

    if mx_hosts:
        invalid = [h for h in mx_hosts if not is_valid_hostname(h)]
        if invalid:
            print(f"Invalid MX hostnames for {service}: {invalid}")
            sys.exit(1)
        mx_hosts = sorted(set(mx_hosts))

    if account_type and account_type not in allowed_types:
        print(f"Invalid account type: {account_type}. Allowed: {allowed_types}")
        sys.exit(1)

    if signup_verification and signup_verification not in allowed_verifications:
        print(f"Invalid signup verification: {signup_verification}. Allowed: {allowed_verifications}")
        sys.exit(1)

    return hosts, mx_hosts


def update_json(
    file_path: str,
    service: str,
    hosts: list[str] | None = None,
    mx_hosts: list[str] | None = None,
    account_type: str | None = None,
    signup_verification: str | None = None,
    schema_path: str = "schemas/mailservices.schema.json",
) -> None:
    """Update or add a service entry in the JSON file."""
    allowed_types, allowed_verifications = get_allowed_values(schema_path)
    hosts, mx_hosts = _validate_and_normalize(
        service, hosts, mx_hosts, account_type, signup_verification,
        allowed_types, allowed_verifications,
    )

    data = load_json(file_path)

    if service in data:
        existing = data[service]
        new_hosts = set(existing.get("hosts", []))
        new_mx_hosts = set(existing.get("mx_hosts", []))

        if hosts:
            new_hosts.update(hosts)
        if mx_hosts:
            new_mx_hosts.update(mx_hosts)

        existing["hosts"] = sorted(new_hosts)
        if new_mx_hosts:
            existing["mx_hosts"] = sorted(new_mx_hosts)
    else:
        data[service] = {"hosts": hosts or []}
        if mx_hosts:
            data[service]["mx_hosts"] = mx_hosts

    if account_type:
        data[service]["type"] = account_type
    if signup_verification:
        data[service]["signup_verification"] = [signup_verification]

    save_json(file_path, data)
    print(f"Updated {service} in {file_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update JSON file with service details.")

    parser.add_argument("--file", default="mailservices.json", help="Path to the JSON file.")
    parser.add_argument("--service", required=True, help="Service name to update/add.")
    parser.add_argument("--host", action="append", default=[], help="Hostnames (can be used multiple times).")
    parser.add_argument("--mx-host", action="append", default=[], help="MX hostnames (can be used multiple times).")
    parser.add_argument("--stdin", action="store_true", help="Read hosts from stdin (line by line).")
    parser.add_argument("--type", help="Account type.")
    parser.add_argument("--verify", help="Signup verification type.")
    parser.add_argument("--schema", default="schemas/mailservices.schema.json", help="Path to the schema file.")

    args = parser.parse_args()

    stdin_hosts = []
    if args.stdin:
        stdin_hosts = [line.strip() for line in sys.stdin if line.strip()]

    all_hosts = args.host + stdin_hosts
    all_mx_hosts = args.mx_host

    update_json(
        args.file,
        args.service,
        all_hosts,
        all_mx_hosts,
        args.type,
        args.verify,
        args.schema,
    )


if __name__ == "__main__":
    main()
