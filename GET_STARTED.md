# 🚀 Welcome to Job Finder!

An AI-powered job application automation system.

## What It Does

1. **Scrapes Jobs** - Automatically extracts job listings from top tech companies
2. **Smart Matching** - AI scores each job based on your skills and preferences
3. **Auto-Apply** - Fills and submits applications automatically (optional)
4. **Web Interface** - User-friendly dashboard to manage everything

## Supported Companies

Netflix • Meta • Google • IBM • Samsung • Vodafone • Rockstar • Rebellion • Miniclip

## Get Started in 3 Steps

### 1️⃣ Install

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2️⃣ Setup

```bash
# Create database
createdb jobfinder
psql -d jobfinder -f database/schema.sql

# Configure
cp .env.example .env
# Add your GEMINI_API_KEY and DATABASE_URL to .env
```

### 3️⃣ Run

```bash
./start_web.sh
```

Open **http://localhost:5000** 🎉

## Documentation

- 📖 [QUICKSTART.md](QUICKSTART.md) - Detailed setup guide
- 🏗️ [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - How it works
- 🤖 [docs/AUTO_APPLY_GUIDE.md](docs/AUTO_APPLY_GUIDE.md) - Auto-apply feature
- 🚀 [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment
- 🤝 [CONTRIBUTING.md](CONTRIBUTING.md) - How to contribute

## Requirements

- Python 3.9+
- PostgreSQL 12+
- Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))

## Need Help?

Run the verification script:

```bash
./verify_setup.sh
```

Check [QUICKSTART.md](QUICKSTART.md) for troubleshooting.

## Features

✅ Web-based job search  
✅ AI-powered job matching  
✅ Multi-company scraping  
✅ Cover letter generation  
✅ Automated applications  
✅ Question discovery  
✅ Profile management  

## License

MIT License - See [LICENSE](LICENSE)

---

**Ready?** Run `./start_web.sh` and find your next job! 💼
