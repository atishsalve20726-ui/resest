# Render Deployment Guide

## Quick Deployment Steps

### 1. Prepare Your Repository
- Push this project to a Git repository (GitHub, GitLab, or Bitbucket)
- Make sure all files are committed except those in `.gitignore`

### 2. Create a New Web Service on Render

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"Web Service"**
3. Connect your Git repository
4. Select this repository

### 3. Configure the Service

Use these settings:

- **Name**: `instagram-password-reset-bot` (or your preferred name)
- **Region**: Choose closest to your users
- **Branch**: `main` (or your default branch)
- **Runtime**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python telegram_bot.py`

### 4. Add Environment Variables

Click on **"Environment"** and add these variables:

**Required:**
- `TELEGRAM_BOT_TOKEN` = Your bot token from @BotFather

**Optional (for Force Join feature):**
- `FORCE_CHANNEL_ID` = Your channel ID (e.g., `-1002346252889`)
- `FORCE_GROUP_ID` = Your group ID (e.g., `-1002987857677`)
- `FORCE_CHANNEL_INVITE_LINK` = Channel invite link (for private channels)
- `FORCE_GROUP_INVITE_LINK` = Group invite link (for private groups)

### 5. Deploy

1. Click **"Create Web Service"**
2. Wait for the deployment to complete (usually 2-5 minutes)
3. Your bot will automatically start running!

## Important Notes

### Free Tier Limitations
- Render's free tier spins down after 15 minutes of inactivity
- The bot will wake up when it receives a request (may take 30-60 seconds)
- Consider upgrading to a paid plan for 24/7 uptime

### Data Persistence
- `bot_data.json` and `users.json` will be created automatically
- **Warning**: On Render's free tier, data may be lost when the service restarts
- For persistent data storage, consider using:
  - Render Disks (paid feature)
  - External database (PostgreSQL, MongoDB, etc.)
  - Redis for session storage

### Monitoring
- Check logs in the Render dashboard under **"Logs"** tab
- Look for `🚀 High-Performance Bot is running...` message to confirm successful start

### Updating Your Bot
- Push changes to your Git repository
- Render will automatically detect changes and redeploy
- Or manually trigger a deploy from the Render dashboard

## Troubleshooting

### Bot doesn't start
- Check the logs for error messages
- Verify `TELEGRAM_BOT_TOKEN` is set correctly
- Ensure `requirements.txt` has all dependencies

### Bot goes offline frequently
- This is normal on free tier (15-minute inactivity timeout)
- Upgrade to paid tier for continuous operation
- Or set up a cron job to ping your service every 10 minutes

### Environment variables not working
- Double-check variable names (case-sensitive)
- Restart the service after adding/changing variables
- Verify no extra spaces in variable values

## Support

For issues or questions:
1. Check the logs first
2. Verify all environment variables are set correctly
3. Ensure your repository is up to date
4. Review the main README.md for bot configuration details

## Alternative: Using Docker (Optional)

If you prefer Docker deployment on Render:

1. Create a `Dockerfile` in your repository:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "telegram_bot.py"]
```

2. In Render settings, change:
   - **Runtime**: `Docker`
   - **Build Command**: (leave empty)
   - **Start Command**: (leave empty - uses Dockerfile CMD)
