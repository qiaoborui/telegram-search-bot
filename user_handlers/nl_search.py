import json
from datetime import datetime, date, timedelta
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from database import User, Message, Chat, DBSession
from sqlalchemy import and_, or_, func
from utils import get_filter_chats, get_text_func, auto_delete
import os
import httpx
import telegram
import math
from datetime import timezone
import pytz

_ = get_text_func()

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.siliconflow.cn/v1/chat/completions"

def parse_date_with_llm(query: str, current_time: datetime, from_user_id: int, reply_to_message=None, session=None) -> dict:
    """使用DeepSeek模型解析自然语言查询"""
    
    # 转换为本地时间显示
    local_tz = pytz.timezone('Asia/Shanghai')
    local_time = current_time.astimezone(local_tz)
    
    # 获取当前用户信息
    current_user = session.query(User).filter_by(id=from_user_id).first() if session else None
    current_user_info = ""
    if current_user:
        current_user_info = f"当前用户: {current_user.fullname}"
    
    # 获取回复消息的用户信息
    reply_user_info = ""
    if reply_to_message and hasattr(reply_to_message, 'from_user'):
        reply_user = session.query(User).filter_by(id=reply_to_message.from_user.id).first() if session else None
        if reply_user:
            reply_user_info = f"回复用户: {reply_user.fullname}"
    
    prompt = f"""当前时间是：{local_time.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)

{current_user_info}
{reply_user_info}

你是一个专门解析搜索查询的助手。请将以下自然语言搜索查询解析为JSON格式。
重要说明：
1. 所有时间必须返回北京时间（UTC+8）
2. 如果查询中包含任何时间相关信息（比如"昨天"、"上周"、"最近"等），必须在time_range中设置对应的时间范围
3. 时间范围解析规则：
   - "最近"默认解析为过去7天
   - "上周"指上一个自然周（周一到周日）
   - "上个月"指上一个自然月
   - "昨天"指前一天的0点到23:59:59
4. 用户名解析规则：
   - "我"表示当前用户
   - 在回复消息时，"他"表示被回复的用户

查询：{query}

请返回以下格式的JSON（不要包含任何其他文字）：
{{
    "keywords": [],  // 搜索关键词列表，不是必须填写，如果有才需要填写
    "time_range": {{  // 如果查询中有任何时间相关信息，必须填写
        "start": "YYYY-MM-DD HH:mm:ss",  // 开始时间（北京时间 UTC+8）
        "end": "YYYY-MM-DD HH:mm:ss"     // 结束时间（北京时间 UTC+8）
    }},
    "user": null,    // 指定的用户名，如果有
    "chat": null     // 指定的群组名，如果有
}}

"""

    try:
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "deepseek-ai/DeepSeek-V3",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
        }
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(DEEPSEEK_API_URL, json=data, headers=headers)
            response.raise_for_status()
            result = response.json()
            parsed = json.loads(result['choices'][0]['message']['content'])
            
            # 如果有时间范围，将北京时间转换为UTC时间
            if parsed.get('time_range'):
                local_tz = pytz.timezone('Asia/Shanghai')
                
                # 转换开始时间
                start_local = local_tz.localize(datetime.strptime(
                    parsed['time_range']['start'], 
                    '%Y-%m-%d %H:%M:%S'
                ))
                parsed['time_range']['start'] = start_local.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
                
                # 转换结束时间
                end_local = local_tz.localize(datetime.strptime(
                    parsed['time_range']['end'], 
                    '%Y-%m-%d %H:%M:%S'
                ))
                parsed['time_range']['end'] = end_local.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
            
            return parsed
            
    except Exception as e:
        logging.error(f"DeepSeek API调用失败: {str(e)}")
        raise

