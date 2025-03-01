import os
from telegram.ext import CommandHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils import auto_delete

# Bot username is needed for t.me links
BOT_USERNAME = os.getenv('BOT_USERNAME', 'kuakuachaichai_bot')

@auto_delete
def setting_command(update, context):
    """Send a link to the web app with the current chat ID"""
    chat_id = update.effective_chat.id
    
    # Use t.me link format instead of custom domain
    # Format: t.me/botusername/web?startapp=chat{chat_id}
    webapp_link = f"https://t.me/{BOT_USERNAME}/web?startapp=chat{chat_id}"
    
    # Create keyboard with web app button
    keyboard = [[
        InlineKeyboardButton(
            "打开群组设置", 
            web_app={"url": webapp_link}
        )
    ]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message with the button
    sent_message = context.bot.send_message(
        chat_id=chat_id,
        text="点击下方按钮打开群组设置，您可以查看统计数据并启用或禁用群组功能。",
        reply_markup=reply_markup
    )
    
    return sent_message

# Create handler
handler = CommandHandler('setting', setting_command) 