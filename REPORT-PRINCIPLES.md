# The report

The report is the product. Every run writes it, whoever runs it. Its structure
and look do not change between sites or runs. This file is the contract;
`omtal/report.py` implements it and `tests/test_omtal.py` fails the build
when the page breaks it.

## Structure, always in this order

1. **Title block.** "AI Discoverability Check", the product's name, the run
   date in words, the site address, and where the product stands on the
   ladder in one sentence.
2. **In one look.** How many findings keep machines out, how many weaken
   understanding, how many are still open, how many are in order.
3. **What keeps machines out.** Red. Per finding: the rule in plain words,
   what was found, why it matters, how we know.
4. **What weakens understanding.** Amber. Same shape.
5. **What is still to be checked**, grouped by who can close it: an engine
   key, the product's owner or a reader. Blue.
6. **Worth knowing.** Grey.
7. **What the engines did with the questions.** A table per engine:
   answers, mentioned, cited, recommended, sources cited most; then the
   questions themselves. Empty runs say so plainly.
8. **What is in order.** Green, collapsed.
9. **Method** and the legend for "how we know".

## Words

- Status words a stranger understands: "Keeps machines out", "Weakens
  understanding", "Not checked yet", "Worth knowing", "In order".
- "How we know" is one of: fetched the pages and ran the queries directly;
  a reviewer or model said so; inferred from what the pages say; needs an
  engine key to ask; needs the product's owner to answer.
- Every finding carries "why it matters" in one or two sentences, because
  the reader is a product owner, not a crawler engineer.
- No tool vocabulary on the page. Rule ids appear only in the small print.

## Look

- The reader's system sans; one accent (indigo) for structure; one fixed
  colour per status, the same on every run; the status is always also a word.
- The layout of an inspection report. No hero, no cards for everything.
- Print is an export. The three exports (Markdown, CSV, actions JSON) travel
  inside the page; the page carries the data's fingerprint and `omtal check`
  fails on a hand edit.
