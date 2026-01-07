# Telegram Productivity Bot 🚀

A frictionless productivity tracker that lives in Telegram. Log activities, track goals, and build streaks without ever leaving your favorite messaging app.

## Features ✨

- **Quick Activity Logging**: Just type `exercise 30m` and it's logged
- **Goal Tracking**: Set weekly goals and track your progress
- **Streaks**: Build daily habits with streak tracking
- **Quick Buttons**: One-tap logging for your most common activities
- **Daily/Weekly Summaries**: See your progress at a glance
- **Notes**: Add context to your activities

## Setup Instructions 🛠️

### Step 1: Create Your Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` to BotFather
3. Follow the prompts:
   - Choose a name for your bot (e.g., "My Productivity Tracker")
   - Choose a username (must end in 'bot', e.g., "myproductivity_bot")
4. BotFather will give you a **token** - save this! It looks like:

   ```
   123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

### Step 2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

Or install directly:

```bash
pip install python-telegram-bot==21.0
```

### Step 3: Set Your Bot Token

**Option A: Environment Variable (Recommended)**

```bash
export TELEGRAM_BOT_TOKEN='your-token-here'
```

**Option B: Edit the Script**
Open `productivity_bot.py` and replace this line:

```python
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
```

with:

```python
TOKEN = 'your-token-here'
```

### Step 4: Run the Bot

```bash
python productivity_bot.py
```

You should see: `Bot is starting...`

### Step 5: Start Using It

1. Open Telegram and search for your bot by its username
2. Send `/start` to begin
3. Start logging activities!

## How to Use 📖

### Logging Activities

Just send a message in this format:

```
<activity> <duration> [optional notes]
```

Examples:

- `exercise 30m`
- `reading 1h`
- `meditation 15m felt really focused`
- `coding 2h working on bot project`

Supported time formats:

- `30m` or `30 minutes` for minutes
- `1h` or `1 hour` for hours

### Commands

- `/start` - Welcome message and quick start
- `/help` - Detailed help information
- `/today` - See today's logged activities
- `/week` - Week summary with totals and streaks
- `/goals` - Check your goal progress
- `/setgoal <activity> <minutes>` - Set a weekly goal
- `/streak` - View your current streaks
- `/quick` - Show quick-log buttons
- `/addbutton <activity> <minutes>` - Create a quick-log button

### Setting Goals

Set weekly goals to stay motivated:

```
/setgoal exercise 150
```

This sets a goal of 150 minutes of exercise per week.

### Quick Buttons

Create buttons for activities you log frequently:

```
/addbutton exercise 30
/addbutton reading 45
```

Then use `/quick` to get one-tap logging!

## Examples 💡

### Daily Routine

```
Morning:
meditation 10m started my day right

Afternoon:
exercise 45m gym session
reading 30m finished chapter 3

Evening:
/today
```

### Setting Up Your Workflow

```
/setgoal exercise 150
/setgoal reading 300
/addbutton exercise 30
/addbutton reading 45
/addbutton meditation 10
```

### Checking Progress

```
/goals    - See how you're tracking toward weekly goals
/streak   - Check your consecutive days
/week     - Full week summary
```

## Deployment Options 🌐

### Run Locally

Keep it running on your computer. Simple but requires your computer to be on.

### Deploy to a Server

**Option 1: Railway.app (Free tier available)**

1. Create account at railway.app
2. Create new project
3. Add PostgreSQL database (optional upgrade later)
4. Upload your code
5. Add environment variable: `TELEGRAM_BOT_TOKEN`

**Option 2: Render.com (Free tier available)**

1. Create account at render.com
2. Create new "Web Service"
3. Connect your GitHub repo (or upload code)
4. Add environment variable: `TELEGRAM_BOT_TOKEN`

**Option 3: VPS (DigitalOcean, Linode, etc.)**

```bash
# On your server
git clone your-repo
cd your-repo
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN='your-token'
nohup python productivity_bot.py &
```

### Using Screen (for VPS)

```bash
screen -S productivity-bot
python productivity_bot.py
# Press Ctrl+A then D to detach
# Use 'screen -r productivity-bot' to reattach
```

## Data Storage 💾

The bot uses SQLite to store your data in `productivity.db`. This file contains:

- All your logged activities
- Your goals
- Your quick buttons
- Activity streaks

**Backup your data:**

```bash
cp productivity.db productivity.db.backup
```

## Customization Ideas 🎨

1. **Add more activity types**: The bot works with any activity name
2. **Adjust goal periods**: Modify the code to add daily goals
3. **Add reminders**: Integrate with Telegram's notification system
4. **Charts and graphs**: Export data and visualize in a spreadsheet
5. **Multiple users**: The bot already supports multiple users out of the box

## Troubleshooting 🔧

**Bot doesn't respond:**

- Check that the bot is running (`python productivity_bot.py`)
- Verify your token is correct
- Make sure you've sent `/start` to the bot first

**"TELEGRAM_BOT_TOKEN not set" error:**

- Set the environment variable: `export TELEGRAM_BOT_TOKEN='your-token'`
- Or edit the script to hardcode your token (less secure)

**Database errors:**

- Delete `productivity.db` to start fresh (backs up your data first!)
- Check file permissions

**Bot stops when I close terminal:**

- Use `nohup python productivity_bot.py &` to run in background
- Or deploy to a cloud service

## Tips for Success 💪

1. **Log immediately**: The less friction, the better. Log right after finishing an activity
2. **Use quick buttons**: Set them up for your most common activities
3. **Check /today every evening**: Review your day and stay motivated
4. **Set realistic goals**: Start small and increase gradually
5. **Build streaks**: Even 10 minutes counts - consistency beats intensity

## Privacy & Security 🔒

- All data is stored locally in your SQLite database
- Your Telegram bot token is private - never share it
- Each user's data is separate and private
- The bot doesn't collect any data beyond what you log

## Future Enhancements Ideas 🚀

- Weekly/monthly reports
- Export to CSV
- Integration with Google Calendar
- Visualization charts
- Habit suggestions based on patterns
- Social features (share achievements)
- Custom categories and tags

## Support 💬

Having issues? Want to suggest features? The bot is yours to customize!

## License

Feel free to modify and use this bot however you like. Built with ❤️ for productivity enthusiasts.

---

**Start tracking, stay motivated, achieve your goals!** 🎯
