import os
import json
import logging
from flask import Flask, render_template, jsonify, request, Response
from sqlalchemy import func, desc, extract
from database import DBSession, Message, User, Chat
from datetime import datetime, timedelta
import hmac
import hashlib
from flask_cors import CORS
import urllib.parse
import requests
import re

# 配置日志
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建Flask应用
app = Flask(__name__, static_folder='static', template_folder='templates')

# 配置CORS，只允许来自Telegram的请求
CORS(app, resources={
    r"/api/*": {
        "origins": ["https://web.telegram.org", "https://*.telegram.org"],
        "methods": ["GET", "POST"],
        "allow_headers": ["Content-Type"]
    }
})

# 获取Telegram Bot Token，用于验证
BOT_TOKEN = os.environ.get('BOT_TOKEN')

def verify_telegram_data(init_data):
    """验证Telegram传递的数据"""
    if not init_data:
        logger.warning("Missing initData parameter")
        return None
    
    try:
        # 将initData转换为字典
        data_dict = {}
        for item in init_data.split('&'):
            if '=' not in item:
                continue
            key, value = item.split('=', 1)  # 只分割第一个等号
            data_dict[key] = urllib.parse.unquote(value)  # URL解码
        
        # 获取hash
        received_hash = data_dict.get('hash')
        if not received_hash:
            logger.warning("No hash found in initData")
            return None
        
        # 移除hash并按字母顺序排序数据检查字符串
        data_check_arr = []
        
        for key, value in sorted(data_dict.items()):
            if key != 'hash':
                data_check_arr.append(f"{key}={value}")
        
        data_check_string = '\n'.join(data_check_arr)
        logger.debug(f"Data check string for hash calculation: {data_check_string}")
        
        # 计算HMAC-SHA-256
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN environment variable not set")
            return None
            
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash != received_hash:
            logger.warning(f"Hash verification failed. Expected: {received_hash}, Calculated: {calculated_hash}")
            logger.debug(f"Used BOT_TOKEN: {BOT_TOKEN}")
        
        return data_dict if calculated_hash == received_hash else None
    except Exception as e:
        logger.error(f"Error verifying Telegram data: {str(e)}")
        return None

def get_chat_statistics(chat_id):
    """获取群组统计数据"""
    session = DBSession()
    try:
        # 获取群组信息
        logger.info(f"Looking for chat with ID: {chat_id}")
        chat = session.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            logger.warning(f"Chat with ID {chat_id} not found in database")
            return None
        
        logger.info(f"Found chat: {chat.title}, enabled: {chat.enable}")
        
        # 基本统计
        total_messages = session.query(func.count(Message.id)).filter(Message.from_chat == chat_id).scalar() or 0
        total_users = session.query(func.count(func.distinct(Message.from_id))).filter(Message.from_chat == chat_id).scalar() or 0
        
        logger.info(f"Basic stats: total_messages={total_messages}, total_users={total_users}")
        
        # 最近7天消息
        week_ago = datetime.now() - timedelta(days=7)
        recent_messages = session.query(func.count(Message.id)).filter(
            Message.from_chat == chat_id,
            Message.date >= week_ago
        ).scalar() or 0
        
        # 消息类型统计
        msg_types = {}
        for type_result in session.query(Message.type, func.count(Message.id)).filter(
            Message.from_chat == chat_id
        ).group_by(Message.type).all():
            msg_types[type_result[0] or 'unknown'] = type_result[1]
        
        # 活跃用户
        top_users_query = session.query(
            Message.from_id,
            func.count(Message.id).label('message_count')
        ).filter(
            Message.from_chat == chat_id
        ).group_by(Message.from_id).order_by(desc('message_count')).limit(10)
        
        top_users = []
        for user_id, count in top_users_query:
            user = session.query(User).filter(User.id == user_id).first()
            top_users.append({
                'id': user_id,
                'name': user.fullname if user else f"User {user_id}",
                'username': user.username if user else None,
                'count': count
            })
        
        # 按小时分布
        hourly_stats = {}
        for hour in range(24):
            hourly_stats[hour] = 0
            
        for hour_result in session.query(
            extract('hour', Message.date).label('hour'),
            func.count(Message.id)
        ).filter(
            Message.from_chat == chat_id
        ).group_by('hour').all():
            hourly_stats[hour_result[0]] = hour_result[1]
        
        # 按星期分布
        weekly_stats = {}
        for day in range(1, 8):  # 1-7 (周一到周日)
            weekly_stats[day] = 0
            
        for day_result in session.query(
            extract('dow', Message.date).label('day'),
            func.count(Message.id)
        ).filter(
            Message.from_chat == chat_id
        ).group_by('day').all():
            day_of_week = int(day_result[0])
            # 将星期日(0)转换为7，与前端表示一致
            if day_of_week == 0:
                day_of_week = 7
            weekly_stats[day_of_week] = day_result[1]
        
        return {
            'chat_id': chat_id,
            'chat_title': chat.title,
            'enable': chat.enable,
            'total_messages': total_messages,
            'total_users': total_users,
            'recent_messages': recent_messages,
            'message_types': msg_types,
            'top_users': top_users,
            'hourly_stats': hourly_stats,
            'weekly_stats': weekly_stats
        }
    except Exception as e:
        logger.error(f"Error getting statistics: {str(e)}")
        return None
    finally:
        session.close()

