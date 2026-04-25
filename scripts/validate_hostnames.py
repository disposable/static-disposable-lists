#!/usr/bin/env python3
"""Validate hostname files - check each line is a valid domain name."""
import re
import sys

HOSTNAME_RE = re.compile(r"^(?!-)[A-Za-z0-9\-]{1,255}(?<!-)(\.[A-Za-z0-9\-]{2,64})+$")

def validate_hostnames(filename: str) -> bool:
    errors = []
    with open(filename) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if not HOSTNAME_RE.match(line):
                errors.append(f"Line {line_num}: {line} is not a valid domain name.")
    
    if errors:
        print(f"Validation failed for {filename}:")
        for error in errors:
            print(error)
        return False
    print(f"{filename} is valid")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: validate_hostnames.py <file> [file2 ...]")
        sys.exit(1)
    
    error = False
    for filename in sys.argv[1:]:
        if not validate_hostnames(filename):
            error = True
    
    sys.exit(1 if error else 0)
