# Static Disposable Lists

Static data repository for disposable email domains and mail service definitions that cannot be dynamically updated via the main [disposable](https://github.com/disposable/disposable) project.

**Web Interface:** [https://disposable.github.io/static-disposable-lists/](https://disposable.github.io/static-disposable-lists/) ([DNS Services](https://disposable.github.io/static-disposable-lists/dns.html), [Tunnel Brokers](https://disposable.github.io/static-disposable-lists/tunnelbrokers.html))


## Data Files

| File | Description |
|------|-------------|
| [mailservices.json](mailservices.json) | Email service definitions with host and verification metadata; drives whitelist/strict-tier classification in disposable (see below) |
| [dnsservices.json](dnsservices.json) | Dynamic DNS / free hostname provider definitions: offered domains, pricing, update support, API, revalidation and signup metadata (see below). Source of truth — hand-edited, web-facing; imported `hosts` capped at 500 per provider |
| [dnsservices.full.json](dnsservices.full.json) | Generated artifact — same records, but `hosts` extended with every imported upstream domain (multi-MB; do not edit by hand) |
| [dnsservices-candidates.json](dnsservices-candidates.json) | Generated staging file: domains seen in upstream DNS lists but not yet cataloged, with provider hint, `added_on`/`last_checked`/`resolves` state and review marks (`status`, `validated`); review and promote into `dnsservices.json` |
| [disposable-mail-hosts.json](disposable-mail-hosts.json) | Disposable mail-backend fingerprints: MX hostnames, hostname suffixes, IPv4 addresses and CIDR ranges used to attribute disposable domains to a provider |
| [tunnelbrokers.json](tunnelbrokers.json) | IPv6 tunnel broker catalog (RFC 3053-style services): protocols, routed prefixes, BGP/rDNS/BYOIP support, endpoint update methods, PoPs and limits. Hand-curated; includes discontinued providers for reference |
| [mail-data-hosts-net.txt](mail-data-hosts-net.txt) | Hostnames from mx.mail-data.net |
| [manual.txt](manual.txt) | Manually curated list of disposable email domains |
| [free.txt](free.txt) / [free.csv](free.csv) | Free email provider domain lists (staging resource for new `mailservices.json` entries, not consumed directly) |
| [domains.csv](domains.csv) | Domain classification data |
| [generator-email-hosts.txt](generator-email-hosts.txt) | Email generator service hostnames |

### mailservices.json classification

The `type` and `signup_verification` fields determine how [disposable](https://github.com/disposable/disposable) treats each provider's hosts:

| Classification | Rule |
|----------------|------|
| whitelist | `free`/`paid`/`reserved` with verified signup (`mobile`/`phone`/`sms`/`payment`/`other`) or unset verification |
| strict tier (greylist) | `forwarding` always; `free`/`paid` offering `none` or `email` signup verification |
| excluded entirely | `discontinued: true` services feed neither tier |

`free.txt`/`free.csv` remain as broad reference lists when researching new catalog entries.

### dnsservices.json

Catalog of dynamic DNS and free hostname providers (DuckDNS, No-IP, DNSExit, FreeDNS/afraid.org, vendor router DDNS, ...), initially seeded from the [HaGeZi DynDNS blocklist](https://github.com/hagezi/dns-blocklists) with provider attribution via nameserver fingerprints and curated provider domain lists.

Key fields per provider:

| Field | Meaning |
|-------|---------|
| `hosts` / `old_hosts` | Domains under which hostnames are issued / retired domains |
| `status` | `active`, `restricted` (gated signup), `no_new_registrations`, `discontinued` |
| `type` | `free`, `paid`, `freemium`, `reserved` |
| `updates` | `dynamic` (DDNS clients), `static` (records only), `both` |
| `public` | `false` when hostnames can only be created via vendor hardware/interface or gated access |
| `api` / `update_protocols` | Programmatic access (`dyndns2`, `http`, `rfc2136`, `acme-dns01`) |
| `record_types` | DNS record types users may set (A, AAAA, CNAME, MX, TXT, NS, SRV, CAA, PTR) |
| `own_domains` / `shared_registry` | Bring-your-own-domain support / community-shared domain registry |
| `revalidation_days` / `expire_days` | Periodic manual re-confirmation / auto-purge after idle days |
| `free_hostname_limit` | Max hostnames on the free tier |
| `signup_verification` | Account signup verification method(s) |
| `ns_hosts` / `ns_suffixes` | Provider nameserver fingerprints for domain attribution |
| `hosts_total` | Real host count — only present in `dnsservices.json` when `hosts` was truncated to 500 |
| `jurisdiction` | ISO country of the provider's legal seat (imprint/terms); absent = unknown |
| `hosted` / `cloud` | GeoIP country where the site resolves / cloud-CDN operator from ASN |

`jurisdiction`, `hosted` and `cloud` also exist on `mailservices.json` entries. Geographic
fields are refreshed monthly by `scripts/update_geo_metadata.py`; legal-seat data is curated in
[data/jurisdiction_overrides.json](data/jurisdiction_overrides.json).

#### Automated domain import

A daily GitHub Actions run ([import-dyndns-list.yml](.github/workflows/import-dyndns-list.yml)) merges domains from the
[dyn-dns-list](https://github.com/alexandrosmagos/dyn-dns-list) project (scraped from provider sites, per-domain provider
provenance in `links.json`) into `dnsservices.json` — existing `hosts` are kept as-is, new upstream domains fill each
provider's list up to 500 — and generates `dnsservices.full.json` containing the complete merged host lists. Upstream
provider names are mapped to catalog keys in `scripts/import_dyndns_list.py` (`PROVIDER_MAP`); unmapped domains are
skipped. Thanks to [@alexandrosmagos](https://github.com/alexandrosmagos) for maintaining the upstream list.

A second weekly job ([dns-candidates.yml](.github/workflows/dns-candidates.yml)) regenerates
`dnsservices-candidates.json`: domains seen in the HaGeZi DynDNS list, korlabsio/subdomain_providers,
binjoo/PublicFreeSuffix, the Public Suffix List private section and OpenWrt's ddns-scripts provider registry that are
not cataloged yet. Each entry carries a provider hint (source metadata or NS-fingerprint match against
`ns_hosts`/`ns_suffixes`) plus `added_on`, `last_checked` and `resolves` (NS/SOA check) so unverifiable domains get
retried instead of dropped. Two manual review marks are preserved across regenerations: `status`
(`new`/`approved`/`rejected`/`deferred`) and `validated`. It's a staging area only — nothing is added to the
catalog automatically.

To edit the catalog, modify `dnsservices.json` — `dnsservices.full.json` is regenerated by the importer.

### tunnelbrokers.json

Catalog of IPv6 tunnel broker providers (Hurricane Electric tunnelbroker.net, route64.org,
tb.tahio.eu, tunnelbroker.ch, NetAssist, ...), seeded from the Wikipedia tunnel broker lists
([de](https://de.wikipedia.org/wiki/Liste_von_IPv6-Tunnelbrokern),
[zh](https://zh.wikipedia.org/wiki/IPv6隧道中间人列表),
[es](https://es.wikipedia.org/wiki/Anexo:Proveedores_de_túneles_IPv6)) and verified against the
provider sites. Defunct brokers (SixXS, gogo6/Freenet6, Renater, ...) are kept as reference with
`status: "discontinued"` and an `until` year where known. Hand-edited - no automated imports, no
public web page.

Key fields per provider:

| Field | Meaning |
|-------|---------|
| `protocols` | Tunnel protocols: `6in4` (proto-41/SIT), `4in6`, `gre`, `gretap`, `ayiya`, `tsp`, `heartbeat`, `openvpn`, `wireguard`, `l2tpv3`, `vxlan`, `ip6ip`, `zerotier`, `ipsec` |
| `prefixes` | Routed IPv6 prefix lengths handed to users (e.g. 48, 56, 64); absent for BYOIP-only providers |
| `bgp` / `rdns` / `byoip` | BGP peering over tunnel / reverse DNS delegation / announce own space or ASN |
| `endpoint_update` | Dynamic IPv4 endpoint handling: `none` (static required), `dyndns2`, `http` (custom URL), `automatic` (e.g. WireGuard roaming) |
| `nat` | Works behind NAT/CGNAT without a public IPv4 |
| `pops` / `locations` | Tunnel PoP count and 'City, CC' location list |
| `tunnel_limit` / `bandwidth_mbps` | Max tunnels per account / documented per-tunnel cap |
| `asn` / `allocation` | Provider ASN / own IPv6 allocations the tunnel space is drawn from |
| `api` | Programmatic provisioning/management |
| `services` | Extras beyond plain tunnels: `transit`, `anycast`, `static_ips`, `ix_peering` |
| `since` / `until` | Activity window (`until` for discontinued providers) |
| `status` / `type` / `public` / `signup_verification` | Same semantics as `dnsservices.json` |
| `jurisdiction` | ISO country of the provider's legal seat; hand-curated (no `hosted`/`cloud` fields here) |


## JSON Schemas

All JSON data files are validated against schemas:

| Schema | Validates |
|--------|-----------|
| [schemas/mailservices.schema.json](schemas/mailservices.schema.json) | `mailservices.json` |
| [schemas/disposable-mail-hosts.schema.json](schemas/disposable-mail-hosts.schema.json) | `disposable-mail-hosts.json` |
| [schemas/dnsservices.schema.json](schemas/dnsservices.schema.json) | `dnsservices.json`, `dnsservices.full.json` |
| [schemas/dnsservices-candidates.schema.json](schemas/dnsservices-candidates.schema.json) | `dnsservices-candidates.json` |
| [schemas/jurisdiction-overrides.schema.json](schemas/jurisdiction-overrides.schema.json) | `data/jurisdiction_overrides.json` |
| [schemas/tunnelbrokers.schema.json](schemas/tunnelbrokers.schema.json) | `tunnelbrokers.json` |


## Scripts

| Script | Purpose |
|--------|---------|
| [scripts/check-mx.py](scripts/check-mx.py) | Resolve and validate MX records for mail services, update `mx_hosts` fields |
| [scripts/refresh_mail_hosts.py](scripts/refresh_mail_hosts.py) | Refresh `ip_addresses` in `disposable-mail-hosts.json` from live MX host A records (`--check` for CI staleness gate) |
| [scripts/mailservice-editor.py](scripts/mailservice-editor.py) | Add or update entries in `mailservices.json` |
| [scripts/validate_hostnames.py](scripts/validate_hostnames.py) | Validate that each line in a file is a valid domain name |
| [scripts/sort_json_keys.py](scripts/sort_json_keys.py) | Recursively sort JSON keys alphabetically |
| [scripts/import_dyndns_list.py](scripts/import_dyndns_list.py) | Daily import of alexandrosmagos/dyn-dns-list into `dnsservices.json` (capped) + regenerate `dnsservices.full.json` |
| [scripts/fetch_dns_candidates.py](scripts/fetch_dns_candidates.py) | Weekly fetch of upstream DNS lists → `dnsservices-candidates.json` staging file (NS/SOA-verified) |
| [scripts/update_geo_metadata.py](scripts/update_geo_metadata.py) | Monthly refresh of `hosted`/`cloud`/`jurisdiction` on both catalogs via free DB-IP Lite MMDBs + `data/jurisdiction_overrides.json` |
| [scripts/scan_jurisdiction_pages.py](scripts/scan_jurisdiction_pages.py) | Scan provider contact/terms/imprint/AGB pages for legal-seat signals (VAT IDs, legal forms, governing law, addresses) → candidate `jurisdiction` overrides for manual review |


## Validation & CI

Pre-commit hooks and GitHub Actions ensure data integrity:

- **JSON schema validation** via `check-jsonschema`
- **Key sorting** for consistent JSON formatting
- **Hostname validation** for plain-text lists
- **Automated deployment** of the web interface to GitHub Pages on every push to `master`


## Credits

`dnsservices.json` was built with help from these sources:

- [alexandrosmagos/dyn-dns-list](https://github.com/alexandrosmagos/dyn-dns-list) — scraped dynamic DNS provider domains, auto-imported daily
- [HaGeZi DNS blocklists](https://github.com/hagezi/dns-blocklists) — initial DynDNS domain seed; DynDNS list polled weekly into `dnsservices-candidates.json`
- [korlabsio/subdomain_providers](https://github.com/korlabsio/subdomain_providers) — categorized subdomain-provider index, polled weekly into `dnsservices-candidates.json`
- [binjoo/PublicFreeSuffix](https://github.com/binjoo/PublicFreeSuffix) — free NS-delegated suffixes, polled weekly into `dnsservices-candidates.json`
- [wdhdev/free-for-life](https://github.com/wdhdev/free-for-life) — free developer services list
- [WebSnifferHQ/subdomain-providers](https://github.com/WebSnifferHQ/subdomain-providers) — subdomain provider list
- [Public Suffix List](https://publicsuffix.org/) — private-section operator groups polled weekly into `dnsservices-candidates.json`
- [OpenWrt ddns-scripts](https://github.com/openwrt/packages/tree/master/net/ddns-scripts) — DDNS provider registry polled weekly into `dnsservices-candidates.json`
- [DB-IP Lite](https://db-ip.com) — free IP geolocation and ASN databases (CC BY 4.0) used for `hosted`/`cloud` fields, refreshed monthly by `update_geo_metadata.py`
- Wikipedia tunnel broker lists ([de](https://de.wikipedia.org/wiki/Liste_von_IPv6-Tunnelbrokern), [zh](https://zh.wikipedia.org/wiki/IPv6隧道中间人列表), [es](https://es.wikipedia.org/wiki/Anexo:Proveedores_de_túneles_IPv6)) - provider seed for `tunnelbrokers.json`


## License

See [LICENSE](LICENSE).