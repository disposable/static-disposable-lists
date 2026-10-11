#!/usr/bin/env python3
"""Refresh geographic/hosting metadata on dnsservices.json + mailservices.json.

For every provider key:

- hosted:       ISO country where the provider's site resolves, looked up
                against free DB-IP Lite country MMDBs (IPv4 + IPv6).
- cloud:        cloud/CDN operator from DB-IP Lite ASN MMDBs (Cloudflare,
                AWS, Azure, Google Cloud, Hetzner, ...).
- jurisdiction: ISO country of the provider's legal seat. Layered:
                1. data/jurisdiction_overrides.json (curated; also matched
                   against a provider's host domains)
                2. an existing jurisdiction value (manual curation wins)
                3. ccTLD heuristic on the provider key
                Unknown stays unset - never guessed.

GeoIP data: DB-IP Lite databases (CC BY 4.0, https://db-ip.com), downloaded
into .geoip/ (gitignored). Requires: dnspython, maxminddb.

Usage: python scripts/update_geo_metadata.py [--db-dir .geoip]
"""

import gzip
import ipaddress
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOGS = ["dnsservices.json", "mailservices.json"]
OVERRIDES = REPO / "data" / "jurisdiction_overrides.json"
DB_BASE = "https://download.db-ip.com/free"
DB_FILES = {
    "country4": "dbip-country-lite-{ym}.mmdb.gz",
    "country6": "dbip-country-ipv6-lite-{ym}.mmdb.gz",
    "asn4": "dbip-asn-ipv4-lite-{ym}.mmdb.gz",
    "asn6": "dbip-asn-ipv6-lite-{ym}.mmdb.gz",
}

# Cloud/CDN operator patterns matched against the ASN organization string.
CLOUD = {
    "Cloudflare": "Cloudflare",
    "Amazon": "AWS",
    "Microsoft": "Azure",
    "Google": "Google Cloud",
    "Fastly": "Fastly",
    "Akamai": "Akamai",
    "Linode": "Akamai",
    "DigitalOcean": "DigitalOcean",
    "Hetzner": "Hetzner",
    "OVH": "OVH",
    "Oracle": "Oracle Cloud",
    "Alibaba": "Alibaba Cloud",
    "Contabo": "Contabo",
    "IONOS": "IONOS",
    "ProfitBricks": "IONOS",
    "Vercel": "Vercel",
    "Netlify": "Netlify",
    "Automattic": "Automattic",
    "Scaleway": "Scaleway",
    "UpCloud": "UpCloud",
    "Vultr": "Vultr",
    "Leaseweb": "Leaseweb",
    "Railway": "Railway",
    "Render": "Render",
    "Fly.io": "Fly.io",
    "Heroku": "Heroku",
    "Salesforce": "Salesforce",
    "IBM": "IBM Cloud",
    "Tencent": "Tencent Cloud",
    "Huawei": "Huawei Cloud",
    "Vercara": "UltraDNS",
    "Bunny": "BunnyCDN",
    "CDN77": "CDN77",
    "G-Core": "G-Core",
    "StackPath": "StackPath",
    "Imperva": "Imperva",
    "Sucuri": "Sucuri",
    "DDoS-Guard": "DDoS-Guard",
    "Qrator": "Qrator",
    "Yandex": "Yandex Cloud",
    "Selectel": "Selectel",
    "Kinsta": "Kinsta",
    "WP Engine": "WP Engine",
    "netcup": "netcup",
    "Apple": "Apple",
    "Meta": "Meta",
}

# Country-code TLDs that reliably indicate a national operator. Generic
# ccTLDs adopted globally (io, co, me, tv, ai, to, gg, fm, am, ag, ws, cc,
# cx, nu, ly, sh, ac, pw, re, je, im, sc, ms, vg, ky, bm, bz, vu, tk, ml,
# ga, cf, gq, sx, lc) are deliberately absent.
CCTLD = {
    "de": "DE", "at": "AT", "ch": "CH", "fr": "FR", "nl": "NL", "be": "BE",
    "it": "IT", "es": "ES", "pt": "PT", "pl": "PL", "cz": "CZ", "sk": "SK",
    "hu": "HU", "ro": "RO", "bg": "BG", "gr": "GR", "hr": "HR", "si": "SI",
    "rs": "RS", "ua": "UA", "ru": "RU", "su": "RU", "by": "BY", "se": "SE",
    "no": "NO", "dk": "DK", "fi": "FI", "ee": "EE", "lv": "LV", "lt": "LT",
    "is": "IS", "ie": "IE", "uk": "GB", "ca": "CA", "au": "AU", "nz": "NZ",
    "jp": "JP", "cn": "CN", "tw": "TW", "kr": "KR", "in": "IN", "br": "BR",
    "cl": "CL", "ar": "AR", "mx": "MX", "za": "ZA", "tr": "TR", "il": "IL",
    "ir": "IR", "ae": "AE", "th": "TH", "vn": "VN", "id": "ID", "my": "MY",
    "ph": "PH", "sg": "SG", "hk": "HK", "kz": "KZ", "ge": "GE", "md": "MD",
    "al": "AL", "ba": "BA", "mk": "MK", "ng": "NG", "ke": "KE", "gh": "GH",
    "lu": "LU", "li": "LI", "mt": "MT", "cy": "CY", "uy": "UY", "cr": "CR",
    "pa": "PA", "ec": "EC", "sa": "SA", "eg": "EG", "ma": "MA", "tn": "TN",
    "dz": "DZ", "bd": "BD", "pk": "PK", "az": "AZ", "kg": "KG", "mn": "MN",
    "iq": "IQ", "af": "AF", "qa": "QA", "kw": "KW", "lk": "LK", "np": "NP",
    "mm": "MM", "kh": "KH", "la": "LA", "ve": "VE", "py": "PY", "do": "DO",
    "bn": "BN", "na": "NA", "ci": "CI", "ad": "AD", "mc": "MC", "gi": "GI",
    "mu": "MU", "xk": "XK", "jo": "JO", "pe": "PE",
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, obj):
    def sortrec(o):
        if isinstance(o, dict):
            return {k: sortrec(v) for k, v in sorted(o.items())}
        if isinstance(o, list):
            return [sortrec(i) for i in o]
        return o
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sortrec(obj), f, indent=2, ensure_ascii=False)
        f.write("\n")


