"""
Ultimate Productivity Bot - Complete Version
Simple, button-based habit tracking with automatic weekly PDF reports
"""

import os
import sqlite3
import re
import pickle
from datetime import datetime, timedelta, time
from typing import Optional, List, Tuple, Dict
import logging
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# For PDF generation
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import io

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Storage
DB_FILE = 'productivity.db'
STORAGE_FILE = 'user_data.pkl'


class ProductivityDB:
    """Database handler for productivity tracking"""
    
    def __init__(self, db_path=DB_FILE):
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
                date TEXT NOT NULL,
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
                emoji TEXT DEFAULT '⭐',
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
            now = datetime.now()
            cursor.execute('''
                INSERT INTO activities (user_id, activity_name, duration_minutes, date, notes)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, activity_name, duration_minutes, now.strftime('%Y-%m-%d'), notes))
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
        today = datetime.now().date().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT activity_name, duration_minutes, timestamp, notes
            FROM activities
            WHERE user_id = ? AND date = ?
            ORDER BY timestamp DESC
        ''', (user_id, today))
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_week_summary(self, user_id: int) -> List[Tuple]:
        """Get activity summary for the past week"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        week_ago = (datetime.now() - timedelta(days=7)).date().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT activity_name, SUM(duration_minutes) as total_minutes, COUNT(*) as count
            FROM activities
            WHERE user_id = ? AND date >= ?
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
        
        cursor.execute('''
            SELECT DISTINCT date
            FROM activities
            WHERE user_id = ? AND activity_name = ?
            ORDER BY date DESC
        ''', (user_id, activity_name))
        
        dates = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        if not dates:
            return 0
        
        streak = 1
        current_date = datetime.strptime(dates[0], '%Y-%m-%d').date()
        today = datetime.now().date()
        
        # Must be today or yesterday
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
            # Deactivate old goals
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
            SELECT activity_name, target_minutes, period
            FROM goals
            WHERE user_id = ? AND active = 1
        ''', (user_id,))
        
        goals = cursor.fetchall()
        results = []
        
        for activity_name, target_minutes, period in goals:
            # Calculate progress
            if period == 'day':
                start_date = datetime.now().date().strftime('%Y-%m-%d')
            else:  # week
                start_date = (datetime.now() - timedelta(days=7)).date().strftime('%Y-%m-%d')
            
            cursor.execute('''
                SELECT SUM(duration_minutes)
                FROM activities
                WHERE user_id = ? AND activity_name = ? AND date >= ?
            ''', (user_id, activity_name, start_date))
            
            current = cursor.fetchone()[0] or 0
            results.append((activity_name, target_minutes, current, period))
        
        conn.close()
        return results
    
    def add_quick_button(self, user_id: int, activity_name: str, 
                        duration_minutes: int, emoji: str = '⭐') -> bool:
        """Add a quick button for easy logging"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO quick_buttons (user_id, activity_name, duration_minutes, emoji)
                VALUES (?, ?, ?, ?)
            ''', (user_id, activity_name, duration_minutes, emoji))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error adding quick button: {e}")
            return False
        finally:
            conn.close()
    
    def remove_quick_button(self, user_id: int, activity_name: str, 
                           duration_minutes: int) -> bool:
        """Remove a quick button"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                DELETE FROM quick_buttons 
                WHERE user_id = ? AND activity_name = ? AND duration_minutes = ?
            ''', (user_id, activity_name, duration_minutes))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing quick button: {e}")
            return False
        finally:
            conn.close()
    
    def get_quick_buttons(self, user_id: int) -> List[Tuple]:
        """Get all quick buttons for user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT activity_name, duration_minutes, emoji
            FROM quick_buttons
            WHERE user_id = ?
            ORDER BY activity_name, duration_minutes
        ''', (user_id,))
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_week_data_for_report(self, user_id: int) -> Dict:
        """Get all data needed for weekly report"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        week_ago = (datetime.now() - timedelta(days=7)).date().strftime('%Y-%m-%d')
        
        # Get all activities for the week
        cursor.execute('''
            SELECT date, activity_name, SUM(duration_minutes) as total
            FROM activities
            WHERE user_id = ? AND date >= ?
            GROUP BY date, activity_name
            ORDER BY date
        ''', (user_id, week_ago))
        
        activities_by_day = {}
        for date_str, activity, minutes in cursor.fetchall():
            if date_str not in activities_by_day:
                activities_by_day[date_str] = {}
            activities_by_day[date_str][activity] = minutes
        
        # Get totals by activity
        cursor.execute('''
            SELECT activity_name, SUM(duration_minutes) as total, COUNT(*) as sessions
            FROM activities
            WHERE user_id = ? AND date >= ?
            GROUP BY activity_name
            ORDER BY total DESC
        ''', (user_id, week_ago))
        
        totals = {row[0]: {'minutes': row[1], 'sessions': row[2]} 
                  for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            'activities_by_day': activities_by_day,
            'totals': totals,
            'week_start': week_ago,
            'week_end': datetime.now().date().strftime('%Y-%m-%d')
        }


