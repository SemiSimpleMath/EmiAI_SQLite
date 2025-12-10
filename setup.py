#!/usr/bin/env python3
"""
EmiAi Setup Script
Initializes the application for first-time use
"""

import sys
import subprocess
import os
from pathlib import Path

def print_header(text):
    """Print a formatted header"""
    print("\n" + "="*80)
    print(f"  {text}")
    print("="*80)

def print_step(step_num, total_steps, text):
    """Print a formatted step"""
    print(f"\n[{step_num}/{total_steps}] {text}")

def check_python_version():
    """Check if Python version is 3.10+"""
    print_step(1, 8, "Checking Python version...")
    
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print(f"❌ ERROR: Python 3.10+ required, you have {version.major}.{version.minor}")
        return False
    
    print(f"✅ Python {version.major}.{version.minor}.{version.micro} detected")
    return True

def create_virtual_environment():
    """Create a Python virtual environment"""
    print_step(2, 8, "Creating virtual environment...")
    
    venv_path = Path(".venv")
    if venv_path.exists():
        print("⚠️  Virtual environment already exists, skipping...")
        return True
    
    try:
        subprocess.run([sys.executable, "-m", "venv", ".venv"], check=True)
        print("✅ Virtual environment created at .venv/")
        
        # Ensure pip is available in the venv
        python_cmd = get_python_command()
        try:
            print("   Ensuring pip is available...")
            subprocess.run([python_cmd, "-m", "ensurepip", "--default-pip"], check=False)
            print("   ✅ pip is ready")
        except Exception as e:
            print(f"   ⚠️  Note: {e}")
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: Failed to create virtual environment: {e}")
        return False

def get_pip_command():
    """Get the pip command for the current OS"""
    if sys.platform == "win32":
        return str(Path(".venv") / "Scripts" / "pip.exe")
    else:
        return str(Path(".venv") / "bin" / "pip")

def install_dependencies():
    """Install Python dependencies"""
    print_step(3, 8, "Installing dependencies...")
    
    pip_cmd = get_pip_command()
    python_cmd = get_python_command()
    
    # Try to upgrade pip (non-critical)
    try:
        print("\n   Upgrading pip...")
        subprocess.run([pip_cmd, "install", "--upgrade", "pip"], check=False)
    except Exception as e:
        print(f"   ⚠️  Could not upgrade pip (non-critical): {e}")
    
    # Install requirements (critical)
    try:
        print("\n   Installing packages from requirements.txt...")
        subprocess.run([pip_cmd, "install", "-r", "requirements.txt"], check=True)
        print("✅ All dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: Failed to install dependencies: {e}")
        return False
    
    # Skip spaCy for alpha (not needed without KG)
    print("\n⏸️  spaCy model download skipped (not needed for alpha)")
    print("   Knowledge Graph features disabled in this release")
    return True

def check_credentials():
    """Check if required credential files exist"""
    print_step(4, 8, "Checking credentials...")
    
    creds_dir = Path("app/assistant/lib/credentials")
    required_files = {
        "credentials.json": "Google API credentials (for Calendar/Gmail)",
        "token.pickle": "Google API token (will be created on first auth)"
    }
    
    missing = []
    for file, desc in required_files.items():
        file_path = creds_dir / file
        if not file_path.exists():
            if file == "token.pickle":
                print(f"⚠️  {file} - {desc} (will be created when you authorize)")
            else:
                print(f"❌ MISSING: {file} - {desc}")
                missing.append(file)
        else:
            print(f"✅ {file} found")
    
    if missing:
        print("\n⚠️  WARNING: Some credentials are missing.")
        print("   You'll need to provide these before using Calendar/Gmail features.")
        print("   See docs/gettin_started/ for instructions.")
    
    return True  # Not critical, just warn

def create_directories():
    """Create necessary directories"""
    print_step(5, 8, "Creating directories...")
    
    directories = [
        "logs",
        "uploads",
        "instance",
        "app/personal_info",
        "chroma_db"
    ]
    
    for dir_path in directories:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"✅ Created {dir_path}/")
    
    return True

def get_python_command():
    """Get the Python command for the current OS from venv"""
    if sys.platform == "win32":
        return str(Path(".venv") / "Scripts" / "python.exe")
    else:
        return str(Path(".venv") / "bin" / "python")

