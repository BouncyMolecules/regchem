<div align="center">

# Quanta

**Premium RegOps decision support for Starting Material classification** — traceable hypotheses, grounded in source narrative, tuned for audits and submissions.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-0f172a?style=flat&labelColor=0f172a&color=14b8a9)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/app-Streamlit-0f172a?style=flat&labelColor=0f172a&color=14b8a9)](https://streamlit.io)

<br/>

[**Try live demo →**](REPLACE_WITH_STREAMLIT_CLOUD_URL)

<sub>After you deploy to [Streamlit Community Cloud](https://streamlit.io/cloud), replace <code>REPLACE_WITH_STREAMLIT_CLOUD_URL</code> with your public app URL.</sub>

</div>

---

## Why Quanta?

Regulatory Operations teams drowning in unstructured CMC text need more than summaries: they need **defensible rationales**, **replayable lineage**, and a way to **pressure-test narratives** without pretending the computer is the qualified person. Quanta wraps extraction, tiering, and verification workflows in an interface that behaves like operational software — intentional, restrained, audit-aware — rather than another chat box.

---

## What you get

| Capability | Outcome |
|------------|---------|
| **Self-evolving graph memory** | Each run reinforces an append-only **hypergraph ledger** — evidence, entities, and higher-order joins accumulate without overwriting history. |
| **Higher-order relationships** | Signals connect across excerpts, tiers, supplier cues, and verification layers so reviewers see *structure*, not scattered rows. |
| **Predictive what-if** | Regulatory-style **risk-forecast scaffolding** contrasts scenarios so teams can rehearse objections before filings and meetings. |
| **User-in-the-loop learning** | Explicit feedback paths feed **continual-learning hooks** anchored to correlated runs — humans stay in authority; the model does not silently “optimize away” accountability. |
| **Full auditability** | Provenance payloads, hashed ledger rows, correlation IDs, and parse/classify/verify stages are designed so every interesting output can answer *why* and *since when*. |

---

## Product gallery *(screenshot placeholders — add PNGs before launch PR)*

> **Brand note:** Capture PNGs once the UI settles. Use **Quanta’s navy + teal** shell references (`#0f172a` ink, `#14b8a9` teal accents) so the readme gallery feels bespoke, not generic.
>
> Recommended asset folder: `./docs/screenshots/` — uncomment markdown image lines once files exist.

### 1. Command posture — ingest & classify

<!--
![Quanta — ingest & classification workspace](./docs/screenshots/01-ingest-classify.png)
-->

**Asset path:** `./docs/screenshots/01-ingest-classify.png` *(add PNG and uncomment the image line above)*

**Caption:** High-signal view of pasted or uploaded narrative, correlated run identity, and the first classification scaffold before deeper verification panels.

---

### 2. Provenance-forward results

<!--
![Quanta — provenance-forward result cards](./docs/screenshots/02-provenance.png)
-->

**Asset path:** `./docs/screenshots/02-provenance.png`

**Caption:** Every hypothesis ships with excerpts, locators, and tier rationale text suitable for dossier appendix talking points — not vibes.

---

### 3. Supplier & narrative stress points

<!--
![Quanta — supplier linkage & verification](./docs/screenshots/03-supplier-stress.png)
-->

**Asset path:** `./docs/screenshots/03-supplier-stress.png`

**Caption:** Highlights where supplier language and synthesis narrative create classification tension — intended for Regulatory CMC pairing sessions.

---

### 4. Graph memory corpus & hypergraph ledger

<!--
![Quanta — graph memory & ledger](./docs/screenshots/04-graph-memory.png)
-->

**Asset path:** `./docs/screenshots/04-graph-memory.png`

**Caption:** Operational window into corpus growth, ledger edges, and append-only semantics that protect historical truth when teams iterate.

---

### 5. What-if forecasting & reviewer teaching-the-desk

<!--
![Quanta — predictive what-if & teaching rail](./docs/screenshots/05-whatif-teach.png)
-->

**Asset path:** `./docs/screenshots/05-whatif-teach.png`

**Caption:** Comparative forecast lines paired with explanatory copy so SMEs can critique model posture without losing governance language.

---

## Quick start *(local)*

Requirements: **Python ≥ 3.11**.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
streamlit run app.py
```

Optional quality gates maintained in-repo:

```powershell
ruff check .
ruff format --check .
mypy
pytest
```

> **Naming:** The packaged module path is **`regchem_sentinel`** (`regchem-sentinel` in metadata). Customer-facing framing is **Quanta**.

---

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub (**Quanta ships from this repository** regardless of legacy folder names inside `src/`).
2. Visit [share.streamlit.io](https://share.streamlit.io) → **New app** → authorize the repo.
3. Configure:
   - **Main file path:** `app.py`
   - **Branch:** typically `main` or your release branch  
4. Populate **Secrets** in Streamlit Cloud to match whatever keys the app expects via **`st.secrets`** (mirror your local secrets privately — **never commit** credential files).
5. Hit **Deploy** → copy the HTTPS URL → replace `REPLACE_WITH_STREAMLIT_CLOUD_URL` near the top of this README.

`app.py` already prepends `./src` to `PYTHONPATH`, matching Streamlit Cloud’s sparse checkout expectations.

---

## GxP & regulatory posture

Quanta supports **regulated-adjacent** workflows but is intentionally scoped as software that **helps humans decide faster with better artefacts — not decide for them**:

- Quanta is **not** marketed or validated here as a **medical device**, **GxP-qualified system substitute**, nor a guarantee of **agency acceptance**.
- Automated outputs are **decision-support hypotheses** with structured trace metadata. Treat outputs as **wrong until corroborated** against approved baseline documents inside your Quality System.
- Align record handling with applicable expectations such as **ALCOA+**, **21 CFR Part 11**, **EU Annex 11**, and **ICH Q9/Q10**, according to scope your organization asserts.
- **Do not strip or bypass verification, provenance, or correlation capture** outside the controls of your risk management process — those controls are precisely what distinguishes portfolio-grade RegOps tooling from dashboard fiction.

Maintainers welcome feedback from Quality & IT teams tightening deployment patterns (segregated databases, cryptographic anchoring extensions, SSO, validated SDLC hooks).

---

## Architecture overview

Quanta adopts **clean layering** familiar to auditors and hiring managers evaluating digital transformation chops:

| Layer | Role |
|-------|------|
| **`src/regchem_sentinel/core`** | Pure domain logic — parsers, classifiers, verifiers, **graph-memory writers**, forecasting helpers — kept free of Streamlit imports. |
| **`src/regchem_sentinel/ui`** | Streamlit surfaces, typography and **navy + teal presentation tokens**, pagination, reviewer affordances. |
| **`app.py`** | Hosted entry shim that fixes `PYTHONPATH`, then invokes `run_app()`. |

**Fast–slow cognition:** heuristic / deterministic tiers move quickly across narrative structure, while richer verification plus **persisted ledger projections** deliberate where mistakes are costly. **Graph memory** closes the loop: each audited snapshot can append hashed hyperedges so longitudinal intelligence compounds without orphaned spreadsheets.

Dependency construction happens in **`regchem_sentinel.ui.app`**; shared objects live on Streamlit **`session_state`** so reruns preserve continuity without covert global singletons.

---

## Stay connected

- **Source & roadmap:** [`github.com/BouncyMolecules/regchem`](https://github.com/BouncyMolecules/regchem)
- **Writing — Clinical Future *(Substack)*:** [`clinicalfuture.substack.com`](https://clinicalfuture.substack.com/)
- **LinkedIn *(update slug):*** [`linkedin.com/in/USERNAME`](https://www.linkedin.com/in/USERNAME/)

---

## License & disclaimer

Distributed under the **MIT License** — permissive reuse with attribution — see **`LICENSE`** for the full verbatim text *(add MIT `LICENSE` at repo root when publishing; prose here is informational).*  

THE SOFTWARE IS PROVIDED **“AS IS”**, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.

---

<sub>© 2026 Quanta maintainers • Built for Regulatory Operations portfolios that emphasize evidence, ergonomics, and grown-up disclaimers.</sub>
