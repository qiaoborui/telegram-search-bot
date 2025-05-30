from telegram.ext import Updater
from threading import Thread
import asyncio
import logging
import os
from app.handlers import (
    bot_help, 
    chat_start, 
    chat_stop, 
    chat_delete, 
    msg_search,
    msg_store,
    nl_search,
    setting_command
)
from app.jobs.commands_set import set_bot_commands
from app.utils import get_text_func

logging.basicConfig(format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)
_ = get_text_func()

def setup_handlers(dispatcher):
    """Set up all command handlers"""
    logger.info("Setting up command handlers...")
    
    # Core handlers
    dispatcher.add_handler(chat_start.handler)
    dispatcher.add_handler(chat_stop.handler)
    dispatcher.add_handler(chat_delete.handler)
    dispatcher.add_handler(bot_help.handler)
    dispatcher.add_handler(setting_command.handler)
    
    # Search handlers
    dispatcher.add_handler(msg_search.handler)
    dispatcher.add_handler(msg_search.command_handler)
    
    # Natural language search handler
    logger.info("Registering natural language search handler...")
    dispatcher.add_handler(nl_search.nl_search_handler)
    logger.info("Natural language search handler registered")
    
    # Common search callback handler
    logger.info("Registering common search callback handler...")
    dispatcher.add_handler(msg_search.callback_handler)
    dispatcher.add_handler(nl_search.nl_page_handler)
    logger.info("Common search callback handler registered")
    
    # Message store handler
    dispatcher.add_handler(msg_store.handler)
    
    
    logger.info("All handlers registered successfully")

def main():
    bot_token = os.getenv('BOT_TOKEN')
    updater = Updater(token=bot_token)
    dispatcher = updater.dispatcher

    # Set up command handlers
    setup_handlers(dispatcher)

    # Set bot commands
    job = updater.job_queue
    job.run_once(set_bot_commands, 30)
    
    # Start bot
    mode_env = os.getenv("BOT_MODE")
    if mode_env == "webhook":
        url_path = os.getenv("URL_PATH")
        hook_url = os.getenv("HOOK_URL")
        updater.start_webhook(listen='0.0.0.0',
                            port=9968,
                            url_path=url_path,
                            webhook_url=hook_url)
    else:
        updater.start_polling()
    
    logger.info(_('robot start...'))
    updater.idle()

if __name__ == '__main__':
    main() 