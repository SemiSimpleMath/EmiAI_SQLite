#!/usr/bin/env python3
"""
EmiAi Setup Script - FULL VERSION
Initializes the application with ALL features (requires C++ Build Tools on Windows)
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
    
    # Install FULL requirements (critical)
    print("\n   📦 Installing FULL requirements (includes ChromaDB, spaCy, ML libraries)...")
    print("   ⚠️  This may take 10-15 minutes and requires C++ Build Tools on Windows")
    
    try:
        subprocess.run([pip_cmd, "install", "-r", "requirements.txt"], check=True)
        print("✅ All dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: Failed to install dependencies: {e}")
        print("\n💡 TROUBLESHOOTING:")
        print("   On Windows, you may need Microsoft C++ Build Tools:")
        print("   https://visualstudio.microsoft.com/visual-cpp-build-tools/")
        print("   Select 'Desktop development with C++' during installation")
        return False
    
    # Download spaCy language model (critical for KG/Taxonomy)
    try:
        print("\n   Downloading spaCy language model...")
        subprocess.run([python_cmd, "-m", "spacy", "download", "en_core_web_sm"], check=True)
        print("✅ spaCy model installed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: Failed to download spaCy model: {e}")
        return False

def check_credentials():
    """Check if required credential files exist"""
    print_step(4, 8, "Checking credentials...")
    
    creds_dir = Path("app/assistant/lib/credentials")
    required_files = {
        "credentials.json": "Google API credentials (for Calendar/Gmail)",
        "token.pickle": "Google API token (will be created on first auth)"
    }
    
    all_present = True
    for filename, description in required_files.items():
        file_path = creds_dir / filename
        if file_path.exists():
            print(f"✅ {filename} found")
        else:
            if filename == "token.pickle":
                print(f"⚠️  {filename} - {description} (will be created when you authorize)")
            else:
                print(f"❌ {filename} - {description} (MISSING)")
                all_present = False
    
    return True  # Don't fail setup if only token.pickle is missing

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
    
    for dir_name in directories:
        dir_path = Path(dir_name)
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created {dir_name}/")
    
    return True

def get_python_command():
    """Get the python command for the current OS"""
    if sys.platform == "win32":
        return str(Path(".venv") / "Scripts" / "python.exe")
    else:
        return str(Path(".venv") / "bin" / "python")

def initialize_database():
    """Initialize the database tables"""
    print_step(6, 8, "Initializing database...")
    
    try:
        python_cmd = get_python_command()
        
        # Create a temporary script to initialize the database (FULL VERSION - includes KG)
        init_script = """
import sys
sys.path.insert(0, '.')

print("   Creating core application tables...")
from app.database.table_initializer import initialize_always_on_tables
initialize_always_on_tables()

print("   Creating knowledge graph tables...")
from app.database.table_initializer import initialize_kg_tables
initialize_kg_tables()
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
    
    try:
        python_cmd = get_python_command()
        
        # Create a temporary script to seed taxonomy
        seed_script = """
import sys
sys.path.insert(0, '.')

from app.assistant.kg_core.kg_setup.seed_taxonomy_from_ontology import main as seed_main
seed_main()
"""
        
        # Run using venv Python
        result = subprocess.run(
            [python_cmd, "-c", seed_script],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=True
        )
        
        if result.stdout:
            print(result.stdout)
        
        print("✅ Taxonomy seeded successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: Failed to seed taxonomy: {e}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False
    except Exception as e:
        print(f"❌ ERROR: Failed to seed taxonomy: {e}")
        import traceback
        traceback.print_exc()
        return False

def create_default_resources():
    """Create default resource files if they don't exist"""
    print_step(8, 8, "Checking resource files...")
    
    resources_dir = Path("resources")
    required_files = [
        "resource_user_data.json",
        "resource_assistant_data.json",
        "resource_assistant_personality_data.json",
        "resource_chat_guidelines_data.json"
    ]
    
    missing_files = []
    for filename in required_files:
        file_path = resources_dir / filename
        if not file_path.exists():
            missing_files.append(filename)
    
    if missing_files:
        print("\n⚠️  WARNING: Missing resource files:")
        for filename in missing_files:
            print(f"   - {filename}")
        print("\n   You'll need to run the setup wizard on first launch.")
        print("   Navigate to http://localhost:8000/setup")
    else:
        print("✅ All resource files present")
    
    return True

def print_next_steps():
    """Print next steps for the user"""
    print_header("✅ SETUP COMPLETE - FULL VERSION")
    print("\n🎉 EmiAi is ready to use with ALL features enabled!")
    print("\n📋 Next steps:")
    print("   1. Start the application:")
    print("      python run_flask.py")
    print("\n   2. Open your browser:")
    print("      http://localhost:8000")
    print("\n   3. Complete the setup wizard (if first time)")
    print("\n✨ FULL VERSION FEATURES:")
    print("   ✅ AI Chat (OpenAI/Anthropic)")
    print("   ✅ Gmail, Calendar, Tasks")
    print("   ✅ Knowledge Graph")
    print("   ✅ Taxonomy Classification")
    print("   ✅ Entity Extraction")
    print("   ✅ RAG (Retrieval Augmented Generation)")
    print("   ✅ Graph Visualizer")
    print("   ✅ Taxonomy Viewer")
    print()

def main():
    """Main setup function"""
    print_header("🚀 EmiAi Setup - FULL VERSION")
    print("\n⚠️  This version includes ALL features:")
    print("   - Knowledge Graph")
    print("   - Taxonomy Classification")
    print("   - Advanced NLP (spaCy)")
    print("   - Vector Search (ChromaDB)")
    print("\n⚠️  REQUIREMENTS:")
    print("   - Python 3.10+")
    print("   - Microsoft C++ Build Tools (Windows)")
    print("   - 10-15 minute installation time")
    print("   - ~3-4 GB disk space\n")
    
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
        print("\nPlease fix the errors and run setup_full.py again.")
        return 1
    
    print_next_steps()
    return 0

if __name__ == "__main__":
    sys.exit(main())

