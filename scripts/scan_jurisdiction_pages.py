#!/usr/bin/env python3
"""Scan provider legal/contact pages for legal-seat (jurisdiction) signals.

Fetches each uncovered provider's homepage footer plus /contact, /about,
/terms, /impressum, /agb, /privacy-style paths and scores country evidence:

- registration IDs (VAT prefixes, SIREN/RCS, KRS, IČO, Companies House, ...)
- legal entity forms (GmbH, LLC, s.r.o., OÜ, SIA, Pty Ltd, Sdn Bhd, ...)
- governing-law / jurisdiction clauses
- "located/registered/based in <country>" phrases
- address lines ending in a country name
- bare country names (weak signal only)

Results are printed as candidate additions for
data/jurisdiction_overrides.json - review before merging; the scanner only
accepts a country when a structural signal (reg/form/govlaw/locphrase/address)
wins with a clear lead over the runner-up.

Usage: python scripts/scan_jurisdiction_pages.py [provider-key ...]
Without arguments it scans every catalog provider lacking `jurisdiction`.
"""

import concurrent.futures as cf
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
PATHS = ["", "contact", "contact-us", "about", "about-us", "company",
         "impressum", "imprint", "legal", "legal-notice", "terms",
         "terms-of-service", "tos", "agb", "privacy", "privacy-policy",
         "mentions-legales", "legalnotice"]

COUNTRIES = {
    'germany': 'DE', 'deutschland': 'DE', 'austria': 'AT', 'österreich': 'AT',
    'switzerland': 'CH', 'schweiz': 'CH', 'france': 'FR', 'united kingdom': 'GB',
    'england': 'GB', 'scotland': 'GB', 'ireland': 'IE', 'netherlands': 'NL',
    'holland': 'NL', 'belgium': 'BE', 'luxembourg': 'LU', 'spain': 'ES',
    'españa': 'ES', 'italy': 'IT', 'italia': 'IT', 'portugal': 'PT',
    'poland': 'PL', 'polska': 'PL', 'czech republic': 'CZ', 'czechia': 'CZ',
    'slovakia': 'SK', 'hungary': 'HU', 'romania': 'RO', 'bulgaria': 'BG',
    'greece': 'GR', 'croatia': 'HR', 'slovenia': 'SI', 'serbia': 'RS',
    'ukraine': 'UA', 'russia': 'RU', 'sweden': 'SE', 'norway': 'NO',
    'denmark': 'DK', 'finland': 'FI', 'estonia': 'EE', 'latvia': 'LV',
    'lithuania': 'LT', 'iceland': 'IS', 'united states': 'US', 'usa': 'US',
    'u.s.': 'US', 'canada': 'CA', 'australia': 'AU', 'new zealand': 'NZ',
    'japan': 'JP', 'singapore': 'SG', 'india': 'IN', 'hong kong': 'HK',
    'china': 'CN', 'taiwan': 'TW', 'south korea': 'KR', 'brazil': 'BR',
    'brasil': 'BR', 'israel': 'IL', 'turkey': 'TR', 'cyprus': 'CY',
    'malta': 'MT', 'liechtenstein': 'LI', 'monaco': 'MC', 'seychelles': 'SC',
    'mauritius': 'MU', 'panama': 'PA', 'malaysia': 'MY', 'indonesia': 'ID',
    'vietnam': 'VN', 'thailand': 'TH', 'philippines': 'PH',
    'united arab emirates': 'AE', 'uae': 'AE', 'south africa': 'ZA',
    'mexico': 'MX', 'argentina': 'AR', 'chile': 'CL', 'colombia': 'CO',
    'peru': 'PE', 'uruguay': 'UY', 'costa rica': 'CR', 'moldova': 'MD',
    'georgia': 'GE', 'armenia': 'AM', 'nigeria': 'NG', 'kenya': 'KE',
    'albania': 'AL', 'north macedonia': 'MK', 'montenegro': 'ME',
    'bosnia': 'BA', 'ghana': 'GH', 'jordan': 'JO', 'egypt': 'EG',
    'morocco': 'MA', 'tunisia': 'TN', 'isle of man': 'IM', 'jersey': 'JE',
    'guernsey': 'GG', 'kosovo': 'XK', 'belarus': 'BY', 'kazakhstan': 'KZ',
    'pakistan': 'PK', 'bangladesh': 'BD', 'sri lanka': 'LK', 'qatar': 'QA',
    'kuwait': 'KW', 'saudi arabia': 'SA', 'ecuador': 'EC', 'paraguay': 'PY',
    'dominican republic': 'DO', 'gibraltar': 'GI', 'andorra': 'AD',
    'namibia': 'NA', 'curacao': 'CW', 'curaçao': 'CW', 'cayman islands': 'KY',
    'puerto rico': 'PR', 'san marino': 'SM',
}