# Initialize database
db = ProductivityDB()


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


def generate_weekly_pdf(user_id: int, username: str) -> io.BytesIO:
    """Generate a beautiful weekly report PDF"""
    data = db.get_week_data_for_report(user_id)
    goals = db.get_active_goals(user_id)
    
    # Create PDF in memory
    pdf_buffer = io.BytesIO()
    
    with PdfPages(pdf_buffer) as pdf:
        # Page 1: Overview
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(11, 8.5))
        fig.suptitle(f'📊 Weekly Productivity Report - {username}', 
                     fontsize=16, fontweight='bold')
        
        # Chart 1: Total time by activity (bar chart)
        if data['totals']:
            activities = list(data['totals'].keys())
            minutes = [data['totals'][a]['minutes'] for a in activities]
            hours = [m/60 for m in minutes]
            
            ax1.barh(activities, hours, color='#4CAF50')
            ax1.set_xlabel('Hours')
            ax1.set_title('Total Time by Activity')
            ax1.grid(axis='x', alpha=0.3)
            
            # Chart 2: Sessions by activity
            sessions = [data['totals'][a]['sessions'] for a in activities]
            ax2.barh(activities, sessions, color='#2196F3')
            ax2.set_xlabel('Sessions')
            ax2.set_title('Number of Sessions')
            ax2.grid(axis='x', alpha=0.3)
            
            # Chart 3: Daily breakdown (stacked bar)
            dates = sorted(data['activities_by_day'].keys())
            if dates:
                date_labels = [datetime.strptime(d, '%Y-%m-%d').strftime('%a %m/%d') 
                              for d in dates]
                
                bottom = [0] * len(dates)
                colors = plt.cm.Set3(range(len(activities)))
                
                for i, activity in enumerate(activities):
                    values = [data['activities_by_day'].get(d, {}).get(activity, 0)/60 
                             for d in dates]
                    ax3.bar(date_labels, values, bottom=bottom, 
                           label=activity.title(), color=colors[i])
                    bottom = [b + v for b, v in zip(bottom, values)]
                
                ax3.set_ylabel('Hours')
                ax3.set_title('Daily Activity Breakdown')
                ax3.legend(loc='upper left', fontsize=8)
                ax3.grid(axis='y', alpha=0.3)
                plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Chart 4: Goal progress
        if goals:
            goal_names = [f"{g[0].title()}\n({g[3]})" for g in goals]
            progress_pct = [(g[2]/g[1]*100) if g[1] > 0 else 0 for g in goals]
            colors_goals = ['#4CAF50' if p >= 100 else '#FFC107' if p >= 75 
                           else '#FF9800' if p >= 50 else '#F44336' 
                           for p in progress_pct]
            
            ax4.barh(goal_names, progress_pct, color=colors_goals)
            ax4.set_xlabel('Progress (%)')
            ax4.set_title('Goal Progress')
            ax4.axvline(x=100, color='green', linestyle='--', alpha=0.5)
            ax4.grid(axis='x', alpha=0.3)
            ax4.set_xlim(0, max(120, max(progress_pct) if progress_pct else 100))
        else:
            ax4.text(0.5, 0.5, 'No goals set', 
                    ha='center', va='center', fontsize=12)
            ax4.axis('off')
        
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()
        
        # Page 2: Detailed statistics
        fig, ax = plt.subplots(figsize=(8.5, 11))
        ax.axis('tight')
        ax.axis('off')
        
        # Title
        fig.text(0.5, 0.95, 'Detailed Statistics', 
                ha='center', fontsize=14, fontweight='bold')
        
        # Summary text
        report_text = f"Week: {data['week_start']} to {data['week_end']}\n\n"
        
        if data['totals']:
            total_minutes = sum(d['minutes'] for d in data['totals'].values())
            total_hours = total_minutes / 60
            report_text += f"📊 TOTAL TIME: {int(total_hours)}h {int(total_minutes % 60)}m\n\n"
            
            report_text += "📈 BY ACTIVITY:\n"
            for activity, stats in sorted(data['totals'].items(), 
                                        key=lambda x: x[1]['minutes'], 
                                        reverse=True):
                h = stats['minutes'] // 60
                m = stats['minutes'] % 60
                streak = db.get_streak(user_id, activity)
                streak_txt = f" 🔥{streak}" if streak > 0 else ""
                report_text += f"  • {activity.title()}: {h}h {m}m ({stats['sessions']} sessions){streak_txt}\n"
            
            report_text += "\n🎯 GOALS:\n"
            if goals:
                for activity_name, target, current, period in goals:
                    pct = (current / target * 100) if target > 0 else 0
                    status = "✅" if pct >= 100 else "⏳"
                    h_target = target // 60
                    m_target = target % 60
                    h_current = current // 60
                    m_current = current % 60
                    period_txt = "per day" if period == 'day' else "per week"
                    report_text += f"  {status} {activity_name.title()}: {h_current}h {m_current}m / {h_target}h {m_target}m {period_txt} ({pct:.0f}%)\n"
            else:
                report_text += "  No goals set\n"
            
            report_text += "\n📅 DAILY BREAKDOWN:\n"
            for date in sorted(data['activities_by_day'].keys()):
                date_label = datetime.strptime(date, '%Y-%m-%d').strftime('%A, %b %d')
                daily_total = sum(data['activities_by_day'][date].values())
                h = daily_total // 60
                m = daily_total % 60
                report_text += f"  {date_label}: {h}h {m}m\n"
                for activity, minutes in sorted(data['activities_by_day'][date].items()):
                    report_text += f"    - {activity.title()}: {minutes}m\n"
        else:
            report_text += "No activities logged this week."
        
        fig.text(0.1, 0.85, report_text, fontsize=10, 
                verticalalignment='top', family='monospace')
        
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()
    
    pdf_buffer.seek(0)
    return pdf_buffer


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message with quick buttons"""
    user = update.effective_user
    user_id = user.id
    
    # Get user's quick buttons
    buttons = db.get_quick_buttons(user_id)
    
    welcome_msg = f"""👋 Hey {user.first_name}! Welcome to Productivity Bot!

