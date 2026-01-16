# Valorant Discord Bot

Discord bot for tracking Valorant ranks and monitoring Riot Games authentication codes.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure the bot:
   - Create `config.json` based on the example structure
   - Fill in your Discord bot token, API keys, channel IDs, and user accounts
   - Update email credentials for code monitoring

3. Run the bot:
```bash
python ds.py
```

## Configuration

Edit `config.json` with your settings:

- **discord_token**: Your Discord bot token
- **admin_user_id**: Discord ID of the admin user
- **channels**: Channel IDs for main, leaderboard, errors, and codes
- **guilds**: Guild ID for authentication
- **api**: Henrik API keys for Valorant data
- **email**: Gmail credentials for monitoring Riot codes
- **users**: List of Valorant accounts to track

## Features

- Real-time rank tracking with automatic updates
- Leaderboard system with visual cards
- Riot Games authentication code monitoring via email
- Ban tracking system
- Automatic watchdog for system health
- Slash commands for manual control

## Commands

- `/forceupdate` - Force rank update
- `/status` - Show bot status
- `/fastcodice` - Check for new Riot codes
- `/forcewatchdog` - Run watchdog checks
- `/restart` - Restart background tasks
- `/sync` - Sync slash commands

## Notes

- The bot requires specific Discord permissions to function
- Keep your API keys and credentials secure

