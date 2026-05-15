# RegChem Sentinel

Auditable **decision-support** scaffolds for spotting **Starting Materials (SMs)** and **supplier**
cues inside unstructured CMC narratives that typically accompany NDAs, ANDAs, and related
submissions. The codebase targets teams who must explain *why* an algorithm surfaced a row and
*which* primary-source excerpt supports it.

## Regulatory posture (read before use)

- This software is **not** a validated medical device, **not** a substitute for qualified SME review,
  and **not** a guarantee of regulatory acceptability. Agency outcomes depend on submission
  quality, scientific merit, and inspection context beyond any tool.
- Outputs are **hypotheses** with trace metadata. Treat every automated label as **wrong until
  proven** against approved source documents under your quality system.
- Follow **ALCOA+** principles: capture configuration, inputs, outputs, reviewers, anomalies, and
  retain records per **21 CFR Part 11**, **EU Annex 11**, **ICH Q9/Q10**, and program-specific
  policies that apply to your organization.
- **Do not** disable verification stages or provenance capture in regulated workflows without an
  approved risk assessment.

## Architecture

- `src/regchem_sentinel/core/`: pure domain logic (no Streamlit imports).
- `src/regchem_sentinel/ui/`: Streamlit composition root, pages, and presentation helpers.
- `app.py`: Streamlit Cloud entrypoint (adjusts `sys.path` for the `src/` layout).

There are **no** module-level service singletons. Dependencies are constructed in
`regchem_sentinel.ui.app` and stored in Streamlit `session_state` only to preserve audit history
across reruns during a browser session.

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy
pytest
streamlit run app.py
```

## Streamlit Cloud

Point the Cloud app entry at `app.py`. Provide secrets via the platform's secret manager; never
commit credentials.

## License

Proprietary — see `pyproject.toml`.
