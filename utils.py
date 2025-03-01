import re
import functools
import gettext
import time
import json
import os
from threading import Thread
from datetime import datetime, timedelta
from sqlalchemy import func
from database import DBSession, Message, User, Chat

CONFIG_FILE = './config/.config.json'

USERBOT_CHAT_MEMBERS_FILE = '.userbot_chat_members'
USERBOT_ADMIN_FILE = '.userbot_admin'

# Default timeout in seconds for auto-delete messages
DEFAULT_DELETE_TIMEOUT = int(os.getenv('DELETE_TIMEOUT', '60'))

def get_text_func():
    """Initialize and return the translation function.
    This function ensures proper initialization of gettext and returns a translation function
    that will always work, even if translation files are not found."""
    try:
        gettext.bindtextdomain('bot', 'locale')
        gettext.textdomain('bot')
        return gettext.gettext
    except Exception as e:
        import logging
        logging.error(f"Failed to initialize translations: {str(e)}")
        # Return a fallback function that just returns the input string
        return lambda x: x

# Initialize the translation function once at module level
_ = get_text_func()

def delay_delete(bot, chat_id, message_id, timeout=None):
    if timeout is None:
        timeout = DEFAULT_DELETE_TIMEOUT
    time.sleep(timeout)
    try:
        bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass  # Ignore any errors when trying to delete message


def auto_delete(fn=None, *, timeout=None, delete_command=True):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            update = args[0]
            bot = args[1].bot
            
            # Store the user's command message ID if it exists
            user_message_id = None
            user_chat_id = None
            if delete_command and hasattr(update, 'message') and update.message:
                user_message_id = update.message.message_id
                user_chat_id = update.message.chat_id
            
            # Execute the original function
            sent_message = func(*args, **kw)
            
            # Delete the bot's response message
            if sent_message:
                Thread(target=delay_delete, args=[bot, sent_message.chat_id, sent_message.message_id, timeout]).start()
                
                # Also delete the user's command message if available
                if user_message_id and user_chat_id:
                    Thread(target=delay_delete, args=[bot, user_chat_id, user_message_id, timeout]).start()
                    
            return sent_message
        return wrapper
    
    if fn is None:
        return decorator
    return decorator(fn)


def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


# calculate num of non-ascii characters
def len_non_ascii(data):
    temp = re.findall('[^a-zA-Z0-9.]+', data)
    count = 0
    for i in temp:
        count += len(i)
    return count


def get_bot_user_name(bot):
    return bot.get_me().username


def get_bot_id(bot):
    return bot.get_me().id


def read_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    f = open(CONFIG_FILE)
    config_dict = json.load(f)
    f.close()
    return config_dict


def check_control_permission(from_user_id):
    try:
        config = read_config()
        if config['enable']:
            if from_user_id in config['group_admins']:
                return True
            else:
                return False
        else:
            return None
    except:
        return None


def load_chat_members():
    if not os.path.exists(USERBOT_CHAT_MEMBERS_FILE):
        with open(USERBOT_CHAT_MEMBERS_FILE, 'w') as f:
            json.dump({}, f)

    with open(USERBOT_CHAT_MEMBERS_FILE, 'r') as f:
        chat_members = json.load(f)
    return chat_members


def write_chat_members(chat_members):
    with open(USERBOT_CHAT_MEMBERS_FILE, 'w') as f:
        json.dump(chat_members, f)


def get_filter_chats(user_id):
    filter_chats = []
    chat_members = load_chat_members()
    for chat_id in chat_members:
        if user_id in chat_members[chat_id]['members']:
            filter_chats.append((int(chat_id),chat_members[chat_id]['title']))
    return filter_chats


def is_userbot_mode():
    return False


def update_userbot_admin_id(user_id):
    current_id = -1
    if os.path.exists(USERBOT_ADMIN_FILE):
        with open(USERBOT_ADMIN_FILE) as f:
            current_id = int(f.read().strip())

    if current_id != user_id:
        with open(USERBOT_ADMIN_FILE, 'w') as f:
            f.write(str(user_id))


def read_userbot_admin_id():
    with open(USERBOT_ADMIN_FILE) as f:
        current_id = int(f.read().strip())
    return current_id


