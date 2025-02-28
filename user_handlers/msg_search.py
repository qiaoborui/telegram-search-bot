import math
import re
import os
import logging
from telegram import InlineQueryResultArticle, InputTextMessageContent, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import InlineQueryHandler, CommandHandler, CallbackQueryHandler, CallbackContext
from database import User, Message, Chat, DBSession
from sqlalchemy import and_, or_

from utils import get_filter_chats, is_userbot_mode, get_text_func, auto_delete
from .search_common import (
    build_search_keyboard, 
    format_search_results, 
    get_filter_chats_for_user,
    handle_search_page_callback,
    SEARCH_PAGE_SIZE
)

# Initialize translation function
_ = get_text_func()

# Helper function to safely use the translation function
def safe_translate(text):
    if callable(_):
        return _(text)
    return text

CACHE_TIME = 300 if not os.getenv('CACHE_TIME') else int(os.getenv('CACHE_TIME'))


def get_query_matches(query):
    user, keywords, page = None, None, 1
    if not query:
        pass
    elif re.match(' *\* +(\d+)', query):
        user, keywords, page = None, None, int(
            re.match('\* +(\d+)', query).group(1))
    # Match @user * page 
    elif re.match(' *@(.+) +\* +(\d+)', query):
        r = re.match(' *@(.+) +\* +(\d+)', query)
        user, keywords, page = r.group(1), None, int(r.group(2))
    else:
        keywords = [word for word in query.split(' ')]
        if keywords[-1].isdigit():
            page = int(keywords[-1])
            keywords.pop()
        else:
            page = 1
        # Special handling when the first character is @
        if len(keywords) >= 1 and keywords[0].startswith('@'):
            user = keywords[0].lstrip('@')
            if len(keywords) >= 2:
                keywords = keywords[1:]
            else:
                keywords = None
    return user, keywords, page


def search_messages(uname, keywords, page, filter_chats):
    messages = []
    start = (page - 1) * SEARCH_PAGE_SIZE
    stop = page * SEARCH_PAGE_SIZE
    session = DBSession()
    chat_ids = [chat[0] for chat in filter_chats]
    chat_titles = [chat[1] for chat in filter_chats]
    user_ids = []

    if uname:
        user_count = session.query(User).filter(
            or_(
                User.fullname.like('%' + uname + '%'),
                User.username.like('%' + uname + '%')
            )).count()
        if user_count >= 1:
            for user in session.query(User).filter(
                or_(
                    User.fullname.like('%' + uname + '%'),
                    User.username.like('%' + uname + '%')
                )).all():
                user_ids.append(user.id)

    if keywords:
        rule = and_(*[Message.text.like('%' + keyword + '%')
                    for keyword in keywords])
        if uname:
            count = session.query(Message).filter(rule).filter(
                Message.from_chat.in_(chat_ids)).filter(Message.from_id.in_(user_ids)).count()
            query = session.query(Message).filter(rule).filter(
                Message.from_chat.in_(chat_ids)).filter(Message.from_id.in_(user_ids))
        else:
            count = session.query(Message).filter(rule).filter(
                Message.from_chat.in_(chat_ids)).count()
            query = session.query(Message).filter(
                rule).filter(Message.from_chat.in_(chat_ids))
    else:
        if uname:
            count = session.query(Message).filter(Message.from_chat.in_(
                chat_ids)).filter(Message.from_id.in_(user_ids)).count()
            query = session.query(Message).filter(Message.from_chat.in_(
                chat_ids)).filter(Message.from_id.in_(user_ids))
        else:
            count = session.query(Message).filter(
                Message.from_chat.in_(chat_ids)).count()
            query = session.query(Message).filter(
                Message.from_chat.in_(chat_ids))

    for message in query.order_by(Message.date.desc()).slice(start, stop).all():
        user = session.query(User).filter_by(id=message.from_id).one()
        user_fullname = user.fullname
        index = chat_ids.index(message.from_chat)
        chat_title = chat_titles[index]

        if message.type != 'text':
            msg_text = f'[{message.type}] {message.text if message.text else ""}'
        else:
            msg_text = message.text

        if msg_text == '':
            continue

        messages.append(
            {
                'id': message.id,
                'link': message.link,
                'text': msg_text,
                'date': message.date,
                'user': user_fullname,
                'chat': chat_title,
                'type': message.type
            }
        )

    session.close()
    return messages, count


