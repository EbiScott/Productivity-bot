import os
import re
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Store user sheet URLs and connections
user_sheets: Dict[int, gspread.Spreadsheet] = {}
user_sheet_urls: Dict[int, str] = {}


class SimpleMultiUserDB:
    """Simple Google Sheets handler - each user has their own sheet"""
    
    def __init__(self, spreadsheet_url: str, client: gspread.Client):
        """Initialize connection to user's spreadsheet"""
        self.spreadsheet = client.open_by_url(spreadsheet_url)
        self._init_sheets()
    
    def _init_sheets(self):
        """Initialize required sheets with headers"""
        # Activities sheet
        try:
            self.activities_sheet = self.spreadsheet.worksheet('Activities')
        except:
            self.activities_sheet = self.spreadsheet.add_worksheet(
                title='Activities', 
                rows=1000, 
                cols=5
            )
            self.activities_sheet.append_row([
                'Activity Name', 'Duration (min)', 'Timestamp', 'Notes', 'Date'
            ])
            # Format header
            self.activities_sheet.format('A1:E1', {"textFormat": {"bold": True}})
        
        # Goals sheet
        try:
            self.goals_sheet = self.spreadsheet.worksheet('Goals')
        except:
            self.goals_sheet = self.spreadsheet.add_worksheet(
                title='Goals',
                rows=100,
                cols=4
            )
            self.goals_sheet.append_row([
                'Activity Name', 'Target (min)', 'Period', 'Active'
            ])
            self.goals_sheet.format('A1:D1', {"textFormat": {"bold": True}})
        
        # Quick Buttons sheet
        try:
            self.buttons_sheet = self.spreadsheet.worksheet('Quick Buttons')
        except:
            self.buttons_sheet = self.spreadsheet.add_worksheet(
                title='Quick Buttons',
                rows=100,
                cols=2
            )
            self.buttons_sheet.append_row([
                'Activity Name', 'Duration (min)'
            ])
            self.buttons_sheet.format('A1:B1', {"textFormat": {"bold": True}})
    
    # ... (rest of the methods are the same as before)
    
    def log_activity(self, activity_name: str, duration_minutes: int, notes: str = None) -> bool:
        try:
            timestamp = datetime.now()
            self.activities_sheet.append_row([
                activity_name,
                duration_minutes,
                timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                notes or '',
                timestamp.strftime('%Y-%m-%d')
            ])
            return True
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
            return False
    
    def get_today_activities(self) -> List[Tuple]:
        try:
            all_records = self.activities_sheet.get_all_records()
            today = datetime.now().date().strftime('%Y-%m-%d')
            
            results = []
            for record in all_records:
                if record.get('Date') == today:
                    results.append((
                        record['Activity Name'],
                        record['Duration (min)'],
                        record['Timestamp'],
                        record.get('Notes', '')
                    ))
            return results
        except Exception as e:
            logger.error(f"Error: {e}")
            return []
    
    def get_week_summary(self) -> List[Tuple]:
        try:
            all_records = self.activities_sheet.get_all_records()
            week_ago = (datetime.now() - timedelta(days=7)).date().strftime('%Y-%m-%d')
            
            activity_totals = {}
            activity_counts = {}
            
            for record in all_records:
                if record.get('Date', '') >= week_ago:
                    activity_name = record['Activity Name']
                    duration = record['Duration (min)']
                    
                    if activity_name not in activity_totals:
                        activity_totals[activity_name] = 0
                        activity_counts[activity_name] = 0
                    
                    activity_totals[activity_name] += duration
                    activity_counts[activity_name] += 1
            
            return [(name, activity_totals[name], activity_counts[name]) 
                    for name in sorted(activity_totals.keys())]
        except Exception as e:
            logger.error(f"Error: {e}")
            return []
    
    def get_streak(self, activity_name: str) -> int:
        try:
            all_records = self.activities_sheet.get_all_records()
            dates = set(record['Date'] for record in all_records 
                       if record['Activity Name'] == activity_name and record.get('Date'))
            
            if not dates:
                return 0
            
            sorted_dates = sorted(dates, reverse=True)
            today = datetime.now().date().strftime('%Y-%m-%d')
            
            if sorted_dates[0] < (datetime.now().date() - timedelta(days=1)).strftime('%Y-%m-%d'):
                return 0
            
            streak = 1
            current_date = datetime.strptime(sorted_dates[0], '%Y-%m-%d').date()
            
            for i in range(1, len(sorted_dates)):
                date = datetime.strptime(sorted_dates[i], '%Y-%m-%d').date()
                if current_date - date == timedelta(days=1):
                    streak += 1
                    current_date = date
                else:
                    break
            
            return streak
        except:
            return 0
    
    def set_goal(self, activity_name: str, target_minutes: int, period: str = 'week') -> bool:
        try:
            all_records = self.goals_sheet.get_all_records()
            for i, record in enumerate(all_records, start=2):
                if record['Activity Name'] == activity_name and record['Period'] == period:
                    self.goals_sheet.update_cell(i, 4, 'FALSE')
            
            self.goals_sheet.append_row([activity_name, target_minutes, period, 'TRUE'])
            return True
        except Exception as e:
            logger.error(f"Error: {e}")
            return False
    
    def get_active_goals(self) -> List[Tuple]:
        try:
            all_goals = self.goals_sheet.get_all_records()
            all_activities = self.activities_sheet.get_all_records()
            results = []
            
            for goal in all_goals:
                if goal['Active'] == 'TRUE':
                    activity_name = goal['Activity Name']
                    target_minutes = goal['Target (min)']
                    period = goal['Period']
                    
                    start_date = (datetime.now() - timedelta(days=7 if period == 'week' else 0)).date().strftime('%Y-%m-%d')
                    
                    current = sum(activity['Duration (min)'] for activity in all_activities
                                 if activity['Activity Name'] == activity_name and 
                                 activity.get('Date', '') >= start_date)
                    
                    results.append((activity_name, target_minutes, current, period))
            
            return results
        except Exception as e:
            logger.error(f"Error: {e}")
            return []
    
    def add_quick_button(self, activity_name: str, duration_minutes: int) -> bool:
        try:
            all_buttons = self.buttons_sheet.get_all_records()
            for button in all_buttons:
                if (button['Activity Name'] == activity_name and 
                    button['Duration (min)'] == duration_minutes):
                    return False
            
            self.buttons_sheet.append_row([activity_name, duration_minutes])
            return True
        except Exception as e:
            logger.error(f"Error: {e}")
            return False
    
    def get_quick_buttons(self) -> List[Tuple]:
        try:
            all_buttons = self.buttons_sheet.get_all_records()
            return sorted([(b['Activity Name'], b['Duration (min)']) for b in all_buttons])
        except:
            return []


