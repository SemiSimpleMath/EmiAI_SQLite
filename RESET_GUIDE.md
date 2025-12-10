# Complete Reset Guide

## Test Alpha Package (Simulate New User Install)

This tests the full new user experience from a clean alpha package.

### Step 1: Delete old alpha package

```powershell
cd E:\
rmdir /s /q Emi_alpha
```

### Step 2: Create fresh alpha package

```powershell
cd E:\EmiAi_sqlite
python create_alpha_package.py
```

### Step 3: Test as a new user

```powershell
cd E:\Emi_alpha
python setup.py
```

### Step 4: Start Flask

```powershell
.venv\Scripts\Activate.ps1
python run_flask.py
```

Navigate to `http://127.0.0.1:8000` and complete the setup wizard.

---

## Reset Development Database (In-Place)

To reset your development environment without recreating the alpha package:

```powershell
cd E:\EmiAi_sqlite

# Delete database
Remove-Item -Force instance\app.db -ErrorAction SilentlyContinue
Remove-Item -Force app\app.db -ErrorAction SilentlyContinue

# Delete user settings
Remove-Item -Force app\assistant\user_settings_manager\user_settings_data\user_settings.json -ErrorAction SilentlyContinue

# Delete vector DB
Remove-Item -Recurse -Force chroma_db -ErrorAction SilentlyContinue

# Delete resource configs (will recreate in setup wizard)
Remove-Item -Force resources\resource_user_data.json -ErrorAction SilentlyContinue
Remove-Item -Force resources\resource_assistant_data.json -ErrorAction SilentlyContinue
Remove-Item -Force resources\resource_assistant_personality_data.json -ErrorAction SilentlyContinue
Remove-Item -Force resources\resource_relationship_config.json -ErrorAction SilentlyContinue
Remove-Item -Force resources\resource_chat_guidelines_data.json -ErrorAction SilentlyContinue

# Delete virtual environment (if you want fresh dependencies)
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
```

### 2. Run setup

```powershell
python setup.py
```

This will:
- Create `.venv`
- Install all dependencies
- Initialize database
- Seed taxonomy

### 3. Activate virtual environment

```powershell
.venv\Scripts\Activate.ps1
```

### 4. Start Flask

```powershell
python run_flask.py
```

Navigate to `http://127.0.0.1:8000` and complete the setup wizard.

---

## What You Need to Add Back

After reset, you'll need to:

1. **API Keys** - Create `.env` file with:
   ```
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   ELEVENLABS_API_KEY=...
   DEEPGRAM_API_KEY=...
   ```

2. **Google OAuth** (for email/calendar/tasks) - Add to `app/assistant/lib/core_tools/credentials/`:
   - `credentials.json` (from Google Cloud Console)
   - `token.pickle` (generated on first OAuth flow)

---

## Quick Troubleshooting

**Setup fails on dependencies:**
```powershell
# Ensure pip is updated in venv
.venv\Scripts\python.exe -m pip install --upgrade pip
```

**Can't activate venv:**
```powershell
# May need to allow script execution
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Setup wizard doesn't appear:**
- Navigate directly to: `http://127.0.0.1:8000/setup`

---

That's it! Complete fresh start in 5 steps. 🚀

