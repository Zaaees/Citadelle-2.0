# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important Instructions for Claude Code

**AUTOMATIC GITHUB PUSH POLICY**: After any modification to the codebase, ALWAYS automatically push changes to GitHub using `git add . && git commit && git push` unless explicitly told otherwise by the user. This ensures all changes are immediately backed up and deployed to production.

**NOTE**: All code files use UTF-8 encoding. Be careful with French characters (é, è, à, ô, etc.) and emojis in logs and messages.

## Common Commands

### Running the Bot
- `python main.py` - Start the Discord bot
- `./start.sh` - Run with startup script (includes environment checks and dependency installation)

### Development Setup
- `pip install -r requirements.txt` - Install dependencies
- The bot uses Python 3.11+ and Discord.py 2.3.0+
- Key dependencies: `gspread>=5.0.0`, `psutil>=5.8.0`, `aiohttp`, `matplotlib`

### Testing
Currently, this project does not have a formal test suite. The bot includes some internal testing commands:
- `!test_names` - Tests name extraction functionality in surveillance scenes
- Built-in validation and error handling throughout the codebase

### GitHub CLI Setup
GitHub CLI is installed and authenticated for user `Zaaees`. Use these commands for efficient GitHub management:

```bash
# Pull Request Management
gh pr list                    # List all open PRs
gh pr view [number]          # View PR details
gh pr checkout [number]      # Checkout PR locally for testing
gh pr review [number] --approve  # Approve a PR
gh pr merge [number]         # Merge a PR

# Code Review Workflow
gh pr diff [number]          # See changes in a PR
gh pr review [number] --comment --body "Your comment"
gh pr review [number] --request-changes --body "Changes needed"

# Repository Operations
gh repo view                 # View repository info
gh issue list               # List issues
gh issue create            # Create new issue
```

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
- `DISCORD_TOKEN` - Discord bot token (REQUIRED)
- `SERVICE_ACCOUNT_JSON` - Google Service Account JSON for Google Sheets integration (REQUIRED for most cogs)
- `GUILD_ID` - Discord server ID for instant slash command sync (RECOMMENDED - without this, commands take 1 hour to sync)
- `PORT` - HTTP server port (defaults to 10000)

**Google Sheets IDs** (feature-specific):
- `GOOGLE_SHEET_ID_CARDS` - Card collection system
- `GOOGLE_SHEET_ID_RP_TRACKER` - Roleplay activity tracking
- `GOOGLE_SHEET_ID_SCENE_SURVEILLANCE` - Scene monitoring
- `GOOGLE_SHEET_ID_INACTIVE` - Inactive user tracking
- Additional IDs for vocabulaire, souselement, excès cogs

**Important**: Missing Google Sheets credentials will cause related cogs to fail loading, but the bot will continue with other cogs.

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

**Critical Cogs** (must load successfully):
- `Cards.py` - Main card collection system (refactored modular architecture)
  - Uses modular structure in `cogs/cards/` directory
  - Slash commands: `/cartes`, `/collection`, `/échanger`, etc.
- `scene_surveillance.py` - Automatic RP scene monitoring system
  - Slash commands: `/surveiller_scene`, `/scenes_actives`
  - Interactive buttons for MJ scene management
  - 7-day inactivity alerts via DM

**Core Cogs** (important features):
- `RPTracker.py` - Roleplay activity tracking with Google Sheets integration
- `InactiveUserTracker.py` - User activity monitoring and automated warnings
- `bump.py` - Server bump functionality and reminders
- `validation.py` - User validation and onboarding system
- `ticket.py` - Support ticket management system
- `inventaire.py` - Player inventory management

**Optional Cogs** (can fail gracefully):
- `vocabulaire.py` - Game vocabulary/glossary management (`/vocabulaire`)
- `souselement.py` - Sub-element management (`/ajouter-sous-element`, `/sous-éléments`)
- `excès.py` - Excess/overflow management (`/excès`)

