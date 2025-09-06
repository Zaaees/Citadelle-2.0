# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important Instructions for Claude Code

**AUTOMATIC GITHUB PUSH POLICY**: After any modification to the codebase, ALWAYS automatically push changes to GitHub using `git add . && git commit && git push` unless explicitly told otherwise by the user. This ensures all changes are immediately backed up and deployed to production.

## Common Commands

### Running the Bot
- `python main.py` - Start the Discord bot
- `./start.sh` - Run with startup script (includes environment checks and dependency installation)

### Development Setup
- `pip install -r requirements.txt` - Install dependencies
- The bot uses Python 3.11+ and Discord.py 2.3.0+

### Testing
Currently, this project does not have a formal test suite. The bot includes some internal testing commands:
- `!test_names` - Tests name extraction functionality in surveillance scenes
- Built-in validation and error handling throughout the codebase

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
- `update_github.bat` (Windows) - Double-click to auto-update
- `update.sh` (Unix/Linux/macOS) - Execute to auto-update

The workflow: Local changes → GitHub → Render auto-deployment

### Environment Variables Required
- `DISCORD_TOKEN` - Discord bot token
- `SERVICE_ACCOUNT_JSON` - Google Service Account JSON for Google Sheets integration
- `GOOGLE_SHEET_ID_*` - Various Google Sheet IDs for different features
- `PORT` - HTTP server port (defaults to 10000)

## High-Level Architecture

### Bot Structure
This is a Discord.py bot (`Citadelle-2.0`) with a modular cog-based architecture. The main entry point is `main.py` which implements:

- Custom bot class with health monitoring and HTTP server for deployment
- Automatic cog loading from the `cogs/` directory
- Robust error handling and reconnection logic
- Health monitoring system with metrics collection

### Core Components

#### Main Bot (`main.py`)
- `CustomBot`/`StableBot` class extends `commands.Bot` with health monitoring
- Built-in HTTP server for health checks (`/health`, `/ping`)
- Background threads for monitoring and self-pinging
- Automatic cog loading and command synchronization

#### Cogs Structure
Located in `cogs/` directory:

**Core Cogs:**
- `Cards.py` - Main card collection system (refactored modular architecture)
- `scene_surveillance.py` - **NEW** Automatic RP scene monitoring system
- `RPTracker.py` - Roleplay activity tracking with Google Sheets integration
- `InactiveUserTracker.py` - User activity monitoring
- `bump.py` - Server bump functionality
- `validation.py` - User validation system
- `ticket.py` - Ticket management system
- `inventaire.py` - Inventory management
- Other utility cogs: `vocabulaire.py`, `souselement.py`, `excès.py`

**Scene Surveillance System (`cogs/scene_surveillance.py`):**
The newest addition to the bot - a comprehensive RP scene monitoring system:

```
SceneSurveillance Features:
├── /surveiller_scene - Start scene monitoring
├── /scenes_actives - List active scenes
├── Interactive buttons (take over/close scene)
├── Smart participant detection (webhooks, bots)
├── Private MJ notifications
├── 7-day inactivity alerts
├── Real-time status updates
└── Google Sheets persistence
```

**Cards System Architecture:**
The cards system has been refactored from a monolithic 6183-line file into a modular architecture:

```
cogs/cards/
├── config.py          # Configuration and constants
├── models.py          # Data models and classes  
├── utils.py           # Shared utilities
├── storage.py         # Google Sheets storage and caching
├── discovery.py       # Card discovery and logging
├── vault.py           # Trading vault system
├── drawing.py         # Card drawing mechanics
├── trading.py         # User trading logic
├── forum.py           # Card forum management
└── views/             # Discord UI components
    ├── menu_views.py  # Main menu interfaces
    ├── trade_views.py # Trading interfaces
    ├── gallery_views.py # Card galleries
    └── modal_views.py # Modal dialogs
```

#### Utilities (`utils/`)
- `health_monitor.py` - Advanced bot health monitoring with metrics
- `connection_manager.py` - Resource management and cleanup

### Key Integrations
- **Google Sheets API** - Extensive use for data persistence across multiple cogs
- **Discord.py** - Modern Discord bot framework with app commands
- **Render.com** - Deployment platform (see `render.yaml`)

### Data Persistence
- Primary storage via Google Sheets API with service account authentication
- Local caching for performance optimization
- File-based logging for debugging and monitoring

### Health & Monitoring System
- HTTP server (`server.py`) provides `/health`, `/ping` endpoints on port 10000
- Health monitoring with configurable failure thresholds
- Resource monitoring and cleanup via `utils/connection_manager.py`
- Self-ping mechanism to maintain activity on hosting platforms

## Development Notes

### Code Organization
- Each cog should be self-contained with clear responsibilities
- Use the modular cards system as an example for complex features
- Maintain Google Sheets integration patterns across cogs
- Follow the established error handling and logging patterns

### Threading Architecture
The bot uses a sophisticated threading system to prevent blocking:
- HTTP server runs in dedicated daemon thread
- Health monitoring in separate daemon thread
- Google Sheets operations wrapped in `asyncio.to_thread()`
- Self-ping functionality in daemon thread

### Authentication
- Google service accounts for Sheets API access
- Discord bot token for Discord API
- Environment variables for all sensitive configuration

### Deployment
- Designed for Render.com deployment with health checks
- Uses persistent disk storage for data directory
- Includes startup scripts and environment validation