def get_statistics_data(chat_id=None):
    """获取统计数据，用于生成统计报告
    
    Args:
        chat_id: 如果提供，则只统计该群组的数据
    """
    session = DBSession()
    stats = {}
    
    # 基础查询 - 根据chat_id过滤
    base_query = session.query(Message)
    if chat_id:
        base_query = base_query.filter(Message.from_chat == chat_id)
    
    # 1. 消息类型分布
    msg_types = base_query.with_entities(Message.type, func.count(Message.id)).group_by(Message.type).all()
    stats['message_types'] = {t[0]: t[1] for t in msg_types}
    
    # 2. 用户活跃度 - 发送消息最多的前10名用户
    top_users = base_query.with_entities(Message.from_id, func.count(Message.id).label('count')) \
                       .group_by(Message.from_id) \
                       .order_by(func.count(Message.id).desc()) \
                       .limit(10).all()
    
    user_ids = [u[0] for u in top_users]
    users = session.query(User).filter(User.id.in_(user_ids)).all()
    user_map = {u.id: u.fullname or u.username or str(u.id) for u in users}
    
    stats['top_users'] = [{'id': u[0], 'name': user_map.get(u[0], str(u[0])), 'count': u[1]} for u in top_users]
    
    # 3. 聊天群组活跃度 - 只在全局统计时显示
    if not chat_id:
        top_chats = session.query(Message.from_chat, func.count(Message.id).label('count')) \
                        .group_by(Message.from_chat) \
                        .order_by(func.count(Message.id).desc()) \
                        .limit(10).all()
        
        chat_ids = [c[0] for c in top_chats]
        chats = session.query(Chat).filter(Chat.id.in_(chat_ids)).all()
        chat_map = {c.id: c.title or str(c.id) for c in chats}
        
        stats['top_chats'] = [{'id': c[0], 'name': chat_map.get(c[0], str(c[0])), 'count': c[1]} for c in top_chats]
    else:
        # 如果是特定群组，则不需要显示群组活跃度
        stats['top_chats'] = []
    
    # 4. 时间模式分析
    # 按小时统计
    hour_stats = base_query.with_entities(func.extract('hour', Message.date).label('hour'), 
                              func.count(Message.id).label('count')) \
                       .group_by('hour') \
                       .order_by('hour').all()
    stats['hour_distribution'] = {int(h[0]): h[1] for h in hour_stats}
    
    # 按星期几统计
    weekday_stats = base_query.with_entities(func.extract('dow', Message.date).label('weekday'), 
                                 func.count(Message.id).label('count')) \
                          .group_by('weekday') \
                          .order_by('weekday').all()
    stats['weekday_distribution'] = {int(w[0]): w[1] for w in weekday_stats}
    
    # 按月份统计
    month_stats = base_query.with_entities(func.extract('month', Message.date).label('month'), 
                               func.count(Message.id).label('count')) \
                        .group_by('month') \
                        .order_by('month').all()
    stats['month_distribution'] = {int(m[0]): m[1] for m in month_stats}
    
    # 5. 消息长度分布
    # 创建长度范围分类
    length_ranges = [
        (0, 10, '0-10'),
        (11, 50, '11-50'),
        (51, 100, '51-100'),
        (101, 200, '101-200'),
        (201, 500, '201-500'),
        (501, float('inf'), '500+')
    ]
    
    length_stats = {}
    for start, end, label in length_ranges:
        query = base_query
        if end == float('inf'):
            count = query.filter(func.length(Message.text) > start).count()
        else:
            count = query.filter(func.length(Message.text) >= start) \
                        .filter(func.length(Message.text) <= end).count()
        length_stats[label] = count
    
    stats['message_length'] = length_stats
    
    # 6. 总体统计
    stats['total_messages'] = base_query.count()
    
    if chat_id:
        # 如果是特定群组，只统计该群组的用户数
        stats['total_users'] = base_query.with_entities(Message.from_id).distinct().count()
        stats['total_chats'] = 1  # 只有一个群组
        
        # 获取群组名称
        chat = session.query(Chat).filter(Chat.id == chat_id).first()
        stats['chat_title'] = chat.title if chat else str(chat_id)
    else:
        # 全局统计
        stats['total_users'] = session.query(func.count(User.id)).scalar()
        stats['total_chats'] = session.query(func.count(Chat.id)).scalar()
    
    # 7. 最近活跃度
    recent_days = 7
    recent_date = datetime.now() - timedelta(days=recent_days)
    stats['recent_messages'] = base_query.filter(Message.date >= recent_date).count()
    
    session.close()
    return stats