def search_messages_with_parsed_data(parsed_data: dict, filter_chats, session, page=1, page_size=25):
    """使用解析后的数据搜索消息"""
    messages = []
    start = (page - 1) * page_size
    stop = page * page_size
    
    chat_ids = [chat[0] for chat in filter_chats]
    chat_titles = [chat[1] for chat in filter_chats]
    user_ids = []

    # 首先获取用户ID列表
    if parsed_data.get('user'):
        user_query = parsed_data['user'].strip().lower()
        user_count = session.query(User).filter(
            or_(
                func.lower(User.fullname).like(f"%{user_query}%"),
                func.lower(User.username).like(f"%{user_query}%")
            )
        ).count()
        
        if user_count >= 1:
            for user in session.query(User).filter(
                or_(
                    func.lower(User.fullname).like(f"%{user_query}%"),
                    func.lower(User.username).like(f"%{user_query}%")
                )
            ).all():
                user_ids.append(user.id)
        else:
            logging.info(f"No users found matching query: {user_query}")
            return [], 0

    # 构建基本查询
    if parsed_data.get('keywords'):
        keyword_conditions = []
        for keyword in parsed_data['keywords']:
            keyword = keyword.strip().lower()
            keyword_conditions.append(func.lower(Message.text).like(f"%{keyword}%"))
        rule = and_(*keyword_conditions)
        
        if parsed_data.get('user'):
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
        if parsed_data.get('user'):
            count = session.query(Message).filter(Message.from_chat.in_(
                chat_ids)).filter(Message.from_id.in_(user_ids)).count()
            query = session.query(Message).filter(Message.from_chat.in_(
                chat_ids)).filter(Message.from_id.in_(user_ids))
        else:
            count = session.query(Message).filter(
                Message.from_chat.in_(chat_ids)).count()
            query = session.query(Message).filter(
                Message.from_chat.in_(chat_ids))

    # 添加时间范围过滤
    if parsed_data.get('time_range'):
        query = query.filter(
            Message.date >= parsed_data['time_range']['start'],
            Message.date <= parsed_data['time_range']['end']
        )
        # 重新计算总数
        count = query.count()

    # 添加群组过滤
    if parsed_data.get('chat'):
        chat_query = parsed_data['chat'].strip().lower()
        matching_chats = [chat[0] for chat in filter_chats 
                         if chat_query in chat[1].lower()]
        if matching_chats:
            query = query.filter(Message.from_chat.in_(matching_chats))
            # 重新计算总数
            count = query.count()
        else:
            return [], 0

    # 获取分页数据
    for message in query.order_by(Message.date.desc()).slice(start, stop).all():
        user = session.query(User).filter_by(id=message.from_id).one()
        chat_title = next(chat[1] for chat in filter_chats if chat[0] == message.from_chat)
        
        if message.type != 'text':
            msg_text = f'[{message.type}] {message.text if message.text else ""}'
        else:
            msg_text = message.text

        if msg_text == '':
            continue

        messages.append({
            'id': message.id,
            'link': message.link,
            'text': msg_text,
            'date': message.date,
            'user': user.fullname,
            'chat': chat_title,
            'type': message.type
        })

    logging.info(f"Retrieved {len(messages)} messages for page {page}")
    return messages, count

def build_nl_keyboard(page, total_pages, parsed_data):
    """构建翻页键盘
    parsed_data: 包含搜索参数的字典，包括 user 和 keywords
    """
    keyboard = []
    buttons = []
    
    # 构建查询参数字符串
    param_str = ''
    if parsed_data.get('user'):
        param_str += f"@{parsed_data['user']} "
    if parsed_data.get('keywords'):
        param_str += ' '.join(parsed_data['keywords']) + ' '
    
    if page > 1:
        prev_command = f"{param_str}{page-1}".strip()
        buttons.append(InlineKeyboardButton("⬅️", callback_data=f"nlpage_{prev_command}"))
    
    buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    
    if page < total_pages:
        next_command = f"{param_str}{page+1}".strip()
        buttons.append(InlineKeyboardButton("➡️", callback_data=f"nlpage_{next_command}"))
    
    keyboard.append(buttons)
    return InlineKeyboardMarkup(keyboard)

def format_parsed_data(parsed_data: dict) -> str:
    """格式化解析后的查询数据"""
    result = "*查询解析结果:*\n"
    
    if parsed_data.get('time_range'):
        # 将UTC时间转换回本地时间显示
        local_tz = pytz.timezone('Asia/Shanghai')
        
        start_utc = datetime.strptime(parsed_data['time_range']['start'], '%Y-%m-%d %H:%M:%S')
        start_utc = pytz.utc.localize(start_utc)
        start_local = start_utc.astimezone(local_tz)
        
        end_utc = datetime.strptime(parsed_data['time_range']['end'], '%Y-%m-%d %H:%M:%S')
        end_utc = pytz.utc.localize(end_utc)
        end_local = end_utc.astimezone(local_tz)
        
        result += f"📅 时间范围: {start_local.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8) 至 {end_local.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)\n"
    
    if parsed_data.get('keywords'):
        result += f"🔍 关键词: {', '.join(parsed_data['keywords'])}\n"
    else:
        result += "🔍 关键词: 无\n"
    
    if parsed_data.get('user'):
        result += f"👤 用户: {parsed_data['user']}\n"
    
    if parsed_data.get('chat'):
        result += f"💬 群组: {parsed_data['chat']}\n"
    
    return result + "\n"

