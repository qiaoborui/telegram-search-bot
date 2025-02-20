import math
import re
import html
import telegram
import os
import logging
from telegram import InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultCachedSticker, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import InlineQueryHandler, CommandHandler, CallbackQueryHandler, CallbackContext
from database import User, Message, Chat, DBSession
from sqlalchemy import and_, or_
import pytz

from utils import get_filter_chats, is_userbot_mode, get_text_func, auto_delete

_ = get_text_func()

SEARCH_PAGE_SIZE = 25
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
    else:
        results = [
            InlineQueryResultArticle(
                id='info',
                title=_('Total: {}. Page {} of {}').format(
                    count, page, math.ceil(count / SEARCH_PAGE_SIZE)),
                description=_('Attention! This is just a prompt message, do not click on it, otherwise a /help message will be sent'),
                input_message_content=InputTextMessageContent(
                    f'/help@{context.bot.get_me().username}')
            )
        ]

    for message in messages:
        results.append(
            InlineQueryResultArticle(
                id=message['id'],
                title='{}'.format(message['text'][:100]),
                description=message['date'].strftime("%Y-%m-%d").ljust(40) + str(message['user']) + '@' + message[
                    'chat'],
                input_message_content=InputTextMessageContent(
                    '「{}」<a href="{}">Via {}</a>'.format(html.escape(message['text']),
                                                         message['link'],
                                                         message['user']), parse_mode='html'
                )
            )
        )
    context.bot.answer_inline_query(
        update.inline_query.id, results, cache_time=CACHE_TIME, is_personal=True)


def build_keyboard(page, total_pages, query_params):
    """构建翻页键盘
    query_params: 包含搜索参数的字典，包括 user 和 keywords
    """
    keyboard = []
    buttons = []
    
    # 构建查询参数字符串
    param_str = ''
    if query_params.get('user'):
        param_str += f"@{query_params['user']} "
    if query_params.get('keywords'):
        param_str += ' '.join(query_params['keywords']) + ' '
    
    if page > 1:
        prev_command = f"{param_str}{page-1}".strip()
        buttons.append(InlineKeyboardButton("⬅️", callback_data=f"page_{prev_command}"))
    
    buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    
    if page < total_pages:
        next_command = f"{param_str}{page+1}".strip()
        buttons.append(InlineKeyboardButton("➡️", callback_data=f"page_{next_command}"))
    
    keyboard.append(buttons)
    return InlineKeyboardMarkup(keyboard)

def format_search_results(messages, page, total_count):
    """格式化搜索结果文本"""
    if not messages:
        return _("No results found")
    
    result = _("*Search Results* (Total: {})\n").format(total_count)
    
    # Group messages by chat
    chat_messages = {}
    for msg in messages:
        if msg['chat'] not in chat_messages:
            chat_messages[msg['chat']] = []
        chat_messages[msg['chat']].append(msg)
    
    # 设置时区
    local_tz = pytz.timezone('Asia/Shanghai')
    
    for chat, msgs in chat_messages.items():
        # Add chat header
        result += f"\n*{html.escape(chat)}*\n"
        result += "━━━━━━━━━━━━━━━\n"
        
        for msg in msgs:
            # Format message with embedded link and sender name
            message_text = html.escape(msg['text'][:200])
            if len(msg['text']) > 200:
                message_text += "..."
            
            # 转换时间到本地时区
            msg_date = msg['date']
            if not msg_date.tzinfo:
                msg_date = pytz.utc.localize(msg_date)
            local_date = msg_date.astimezone(local_tz)
            date_str = local_date.strftime("%Y-%m-%d %H:%M")
            
            # 添加消息链接和格式化
            result += f"[*{html.escape(msg['user'])}*: {message_text}]({msg['link']}) | {date_str}\n"
    
    return result

