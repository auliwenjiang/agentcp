# 在Python文件开头明确指定编码声明
# -*- coding: utf-8 -*-
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
from flask import Flask, request, Response, jsonify
import threading
import socket
import time

from .llm_agent_utils import LLMAgent,AttrDict
from flask import jsonify, make_response
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
app = Flask(__name__)
# app.logger.disabled = True
actual_port = 0

llm_aid_app_key_map = {}
llm_app_key_aid_map = {}
is_running = False

@app.route('/<llm_aid>/chat/completions', methods=['POST'])  # 添加methods参数指定POST方法
async def llm_request(llm_aid):
    # 获取请求头并打印
    headers = dict(request.headers)
    if request.is_json:
        body = request.get_json()
    else:
        body = request.form.to_dict()
    global llm_app_key_aid_map
    auth_str:str = headers.get("Authorization")
    llm_app_key = auth_str.replace("Bearer ","")
    aid = llm_app_key_aid_map.get(llm_app_key)
    if aid is None:
        return make_response(jsonify({"error": "Unauthorized"}), 401)
    llm_agent = LLMAgent(llm_agent=llm_aid, aid = aid)
    response = await llm_agent.chat_create(body)
    # print(response.get("status",""))
    if isinstance(response, AttrDict) and response.get("status","") == 'error':
        # 如果是错误状态，可以进行特殊处理，例如记录日志或返回自定义错误信息
        return make_response(jsonify({"error": response.get('message', "未知错误")}), response.get('code', 400))
    return response

# @app.route('/', defaults={'path': ''}, methods=['OPTIONS', 'GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
# @app.route('/<path:path>', methods=['OPTIONS', 'GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
# async def proxy(path):
#     try:
#         if request.method == 'OPTIONS':
#             # 返回 CORS 预检响应头
#             response = Response()
#             response.headers['Access-Control-Allow-Origin'] = '*'
#             response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
#             response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
#             return response
#         elif request.method == 'POST':
#             # 这个最终来自路由服务器,即模型名称对应一个地址和key
#             # 校验请求数据
#             # data = request.get_json()
#             try:
#                 #return llm_request(llm_aid)
#                 llm_aid = path.split('/')[0]
#                 return await llm_request(llm_aid)
#             except Exception as e:
#                 return jsonify({"error": f"{path}"}), 502
#         elif request.method == 'GET':
#             return jsonify({"result": "服务访问正常"}), 200
#         else:
#             return jsonify({"error": "Method not allowed"}), 405

#     except Exception as e:
#         return jsonify({"error": "Internal server error", "details": str(e)}), 500


def add_llm_aid(aid):
    global llm_aid_app_key_map, llm_app_key_aid_map
    import hashlib
    if aid.id in llm_aid_app_key_map:
        llm_app_key = llm_aid_app_key_map[aid.id]
    else:
        llm_app_key = str(int(time.time())+actual_port)
        llm_app_key = hashlib.sha256(llm_app_key.encode()).hexdigest()
        llm_aid_app_key_map[aid.id] = llm_app_key
    llm_app_key_aid_map[llm_app_key] = aid
    return True


def add_llm_api_key(aid,llm_app_key):
    global llm_aid_app_key_map, llm_app_key_aid_map
    llm_aid_app_key_map[aid.id] = llm_app_key
    llm_app_key_aid_map[llm_app_key] = aid
    return True
    

def get_base_url(aid,llm_aid):
    global actual_port
    # 获取实际分配的端口号
    return "http://127.0.0.1:"+str(actual_port)+"/"+llm_aid

def get_llm_api_key(aid_str:str):
    # 获取实际分配的端口号
    global llm_aid_app_key_map,llm_app_key_aid_map
    if aid_str not in llm_aid_app_key_map:
        import secrets,hashlib
        llm_app_key = secrets.token_hex(16)
        llm_app_key = hashlib.sha256(llm_app_key.encode()).hexdigest()
        llm_aid_app_key_map[aid_str] = llm_app_key
    return llm_aid_app_key_map[aid_str]

def llm_server_is_running():
    global is_running
    return is_running

def __run_server():
    # 端口设为0让系统自动分配
    try:
        global actual_port
        if actual_port == 0:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('', 0))
            actual_port = sock.getsockname()[1]
            sock.close()
            app.run(host='127.0.0.1', port = actual_port, debug=False)
        else:
            app.run(host='127.0.0.1', port = actual_port, debug=False)

        global is_running
        is_running = True
    except Exception as e:
        is_running = False
        #print(f"Flask服务启动失败,请检查端口占用后，重启服务")

def run_server(debug:bool = False,port:int = 0,llm_aid_app_key_map_h = {},llm_app_key_aid_map_h = {}):
    # 创建并启动子线程运行Flask服务
    app.logger.disabled = (not debug)
    global actual_port,llm_aid_app_key_map,llm_app_key_aid_map
    try:
        actual_port = int(port)
    except (ValueError, TypeError):
        actual_port = 0  # 如果转换失败，设置为默认值0
    llm_aid_app_key_map = llm_aid_app_key_map_h
    llm_app_key_aid_map = llm_app_key_aid_map_h
    server_thread = threading.Thread(target=__run_server)
    server_thread.daemon = True  # 设置为守护线程，主线程退出时会自动结束
    server_thread.start()
    # 主线程可以继续执行其他任务

# 添加一个关闭服务器的路由
@app.route('/shutdown', methods=['POST'])
def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        return jsonify({"status": "error", "message": "Not running with Werkzeug Server"})
    func()
    return jsonify({"status": "success", "message": "Server shutting down..."})