**Loading Priority**: Critical cogs are loaded first. If they fail, detailed errors are logged. Optional cogs can fail (e.g., missing Google Sheets config) without stopping the bot.

**Scene Surveillance System (`cogs/scene_surveillance.py`):**
A comprehensive RP scene monitoring system with intelligent participant detection:

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
├── __init__.py        # Package initialization
├── config.py          # Configuration and constants
├── models.py          # Data models and card classes
├── utils.py           # Shared utility functions
├── storage.py         # Google Sheets storage and caching layer
├── discovery.py       # Card discovery mechanics
├── logging.py         # Card event logging system
├── vault.py           # Trading vault and escrow system
├── drawing.py         # Card drawing/gacha mechanics
├── trading.py         # User-to-user trading logic
├── forum.py           # Card forum/marketplace management
└── views/             # Discord UI components (Buttons, Modals, Selects)
    ├── __init__.py
    ├── menu_views.py  # Main menu interfaces
    ├── trade_views.py # Trading interfaces
    ├── gallery_views.py # Card gallery displays
    └── modal_views.py # Modal dialogs (text input)
```

**Key Design Patterns:**
- **Separation of Concerns**: Each module handles a specific domain (storage, trading, UI)
- **Caching Layer**: `storage.py` implements intelligent caching to reduce Google Sheets API calls
- **Async Operations**: All Google Sheets operations wrapped in `asyncio.to_thread()` to prevent blocking
- **View Persistence**: Discord views use `timeout=None` and custom_ids for persistence across bot restarts

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
- Designed for Render.com deployment with health checks (`render.yaml`)
- Uses persistent disk storage for data directory (1GB mounted at `/opt/render/project/data`)
- Includes startup scripts (`start.sh`) with environment validation
- Auto-deployment enabled on GitHub pushes
- Health check endpoints: `/ping` (simple), `/health` (detailed JSON)
- Port configuration via `PORT` environment variable (default: 10000)

## Complete File Structure

```
Citadelle-2.0/
├── main.py                    # Main bot entry point (StableBot class)
├── server_minimal.py          # HTTP health check server
├── monitoring_minimal.py      # Bot health monitoring
├── auto_update.py            # Git automation tool
├── start.sh                  # Startup script for deployment
├── update.sh / update.bat    # Quick update scripts
├── requirements.txt          # Python dependencies
├── render.yaml              # Render.com deployment config
├── bot.log                  # Main bot logs
├── auto_update.log          # Auto-update logs
│
├── cogs/                    # Bot functionality modules
│   ├── Cards.py             # Main cards cog (loads cards package)
│   ├── scene_surveillance.py # RP scene monitoring
│   ├── RPTracker.py         # RP activity tracking
│   ├── InactiveUserTracker.py # User activity monitoring
│   ├── bump.py              # Server bump system
│   ├── validation.py        # User validation
│   ├── ticket.py            # Support tickets
│   ├── inventaire.py        # Inventory system
│   ├── vocabulaire.py       # Vocabulary management
│   ├── souselement.py       # Sub-element management
│   ├── excès.py             # Excess management
│   │
│   └── cards/               # Modular cards system
│       ├── __init__.py
│       ├── config.py
│       ├── models.py
│       ├── utils.py
│       ├── storage.py
│       ├── discovery.py
│       ├── logging.py
│       ├── vault.py
│       ├── drawing.py
│       ├── trading.py
│       ├── forum.py
│       └── views/
│           ├── menu_views.py
│           ├── trade_views.py
│           ├── gallery_views.py
│           └── modal_views.py
│
├── utils/                   # Shared utilities
│   ├── health_monitor.py    # Health monitoring
│   └── connection_manager.py # Connection management
│
├── .claude/                 # Claude Code configuration
├── logs/                    # Log directory (created at runtime)
└── data/                    # Data directory (Render persistent disk)
```

## Common Patterns & Conventions

### Error Handling
- **Try-catch with logging**: All async operations wrapped in try-except with detailed logging
- **Graceful degradation**: Optional cogs can fail without crashing the bot
- **User-friendly errors**: Discord users see friendly error messages, detailed errors go to logs

Example pattern:
```python
try:
    # Risky operation
    result = await some_operation()
