# Instagram Password Reset Telegram Bot

A Telegram bot that helps send password reset links to Instagram accounts using multiple methods.

## Features

- 🔄 **Multiple Reset Methods**: Uses 3 different Instagram password reset endpoints
- 🤖 **Easy to Use**: Simple Telegram interface - just send a username or email
- 📊 **Detailed Results**: Shows results from all attempted methods
- ⚡ **Fast Processing**: Attempts all methods simultaneously
- 🔒 **Force Join**: Optional feature to require users to join your channel/group before using the bot

## Prerequisites

- Python 3.7 or higher
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

## Installation

1. **Clone or download this repository**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Get your Telegram Bot Token**:
   - Open Telegram and search for [@BotFather](https://t.me/BotFather)
   - Send `/newbot` and follow the instructions
   - Copy the bot token you receive

4. **Configure the bot**:
   - Copy `.env.example` to `.env`:
     ```bash
     copy .env.example .env
     ```
   - Open `.env` and replace `your_bot_token_here` with your actual bot token:
     ```
     TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
     ```

## Force Join Configuration (Optional)

To require users to join your channel/group before using the bot:

1. **Get your channel/group ID**:
   - Add [@userinfobot](https://t.me/userinfobot) to your channel/group
   - Forward a message from the channel/group to the bot
   - Copy the chat ID (e.g., `-1002346252889`)

2. **Get invite links for private channels/groups**:
   - Open your channel/group settings
   - Go to "Invite Links" → "Create a new link"
   - Copy the invite link (e.g., `https://t.me/+AbCdEfGhIjK`)

3. **Update your `.env` file**:
   ```env
   # For private channels/groups (numeric IDs)
   FORCE_CHANNEL_ID=-1002346252889
   FORCE_GROUP_ID=-1002987857677
   
   # Add the invite links (REQUIRED for private groups if bot is not admin)
   FORCE_CHANNEL_INVITE_LINK=https://t.me/+your_channel_invite_link
   FORCE_GROUP_INVITE_LINK=https://t.me/+your_group_invite_link
   ```
   
   OR for public channels/groups:
   ```env
   # For public channels/groups (usernames)
   FORCE_CHANNEL_ID=@your_channel_username
   FORCE_GROUP_ID=@your_group_username
   # No invite links needed for public channels
   ```

4. **Important Notes**:
   - ✅ Users who are **pending approval** in private groups can still use the bot
   - ✅ If bot is not added to the group, it will allow all users (fail-safe mode)
   - ⚠️ For best results with private groups, add the bot as admin with "Invite users" permission

## Usage

1. **Start the bot**:
   ```bash
   python telegram_bot.py
   ```

2. **Open your bot in Telegram** and send `/start`

3. **Send any Instagram username or email** to trigger the password reset process

### Example

```
username123
```
or
```
user@email.com
```

The bot will attempt to send password reset links using 3 different methods and report the results.

## Commands

- `/start` - Start the bot and see welcome message
- `/help` - Show help information

## How It Works

The bot uses three different Instagram password reset methods:

1. **Method 1**: Basic account recovery endpoint
2. **Method 2**: API-based reset using Instagram's web profile API
3. **Method 3**: Web-based account recovery with enhanced headers

Each method attempts to send a password reset link to the provided username or email.

## Important Notes

⚠️ **Rate Limiting**: Instagram may rate-limit requests from your IP. If you encounter rate limits, consider using a VPN.

⚠️ **Legal Use**: This tool uses Instagram's official password reset endpoints. Only use it for legitimate account recovery purposes.

⚠️ **Success Rate**: Not all methods work for all accounts. The bot tries multiple methods to increase success rate.

## Troubleshooting

### "IP LIMITED" Error
- Instagram has rate-limited your IP address
- Solution: Use a VPN or wait before trying again

### Bot doesn't respond
- Check if the bot token is correct
- Ensure the bot is running (`python telegram_bot.py`)
- Check your internet connection

### "Failed to parse response"
- Instagram's API may have changed
- Check if you're being rate-limited

## Original Script

The original command-line script is available as `RESET.py` in this repository.

## License

This project is for educational purposes only. Use responsibly and in accordance with Instagram's Terms of Service.

## Disclaimer

This tool is provided as-is without any warranties. The authors are not responsible for any misuse or damage caused by this tool. Always ensure you have permission to access the accounts you're trying to recover.
