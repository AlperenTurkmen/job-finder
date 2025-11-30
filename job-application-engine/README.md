# Job Application Engine (ADK)

This directory contains a deterministic multi-agent automation flow built on top of the Gemini 2.5 family. The system ingests a role description and a personal profile package, produces cover letters in the user’s style, and iterates with an HR simulation loop until the fit score meets the target threshold.

## Components

- `agents/` — Cover-letter stack (role analysis, profile ingestion, style extraction, cover letter generation, HR simulation, orchestration) **plus** the role-evaluation agents (role validation, For-Me scoring, For-Them scoring, insight generator, CSV writer, role evaluation engine).
- `memory/` — Structured profile store, CV variants, and writing samples used as context.
- `workflows/` — YAML definitions describing both the generation pipeline and the new `evaluate_all_roles` scoring loop.
- `input/` — Dropped-in payloads from the user (role JSON for drafting; `all_jobs.json` for bulk evaluation) plus uploaded CV artifacts.
- `output/` — Deterministic artifacts (final letter, HR report, revision history, role fit score, the chosen CV record, bulk evaluation JSON, and the running `job_scores.csv`).

## Auto Apply Workflow (ADK/Gemini + Playwright)

The `auto_apply_to_job` workflow turns the engine into a fully modular multi-agent system that can open a job URL, validate every form question against persisted user data, block for human input when needed, and finally submit the application directly through a Playwright-driven browser session (no BrowserMCP daemon required).

### Agents & Responsibilities

1. **Application Navigator Agent** (`auto_apply/application_navigator_agent.py`)
	- Drives a native Playwright session to load the `job_url`, locate "Apply" buttons, and scrape DOM snapshots.
	- Emits a structured list of form steps + normalized field descriptors (label, selector, type, options, required flag).
2. **Answer Validity Agent** (`auto_apply/answer_validity_agent.py`)
	- Runs on Gemini 2.5 Pro with strict instructions to **never hallucinate**.
	- Uses the `KnowledgeBase` (persisted `profile.json`, parsed `cv.pdf`, cover letter text) for semantic retrieval, then decides if a field can be auto-answered.
3. **User Input Required Agent** (`auto_apply/user_input_agent.py`)
	- When a field lacks grounded data, writes `output/pending_questions.{json,md}` and blocks.
	- Polls `input/user_answers.json` until the user supplies the missing `field_id → answer` pairs, then resumes automatically.
4. **Application Submit Agent** (`auto_apply/application_submit_agent.py`)
	- Replays the apply flow, fills every validated answer, uploads the CV PDF where required, pastes the cover letter, and attempts the final submit click via Playwright.
5. **Application Writer Agent** (`auto_apply/application_writer_agent.py`)
	- On success, writes `answers/applied/a_<job_name>.json` with the final answers, provenance, submission steps, and ISO timestamp.
6. **Failure Writer Agent** (`auto_apply/failure_writer_agent.py`)
	- On any blocking issue (no apply flow, browser failure, human-only step), saves `answers/not_applied/a_<job_name>.json` including the reason and recommended data.

### Knowledge Persistence & CV Parsing

- Drop the latest `profile.json` and `cv.pdf` under `job-application-engine/input/` (see samples already provided).
- The orchestrator copies `profile.json` into `memory/profile_store/profile_application.json` and parses the PDF via `pypdf`, generating `memory/profile_store/parsed_cv.json` with paragraph-level chunks for semantic search.
- Cover letter snippets are persisted at `memory/profile_store/cover_letter.txt` so every agent can treat them as a long-term knowledge source.

### Workflow Definition

`workflows/auto_apply_to_job.yaml` wires everything together. Inputs:

| Input Key          | Description                                    |
|--------------------|------------------------------------------------|
| `job_url`          | The absolute URL of the job application page.  |
| `cover_letter_file`| Path to the markdown/text cover letter.        |
| `profile_json`     | Path to the candidate master profile JSON.     |
| `cv_pdf`           | Path to the candidate CV PDF.                  |

Outputs of the workflow include the `answers/applied/` or `answers/not_applied/` artifact, DOM snapshots (`output/dom_snapshots/`), and any pending question files.

### Running the Orchestrator

1. Update the input assets:
	- `job-application-engine/input/cover_letter.md`
	- `job-application-engine/input/profile.json`
	- `job-application-engine/input/user_uploaded_cv.pdf`
	- (Optional) write the target URL into an environment variable or pass it on the CLI.
