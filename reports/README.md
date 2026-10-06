# Reports

`python -m evals.run_evals` writes eval reports here; `python -m sales_compliance batch` writes
compliance summaries and per-call results here.

Nothing is committed until a real eval run has been reviewed. Before committing a report:

1. Read every missed finding, false finding and figure leak in `eval_latest.md`.
2. Confirm the model names in the header are the ones you intend to publish.
3. Keep the synthetic-data caveat at the top.
4. Never commit results from real calls.