def inline_caps(update, context):
    from_user_id = update.inline_query.from_user.id
    session = DBSession()
    chats = session.query(Chat)
    if not chats:
        return

    # Userbot mode
    if is_userbot_mode():
        filter_chats = get_filter_chats(from_user_id)
    else:
        filter_chats = []
        enabled_chats = [chat for chat in chats if chat.enable]
        
        if not enabled_chats:
            results = [
                InlineQueryResultArticle(
                    id='no_enabled_chats',
                    title=_('No enabled groups found'),
                    description=_('Please use /start to enable the bot in your group first'),
                    input_message_content=InputTextMessageContent(_('Please use /start to enable the bot in your group first'))
                )
            ]
            context.bot.answer_inline_query(
                update.inline_query.id, results, cache_time=10)
            return
            
        for chat in enabled_chats:
            try:
                chat_member = context.bot.get_chat_member(
                    chat_id=chat.id, user_id=from_user_id)
                if chat_member.status not in ['left', 'kicked']:
                    filter_chats.append((chat.id, chat.title))
            except telegram.error.BadRequest as e:
                logging.error(f"获取群组 {chat.id} 成员信息失败: {str(e)}")
            except telegram.error.Unauthorized as e:
                logging.error(f"群组 {chat.id} 未授权: {str(e)}")
            except Exception as e:
                logging.error(f"处理群组 {chat.id} 时发生错误: {str(e)}")

    query = update.inline_query.query
    user, keywords, page = get_query_matches(query)

    if len(filter_chats) == 0:
        results = [
            InlineQueryResultArticle(
                id='no_access',
                title=_('No searchable groups'),
                description=_('Please ensure: 1. Use /start to enable the bot 2. Grant admin rights 3. Disable privacy mode'),
                input_message_content=InputTextMessageContent(_('Please ensure the bot is properly enabled and has sufficient permissions'))
            )
        ]
        context.bot.answer_inline_query(
            update.inline_query.id, results, cache_time=10)
        return

    messages, count = search_messages(user, keywords, page, filter_chats)

    if count == 0:
        results = [
            InlineQueryResultArticle(
                id='empty',
                title=_('No results found'),
                description=_('Attention! Do not click any buttons, otherwise an empty message will be sent'),
                input_message_content=InputTextMessageContent('⁤')
            )]
        context.bot.answer_inline_query(
            update.inline_query.id, results, cache_time=10)
        return

    total_pages = math.ceil(count / SEARCH_PAGE_SIZE)

    result_text = format_search_results(messages, page, count)
    query_params = {
        'user': user,
        'keywords': keywords
    }

    results = [
        InlineQueryResultArticle(
            id='search_result',
            title=_('Search Results (Total: {})').format(count),
            description=_('Page {} of {}').format(page, total_pages),
            input_message_content=InputTextMessageContent(
                result_text,
                parse_mode='Markdown',
                disable_web_page_preview=True
            ),
            reply_markup=build_search_keyboard(page, total_pages, "search", query_params)
        )
    ]

    context.bot.answer_inline_query(
        update.inline_query.id, results, cache_time=CACHE_TIME)

@auto_delete(timeout=120)  # 设置2分钟超时
def handle_search_command(update: Update, context: CallbackContext):
    """处理/search命令"""
    if not update.message:
        return None
    
    query = ' '.join(context.args) if context.args else ''
    user, keywords, page = get_query_matches(query)
    
    from_user_id = update.effective_user.id
    current_chat_id = update.effective_chat.id
    
    # 获取可搜索的群组
    filter_chats = get_filter_chats_for_user(context, from_user_id)
    
    if len(filter_chats) == 0:
        return update.message.reply_text(safe_translate("You are not a member of any groups where the bot is enabled.") + "\n" + 
                                safe_translate("Please ensure:\n1. Use /start to enable the bot\n2. Grant admin rights\n3. Disable privacy mode"))
    
    # 保存当前群组ID到用户数据中，用于翻页时验证
    context.user_data['last_chat_id'] = current_chat_id
    
    # 构建查询参数
    query_params = {
        'user': user,
        'keywords': keywords
    }
    
    messages, count = search_messages(user, keywords, page, filter_chats)
    total_pages = math.ceil(count / SEARCH_PAGE_SIZE)
    
    result_text = format_search_results(messages, page, count)
    
    return update.message.reply_text(
        result_text,
        parse_mode='Markdown',
        disable_web_page_preview=True,
        reply_markup=build_search_keyboard(page, total_pages, "search", query_params)
    )

# 添加新的handler
command_handler = CommandHandler('search', handle_search_command)
callback_handler = CallbackQueryHandler(handle_search_page_callback, pattern=r'^search\|search\|')

handler = InlineQueryHandler(inline_caps)