2. Install the Playwright browsers once (e.g., `playwright install chromium`). No BrowserMCP server is required.
3. Run the CLI helper:

	```bash
	python job-application-engine/agents/run_auto_apply.py \
	  "https://careers.example.com/backend-engineer" \
	  job-application-engine/input/cover_letter.md \
	  job-application-engine/input/profile.json \
	  job-application-engine/input/user_uploaded_cv.pdf
	```

4. Watch `output/pending_questions.md` if the workflow pauses for human input. Provide answers in `input/user_answers.json`; the system resumes automatically.
5. Check `answers/applied/a_<job>.json` (success) or `answers/not_applied/a_<job>.json` (failure) for the final audit trail.

#### Debug answers mode

When you want to bypass the profile/CV heuristics and LLM assessment phase, provide a JSON file with explicit `field_id → answer` pairs:

```json
{
	"firstname": "Alperen",
	"lastname": "Turkmen",
	"CA_11005": "Milton Keynes",
	"cover_letter": {
		"answer": "<full text>",
		"display_name": "Cover letter"
	}
}
```

Run the orchestrator with the `--answers-json` flag:

```bash
python job-application-engine/agents/run_auto_apply.py \
	"https://careers.example.com/backend-engineer" \
	job-application-engine/input/cover_letter.md \
	job-application-engine/input/profile.json \
	job-application-engine/input/user_uploaded_cv.pdf \
	--answers-json job-application-engine/input/user_answers.json
```

In this mode the workflow loads only the debug file, skips auto-filled answers from the profile/CV, and immediately prompts you for any required fields that are still missing.

#### Captcha checkpoints

Some career sites trigger a captcha after clicking “Submit application.” Automated solving is out of scope (and usually prohibited by the site’s terms), so the best practice is to rerun the workflow with a **headed** Playwright session, let it pause on the captcha, and complete the challenge manually before the submit helper clicks the final button. Keep the browser window open until you see the confirmation page; you can then terminate the run or continue to the next job.

### Notes

- All agents respect the “no hallucination” policy by routing every field through the Answer Validity Agent.
- User-provided overrides always win; even if an answer existed previously, new entries in `user_answers.json` replace it.
- DOM snapshots are kept per job under `output/dom_snapshots/` for debugging or compliance review.

## Running the Cover-Letter Flow

1. Update `input/role.json`, `input/user_uploaded_cv.pdf`, and the assets under `memory/profile_store/`:
	- `profile.json` now holds *all* qualifications/skills/experience/projects/metadata in one place.
	- `cv_library/*.json` stores summaries of your different CV variants.
	- `writing_samples/*.md` feed the style extractor.
2. Export your Gemini key (`GEMINI_API_KEY` or `GOOGLE_API_KEY`) so the agents can call the live endpoints.
3. Execute the orchestrator:

```bash
python job-application-engine/agents/orchestrator_agent.py
```

4. Inspect the refreshed artifacts in `job-application-engine/output/`.

## Running the Role-Evaluation Workflow

The workflow now routes every step through Gemini 2.5 agents: validation, For-Me scoring, For-Them scoring, and insight synthesis are all LLM-powered. You can run it either through ADK or the convenience Python orchestrator (both paths call the exact same agents).

1. Populate `input/all_jobs.json` with an array of role objects (company, role, location, salary, job_type, tech_stack, responsibilities).
2. Keep `memory/profile_store/profile.json` and `memory/profile_store/preferences.json` current.
3. Export your Gemini key (`GEMINI_API_KEY` or `GOOGLE_API_KEY`).
4. **ADK run (preferred):** the workflow YAML already points at the default input files, so you can just execute:

```bash
adk run workflows/evaluate_all_roles.yaml
```

If you need to point to different files, edit the `inputs` block near the top of `workflows/evaluate_all_roles.yaml`.

5. **Python orchestrator (alternate):**

```bash
python -m agents.role_evaluation_engine
```

Both options will hit the LLM for every role and then persist `output/evaluation_results.json` + `output/job_scores.csv`.

## Notes

- Reasoning-heavy steps (role analysis, HR scoring, orchestration) are configured for **Gemini 2.5 Pro**.
- Style extraction and rewriting leverage **Gemini 2.5 Flash** for speed and deterministic phrasing.
- The workflow YAML files can be imported into any ADK-compatible runner; each step aligns with the agents defined in this package.

### CV Library quick reference

Each file under `memory/profile_store/cv_library/` represents a specific CV flavor (e.g., `cv_data_engineering.json`, `cv_product.json`). Every JSON contains:

- `summary`: one-paragraph positioning statement for that CV variant.
- `highlights`: bullet-level achievements that agent can quote.
- `sections`: optional hints about which experience/skills sections to emphasize.

The role analysis agent compares the role vector against these summaries to pick the most relevant CV before drafting.
