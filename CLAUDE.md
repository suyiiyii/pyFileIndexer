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

# Build Docker image
docker build -t pyfileindexer .

# Run via Docker
docker run --rm -v $(pwd):$(pwd) pyfileindexer $(pwd) --db_path $(pwd)/indexer.db --log_path $(pwd)/indexer.log
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