# Plan: teach Omtal what a CDN does, and let it check a build before it ships

## The goal
A real audit of a live site (pompedozare.ro) surfaced three things Omtal could
not see on its own, and a person had to work out by hand. A CDN sits between the
site and the crawler and quietly rewrites what the crawler receives, so some
findings are the CDN's doing, not the site's. Omtal should recognise that, name
it, and stop reporting a CDN's own artifacts as if the site were broken. And a
person should be able to point Omtal at a build before it goes live, without the
audit failing for reasons that are only true locally. This plan adds those
without changing how any existing rule reads a normal site.

## What is needed
| Need | Where it comes from | How we get it | Have / missing |
|---|---|---|---|
| See response headers | the HTTP fetch | capture a small header subset in web.fetch | missing |
| Recognise a CDN and its artifacts | headers + page HTML | a detector in web.py, a check in checks.py | missing |
| Duplicate `User-agent: *` groups | robots.txt | keep group multiplicity in parse_robots | missing |
| Audit a local build honestly | the CLI | a pre-deploy flag that relabels HTTPS and remaps sitemap/robots hosts | missing |

## Where the tools and access are
All in this repo, standard library only. Checks return `(verdict, evidence,
provenance)`; rules are TOML that name a check; the grid assembles them. Nothing
online to borrow — this is engine-specific. The three findings that seeded this
came from the pompedozare.ro audit on 2026-09-09.

## Status: all three steps built, self-tested, and shown (2026-09-09)

- Step 1 done: live audit of pompedozare.ro now names Cloudflare and explains the
  email link; the spurious `cdn-cgi` page error is gone; site shows 0 RISK.
- Step 2 done: same audit flags the two `User-agent: *` groups and names the
  `/admin/` lines a strict crawler would skip.
- Step 3 done: a local build served over HTTP audits clean with `--pre-deploy`
  (HTTPS not-applicable, sitemap read from the build, not the live host).
- `omtal self-test` green. Not pushed to GitHub or synced to the NAS.

## The steps (one at a time, each ends in a visible audit difference)

1. **CDN awareness.** Capture a few response headers in the fetch. Detect the CDN
   in front (Cloudflare first). Recognise the `cdn-cgi/l/email-protection`
   artifact and explain it instead of letting it show up as a broken page. Skip
   `cdn-cgi` paths in the crawl so they stop polluting the page errors. New NOTE
   rule `access.cdn-delivery`. Visible result: re-audit pompedozare.ro and the
   report names Cloudflare and explains the email link, and the spurious page
   error is gone.

2. **Duplicate `User-agent: *` in robots.txt.** Keep group multiplicity in
   parse_robots. New NOTE rule that warns when two or more groups target the same
   agent, because a strict crawler honours only the first and would miss the
   rest. Visible result: a robots.txt with a CDN-prepended block is flagged.

3. **Pre-deploy audit mode.** A `--pre-deploy` flag: treat the HTTPS requirement
   as not-applicable for a local/http host instead of a FAIL, and rewrite
   sitemap/robots/canonical references from the production host to the audited
   base so the crawl checks the local build, not the live site. Visible result:
   audit a local build on http://localhost and neither the TLS rule nor the
   sitemap rule fires a false signal.

## Follow-on: hosted front door made private (2026-09-09)

The hosted check (tools/check.cgi.py) used to write every report to a public
folder named after the checked site and redirect to it, so reports were
world-readable, guessable, and browsable, and a repeat check of the same site
served the cached public file to anyone. It also dead-ended: the report page had
no way to check another site or re-run. Fixed, on the owner's decision "private,
shown inline":
- the report is returned in the response to the visitor who asked; nothing is
  written to a public folder;
- a private cache under CACHE keeps a repeat check of the same public site fast;
- a controls bar wraps the report with a "Check another site" form and a
  "Run this one again" link (fresh=1 skips the cache);
- the report body is still exactly what `omtal` renders, so the fingerprint
  integrity check is untouched.
Smoke-tested locally against a public site: 200 inline, cache hit, fresh bypass,
report stored only under the private cache. Not yet deployed to the web host.

## Not building (imagined, not demanded)
A full origin-versus-edge diff that fetches the true origin behind the CDN. It
needs an origin address or a host trick, and no failure this session demanded it.
Step 1 gives the honest core: name the CDN and explain what it changed. If the
owner later wants the diff, it becomes a `--origin` option.

## Record
Developed in the Mac clone (~/Projects/omtal, tracks github petresandu-cloud/omtal).
Verified with `omtal self-test` and a live audit each step. Pushing to GitHub or
syncing to the NAS is a separate decision, not done without the owner's say.
