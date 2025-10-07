# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

pyFileIndexer is a file indexing system that scans directories and creates a SQLite database of file metadata and hashes (MD5, SHA1, SHA256). It helps track files across multiple storage locations (local, USB, NAS, cloud) for easy searching and deduplication.

## Key Commands

### Development
```bash
# Install dependencies (uses uv package manager)
uv sync

# Run the indexer
uv run python pyFileIndexer/main.py <path> --machine_name <name> --db_path <db_file> --log_path <log_file>

# Run web interface locally
uv run python pyFileIndexer/main.py --web --db_path indexer.db --port 8000

# Merge multiple databases
uv run python pyFileIndexer/main.py --merge --source db1.db db2.db db3.db --db_path merged.db

# Build Docker image
docker build -t pyfileindexer .

# Run indexer via Docker (scanning files)
docker run --rm -v $(pwd):$(pwd) pyfileindexer $(pwd) --db_path $(pwd)/indexer.db --log_path $(pwd)/indexer.log

# Run web interface via Docker
docker run --rm -p 8000:8000 --tmpfs /data pyfileindexer --web --db_path /data/indexer.db --port 8000
# Or with persistent data:
docker run --rm -p 8000:8000 -v $(pwd)/data:/data pyfileindexer --web --db_path /data/indexer.db --port 8000
```

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_database.py

# Run with coverage
uv run pytest --cov=pyFileIndexer --cov-report=html

# Run parallel tests
uv run pytest -n auto

# Run only unit tests
uv run pytest -m unit

# Run only integration tests
uv run pytest -m integration
```

### Frontend Development
```bash
cd frontend
pnpm install
pnpm run dev      # Development server
pnpm run build    # Production build
pnpm run preview  # Preview production build
```

## Architecture

### Core Components

1. **main.py**: Entry point that orchestrates the scanning process
   - Uses producer-consumer pattern with threading
   - Single-threaded directory traversal followed by file hash calculation
   - Direct disk database operations during scanning

2. **database.py**: Database abstraction layer
   - SQLAlchemy ORM with SQLite backend
   - Direct disk database operations for data persistence
   - Thread-safe with SessionLock for concurrent access

3. **models.py**: Data models
   - `FileHash`: Stores file size and hash values (MD5, SHA1, SHA256)
   - `FileMeta`: Stores file metadata (path, name, dates, machine, operation type)
   - Separate tables for normalization - multiple files can reference same hash

4. **config.py**: Configuration management using Dynaconf
   - Loads from `settings.toml` and `.secrets.toml`
   - Environment variables with `DYNACONF_` prefix

5. **web_server.py**: FastAPI-based web interface
   - Provides REST API for file searching, statistics, and duplicate detection
   - Serves static React frontend from `frontend/dist`

6. **archive_scanner.py**: Archive file scanning
   - Supports ZIP, TAR, RAR formats
   - Creates virtual paths for archived files (`archive_path::internal_file_path`)

### Scanning Workflow

1. Directory traversal collects file paths into queue
2. Worker thread processes files from queue:
   - Checks if file exists in DB with same size/timestamps
   - Skips unchanged files for efficiency
   - Calculates hashes for new/modified files
   - Updates disk database directly with ADD/MOD operations

### File Filtering

The `.ignore` file controls which paths to skip:
- Lines without `/`: Skip directories with exact name match
- Lines with `/`: Skip if path contains this partial string
- Automatically skips directories starting with `.` or `_`
- Comments supported with `#`

## Database Schema

- `file_hash` table: Deduplicated hash storage
- `file_meta` table: File metadata with foreign key to hash
- Indexed columns for efficient lookups: hashes, file names, paths
- Operation tracking: ADD for new files, MOD for modified files
- Archive support: `is_archived` field (0/1) and `archive_path` field for compressed file handling

## Archive Scanning

### Supported Formats
- ZIP (.zip) - No external dependencies required
- TAR (.tar, .tar.gz, .tgz, .tar.bz2, .tbz2, .tar.xz, .txz) - No external dependencies required
- RAR (.rar) - Requires external extraction tool (see System Dependencies below)

### System Dependencies

**RAR Support Requirements:**
RAR file scanning requires one of the following extraction tools to be installed:
- **unar** (recommended) - Open source, available on most platforms
- **unrar** - Official RAR tool
- **7z** - 7-Zip command line tool

**Installation:**
```bash
# macOS (using Homebrew)
brew install unar

# Debian/Ubuntu Linux
apt-get install unar

# RHEL/CentOS/Fedora
yum install unar

# Docker
# Already included in the Dockerfile
```

If no RAR tool is available, RAR files will be skipped with a warning message.

### Configuration
Add these settings to `settings.toml`:
```toml
# Archive scanning configuration
scan_archives = true  # Enable/disable archive scanning
max_archive_size = 524288000  # Maximum archive size (500MB)
max_archive_file_size = 104857600  # Maximum size for files within archives (100MB)
```

### Virtual Paths
Files within archives use virtual path format: `archive_path::internal_file_path`

Example: `/path/to/archive.zip::folder/file.txt`

### Database Fields
- `is_archived`: 1 for files within archives, 0 for regular files
- `archive_path`: Full path to the containing archive (NULL for regular files)