import os
import json
import psycopg2
from datetime import datetime
import sys
from concurrent.futures import ThreadPoolExecutor
from psycopg2 import pool
from queue import Queue
import threading

# 获取数据库连接配置
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/telegram_bot')

# 设置线程池大小和批处理大小
MAX_WORKERS = 32  # 增加工作线程数
BATCH_SIZE = 1000  # 增加批处理大小以减少数据库交互次数

# 创建数据库连接池
class DatabasePool:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabasePool, cls).__new__(cls)
                cls._instance.init_pool()
            return cls._instance
    
    def init_pool(self):
        conn_params = parse_database_url(DATABASE_URL)
        self.pool = pool.ThreadedConnectionPool(
            minconn=4,  # 增加最小连接数
            maxconn=MAX_WORKERS * 2,  # 增加最大连接数
            **conn_params
        )
    
    def get_conn(self):
        return self.pool.getconn()
    
    def put_conn(self, conn):
        self.pool.putconn(conn)

def parse_database_url(url):
    """解析数据库URL为连接参数"""
    url = url.replace('postgresql://', '')
    auth, rest = url.split('@') if '@' in url else ('', url)
    username, password = auth.split(':') if ':' in auth else ('', '')
    host_port, dbname = rest.split('/') if '/' in rest else (rest, '')
    host, port = host_port.split(':') if ':' in host_port else (host_port, '5432')
    
    return {
        'dbname': dbname,
        'user': username,
        'password': password,
        'host': host,
        'port': port
    }

def create_tables(conn):
    """创建必要的数据表和索引"""
    with conn.cursor() as cur:
        # 创建message表
        cur.execute("""
        CREATE TABLE IF NOT EXISTS message (
            _id SERIAL PRIMARY KEY,
            id BIGINT,
            link TEXT,
            type TEXT,
            category TEXT,
            text TEXT,
            video TEXT,
            photo TEXT,
            audio TEXT,
            voice TEXT,
            date TIMESTAMP,
            from_id BIGINT,
            from_chat BIGINT
        )
        """)
        
        # 添加唯一索引以防止重复消息
        cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_message_unique 
        ON message (from_chat, id)
        """)
        
        # 创建user表
        cur.execute("""
        CREATE TABLE IF NOT EXISTS "user" (
            id BIGINT PRIMARY KEY,
            fullname TEXT,
            username TEXT
        )
        """)
        
        # 创建chat表
        cur.execute("""
        CREATE TABLE IF NOT EXISTS chat (
            id BIGINT PRIMARY KEY,
            title TEXT,
            enable BOOLEAN
        )
        """)
        
        # 创建user_alias表
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_alias (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            alias TEXT,
            created_by BIGINT,
            created_at TIMESTAMP
        )
        """)
        
        conn.commit()

def strip_user_id(id_):
    """处理用户ID格式"""
    id_str = str(id_)
    if id_str.startswith('user'):
        return int(id_str[4:])
    return int(id_str)

def insert_chat(cur, chat_id, title):
    """插入群组信息"""
    cur.execute("""
    INSERT INTO chat (id, title, enable)
    VALUES (%s, %s, %s)
    ON CONFLICT (id) DO NOTHING
    """, (chat_id, title, False))

def insert_user(cur, user_id, fullname, username):
    """插入用户信息"""
    cur.execute("""
    INSERT INTO "user" (id, fullname, username)
    VALUES (%s, %s, %s)
    ON CONFLICT (id) DO NOTHING
    """, (user_id, fullname, username))

