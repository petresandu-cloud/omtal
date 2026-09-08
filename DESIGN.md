# Design

Why Omtal is built the way it is. The code is the authority where this file
and the code disagree.

## The question

What must change on the public web so that AI systems discover, understand,
cite and appropriately recommend a product when users have problems it
genuinely solves? Then: did the change work?

This is not search engine optimisation. Search optimises keyword, ranking,
click. Omtal follows the chain an answer engine follows: a user need, the
engine's reading of the product, the evidence it gathers, the entity it
resolves, the citation it gives, the recommendation it makes.

## Decisions

**Read the site the way a crawler does.** Standard-library HTTP with a named
user agent, robots.txt parsed by the longest-match rule, sitemaps followed,
pages parsed for the things engines read: title, description, canonical,
headings, JSON-LD, visible text, links. No headless browser: the engines that
matter fetch HTML, and a site that needs a browser to say what it is has its
first finding right there.

**Declared and apparent, kept apart.** What the site states in structured
data is a fact about the site. What its headings and text suggest is an
inference, labelled so. A model may refine the apparent half; it never
overwrites the declared half.

**Intents are questions, not keywords.** From each capability the site
declares: a problem, a situation, the natural questions. Deterministic
templates produce the candidates; a person or a model adds, ranks or strikes,
and every intent records who put it there. An intent is never proof of
demand.

**The database is the evidence; a model is at most an analyst.** Every engine
answer is stored verbatim, immutable, before anything is extracted from it.
The report counts from stored rows. Nothing on the page comes from a model's
memory of what engines usually say.

**Documented interfaces only, keys from the environment.** No private
endpoints, no browser automation of chat products. An engine without a key is
skipped and the report says so; that is a gap, not a failure.

**Absence of evidence is never a failure.** Input not given is an open
question naming what to add. A scan that admits it may miss things is a risk
at most. Only what was read and is wrong keeps machines out.

**The ladder, not a score.** Unreachable, reachable, understood, cited,
recommended. A product stands on one rung and the report says what keeps it
from the next. There is no composite number to argue with.

**Interventions are the smallest change that closes the gap.** Fix the
robots policy, add the product node, write the page for the one capability
that has none, name who it is for. Never "publish fifty articles".

## The record shapes

- **Fact** (`probes.json`): id, value or null with an error, source, observed
  time, provenance in verified-directly, sub-agent-reported, inferred,
  needs-engine-access, needs-owner-answer.
- **Product graph**: declared (organization, products with types, offers,
  features, sameAs) and apparent (name, tagline, features from headings,
  claims with numbers, audience, languages, contact).
- **Intent** (`intents.json`): id, question, family, capability, who added
  it, status (candidate or struck).
- **Observation** (`observations.jsonl`, append-only): intent, question,
  engine, run, time, the raw answer and citations, and what was extracted:
  mentioned, cited, recommended, domains cited, competitors named.
- **Rule** (`rules/*.toml`): id, layer, title, what it consumes, kind
  (mechanical with a check, or judgement with a question), severity, and why
  it matters in one or two sentences.
- **Grid row**: the rule, its verdict, exactly one provenance marker, the
  evidence in one sentence.

## The loop

Read the site, derive the questions, ask the engines, count what they did,
diagnose the gap, change the site, read it again. The value is longitudinal:
which change on which site moved which engine. That record is what a run
adds to and what a static audit cannot.