📊 **Track your habits instantly with quick buttons!**

"""
    
    if buttons:
        welcome_msg += "✨ **Your Quick Buttons:**\n(Tap to log instantly!)\n\n"
        # Show buttons
        keyboard = create_button_keyboard(buttons)
        await update.message.reply_text(welcome_msg, reply_markup=keyboard)
    else:
        welcome_msg += """🚀 **Get Started:**

1️⃣ Add quick buttons:
   `/addbutton prayer 15` - Adds a 15min button
   `/addbutton exercise 30` - Adds a 30min button

2️⃣ Set goals:
   `/setgoal prayer 600 week` - 10h/week goal
   `/setgoal exercise 30 day` - 30min/day goal

3️⃣ Tap buttons to log activities!

**Commands:**
/today - Today's summary
/week - This week's summary
/goals - View your goals
/streak - View your streaks
/help - Full help

Let's start! Try: `/addbutton prayer 15`
"""
        await update.message.reply_text(welcome_msg)


def create_button_keyboard(buttons: List[Tuple]) -> InlineKeyboardMarkup:
    """Create inline keyboard from quick buttons"""
    keyboard = []
    for activity_name, duration, emoji in buttons:
        button_text = f"{emoji} {activity_name.title()} {duration}m"
        callback_data = f"log_{activity_name}_{duration}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Add refresh button
    keyboard.append([InlineKeyboardButton("🔄 Refresh Buttons", callback_data="refresh")])
    
    return InlineKeyboardMarkup(keyboard)


async def show_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's quick buttons"""
    user_id = update.effective_user.id
    buttons = db.get_quick_buttons(user_id)
    
    if not buttons:
        await update.message.reply_text(
            "You don't have any quick buttons yet!\n\n"
            "Add one with: `/addbutton prayer 15`"
        )
        return
    
    keyboard = create_button_keyboard(buttons)
    await update.message.reply_text("⚡ **Quick Log:**", reply_markup=keyboard)