def ensure_dbs(db_dir):
    """Download DB-IP Lite MMDBs for the current month, falling back to
    previous months (the free DBs appear a few days into each month)."""
    db_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    for months_back in range(0, 4):
        d = now - timedelta(days=30 * months_back)
        ym = f"{d.year}-{d.month:02d}"
        missing = [k for k, pat in DB_FILES.items()
                   if not (db_dir / pat.format(ym=ym).removesuffix(".gz")).exists()]
        if not missing:
            return {k: db_dir / pat.format(ym=ym).removesuffix(".gz")
                    for k, pat in DB_FILES.items()}
        ok = True
        for k in missing:
            name = DB_FILES[k].format(ym=ym)
            try:
                req = urllib.request.Request(
                    f"{DB_BASE}/{name}", headers={"User-Agent": "geo-update/1.0"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    raw = r.read()
                data = gzip.decompress(raw)
                if len(data) < 1_000_000:
                    ok = False
                    break
                (db_dir / name.removesuffix(".gz")).write_bytes(data)
            except Exception:
                ok = False
                break
        if ok or months_back == 3:
            paths = {k: db_dir / pat.format(ym=ym).removesuffix(".gz")
                     for k, pat in DB_FILES.items()}
            if all(p.exists() for p in paths.values()):
                print(f"GeoIP databases: {ym}")
                return paths
    raise SystemExit("could not fetch DB-IP Lite databases")


def resolve_ips(keys):
    """A/AAAA lookup per provider key; first public IP wins."""
    import dns.resolver
    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = 4
    resolver.lifetime = 6

    def one(key):
        if "." not in key:  # non-domain provider labels
            return key, None
        for rdtype in ("A", "AAAA"):
            try:
                for rr in resolver.resolve(key, rdtype):
                    ip = ipaddress.ip_address(rr.address)
                    if ip.is_global:
                        return key, str(ip)
            except Exception:
                pass
        return key, None

    out = {}
    with ThreadPoolExecutor(max_workers=32) as pool:
        futs = {pool.submit(one, k): k for k in keys}
        for f in as_completed(futs):
            k, ip = f.result()
            out[k] = ip
    return out


def main():
    db_dir = Path(sys.argv[sys.argv.index("--db-dir") + 1]) \
        if "--db-dir" in sys.argv else REPO / ".geoip"
    try:
        import maxminddb
    except ImportError:
        sys.exit("pip install maxminddb dnspython")

    dbs = ensure_dbs(db_dir)
    country_v4 = maxminddb.open_database(str(dbs["country4"]))
    country_v6 = maxminddb.open_database(str(dbs["country6"]))
    asn_v4 = maxminddb.open_database(str(dbs["asn4"]))
    asn_v6 = maxminddb.open_database(str(dbs["asn6"]))

    overrides = load_json(OVERRIDES)
    catalogs = {name: load_json(REPO / name) for name in CATALOGS}
    keys = sorted(set().union(*[set(c) for c in catalogs.values()]))

    ips = resolve_ips(keys)
    resolved = sum(1 for v in ips.values() if v)
    print(f"resolved {resolved}/{len(keys)} provider sites")

    def geo(ip):
        if not ip:
            return None, None, None
        v6 = ":" in ip
        try:
            rec = (country_v6 if v6 else country_v4).get(ip) or {}
            cc = (rec.get("country_code")  # dbip lite flat schema
                  or (rec.get("country") or {}).get("iso_code")
                  or (rec.get("registered_country") or {}).get("iso_code"))
        except Exception:
            cc = None
        try:
            arec = (asn_v6 if v6 else asn_v4).get(ip) or {}
            org = arec.get("autonomous_system_organization")
        except Exception:
            org = None
        cloud = None
        if org:
            for pat, name in CLOUD.items():
                if pat.lower() in org.lower():
                    cloud = name
                    break
        return cc, org, cloud

    def juris_of(key, svc, existing):
        # precedence: explicit key override > existing manual value >
        # override via a known host domain > ccTLD heuristic
        if key in overrides:
            return overrides[key]
        if existing:
            return existing
        for h in (svc.get("hosts") or []) + (svc.get("old_hosts") or []):
            if h in overrides:
                return overrides[h]
        tld = key.rsplit(".", 1)[-1] if "." in key else None
        return CCTLD.get(tld) if tld else None

    stats = {"hosted": 0, "cloud": 0, "jurisdiction": 0}
    for name, cat in catalogs.items():
        for key, svc in cat.items():
            cc, org, cloud = geo(ips.get(key))
            if cc:
                svc["hosted"] = cc
                stats["hosted"] += 1
            if cloud:
                svc["cloud"] = cloud
                stats["cloud"] += 1
            j = juris_of(key, svc, svc.get("jurisdiction"))
            if j:
                svc["jurisdiction"] = j
                stats["jurisdiction"] += 1
        dump_json(REPO / name, cat)

    print(f"hosted {stats['hosted']}, cloud {stats['cloud']}, "
          f"jurisdiction {stats['jurisdiction']} (of {len(keys)} providers)")


if __name__ == "__main__":
    main()