ISO = set(COUNTRIES.values())

# legal-form patterns -> unambiguous cc, or ambiguity set resolved via AMBIG
FORMS = [
    (r'\bGmbH\b', 'DACH', 2), (r'\bAG\b', 'DACH', 1),
    (r'\bLLC\b|\bL\.L\.C\.\b', 'US', 3),
    (r'\bInc\.?\b|\bIncorporated\b|\bCorp(?:oration)?\.?\b', 'US', 2),
    (r'\bLtd\.?\b|\bLimited\b', 'COMMON', 1), (r'\bPLC\b', 'GBIE', 2),
    (r'\bPty\.?\s*Ltd\.?\b', 'AUZA', 4),
    (r'\bS\.?A\.?R\.?L\.?\b|\bEURL\b|\bSASU\b|\bSNC\b|\bSCI\b', 'FR', 4),
    (r'\bSAS\b|\bS\.A\.S\.\b', 'FR', 4),
    (r'\bB\.?V\.?\b', 'NL', 4), (r'\bV\.O\.F\.\b|\bmaatschap\b', 'NL', 3),
    (r'\bBVBA\b|\bSPRL\b|\bsprl\b', 'BE', 4),
    (r'\bs\.?r\.?o\.?\b|\bspol\.?\s*s\s*r\.?\s*o\.?\b', 'CZSK', 4),
    (r'\bsp\.?\s*z\s*o\.?\s*o\.?\b|\bSpółka\b', 'PL', 4),
    (r'\bKft\.?\b|\bZrt\.?\b|\bBt\.?\b|\bKkt\.?\b', 'HU', 4),
    (r'\bs\.r\.l\.?\b|\bS\.p\.A\.\b|\bSpA\b', 'IT', 4),
    (r'\bd\.o\.o\.?\b|\bd\.d\.?\b', 'EXYU', 3), (r'\bs\.p\.?\b', 'SI', 2),
    (r'\bOÜ\b', 'EE', 5), (r'\bSIA\b', 'LV', 5), (r'\bUAB\b', 'LT', 5),
    (r'\bAB\b|\bAktiebolag\b', 'SE', 3), (r'\bApS\b|\bIVS\b|\bS/I\b', 'DK', 4),
    (r'\bA/S\b|\bANS\b', 'NODK', 2), (r'\bOy\b|\bOsakeyhtiö\b', 'FI', 4),
    (r'\behf\.?\b', 'IS', 4),
    (r'\bS\.L\.?U?\.?\b', 'ES', 3), (r'\bLda\.?\b|\bUnipessoal\b', 'PT', 4),
    (r'\bEOOD\b|\bOOD\b|\bЕООД\b', 'BG', 4),
    (r'\bIKE\b|\bΙΚΕ\b', 'GR', 4),
    (r'\bFZ-?LLC\b|\bFZE\b|\bDMCC\b|\bFZCO\b', 'AE', 4),
    (r'\bSdn\.?\s*Bhd\.?\b', 'MY', 5), (r'\bPte\.?\s*Ltd\.?\b', 'SG', 4),
    (r'\bPvt\.?\s*Ltd\.?\b', 'IN', 4),
    (r'\bKabushiki[- ]?Kaisha\b|\bK\.K\.\b|\bG\.K\.\b', 'JP', 4),
    (r'\bSA de CV\b|\bS\.A\. de C\.V\.\b', 'MX', 5),
    (r'\bLtda\.?\b|\bLTDA\b|\bEIRELI\b|\bMEI\b', 'BR', 4),
    (r'\bOOO\b|\bООО\b|\bЗАО\b|\bОАО\b|\bИП\b', 'RU', 3),
    (r'\bТОВ\b|\bФОП\b', 'UA', 4),
    (r'\be\.U\.\b|\beingetragener Verein\b|\be\.V\.\b', 'DE', 3),
    (r'\bry\b(?=[ ,.])', 'FI', 2), (r'\bAPS\b', 'DK', 1),
]

AMBIG = {
    'DACH': ['DE', 'AT', 'CH'], 'COMMON': ['GB', 'IE', 'AU', 'NZ', 'CA'],
    'GBIE': ['GB', 'IE'], 'AUZA': ['AU', 'ZA'], 'CZSK': ['CZ', 'SK'],
    'EXYU': ['HR', 'SI', 'RS'], 'NODK': ['NO', 'DK'], 'HRSI': ['HR', 'SI'],
}