def initialize_database():
    """Initialize the database tables"""
    print_step(6, 8, "Initializing database...")
    
    try:
        python_cmd = get_python_command()
        
        # Create a temporary script to initialize the database (skip KG tables for alpha)
        init_script = """
import sys
sys.path.insert(0, '.')

print("   Creating core application tables...")
from app.database.table_initializer import initialize_always_on_tables
initialize_always_on_tables()

print("   ⏸️  Knowledge graph tables skipped (disabled in alpha)")
"""
        
        # Run using venv Python
        result = subprocess.run(
            [python_cmd, "-c", init_script],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=True
        )
        
        if result.stdout:
            print(result.stdout)
        
        print("✅ Database tables initialized")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: Failed to initialize database: {e}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False
    except Exception as e:
        print(f"❌ ERROR: Failed to initialize database: {e}")
        import traceback
        traceback.print_exc()
        return False

def seed_taxonomy():
    """Seed the taxonomy from the official ontology"""
    print_step(7, 8, "Seeding taxonomy ontology...")
    
    # Skip taxonomy seeding for alpha
    print("⏸️  Taxonomy seeding skipped (disabled in alpha)")
    print("   Knowledge Graph and Taxonomy features will be enabled in future releases")
    return True

def create_default_resources():
    """Create default resource files if they don't exist"""
    print_step(8, 8, "Checking resource files...")
    
    resources_dir = Path("resources")
    
    # Check if critical resource files exist
    required_resources = [
        "resource_user_data.json",
        "resource_assistant_data.json",
        "resource_assistant_personality_data.json",
        "resource_chat_guidelines_data.json"
    ]
    
    missing = []
    for resource in required_resources:
        if not (resources_dir / resource).exists():
            missing.append(resource)
    
    if missing:
        print(f"\n⚠️  WARNING: Missing resource files:")
        for res in missing:
            print(f"   - {res}")
        print("\n   You'll need to run the setup wizard on first launch.")
        print("   Navigate to http://localhost:5000/setup")
    else:
        print("✅ All resource files present")
    
    return True

def print_next_steps():
    """Print next steps for the user"""
    print_header("✅ SETUP COMPLETE!")
    
    print("\n📋 Next Steps:\n")
    
    if sys.platform == "win32":
        activate_cmd = ".venv\\Scripts\\activate"
        python_cmd = "python"
    else:
        activate_cmd = "source .venv/bin/activate"
        python_cmd = "python3"
    
    print(f"1. Activate the virtual environment:")
    print(f"   {activate_cmd}")
    print()
    print(f"2. Run the Flask application:")
    print(f"   {python_cmd} run_flask.py")
    print()
    print("3. Open your browser to:")
    print("   http://localhost:5000")
    print()
    print("4. If this is your first time, complete the setup wizard at:")
    print("   http://localhost:5000/setup")
    print()
    print("📚 Documentation:")
    print("   - Quick Start: QUICK_START.md")
    print("   - Full Docs: docs/")
    print("   - Database Setup: docs/DATABASE_SETUP_GUIDE.md")
    print()
    print("🆘 Need Help?")
    print("   - Check docs/gettin_started/")
    print("   - Review README.md")
    print()

def main():
    """Main setup function"""
    print_header("🚀 EmiAi Setup")
    print("\nThis script will set up your EmiAi environment.\n")
    
    # Change to script directory
    os.chdir(Path(__file__).parent)
    
    steps = [
        ("Checking Python version", check_python_version),
        ("Creating virtual environment", create_virtual_environment),
        ("Installing dependencies", install_dependencies),
        ("Checking credentials", check_credentials),
        ("Creating directories", create_directories),
        ("Initializing database", initialize_database),
        ("Seeding taxonomy", seed_taxonomy),
        ("Checking resources", create_default_resources)
    ]
    
    failed = []
    
    for step_name, step_func in steps:
        try:
            if not step_func():
                failed.append(step_name)
        except Exception as e:
            print(f"\n❌ ERROR in {step_name}: {e}")
            import traceback
            traceback.print_exc()
            failed.append(step_name)
    
    if failed:
        print_header("❌ SETUP INCOMPLETE")
        print("\nThe following steps failed:")
        for step in failed:
            print(f"   ❌ {step}")
        print("\nPlease fix the errors and run setup.py again.")
        return 1
    
    print_next_steps()
    return 0

if __name__ == "__main__":
    sys.exit(main())