def update_chat_status(chat_id, enable):
    """更新群组启用状态"""
    session = DBSession()
    try:
        chat = session.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            return False
        
        chat.enable = enable
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Error updating chat status: {str(e)}")
        session.rollback()
        return False
    finally:
        session.close()

def extract_chat_id_from_startapp(startapp):
    """从startapp参数中提取群组ID"""
    if not startapp:
        return None
    
    logger.info(f"Trying to extract chat_id from startapp: {startapp}")
    
    # 简化逻辑：直接检查字符串是否以"chat"开头
    if startapp.startswith('chat'):
        try:
            # 直接获取"chat"后面的所有字符，并转换为整数
            chat_id_str = startapp[4:]  # 跳过前4个字符 "chat"
            chat_id = int(chat_id_str)
            logger.info(f"Extracted chat_id from startapp: {chat_id}")
            return chat_id
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to convert extracted chat_id to int: {startapp[4:]}, error: {e}")
    else:
        logger.warning(f"startapp doesn't start with 'chat': {startapp}")
    
    return None

def get_user_chats():
    """获取数据库中的所有群组"""
    session = DBSession()
    try:
        # 查询所有启用的群组
        chats = session.query(Chat).filter(Chat.enable == True).all()
        
        result = []
        for chat in chats:
            # 获取每个群组的基本信息和消息数量
            message_count = session.query(func.count(Message.id)).filter(Message.from_chat == chat.id).scalar() or 0
            
            result.append({
                'id': chat.id,
                'title': chat.title,
                'message_count': message_count
            })
        
        # 按消息数量降序排序
        result.sort(key=lambda x: x['message_count'], reverse=True)
        
        return result
    except Exception as e:
        logger.error(f"Error getting user chats: {str(e)}")
        return []
    finally:
        session.close()

@app.route('/')
def index():
    """主页面，加载Telegram Web App"""
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    """获取群组统计API"""
    # 获取并验证Telegram的initData
    init_data = request.args.get('initData')
    
    # 打印调试信息
    logger.info(f"Received request to /api/stats with initData length: {len(init_data) if init_data else 0}")
    
    data = verify_telegram_data(init_data)
    
    if not data:
        logger.warning("Authentication failed for /api/stats request")
        return jsonify({'error': 'Invalid authentication data'}), 403
    
    # 解析用户数据
    try:
        user_str = data.get('user', '{}')
        # user_str是已经URL解码过的，但Telegram在initData中嵌套编码，所以可能需要额外解码
        if user_str.startswith('%'):
            user_str = urllib.parse.unquote(user_str)
        user_data = json.loads(user_str)
        logger.info(f"User data: {user_data}")
        
        # 从startapp参数中获取群组ID
        # 首先尝试从URL参数中获取
        startapp = request.args.get('startapp')
        if not startapp:
            # 如果URL参数中没有，则从initData中获取
            startapp = data.get('start_param')
            
        # 从URL参数中直接获取群组ID（用于从选择页面跳转）
        selected_chat_id = request.args.get('chat_id')
        if selected_chat_id:
            try:
                chat_id = int(selected_chat_id)
                logger.info(f"Using chat_id from URL parameter: {chat_id}")
            except (ValueError, TypeError):
                logger.warning(f"Invalid chat_id from URL parameter: {selected_chat_id}")
                chat_id = None
        else:
            logger.info(f"Raw startapp parameter: {startapp}")
            chat_id = extract_chat_id_from_startapp(startapp)
        
        if not chat_id:
            logger.warning("No chat_id found in parameters, returning available chats")
            
            # 没有指定群组ID，返回特殊标记，前端会显示选择界面
            return jsonify({
                'no_chat_id': True,
                'message': '请从下方选择一个群组查看统计数据'
            })
        
        logger.info(f"Processed request data: user_id={user_data.get('id')}, chat_id={chat_id}")
        
        # 尝试获取群组统计数据
        try:
            stats = get_chat_statistics(chat_id)
            
            if stats:
                logger.info(f"Successfully retrieved stats for chat_id: {chat_id}")
                return jsonify(stats)
            else:
                # 检查群组是否存在
                session = DBSession()
                chat_exists = session.query(Chat).filter(Chat.id == chat_id).first() is not None
                session.close()
                
                if chat_exists:
                    logger.warning(f"Chat exists but no statistics available for chat_id: {chat_id}")
                    return jsonify({'error': '此群组未产生任何消息。请先在群组中使用机器人。'}), 404
                else:
                    logger.warning(f"Chat with ID {chat_id} does not exist in database")
                    return jsonify({'error': '此群组不存在。请确保机器人已被添加到群组并使用 /start 命令激活。'}), 404
        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            return jsonify({'error': f'获取统计数据时出错: {str(e)}'}), 500
            
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return jsonify({'error': f'处理请求时出错: {str(e)}'}), 400

