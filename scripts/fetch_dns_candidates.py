#!/usr/bin/env python3
"""Fetch DNS-domain candidates from upstream sources and write
dnsservices-candidates.json — a stateful staging file of domains not yet
cataloged in dnsservices.json, for manual review (nothing is added
automatically).

Per-domain record:
  added_on     first day the domain was seen in any source
  last_checked last day its DNS was verified (NS or SOA)
  resolves     whether the domain currently has NS/SOA records
  hint         likely provider key (source metadata or NS fingerprint)
  sources      which upstream lists currently report the domain
  status       manual triage: new (default) / approved / rejected / deferred
  validated    manual flag: reviewer verified the domain/hint

`status` and `validated` are preserved across regenerations — the script
only manages the auto fields; review marks are yours.

Entries persist while any source lists them; domains that fail resolution
stay flagged resolves=false and are retried on the next run.

Sources:
  - hagezi/dns-blocklists wildcard/dyndns.txt (flat *.domain list, ~daily)
  - korlabsio/subdomain_providers names (domain, category CSV)
  - binjoo/PublicFreeSuffix public_sld_list.json (operator metadata)
  - publicsuffix.org list (PRIVATE section, operator-comment grouped)
  - openwrt/packages ddns-scripts default/*.json (per-provider files)
"""
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

SOURCES = {
    "hagezi": "https://raw.githubusercontent.com/hagezi/dns-blocklists/"
              "main/wildcard/dyndns.txt",
    "korlabsio": "https://raw.githubusercontent.com/korlabsio/"
                 "subdomain_providers/main/names",
    "publicfreesuffix": "https://raw.githubusercontent.com/binjoo/"
                        "PublicFreeSuffix/main/public_sld_list.json",
    "psl": "https://publicsuffix.org/list/public_suffix_list.dat",
    "openwrt": "https://api.github.com/repos/openwrt/packages/contents/"
               "net/ddns-scripts/files/usr/share/ddns/default",
}
CATALOG_FILE = "dnsservices.json"
OUT_FILE = "dnsservices-candidates.json"

# PublicFreeSuffix operator.organization -> catalog key
OPERATOR_MAP = {
    "public free suffix": "pfsdns.org",
}

# NS suffixes of public/shared DNS operators: a domain delegated here only
# proves it uses that DNS host — it does NOT identify the issuer. NS
# fingerprint hints matching these are dropped.
SHARED_NS = {
    "beget.com", "beget.pro", "cloudflare.com", "cloudns.com", "cloudns.net",
    "desec.io", "desec.org", "dns-auth.net", "dns.oraclecloud.net",
    "dnsauthority.com", "dnsmadeeasy.com", "dnsv5.com", "dyna-ns.net",
    "dynamicnetworkservices.net", "easydns.com", "easydns.net",
    "first-ns.de", "he.net", "opendns.com", "plako.net", "second-ns.com",
    "securepoint.de", "aseinet.ne.jp", "dns.ne.jp",
    "second-ns.de", "spaceweb.pro", "spaceweb.ru", "uadns.com",
    "xundns.com", "zoneedit.com", "byet.org", "epizy.com",
}

# OpenWrt service-file suffixes that are variant/transport markers
OWRT_VARIANT = re.compile(r"-(v\d+|token|basicauth|keyauth|basic)$")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "devin-candidates"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "replace")


def parse_hagezi(text):
    out = set()
    for line in text.splitlines():
        line = line.strip().lower()
        if line and not line.startswith("#"):
            out.add(line.lstrip("*."))
    return out


def parse_korlabsio(text):
    out = {}
    for line in text.splitlines():
        line = line.strip().lower()
        if line and "," in line:
            domain, _, cat = line.partition(",")
            out[domain.strip()] = cat.strip()
    return out


def parse_publicfreesuffix(text):
    out = {}
    for domain, info in json.loads(text).items():
        org = (info.get("operator") or {}).get("organization", "")
        out[domain.strip().lower()] = OPERATOR_MAP.get(org.lower())
    return out


# PSL comment tokens that are not operator headers
PSL_STOPWORDS = {"http", "https", "reference", "submitted", "see", "note"}
PSL_OP_RE = re.compile(r"//\s*(.+?)\s*:\s*(?:https?://)?(\S+)")
PSL_SUBMIT_RE = re.compile(r"@([a-z0-9.-]+\.[a-z]{2,})", re.I)
DOMAIN_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$")


def idna(domain):
    """Normalize unicode domains to punycode so they match catalog entries."""
    try:
        return domain.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        return domain


