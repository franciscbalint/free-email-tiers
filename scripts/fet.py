#!/usr/bin/env python3
"""Checks and builds the Free Email Tiers list.

    python3 scripts/fet.py validate              # schema + duplicate checks for every service file
    python3 scripts/fet.py evidence [FILES...]   # fetch pages, confirm the evidence quote is on the pricing page
    python3 scripts/fet.py build                 # regenerate README.md from services/*.yaml
    python3 scripts/fet.py site [DIR]            # build the GitHub Pages site (default: _site/)
    python3 scripts/fet.py vendor-check PR_AUTHOR FILE...   # is the PR author verified for these vendors?

Needs Python 3.10+ and PyYAML.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SERVICES = ROOT / "services"
README = ROOT / "README.md"
INTRO = ROOT / "meta" / "intro.md"
OUTRO = ROOT / "meta" / "outro.md"
OPT_OUT = ROOT / "meta" / "opt-out.txt"
SITE = ROOT / "meta" / "site.html"

USER_AGENT = "Mozilla/5.0 (compatible; free-email-tiers-checker/1.0; +https://github.com/franciscbalint/free-email-tiers)"
TXT_RECORD = "_free-email-tiers"

CATEGORIES = {
    "verification": "Email verification",
    "sending": "Sending (SMTP and API)",
    "receiving": "Receiving and forwarding",
    "testing": "Testing and sandboxes",
    "authentication": "Authentication and deliverability monitoring",
}

REQUIRED = {
    "name": str,
    "website": str,
    "category": str,
    "description": str,
    "free": dict,
    "evidence": dict,
    "privacy_policy": str,
    "vendor": dict,
}
OPTIONAL = {"maintainer_affiliated": bool}
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
BANNED_WORDS = re.compile(r"\b(best|leading|#1|number one|world'?s|revolutionary|cutting[- ]edge|ultimate)\b", re.I)


# ---------------------------------------------------------------- loading

def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError("file must contain a YAML mapping")
    return data


def service_files() -> list[Path]:
    return sorted(SERVICES.glob("*.yaml"))


# ---------------------------------------------------------------- validate

def problems_for(path: Path, data: dict) -> list[str]:
    out = []
    if not SLUG.match(path.stem):
        out.append("file name must be lowercase-with-dashes.yaml")
    for key, kind in REQUIRED.items():
        if key not in data:
            out.append(f"missing `{key}`")
        elif not isinstance(data[key], kind):
            out.append(f"`{key}` must be a {kind.__name__}")
    for key in data:
        if key not in REQUIRED and key not in OPTIONAL:
            out.append(f"unknown key `{key}`")
    for key, kind in OPTIONAL.items():
        if key in data and not isinstance(data[key], kind):
            out.append(f"`{key}` must be true or false")
    if any(key not in data or not isinstance(data[key], kind) for key, kind in REQUIRED.items()):
        return out  # the checks below need every required field present

    if data["category"] not in CATEGORIES:
        out.append(f"`category` must be one of: {', '.join(CATEGORIES)}")
    for key in ("website", "privacy_policy"):
        if not data[key].startswith("https://"):
            out.append(f"`{key}` must be an https:// URL")

    desc = data["description"].strip()
    if len(desc) > 160:
        out.append("`description` must be 160 characters or fewer")
    if not desc.endswith("."):
        out.append("`description` must be one sentence ending with a full stop")
    if BANNED_WORDS.search(desc):
        out.append("`description` must be factual; drop marketing words like 'best' or 'leading'")

    free = data["free"]
    if not isinstance(free.get("allowance"), str) or not free["allowance"].strip():
        out.append("`free.allowance` is required, e.g. '100 verifications per month'")
    elif not re.search(r"\d|unlimited|no limit stated", free["allowance"], re.I):
        out.append("`free.allowance` must state an amount: a number, 'unlimited', or 'no limit stated'")
    if "conditions" in free and free["conditions"] is not None and not isinstance(free["conditions"], str):
        out.append("`free.conditions` must be text or omitted")
    if set(free) - {"allowance", "conditions"}:
        out.append("`free` only takes `allowance` and `conditions`")

    ev = data["evidence"]
    if not str(ev.get("url", "")).startswith("https://"):
        out.append("`evidence.url` must be the https:// pricing page")
    quote = ev.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        out.append("`evidence.quote` is required: a short exact phrase from the pricing page")
    elif len(quote.split()) > 15:
        out.append("`evidence.quote` must be 15 words or fewer")
    checked = ev.get("checked")
    if not isinstance(checked, dt.date):
        out.append("`evidence.checked` must be a date like 2026-11-11")
    elif checked > dt.date.today() + dt.timedelta(days=1):
        out.append("`evidence.checked` is in the future")
    if set(ev) - {"url", "quote", "checked"}:
        out.append("`evidence` only takes `url`, `quote` and `checked`")

    vendor = data["vendor"]
    domains = vendor.get("domains")
    if not isinstance(domains, list) or not domains or not all(isinstance(d, str) for d in domains):
        out.append("`vendor.domains` must list the vendor's email domains, e.g. [example.com]")
    elif any("/" in d or d.startswith("www.") for d in domains):
        out.append("`vendor.domains` takes bare domains like example.com")
    org = vendor.get("github_org")
    if org is not None and not (isinstance(org, str) and re.fullmatch(r"[A-Za-z0-9-]+", org)):
        out.append("`vendor.github_org` must be a GitHub organization login or null")
    if set(vendor) - {"domains", "github_org"}:
        out.append("`vendor` only takes `domains` and `github_org`")
    return out


def host(url: str) -> str:
    h = urllib.parse.urlsplit(url).hostname or ""
    return h.removeprefix("www.")


def site_key(url: str) -> str:
    # One vendor can list several products, so compare host and path, not just the host.
    parts = urllib.parse.urlsplit(url)
    return host(url) + parts.path.rstrip("/").lower()


def opted_out() -> set[str]:
    if not OPT_OUT.exists():
        return set()
    lines = (l.split("#", 1)[0].strip().casefold() for l in OPT_OUT.read_text(encoding="utf-8").splitlines())
    return {l for l in lines if l}


def cmd_validate(_args: list[str]) -> int:
    failed = False
    seen_names: dict[str, Path] = {}
    seen_hosts: dict[str, Path] = {}
    blocked = opted_out()
    for path in service_files():
        rel = path.relative_to(ROOT)
        try:
            data = load(path)
        except Exception as exc:  # noqa: BLE001 - report any parse error
            print(f"::error file={rel}::cannot read YAML: {exc}")
            failed = True
            continue
        for msg in problems_for(path, data):
            print(f"::error file={rel}::{msg}")
            failed = True
        name = str(data.get("name", "")).casefold()
        site = host(str(data.get("website", "")))
        key = site_key(str(data.get("website", "")))
        if name in seen_names:
            print(f"::error file={rel}::duplicate of {seen_names[name].name}")
            failed = True
        if key and key in seen_hosts:
            print(f"::error file={rel}::same website as {seen_hosts[key].name}")
            failed = True
        if any(site == d or site.endswith("." + d) for d in blocked):
            print(f"::error file={rel}::this vendor asked not to be listed (meta/opt-out.txt)")
            failed = True
        seen_names[name] = path
        seen_hosts[key] = path
    if not failed:
        print(f"ok: {len(service_files())} service files valid")
    return 1 if failed else 0


# ---------------------------------------------------------------- evidence

def fetch_once(url: str, timeout: int) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(5_000_000).decode(resp.headers.get_content_charset() or "utf-8", "replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, ""


def fetch(url: str, timeout: int = 30) -> tuple[int, str]:
    # Sites rate-limit or hiccup; retry once before calling it a failure.
    try:
        status, body = fetch_once(url, timeout)
        if status in (403, 429) or status >= 500:
            raise urllib.error.URLError(f"HTTP {status}")
        return status, body
    except (urllib.error.URLError, TimeoutError):
        time.sleep(10)
        return fetch_once(url, timeout)


def normalise(text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.translate(str.maketrans({" ": " ", "’": "'", "‘": "'", "“": '"',
                                          "”": '"', "–": "-", "—": "-", " ": " "}))
    return re.sub(r"\s+", " ", text).strip().casefold()


def check_evidence(path: Path) -> list[str]:
    data = load(path)
    out = []
    for key, url in (("website", data["website"]), ("privacy_policy", data["privacy_policy"])):
        try:
            status, _ = fetch(url)
        except Exception as exc:  # noqa: BLE001
            out.append(f"`{key}` could not be fetched: {exc}")
            continue
        if status >= 400:
            out.append(f"`{key}` returned HTTP {status}")
    ev = data["evidence"]
    try:
        status, body = fetch(ev["url"])
    except Exception as exc:  # noqa: BLE001
        return out + [f"`evidence.url` could not be fetched: {exc}"]
    if status >= 400:
        return out + [f"`evidence.url` returned HTTP {status}"]
    if normalise(ev["quote"]) not in normalise(body):
        out.append(f"`evidence.quote` not found on {ev['url']} (the page may have changed, or prices load with JavaScript)")
    return out


def cmd_evidence(args: list[str]) -> int:
    paths = [ROOT / a for a in args if a.endswith(".yaml") and (ROOT / a).exists()] if args else service_files()
    failed = []
    for path in paths:
        rel = path.relative_to(ROOT)
        msgs = check_evidence(path)
        for msg in msgs:
            print(f"::error file={rel}::{msg}")
        if msgs:
            failed.append(str(rel))
        else:
            print(f"ok: {rel}")
    if failed:
        print(f"\n{len(failed)} of {len(paths)} failed: {', '.join(failed)}")
    return 1 if failed else 0


# ---------------------------------------------------------------- build

def entry_line(data: dict) -> str:
    name = data["name"] + (" ‡" if data.get("maintainer_affiliated") else "")
    line = f"- **[{name}]({data['website']})** - {data['description'].strip()} **Free:** {data['free']['allowance'].strip()}."
    cond = (data["free"].get("conditions") or "").strip()
    if cond:
        line += f" _{cond.rstrip('.')}._"
    ev = data["evidence"]
    line += f" <sub>[source]({ev['url']}), checked {ev['checked'].isoformat()}</sub>"
    return line


def anchor(title: str) -> str:
    return re.sub(r"[^a-z0-9 -]", "", title.lower()).replace(" ", "-")


def render() -> str:
    by_cat: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for path in service_files():
        data = load(path)
        by_cat[data["category"]].append(data)
    parts = [INTRO.read_text(encoding="utf-8").rstrip(), "", "## Contents", ""]
    for cat, title in CATEGORIES.items():
        if by_cat[cat]:
            parts.append(f"- [{title}](#{anchor(title)}) ({len(by_cat[cat])})")
    for cat, title in CATEGORIES.items():
        if not by_cat[cat]:
            continue
        parts += ["", f"## {title}", ""]
        parts += [entry_line(d) for d in sorted(by_cat[cat], key=lambda d: d["name"].casefold())]
    parts += ["", OUTRO.read_text(encoding="utf-8").rstrip(), ""]
    return "\n".join(parts)


def cmd_build(args: list[str]) -> int:
    text = render()
    if "--check" in args:
        if not README.exists() or README.read_text(encoding="utf-8") != text:
            print("README.md is out of date: run `python3 scripts/fet.py build`")
            return 1
        print("ok: README.md is up to date")
        return 0
    README.write_text(text, encoding="utf-8")
    print(f"wrote {README.relative_to(ROOT)}")
    return 0


def site_data() -> dict:
    services = []
    for path in service_files():
        d = load(path)
        services.append({
            "slug": path.stem, "name": d["name"], "website": d["website"], "category": d["category"],
            "description": d["description"].strip(), "allowance": d["free"]["allowance"].strip(),
            "conditions": (d["free"].get("conditions") or "").strip() or None,
            "source": d["evidence"]["url"], "checked": d["evidence"]["checked"].isoformat(),
            "affiliated": bool(d.get("maintainer_affiliated")),
        })
    services.sort(key=lambda s: s["name"].casefold())
    return {
        "built": dt.date.today().isoformat(),
        "categories": [{"key": k, "title": v} for k, v in CATEGORIES.items()],
        "services": services,
    }


def cmd_site(args: list[str]) -> int:
    out = Path(args[0]) if args else ROOT / "_site"
    out.mkdir(parents=True, exist_ok=True)
    data = site_data()
    blob = json.dumps(data, ensure_ascii=False)
    # The JSON sits inside a <script> tag, so a literal "</" must not appear in it.
    page = SITE.read_text(encoding="utf-8").replace("/*DATA*/", blob.replace("</", "<\\/"))
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}/index.html and data.json ({len(data['services'])} services)")
    return 0


# ---------------------------------------------------------------- vendor verification

def is_public_member(org: str, user: str) -> bool:
    # 204 = public member, 404 = not a public member. No token needed.
    req = urllib.request.Request(f"https://api.github.com/orgs/{org}/public_members/{user}",
                                 headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status == 204
    except urllib.error.HTTPError:
        return False


def txt_records(name: str) -> list[str]:
    url = "https://cloudflare-dns.com/dns-query?" + urllib.parse.urlencode({"name": name, "type": "TXT"})
    req = urllib.request.Request(url, headers={"Accept": "application/dns-json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        answer = json.load(resp).get("Answer") or []
    # TXT data comes back quoted and may be split into several strings.
    return ["".join(re.findall(r'"([^"]*)"', a.get("data", ""))) or a.get("data", "") for a in answer if a.get("type") == 16]


def vendor_proof(data: dict, user: str) -> str | None:
    org = data["vendor"].get("github_org")
    if org and is_public_member(org, user):
        return f"@{user} is a public member of the {org} GitHub organization"
    want = f"github={user}".casefold()
    for domain in data["vendor"]["domains"]:
        try:
            records = txt_records(f"{TXT_RECORD}.{domain}")
        except Exception:  # noqa: BLE001 - DNS failure just means no proof
            continue
        if any(r.strip().casefold() == want for r in records):
            return f"DNS TXT record {TXT_RECORD}.{domain} names @{user}"
    return None


def cmd_vendor_check(args: list[str]) -> int:
    """Print a JSON verdict. FILEs are base-branch copies of the service files the PR changes."""
    if len(args) < 2:
        print("usage: fet.py vendor-check PR_AUTHOR FILE...", file=sys.stderr)
        return 2
    user, files = args[0], args[1:]
    results = []
    for f in files:
        path = Path(f)
        if not path.exists():
            continue  # a brand-new file: nothing to verify against
        data = load(path)
        results.append({"file": path.name, "vendor": data["name"], "proof": vendor_proof(data, user)})
    verified = bool(results) and all(r["proof"] for r in results)
    print(json.dumps({"author": user, "verified": verified, "results": results}, indent=2))
    return 0


COMMANDS = {"validate": cmd_validate, "evidence": cmd_evidence, "build": cmd_build, "site": cmd_site, "vendor-check": cmd_vendor_check}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]))
