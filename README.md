# Static Disposable Lists

Static data repository for disposable email domains and mail service definitions that cannot be dynamically updated via the main [disposable](https://github.com/disposable/disposable) project.

**Web Interface:** [https://disposable.github.io/static-disposable-lists/](https://disposable.github.io/static-disposable-lists/) ([DNS Services](https://disposable.github.io/static-disposable-lists/dns.html))


## Data Files

| File | Description |
|------|-------------|
| [mailservices.json](mailservices.json) | Email service definitions with host and verification metadata; drives whitelist/strict-tier classification in disposable (see below) |
| [dnsservices.json](dnsservices.json) | Dynamic DNS / free hostname provider definitions: offered domains, pricing, update support, API, revalidation and signup metadata (see below) |
| [disposable-mail-hosts.json](disposable-mail-hosts.json) | Disposable mail-backend fingerprints: MX hostnames, hostname suffixes, IPv4 addresses and CIDR ranges used to attribute disposable domains to a provider |
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


## JSON Schemas

All JSON data files are validated against schemas:

| Schema | Validates |
|--------|-----------|
| [schemas/mailservices.schema.json](schemas/mailservices.schema.json) | `mailservices.json` |
| [schemas/disposable-mail-hosts.schema.json](schemas/disposable-mail-hosts.schema.json) | `disposable-mail-hosts.json` |
| [schemas/dnsservices.schema.json](schemas/dnsservices.schema.json) | `dnsservices.json` |


## Scripts

| Script | Purpose |
|--------|---------|
| [scripts/check-mx.py](scripts/check-mx.py) | Resolve and validate MX records for mail services, update `mx_hosts` fields |
| [scripts/refresh_mail_hosts.py](scripts/refresh_mail_hosts.py) | Refresh `ip_addresses` in `disposable-mail-hosts.json` from live MX host A records (`--check` for CI staleness gate) |
| [scripts/mailservice-editor.py](scripts/mailservice-editor.py) | Add or update entries in `mailservices.json` |
| [scripts/validate_hostnames.py](scripts/validate_hostnames.py) | Validate that each line in a file is a valid domain name |
| [scripts/sort_json_keys.py](scripts/sort_json_keys.py) | Recursively sort JSON keys alphabetically |


## Validation & CI

Pre-commit hooks and GitHub Actions ensure data integrity:

- **JSON schema validation** via `check-jsonschema`
- **Key sorting** for consistent JSON formatting
- **Hostname validation** for plain-text lists
- **Automated deployment** of the web interface to GitHub Pages on every push to `master`


## License

See [LICENSE](LICENSE).