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
import logging

from agentcp.base.env import Environ


def get_logger(name=__name__, level=Environ.LOG_LEVEL.get(logging.INFO)) -> logging.Logger:
    """
    Set up the log for the agentid module.
    """
    log = logging.getLogger(name)
    log.setLevel(level)
    if not log.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(formatter)
        log.addHandler(console_handler)
    else:
        for handler in log.handlers:
            try:
                handler.setLevel(level)
            except Exception:
                pass
    return log


logger = None
log_enabled = True


def _ensure_logger() -> logging.Logger:
    """Ensure module-level logger is initialized to avoid None dereferences."""
    global logger
    if logger is None:
        try:
            logger = get_logger(name="agentid", level=Environ.LOG_LEVEL.get(logging.INFO))
        except Exception:
            logger = logging.getLogger("agentid")
    return logger


def set_log_enabled(enabled: bool, level: int):
    global log_enabled, logger
    log_enabled = enabled
    logger = get_logger(name="agentid", level=Environ.LOG_LEVEL.get(level))
    
def log_exception(e):
    global log_enabled
    if log_enabled:
        _ensure_logger().exception(e)
        
def log_info(content:str):
    global log_enabled
    if log_enabled and _ensure_logger().isEnabledFor(logging.INFO):
        _ensure_logger().info(content)
        
def log_error(content:str):
    global log_enabled
    if log_enabled and _ensure_logger().isEnabledFor(logging.ERROR):
        _ensure_logger().error(content)

def log_debug(content:str):
    global log_enabled
    if log_enabled and _ensure_logger().isEnabledFor(logging.DEBUG):
        _ensure_logger().debug(content)
        
def log_warning(content:str):
    global log_enabled
    if log_enabled and _ensure_logger().isEnabledFor(logging.WARNING):
        _ensure_logger().warning(content)

# 新增关键日志级别
def log_critical(content:str):
    global log_enabled
    if log_enabled and _ensure_logger().isEnabledFor(logging.CRITICAL):
        _ensure_logger().critical(content)

# 新增详细日志级别        
def log_verbose(content:str):
    global log_enabled
    if log_enabled and _ensure_logger().isEnabledFor(logging.DEBUG - 1):
        _ensure_logger().log(logging.DEBUG - 1, content)
