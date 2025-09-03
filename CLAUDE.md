# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Bot
```bash
python main.py
```

### Testing
Currently, this project does not have a formal test suite. The bot includes some internal testing commands:
- `!test_names` - Tests name extraction functionality in surveillance scenes
- Built-in validation and error handling throughout the codebase

### Dependencies
```bash
pip install -r requirements.txt
```

### Environment Setup
Copy `.env` file and configure required environment variables:
- `DISCORD_TOKEN` - Your Discord bot token
- `SERVICE_ACCOUNT_JSON` - Google service account credentials (JSON string)

### Local Development
```bash
# Ensure environment variables are set
python main.py
```
The bot will start with health monitoring on port 10000 by default.

### Auto-Update GitHub (Local → GitHub → Render)
```bash
# Automatic commit and push with generated message
python auto_update.py

# Custom commit message
python auto_update.py --message "fix: your custom message"

# Check for changes without committing
python auto_update.py --check
```

**Quick Scripts:**
- `update.bat` (Windows) - Double-click to auto-update
- `update.sh` (Unix/Linux/macOS) - Execute to auto-update

The workflow: Local changes → GitHub → Render auto-deployment

## Project Architecture

This is a Discord bot built with discord.py that implements a comprehensive role-playing and card collection system. The bot is designed for deployment on Render with health monitoring and automatic recovery capabilities.

### Core Components

**Main Bot (`main.py`)**
- CustomBot class extends discord.py Bot with health monitoring
- Automatic thread management for HTTP server, health checks, and self-ping
- Resilient connection handling with automatic reconnection
- Comprehensive error logging and thread recovery

**Health & Monitoring System**
- HTTP server (`server.py`) provides `/health`, `/ping` endpoints on port 10000
- Health monitoring (`monitoring.py`) with configurable failure thresholds
- Resource monitoring and cleanup via `utils/connection_manager.py`
- Self-ping mechanism to maintain activity on hosting platforms

**Card Collection System (`cogs/Cards.py` + `cogs/cards/` modules)**
- Modular architecture with specialized modules:
  - `config.py` - Configuration and constants
  - `models.py` - Data models and structures  
  - `storage.py` - Google Sheets integration
  - `drawing.py` - Card drawing mechanics
  - `trading.py` - Trading system
  - `forum.py` - Forum functionality
  - `discovery.py` - Discovery logging
  - `utils.py` - Utility functions
- Google Sheets integration for persistent storage
- Features: card drawing, trading, vault system, discovery logging, forum
- Async/threaded Google API operations to prevent Discord event loop blocking

### Cog Structure

The bot uses Discord.py's cog system with these main components:

- `Cards` - Card collection and trading system (refactored into modules)
- `Surveillance_scene` - RP scene monitoring and management
- `RPTracker` - Role-playing activity tracking
- `InactiveUserTracker` - User activity monitoring
- `inventaire`, `vocabulaire`, `souselement` - Various utility features
- `ticket`, `validation` - Administrative features
- `bump` - Server bumping functionality

### Google Services Integration

The bot integrates heavily with Google services:
- **Google Sheets** for data persistence (cards, user data, scenes)
- **Google Drive** for file operations
- **Service Account authentication** via `SERVICE_ACCOUNT_JSON` environment variable
- Async threading for Google API calls to prevent blocking

### Configuration

Key environment variables:
- `DISCORD_TOKEN` - Discord bot token (required)
- `SERVICE_ACCOUNT_JSON` - Google service account credentials (required)
- `PORT` - HTTP server port (defaults to 10000)
- `HEALTHCHECK_MAX_FAILURES` - Health check failure threshold (default: 10)
- `HEALTHCHECK_FORCE_RESTART` - Enable automatic restarts (default: false)

### Development Testing

The project currently lacks a formal test suite, but includes internal validation:
- Bot commands include built-in error handling and validation
- Google Sheets operations include connection testing and retry logic
- Health monitoring system provides continuous validation of bot state

### Deployment

Configured for Render deployment with:
- `render.yaml` - Service configuration
- `start.sh` - Startup script with environment validation
- Health check endpoint at `/health`
- Persistent disk mounted at `/opt/render/project/data`

## Development Notes

### Threading Architecture
The bot uses a sophisticated threading system to prevent blocking:
- HTTP server runs in dedicated daemon thread
- Health monitoring in separate daemon thread
- Google Sheets operations wrapped in `asyncio.to_thread()`
- Self-ping functionality in daemon thread

### Error Handling
- Global error handling in `CustomBot.on_error()`
- Error logging to both console and `error.log` file
- Automatic thread restart on failure detection
- Configurable restart behavior via environment variables

### Cards System Refactoring
The card system was refactored from a single 6,183-line file into a modular architecture:
- 91% reduction in main file size (530 lines)
- 15 specialized modules with clear responsibilities
- Preserved all original functionality
- Improved maintainability and testability