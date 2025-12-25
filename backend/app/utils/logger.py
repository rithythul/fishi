"""
logconfiguremodule
提供统一oflog管理，同时输出到控制台andfile
"""

import os
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler


# logdirectory
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')


def setup_logger(name: str = 'fishi', level: int = logging.DEBUG) -> logging.Logger:
    """
    setlog器
    
    Args:
        name: log器名称
        level: log级别
        
    Returns:
        configure好oflog器
    """
    # 确保logdirectory存in
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # createlog器
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 阻止log向upload播到根 logger，避免重复输出
    logger.propagate = False
    
    # ifalready经haveprocessing器，not重复添加
    if logger.handlers:
        return logger
    
    # logformat
    detailed_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 1. fileprocessing器 - detailedlog（Bydate命名，带轮转）
    log_filename = datetime.now().strftime('%Y-%m-%d') + '.log'
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, log_filename),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    
    # 2. 控制台processing器 - 简洁log（INFOand以上）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    
    # 添加processing器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def get_logger(name: str = 'fishi') -> logging.Logger:
    """
    getlog器（ifnot存in则create）
    
    Args:
        name: log器名称
        
    Returns:
        log器instance
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


# create默认log器
logger = setup_logger()


# 便捷method
def debug(msg, *args, **kwargs):
    logger.debug(msg, *args, **kwargs)

def information(msg, *args, **kwargs):
    logger.info(msg, *args, **kwargs)

def warning(msg, *args, **kwargs):
    logger.warning(msg, *args, **kwargs)

def error(msg, *args, **kwargs):
    logger.error(msg, *args, **kwargs)

def critical(msg, *args, **kwargs):
    logger.critical(msg, *args, **kwargs)

