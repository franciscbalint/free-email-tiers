# Contributing

Thanks for helping. You can use an AI agent or do it by hand; the rules are the same and are written out in [AGENTS.md](AGENTS.md).

## The short version

1. Copy [`meta/service-template.yaml`](meta/service-template.yaml) to `services/<name>.yaml` and fill it in from the vendor's own pricing page.
2. Optional, but it saves a round trip: run `python3 scripts/fet.py validate` and `python3 scripts/fet.py evidence services/<name>.yaml` (needs `pip install pyyaml`).
3. Open a pull request and fill in the template. Don't edit `README.md`; it is rebuilt after merge.

You can do all of this in the GitHub website: open `services/`, choose **Add file → Create new file**, paste the template, and GitHub will offer to open a pull request.

## What the checks do

Every pull request runs these automatically:

- **validate**: every file has the right fields, there are no duplicates, and the vendor hasn't opted out.
- **evidence**: downloads the website, privacy policy and pricing page, and confirms the quoted phrase is on the pricing page.

Every week the evidence check runs again on all entries and opens an issue listing anything that changed.

## Reporting a wrong entry

Open an issue with the entry name and a link showing the current free tier.

## Vendors

To correct or remove your own entry, see [VENDORS.md](VENDORS.md).
