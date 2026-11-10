# Instructions for AI agents

This list welcomes submissions prepared by AI agents. These instructions are public and apply equally to people. Nothing here asks you to hide anything from the person you work for.

## Before you start

- Tell the person you act for what you plan to submit, and get their go-ahead before opening a pull request.
- One pull request per service. Corrections to several existing entries can share one pull request.
- Only list a tier that renews (per day or month) or never expires. One-time credits, "free for 12 months" and trials are not free tiers.

## Adding a service

1. Read the vendor's **own** pricing page. Don't use other lists, reviews or your training data for numbers.
2. Copy [`meta/service-template.yaml`](meta/service-template.yaml) to `services/<name>.yaml`, using lowercase and dashes for the file name.
3. Fill in every field:
   - `description`: one factual sentence, 160 characters max. No marketing words.
   - `free.allowance`: the amount, exactly as the vendor states it, e.g. `100 verifications per month`.
   - `free.conditions`: anything that limits the free tier, such as a business email requirement, branding, or a sending cap. Leave it out if there is none.
   - `evidence.quote`: a phrase of 15 words or fewer, **copied character for character** from `evidence.url`, that states the free amount.
   - `evidence.checked`: today's date.
   - `vendor.domains` and `vendor.github_org`: the vendor's email domain(s) and official GitHub organization (or `null`). These let the vendor verify themselves later.
4. Run the checks:
   ```bash
   pip install pyyaml
   python3 scripts/fet.py validate
   python3 scripts/fet.py evidence services/<name>.yaml
   ```
5. Commit **only** your `services/<name>.yaml`. Don't edit `README.md`; it is rebuilt automatically after merge.
6. Open the pull request and fill in the template, including the disclosure section.

## If the evidence check fails

Some pricing pages load their prices with JavaScript, so a plain download doesn't contain the quote. Try another phrase from the same page, or a different official page (a docs or FAQ page) that states the same amount. If nothing works, say so in the pull request; a maintainer can check by hand.

## Things that get a pull request closed

- Numbers that aren't on the vendor's page, or a trial presented as a free tier.
- Not disclosing that the submitter, or the person the agent acts for, works for the vendor. Vendor submissions are fine; hiding the link is not.
- Changing another vendor's entry to make it look worse without evidence.