@app.route('/api/toggle_status', methods=['POST'])
def toggle_status():
    """切换群组启用状态"""
    # 获取并验证Telegram的initData
    init_data = request.form.get('initData')
    
    # 打印调试信息
    logger.info(f"Received request to /api/toggle_status with initData length: {len(init_data) if init_data else 0}")
    
    data = verify_telegram_data(init_data)
    
    if not data:
        logger.warning("Authentication failed for /api/toggle_status request")
        return jsonify({'error': 'Invalid authentication data'}), 403
    
    # 解析用户数据和请求参数
    try:
        user_str = data.get('user', '{}')
        # user_str是已经URL解码过的，但Telegram在initData中嵌套编码，所以可能需要额外解码
        if user_str.startswith('%'):
            user_str = urllib.parse.unquote(user_str)
        user_data = json.loads(user_str)
        logger.info(f"User data: {user_data}")
        
        # 获取enable状态
        enable = request.form.get('enable') == 'true'
        logger.info(f"Toggle status request: enable={enable}")
        
        # 直接从表单获取chat_id
        form_chat_id = request.form.get('chat_id')
        if form_chat_id:
            try:
                chat_id = int(form_chat_id)
                logger.info(f"Using chat_id from form parameter: {chat_id}")
            except (ValueError, TypeError):
                logger.warning(f"Invalid chat_id from form parameter: {form_chat_id}")
                chat_id = None
        else:
            # 从startapp参数中获取群组ID
            # 首先尝试从表单参数中获取
            startapp = request.form.get('startapp')
            if not startapp:
                # 如果表单参数中没有，则从initData中获取
                startapp = data.get('start_param')
            
            logger.info(f"Raw startapp parameter: {startapp}")
            
            chat_id = extract_chat_id_from_startapp(startapp)
        
        if not chat_id:
            logger.warning("No chat_id found in parameters")
            return jsonify({
                'error': '无法确定群组ID。请指定一个有效的群组。',
                'details': {
                    'startapp_present': bool(startapp) if 'startapp' in locals() else False,
                    'startapp_value': startapp if 'startapp' in locals() else None,
                    'form_chat_id_present': bool(form_chat_id),
                    'form_chat_id_value': form_chat_id
                }
            }), 400
        
        logger.info(f"Processed request data: user_id={user_data.get('id')}, chat_id={chat_id}, enable={enable}")
        
        success = update_chat_status(chat_id, enable)
        
        if success:
            logger.info(f"Successfully updated chat status: chat_id={chat_id}, enable={enable}")
            return jsonify({'success': True, 'chat_id': chat_id, 'enable': enable})
        else:
            logger.warning(f"Failed to update chat status: chat_id={chat_id}, enable={enable}")
            return jsonify({'error': '更新群组状态失败。请确保机器人是群组的成员。'}), 500
            
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return jsonify({'error': '数据格式无效'}), 400