async def add_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a quick button"""
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/addbutton <activity> <minutes> [emoji]`\n\n"
            "Examples:\n"
            "• `/addbutton prayer 15` - Default emoji\n"
            "• `/addbutton prayer 30 🙏` - Custom emoji\n"
            "• `/addbutton exercise 45 💪`\n"
            "• `/addbutton reading 60 📖`"
        )
        return
    
    activity = context.args[0].lower()
    try:
        duration = int(context.args[1])
    except:
        await update.message.reply_text("❌ Invalid number!")
        return
    
    emoji = context.args[2] if len(context.args) >= 3 else '⭐'
    
    if db.add_quick_button(user_id, activity, duration, emoji):
        await update.message.reply_text(
            f"✅ Quick button added!\n"
            f"{emoji} {activity.title()} {duration}m\n\n"
            "Use /buttons to see all your buttons!"
        )
        
        # Show updated buttons
        buttons = db.get_quick_buttons(user_id)
        keyboard = create_button_keyboard(buttons)
        await update.message.reply_text("⚡ **Your Buttons:**", reply_markup=keyboard)
    else:
        await update.message.reply_text("❌ Button already exists or failed to add.")


async def remove_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a quick button"""
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/removebutton <activity> <minutes>`\n\n"
            "Example: `/removebutton prayer 15`"
        )
        return
    
    activity = context.args[0].lower()
    try:
        duration = int(context.args[1])
    except:
        await update.message.reply_text("❌ Invalid number!")
        return
    
    if db.remove_quick_button(user_id, activity, duration):
        await update.message.reply_text(
            f"✅ Button removed!\n"
            f"{activity.title()} {duration}m"
        )
    else:
        await update.message.reply_text("❌ Button not found.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "refresh":
        # Refresh buttons
        buttons = db.get_quick_buttons(user_id)
        if buttons:
            keyboard = create_button_keyboard(buttons)
            await query.edit_message_text("⚡ **Quick Log:**", reply_markup=keyboard)
        else:
            await query.edit_message_text("No buttons yet! Add one with /addbutton")
        return
    
    if data.startswith("log_"):
        _, activity_name, duration_str = data.split("_")
        duration = int(duration_str)
        
        if db.log_activity(user_id, activity_name, duration):
            # Get goals for this activity
            goals = db.get_active_goals(user_id)
            msg = f"✅ {activity_name.title()}: {duration}m logged!"
            
            # Show goal progress
            for goal_activity, target, current, period in goals:
                if goal_activity == activity_name:
                    pct = (current / target * 100) if target > 0 else 0
                    period_txt = "today" if period == 'day' else "this week"
                    status = "✅" if pct >= 100 else "⏳"
                    msg += f"\n{status} Goal ({period_txt}): {current}/{target}m ({pct:.0f}%)"
            
            await query.edit_message_text(msg)
        else:
            await query.edit_message_text("❌ Failed to log. Try again!")


async def log_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual logging via command"""
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/log <activity> <time>`\n\n"
            "Examples:\n"
            "• `/log prayer 15m`\n"
            "• `/log exercise 1h`"
        )
        return
    
    activity = context.args[0].lower()
    time_str = context.args[1]
    
    # Parse time
    match = re.match(r'(\d+)(m|h)', time_str, re.IGNORECASE)
    if not match:
        await update.message.reply_text("❌ Invalid time format! Use 15m or 1h")
        return
    
    duration = int(match.group(1))
    unit = match.group(2).lower()
    if unit == 'h':
        duration *= 60
    
    if db.log_activity(user_id, activity, duration):
        await update.message.reply_text(f"✅ Logged: {activity.title()} {duration}m")
    else:
        await update.message.reply_text("❌ Failed to log!")


