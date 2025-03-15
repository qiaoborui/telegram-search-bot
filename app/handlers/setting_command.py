import os
from telegram.ext import CommandHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from app.utils import auto_delete

# Bot username is needed for t.me links
BOT_USERNAME = os.getenv('BOT_USERNAME', 'kuakuachaichai_bot')

@auto_delete
def setting_command(update, context):
    """Send a link to the web app with the current chat ID"""
    chat_id = update.effective_chat.id
    
    # Check if this is a group chat
    is_group = update.effective_chat.type in ["group", "supergroup"]
    
    # Create webapp link
    if is_group:
        # For group chats, include the chat ID in the startapp parameter
        webapp_link = f"https://t.me/{BOT_USERNAME}/web?startapp=chat{chat_id}"
        button_text = "打开群组设置"
        message_text = "点击下方按钮打开群组设置，您可以查看统计数据并启用或禁用群组功能。"
    else:
        # For private chats, open the webapp without a specific chat ID
        webapp_link = f"https://t.me/{BOT_USERNAME}/web"
        button_text = "打开群组选择"
        message_text = "点击下方按钮选择要管理的群组，您可以查看统计数据并启用或禁用群组功能。"
    
    # Create keyboard with URL button
    keyboard = [[
        InlineKeyboardButton(
            button_text, 
            url=webapp_link
        )
    ]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message with the button
    sent_message = context.bot.send_message(
        chat_id=chat_id,
        text=message_text,
        reply_markup=reply_markup
    )
    
    return sent_message

# Create handler
handler = CommandHandler('setting', setting_command) 