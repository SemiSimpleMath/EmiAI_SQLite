#!/usr/bin/env python3
"""
Create Alpha Package Script
Copies only necessary files from E:/EmiAi_sqlite to Emi_alpha folder
"""

import shutil
import os
from pathlib import Path
import json
import sys

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

def print_header(text):
    """Print a formatted header"""
    print("\n" + "="*80)
    print(f"  {text}")
    print("="*80)

def print_step(text):
    """Print a step"""
    print(f"\n> {text}")

def create_alpha_package():
    """Create the alpha package by copying necessary files"""
    
    # Source and destination
    source_root = Path("E:/EmiAi_sqlite")
    dest_root = Path("E:/Emi_alpha")
    
    print_header("Creating EmiAi Alpha Package")
    print(f"\nSource: {source_root}")
    print(f"Destination: {dest_root}")
    
    # Directories to copy (will be copied recursively)
    directories_to_copy = [
        "app",
        "resources",
        "docs",
        "tools",  # Database utilities
    ]
    
    # Root-level directories to EXCLUDE (will not be copied)
    root_dirs_to_exclude = [
        "_archive",  # Old/deprecated code
        "chroma_db",  # Vector database - will be created fresh
        "instance",  # User-specific Flask instance
        "logs",  # User logs
        "migration_scripts",  # PostgreSQL migration (not needed for alpha)
        "postgresql_to_sqlite_migration",  # PostgreSQL migration (not needed for alpha)
        "sqlite_utilities",  # Moved to tools/
        "tests",  # Test suite (not needed for alpha)
        "templates",  # Old standalone templates (not needed)
        "uploads",  # User uploads
        ".git",  # Git repository
        ".vscode",  # IDE settings
        ".idea",  # IDE settings
        ".vs",  # IDE settings
        "__pycache__",  # Python cache
        ".pytest_cache",  # Test cache
    ]
    
    # Files in root to copy
    root_files_to_copy = [
        ".gitignore",
        "config.py",
        "requirements_alpha.txt",  # Lightweight requirements (will be renamed to requirements.txt)
        "requirements.txt",  # Full requirements (will be renamed to requirements_full.txt)
        "run_flask.py",
        "run.py",
        "setup.py",  # Lightweight setup (alpha)
        "setup_full.py",  # Full setup (all features)
        "README.md",
        "QUICK_START.md",
        "INSTALL.md",
        "GOOGLE_OAUTH_IMPLEMENTATION.md",
        "GOOGLE_OAUTH_USER_GUIDE.md",
        "CREDENTIALS_SETUP_INSTRUCTIONS.md",  # Instructions for placing credentials.json
        "reset_corrupted_database.sql",
        "RESET_GUIDE.md",  # User guide for resetting environment
        "ALPHA_PACKAGE_CONTENTS.md",  # Documentation of what's included/excluded
        "UPGRADE_TO_FULL.md",  # Guide for upgrading to full version
    ]
    
    # Root-level files to EXCLUDE (will not be copied)
    root_files_to_exclude = [
        ".env",  # User's API keys
        "*.db",  # Database files
        "*.sqlite",  # Database files
        "*.sqlite3",  # Database files
        "*.log",  # Log files
        "*.iml",  # IDE files
        "user_settings.json",  # User settings
        "create_alpha_package.py",  # This script itself
        "run_kg_explorer.py",  # Standalone app (deprecated)
        "run_migration.py",  # PostgreSQL migration
        "run_repair_pipeline.py",  # Maintenance script
        "requirements_full.txt",  # Old requirements
        "ALPHA_PACKAGE_SUMMARY.md",  # Internal doc
        "ALPHA_RELEASE.md",  # Internal doc
    ]
    
    # Directories to exclude from app/ directory
    app_excludes = [
        "__pycache__",
        "*.pyc",
        "*.pyo",
        "*.db",
        ".pytest_cache",
    ]
    
    # Specific subdirectories within app/ to exclude
    app_subdirs_to_exclude = [
        # None currently - we want all of app/
    ]
    
    # Function to should_exclude path
    def should_exclude(path: Path, relative_to: Path) -> bool:
        """Check if a path should be excluded"""
        rel_path = path.relative_to(relative_to)
        rel_str = str(rel_path)
        
        # Exclude __pycache__ directories
        if "__pycache__" in path.parts:
            return True
        
        # Exclude .pyc files
        if path.suffix in [".pyc", ".pyo"]:
            return True
        
        # Exclude database files
        if path.suffix in [".db", ".sqlite", ".sqlite3"]:
            return True
        
        # Exclude log files
        if path.suffix == ".log":
            return True
        
        # Exclude node_modules
        if "node_modules" in path.parts:
            return True
        
        # Exclude .git directory
        if ".git" in path.parts:
            return True
        
        # Exclude .pytest_cache
        if ".pytest_cache" in path.parts:
            return True
        
        # Exclude .vscode, .idea (IDE settings)
        if any(ide in path.parts for ide in [".vscode", ".idea", ".vs"]):
            return True
        
        # Exclude personal resource files (will be created by setup wizard)
        if path.parent.name == "resources" and path.suffix == ".json":
            # Exclude ALL JSON files from resources/ - they're user-specific
            return True
        
        # Exclude daily summaries (user-generated content)
        if "daily_summaries" in path.parts:
            return True
        
        # Exclude chroma_db (vector database - will be created fresh)
        if "chroma_db" in path.parts:
            return True
        
        # Exclude uploads directory (user files)
        if "uploads" in path.parts:
            return True
        
        # Exclude credentials (OAuth tokens, but INCLUDE credentials.json for alpha testers)
        # IMPORTANT: credentials.json contains OAuth client ID/secret (safe for desktop apps)
        #            token.pickle contains user-specific OAuth token (must exclude)
        #            token.json is also user-specific (from old tasks tool)
        if "credentials" in path.parts:
            if path.name in ["token.pickle", "token.json"]:
                return True  # Exclude user's OAuth tokens
            if path.suffix in [".pem"]:
                return True  # Exclude certificates
            # Keep credentials.json for alpha testers
        
        # Exclude .env file (contains user's API keys)
        if path.name == ".env":
            return True
        
        return False
    
    # Step 1: Remove existing destination if it exists
    if dest_root.exists():
        print_step(f"Removing existing {dest_root.name} directory...")
        try:
            shutil.rmtree(dest_root)
            print(f"   [OK] Removed {dest_root}")
        except Exception as e:
            print(f"   [ERROR] Error removing directory: {e}")
            print(f"\n   [TIP] Close any terminals or explorer windows in {dest_root}")
            print(f"   [TIP] Or manually delete {dest_root} and run again")
            return False
    
    # Step 2: Create destination directory
    print_step("Creating destination directory...")
    dest_root.mkdir(parents=True, exist_ok=True)
    print(f"   [OK] Created {dest_root}")
    
    # Step 3: Copy root files
    print_step("Copying root files...")
    copied_files = 0
    for filename in root_files_to_copy:
        src_file = source_root / filename
        dest_file = dest_root / filename
        
        if src_file.exists():
            try:
                shutil.copy2(src_file, dest_file)
                print(f"   [OK] {filename}")
                copied_files += 1
            except Exception as e:
                print(f"   [ERROR] {filename}: {e}")
        else:
            print(f"   [WARN] {filename} not found (skipping)")
    
    print(f"\n   Copied {copied_files} root files")
    
    # Step 3.5: Rename requirements files
    # Alpha requirements → requirements.txt (default)
    alpha_req = dest_root / "requirements_alpha.txt"
    normal_req = dest_root / "requirements.txt"
    full_req_src = dest_root / "requirements.txt"
    full_req_dst = dest_root / "requirements_full.txt"
    
    # First, rename full requirements.txt to requirements_full.txt
    if full_req_src.exists():
        try:
            full_req_src.rename(full_req_dst)
            print(f"   [OK] Renamed requirements.txt → requirements_full.txt")
        except Exception as e:
            print(f"   [ERROR] Failed to rename full requirements: {e}")
    
    # Then rename alpha requirements to requirements.txt
    if alpha_req.exists():
        try:
            alpha_req.rename(normal_req)
            print(f"   [OK] Renamed requirements_alpha.txt → requirements.txt")
        except Exception as e:
            print(f"   [ERROR] Failed to rename alpha requirements: {e}")
    
    # Step 4: Copy directories
    print_step("Copying directories...")
    
    for dir_name in directories_to_copy:
        src_dir = source_root / dir_name
        dest_dir = dest_root / dir_name
        
        if not src_dir.exists():
            print(f"   [WARN] {dir_name}/ not found (skipping)")
            continue
        
        print(f"\n   [FOLDER] Copying {dir_name}/...")
        
        # Create destination directory
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Walk through source directory
        file_count = 0
        excluded_count = 0
        
        for src_path in src_dir.rglob("*"):
            if src_path.is_file():
                # Check if should be excluded
                if should_exclude(src_path, src_dir):
                    excluded_count += 1
                    continue
                
                # Calculate destination path
                rel_path = src_path.relative_to(src_dir)
                dest_path = dest_dir / rel_path
                
                # Create parent directories
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                try:
                    shutil.copy2(src_path, dest_path)
                    file_count += 1
                except Exception as e:
                    print(f"      [ERROR] Error copying {rel_path}: {e}")
        
        print(f"      [OK] Copied {file_count} files (excluded {excluded_count})")
    
    # Step 5: Create empty directories that app will need
    print_step("Creating empty directories for runtime...")
    
    runtime_dirs = [
        "logs",
        "uploads",
        "instance",
        "chroma_db",
    ]
    
    for dir_name in runtime_dirs:
        runtime_dir = dest_root / dir_name
        runtime_dir.mkdir(parents=True, exist_ok=True)
        
        # Create .gitkeep file
        gitkeep = runtime_dir / ".gitkeep"
        gitkeep.touch()
        
        print(f"   [OK] {dir_name}/")
    
    # Step 6: Create a README in the package
    print_step("Creating package README...")
    
    package_readme = dest_root / "PACKAGE_INFO.txt"
    with open(package_readme, "w") as f:
        f.write("EmiAi Alpha Package\n")
        f.write("=" * 80 + "\n\n")
        f.write("This is the EmiAi alpha release package.\n\n")
        f.write("To install:\n")
        f.write("1. Read INSTALL.md\n")
        f.write("2. Run: python setup.py\n")
        f.write("3. Activate venv and run: python run_flask.py\n\n")
        f.write("For detailed instructions, see INSTALL.md\n")
    
    print(f"   [OK] Created PACKAGE_INFO.txt")
    
    # Step 7: Calculate package size
    print_step("Calculating package size...")
    
    total_size = 0
    total_files = 0
    
    for path in dest_root.rglob("*"):
        if path.is_file():
            total_size += path.stat().st_size
            total_files += 1
    
    size_mb = total_size / (1024 * 1024)
    print(f"   [INFO] Total: {total_files} files, {size_mb:.2f} MB")
    
    # Step 8: Summary
    print_header("Package Creation Complete!")
    
    print("\n[PACKAGE] Alpha package created at:")
    print(f"   {dest_root}")
    print(f"\n[INFO] Package contents:")
    print(f"   - {total_files} files")
    print(f"   - {size_mb:.2f} MB")
    
    print("\n[NEXT] Next steps:")
    print(f"   1. Review the package in {dest_root}")
    print(f"   2. Test installation: cd {dest_root} && python setup.py")
    print(f"   3. Create archive: zip -r Emi_alpha.zip {dest_root.name}")
    print(f"      or: tar -czf Emi_alpha.tar.gz {dest_root.name}")
    
    print("\n[SUCCESS] Ready to distribute!\n")
    
    return True

if __name__ == "__main__":
    try:
        success = create_alpha_package()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[CANCEL] Cancelled by user")
        exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

