"""集中日志配置 — dictConfig + request_id 上下文追踪"""

import uuid
from contextvars import ContextVar
from logging.config import dictConfig

request_id_ctx: ContextVar[str] = ContextVar('request_id', default='-')


class RequestIdFilter:
    """将 request_id 注入到 log record"""

    def filter(self, record):
        record.request_id = request_id_ctx.get()
        return True


LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] [%(levelname)-7s] [rid:%(request_id)s] [%(name)s] %(message)s',
            'datefmt': '%m-%d %H:%M:%S',
        },
    },
    'filters': {
        'request_id': {
            '()': 'backend.its_knowledge.utils.logging_config.RequestIdFilter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'filters': ['request_id'],
        },
    },
    'loggers': {
        'backend.its_knowledge': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # 抑制第三方库噪音
        'chromadb': {'level': 'WARNING'},
        'httpx': {'level': 'WARNING'},
        'openai': {'level': 'WARNING'},
        'urllib3': {'level': 'WARNING'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}


def setup_logging():
    dictConfig(LOGGING_CONFIG)