def get_sheets_client():
    """Get Google Sheets client using service account"""
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    creds_dict = eval(os.getenv('GOOGLE_CREDENTIALS'))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)


def get_user_db(user_id: int) -> Optional[SimpleMultiUserDB]:
    """Get database connection for user"""
    if user_id not in user_sheets:
        return None
    return user_sheets[user_id]


def parse_activity(text: str) -> Optional[Tuple[str, int, str]]:
    """Parse activity from text"""
    pattern = r'^(\w+(?:\s+\w+)?)\s+(\d+)\s*(m|min|minutes?|h|hours?)\s*(.*)?$'
    match = re.match(pattern, text.strip(), re.IGNORECASE)
    
    if not match:
        return None
    
    activity_name = match.group(1).lower()
    duration = int(match.group(2))
    unit = match.group(3).lower()
    notes = match.group(4).strip() if match.group(4) else None
    
    if unit.startswith('h'):
        duration *= 60
    
    return activity_name, duration, notes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    user = update.effective_user
    user_id = user.id
    
    if user_id in user_sheets:
        await update.message.reply_text(
            f"👋 Welcome back, {user.first_name}!\n\n"
            f"Your Google Sheet is connected! ✅\n\n"
            f"📝 Log: `exercise 30m`\n"
            f"📊 Today: /today\n"
            f"🎯 Goals: /goals\n"
            f"📄 Sheet: /sheet"
        )
    else:
        await update.message.reply_text(
            f"👋 Hey {user.first_name}! Welcome to Productivity Bot!\n\n"
            f"**Setup Instructions:**\n\n"
            f"1. Create a new Google Sheet at sheets.google.com\n"
            f"2. Share it with this email (Editor access):\n"
            f"   `{get_service_account_email()}`\n"
            f"3. Copy the sheet URL\n"
            f"4. Send me: `/connect <sheet-url>`\n\n"
            f"Example:\n"
            f"`/connect https://docs.google.com/spreadsheets/d/abc123...`\n\n"
            f"✅ Your data stays in YOUR Google account!\n"
            f"✅ Only you can see it (unless you share it)\n"
            f"✅ You can view/edit it anytime"
        )