# registration/company-id patterns -> cc (unambiguous, high confidence)
REG = [
    (r'\bSIREN\b|\bSIRET\b|\bRCS\b[^.]{0,40}paris', 'FR'),
    (r'\bP\.?\s*IVA\b|\bpartita iva\b', 'IT'),
    (r'\bKRS\b\s*\d|\bREGON\b', 'PL'), (r'\bNIP\b[\s:]*\d{3}', 'PL'),
    (r'\bIČO\b|\bIČ\s*:?\s*\d{7,8}\b', 'CZ'), (r'\bDIČ\b', 'SK'),
    (r'\bCVR\b[\s:]*\d', 'DK'),
    (r'\bCompanies House\b|\bregistered in (?:England|Wales|Scotland)\b', 'GB'),
    (r'\bABN\b[\s:]*\d{2}[\s]*\d{3}', 'AU'), (r'\bACN\b[\s:]*\d{3}', 'AU'),
    (r'\bNZBN\b', 'NZ'),
    (r'\bKVK\b|\bKvK[\s:-]*(?:nummer)?[\s:]*\d', 'NL'),
    (r'\bondernemingsnummer\b|\bBCE[-\s]?\d', 'BE'),
    (r'\bHRB\s*\d|\bHRA\s*\d', 'DE'), (r'\bFirmenbuch\b|\bFN\s*\d{5}', 'AT'),
    (r'\bCHE[-\s]?\d{3}', 'CH'),
    (r'\bRegistro Mercantil\b|\bCIF\b[\s:]*[A-Z]\d', 'ES'),
    (r'\bRegistre du commerce\b', 'FR'), (r'\bRCSL?\b', 'LU'),
    (r'\bONRC\b|\bnumăr de înregistrare\b|\bCUI\b[\s:]*(?:RO)?\s*\d', 'RO'),
    (r'\bЕИК\b|\bBULSTAT\b', 'BG'), (r'\bΓ\.?Ε\.?Μ\.?Η\.?\b|\bΑΦΜ\b', 'GR'),
    (r'\bOIB\b[\s:]*\d', 'HR'), (r'\bMBS\b[\s:]*\d', 'HRSI'),
    (r'\badószám\b|\bcégjegyzékszám\b', 'HU'),
    (r'\bY-tunnus\b|\bFO-number\b', 'FI'),
    (r'\bCNPJ\b[\s:]*\d', 'BR'), (r'\bGSTIN\b', 'IN'), (r'\bUEN\b', 'SG'),
    (r'\bEIN\b[\s:]*\d{2}-\d{7}', 'US'), (r'\bSecretary of State\b', 'US'),
    (r'\bDelaware\s+(?:LLC|corporation|corp)\b|\bincorporated in Delaware\b', 'US'),
    (r'\bBN\b[\s:]*\d{9}[A-Z]{2}\d{4}', 'CA'),
    (r'\b法人番号\b', 'JP'), (r'\b统[一一]社会信用代码\b', 'CN'),
    (r'\bRFC\b[\s:]*[A-Z]{3,4}\d', 'MX'), (r'\bNIT\b[\s:]*\d', 'CO'),
    (r'\bTRN\b[\s:]*\d{15}', 'AE'),
    (r'\bICO\b[\s:]*\d{8}\b', 'CZ'), (r'\bOrg\.?\s*nr\.?\b', 'SE'),
    (r'\bMVA\b[\s:]*\d', 'NO'), (r'\bSE[- ]?(?:nummer|nr)\b', 'DK'),
]

VAT_RE = re.compile(
    r'\b(?:VAT|USt|MwSt|UID|TVA|IVA|BTW|MVA|Moms|DPH|PID|VATIN|GST)'
    r'[\s:#.-]*(?:ID|no\.?|nr\.?|number|ue)?[\s:#.-]*'
    r'([A-Z]{2})\s*[\dA-Z]{5,}', re.I)

GOV_RE = re.compile(
    r'(?:governed by|laws of|courts? of|exclusive jurisdiction|'
    r'place of jurisdiction|Gerichtsstand|loi[s]?\s+de|droit '
    r'(?:français|belge|luxembourgeois)|leyes de|legge|diritto|'
    r'wet van|wetgeving)[^.\n]{0,80}', re.I)

LOC_RE = re.compile(
    r'(?:located|registered|based|incorporated|established|headquartered|'
    r'domiciled|residing|headquarters? (?:in|at)|sitz|siège|sede|zetel|'
    r'seat|maatschappelijke zetel)[^.\n]{0,70}', re.I)