async def today_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's activities"""
    user_id = update.effective_user.id
    activities = db.get_today_activities(user_id)
    
    if not activities:
        await update.message.reply_text("📊 No activities today yet!\n\nTap a quick button to log! /buttons")
        return
    
    # Group by activity
    activity_totals = {}
    for activity_name, duration, timestamp, notes in activities:
        activity_totals[activity_name] = activity_totals.get(activity_name, 0) + duration
    
    msg = f"📊 **Today ({datetime.now().strftime('%A, %b %d')})**\n\n"
    total = 0
    
    for activity, duration in sorted(activity_totals.items()):
        h, m = duration // 60, duration % 60
        time_str = f"{h}h {m}m" if h > 0 else f"{m}m"
        msg += f"• {activity.title()}: {time_str}\n"
        total += duration
    
    h, m = total // 60, total % 60
    msg += f"\n**Total: {h}h {m}m**" if h > 0 else f"\n**Total: {m}m**"
    
    # Show daily goals
    goals = db.get_active_goals(user_id)
    daily_goals = [g for g in goals if g[3] == 'day']
    if daily_goals:
        msg += "\n\n🎯 **Daily Goals:**\n"
        for activity_name, target, current, _ in daily_goals:
            pct = (current / target * 100) if target > 0 else 0
            status = "✅" if pct >= 100 else "⏳"
            msg += f"{status} {activity_name.title()}: {current}/{target}m ({pct:.0f}%)\n"
    
    await update.message.reply_text(msg)


async def week_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show week summary"""
    user_id = update.effective_user.id
    activities = db.get_week_summary(user_id)
    
    if not activities:
        await update.message.reply_text("📈 No activities this week yet!")
        return
    
    msg = "📈 **This Week:**\n\n"
    
    for activity_name, total_minutes, count in activities:
        h, m = total_minutes // 60, total_minutes % 60
        time_str = f"{h}h {m}m" if h > 0 else f"{m}m"
        streak = db.get_streak(user_id, activity_name)
        streak_txt = f" 🔥{streak}" if streak > 0 else ""
        msg += f"• {activity_name.title()}: {time_str} ({count}x){streak_txt}\n"
    
    await update.message.reply_text(msg)


async def goals_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show goals"""
    user_id = update.effective_user.id
    goals = db.get_active_goals(user_id)
    
    if not goals:
        await update.message.reply_text(
            "🎯 No goals set!\n\n"
            "Examples:\n"
            "• `/setgoal prayer 600 week` - 10h/week\n"
            "• `/setgoal exercise 30 day` - 30min/day"
        )
        return
    
    msg = "🎯 **Your Goals:**\n\n"
    
    # Group by period
    daily_goals = [g for g in goals if g[3] == 'day']
    weekly_goals = [g for g in goals if g[3] == 'week']
    
    if daily_goals:
        msg += "**Daily Goals:**\n"
        for activity_name, target, current, _ in daily_goals:
            pct = (current / target * 100) if target > 0 else 0
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            status = "✅" if pct >= 100 else ""
            msg += f"{activity_name.title()}\n{bar} {pct:.0f}% {status}\n{current}/{target}m\n\n"
    
    if weekly_goals:
        msg += "**Weekly Goals:**\n"
        for activity_name, target, current, _ in weekly_goals:
            pct = (current / target * 100) if target > 0 else 0
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            status = "✅" if pct >= 100 else ""
            msg += f"{activity_name.title()}\n{bar} {pct:.0f}% {status}\n{current}/{target}m\n\n"
    
    await update.message.reply_text(msg)


async def set_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set goal"""
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/setgoal <activity> <minutes> [period]`\n\n"
            "Examples:\n"
            "• `/setgoal prayer 600 week` - 10h/week\n"
            "• `/setgoal exercise 30 day` - 30min/day\n"
            "• `/setgoal reading 300` - defaults to week"
        )
        return
    
    activity = context.args[0].lower()
    try:
        target = int(context.args[1])
    except:
        await update.message.reply_text("❌ Invalid number!")
        return
    
    period = 'week'
    if len(context.args) >= 3:
        period_arg = context.args[2].lower()
        if period_arg in ['day', 'daily', 'd']:
            period = 'day'
        elif period_arg not in ['week', 'weekly', 'w']:
            await update.message.reply_text("❌ Invalid period! Use 'day' or 'week'")
            return
    
    if db.set_goal(user_id, activity, target, period):
        h, m = target // 60, target % 60
        time = f"{h}h {m}m" if h > 0 else f"{m}m"
        period_txt = "per day" if period == 'day' else "per week"
        await update.message.reply_text(
            f"✅ Goal set!\n"
            f"{activity.title()}: {time} {period_txt} 💪"
        )
    else:
        await update.message.reply_text("❌ Failed to set goal!")


async def streak_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show streaks"""
    user_id = update.effective_user.id
    activities = db.get_week_summary(user_id)
    
    if not activities:
        await update.message.reply_text("🔥 No activities to show streaks for yet!")
        return
    
    msg = "🔥 **Your Streaks:**\n\n"
    has_streak = False
    
    for activity_name, _, _ in activities:
        streak = db.get_streak(user_id, activity_name)
        if streak > 0:
            msg += f"• {activity_name.title()}: {streak} day{'s' if streak != 1 else ''} 🔥\n"
            has_streak = True
        else:
            msg += f"• {activity_name.title()}: No active streak\n"
    
    if not has_streak:
        msg += "\n💡 Tip: Do activities daily to build streaks!"
    
    await update.message.reply_text(msg)


