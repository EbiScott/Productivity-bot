#!/bin/bash

# Productivity Bot Startup Script

echo "🚀 Starting Productivity Bot..."
echo ""

# Check if token is set
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "⚠️  TELEGRAM_BOT_TOKEN environment variable not set!"
    echo ""
    echo "Please set your bot token:"
    echo "  export TELEGRAM_BOT_TOKEN='your-token-here'"
    echo ""
    echo "Or enter it now:"
    read -p "Token: " TOKEN
    export TELEGRAM_BOT_TOKEN=$TOKEN
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed!"
    exit 1
fi

# Check if dependencies are installed
if ! python3 -c "import telegram" &> /dev/null; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

# Run the bot
echo "✅ Starting bot..."
echo ""
python3 productivity_bot.py