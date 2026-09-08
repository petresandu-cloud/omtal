# Contributing

- Standard library only. No headless browsers, no scraping of chat products,
  no private endpoints. An engine adapter uses a documented API and a key
  from the environment.
- Facts and verdicts stay apart: probes return facts with provenance; checks
  turn facts into verdicts; a check never fetches.
- A FAIL or RISK rests on something read. Missing input is an open question
  naming what to add.
- Every rule carries `why`: one or two sentences a product owner understands.
- The page is generated. Change `omtal/report.py` and `REPORT-PRINCIPLES.md`
  together; the tests enforce the contract.
- `python3 -m unittest` and `python3 -m omtal self-test` must pass. One
  change per pull request, with the test that proves it and the commands you
  ran.
