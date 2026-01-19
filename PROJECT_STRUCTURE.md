# Project Structure

```
doubao-earphone-to-obsidian/
├── README.md              # Chinese documentation
├── README_EN.md           # English documentation
├── SHOWCASE.md            # Hacker News optimized overview
├── TECHNICAL.md           # Technical architecture details
├── CONTRIBUTING.md        # Contribution guidelines
├── LICENSE                # GPL-3.0 license
├── requirements.txt       # Python dependencies
├── .env.example          # Environment configuration template
├── main.py               # Core application
├── data/                 # SQLite database and logs
└── .venv/                # Python virtual environment
```

## File Descriptions

### Documentation
- **README.md**: Comprehensive Chinese documentation with features, installation, and usage
- **README_EN.md**: English version for international audience
- **SHOWCASE.md**: Concise overview optimized for Hacker News and developer communities
- **TECHNICAL.md**: Deep technical architecture and implementation details
- **CONTRIBUTING.md**: Guidelines for contributors and development setup

### Core Files
- **main.py**: Main application with voice monitoring, pattern recognition, and file writing
- **requirements.txt**: Python package dependencies (Playwright, Pydantic, etc.)
- **.env.example**: Configuration template for environment variables

### Data
- **data/voice_notes.db**: SQLite database for deduplication and message history
- **data/logs/**: Application logs and debug information

## Quick Navigation

- **New users**: Start with [README_EN.md](README_EN.md)
- **Developers**: Check [TECHNICAL.md](TECHNICAL.md) and [CONTRIBUTING.md](CONTRIBUTING.md)
- **Hacker News**: See [SHOWCASE.md](SHOWCASE.md) for quick overview
- **Contributors**: Read [CONTRIBUTING.md](CONTRIBUTING.md) for development setup