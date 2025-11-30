# Mock Assets for Offline Testing

This folder contains deterministic fixtures that let you exercise the full apply pipeline without calling
real LLMs or scraping live websites.

## Files

| File | Purpose |
| --- | --- |
| `mock_llm_responses.json` | Synthetic responses returned whenever the `MOCK_LLM_RESPONSES` environment variable points to this file. Every Gemini-powered agent (scoring, cover letters, answer validation, etc.) reads from these buckets instead of hitting the API. |
| `normalized_roles.json` | Structured role payloads indexed by `job_url`. Pass this file to `pipeline/scrape_and_normalize.py --mock-normalized-json` to bypass the normalization LLM after scraping the mock site. |

## Usage Overview

1. Serve the static site in `mock_site/` (see README for details).
2. Point your companies CSV at the hosted careers page (e.g. `http://localhost:8000/careers.html`).
3. Export the environment variable so *all* LLM calls are mocked:

```bash
export MOCK_LLM_RESPONSES=$(pwd)/mock_data/mock_llm_responses.json
```

4. Run the pipeline with the mock-normalized roles file:

```bash
python pipeline/run_apply_pipeline.py \
  --companies-csv data/companies/mock_companies.csv \
  --job-urls-csv data/job_urls/mock_urls.csv \
  --intermediate-csv data/roles_for_llm/mock_scraped.csv \
  --output-dir data/roles_mock \
  --mock-normalized-json mock_data/normalized_roles.json \
  --apply-threshold 60
```

The script will:
- Extract job links heuristically from the mock careers page.
- Scrape each static HTML page via Playwright.
- Load structured role data from `normalized_roles.json` instead of calling the normalizer LLM.
- Forward the roles to the scoring + cover-letter stack, which now returns canned results from `mock_llm_responses.json`.
- Drive the auto-apply workflow against the HTML form embedded in `mock_site/jobs/mockcorp-data-scientist.html`.

Feel free to duplicate the sample entries to cover more scenarios. Bucket names in `mock_llm_responses.json` correspond to the agent names documented inside that file.
