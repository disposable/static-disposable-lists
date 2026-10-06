#!/usr/bin/env python3
"""Import domains from alexandrosmagos/dyn-dns-list into dnsservices.json
and generate the uncapped dnsservices.full.json.

Upstream: https://github.com/alexandrosmagos/dyn-dns-list
Source file: links.json (daily-generated, per-domain provider provenance)

Files:
  dnsservices.json      - source of truth, hand-edited and web-facing.
                          Existing `hosts` are preserved verbatim; new upstream
                          domains fill each provider's list up to CAP entries,
                          with `hosts_total` recording the real count.
  dnsservices.full.json - generated; identical records but `hosts` extended
                          with every imported upstream domain (multi-MB, do
                          not edit by hand).

Note: the import is append-only. Domains dropped upstream are kept, matching
the repo's habit of retaining retired names; domains sourced from upstream
re-import while listed there.
"""
import json
import sys
import urllib.request

UPSTREAM_URL = (
    "https://raw.githubusercontent.com/alexandrosmagos/dyn-dns-list/"
    "refs/heads/master/links.json"
)
SOURCE_FILE = "dnsservices.json"
FULL_FILE = "dnsservices.full.json"
CAP = 500

# upstream provider name -> catalog key, only where they differ;
# identical names resolve directly against the catalog keys.
PROVIDER_MAP = {
    "afraid.org": "freedns.afraid.org",
    "noip.com": "no-ip.com",
    "pubyun.com": "3322.org",
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def known_domains(catalog):
    known = set()
    for svc in catalog.values():
        known.update(svc.get("hosts") or [])
        known.update(svc.get("old_hosts") or [])
    return known


def main():
    with urllib.request.urlopen(UPSTREAM_URL, timeout=120) as r:
        upstream = json.load(r)
    records = upstream.get("domains", [])
    print(f"upstream: {len(records)} domains (generatedAt {upstream.get('generatedAt')})")

    catalog = load_json(SOURCE_FILE)
    try:
        prev_full = load_json(FULL_FILE)
    except FileNotFoundError:
        prev_full = {}
    prev_known = known_domains(prev_full)

    # group new upstream domains by catalog provider, preserving upstream order
    known = known_domains(catalog)
    incoming = {}
    skipped_provider = set()
    for rec in records:
        domain = rec.get("domain", "").strip().lower()
        if not domain or domain in known:
            continue
        target = None
        for prov in rec.get("providers", []):
            key = prov if prov in catalog else PROVIDER_MAP.get(prov)
            if key and key in catalog:
                target = key
                break
        if target is None:
            skipped_provider.update(rec.get("providers", []))
            continue
        incoming.setdefault(target, []).append(domain)
        known.add(domain)

    # full catalog: existing hosts + all new upstream domains
    full = {}
    for key, svc in catalog.items():
        svc = dict(svc)
        svc["hosts"] = list(svc.get("hosts") or []) + incoming.get(key, [])
        svc.pop("hosts_total", None)
        full[key] = svc
    full = dict(sorted(full.items()))
    dump_json(FULL_FILE, full)

    # web-facing catalog: existing hosts preserved, upstream fills up to CAP
    capped = {}
    truncated = 0
    for key, svc_full in full.items():
        svc = dict(svc_full)
        existing = (catalog[key].get("hosts") or [])
        hosts = svc_full["hosts"]
        svc["hosts"] = existing if len(existing) >= CAP else hosts[:CAP]
        if len(svc["hosts"]) < len(hosts):
            svc["hosts_total"] = len(hosts)
            truncated += 1
        capped[key] = svc
    dump_json(SOURCE_FILE, capped)

    new_to_full = sum(1 for d in known if d not in prev_known)
    print(f"new domains in {FULL_FILE}: {new_to_full} "
          f"({sum(len(v) for v in incoming.values())} unlisted upstream domains processed)")
    if skipped_provider:
        print("unmapped upstream providers:", ", ".join(sorted(skipped_provider)))
    print(f"{SOURCE_FILE}: {truncated} providers capped at {CAP} hosts")


if __name__ == "__main__":
    sys.exit(main())
