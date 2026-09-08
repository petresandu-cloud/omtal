<img src="assets/omtal-logo.svg" alt="Omtal, AI discoverability check" width="360">

# Omtal

**Can AI systems find, understand, cite and recommend your product?** Omtal
reads your site the way a crawler does, works out what you say the product is,
derives the questions people would ask an AI that your product could answer,
asks the engines those questions when you give it a key, and writes one report
where every finding says what was found, why it matters and how it knows.

It is not an article generator. It tells you what to change on the public web
and measures whether the change worked.

## The ladder

```
unreachable   the machines that answer questions cannot read the site
reachable     they can read it, but what the product is has to be guessed
understood    the product is declared in a form machines read
cited         engines use the site as a source when answering
recommended   engines name the product for the questions it answers
```

Every run says which rung the product stands on and what keeps it from the
next one.

## Install

Python 3.11 or later, standard library only.

```sh
pip install git+https://github.com/petresandu-cloud/omtal
omtal audit https://your-product.example
```

That writes `omtal-out/<host>/report.html` with the exports beside it. Open
it in any browser.

## What it checks

24 rules in four layers:

- **Reach.** The home page answers over HTTPS; robots.txt admits the
  crawlers that produce answers (OAI-SearchBot, PerplexityBot, Googlebot,
  Bingbot, Claude-SearchBot and the rest) and names a sitemap; a sitemap
  exists; an llms.txt summarises the site; the crawl reaches the pages the
  sitemap promises.
- **Understanding.** The maker and the product are declared in structured
  data with a description; the name is consistent across pages; every page
  has a canonical address, a title, a description, one h1 and a language.
- **Content and evidence.** Each declared capability has a page or a section
  of its own; pages carry enough text; images are described; claims with
  numbers have a source; the positioning names the function, not the feeling.
- **What the engines do.** With a key, the questions are asked and every
  answer stored. The report counts, per engine, in how many answers the
  product was mentioned, the site was cited and the product recommended, and
  which sources the engines rely on instead.

Two of the rules are judgement rules: a person or a model answers them by
reading, and the answer is kept only while the facts it saw are unchanged.

## The loop

```sh
omtal audit https://your-product.example              # read, derive, judge, report
omtal intents https://your-product.example            # see the questions; --strike ID, --add "question"
BRAVE_SEARCH_API_KEY=… omtal observe https://your-product.example --runs 3
omtal audit https://your-product.example              # fold the observations into the report
omtal judge https://your-product.example evidence.positioning-accurate RISK "The description says 'peace of mind'; nowhere does it say what the app does." --by "your name"
omtal check https://your-product.example              # the page is what it renders; edited by hand is caught
```

Change the site, run the audit again. A finding is gone only when its check
passes. Observations are never overwritten: `observations.jsonl` grows, and
the report speaks in fractions from it, never from a model's memory.

## Engines

| Key | What is asked | What comes back |
|---|---|---|
| `BRAVE_SEARCH_API_KEY` | Brave Web Search API | the sources a search-grounded answer draws on |
| `OPENAI_API_KEY` | OpenAI Responses API with web search | an answer with its citations |
| `ANTHROPIC_API_KEY` | Anthropic Messages API with web search | an answer with its citations |

Documented interfaces only. Without a key the engine is skipped and the report
says so. Answers are stochastic: ask each question several times (`--runs`)
and read the fractions.

## What it never does

- Never generates pages. It says which question has no page and why that
  page would be cited; a person writes it.
- Never promises a ranking or a recommendation. The engines decide; Omtal
  measures.
- Never reports a score without the observations behind it. Every finding
  carries its provenance, and the observation rows are stored verbatim.
- Never phones home. Fetches go to your site and, with your key, to the
  engine you chose.

## Development

```sh
python3 -m unittest
python3 -m omtal self-test
```

The report's structure and words are a contract, written in
[REPORT-PRINCIPLES.md](REPORT-PRINCIPLES.md) and enforced by the tests. Why
it is built this way is in [DESIGN.md](DESIGN.md).

## Licence

Copyright © 2026 Editerra AB. Published under the GNU Affero General Public
License, version 3 or later: see [LICENSE](LICENSE). Omtal and its mark are
trademarks of Editerra AB and are not covered by the licence. For use in a
closed product or a hosted service, or for the engines asked on your behalf
under an agreement, see [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).