async def connect_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Connect user's Google Sheet"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "Please provide your Google Sheet URL:\n\n"
            "Usage: `/connect <sheet-url>`\n\n"
            "Example:\n"
            "`/connect https://docs.google.com/spreadsheets/d/abc123...`"
        )
        return
    
    sheet_url = context.args[0]
    
    # Validate URL
    if 'docs.google.com/spreadsheets' not in sheet_url:
        await update.message.reply_text(
            "❌ That doesn't look like a Google Sheets URL!\n\n"
            "It should look like:\n"
            "`https://docs.google.com/spreadsheets/d/...`"
        )
        return
    
    await update.message.reply_text("⏳ Connecting to your sheet...")
    
    try:
        client = get_sheets_client()
        db = SimpleMultiUserDB(sheet_url, client)
        
        # Store connection
        user_sheets[user_id] = db
        user_sheet_urls[user_id] = sheet_url
        
        await update.message.reply_text(
            "✅ **Connected successfully!**\n\n"
            "Your productivity tracker is ready!\n\n"
            "Try logging an activity:\n"
            "`exercise 30m`\n\n"
            "Commands: /help"
        )
    except Exception as e:
        logger.error(f"Connection error: {e}")
        await update.message.reply_text(
            "❌ **Connection failed!**\n\n"
            "Please make sure:\n"
            "1. The sheet exists\n"
            "2. You shared it with:\n"
            f"   `{get_service_account_email()}`\n"
            "3. You gave 'Editor' access\n"
            "4. The URL is correct\n\n"
            "Try again with: `/connect <url>`"
        )


def get_service_account_email() -> str:
    """Get service account email from credentials"""
    try:
        creds_dict = eval(os.getenv('GOOGLE_CREDENTIALS'))
        return creds_dict.get('client_email', 'ERROR: Email not found')
    except:
        return 'ERROR: Configure GOOGLE_CREDENTIALS'


