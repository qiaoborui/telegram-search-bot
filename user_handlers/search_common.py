import json
import html
import logging
import math
import pytz
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from database import Chat, DBSession
from utils import get_text_func, auto_delete

# Initialize translation function
_ = get_text_func()

# Helper function to safely use the translation function
def safe_translate(text):
    if callable(_):
        return _(text)
    return text

# Default search page size
SEARCH_PAGE_SIZE = 25

def build_search_keyboard(page, total_pages, search_type, query_params):
    """
    构建通用的翻页键盘
    
    Args:
        page: 当前页码
        total_pages: 总页数
        search_type: 搜索类型，'search' 或 'nlsearch'
        query_params: 包含搜索参数的字典
    
    Returns:
        InlineKeyboardMarkup: 翻页键盘
    """
    keyboard = []
    buttons = []
    
    # 将查询参数序列化为JSON字符串
    query_json = json.dumps(query_params)
    
    if page > 1:
        buttons.append(InlineKeyboardButton(
            "⬅️", 
            callback_data=f"search|{search_type}|{page-1}|{query_json}"
        ))
    
    buttons.append(InlineKeyboardButton(
        f"{page}/{total_pages}", 
        callback_data="noop"
    ))
    
    if page < total_pages:
        buttons.append(InlineKeyboardButton(
            "➡️", 
            callback_data=f"search|{search_type}|{page+1}|{query_json}"
        ))
    
    keyboard.append(buttons)
    return InlineKeyboardMarkup(keyboard)

def format_search_results(messages, page, total_count):
    """格式化搜索结果文本"""
    if not messages:
        return safe_translate("No results found")
    
    result = safe_translate("*Search Results* (Total: {})\n").format(total_count)
    
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
            user_name = msg['user'] if msg['user'] is not None else 'Unknown'
            result += f"[*{html.escape(user_name)}*: {message_text}]({msg['link']}) | {date_str}\n"
    
    return result

def get_filter_chats_for_user(context, from_user_id, current_chat_id=None):
    """
    获取用户可以搜索的群组列表
    
    Args:
        context: CallbackContext
        from_user_id: 用户ID
        current_chat_id: 当前群组ID，如果指定则只返回该群组
        
    Returns:
        list: 可搜索的群组列表，格式为 [(chat_id, chat_title), ...]
    """
    session = DBSession()
    filter_chats = []
    
    try:
        # 如果指定了当前群组，只搜索当前群组
        if current_chat_id:
            current_chat = session.query(Chat).filter_by(id=current_chat_id).first()
            if current_chat and current_chat.enable:
                try:
                    chat_member = context.bot.get_chat_member(
                        chat_id=current_chat_id, 
                        user_id=from_user_id
                    )
                    if chat_member.status not in ['left', 'kicked']:
                        filter_chats.append((current_chat_id, current_chat.title))
                except telegram.error.BadRequest as e:
                    logging.error(f"获取群组 {current_chat_id} 成员信息失败: {str(e)}")
                except Exception as e:
                    logging.error(f"验证用户群组成员资格时出错: {str(e)}")
        else:
            # 否则搜索所有启用的群组
            enabled_chats = [chat for chat in session.query(Chat).all() if chat.enable]
            
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
    finally:
        session.close()
        
    return filter_chats

@auto_delete(timeout=120, delete_command=False)  # Callback queries don't need to delete the command
def handle_search_page_callback(update: Update, context: CallbackContext):
    """
    处理通用的搜索翻页回调
    
    Args:
        update: Update
        context: CallbackContext
    """
    query = update.callback_query
    
    if query.data == "noop":
        query.answer()
        return
    
    try:
        # 解析回调数据
        parts = query.data.split('|')
        if len(parts) != 4:
            query.answer(safe_translate("Invalid callback data"), show_alert=True)
            return
            
        action, search_type, page, query_json = parts
        
        if action != "search":
            query.answer()
            return
            
        page = int(page)
        query_params = json.loads(query_json)
        
        # 获取当前用户ID
        from_user_id = update.effective_user.id
        current_chat_id = update.effective_message.chat_id
        
        # 检查是否是原始搜索的群组
        original_chat_id = context.user_data.get('last_chat_id')
        if original_chat_id and original_chat_id != current_chat_id:
            query.answer(safe_translate("Please use the search command in the original group"), show_alert=True)
            return
        
        # 获取可搜索的群组
        filter_chats = get_filter_chats_for_user(context, from_user_id, original_chat_id)
        
        if not filter_chats:
            query.answer(safe_translate("No searchable groups, please ensure the bot is properly enabled"), show_alert=True)
            return
        
        # 根据搜索类型执行不同的搜索
        if search_type == "search":
            from .msg_search import search_messages
            messages, count = search_messages(
                query_params.get('user'), 
                query_params.get('keywords'), 
                page, 
                filter_chats
            )
        elif search_type == "nlsearch":
            from .nl_search import search_messages_with_parsed_data
            messages, count = search_messages_with_parsed_data(
                query_params, 
                filter_chats, 
                DBSession(), 
                page
            )
        else:
            query.answer(safe_translate("Invalid search type"), show_alert=True)
            return
            
        if count == 0:
            query.answer(safe_translate("No messages found matching your criteria"), show_alert=True)
            return
            
        total_pages = math.ceil(count / SEARCH_PAGE_SIZE)
        
        if page > total_pages:
            query.answer(safe_translate("Already at the last page"), show_alert=True)
            return
            
        # 格式化结果
        result_text = format_search_results(messages, page, count)
        
        # 更新消息
        query.edit_message_text(
            result_text,
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=build_search_keyboard(page, total_pages, search_type, query_params)
        )
        
    except Exception as e:
        logging.error(f"Error handling page callback: {str(e)}", exc_info=True)
        query.answer(safe_translate("Error processing page request, please try again"), show_alert=True)
    
    query.answer() 