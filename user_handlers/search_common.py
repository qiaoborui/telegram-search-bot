import json
import html
import logging
import math
import pytz
import telegram
from datetime import datetime, timedelta
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
    
    # 记录原始查询参数大小
    original_json = json.dumps(query_params)
    original_size = len(original_json)
    logging.info(f"Original query params size: {original_size} bytes")
    
    # 压缩查询参数以避免回调数据过长
    compressed_params = compress_query_params(query_params)
    
    # 将查询参数序列化为JSON字符串
    query_json = json.dumps(compressed_params)
    compressed_size = len(query_json)
    logging.info(f"Compressed query params size: {compressed_size} bytes (减少了 {original_size - compressed_size} bytes)")
    
    # 确保回调数据不超过64字节
    max_callback_length = 64
    callback_data = f"search|{search_type}|{page}|{query_json}"
    
    if len(callback_data) > max_callback_length:
        # 如果超过限制，进一步压缩
        logging.warning(f"Callback data too long: {len(callback_data)} bytes")
        compressed_params = further_compress_params(compressed_params)
        query_json = json.dumps(compressed_params)
        further_compressed_size = len(query_json)
        callback_data = f"search|{search_type}|{page}|{query_json}"
        logging.info(f"Further compressed to: {len(callback_data)} bytes (减少了 {compressed_size - further_compressed_size} bytes)")
        
        # 如果还是太长，使用最小化的回调数据
        if len(callback_data) > max_callback_length:
            # 最后的手段：只保留页码信息，丢弃查询参数
            callback_data = f"search|{search_type}|{page}|{{}}"
            logging.warning(f"Using minimal callback data: {len(callback_data)} bytes")
    
    if page > 1:
        prev_callback = f"search|{search_type}|{page-1}|{query_json}"
        if len(prev_callback) > max_callback_length:
            prev_callback = f"search|{search_type}|{page-1}|{{}}"
        
        buttons.append(InlineKeyboardButton(
            "⬅️", 
            callback_data=prev_callback
        ))
    
    buttons.append(InlineKeyboardButton(
        f"{page}/{total_pages}", 
        callback_data="noop"
    ))
    
    if page < total_pages:
        next_callback = f"search|{search_type}|{page+1}|{query_json}"
        if len(next_callback) > max_callback_length:
            next_callback = f"search|{search_type}|{page+1}|{{}}"
            
        buttons.append(InlineKeyboardButton(
            "➡️", 
            callback_data=next_callback
        ))
    
    keyboard.append(buttons)
    return InlineKeyboardMarkup(keyboard)

def compress_query_params(params):
    """压缩查询参数，移除不必要的数据"""
    compressed = {}
    
    # 复制必要的字段
    if 'keywords' in params and params['keywords']:
        # 限制关键词长度
        compressed['k'] = [k[:10] for k in params['keywords'][:3]] if params['keywords'] else None
    
    if 'time_range' in params and params['time_range']:
        # 将日期时间转换为时间戳
        time_range = params['time_range']
        compressed['t'] = {}
        
        if 'start' in time_range:
            try:
                # 解析日期时间字符串为datetime对象
                start_dt = datetime.strptime(time_range['start'], '%Y-%m-%d %H:%M:%S')
                # 转换为时间戳
                compressed['t']['s'] = int(start_dt.timestamp())
            except:
                # 解析失败时不包含此字段
                pass
                
        if 'end' in time_range:
            try:
                # 解析日期时间字符串为datetime对象
                end_dt = datetime.strptime(time_range['end'], '%Y-%m-%d %H:%M:%S')
                # 转换为时间戳
                compressed['t']['e'] = int(end_dt.timestamp())
            except:
                # 解析失败时不包含此字段
                pass
    
    if 'user' in params and params['user']:
        # 限制用户名长度
        compressed['u'] = params['user'][:10] if params['user'] else None
    
    if 'chat' in params and params['chat']:
        # 限制群组名长度
        compressed['c'] = params['chat'][:10] if params['chat'] else None
    
    return compressed

def further_compress_params(params):
    """进一步压缩参数，用于处理极端情况"""
    # 如果还是太长，只保留最基本的信息
    minimal = {}
    
    # 只保留用户名，最多3个字符
    if 'u' in params and params['u']:
        minimal['u'] = params['u'][:3]
    
    # 时间范围保留时间戳
    if 't' in params:
        minimal['t'] = {}
        if 's' in params['t']:
            minimal['t']['s'] = params['t']['s']
        if 'e' in params['t']:
            minimal['t']['e'] = params['t']['e']
    
    # 完全省略关键词和群组
    
    return minimal