except Exception as e:
    logger.error(f"❌ Operation failed: {e}")
    logger.error(traceback.format_exc())
    await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
```

### Google Sheets Integration Pattern
All cogs using Google Sheets follow this pattern:

```python
# 1. Authenticate with service account
creds = service_account.Credentials.from_service_account_info(
    json.loads(os.getenv('SERVICE_ACCOUNT_JSON'))
)

# 2. Async wrapper to prevent blocking
sheet = await asyncio.to_thread(
    lambda: gspread.authorize(creds).open_by_key(sheet_id)
)

# 3. Error handling for missing credentials
try:
    worksheet = await asyncio.to_thread(sheet.worksheet, "SheetName")
except gspread.exceptions.WorksheetNotFound:
    logger.error("❌ Worksheet not found")
```

### Discord Slash Commands
- Use `@app_commands.command()` decorator for slash commands
- All interactions should be deferred for operations >3 seconds
- Use `ephemeral=True` for private responses
- Follow naming convention: French names for user-facing commands

### Logging Conventions
- Emojis for visual scanning: ✅ success, ❌ error, ⚠️ warning, 🔍 debug, 📊 stats
- Log levels: INFO for normal operations, ERROR for failures, WARNING for degraded state
- Include context: user IDs, channel IDs, operation names in logs

### View Persistence
For buttons/selects that should persist across bot restarts:
- Set `timeout=None` in View constructor
- Use unique `custom_id` for each button/select
- Register persistent views in cog setup

## Troubleshooting Guide

### Common Issues

**1. Slash commands not appearing**
- Check `GUILD_ID` is set in environment variables
- Wait 1 hour for global sync OR restart with correct `GUILD_ID` for instant sync
- Verify bot has `applications.commands` scope
- Check logs for sync errors: `grep "sync" bot.log`

**2. Cogs failing to load**
- Missing `SERVICE_ACCOUNT_JSON`: Expected for Google Sheets cogs
- Check logs for specific error: `grep "Extension.*chargée\|Erreur" bot.log`
- Verify Google Sheets IDs are correct in environment variables

**3. Bot disconnecting frequently**
- Check Render.com logs for memory/CPU issues
- Verify health check endpoint responding: `curl https://your-app.onrender.com/ping`
- Review connection errors: `grep "disconnect\|Erreur" bot.log`

**4. Google Sheets API errors**
- Rate limit: Implement caching (see `cards/storage.py` for example)
- Authentication: Verify service account JSON is valid
- Permissions: Ensure service account has Editor access to sheets

**5. Unicode/Encoding errors**
- All files should be UTF-8 encoded
- Use `encoding='utf-8'` when opening files
- Log handlers should specify UTF-8 encoding

### Debug Commands
```bash
# Check bot status
tail -f bot.log

# Check recent errors
grep "ERROR\|CRITICAL" bot.log | tail -20

# Check cog loading
grep "Extension" bot.log | tail -20

# Check slash command sync
grep "commandes synchronisées" bot.log

# Monitor auto-updates
tail -f auto_update.log
```

## Development Workflow

### Making Changes
1. Make code changes locally
2. Test locally if possible (`python main.py`)
3. Use auto-update script: `python auto_update.py` OR `./update.sh`
4. Monitor Render deployment logs
5. Check `/ping` endpoint for health status

### Adding New Cogs
1. Create cog file in `cogs/` directory
2. Inherit from `commands.Cog`
3. Implement `setup()` function at bottom
4. Add to extensions list in `main.py` (lines 41-54)
5. Test loading locally before deploying

