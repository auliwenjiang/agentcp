import logging
from agentcp.env import Environ        
def get_logger(name=__name__, level=Environ.LOG_LEVEL.get(logging.INFO)) -> logging.log:
    """
    Set up the log for the agentid module.
    """
    log = logging.getLogger(name)
    log.setLevel(level)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(formatter)
    log.addHandler(console_handler)
    return log


logger = get_logger(name="agentid", level=Environ.LOG_LEVEL.get(logging.INFO))
log_enabled = True
def set_log_enabled(enabled:bool):
    global log_enabled
    log_enabled = enabled
    
def log_exception(e):
    global log_enabled
    if log_enabled:
        logger.exception(e)
        
def log_info(content:str):
    global log_enabled
    if log_enabled:
        logger.info(content)
        
def log_error(content:str):
    global log_enabled
    if log_enabled:
        logger.error(content)

def log_debug(content:str):
    global log_enabled
    if log_enabled:
        logger.debug(content)
        
def log_warning(content:str):
    global log_enabled
    if log_enabled:
        logger.warning(content)