def process_message_batch(messages, chat_id, progress_queue):
    """处理一批消息"""
    db_pool = DatabasePool()
    conn = db_pool.get_conn()
    success_count = 0
    fail_count = 0
    fail_messages = []
    
    try:
        with conn.cursor() as cur:
            batch_messages = []
            for message in messages:
                try:
                    if 'from_id' not in message or 'user' not in message['from_id']:
                        continue

                    # 插入用户信息
                    from_id = strip_user_id(message['from_id'])
                    insert_user(cur, from_id, message.get('from', ''), message.get('from', ''))
                    
                    # 处理消息文本
                    if isinstance(message.get('text'), list):
                        msg_text = ''.join([
                            obj['text'] if isinstance(obj, dict) else obj
                            for obj in message['text']
                        ])
                    else:
                        msg_text = message.get('text', '')
                    
                    if not msg_text:
                        msg_text = '[other msg]'
                    
                    # 处理消息日期
                    message_date = datetime.strptime(message['date'], '%Y-%m-%dT%H:%M:%S')
                    
                    # 构建消息链接
                    link_chat_id = str(chat_id)[4:]
                    message_link = f'https://t.me/c/{link_chat_id}/{message["id"]}'
                    
                    # 将消息添加到批处理列表
                    batch_messages.append((
                        message['id'], message_link, msg_text, '', '', '', '', 'text', '',
                        from_id, chat_id, message_date
                    ))
                    
                    # 当达到批处理大小时执行批量插入
                    if len(batch_messages) >= BATCH_SIZE:
                        cur.executemany("""
                        INSERT INTO message (id, link, text, video, photo, audio, voice, type, category, from_id, from_chat, date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (from_chat, id) DO NOTHING
                        """, batch_messages)
                        
                        conn.commit()
                        success_count += len(batch_messages)
                        progress_queue.put(len(batch_messages))
                        batch_messages = []
                    
                except Exception as e:
                    fail_count += 1
                    fail_messages.append(str(message))
            
            # 处理剩余的消息
            if batch_messages:
                try:
                    cur.executemany("""
                    INSERT INTO message (id, link, text, video, photo, audio, voice, type, category, from_id, from_chat, date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (from_chat, id) DO NOTHING
                    """, batch_messages)
                    
                    conn.commit()
                    success_count += len(batch_messages)
                    progress_queue.put(len(batch_messages))
                except Exception as batch_error:
                    fail_count += len(batch_messages)
                    for msg in batch_messages:
                        fail_messages.append(str(msg))
    
    finally:
        db_pool.put_conn(conn)
    
    return success_count, fail_count, fail_messages

def process_json_file(file_path, conn):
    """处理JSON文件并导入数据"""
    print("开始读取JSON文件...")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 验证是否为超级群组
    if 'type' not in data:
        print("错误：只支持导入超级群组的历史记录！")
        return
    
    # 获取群组信息
    group_name = data.get('name')
    group_id = data.get('id')
    if not group_name or not group_id:
        print("错误：无法获取群组信息！")
        return
    
    # 处理群组ID格式
    edited_id = int(group_id) if str(group_id).startswith('-100') else int(f'-100{group_id}')
    
    # 获取有效消息
    valid_messages = [msg for msg in data.get('messages', []) 
                     if 'from_id' in msg and 'user' in msg['from_id']]
    total_messages = len(valid_messages)
    print(f"\n总消息数量: {total_messages}")
    
    # 插入群组信息
    with conn.cursor() as cur:
        print(f"正在导入群组 {group_name} (ID: {edited_id})...")
        insert_chat(cur, edited_id, group_name)
        conn.commit()
    
    # 创建进度队列和计数器
    progress_queue = Queue()
    processed_count = 0
    
    # 将消息分成多个批次
    chunk_size = (total_messages + MAX_WORKERS - 1) // MAX_WORKERS
    message_chunks = [valid_messages[i:i + chunk_size] 
                     for i in range(0, total_messages, chunk_size)]
    
    # 使用线程池并发处理消息
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_message_batch, chunk, edited_id, progress_queue) 
                  for chunk in message_chunks]
        
        # 显示实时进度
        while processed_count < total_messages:
            batch_count = progress_queue.get()
            processed_count += batch_count
            progress = (processed_count / total_messages) * 100
            print(f"\r导入进度: {progress:.1f}% ({processed_count}/{total_messages})", 
                  end='', flush=True)
        
        # 收集所有结果
        for future in futures:
            success, fail, messages = future.result()
            results.append((success, fail, messages))
    
    # 汇总结果
    total_success = sum(r[0] for r in results)
    total_fail = sum(r[1] for r in results)
    all_fail_messages = [msg for r in results for msg in r[2]]
    
    print(f"\n导入结果:\n")
    print(f"群组: {group_name} ({group_id})")
    print(f"成功: {total_success}")
    print(f"失败: {total_fail}")
    if all_fail_messages:
        print("\n失败的消息:")
        for msg in all_fail_messages:
            print(f"\t{msg}")

def main():
    if len(sys.argv) != 2:
        print("使用方法: python import_to_pg.py <json_file_path>")
        return
    
    json_file = sys.argv[1]
    if not os.path.exists(json_file):
        print(f"错误：文件 {json_file} 不存在！")
        return
    
    try:
        # 连接数据库
        conn_params = parse_database_url(DATABASE_URL)
        print("正在连接数据库...")
        conn = psycopg2.connect(**conn_params)
        
        # 创建表和索引
        print("正在检查并创建数据表...")
        create_tables(conn)
        
        # 处理JSON文件
        process_json_file(json_file, conn)
        
        conn.close()
        print("\n导入完成！")
        
    except Exception as e:
        print(f"错误：{str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()