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
from requests import get


def parse_html(json_data):
    html_content1 = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>智能体描述页面</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
            :root {
                --primary-color: #3498db;
                --secondary-color: #2ecc71;
                --dark-color: #2c3e50;
                --light-color: #ecf0f1;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f8f9fa;
                color: #333;
            }
            
            .navbar {
                background: linear-gradient(135deg, var(--primary-color), var(--dark-color));
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            }
            
            .hero-section {
                background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
                color: white;
                padding: 4rem 0;
                margin-bottom: 2rem;
                border-radius: 0 0 20px 20px;
            }
            
            .card {
                border: none;
                border-radius: 10px;
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
                transition: transform 0.3s ease;
                margin-bottom: 20px;
            }
            
            .card:hover {
                transform: translateY(-5px);
            }
            
            .card-header {
                background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
                color: white;
                border-radius: 10px 10px 0 0 !important;
                font-weight: bold;
            }
            
            .feature-icon {
                font-size: 2.5rem;
                color: var(--primary-color);
                margin-bottom: 1rem;
            }
            
            .tech-specs {
                background-color: white;
                border-radius: 10px;
                padding: 2rem;
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
            }
            
            .tech-specs h3 {
                color: var(--primary-color);
                margin-bottom: 1.5rem;
            }
            
            .tech-specs table {
                width: 100%;
            }
            
            .tech-specs th {
                background-color: var(--light-color);
                padding: 12px;
                text-align: left;
            }
            
            .tech-specs td {
                padding: 12px;
                border-bottom: 1px solid #eee;
            }
            
            .chart-container {
                background-color: white;
                border-radius: 10px;
                padding: 2rem;
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
                margin-bottom: 2rem;
            }
            
            footer {
                background-color: var(--dark-color);
                color: white;
                padding: 2rem 0;
                margin-top: 3rem;
            }
            
            .badge-custom {
                background-color: var(--secondary-color);
                color: white;
                font-weight: normal;
                padding: 5px 10px;
                border-radius: 20px;
            }
        </style>
    </head>
    """
    html_content3 = """
    <body>
        <!-- 导航栏 -->
        <nav class="navbar navbar-expand-lg navbar-dark">
            <div class="container">
                <a class="navbar-brand" href="#">
                    <i class="bi bi-cloud-sun-fill me-2"></i>
                    {name}
                </a>
                <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                    <span class="navbar-toggler-icon"></span>
                </button>
                <div class="collapse navbar-collapse" id="navbarNav">
                    <ul class="navbar-nav ms-auto">
                        <li class="nav-item">
                            <a class="nav-link active" href="#overview">概述</a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="#features">功能</a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="#tech">技术</a>
                        </li>
                    </ul>
                </div>
            </div>
        </nav>

        <!-- 标题区 -->
        <section class="hero-section text-center">
            <div class="container">
                <h1 class="display-4 fw-bold mb-3">{name}</h1>
                <p class="lead mb-4"> {description}</p>
                <span class="badge badge-custom mb-3">版本 1.0.0</span>
                <p class="mb-0">最后更新: {lastUpdated}</p>
            </div>
        </section>

        <!-- 主要内容区 -->
        <div class="container">
            <!-- 基本信息卡片 -->
            <section id="overview" class="mb-5">
                <div class="row">
                    <div class="col-12">
                        <div class="card h-100">
                            <div class="card-header">
                                <h5 class="card-title mb-0"><i class="bi bi-info-circle me-2"></i>系统信息</h5>
                            </div>
                            <div class="card-body">
                                <ul class="list-group list-group-flush">
                                    <li class="list-group-item d-flex justify-content-between align-items-center">
                                        <span><i class="bi bi-tag me-2"></i>名称</span>
                                        <span class="text-muted">{name}</span>
                                    </li>
                                    <li class="list-group-item d-flex justify-content-between align-items-center">
                                        <span><i class="bi bi-card-text me-2"></i>发布者</span>
                                        <span class="text-muted">{publisherAid}</span>
                                    </li>
                                    <li class="list-group-item d-flex justify-content-between align-items-center">
                                        <span><i class="bi bi-123 me-2"></i>版本</span>
                                        <span class="text-muted">{version}</span>
                                    </li>
                                    <li class="list-group-item d-flex justify-content-between align-items-center">
                                        <span><i class="bi bi-calendar-check me-2"></i>最后更新</span>
                                        <span class="text-muted">{lastUpdated}</span>
                                    </li>
                                    <li class="list-group-item d-flex justify-content-between align-items-center">
                                        <span><i class="bi bi-building me-2"></i>认证机构</span>
                                        <span class="text-muted">{organization}</span>
                                    </li>
                                </ul>
                            </div>
                        </div>
                    </div>
                    <div class="col-12 mt-4">
                        <div class="card h-100">
                            <div class="card-header">
                                <h5 class="card-title mb-0"><i class="bi bi-lightning-charge me-2"></i>核心能力</h5>
                            </div>
                            <div class="card-body">
                                <div class="text-center mb-4">
                                    <i class="bi bi-geo-alt-fill feature-icon"></i>
                                    <h4>{capabilitiesCore}</h4>
                                </div>
                                <hr>
                                <div class="text-center">
                                    <i class="bi bi-arrow-repeat feature-icon"></i>
                                    <h4>异步支持</h4>
                                    <p class="text-muted">系统支持异步操作，提高响应效率</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- 功能展示区 -->
            <section id="features" class="mb-5">
                <h2 class="text-center mb-4" style="color: var(--primary-color);"><i class="bi bi-stars me-2"></i>功能特点</h2>
                <div class="row">
                    <div class="col-12 mb-4">
                        <div class="card h-100">
                            <div class="card-body text-center">
                                <i class="bi bi-cloud-sun feature-icon"></i>
                                <h4>{description}</h4>
                                <p class="text-muted">{capabilitiesCore}</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-12 mb-4">
                        <div class="card h-100">
                            <div class="card-body text-center">
                                <i class="bi bi-code-slash feature-icon"></i>
                                <h4>标准接口</h4>
                                <p class="text-muted">采用JSON输入/Markdown输出，标准化接口设计</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-12">
                        <div class="card h-100">
                            <div class="card-body text-center">
                                <i class="bi bi-shield-check feature-icon"></i>
                                <h4>安全认证</h4>
                                <p class="text-muted">通过数字签名认证，确保数据安全可靠</p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- 技术细节表格 -->
            <section id="tech" class="mb-5">
                <div class="tech-specs">
                    <h3 class="text-center"><i class="bi bi-cpu me-2"></i>技术规格</h3>
                    <div class="table-responsive">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>类别</th>
                                    <th>项目</th>
                                    <th>详情</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td rowspan="2">输入</td>
                                    <td>类型</td>
                                    <td>content</td>
                                </tr>
                                <tr>
                                    <td>格式</td>
                                    <td>JSON</td>
                                </tr>
                                <tr>
                                    <td rowspan="2">输出</td>
                                    <td>类型</td>
                                    <td>content</td>
                                </tr>
                                <tr>
                                    <td>格式</td>
                                    <td>Markdown</td>
                                </tr>
                                <tr>
                                    <td>操作模式</td>
                                    <td colspan="2">支持异步操作 (support_async: true)</td>
                                </tr>
                                <tr>
                                    <td>授权</td>
                                    <td colspan="2">免费使用 (当前智能体免费使用，无费用)</td>
                                </tr>
                                <tr>
                                    <td>认证</td>
                                    <td colspan="2">{organization}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </section>
        </div>

        <!-- 页脚 -->
        <footer class="text-center">
            <div class="container">
                <p class="mb-2"><i class="bi bi-cloud-sun-fill me-2"></i>{name}</p>
                <p class="mb-0">© 2025 {organization} 版权所有</p>
            </div>
        </footer>
    """.format(
        name=json_data.get("name", "AI Agent"),
        description=json_data.get("description","AI智能体"),
        lastUpdated=json_data.get("lastUpdated","----"),
        version=json_data.get("version","----"),
        publisherAid=json_data.get("publisherInfo",{}).get("publisherAid","未知发布者"),
        organization = json_data.get("publisherInfo",{}).get("organization","未知认证机构"),
        capabilitiesCore = "，".join(json_data.get("capabilities",{}).get("core", [])),
    )
    html_content4="""
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    return html_content1  + html_content3 +html_content4
    