def decompress_query_params(compressed_params):
    """将压缩的查询参数还原为原始格式"""
    original = {}
    
    if 'k' in compressed_params:
        original['keywords'] = compressed_params['k']
    
    if 't' in compressed_params:
        # 还原时间范围
        time_range = compressed_params['t']
        original['time_range'] = {}
        
        # 处理时间戳
        if 's' in time_range:
            try:
                # 如果是整数时间戳
                if isinstance(time_range['s'], int):
                    # 从时间戳创建datetime对象
                    start_dt = datetime.fromtimestamp(time_range['s'])
                    original['time_range']['start'] = start_dt.strftime('%Y-%m-%d %H:%M:%S')
                # 兼容旧格式 (短日期格式 MM-DD)
                elif isinstance(time_range['s'], str) and len(time_range['s']) <= 5:
                    year = datetime.now().year
                    original['time_range']['start'] = f"{year}-{time_range['s']} 00:00:00"
                # 兼容旧格式 (完整日期)
                elif isinstance(time_range['s'], str):
                    original['time_range']['start'] = f"{time_range['s']} 00:00:00"
            except:
                # 解析失败时使用默认值
                original['time_range']['start'] = "2000-01-01 00:00:00"
        
        if 'e' in time_range:
            try:
                # 如果是整数时间戳
                if isinstance(time_range['e'], int):
                    # 从时间戳创建datetime对象
                    end_dt = datetime.fromtimestamp(time_range['e'])
                    original['time_range']['end'] = end_dt.strftime('%Y-%m-%d %H:%M:%S')
                # 兼容旧格式 (短日期格式 MM-DD)
                elif isinstance(time_range['e'], str) and len(time_range['e']) <= 5:
                    year = datetime.now().year
                    original['time_range']['end'] = f"{year}-{time_range['e']} 23:59:59"
                # 兼容旧格式 (完整日期)
                elif isinstance(time_range['e'], str):
                    original['time_range']['end'] = f"{time_range['e']} 23:59:59"
            except:
                # 解析失败时使用当前时间
                original['time_range']['end'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 如果只有结束日期，设置开始日期为结束日期的前一天
        if 'end' in original['time_range'] and 'start' not in original['time_range']:
            try:
                end_dt = datetime.strptime(original['time_range']['end'], '%Y-%m-%d %H:%M:%S')
                start_dt = end_dt - timedelta(days=1)
                original['time_range']['start'] = start_dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                original['time_range']['start'] = "2000-01-01 00:00:00"
        
        # 如果只有开始日期，设置结束日期为开始日期的当天结束
        if 'start' in original['time_range'] and 'end' not in original['time_range']:
            original['time_range']['end'] = original['time_range']['start'].replace("00:00:00", "23:59:59")
    
    if 'u' in compressed_params:
        original['user'] = compressed_params['u']
    
    if 'c' in compressed_params:
        original['chat'] = compressed_params['c']
    
    return original

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
        
        # 处理空查询参数的情况
        if query_json == "{}" or not query_json:
            # 如果查询参数为空，使用用户数据中存储的最后一次查询
            if 'last_search_params' not in context.user_data:
                query.answer(safe_translate("Search parameters lost. Please search again."), show_alert=True)
                return
            query_params = context.user_data['last_search_params']
            logging.info("Using cached search parameters from user_data")
        else:
            # 正常解析查询参数
            compressed_params = json.loads(query_json)
            # 解压缩查询参数
            query_params = decompress_query_params(compressed_params)
            # 缓存查询参数以备后用
            context.user_data['last_search_params'] = query_params
            logging.info(f"Decompressed query parameters: {query_params}")
        
        # 获取当前用户ID
        from_user_id = update.effective_user.id
        current_chat_id = update.effective_message.chat_id
        
        # 检查是否是原始搜索的群组
        original_chat_id = context.user_data.get('last_chat_id')
        if original_chat_id and original_chat_id != current_chat_id:
            query.answer(safe_translate("Please use the search command in the original group"), show_alert=True)
            return
        
        # 获取可搜索的群组
        # 使用current_search_chat_id确保只搜索当前群组的消息
        search_chat_id = context.user_data.get('current_search_chat_id', original_chat_id)
        filter_chats = get_filter_chats_for_user(context, from_user_id, search_chat_id)
        
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