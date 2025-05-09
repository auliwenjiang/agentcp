# Copyright 2025 AgentUnion Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import sqlite3
import hashlib
import os
class DBManager:
    
    def __init__(self,aid_path,aid):
        db_path = os.path.join(aid_path,"data")
        os.path.exists(db_path) or os.makedirs(db_path)
        db_file_path = os.path.join(db_path, "agentid_data.db")
        
        self.conn = sqlite3.connect(db_file_path, check_same_thread=False)
        self.aid = aid
        self.create_table(self.aid)
            
    def add_friend_agent(self,aid,friend_aid,name,avaUrl,description):
        try:
            aid_md5 = hashlib.md5(aid.encode('utf-8')).hexdigest()
            friend_table = f"friend_{aid_md5}"
            # 修改为使用动态生成的friend_table表名
            cursor = self.conn.cursor()
            cursor.execute(f'''INSERT INTO {friend_table} (aid, name, avaurl, description) VALUES (?, ?, ?, ?)''', 
                              (friend_aid, name, avaUrl, description))
            self.conn.commit()
            result = cursor.rowcount > 0
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"add_friend_agent数据库操作失败: {str(e)}")
            return False

    def get_friend_agent_list(self,aid):
        try:
            aid_md5 = hashlib.md5(aid.encode('utf-8')).hexdigest()
            friend_table = f"friend_{aid_md5}"
            # 修改为使用动态生成的friend_table表名
            cursor = self.conn.cursor()
            cursor.execute(f'''SELECT * FROM {friend_table}''')
            #columns = [column[0] for column in cursor.description]  # 获取列名
            rows = cursor.fetchall()
            result = []
            for row in rows:
                row_dict = {
                    "id":row[0],
                    "aid":row[1],
                    "name":row[2],
                    "avaurl":row[3],
                    "description":row[4]
                }
                result.append(row_dict)
            cursor.close()
            return result
        except sqlite3.Error as e:
            print(f"get_friend_agent_list数据库操作失败: {str(e)}")
            return []
        
    
    def _create_table(self):
        # 身份表，TODO 需考虑加密..
        # cursor.execute("""DELETE FROM agentids""")
        cursor = self.conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS agentids (
            aid TEXT PRIMARY KEY, 
            ep_aid TEXT,
            ep_url TEXT,
            avaUrl TEXT,
            name TEXT,
            description TEXT)
        ''')
       
        self.conn.commit()
        cursor.close()
    
    def create_table(self,aid):
        # 生成aid的MD5哈希作为表名前缀
        cursor = self.conn.cursor()
        aid_md5 = hashlib.md5(aid.encode('utf-8')).hexdigest()
        conversation_table = f"conversation_{aid_md5}"
        messages_table = f"messages_{aid_md5}"
        friend_table = f"friend_{aid_md5}"
        chat_config_table = f"chat_config_{aid_md5}"
        # cursor.execute(f"DROP TABLE IF EXISTS {conversation_table}")

        cursor.execute(f'''CREATE TABLE IF NOT EXISTS {conversation_table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            identifying_code TEXT NOT NULL,
            main_aid TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            timestamp DATETIME DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
        )''')
        
        # cursor.execute(f"DROP TABLE IF EXISTS {messages_table}")
        
        cursor.execute(f'''CREATE TABLE IF NOT EXISTS {messages_table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT,  -- 消息id, 用于去重
            session_id INTEGER,  -- 关联到对话表的id
            role TEXT NOT NULL,  -- 消息发送者,
            message_aid TEXT NOT NULL, 
            parent_message_id INTEGER,  -- 关联到父消息的id
            to_aids TEXT NOT NULL,  -- 消息发送者,
            content TEXT NOT NULL,  -- 消息内容,
            type TEXT NOT NULL,  -- 消息状态，如"sent", "received",
            status TEXT NOT NULL,  -- 消息状态，如"error", "success",
            timestamp DATETIME DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
        )''')
        
        cursor.execute(f'''CREATE TABLE IF NOT EXISTS {chat_config_table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,  
            aid TEXT NOT NULL,  
            avaurl TEXT,
            description TEXT, 
            post_data TEXT
        )''')
        
        cursor.execute(f'''CREATE TABLE IF NOT EXISTS {friend_table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aid TEXT NOT NULL,
            name TEXT,
            avaurl TEXT,
            description TEXT
        )''')
        
        self.conn.commit()
        cursor.close()
        
    
    
    def update_aid_info(self, aid, avaUrl, name, description):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''UPDATE agentids SET avaUrl =?, name =?, description =? WHERE aid =?''', (avaUrl, name, description, aid))
            self.conn.commit()
            result = cursor.rowcount > 0
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"update_aid_info数据库操作失败: {str(e)}")
            return False
    
    def create_conversation(self, aid,session_id,identifying_code,name, type,to_aid_list:list):
        try:
            cursor = self.conn.cursor()
            import hashlib
            aid_md5 = hashlib.md5(aid.encode('utf-8')).hexdigest()
            conversation_table = f"conversation_{aid_md5}"
            main_aid = ""      
            # 修正参数数量，确保5个值对应5个占位符
            cursor.execute(f'''INSERT INTO {conversation_table} (session_id,identifying_code,main_aid,name,type) VALUES (?,?,?,?,?)''', 
                              (session_id, identifying_code, main_aid, name, type))
            self.conn.commit()
            result = cursor.lastrowid
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"create_conversation数据库操作失败: {str(e)}")
            
    def invite_member(self, aid, session_id, invite_aid:str):
        try:
            cursor = self.conn.cursor()
            import hashlib
            aid_md5 = hashlib.md5(aid.encode('utf-8')).hexdigest()
            chat_config_table = f"chat_config_{aid_md5}"
            cursor.execute(f'''INSERT INTO {chat_config_table} (session_id,aid,avaurl,description, post_data) VALUES (?,?,?,?,?)''', 
                                    (session_id,invite_aid,"","",""))
            self.conn.commit()
            result = cursor.lastrowid
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"invite_member数据库操作失败: {str(e)}")
            return False
        except Exception as e:
            print(f"invite_member数据库操作失败: {str(e)}")
            return False
    
    def get_message_by_id(self, aid, session_id,message_id):
        try:
            cursor = self.conn.cursor()
            import hashlib
            aid_md5 = hashlib.md5(aid.encode('utf-8')).hexdigest()
            messages_table = f"messages_{aid_md5}"
            cursor.execute(f'''SELECT * FROM {messages_table} WHERE session_id =? AND message_id =?''', (session_id,message_id))
            columns = ['id','session_id','message_id','role','message_aid', 'parent_message_id', 'to_aids', 'content', 'type', 'status', 'timestamp']
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            cursor.close()  # 关闭cursor对象
            # 返回JSON格式字符串
            return results
        except sqlite3.Error as e:
            print(f"get_message_by_id数据库操作失败: {str(e)}")
            return []

    def save_message(message):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''INSERT INTO messages (session_id, role, message_id, parent_message_id, to_aids, content, type, status) VALUES (?,?,?,?,?,?,?,?)''', (message.session_id, message.role, message.message_id, message.parent_message_id, message.to_aids, message.content, message.type, message.status))
            self.conn.commit()
            result = cursor.lastrowid
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"save_message数据库操作失败: {str(e)}")
            return None
        
    def update_message(self, aid, message):
        try:
            cursor = self.conn.cursor()
            import hashlib
            aid_md5 = hashlib.md5(aid.encode('utf-8')).hexdigest()
            messages_table = f"messages_{aid_md5}"
            cursor.execute(f'''UPDATE {messages_table} SET content =?,status =? WHERE id =?''', (message["content"], message["status"], message["id"]))
            self.conn.commit()
            result = cursor.rowcount > 0
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"update_message数据库操作失败: {str(e)}")
            return False
    
    def insert_message(self, role,aid,conversation_id, message_aid, parent_message_id, to_aids, content, type, status,message_id=''):
        try:
            import hashlib
            cursor = self.conn.cursor()
            aid_md5 = hashlib.md5(aid.encode('utf-8')).hexdigest()
            messages_table = f"messages_{aid_md5}"
            # 将json.dump改为json.dumps
            cursor.execute(f'''INSERT INTO {messages_table} (session_id, role,message_id,message_aid, parent_message_id, to_aids, content, type, status) VALUES (?,?,?,?,?,?,?,?,?)''',
                                (conversation_id, role,message_id,message_aid, parent_message_id, to_aids, content, type, status))
            self.conn.commit()
            result = cursor.lastrowid
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"insert_message数据库操作失败: {str(e)}")
    
    def load_aid(self, aid):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''SELECT ep_aid, ep_url,avaUrl,name,description FROM agentids WHERE aid = ?''', (aid,))
            result = cursor.fetchone()
            cursor.close()  # 关闭cursor对象
            if result:
                return result[0], result[1],result[2],result[3],result[4]
            else:
                return None, None,None,None,None
        except sqlite3.Error as e:
            print(f"load_aid数据库操作失败: {str(e)}")
            return None, None,None,None,None

    def create_aid(self, aid,ep_aid = "",ep_url = "",avaUrl = "",name = "",description=""):
        try:
            cursor = self.conn.cursor()
            # 将私钥和CSR序列化为PEM格式字符串            
            cursor.execute('''INSERT INTO agentids (aid, ep_aid, ep_url,avaUrl,name,description) 
                                VALUES (?,?,?,?,?,?)''', 
                                (aid, ep_aid , ep_url,avaUrl,name,description))
            self.conn.commit()
            cursor.close()  # 关闭cursor对象
            return ""
        except sqlite3.Error as e:
            print(f"save_aid数据库操作失败: {str(e)}")
            raise RuntimeError(f"save_aid数据库操作失败: {str(e)}")
            
    def update_aid(self, aid, ep_aid, ep_url):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''UPDATE agentids SET ep_aid =?, ep_url =? WHERE aid =?''', (ep_aid, ep_url, aid))
            self.conn.commit()
            result = cursor.rowcount > 0
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"update_aid数据库操作失败: {str(e)}")
            return False
    
    def get_agentid_list(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''SELECT aid FROM agentids''')
            result = [row[0] for row in cursor.fetchall()]  # 提取每个元组的第一个元素
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"get_agentid_list数据库操作失败: {str(e)}")
            return []

    def get_conversation_by_id(self, aid, conversation_id):
        try:
            import hashlib
            cursor = self.conn.cursor()
            aid_md5 = hashlib.md5(aid.encode('utf-8')).hexdigest()
            conversation_table = f"conversation_{aid_md5}"
            cursor.execute(f'''SELECT id, session_id,identifying_code,main_aid,name,type FROM {conversation_table} WHERE id =?''', (conversation_id,))
            result = cursor.fetchone()
            cursor.close()  # 关闭cursor对象
            if result:
                return {
                    'id': result[0],
                    'session_id': result[1],
                    'identifying_code': result[2],
                    'main_aid': result[3],
                    'name': result[4],
                    'type': result[5]
                }
            else:
                return None
        except sqlite3.Error as e:
            print(f"get_conversation_by_id数据库操作失败: {str(e)}")
            return None
          
    def get_conversation_list(self, aid, main_aid, page=1, page_size=10):
        try:
            offset = (page - 1) * page_size
            import hashlib
            cursor = self.conn.cursor()
            aid_md5 = hashlib.md5(aid.encode('utf-8')).hexdigest()
            conversation_table = f"conversation_{aid_md5}"
            if main_aid == "" or main_aid == None:
                cursor.execute(
                    f'''SELECT id, session_id, identifying_code, name, type, timestamp
                        FROM {conversation_table}
                        ORDER BY timestamp DESC
                        LIMIT? OFFSET?''',  
                    (page_size, offset)
                )
            else:
                cursor.execute(
                    f'''SELECT id, session_id, identifying_code, name, type, timestamp 
                        FROM {conversation_table} 
                        WHERE main_aid = ? 
                        ORDER BY timestamp DESC 
                        LIMIT ? OFFSET ?''', 
                    (main_aid, page_size, offset))
            
            # 将查询结果转换为字典列表
            columns = ['id', 'session_id', 'identifying_code', 'name', 'type', 'timestamp']
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            cursor.close()  # 关闭cursor对象
            # 返回JSON格式字符串
            return results
            
        except sqlite3.Error as e:
            print(f"get_conversation_list数据库操作失败: {str(e)}")
            return []
    
    def get_conversation_messages(self, conversation_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''SELECT id, aid, content, timestamp FROM messages WHERE conversation_id =? ORDER BY timestamp ASC''', (conversation_id,))
            result = cursor.fetchall()
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"get_conversation_messages数据库操作失败: {str(e)}")
            return []
    
    def get_conversation_config(self, conversation_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''SELECT id, aid, avaurl, description, post_data FROM chat_config WHERE conversation_id =?''', (conversation_id,))
            result = cursor.fetchall()
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"get_conversation_config数据库操作失败: {str(e)}")
            return []

    def add_conversation_config(self, conversation_id, aid, avaurl, description, post_data):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''INSERT INTO chat_config (conversation_id, aid, avaurl, description, post_data) VALUES (?,?,?,?,?)''', (conversation_id, aid, avaurl, description, post_data))
            self.conn.commit()
            result = cursor.lastrowid
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"add_conversation_config数据库操作失败: {str(e)}")
            return None

    def update_conversation_config(self, config_id, avaurl, description, post_data):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''UPDATE chat_config SET avaurl = ?, description = ?, post_data = ? WHERE id = ?''', (avaurl, description, post_data, config_id))
            self.conn.commit()
            result = cursor.rowcount > 0
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"update_conversation_config数据库操作失败: {str(e)}")
            return False
    
    def get_message_list(self, aid, session_id, page=1, page_size=10):
        try:
            offset = (page - 1) * page_size
            import hashlib
            cursor = self.conn.cursor()
            aid_md5 = hashlib.md5(aid.encode('utf-8')).hexdigest()
            messages_table = f"messages_{aid_md5}"
            
            # 修正SQL语句，移除多余的括号
            cursor.execute(
                f'''SELECT id, session_id,message_id,role,message_aid, parent_message_id, to_aids, content, type, status, timestamp
                    FROM {messages_table}
                    WHERE session_id = ? 
                    ORDER BY timestamp ASC LIMIT ? OFFSET ?''', 
                (session_id, page_size, offset))
            
            # 将查询结果转换为字典列表
            columns = ['id','session_id','message_id','role','message_aid', 'parent_message_id', 'to_aids', 'content', 'type', 'status', 'timestamp']
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            cursor.close()  # 关闭cursor对象
            # 返回JSON格式字符串
            return results
        except sqlite3.Error as e:
            print(f"get_message_list数据库操作失败: {str(e)}")
            return []
        # return [dict(row) for row in cursor.fetchall(
    
    def get_session_member_list(self,aid,session_id):
        try:
            aid_md5 = hashlib.md5(aid.encode('utf-8')).hexdigest()
            chat_config_table = f"chat_config_{aid_md5}"
            # 修改为使用动态生成的friend_table表名
            cursor = self.conn.cursor()
            cursor.execute(f'''SELECT * FROM {chat_config_table} WHERE session_id =?''', (session_id,))
            columns = [column[0] for column in cursor.description]  # 获取列名
            rows = cursor.fetchall()
            result = []
            for row in rows:
                row_dict = {columns[i]: row[i] for i in range(len(columns))}
                result.append(row_dict)
            cursor.close()  # 关闭cursor对象
            return result
        except sqlite3.Error as e:
            print(f"get_session_member_list数据库操作失败: {str(e)}")
            return False
    