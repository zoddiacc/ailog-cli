# Contributing to AILog

Thanks for your interest in improving AILog! This project helps AOSP and Android
Automotive platform developers make sense of build and logcat output. Contributions
of all sizes are welcome.

## Ways to contribute

- **Add knowledge-pack entries** — the easiest and highest-impact contribution.
  The knowledge pack (`src/ailog/knowledge_pack.py`) is pure data that teaches the
  tool about real AOSP/Automotive errors, so even small local models give good
  answers. Adding a VHAL property, a SELinux/binder/CarService signature, or a new
  error explanation is a great first PR (see below).
- Fix bugs or improve robustness.
- Improve docs, examples, or the terminal UX.
- Add tests.

## Project ground rules

- **Zero runtime dependencies.** AILog is standard-library only. Do not add
  third-party packages to `pyproject.toml`. HTTP uses `urllib`, not `requests`.
- **Python 3.9+.** Keep code compatible with 3.9 through 3.14.
- **Every change keeps CI green** — tests pass and `ruff` is clean.

## Development setup

```bash
git clone https://github.com/<your-username>/AILog.git
cd AILog
pip install -e .

# Run the CLI from source
python3 run.py --help

# Run the test suite
python3 -m unittest discover -s tests -v

# Lint
pip install ruff
ruff check src/ tests/ tools/
```

## Adding a knowledge-pack entry

Everything is in `src/ailog/knowledge_pack.py`:

- **A vehicle property** → add to the `VHAL_PROPERTIES` dict:
  `'PROPERTY_NAME': ('short summary', 'full guidance incl. access + Car.PERMISSION_*')`.
- **An error signature** (SELinux, binder, a HAL, a build error, …) → add a
  `_entry(...)` to the `KNOWLEDGE` list with a regex and concise, accurate guidance.

Then add a matching test in `tests/test_knowledge_pack.py`.

> **Accuracy matters more than volume.** The guidance is injected into AI prompts
> as authoritative fact, so a wrong entry is worse than none. Cite the stable
> public API where you can; `tools/gen_vhal_knowledge.py` can generate VHAL entries
> from a `VehicleProperty.aidl` in an AOSP tree.

## Pull request workflow

1. Fork the repo and create a branch off `master` (e.g. `git checkout -b fix/vhal-typo`).
2. Make your change, add/adjust tests, and run the suite + `ruff` locally.
3. Push your branch and open a pull request against `master`.
4. CI (tests on Python 3.9–3.14, lint, coverage) must pass. A maintainer will review.

Keep PRs focused — one logical change per PR is easier to review and merge.

## Commit messages

Write a concise, imperative subject line ("Add EV charge-limit VHAL properties")
and explain the *why* in the body when it isn't obvious.

## Reporting bugs / requesting features

Use the issue templates under **Issues → New issue**. For security issues, please
follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Code of conduct

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).