@auto_delete(timeout=120)  # 设置2分钟超时
def handle_search_command(update: Update, context: CallbackContext):
    """处理/search命令"""
    if not update.message:
        return None
    
    query = ' '.join(context.args) if context.args else ''
    user, keywords, page = get_query_matches(query)
    
    from_user_id = update.effective_user.id
    session = DBSession()
    chats = session.query(Chat)
    
    # 检查是否有启用的群组
    enabled_chats = [chat for chat in chats if chat.enable]
    if not enabled_chats:
        return update.message.reply_text(_("No enabled groups found, please use /start to enable the bot first"))
        
    filter_chats = []
    for chat in enabled_chats:
        try:
            chat_member = context.bot.get_chat_member(
                chat_id=chat.id, user_id=from_user_id)
            if chat_member.status not in ['left', 'kicked']:
                filter_chats.append((chat.id, chat.title))
        except telegram.error.BadRequest as e:
            logging.error(f"获取群组 {chat.id} 成员信息失败: {str(e)}")
            if "administrator" in str(e).lower():
                update.message.reply_text(_("Group {} requires bot admin privileges").format(chat.title))
        except telegram.error.Unauthorized as e:
            logging.error(f"群组 {chat.id} 未授权: {str(e)}")
        except Exception as e:
            logging.error(f"处理群组 {chat.id} 时发生错误: {str(e)}")
    
    session.close()
    
    if len(filter_chats) == 0:
        return update.message.reply_text(_("You are not a member of any groups where the bot is enabled.") + "\n" + 
                                _("Please ensure:\n1. Use /start to enable the bot\n2. Grant admin rights\n3. Disable privacy mode"))
    
    messages, count = search_messages(user, keywords, page, filter_chats)
    total_pages = math.ceil(count / SEARCH_PAGE_SIZE)
    
    result_text = format_search_results(messages, page, count)
    query_params = {
        'user': user,
        'keywords': keywords
    }
    
    return update.message.reply_text(
        result_text,
        parse_mode='Markdown',
        disable_web_page_preview=True,
        reply_markup=build_keyboard(page, total_pages, query_params)
    )

def handle_page_callback(update: Update, context: CallbackContext):
    """处理翻页回调"""
    query = update.callback_query
    
    if query.data == "noop":
        query.answer()
        return
        
    try:
        # 解析回调数据
        _, callback_query = query.data.split('_', 1)
        user, keywords, page = get_query_matches(callback_query)
        
        from_user_id = update.effective_user.id
        session = DBSession()
        chats = session.query(Chat)
        
        enabled_chats = [chat for chat in chats if chat.enable]
        filter_chats = []
        
        for chat in enabled_chats:
            try:
                chat_member = context.bot.get_chat_member(
                    chat_id=chat.id, user_id=from_user_id)
                if chat_member.status not in ['left', 'kicked']:
                    filter_chats.append((chat.id, chat.title))
            except (telegram.error.BadRequest, telegram.error.Unauthorized) as e:
                logging.error(f"获取群组 {chat.id} 成员信息失败: {str(e)}")
                continue
        
        session.close()
        
        if not filter_chats:
            query.answer(_("No searchable groups, please ensure the bot is properly enabled"), show_alert=True)
            return
            
        messages, count = search_messages(user, keywords, page, filter_chats)
        total_pages = math.ceil(count / SEARCH_PAGE_SIZE)
        
        if page > total_pages:
            query.answer(_("Already at the last page"), show_alert=True)
            return
            
        result_text = format_search_results(messages, page, count)
        query_params = {
            'user': user,
            'keywords': keywords
        }
        
        query.edit_message_text(
            result_text,
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=build_keyboard(page, total_pages, query_params)
        )
        
    except Exception as e:
        logging.error(f"处理翻页回调时发生错误: {str(e)}")
        query.answer(_("Error processing page request, please try again"), show_alert=True)
    
    query.answer()

# 添加新的handler
command_handler = CommandHandler('search', handle_search_command)
callback_handler = CallbackQueryHandler(handle_page_callback)

handler = InlineQueryHandler(inline_caps)
