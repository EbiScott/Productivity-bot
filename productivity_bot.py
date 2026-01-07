import os
import sqlite3
import re
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
import logging
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class ProductivityDB:
    """Database handler for productivity tracking"""
    
    def __init__(self, db_path='productivity.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Activities table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                activity_name TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
        ''')
        
        # Goals table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                activity_name TEXT NOT NULL,
                target_minutes INTEGER NOT NULL,
                period TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1
            )
        ''')
        
        # Quick buttons table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quick_buttons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                activity_name TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                UNIQUE(user_id, activity_name, duration_minutes)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def log_activity(self, user_id: int, activity_name: str, 
                     duration_minutes: int, notes: str = None) -> bool:
        """Log a new activity"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO activities (user_id, activity_name, duration_minutes, notes)
                VALUES (?, ?, ?, ?)
            ''', (user_id, activity_name, duration_minutes, notes))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
            return False
        finally:
            conn.close()
    
    def get_today_activities(self, user_id: int) -> List[Tuple]:
        """Get all activities for today"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().date()
        cursor.execute('''
            SELECT activity_name, duration_minutes, timestamp, notes
            FROM activities
            WHERE user_id = ? AND DATE(timestamp) = ?
            ORDER BY timestamp DESC
        ''', (user_id, today))
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_week_summary(self, user_id: int) -> List[Tuple]:
        """Get activity summary for the past week"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        week_ago = (datetime.now() - timedelta(days=7)).date()
        cursor.execute('''
            SELECT activity_name, SUM(duration_minutes) as total_minutes, COUNT(*) as count
            FROM activities
            WHERE user_id = ? AND DATE(timestamp) >= ?
            GROUP BY activity_name
            ORDER BY total_minutes DESC
        ''', (user_id, week_ago))
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_streak(self, user_id: int, activity_name: str) -> int:
        """Calculate consecutive days streak for an activity"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get distinct dates with this activity
        cursor.execute('''
            SELECT DISTINCT DATE(timestamp) as activity_date
            FROM activities
            WHERE user_id = ? AND activity_name = ?
            ORDER BY activity_date DESC
        ''', (user_id, activity_name))
        
        dates = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        if not dates:
            return 0
        
        streak = 1
        current_date = datetime.strptime(dates[0], '%Y-%m-%d').date()
        
        # Check if today or yesterday
        today = datetime.now().date()
        if current_date < today - timedelta(days=1):
            return 0
        
        for i in range(1, len(dates)):
            date = datetime.strptime(dates[i], '%Y-%m-%d').date()
            if current_date - date == timedelta(days=1):
                streak += 1
                current_date = date
            else:
                break
        
        return streak
    
    def set_goal(self, user_id: int, activity_name: str, 
                 target_minutes: int, period: str = 'week') -> bool:
        """Set a goal for an activity"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            # Deactivate old goals for this activity
            cursor.execute('''
                UPDATE goals SET active = 0 
                WHERE user_id = ? AND activity_name = ? AND period = ?
            ''', (user_id, activity_name, period))
            
            # Insert new goal
            cursor.execute('''
                INSERT INTO goals (user_id, activity_name, target_minutes, period)
                VALUES (?, ?, ?, ?)
            ''', (user_id, activity_name, target_minutes, period))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting goal: {e}")
            return False
        finally:
            conn.close()
    
    def get_active_goals(self, user_id: int) -> List[Tuple]:
        """Get all active goals with progress"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, activity_name, target_minutes, period
            FROM goals
            WHERE user_id = ? AND active = 1
        ''', (user_id,))
        
        goals = cursor.fetchall()
        results = []
        
        for goal_id, activity_name, target_minutes, period in goals:
            # Calculate progress
            if period == 'week':
                start_date = (datetime.now() - timedelta(days=7)).date()
            elif period == 'day':
                start_date = datetime.now().date()
            else:
                start_date = datetime.now().date()
            
            cursor.execute('''
                SELECT SUM(duration_minutes)
                FROM activities
                WHERE user_id = ? AND activity_name = ? AND DATE(timestamp) >= ?
            ''', (user_id, activity_name, start_date))
            
            current = cursor.fetchone()[0] or 0
            results.append((activity_name, target_minutes, current, period))
        
        conn.close()
        return results
    
    def add_quick_button(self, user_id: int, activity_name: str, 
                        duration_minutes: int) -> bool:
        """Add a quick button for easy logging"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO quick_buttons (user_id, activity_name, duration_minutes)
                VALUES (?, ?, ?)
            ''', (user_id, activity_name, duration_minutes))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding quick button: {e}")
            return False
        finally:
            conn.close()
    
    def get_quick_buttons(self, user_id: int) -> List[Tuple]:
        """Get all quick buttons for user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT activity_name, duration_minutes
            FROM quick_buttons
            WHERE user_id = ?
            ORDER BY activity_name
        ''', (user_id,))
        results = cursor.fetchall()
        conn.close()
        return results


# Initialize database
db = ProductivityDB()


def parse_activity(text: str) -> Optional[Tuple[str, int, str]]:
    """
    Parse activity from text like:
    - "exercise 30m"
    - "reading 45 minutes"
    - "coding 2h"
    - "meditation 15m really focused today"
    """
    # Pattern: activity_name duration [notes]
    pattern = r'^(\w+(?:\s+\w+)?)\s+(\d+)\s*(m|min|minutes?|h|hours?)\s*(.*)?$'
    match = re.match(pattern, text.strip(), re.IGNORECASE)
    
    if not match:
        return None
    
    activity_name = match.group(1).lower()
    duration = int(match.group(2))
    unit = match.group(3).lower()
    notes = match.group(4).strip() if match.group(4) else None
    
    # Convert to minutes
    if unit.startswith('h'):
        duration *= 60
    
    return activity_name, duration, notes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    welcome_msg = f"""
