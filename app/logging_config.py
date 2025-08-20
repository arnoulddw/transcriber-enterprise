import logging
import logging.config
import os
from pythonjsonlogger import jsonlogger

# ==============================================================================
# Standardized Context Keys
# ==============================================================================
# To ensure consistency across all logs, the following keys should be used
# within the 'context' dictionary of a log record.
#
# - user_id:      The ID of the user who initiated the action.
# - job_id:       The unique identifier for a transcription or workflow job.
# - llm_op_id:    The ID for a specific Large Language Model operation.
# - request_id:   A unique ID for tracking a single HTTP request.
# - component:    The name of the application component (e.g., 'WorkflowService', 'OpenAIClient').
# - client_ip:    The IP address of the client making a request.
# ==============================================================================

class AppContextFilter(logging.Filter):
    """
    A custom logging filter to ensure the 'context' field exists.
    The ContextualLogger adapter is responsible for populating it.
    """
    def filter(self, record):
        if not hasattr(record, 'context'):
            record.context = {}
        return True

def setup_logging():
    """
    Configures the application's logging.
    This setup uses a JSON formatter to produce structured logs, which is
    ideal for log management systems. It configures a console handler
    and a rotating file handler.
    """
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'filters': {
            'app_context': {
                '()': AppContextFilter,
            }
        },
        'formatters': {
            'json': {
                '()': jsonlogger.JsonFormatter,
                'format': '%(asctime)s %(name)s %(levelname)s %(message)s %(context)s',
                'datefmt': '%Y-%m-%dT%H:%M:%S%z'
            },
            'standard': {
                'format': '%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s'
            }
        },
        'handlers': {
            'console': {
                'level': 'INFO',
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
                'filters': ['app_context']
            },
            'file': {
                'level': 'INFO',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': os.path.join(log_dir, 'app.log'),
                'maxBytes': 1024 * 1024 * 5,  # 5 MB
                'backupCount': 5,
                'formatter': 'json',
                'filters': ['app_context']
            }
        },
        'loggers': {
            '': {  # root logger
                'handlers': ['console', 'file'],
                'level': 'INFO',
            },
            'app': {
                'handlers': ['console', 'file'],
                'level': 'INFO',
                'propagate': False
            }
        }
    })

class ContextualLogger(logging.LoggerAdapter):
    """
    A logger adapter to simplify adding contextual information.
    It automatically formats the 'extra' dictionary into the 'context'
    field that our filter and formatter expect.
    """
    def process(self, msg, kwargs):
        # If 'extra' is provided, ensure it's a dictionary and move it to 'context'
        if 'extra' in kwargs:
            kwargs['extra'] = {'context': kwargs['extra']}
        return msg, kwargs

def get_logger(name, **context):
    """
    Returns a logger instance that is pre-configured with context.

    Usage:
        logger = get_logger(__name__, job_id="123", user_id="456")
        logger.info("This message will have the context.")
    """
    logger = logging.getLogger(name)
    adapter = ContextualLogger(logger, context)
    return adapter