@app.route('/api/debug', methods=['GET', 'POST'])
def debug_info():
    """调试端点，用于诊断问题"""
    # 只在调试模式下启用
    if not app.debug:
        return jsonify({'error': 'Debug endpoint is only available in debug mode'}), 403
    
    # 获取并验证Telegram的initData
    if request.method == 'GET':
        init_data = request.args.get('initData')
    else:
        init_data = request.form.get('initData')
    
    # 打印调试信息
    logger.info(f"Received request to /api/debug with initData length: {len(init_data) if init_data else 0}")
    
    # 解析initData
    data_dict = {}
    if init_data:
        try:
            for item in init_data.split('&'):
                if '=' not in item:
                    continue
                key, value = item.split('=', 1)  # 只分割第一个等号
                data_dict[key] = urllib.parse.unquote(value)  # URL解码
        except Exception as e:
            logger.error(f"Error parsing initData: {str(e)}")
    
    # 获取用户信息
    user_str = data_dict.get('user', '{}')
    user_obj = None
    try:
        if isinstance(user_str, str) and user_str.startswith('%'):
            user_str = urllib.parse.unquote(user_str)
        user_obj = json.loads(user_str)
    except Exception as e:
        logger.error(f"Error parsing user data: {str(e)}")
    
    # 获取startapp参数
    startapp = data_dict.get('start_param')
    chat_id = extract_chat_id_from_startapp(startapp)
    
    # 尝试不同的格式解析startapp
    alternative_chat_id = None
    if startapp and not chat_id:
        # 尝试直接解析为整数
        try:
            alternative_chat_id = int(startapp)
        except ValueError:
            pass
        
        # 尝试其他可能的格式
        if not alternative_chat_id and startapp.startswith('chat'):
            try:
                # 尝试从任何位置提取数字
                match = re.search(r'chat[-_]?(-?\d+)', startapp)
                if match:
                    alternative_chat_id = int(match.group(1))
            except Exception as e:
                logger.error(f"Error extracting alternative chat_id: {str(e)}")
    
    # 返回调试信息
    debug_info = {
        'raw_init_data': init_data,
        'parsed_data': data_dict,
        'user': user_obj,
        'start_param': startapp,
        'extracted_chat_id': chat_id,
        'alternative_chat_id': alternative_chat_id,
        'startapp_analysis': {
            'raw': startapp,
            'starts_with_chat_': startapp.startswith('chat_') if startapp else False,
            'starts_with_chat-': startapp.startswith('chat-') if startapp else False,
            'starts_with_chat': startapp.startswith('chat') if startapp else False,
            'length': len(startapp) if startapp else 0
        },
        'auth_date': data_dict.get('auth_date'),
        'hash': data_dict.get('hash'),
        'bot_token_available': bool(BOT_TOKEN),
        'request_method': request.method,
        'request_headers': dict(request.headers),
        'request_args': dict(request.args),
        'request_form': dict(request.form) if request.method == 'POST' else None
    }
    
    return jsonify(debug_info)

@app.route('/api/chats')
def list_chats():
    """获取用户可访问的群组列表"""
    # 获取并验证Telegram的initData
    init_data = request.args.get('initData')
    
    logger.info(f"Received request to /api/chats with initData length: {len(init_data) if init_data else 0}")
    
    data = verify_telegram_data(init_data)
    
    if not data:
        logger.warning("Authentication failed for /api/chats request")
        return jsonify({'error': 'Invalid authentication data'}), 403
    
    # 解析用户数据
    try:
        user_str = data.get('user', '{}')
        # user_str是已经URL解码过的，但Telegram在initData中嵌套编码，所以可能需要额外解码
        if user_str.startswith('%'):
            user_str = urllib.parse.unquote(user_str)
        user_data = json.loads(user_str)
        logger.info(f"User data: {user_data}")
        
        # 获取所有可访问的群组
        chats = get_user_chats()
        
        return jsonify(chats)
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return jsonify({'error': f'处理请求时出错: {str(e)}'}), 400

@app.route('/api/messages/<int:chat_id>')
def get_messages(chat_id):
    """获取群组消息"""
    session = DBSession()
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        # 获取消息列表
        messages = session.query(Message).filter(
            Message.from_chat == chat_id
        ).order_by(
            Message.date.desc()
        ).offset((page - 1) * per_page).limit(per_page).all()
        
        # 获取总消息数
        total_messages = session.query(func.count(Message.id)).filter(
            Message.from_chat == chat_id
        ).scalar()
        
        # 格式化消息
        result = []
        for msg in messages:
            user = session.query(User).filter(User.id == msg.from_id).first()
            result.append({
                'id': msg.id,
                'text': msg.text,
                'type': msg.type,
                'date': msg.date.isoformat(),
                'from_user': {
                    'id': user.id if user else None,
                    'name': user.fullname if user else 'Unknown',
                    'username': user.username if user else None
                }
            })
        
        return jsonify({
            'messages': result,
            'total': total_messages,
            'page': page,
            'per_page': per_page
        })
    except Exception as e:
        logger.error(f"Error getting messages: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/api/send_message', methods=['POST'])
def send_message():
    """发送消息到群组"""
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        text = data.get('text')
        
        if not chat_id or not text:
            return jsonify({'error': 'Missing chat_id or text'}), 400
            
        # 使用 Bot API 发送消息
        api_url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
        response = requests.post(api_url, json={
            'chat_id': chat_id,
            'text': text
        })
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'Message sent successfully'})
        else:
            return jsonify({'error': f'Failed to send message: {response.text}'}), 500
            
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/messages')
def messages():
    """渲染消息页面"""
    return render_template('messages.html')

if __name__ == '__main__':
    # 创建必要的目录
    os.makedirs('static', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # 获取端口号，默认为8080
    port = int(os.environ.get('PORT', 8080))
    
    # 是否开启调试模式
    debug_mode = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'
    if debug_mode:
        logger.setLevel(logging.DEBUG)
        app.debug = True
        logger.debug("Debug mode enabled")
    
    # 启动Flask应用
    app.run(host='0.0.0.0', port=port) 