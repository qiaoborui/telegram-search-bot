import logging
import matplotlib.pyplot as plt
import numpy as np
import io
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from utils import get_statistics_data, get_text_func, auto_delete
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端

# 设置中文字体支持
try:
    # 尝试多种可能的中文字体
    font_list = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'PingFang SC', 'Heiti SC', 'Source Han Sans CN', 'Noto Sans CJK SC', 'Noto Sans SC']
    for font in font_list:
        try:
            plt.rcParams['font.sans-serif'] = [font] + plt.rcParams['font.sans-serif']
            # 测试字体是否可用
            fig, ax = plt.subplots()
            ax.set_title('测试')
            plt.close(fig)
            logging.info(f"成功使用字体: {font}")
            break
        except:
            continue
    
    plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号
except Exception as e:
    logging.warning(f"无法设置中文字体，图表中的中文可能无法正确显示: {str(e)}")
    # 使用不依赖字体的替代方案
    plt.rcParams['font.family'] = 'sans-serif'

# 初始化翻译函数
_ = get_text_func()

# 安全使用翻译函数的辅助函数
def safe_translate(text):
    if callable(_):
        return _(text)
    return text

# 回调数据前缀
STATS_CALLBACK_PREFIX = "stats_"

# 统计类型
STATS_TYPES = {
    "overview": "总览",
    "msg_types": "消息类型",
    "top_users": "活跃用户",
    "top_chats": "活跃群组",
    "time_patterns": "时间模式",
    "msg_length": "消息长度"
}

def generate_overview_chart(stats):
    """生成总览统计图表"""
    # 创建图表
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # 准备数据
    if 'chat_title' in stats:
        # 群组特定统计
        title = f"群组 '{stats['chat_title']}' 数据总览"
    else:
        # 全局统计
        title = 'Telegram 机器人数据总览'
    
    labels = ['总消息数', '总用户数', '最近7天消息']
    values = [
        stats['total_messages'],
        stats['total_users'],
        stats['recent_messages']
    ]
    
    # 如果是全局统计，添加群组数量
    if 'chat_title' not in stats:
        labels.append('总群组数')
        values.append(stats['total_chats'])
    
    # 创建柱状图
    colors = ['#3498db', '#2ecc71', '#f39c12']
    if len(labels) > 3:
        colors.append('#e74c3c')
    
    bars = ax.bar(labels, values, color=colors)
    
    # 添加数值标签
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                f'{int(height):,}', ha='center', va='bottom')
    
    # 设置标题和标签
    ax.set_title(title, fontsize=16)
    ax.set_ylabel('数量')
    
    # 保存到内存
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close(fig)
    
    return buf

def generate_message_types_chart(stats):
    """生成消息类型分布图表"""
    # 创建图表
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # 准备数据
    msg_types = stats['message_types']
    labels = list(msg_types.keys())
    values = list(msg_types.values())
    
    # 创建饼图
    wedges, texts, autotexts = ax.pie(
        values, 
        labels=labels, 
        autopct='%1.1f%%',
        textprops={'fontsize': 12},
        colors=plt.cm.Paired(np.linspace(0, 1, len(labels)))
    )
    
    # 设置标题
    ax.set_title('消息类型分布', fontsize=16)
    
    # 保存到内存
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close(fig)
    
    return buf

def generate_top_users_chart(stats):
    """生成活跃用户图表"""
    # 创建图表
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # 准备数据
    top_users = stats['top_users']
    names = [user['name'] for user in top_users]
    counts = [user['count'] for user in top_users]
    
    # 创建水平条形图
    bars = ax.barh(names, counts, color=plt.cm.viridis(np.linspace(0, 0.8, len(names))))
    
    # 添加数值标签
    for i, bar in enumerate(bars):
        width = bar.get_width()
        ax.text(width + 3, bar.get_y() + bar.get_height()/2, f'{int(width):,}',
                ha='left', va='center')
    
    # 设置标题和标签
    ax.set_title('最活跃的用户 (Top 10)', fontsize=16)
    ax.set_xlabel('消息数量')
    
    # 反转y轴，使最活跃的用户显示在顶部
    ax.invert_yaxis()
    
    # 保存到内存
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close(fig)
    
    return buf

def generate_top_chats_chart(stats):
    """生成活跃群组图表"""
    # 创建图表
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # 准备数据
    top_chats = stats['top_chats']
    names = [chat['name'] for chat in top_chats]
    counts = [chat['count'] for chat in top_chats]
    
    # 创建水平条形图
    bars = ax.barh(names, counts, color=plt.cm.cool(np.linspace(0, 0.8, len(names))))
    
    # 添加数值标签
    for i, bar in enumerate(bars):
        width = bar.get_width()
        ax.text(width + 3, bar.get_y() + bar.get_height()/2, f'{int(width):,}',
                ha='left', va='center')
    
    # 设置标题和标签
    ax.set_title('最活跃的群组 (Top 10)', fontsize=16)
    ax.set_xlabel('消息数量')
    
    # 反转y轴，使最活跃的群组显示在顶部
    ax.invert_yaxis()
    
    # 保存到内存
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close(fig)
    
    return buf

