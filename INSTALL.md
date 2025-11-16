# EmiAi Installation Guide

Welcome to EmiAi! This guide will help you get started.

## 📋 Prerequisites

Before you begin, you **ONLY** need:

- **Python 3.10 or higher** ([Download here](https://www.python.org/downloads/))
  - Make sure to check "Add Python to PATH" during installation on Windows
  - Verify: `python --version` should show 3.10+
- **Internet connection** (to download dependencies during setup)
- **4GB RAM** minimum (8GB recommended)
- **2GB disk space** for the application and database

**That's it!** The setup script will install everything else automatically.

## 🔧 What the Setup Script Does

When you run `setup.py`, it will automatically:

1. ✅ Check your Python version
2. ✅ Create a virtual environment (`.venv/`)
3. ✅ Install all required packages into the venv:
   - Flask (web framework)
   - SQLAlchemy (database)
   - ChromaDB (vector database)
   - OpenAI, Anthropic (AI APIs)
   - And ~50 other dependencies
4. ✅ Initialize the SQLite database
5. ✅ Seed the taxonomy (1500+ categories)
6. ✅ Create necessary directories

**All packages are installed in the virtual environment** - they won't affect your system Python!

## 🚀 Quick Installation

### Step 1: Extract the Archive

Extract the EmiAi zip/tar file to your desired location.

### Step 2: Run Setup

Open a terminal/command prompt in the extracted directory and run:

```bash
python setup.py
```

The setup script will:
- ✅ Check your Python version
- ✅ Create a virtual environment
- ✅ Install all dependencies
- ✅ Initialize the database
- ✅ Seed the taxonomy
- ✅ Create necessary directories

This may take 5-10 minutes depending on your internet speed.

### Step 3: Activate Virtual Environment

**Windows:**
```bash
.venv\Scripts\activate
```

**Mac/Linux:**
```bash
source .venv/bin/activate
```

You should see `(.venv)` appear in your terminal prompt.

### Step 4: Start the Application

```bash
python run_flask.py
```

You should see:
```
 * Running on http://127.0.0.1:5000
```

### Step 5: Open in Browser

Open your web browser and navigate to:
```
http://localhost:5000
```

### Step 6: Complete Setup Wizard

On first launch, you'll be directed to the setup wizard at:
```
http://localhost:5000/setup
```

Follow the prompts to configure:
- Your name and preferences
- Emi's personality
- Communication style
- Your relationship

## 🔧 Configuration (Optional)

### Google Calendar & Gmail Integration

To use Calendar and Gmail features:

1. Create a Google Cloud Project
2. Enable Calendar API and Gmail API
3. Download OAuth credentials
4. Place `credentials.json` in: `app/assistant/lib/credentials/`
5. On first use, authorize the app (creates `token.pickle`)

See `docs/gettin_started/google_api_setup.md` for detailed instructions.

### Slack Integration

To use Slack integration:

1. Create a Slack App
2. Get your Bot Token
3. Configure in user settings

See `docs/gettin_started/slack_setup.md` for details.

## 🆘 Troubleshooting

### "Python not found"
- Install Python 3.10+ from python.org
- Make sure to check "Add Python to PATH" during installation

### "pip: command not found"
- Python installation might not be complete
- Try `python -m pip` instead of just `pip`

### "Port 5000 already in use"
- Another application is using port 5000
- Stop the other application or edit `config.py` to change the port

### "ModuleNotFoundError"
- Make sure virtual environment is activated
- Run `pip install -r requirements.txt` again

### Database errors
- Delete `emi.db` and restart
- Run setup.py again
- See `docs/DATABASE_SETUP_GUIDE.md`

### Setup wizard doesn't appear
- Clear browser cache
- Navigate manually to `http://localhost:5000/setup`

## 📚 Next Steps

After installation:

1. **Read the Quick Start Guide**: `QUICK_START.md`
2. **Explore the Documentation**: Check `docs/` folder
3. **Try the Chat**: Start chatting with Emi!
4. **Explore Tools**:
   - Knowledge Graph Visualizer: `http://localhost:5000/kg-visualizer`
   - Taxonomy Viewer: `http://localhost:5000/taxonomy_webviewer`
   - Entity Cards: `http://localhost:5000/entity_cards`

## 🐛 Reporting Issues

If you encounter any problems:

1. Check the troubleshooting section above
2. Review `logs/emi_logs.log` for error messages
3. Contact support with:
   - Error message
   - Steps to reproduce
   - Your OS and Python version

## 📞 Support

- **Email**: [Your support email]
- **Documentation**: `docs/` folder
- **GitHub Issues**: [Your repo URL]

## 🎉 You're Ready!

Welcome to EmiAi! Start by saying "Hi" in the chat.

For detailed features and usage, see `QUICK_START.md` and the documentation in `docs/`.