def parse_psl(text, keys):
    """PRIVATE section -> {domain: hint}, hint = catalog key via operator URL,
    or 'psl:<operator>' for unknown operators with several entries.
    Operator header = the first // comment line of a blank-line-separated block."""
    try:
        priv = text.split("===BEGIN PRIVATE DOMAINS===")[1]
    except IndexError:
        return {}
    by_op = {}
    op = submitted = None
    block_open = True
    for line in priv.splitlines():
        s = line.strip()
        if not s:
            op = submitted = None
            block_open = True
            continue
        if s.startswith("//"):
            m = PSL_OP_RE.match(s)
            if block_open and m and m.group(1).lower() not in PSL_STOPWORDS \
                    and DOMAIN_RE.match(m.group(2).rstrip("/").split("/")[0].lower()):
                op = (m.group(1), m.group(2).rstrip("/").split("/")[0].lower())
            elif block_open and op is None:
                # headerless block: keep the comment text as operator name
                label = s[2:].strip().split(":", 1)[0].strip()
                if label and label.lower() not in PSL_STOPWORDS:
                    op = (label, None)
            m2 = PSL_SUBMIT_RE.search(s)
            if m2:
                submitted = m2.group(1).lower()
            block_open = False
            continue
        if s.startswith("!"):
            continue
        block_open = False
        key_op = op
        if key_op and not key_op[1] and submitted:
            key_op = (key_op[0], submitted)
        elif key_op is None and submitted:
            key_op = (submitted, submitted)
        by_op.setdefault(key_op, set()).add(s.lstrip("*.").lower())
    out = {}
    for opk, doms in by_op.items():
        if opk is None:
            hint = None
        else:
            name, host = opk
            if host and host in keys:
                hint = host
            elif len(doms) >= 3:
                hint = f"psl:{name}"
            else:
                hint = None
        for d in doms:
            out[d] = hint
    return out


def parse_openwrt(text, keys):
    """Provider JSON filenames -> provider service domains not in catalog."""
    out = {}
    for f in json.loads(text):
        name = f.get("name", "")
        if not name.endswith(".json"):
            continue
        prov = OWRT_VARIANT.sub("", name[:-5])
        if prov not in keys:
            out[prov] = "new-provider"
    return out


def ns_fingerprints(catalog):
    suffix_map, host_map = {}, {}
    for key, svc in catalog.items():
        for suf in svc.get("ns_suffixes") or []:
            suf = suf.lower()
            if suf not in SHARED_NS:
                suffix_map[suf] = key
        for host in svc.get("ns_hosts") or []:
            host_map[host.lower()] = key
    return suffix_map, host_map


def check_domain(domain):
    """Return (ns_set, resolves) — resolves true if NS or SOA records exist."""
    import dns.resolver
    ns = set()
    try:
        for r in dns.resolver.resolve(domain, "NS", lifetime=5):
            ns.add(str(r.target).rstrip(".").lower())
        return ns, bool(ns)
    except Exception:
        pass
    try:
        dns.resolver.resolve(domain, "SOA", lifetime=5)
        return ns, True
    except Exception:
        return ns, False


def attribute(ns, suffix_map, host_map):
    for ns_host in ns:
        if ns_host in host_map:
            return host_map[ns_host]
        for suf, key in suffix_map.items():
            if ns_host == suf or ns_host.endswith("." + suf):
                return key
    return None


def main():
    today = date.today().isoformat()
    catalog = json.load(open(CATALOG_FILE, encoding="utf-8"))
    keys = set(catalog)
    known = set(catalog)
    for svc in catalog.values():
        known.update(svc.get("hosts") or [])
        known.update(svc.get("old_hosts") or [])
        own = svc.get("own_domains")
        if isinstance(own, list):
            known.update(own)

    try:
        prev = json.load(open(OUT_FILE, encoding="utf-8"))
    except FileNotFoundError:
        prev = {}

    # domain -> {sources: set, hint: str|None}
    seen = {}
    for name, url in SOURCES.items():
        try:
            text = fetch(url)
        except Exception as e:
            print(f"{name}: fetch failed: {e}")
            continue
        if name == "hagezi":
            items = {d: None for d in parse_hagezi(text)}
        elif name == "korlabsio":
            items = {}
            for d, cat in parse_korlabsio(text).items():
                d = idna(d)
                if d not in known:
                    seen.setdefault(d, {"sources": set(), "hint": None})
                    seen[d]["sources"].add(f"korlabsio:{cat}")
        elif name == "publicfreesuffix":
            items = parse_publicfreesuffix(text)
        elif name == "psl":
            items = parse_psl(text, keys)
        else:
            items = parse_openwrt(text, keys)
        for d, hint in items.items():
            d = idna(d)
            if d in known:
                continue
            seen.setdefault(d, {"sources": set(), "hint": None})
            seen[d]["sources"].add(name)
            if hint and not seen[d]["hint"]:
                seen[d]["hint"] = hint

    print(f"{len(seen)} candidate domains after filtering known")

    # carry forward added_on + manual review marks for entries still listed
    out = {}
    for d in seen:
        out[d] = dict(prev.get(d) or {})
        out[d].setdefault("added_on", today)
        out[d]["status"] = out[d].get("status", "new")
        if "validated" not in out[d]:
            out[d]["validated"] = False

    # verify DNS + NS-fingerprint attribution for entries lacking a hint
    suffix_map, host_map = ns_fingerprints(catalog)
    with ThreadPoolExecutor(max_workers=32) as pool:
        results = dict(zip(seen, pool.map(check_domain, seen)))
    resolves = sum(1 for ns, ok in results.values() if ok)
    for d, (ns, ok) in results.items():
        out[d]["last_checked"] = today
        out[d]["resolves"] = ok
        out[d]["sources"] = sorted(seen[d]["sources"])
        hint = seen[d]["hint"] or attribute(ns, suffix_map, host_map)
        if hint:
            out[d]["hint"] = hint
        else:
            out[d].pop("hint", None)
    print(f"{resolves}/{len(seen)} resolve (NS or SOA), "
          f"{sum(1 for v in out.values() if v.get('hint'))} with provider hint")

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(out.items())), f, indent=2,
                  ensure_ascii=False, sort_keys=True)
        f.write("\n")
    print(f"wrote {OUT_FILE}")


if __name__ == "__main__":
    sys.exit(main())
