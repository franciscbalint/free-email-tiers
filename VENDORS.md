# For vendors: corrections and removal

If you run a listed service, you can change or remove its entry. You need to show that you speak for the vendor, using **any one** of these:

## 1. A pull request from your company's GitHub organization (fastest)

Open a pull request that edits or deletes `services/<your-service>.yaml`, from a GitHub account that is a **public** member of the organization named in that file's `vendor.github_org`.

A bot checks the membership and labels the pull request `vendor-verified`. If your membership is private, make it public under your organization's **People** page first. You can hide it again afterwards.

## 2. A DNS record on your domain

Add this TXT record to one of the domains in the entry's `vendor.domains`:

| Name | Value |
| --- | --- |
| `_free-email-tiers.yourdomain.com` | `github=<your-github-username>` |

Then open the pull request from that GitHub account. The bot finds the record and labels the pull request `vendor-verified`. You can delete the record once the pull request is merged.

## 3. Email

Email **hello@franciscbalint.com** from an address at one of the domains in `vendor.domains`. Say which entry it is and what should change, or that you want it removed. This is handled by hand.

## What happens next

- **Removal:** verified removal requests are always accepted. Your domain is added to `meta/opt-out.txt` so the entry isn't added again by someone else. Ask the same way to be listed again.
- **Corrections:** verified corrections are merged once the evidence check passes, meaning the new amount appears on your pricing page.
- **Wrong or changed free tier:** if you dropped your free tier, tell us and the entry is removed. No proof needed for that.

Unverified requests are still welcome. They just need a link to your pricing page showing the change.