👋 Hey {user.first_name}! Welcome to your Productivity Bot!

I'll help you track activities and stay on top of your goals with minimal friction.

**Quick Start:**
📝 Log an activity: `exercise 30m` or `reading 1h`
📊 See today: /today
🎯 Check goals: /goals
⚡ Quick buttons: /quick

**Commands:**
/start - Show this message
/today - Today's activities
/week - This week's summary
/goals - View your goals
/setgoal - Set a new goal
/quick - Quick log buttons
/help - Detailed help

Just message me like "exercise 30m" and I'll track it! 🚀
"""
    await update.message.reply_text(welcome_msg)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message"""
    help_text = """
📚 **How to use this bot:**

**Logging Activities:**
Just send a message like:
• `exercise 30m`
• `reading 1h`
• `coding 45 minutes`
• `meditation 15m felt great today`

You can add notes at the end!

**Commands:**
/today - See what you've done today
/week - Week summary with totals
/goals - Check your goal progress
/setgoal - Set weekly goals (e.g., `/setgoal exercise 150`)
/streak - Check your streaks
/quick - Setup quick-log buttons
/addbutton - Add a quick button

**Examples:**
`exercise 30m` - Logs 30 minutes of exercise
`reading 1h really enjoyed this book` - Logs with a note
`/setgoal exercise 150` - Set goal: 150 min/week of exercise
`/addbutton exercise 30` - Create quick button for 30m exercise

The more you log, the better you'll understand your habits! 💪
"""
    await update.message.reply_text(help_text)


async def today_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's activities"""
    user_id = update.effective_user.id
    activities = db.get_today_activities(user_id)
    
    if not activities:
        await update.message.reply_text("No activities logged today yet! Time to start? 💪")
        return
    
    # Group by activity
    activity_totals = {}
    for activity_name, duration, timestamp, notes in activities:
        if activity_name not in activity_totals:
            activity_totals[activity_name] = 0
        activity_totals[activity_name] += duration
    
    msg = "📊 **Today's Activities:**\n\n"
    total_minutes = 0
    
    for activity, duration in sorted(activity_totals.items()):
        hours = duration // 60
        mins = duration % 60
        time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
        msg += f"• {activity.title()}: {time_str}\n"
        total_minutes += duration
    
    total_hours = total_minutes // 60
    total_mins = total_minutes % 60
    total_str = f"{total_hours}h {total_mins}m" if total_hours > 0 else f"{total_mins}m"
    
    msg += f"\n**Total: {total_str}**"
    
    # Check goals
    goals = db.get_active_goals(user_id)
    if goals:
        msg += "\n\n🎯 **Goal Progress:**\n"
        for activity_name, target, current, period in goals:
            if activity_name in activity_totals:
                percentage = (current / target * 100) if target > 0 else 0
                msg += f"• {activity_name.title()}: {current}/{target}m ({percentage:.0f}%)\n"
    
    await update.message.reply_text(msg)


async def week_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show week's summary"""
    user_id = update.effective_user.id
    activities = db.get_week_summary(user_id)
    
    if not activities:
        await update.message.reply_text("No activities logged this week yet!")
        return
    
    msg = "📈 **This Week's Summary:**\n\n"
    
    for activity_name, total_minutes, count in activities:
        hours = total_minutes // 60
        mins = total_minutes % 60
        time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
        
        # Get streak
        streak = db.get_streak(user_id, activity_name)
        streak_emoji = "🔥" if streak > 0 else ""
        
        msg += f"• {activity_name.title()}: {time_str} ({count} sessions) {streak_emoji}{streak if streak > 0 else ''}\n"
    
    await update.message.reply_text(msg)


