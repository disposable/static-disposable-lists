#!/usr/bin/env python3
"""Sort JSON keys alphabetically to maintain consistent ordering."""
import json
import sys


def sort_json_keys(file_path: str):
    """Load JSON, sort keys recursively, and save back."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    def sort_dict(obj):
        if isinstance(obj, dict):
            return {k: sort_dict(v) for k, v in sorted(obj.items())}
        elif isinstance(obj, list):
            return [sort_dict(item) for item in obj]
        return obj

    sorted_data = sort_dict(data)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(sorted_data, f, indent=2, ensure_ascii=False)
        f.write("\n")  # Add trailing newline

    print(f"Sorted keys in {file_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: sort_json_keys.py <file.json>")
        sys.exit(1)

    sort_json_keys(sys.argv[1])
