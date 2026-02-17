# Contributing to Job Finder

Thank you for your interest in contributing to Job Finder!

## Development Setup

1. **Fork and Clone**
   ```bash
   git clone https://github.com/yourusername/job-finder.git
   cd job-finder
   ```

2. **Set Up Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   playwright install chromium
   ```

3. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

4. **Set Up Database**
   ```bash
   createdb jobfinder
   psql -d jobfinder -f database/schema.sql
   ```

5. **Run Tests**
   ```bash
   pytest tests/
   ```

## Project Structure

- `web/` - Flask web application
- `agents/` - Multi-agent system (discovery, scoring, cover letters, auto-apply)
- `pipeline/` - Command-line pipelines
- `tools/scrapers/` - Company-specific scrapers
- `utils/` - Shared utilities (logging, database, content cleaning)
- `database/` - PostgreSQL schema
- `config/` - Prompts and workflow configurations
- `data/` - Input/output data (gitignored)

## Adding New Features

### Adding a New Company Scraper

1. Create `tools/scrapers/{company}_scraper.py`
2. Implement `scrape_jobs(playwright_page) -> List[dict]`
3. Follow existing scraper patterns (see `netflix_scraper.py`)
4. Add company to `AVAILABLE_COMPANIES` in `web/app.py`
5. Test thoroughly before submitting PR

### Adding New Agents

1. Place in appropriate `agents/` subdirectory:
   - `agents/discovery/` - Job discovery and scraping
   - `agents/scoring/` - Job evaluation
   - `agents/cover_letter/` - Cover letter generation
   - `agents/auto_apply/` - Form filling
   - `agents/common/` - Shared utilities

2. Follow agent patterns:
   ```python
   from utils.logging import get_logger
   logger = get_logger(__name__)

   @dataclass(slots=True)
   class ResultClass:
       ...

   async def main_function(...):
       # Use Playwright for web interaction
       # Use Gemini for AI features
       ...
   ```

3. Support mock mode for testing
4. Add comprehensive logging
5. Include docstrings and type hints

## Coding Guidelines

- **Python Style**: Follow PEP 8
- **Type Hints**: Use type hints for function signatures
- **Async**: Use `async/await` for I/O operations
- **Logging**: Use `utils.logging.get_logger(__name__)`
- **Error Handling**: Use try/except with specific exceptions
- **Testing**: Write tests for new functionality

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_agents.py

# Run with coverage
pytest --cov=agents --cov=web tests/
```

## Database Changes

If you modify the database schema:

1. Update `database/schema.sql`
2. Document changes in migration notes
3. Test with fresh database creation
4. Update `utils/db_client.py` if needed

## Documentation

- Update README.md for major features
- Add to `docs/` for detailed guides
- Include docstrings in code
- Update Copilot instructions if architecture changes

## Pull Request Process

1. **Create Branch**: `git checkout -b feature/your-feature-name`
2. **Make Changes**: Implement your feature
3. **Test**: Run tests and verify functionality
4. **Commit**: Use clear, descriptive commit messages
5. **Push**: `git push origin feature/your-feature-name`
6. **PR**: Create pull request with description

### PR Requirements

- [ ] All tests pass
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] No syntax errors
- [ ] Tested on your local machine

## Common Tasks

### Adding Environment Variables

1. Add to `.env.example` with documentation
2. Update README.md configuration section
3. Update `production_check.sh` if critical
4. Load in code using `python-dotenv`

### Updating Dependencies

1. Add to `requirements.txt`
2. Test installation: `pip install -r requirements.txt`
3. Document why dependency is needed

### Fixing Bugs

1. Write test that reproduces bug
2. Fix the bug
3. Verify test passes
4. Submit PR with test and fix

## Getting Help

- Open an issue for bugs or features
- Check existing documentation in `docs/`
- Review existing code for patterns
- Ask questions in PR comments

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
