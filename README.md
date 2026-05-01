# Static Disposable Lists

Static data repository for disposable email domains and mail service definitions that cannot be dynamically updated via the main [disposable](https://github.com/disposable/disposable) project.

**Web Interface:** [https://disposable.github.io/static-disposable-lists/](https://disposable.github.io/static-disposable-lists/)


## Data Files

| File | Description |
|------|-------------|
| [mailservices.json](mailservices.json) | Email service definitions with host and verification metadata |
| [disposable-mail-hosts.json](disposable-mail-hosts.json) | Disposable email host definitions with IP addresses and MX hosts |
| [mail-data-hosts-net.txt](mail-data-hosts-net.txt) | Hostnames from mx.mail-data.net |
| [manual.txt](manual.txt) | Manually curated list of disposable email domains |
| [free.txt](free.txt) / [free.csv](free.csv) | Free email provider domain lists |
| [domains.csv](domains.csv) | Domain classification data |
| [generator-email-hosts.txt](generator-email-hosts.txt) | Email generator service hostnames |


## JSON Schemas

All JSON data files are validated against schemas:

| Schema | Validates |
|--------|-----------|
| [schemas/mailservices.schema.json](schemas/mailservices.schema.json) | `mailservices.json` |
| [schemas/disposable-mail-hosts.schema.json](schemas/disposable-mail-hosts.schema.json) | `disposable-mail-hosts.json` |


## Scripts

| Script | Purpose |
|--------|---------|
| [scripts/check-mx.py](scripts/check-mx.py) | Resolve and validate MX records for mail services, update `mx_hosts` fields |
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