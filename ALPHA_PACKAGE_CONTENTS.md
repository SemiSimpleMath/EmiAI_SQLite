# Alpha Package Contents

This document describes what is included and excluded when creating the alpha distribution package using `create_alpha_package.py`.

## ✅ Included in Alpha Package

### Directories
- **`app/`** - Main application code (with exclusions below)
- **`resources/`** - Template resource files (user-specific JSON files excluded)
- **`docs/`** - Documentation
- **`tools/`** - Database utilities

### Root Files
- `.gitignore` - Git ignore rules
- `config.py` - Application configuration
- `requirements.txt` - Python dependencies
- `run_flask.py` - Flask server launcher
- `run.py` - Main application launcher
- `setup.py` - Initial setup wizard
- `README.md` - Main documentation
- `QUICK_START.md` - Quick start guide
- `INSTALL.md` - Installation instructions
- `GOOGLE_OAUTH_IMPLEMENTATION.md` - OAuth technical details
- `GOOGLE_OAUTH_USER_GUIDE.md` - OAuth user guide
- `reset_corrupted_database.sql` - Database recovery script
- `RESET_GUIDE.md` - Environment reset guide

### Special Notes
- **`app/assistant/lib/credentials/credentials.json`** - **NOT included in package**
  - Distributed separately via email to alpha testers
  - See `CREDENTIALS_SETUP_INSTRUCTIONS.md` for setup guide

## ❌ Excluded from Alpha Package

### Root-Level Directories
- `_archive/` - Old/deprecated code
- `chroma_db/` - Vector database (created fresh by setup)
- `instance/` - User-specific Flask instance
- `logs/` - User log files
- `migration_scripts/` - PostgreSQL migration scripts (not needed)
- `postgresql_to_sqlite_migration/` - PostgreSQL migration (not needed)
- `sqlite_utilities/` - Moved to `tools/`
- `tests/` - Test suite (not needed for alpha)
- `templates/` - Old standalone templates (deprecated)
- `uploads/` - User uploads
- `.git/` - Git repository
- `.vscode/`, `.idea/`, `.vs/` - IDE settings
- `__pycache__/` - Python cache
- `.pytest_cache/` - Test cache

### Root-Level Files
- `.env` - User's API keys (created by setup wizard)
- `*.db`, `*.sqlite`, `*.sqlite3` - Database files (created fresh)
- `*.log` - Log files
- `*.iml` - IDE project files
- `user_settings.json` - User settings (created by setup wizard)
- `create_alpha_package.py` - Package creation script
- `run_kg_explorer.py` - Standalone app (deprecated)
- `run_migration.py` - PostgreSQL migration script
- `run_repair_pipeline.py` - Maintenance script
- `requirements_full.txt` - Old requirements file
- `ALPHA_PACKAGE_SUMMARY.md` - Internal documentation
- `ALPHA_RELEASE.md` - Internal documentation

### File Types (Everywhere)
- `__pycache__/` directories
- `*.pyc`, `*.pyo` - Python bytecode
- `*.db`, `*.sqlite`, `*.sqlite3` - Database files
- `*.log` - Log files
- `node_modules/` - NPM packages (reinstalled by setup)

### Specific Exclusions
- **`resources/*.json`** - User-specific resource files (created by setup wizard)
- **`app/daily_summaries/`** - User-generated summaries
- **`app/assistant/lib/credentials/token.pickle`** - User's OAuth token (created during OAuth)
- **`app/assistant/lib/credentials/token.json`** - User's OAuth token (old format)
- **`app/assistant/lib/credentials/*.pem`** - SSL certificates

## 🔒 Security Notes

### Distributed Separately via Email
- **`credentials.json`** - OAuth client ID/secret
  - While technically safe for desktop apps, distributed via email to avoid GitHub secret scanning
  - Alpha testers receive this file separately with setup instructions

### What Must Be Excluded
- **`token.pickle`/`token.json`** - User-specific OAuth tokens (grants access to user's Google account)
- **`.env`** - User's API keys (OpenAI, etc.)
- **`user_settings.json`** - User's personal settings
- **`*.db`** - User's personal data
- **`*.pem`** - SSL certificates

## 📦 Package Size Optimization

The exclusions significantly reduce package size by removing:
- Development artifacts (cache, logs, IDE settings)
- User-generated content (database, uploads, summaries)
- Migration scripts (only needed for PostgreSQL → SQLite)
- Test suite (not needed for end users)
- Git history (not needed for distribution)

## 🚀 What Users Need to Do

After extracting the alpha package, users must:
1. Run `setup.py` to:
   - Create virtual environment
   - Install dependencies
   - Initialize database
   - Configure API keys
   - Optionally authenticate with Google OAuth
2. Run `run_flask.py` to start the application

All excluded files/directories will be created automatically during setup or runtime.

