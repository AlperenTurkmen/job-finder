# Gemini BrowserMCP Job Scraper

## 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

## 2. Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Configure environment variables

Create a `.env` file in the project root. Use the following template and replace placeholders with your credentials and BrowserMCP endpoint details:

```
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-1.5-pro
BROWSERMCP_WS_ENDPOINT=wss://localhost:12345
BROWSERMCP_API_KEY=optional_browsermcp_api_key
BROWSERMCP_PROJECT=optional_project_name
BROWSERMCP_TIMEOUT=25
LOG_LEVEL=INFO
```

The scraper loads `.env` automatically via `python-dotenv` when modules import.

## 4. Prepare BrowserMCP

1. Install the BrowserMCP Chrome extension from the Chrome Web Store.
2. Open the extension options and configure the MCP server endpoint to match `BROWSERMCP_WS_ENDPOINT`.
3. Enable the extension on the target domain(s) you plan to scrape. Grant any requested permissions so that the tool can capture fully rendered pages.
4. If BrowserMCP is hosted remotely, ensure the server process is running and accessible before you launch the scraper.

Consult the BrowserMCP documentation for any additional authentication or project-scoping requirements. The scraper forwards `BROWSERMCP_API_KEY` and `BROWSERMCP_PROJECT` as headers when present.

## 5. Run the scraper from the command line

Activate the virtualenv and execute:

```bash
python main.py "https://careers.example.com/jobs/12345"
```

The script prints the full Markdown/text captured from the rendered job posting. For additional diagnostics, adjust `LOG_LEVEL` in `.env` (for example, `DEBUG`).