async def goals_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show goal progress"""
    user_id = update.effective_user.id
    goals = db.get_active_goals(user_id)
    
    if not goals:
        await update.message.reply_text(
            "No active goals set! Use /setgoal to create one.\n\n"
            "Example: `/setgoal exercise 150` for 150 minutes per week"
        )
        return
    
    msg = "🎯 **Your Goals:**\n\n"
    
    for activity_name, target, current, period in goals:
        percentage = (current / target * 100) if target > 0 else 0
        
        # Progress bar
        filled = int(percentage / 10)
        bar = "█" * filled + "░" * (10 - filled)
        
        msg += f"**{activity_name.title()}** ({period}ly)\n"
        msg += f"{bar} {percentage:.0f}%\n"
        msg += f"{current}/{target} minutes\n\n"
    
    await update.message.reply_text(msg)


async def set_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set a new goal"""
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/setgoal <activity> <minutes>`\n\n"
            "Examples:\n"
            "• `/setgoal exercise 150` - 150 min/week\n"
            "• `/setgoal reading 300` - 300 min/week\n"
            "• `/setgoal meditation 70` - 70 min/week"
        )
        return
    
    activity_name = context.args[0].lower()
    try:
        target_minutes = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Please provide a valid number for minutes!")
        return
    
    if db.set_goal(user_id, activity_name, target_minutes):
        hours = target_minutes // 60
        mins = target_minutes % 60
        time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
        
        await update.message.reply_text(
            f"✅ Goal set! {activity_name.title()}: {time_str} per week\n\n"
            f"I'll help you track your progress! 💪"
        )
    else:
        await update.message.reply_text("Failed to set goal. Please try again.")


async def streak_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show streaks for all activities"""
    user_id = update.effective_user.id
    activities = db.get_week_summary(user_id)
    
    if not activities:
        await update.message.reply_text("No activities to show streaks for yet!")
        return
    
    msg = "🔥 **Your Streaks:**\n\n"
    
    for activity_name, _, _ in activities:
        streak = db.get_streak(user_id, activity_name)
        if streak > 0:
            msg += f"• {activity_name.title()}: {streak} day{'s' if streak != 1 else ''} 🔥\n"
        else:
            msg += f"• {activity_name.title()}: No active streak\n"
    
    await update.message.reply_text(msg)


async def quick_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show quick log buttons"""
    user_id = update.effective_user.id
    buttons = db.get_quick_buttons(user_id)
    
    if not buttons:
        await update.message.reply_text(
            "No quick buttons set yet!\n\n"
            "Use /addbutton to create them.\n"
            "Example: `/addbutton exercise 30`"
        )
        return
    
    keyboard = []
    for activity_name, duration in buttons:
        button_text = f"{activity_name.title()} {duration}m"
        callback_data = f"log_{activity_name}_{duration}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚡ Quick Log:", reply_markup=reply_markup)


async def add_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a quick button"""
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/addbutton <activity> <minutes>`\n\n"
            "Examples:\n"
            "• `/addbutton exercise 30`\n"
            "• `/addbutton reading 45`\n"
            "• `/addbutton meditation 15`"
        )
        return
    
    activity_name = context.args[0].lower()
    try:
        duration = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Please provide a valid number for minutes!")
        return
    
    if db.add_quick_button(user_id, activity_name, duration):
        await update.message.reply_text(
            f"✅ Quick button added: {activity_name.title()} {duration}m\n\n"
            f"Use /quick to access it!"
        )
    else:
        await update.message.reply_text("Button already exists or failed to add.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("log_"):
        _, activity_name, duration = data.split("_")
        duration = int(duration)
        
        if db.log_activity(user_id, activity_name, duration):
            await query.edit_message_text(
                f"✅ Logged: {activity_name.title()} for {duration} minutes!"
            )
        else:
            await query.edit_message_text("Failed to log activity. Please try again.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages for activity logging"""
    user_id = update.effective_user.id
    text = update.message.text
    
    parsed = parse_activity(text)
    
    if parsed:
        activity_name, duration, notes = parsed
        
        if db.log_activity(user_id, activity_name, duration, notes):
            msg = f"✅ Logged: {activity_name.title()} for {duration} minutes"
            if notes:
                msg += f"\nNote: {notes}"
            
            # Check if this helps with any goals
            goals = db.get_active_goals(user_id)
            for goal_activity, target, current, period in goals:
                if goal_activity == activity_name:
                    percentage = (current / target * 100) if target > 0 else 0
                    msg += f"\n\n🎯 {activity_name.title()} goal: {current}/{target}m ({percentage:.0f}%)"
            
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("Failed to log activity. Please try again.")
    else:
        await update.message.reply_text(
            "I didn't understand that. Try:\n"
            "• `exercise 30m`\n"
            "• `reading 1h`\n"
            "• Use /help for more info"
        )


def main():
    """Start the bot"""
    # Load environment variables from .env file
    load_dotenv()
    
    # Get token from environment variable
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set!")
        print("\nTo get your token:")
        print("1. Open Telegram and search for @BotFather")
        print("2. Send /newbot and follow the instructions")
        print("3. Copy the token and set it as an environment variable:")
        print("   export TELEGRAM_BOT_TOKEN='your-token-here'")
        return
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("today", today_summary))
    application.add_handler(CommandHandler("week", week_summary))
    application.add_handler(CommandHandler("goals", goals_status))
    application.add_handler(CommandHandler("setgoal", set_goal))
    application.add_handler(CommandHandler("streak", streak_info))
    application.add_handler(CommandHandler("quick", quick_buttons))
    application.add_handler(CommandHandler("addbutton", add_button))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    print("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()