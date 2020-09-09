import logging

logger = logging.getLogger(__name__)


offset = ' ' * 4


def log_handler(f):

    def inner(*args, **kwargs):
        message = f'Handler \'{f.__name__}\' called \n{offset}User: {args[0].effective_user}\n'
        if args[0].message:
            pass
            message += f'{offset}Message: {args[0].message.text}\n'
        elif args[0].callback_query:
            pass
            message += f'{offset}Query: {str(args[0].callback_query.data)}\n'
        message += f'{offset}Result: '
        try:
            retval = f(*args, **kwargs)
            logger.info(message + 'DONE')
            return retval
        except Exception as e:
            logger.info(message + 'FAILED')
            raise e
    return inner