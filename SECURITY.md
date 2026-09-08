# Security

Omtal fetches public pages of the site it is pointed at, with a named
user agent, within a page budget, and writes only under its output
directory.

**Engine keys stay in the environment.** The observe step reads
BRAVE_SEARCH_API_KEY, OPENAI_API_KEY and ANTHROPIC_API_KEY from the
environment, never copies or logs them, and calls documented endpoints only.

**Observations are stored verbatim** in the output directory so that every
finding can be traced to the answer it came from. They are yours; nothing
is sent anywhere but to the engine you asked.

To report a vulnerability, open a private security advisory on the GitHub
repository, or write to Editerra AB at contact@editerra.se. Please do not
open a public issue for a security problem.