async def sheet_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send link to user's spreadsheet"""
    user_id = update.effective_user.id
    
    if user_id not in user_sheet_urls:
        await update.message.reply_text("⚠️ No sheet connected! Send /start for instructions.")
        return
    
    await update.message.reply_text(
        f"📊 **Your Productivity Spreadsheet:**\n\n"
        f"{user_sheet_urls[user_id]}\n\n"
        f"You can view and edit it anytime!"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message"""
    user_id = update.effective_user.id
    
    if user_id not in user_sheets:
        await update.message.reply_text(
            "⚠️ No sheet connected yet!\n\n"
            "Send /start for setup instructions."
        )
        return
    
    await update.message.reply_text(
        "📚 **How to use:**\n\n"
        "**Log activities:**\n"
        "• `exercise 30m`\n"
        "• `reading 1h great book`\n\n"
        "**Commands:**\n"
        "/today - Today's activities\n"
        "/week - Week summary\n"
        "/goals - Goal progress\n"
        "/setgoal <activity> <min> [period] - Set goal\n"
        "  Examples:\n"
        "  • `/setgoal exercise 150` (weekly)\n"
        "  • `/setgoal meditation 15 daily`\n"
        "/streak - View streaks\n"
        "/sheet - Get sheet link\n\n"
        "✅ All data in YOUR Google Sheet!"
    )


async def today_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's activities"""
    user_id = update.effective_user.id
    db = get_user_db(user_id)
    
    if not db:
        await update.message.reply_text("⚠️ No sheet connected! Send /start")
        return
    
    activities = db.get_today_activities()
    
    if not activities:
        await update.message.reply_text("No activities today yet! 💪")
        return
    
    activity_totals = {}
    for activity_name, duration, _, _ in activities:
        activity_totals[activity_name] = activity_totals.get(activity_name, 0) + duration
    
    msg = "📊 **Today's Activities:**\n\n"
    total = 0
    
    for activity, duration in sorted(activity_totals.items()):
        h, m = duration // 60, duration % 60
        time_str = f"{h}h {m}m" if h > 0 else f"{m}m"
        msg += f"• {activity.title()}: {time_str}\n"
        total += duration
    
    h, m = total // 60, total % 60
    msg += f"\n**Total: {h}h {m}m" if h > 0 else f"\n**Total: {m}m"
    msg += "**"
    
    # Check for daily and weekly goals
    goals = db.get_active_goals()
    if goals:
        msg += "\n\n🎯 **Goal Progress:**\n"
        for activity_name, target, current, period in goals:
            if activity_name in activity_totals:
                percentage = (current / target * 100) if target > 0 else 0
                period_text = "day" if period == 'day' else "week"
                msg += f"• {activity_name.title()}: {current}/{target}m ({percentage:.0f}%) - {period_text}ly\n"
    
    await update.message.reply_text(msg)


async def week_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show week summary"""
    user_id = update.effective_user.id
    db = get_user_db(user_id)
    
    if not db:
        await update.message.reply_text("⚠️ No sheet connected! Send /start")
        return
    
    activities = db.get_week_summary()
    
    if not activities:
        await update.message.reply_text("No activities this week!")
        return
    
    msg = "📈 **This Week:**\n\n"
    
    for activity_name, total_minutes, count in activities:
        h, m = total_minutes // 60, total_minutes % 60
        time_str = f"{h}h {m}m" if h > 0 else f"{m}m"
        streak = db.get_streak(activity_name)
        streak_txt = f" 🔥{streak}" if streak > 0 else ""
        msg += f"• {activity_name.title()}: {time_str} ({count}x){streak_txt}\n"
    
    await update.message.reply_text(msg)


async def goals_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show goals"""
    user_id = update.effective_user.id
    db = get_user_db(user_id)
    
    if not db:
        await update.message.reply_text("⚠️ No sheet connected! Send /start")
        return
    
    goals = db.get_active_goals()
    
    if not goals:
        await update.message.reply_text(
            "No goals set!\n\n"
            "Examples:\n"
            "• `/setgoal exercise 150` (weekly)\n"
            "• `/setgoal meditation 15 daily`"
        )
        return
    
    msg = "🎯 **Your Goals:**\n\n"
    
    for activity_name, target, current, period in goals:
        pct = (current / target * 100) if target > 0 else 0
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        period_text = "day" if period == 'day' else "week"
        msg += f"**{activity_name.title()}** ({period_text}ly)\n{bar} {pct:.0f}%\n{current}/{target}m\n\n"
    
    await update.message.reply_text(msg)


async def set_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set goal"""
    user_id = update.effective_user.id
    db = get_user_db(user_id)
    
    if not db:
        await update.message.reply_text("⚠️ No sheet connected! Send /start")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/setgoal <activity> <minutes> [period]`\n\n"
            "Examples:\n"
            "• `/setgoal exercise 150` - 150 min/week (default)\n"
            "• `/setgoal exercise 30 daily` - 30 min/day\n"
            "• `/setgoal reading 300 weekly` - 300 min/week"
        )
        return
    
    activity = context.args[0].lower()
    try:
        target = int(context.args[1])
    except:
        await update.message.reply_text("Invalid number!")
        return
    
    # Check for period argument (default to weekly)
    period = 'week'
    if len(context.args) >= 3:
        period_arg = context.args[2].lower()
        if period_arg in ['daily', 'day', 'd']:
            period = 'day'
        elif period_arg in ['weekly', 'week', 'w']:
            period = 'week'
        else:
            await update.message.reply_text(
                "Invalid period! Use 'daily' or 'weekly'\n\n"
                "Example: `/setgoal exercise 30 daily`"
            )
            return
    
    if db.set_goal(activity, target, period):
        h, m = target // 60, target % 60
        time = f"{h}h {m}m" if h > 0 else f"{m}m"
        period_text = "day" if period == 'day' else "week"
        await update.message.reply_text(
            f"✅ Goal set!\n{activity.title()}: {time}/{period_text} 💪"
        )
    else:
        await update.message.reply_text("Failed to set goal!")


async def streak_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show streaks"""
    user_id = update.effective_user.id
    db = get_user_db(user_id)
    
    if not db:
        await update.message.reply_text("⚠️ No sheet connected! Send /start")
        return
    
    activities = db.get_week_summary()
    
    if not activities:
        await update.message.reply_text("No activities yet!")
        return
    
    msg = "🔥 **Streaks:**\n\n"
    
    for activity_name, _, _ in activities:
        streak = db.get_streak(activity_name)
        if streak > 0:
            msg += f"• {activity_name.title()}: {streak} day{'s' if streak != 1 else ''} 🔥\n"
        else:
            msg += f"• {activity_name.title()}: No streak\n"
    
    await update.message.reply_text(msg)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle activity logging"""
    user_id = update.effective_user.id
    db = get_user_db(user_id)
    
    if not db:
        await update.message.reply_text(
            "⚠️ No sheet connected!\n\nSend /start for setup."
        )
        return
    
    parsed = parse_activity(update.message.text)
    
    if parsed:
        activity_name, duration, notes = parsed
        
        if db.log_activity(activity_name, duration, notes):
            msg = f"✅ {activity_name.title()}: {duration}m"
            if notes:
                msg += f"\n💭 {notes}"
            
            goals = db.get_active_goals()
            for goal_activity, target, current, _ in goals:
                if goal_activity == activity_name:
                    pct = (current / target * 100) if target > 0 else 0
                    msg += f"\n\n🎯 Goal: {current}/{target}m ({pct:.0f}%)"
            
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("Failed to log!")
    else:
        await update.message.reply_text(
            "Try: `exercise 30m` or /help"
        )


def main():
    """Start bot"""
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set!")
        return
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("connect", connect_sheet))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("sheet", sheet_link))
    application.add_handler(CommandHandler("today", today_summary))
    application.add_handler(CommandHandler("week", week_summary))
    application.add_handler(CommandHandler("goals", goals_status))
    application.add_handler(CommandHandler("setgoal", set_goal))
    application.add_handler(CommandHandler("streak", streak_info))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()