def generate_time_patterns_chart(stats):
    """生成时间模式图表"""
    # 创建图表
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    # 准备小时数据
    hour_data = stats['hour_distribution']
    hours = list(range(24))
    hour_counts = [hour_data.get(h, 0) for h in hours]
    
    # 创建小时柱状图
    ax1.bar(hours, hour_counts, color='#3498db')
    ax1.set_title('按小时分布', fontsize=14)
    ax1.set_xlabel('小时 (24小时制)')
    ax1.set_ylabel('消息数量')
    ax1.set_xticks(range(0, 24, 2))
    
    # 准备星期数据
    weekday_data = stats['weekday_distribution']
    weekdays = list(range(7))
    weekday_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    weekday_counts = [weekday_data.get(w, 0) for w in weekdays]
    
    # 创建星期柱状图
    ax2.bar(weekday_names, weekday_counts, color='#2ecc71')
    ax2.set_title('按星期分布', fontsize=14)
    ax2.set_xlabel('星期')
    ax2.set_ylabel('消息数量')
    
    # 保存到内存
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close(fig)
    
    return buf

def generate_message_length_chart(stats):
    """生成消息长度分布图表"""
    # 创建图表
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # 准备数据
    length_data = stats['message_length']
    labels = list(length_data.keys())
    values = list(length_data.values())
    
    # 创建柱状图
    bars = ax.bar(labels, values, color=plt.cm.plasma(np.linspace(0, 0.8, len(labels))))
    
    # 添加数值标签
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                f'{int(height):,}', ha='center', va='bottom')
    
    # 设置标题和标签
    ax.set_title('消息长度分布', fontsize=16)
    ax.set_xlabel('字符数范围')
    ax.set_ylabel('消息数量')
    
    # 保存到内存
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close(fig)
    
    return buf

def build_stats_keyboard():
    """构建统计类型选择键盘"""
    keyboard = []
    row = []
    
    for key, label in STATS_TYPES.items():
        if len(row) == 3:  # 每行最多3个按钮
            keyboard.append(row)
            row = []
        
        row.append(InlineKeyboardButton(
            label, callback_data=f"{STATS_CALLBACK_PREFIX}{key}"
        ))
    
    if row:  # 添加最后一行
        keyboard.append(row)
    
    return InlineKeyboardMarkup(keyboard)

@auto_delete(timeout=300)  # 设置5分钟超时
def handle_stats_command(update: Update, context: CallbackContext):
    """处理 /stats 命令"""
    # 检查是否在群组中
    chat_id = update.effective_chat.id
    is_group = chat_id < 0  # 群组ID为负数
    
    # 存储聊天ID以便后续使用
    context.user_data['stats_chat_id'] = chat_id if is_group else None
    
    # 准备消息文本
    if is_group:
        message_text = f"📊 *{update.effective_chat.title} 数据统计*\n\n请选择要查看的统计类型："
    else:
        message_text = "📊 *Telegram 数据统计*\n\n请选择要查看的统计类型："
    
    # 发送初始消息
    message = update.message.reply_text(
        message_text,
        parse_mode='Markdown',
        reply_markup=build_stats_keyboard()
    )
    
    # 存储消息ID以便后续更新
    context.user_data['stats_message_id'] = message.message_id

def handle_stats_callback(update: Update, context: CallbackContext):
    """处理统计回调查询"""
    query = update.callback_query
    query.answer()
    
    # 获取选择的统计类型
    callback_data = query.data
    if not callback_data.startswith(STATS_CALLBACK_PREFIX):
        return
    
    stats_type = callback_data[len(STATS_CALLBACK_PREFIX):]
    
    # 获取聊天ID（如果在群组中）
    chat_id = context.user_data.get('stats_chat_id')
    
    # 获取统计数据
    stats = get_statistics_data(chat_id)
    
    # 根据选择的类型生成相应的图表
    if stats_type == "overview":
        chart_buf = generate_overview_chart(stats)
        if chat_id:
            caption = f"📊 群组 '{stats.get('chat_title', '当前群组')}' 数据总览"
        else:
            caption = "📊 Telegram 机器人数据总览"
    elif stats_type == "msg_types":
        chart_buf = generate_message_types_chart(stats)
        caption = "📊 消息类型分布"
    elif stats_type == "top_users":
        chart_buf = generate_top_users_chart(stats)
        caption = "📊 最活跃的用户 (Top 10)"
    elif stats_type == "top_chats":
        # 如果是群组特定统计且没有群组数据，则显示提示
        if chat_id and not stats['top_chats']:
            query.edit_message_text("此统计类型仅在全局统计中可用。请在私聊中使用 /stats 命令查看所有群组的统计数据。")
            return
        chart_buf = generate_top_chats_chart(stats)
        caption = "📊 最活跃的群组 (Top 10)"
    elif stats_type == "time_patterns":
        chart_buf = generate_time_patterns_chart(stats)
        caption = "📊 消息时间模式分析"
    elif stats_type == "msg_length":
        chart_buf = generate_message_length_chart(stats)
        caption = "📊 消息长度分布"
    else:
        query.edit_message_text("❌ 未知的统计类型")
        return
    
    # 如果是群组特定统计，在标题中添加群组名称
    if chat_id and stats_type != "overview" and 'chat_title' in stats:
        caption = f"{caption} - {stats['chat_title']}"
    
    # 发送图表
    query.message.reply_photo(
        photo=chart_buf,
        caption=caption,
        reply_markup=build_stats_keyboard()
    )

# 命令处理器
handler = CommandHandler('stats', handle_stats_command)
callback_handler = CallbackQueryHandler(handle_stats_callback, pattern=f"^{STATS_CALLBACK_PREFIX}") 