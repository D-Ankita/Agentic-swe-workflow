# Contributing

1. Create a focused branch and keep changes small enough to review.
2. Add or update tests for every behavior change.
3. Run `PYTHONPATH=src python3 -m unittest discover -s tests -v`.
4. Run `PYTHONPATH=src python3 -m compileall -q src tests` and `git diff --check`.
5. Explain security-boundary changes explicitly in the pull request.

Never commit secrets, production credentials, generated trace data, or approval
tokens. Security-sensitive changes require a second reviewer.