### Modifying Slash Commands
1. Make changes to command code
2. Test locally (commands sync on startup)
3. Deploy to Render (auto-deploys on push)
4. Commands update instantly with `GUILD_ID` set, 1 hour globally

### Working with Google Sheets
1. Keep operations async: wrap in `asyncio.to_thread()`
2. Implement caching for frequently-read data
3. Batch write operations when possible
4. Handle `WorksheetNotFound` and `APIError` exceptions

## Best Practices

### Performance
- **Caching**: Cache Google Sheets data to minimize API calls (60-second TTL recommended)
- **Async operations**: Never block the event loop - use `asyncio.to_thread()` for I/O
- **Lazy loading**: Load resources only when needed
- **Batch operations**: Combine multiple sheet updates into single API call

### Security
- **Never commit secrets**: Use environment variables for all sensitive data
- **Service account permissions**: Grant minimum necessary permissions to Google Sheets
- **Input validation**: Validate all user input before processing
- **Rate limiting**: Respect Discord and Google API rate limits

### Code Quality
- **Type hints**: Use type hints for function parameters and returns
- **Docstrings**: Document complex functions and classes
- **Error messages**: Provide clear, actionable error messages
- **Logging**: Log all important operations and errors with context

### Discord Best Practices
- **Ephemeral responses**: Use for errors, confirmations, and private data
- **Defer interactions**: Defer if operation takes >3 seconds
- **Embed limits**: Max 25 fields, 6000 total characters, 4096 per field
- **Button limits**: Max 25 buttons per message (5 rows × 5 buttons)

## Additional Resources

### Related Documentation
- `SCENE_SURVEILLANCE_README.md` - Detailed scene surveillance system docs
- `AUTO_UPDATE_README.md` - Auto-update script documentation
- `AMELIORATIONS_SYSTEME.md` - System improvements log
- `SOLUTION_DECONNEXIONS.md` - Disconnection troubleshooting guide

### Important Files to Check Before Modifying
- `main.py` lines 41-54: Cog loading order (critical for dependencies)
- `main.py` lines 96-127: Slash command sync logic
- `server_minimal.py`: Health check implementation
- `render.yaml`: Deployment configuration

### External Dependencies
- Discord.py docs: https://discordpy.readthedocs.io/
- Google Sheets API: https://developers.google.com/sheets/api
- Render.com docs: https://render.com/docs
- gspread library: https://docs.gspread.org/

## Quick Reference

### Most Common Tasks

**1. Add a new slash command to existing cog:**
```python
@app_commands.command(name="command_name", description="Description")
async def command_name(self, interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    # Your code here
    await interaction.followup.send("✅ Done!", ephemeral=True)
```

**2. Access Google Sheets data:**
```python
sheet = await asyncio.to_thread(
    lambda: self.client.open_by_key(os.getenv('GOOGLE_SHEET_ID'))
)
worksheet = await asyncio.to_thread(sheet.worksheet, "SheetName")
data = await asyncio.to_thread(worksheet.get_all_records)
```

**3. Create persistent button:**
```python
class MyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Click", custom_id="unique_id", style=discord.ButtonStyle.primary)
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Clicked!", ephemeral=True)
```

**4. Schedule periodic task:**
```python
from discord.ext import tasks

@tasks.loop(hours=24)
async def daily_task(self):
    # Your code here
    pass

@daily_task.before_loop
async def before_daily_task(self):
    await self.bot.wait_until_ready()
```

### Key File Locations
- Main bot class: `main.py:29-178` (StableBot)
- Cog loading: `main.py:38-93` (setup_hook)
- Health server: `server_minimal.py:56-90`
- Auto-update logic: `auto_update.py:134-178`

---

**Last Updated**: 2025-11-22
**Bot Version**: Citadelle 2.0
**Python Version**: 3.11+
**Discord.py Version**: 2.3.0+