async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send PDF report"""
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    
    await update.message.reply_text("📊 Generating your report... ⏳")
    
    try:
        pdf_buffer = generate_weekly_pdf(user_id, username)
        
        await update.message.reply_document(
            document=pdf_buffer,
            filename=f"productivity_report_{datetime.now().strftime('%Y%m%d')}.pdf",
            caption="📊 Here's your weekly productivity report!"
        )
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        await update.message.reply_text("❌ Failed to generate report. Make sure you have some activities logged!")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message"""
    help_text = """📚 **Productivity Bot - Help**

🚀 **QUICK START:**
1. `/addbutton prayer 15` - Add button
2. Tap button to log activity!
3. `/today` - See your progress

⚡ **QUICK BUTTONS:**
`/addbutton <activity> <min> [emoji]`
`/removebutton <activity> <min>`
`/buttons` - Show all buttons

📝 **LOGGING:**
• Tap quick buttons (easiest!)
• `/log prayer 30m` - Manual logging

🎯 **GOALS:**
`/setgoal <activity> <min> <day/week>`
`/goals` - View all goals

📊 **TRACKING:**
`/today` - Today's summary
`/week` - This week's summary
`/streak` - View your streaks
`/report` - Generate PDF report

**Examples:**
• `/addbutton prayer 15 🙏`
• `/setgoal prayer 600 week`
• `/log exercise 45m`

Keep it simple - just tap buttons! 🎯
"""
    await update.message.reply_text(help_text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for logging"""
    user_id = update.effective_user.id
    text = update.message.text
    
    parsed = parse_activity(text)
    
    if parsed:
        activity_name, duration, notes = parsed
        
        if db.log_activity(user_id, activity_name, duration, notes):
            msg = f"✅ {activity_name.title()}: {duration}m"
            if notes:
                msg += f"\n💭 {notes}"
            
            goals = db.get_active_goals(user_id)
            for goal_activity, target, current, period in goals:
                if goal_activity == activity_name:
                    pct = (current / target * 100) if target > 0 else 0
                    period_txt = "today" if period == 'day' else "this week"
                    msg += f"\n\n🎯 Goal ({period_txt}): {current}/{target}m ({pct:.0f}%)"
            
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("❌ Failed to log!")
    else:
        await update.message.reply_text(
            "💡 Try:\n"
            "• Tap a quick button (/buttons)\n"
            "• Or type: `prayer 30m`\n"
            "• Or use: `/log prayer 30m`"
        )


def main():
    """Start the bot"""
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN not set!")
        print("\n📝 To get your token:")
        print("1. Open Telegram and search for @BotFather")
        print("2. Send /newbot and follow instructions")
        print("3. Set environment variable:")
        print("   export TELEGRAM_BOT_TOKEN='your-token-here'")
        return
    
    application = Application.builder().token(TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("buttons", show_buttons))
    application.add_handler(CommandHandler("addbutton", add_button))
    application.add_handler(CommandHandler("removebutton", remove_button))
    application.add_handler(CommandHandler("log", log_manual))
    application.add_handler(CommandHandler("today", today_summary))
    application.add_handler(CommandHandler("week", week_summary))
    application.add_handler(CommandHandler("goals", goals_status))
    application.add_handler(CommandHandler("setgoal", set_goal))
    application.add_handler(CommandHandler("streak", streak_info))
    application.add_handler(CommandHandler("report", generate_report))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Bot is starting...")
    print("📊 Productivity Bot is ready!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()