# Architecture & Naming Guide

This document explains how the current pipeline pieces fit together and proposes a naming/organization standard you can adopt **without breaking any existing entrypoints**. Treat it as a roadmap: you can implement it incrementally, validating each phase with the existing mock and live workflows.

---

## 1. High-Level Flow

```
Companies CSV
   │
   ▼
agents/job_url_extractor_agent.py   (LLM + Playwright URL filtering)
   │ outputs data/job_urls/*.csv
   ▼
pipeline/scrape_and_normalize.py    (Playwright scrape + normalization)
   │ outputs data/roles_for_llm/*.csv + data/roles/*.json
   ▼
pipeline/run_apply_pipeline.py      (scores roles, writes cover letters, auto-applies)
   │ interacts with job-application-engine/agents/*
   ▼
job-application-engine/output/*     (cover letters, dom snapshots, apply logs)
```

Support assets:
- `mock_site/` + `mock_data/`: deterministic offline runs.
- `job-application-engine/input/`: shared inputs (`profile.json`, `role.json`, `all_jobs.json`).

---

## 2. Component Buckets (Current vs Suggested)

| Concern | Current location | Suggested namespace | Notes |
| --- | --- | --- | --- |
| Ingestion (companies → job URLs) | `agents/job_url_extractor_agent.py` | `pipelines/ingest/` | Package the extractor + helper clients; keep CLI wrappers thin. |
| Scraping + normalization | `pipeline/scrape_and_normalize.py`, `job_scraper_agent.py`, `content_cleaner.py` | `pipelines/scrape/` + `pipelines/normalize/` | Separate scraping from normalization so each can be re-used/tested independently. |
| Orchestration | `pipeline/run_apply_pipeline.py`, `pipeline/run_complete_pipeline.py`, `pipeline/run_all.py` | `pipelines/orchestrators/` | Give each orchestrator a short alias (e.g., `orchestrators/apply_pipeline.py`). |
| Job application engine | `job-application-engine/agents/*` | leave as-is but treat as submodule `job_engine.*` | Add `job_engine/__init__.py` printing key exports and import them via `job_engine.role_evaluation`. |
| Mocks/fixtures | `mock_site/`, `mock_data/` | `tests/mocks/{web, llm, payloads}` | Keep the current assets but mirror them under `tests/mocks` so automated tests can import the same fixtures. |
| Config | `config/settings.yaml`, `config/scoring.yaml` | `config/` (root) | Add schema doc, make every CLI flag map to config key. |
| Docs | scattered (`README.md`, `COMPLETE_PIPELINE_README.md`, `SCRAPER_README.md`, `MAYBE_README.md`) | `/docs/` | Use mkdocs-style structure: `docs/overview.md`, `docs/pipeline.md`, `docs/mock-mode.md`. |

---

## 3. ADK / Job Application Engine Deep Dive

The `job-application-engine/` directory is an ADK (Agent Development Kit) bundle that handles **role evaluation, cover-letter generation, and auto-apply**. Treat it as its own subsystem with two stacks that the pipeline taps into.

### 3.1 Role Evaluation & Cover Letter Stack

```
normalized role JSON
      │
      ▼
RoleAnalysisAgent → RoleValidationAgent → ForMeScoreAgent → ForThemScoreAgent → InsightGeneratorAgent
      │                                                                                       │
      └───────────────► RoleEvaluationEngine (writes job_scores.csv + evaluation_results.json) ┘

RoleAnalysisAgent + StyleExtractorAgent + ProfileAgent + CoverLetter agents → output/final_cover_letter.md
```

- **Inputs**: `job-application-engine/input/all_jobs.json`, `role.json`, `profile.json`, `user_uploaded_cv.pdf`, plus writing samples and CV variants under `memory/profile_store/`.
- **Outputs**: scored CSV/JSON under `output/`, refreshed cover letter markdown, and CV/role metadata used later by auto-apply.
- **Data contract**: the evaluation agents expect `company`, `role`, `location`, `responsibilities`, `tech_stack`, `job_type`, and `job_url`. The cover-letter stack reuses the same payload plus style/profile context.

### 3.2 Auto-Apply Stack (ADK Playwright agents)

```
AutoApplyOrchestrator
   ├─ ApplicationNavigatorAgent      (Playwright discovery of apply steps + DOM snapshots)
   ├─ AnswerValidityAgent           (Gemini vetting against KnowledgeBase)
   ├─ UserInputRequiredAgent        (blocks + persists pending questions)
   ├─ ApplicationSubmitAgent        (replays steps, uploads CV/letter, clicks submit)
   ├─ ApplicationWriterAgent        (writes answers/applied/*.json)
   └─ FailureWriterAgent            (writes answers/not_applied/*.json)
```