@auto_delete(timeout=120)  # 设置2分钟超时
def handle_nl_search(update: Update, context: CallbackContext):
    """处理自然语言搜索命令"""
    logging.info("Received nlsearch command")
    
    if not update.message or not update.message.text:
        logging.warning("No message or text found in update")
        return None
    
    # 获取查询文本
    query = ' '.join(context.args)
    logging.info(f"Search query: {query}")
    
    if not query:
        logging.info("Empty query, sending help message")
        return update.message.reply_text(_("Please provide a search query after /nlsearch"))
    
    try:
        # 获取当前用户和群组信息
        from_user_id = update.effective_user.id
        current_chat_id = update.effective_chat.id
        logging.info(f"Processing request for user {from_user_id} in chat {current_chat_id}")
        
        # 检查是否在群组中执行命令
        if update.effective_chat.type == 'private':
            return update.message.reply_text(_("This command can only be used in groups"))
        
        session = DBSession()
        
        # 检查当前群组是否启用
        current_chat = session.query(Chat).filter_by(id=current_chat_id).first()
        if not current_chat or not current_chat.enable:
            return update.message.reply_text(_("Bot is not enabled in this group. Please use /start first."))
        
        # 检查用户在当前群组的权限
        try:
            chat_member = context.bot.get_chat_member(
                chat_id=current_chat_id, 
                user_id=from_user_id
            )
            if chat_member.status in ['left', 'kicked']:
                return update.message.reply_text(_("You must be a member of this group to search messages."))
        except telegram.error.BadRequest as e:
            logging.error(f"获取群组 {current_chat_id} 成员信息失败: {str(e)}")
            if "administrator" in str(e).lower():
                return update.message.reply_text(_("Bot requires admin privileges in this group"))
            return None
        except Exception as e:
            logging.error(f"检查用户权限时发生错误: {str(e)}")
            return update.message.reply_text(_("Failed to verify your group membership"))
        
        # 只搜索当前群组的消息
        filter_chats = [(current_chat_id, current_chat.title)]
        logging.info(f"Searching in chat: {current_chat.title}")
        
        # 使用LLM解析查询
        current_time = datetime.now()
        status_message = update.message.reply_text(_("Analyzing your query..."))
        logging.info("Calling DeepSeek API for query analysis")
        
        try:
            # 获取回复的消息（如果有）
            reply_to_message = update.message.reply_to_message
            
            parsed_data = parse_date_with_llm(
                query, 
                current_time, 
                from_user_id,
                reply_to_message,
                session
            )
            logging.info(f"Successfully parsed query: {parsed_data}")
            
            # 保存查询数据用于翻页，确保深拷贝并且所有字符串都被规范化
            saved_query = json.loads(json.dumps(parsed_data))
            if saved_query.get('user'):
                saved_query['user'] = saved_query['user'].strip()
            if saved_query.get('chat'):
                saved_query['chat'] = saved_query['chat'].strip()
            if saved_query.get('keywords'):
                saved_query['keywords'] = [k.strip() for k in saved_query['keywords']]
            
            context.user_data['last_nl_query'] = saved_query
            context.user_data['last_chat_id'] = current_chat_id
        except Exception as e:
            logging.error(f"Query parsing failed: {str(e)}", exc_info=True)
            status_message.delete()
            return update.message.reply_text(
                _("Sorry, I couldn't understand your query. Please try again with a different wording.")
            )
        
        # 执行搜索
        logging.info("Executing database search")
        messages, count = search_messages_with_parsed_data(saved_query, filter_chats, session, page=1)
        total_pages = math.ceil(count / 25)
        logging.info(f"Found {count} messages")
        
        # 使用现有的format_search_results函数格式化结果
        from .msg_search import format_search_results
        result_text = format_parsed_data(saved_query) + format_search_results(messages, 1, count)
        
        # 发送结果
        sent_message = status_message.edit_text(
            result_text,
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=build_nl_keyboard(1, total_pages, saved_query)
        )
        logging.info("Search results sent successfully")
        return sent_message
        
    except Exception as e:
        logging.error(f"Natural language search failed: {str(e)}", exc_info=True)
        if 'status_message' in locals():
            status_message.delete()
        return update.message.reply_text(
            _("An error occurred while processing your search. Please try again later.")
        )
    finally:
        if 'session' in locals():
            session.close()