ADDR_RE = re.compile(
    r'(?:street|str\.|straße|straat|rue|via |road|avenue|ave\.?|lane|drive|'
    r'blvd|boulevard|platz|plein|gasse|weg|utca|tér|address|adresse|adres|'
    r'indirizzo|dirección|adresă|adresa|office|po box|p\.o\. box)'
    r'\b[^.]{10,140}', re.I)


def fetch(domain, path):
    url = f"https://{domain}/{path}"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            if r.status != 200:
                return None
            if 'html' not in r.headers.get('content-type', ''):
                return None
            return r.read(600_000).decode('utf-8', errors='replace')
    except Exception:
        return None


def textify(h):
    h = re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>|<!--[\s\S]*?-->', ' ', h)
    h = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', html.unescape(h))


def scan(key):
    votes = {}
    scanned = 0

    def add(cc, w, why):
        if cc not in ISO:
            return
        e = votes.setdefault(cc, [0.0, set()])
        e[0] += w
        e[1].add(why)

    for path in PATHS:
        body = fetch(key, path)
        if not body:
            continue
        scanned += 1
        t = textify(body)
        # homepage: only the tail (footer) usually carries the address
        seg = t if path else t[-6000:]
        segl = seg.lower()
        prio = 1.0 if path else 0.7

        for pat, res in REG:
            if re.search(pat, seg, re.I):
                for cc in AMBIG.get(res, [res]):
                    add(cc, 5 * prio, 'reg')

        m = VAT_RE.search(seg)
        if m and m.group(1).upper() in ISO:
            add(m.group(1).upper(), 6 * prio, 'vatid')

        for pat, res, w in FORMS:
            if re.search(pat, seg):
                for cc in AMBIG.get(res, [res]):
                    add(cc, w * prio / len(AMBIG.get(res, ['x'])), 'form')

        for regex, w, why in ((GOV_RE, 5, 'govlaw'), (LOC_RE, 4, 'locphrase'),
                              (ADDR_RE, 4, 'address')):
            for m in regex.finditer(segl):
                frag = m.group(0)
                for name, cc in COUNTRIES.items():
                    if re.search(r'\b' + re.escape(name) + r'\b', frag):
                        add(cc, w * prio, why)
                        break

        for name, cc in COUNTRIES.items():
            c = len(re.findall(r'\b' + re.escape(name) + r'\b', segl))
            if c:
                add(cc, min(c, 3) * 0.5 * prio, 'name')
        if scanned >= 6:
            break
    return votes


def best(votes):
    if not votes:
        return None, 0, []
    ranked = sorted(votes.items(), key=lambda kv: -kv[1][0])
    (cc, (w, whys)) = ranked[0]
    second = ranked[1][1][0] if len(ranked) > 1 else 0
    strong = whys & {'reg', 'vatid', 'govlaw', 'locphrase', 'address'}
    if w >= 5 and w >= second * 1.5 and strong:
        return cc, round(w, 1), sorted(whys)
    return None, round(w, 1), sorted(whys)


def main():
    keys = sys.argv[1:]
    if not keys:
        for name in ('dnsservices.json', 'mailservices.json'):
            cat = json.loads((REPO / name).read_text(encoding='utf-8'))
            keys += [k for k, v in cat.items() if not v.get('jurisdiction')]
        keys = sorted(set(keys))
    print(f'scanning {len(keys)} providers', file=sys.stderr)

    results = {}
    done = 0
    with cf.ThreadPoolExecutor(max_workers=16) as pool:
        futs = {pool.submit(scan, k): k for k in keys}
        for f in cf.as_completed(futs):
            k = futs[f]
            votes = f.result()
            cc, w, whys = best(votes)
            results[k] = {'cc': cc, 'weight': w, 'signals': whys,
                          'top': sorted(((c, round(v[0], 1)) for c, v in
                                         votes.items()), key=lambda x: -x[1])[:3]}
            done += 1
            if done % 50 == 0:
                print(f'{done}/{len(keys)}', file=sys.stderr, flush=True)

    found = {k: v for k, v in results.items() if v['cc']}
    print(f'\n# {len(found)} candidate overrides (review before merging):')
    print(json.dumps({k: v['cc'] for k, v in sorted(found.items())},
                     indent=1, ensure_ascii=False))
    print(json.dumps(results, indent=1, ensure_ascii=False),
          file=open('/tmp/jurisdiction_scan_detail.json', 'w'))


if __name__ == '__main__':
    main()