- **KnowledgeBase**: built from the latest `profile.json`, parsed CV (`memory/profile_store/parsed_cv.json`), and generated cover letter text so the Answer Validity Agent never fabricates data.
- **Workflow definitions**: `workflows/auto_apply_to_job.yaml` and `workflows/evaluate_all_roles.yaml` mirror the Python orchestrators, keeping ADK runners and CLI invocations in sync.
- **Artifacts**: DOM snapshots in `output/dom_snapshots/`, audit trails under `answers/{applied,not_applied}/`, and optional `output/pending_questions.{md,json}` when human input is required.

### 3.3 Integration Points

- `pipeline/run_apply_pipeline.py` loads `RoleEvaluationEngine`, `OrchestratorAgent`, and `AutoApplyOrchestrator` dynamically so the scraping/normalization code stays decoupled.
- The pipeline writes `all_jobs.json` before scoring, overwrites `role.json` before each cover letter run, and passes the latest cover letter/profile/CV paths into the auto-apply ADK workflow.
- Mock mode sets `MOCK_LLM_RESPONSES`, which the ADK agents honor via `GeminiConfig(mock_bucket=...)`, ensuring deterministic offline runs.

Keep this interface stable—future refactors can shuffle files inside `job-application-engine/agents/`, but as long as the orchestrator classes expose the same constructors + `run()`/`run_with_inputs_async()` signatures, the rest of the repo remains unaffected.

---

## 4. Naming Standards

1. **Modules**: lowercase with underscores, grouped by concern (e.g., `pipelines/ingest/url_extractor.py`).
2. **Packages**: plural nouns for domains (`ingest`, `scrape`, `normalize`, `apply`).
3. **Entrypoints**: verbs describing the workflow (`run_apply_pipeline.py` → `apply_pipeline.py`). Keep `run_` prefix only for backwards-compatible wrappers.
4. **Classes**: PascalCase nouns (`JobUrlExtractor`, `ScrapeCoordinator`).
5. **Env/config keys**: SCREAMING_SNAKE, match CLI option names (`MOCK_LLM_RESPONSES` ↔ `--mock-llm-responses`).
6. **Artifacts**: use consistent prefixes: `data/job_urls/*.csv`, `data/roles_raw/*.json`, `job-application-engine/output/*.md`.

---

## 5. Incremental Re-Org Plan (Zero-Break Strategy)

### Phase 0 – Documentation & Aliases (done/low effort)
- Keep `pipeline/run_apply_pipeline.py` untouched but add this guide + a docs index (`docs/`).
- Create lightweight re-export modules (e.g., `pipelines/__init__.py` with `from .run_apply_pipeline import main as apply_main`).

### Phase 1 – Package Boundaries
- Turn `agents/` into a proper package: `agents/__init__.py`, `agents/ingest/__init__.py`, etc.
- Move script logic into functions (e.g., `extract_all_job_urls`) and keep thin CLI wrappers that import them. Existing CLIs continue to work because module paths stay the same.

### Phase 2 – Namespacing Orchestrators
- Create `pipelines/orchestrators/apply_pipeline.py` that simply imports `run_apply_pipeline`. Mark the old script as shim (print warning) to guide users.
- Do the same for `run_complete_pipeline.py` and `run_all.py`.

### Phase 3 – Asset + Config Hygiene
- Introduce `/docs/`, `/tests/`, `/mocks/` directories with symlinks or small wrappers back to current paths.
- Centralize config defaults in `config/defaults.py` and import them in every CLI to avoid divergence.

### Phase 4 – Naming Cleanup (breaking changes opt-in)
- After shims are stable, rename files (e.g., `job_url_extractor_agent.py` → `url_extractor.py`). Provide `python -m` aliases and deprecation warnings before removing old names.

---

## 6. Quick Wins Without Refactors

- **Add an index README**: populate root `README.md` with links to `COMPLETE_PIPELINE_README.md`, `SCRAPER_README.md`, `job-application-engine/README.md`, and this document.
- **Generate architecture diagram**: a simple Mermaid graph in `docs/architecture.md` helps new contributors instantly understand the flow.
- **Adopt consistent logging prefixes**: e.g., `[INGEST]`, `[SCRAPE]`, `[APPLY]` so logs already hint at component boundaries.

---

## 7. Checklist for Each Future Script

- Lives inside an appropriate package (`pipelines/ingest`, `pipelines/apply`, etc.).
- Has `main()` + `if __name__ == "__main__": raise SystemExit(main())`.
- Imports shared config defaults from `config/defaults.py`.
- Exposes its primary functionality via a callable used by orchestrators/tests.
- Ships with a brief doc in `docs/<area>.md`.

Adopting these small conventions incrementally will make the repo feel cohesive without risking regressions.