def handle_nl_page_callback(update: Update, context: CallbackContext):
    """处理翻页回调"""
    query = update.callback_query
    logging.info("Processing page callback")
    
    if query.data == "noop":
        query.answer()
        return
    
    try:
        # 解析回调数据
        _, callback_query = query.data.split('_', 1)
        
        # 解析查询参数
        user = None
        keywords = []
        page = 1
        
        # 分割查询参数
        parts = callback_query.split()
        if parts:
            # 最后一个参数是页码
            if parts[-1].isdigit():
                page = int(parts[-1])
                parts = parts[:-1]
            
            # 检查是否有用户参数
            if parts and parts[0].startswith('@'):
                user = parts[0][1:]  # 去掉@前缀
                parts = parts[1:]
            
            # 剩余的都是关键词
            keywords = parts if parts else None
        
        # 获取当前用户和群组信息
        from_user_id = update.effective_user.id
        current_chat_id = update.effective_message.chat_id
        
        # 检查是否是原始搜索的群组
        original_chat_id = context.user_data.get('last_chat_id')
        if original_chat_id != current_chat_id:
            query.answer(_("Please use the search command in the original group"), show_alert=True)
            return
        
        session = DBSession()
        
        # 检查群组和用户权限
        try:
            chat_member = context.bot.get_chat_member(
                chat_id=current_chat_id, 
                user_id=from_user_id
            )
            if chat_member.status in ['left', 'kicked']:
                query.answer(_("You are no longer a member of this group"), show_alert=True)
                return
        except telegram.error.BadRequest as e:
            logging.error(f"获取群组 {current_chat_id} 成员信息失败: {str(e)}")
            query.answer(_("Failed to verify your group membership"), show_alert=True)
            return
        
        # 获取群组信息
        current_chat = session.query(Chat).filter_by(id=current_chat_id).first()
        if not current_chat or not current_chat.enable:
            query.answer(_("Bot is no longer enabled in this group"), show_alert=True)
            return
        
        # 只搜索当前群组
        filter_chats = [(current_chat_id, current_chat.title)]
        
        # 构建查询参数
        search_params = {
            'user': user,
            'keywords': keywords
        }
        
        # 从原始查询中获取时间范围和群组过滤
        last_query = context.user_data.get('last_nl_query', {})
        if last_query.get('time_range'):
            search_params['time_range'] = last_query['time_range']
        if last_query.get('chat'):
            search_params['chat'] = last_query['chat']
            
        logging.info(f"Executing search with params: {search_params}")
        messages, count = search_messages_with_parsed_data(search_params, filter_chats, session, page=page)
        
        if count == 0:
            query.answer(_("No messages found matching your criteria"), show_alert=True)
            return
            
        total_pages = math.ceil(count / 25)
        
        if page > total_pages:
            query.answer(_("Already at the last page"), show_alert=True)
            return
        
        # 格式化结果
        from .msg_search import format_search_results
        result_text = format_parsed_data(search_params) + format_search_results(messages, page, count)
        
        # 更新消息
        query.edit_message_text(
            result_text,
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=build_nl_keyboard(page, total_pages, search_params)
        )
        
    except Exception as e:
        logging.error(f"Error handling page callback: {str(e)}", exc_info=True)
        query.answer(_("Error processing page request, please try again"), show_alert=True)
    finally:
        if 'session' in locals():
            session.close()
    
    query.answer()

# 导出handlers
nl_search_handler = CommandHandler('nlsearch', handle_nl_search)
nl_page_handler = CallbackQueryHandler(handle_nl_page_callback, pattern=r'^nlpage_') 