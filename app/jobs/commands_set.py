from telegram.ext import CallbackContext
from telegram import BotCommand
from app.utils import get_text_func

_ = get_text_func()

def set_bot_commands(context: CallbackContext):
    """Set bot commands"""
    commands = [
        BotCommand('start', _('Start bot')),
        BotCommand('stop', _('Stop bot')),
        BotCommand('delete', _('Delete group data')),
        BotCommand('help', _('Help')),
        BotCommand('search', _('Search messages')),
        BotCommand('nlsearch', _('Natural language search')),
        BotCommand('setting', _('Settings & Statistics')),
    ]
    context.bot.set_my_commands(commands)
