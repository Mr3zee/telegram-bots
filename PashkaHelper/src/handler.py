import sys
import traceback

from telegram import Update, error
from telegram.ext import MessageHandler, CommandHandler, CallbackContext, Filters, CallbackQueryHandler, \
    ConversationHandler
from telegram.utils.helpers import mention_html

import src.keyboard as keyboard
import src.database as database
import src.common_functions as cf
import static.consts as consts

import src.parameters_hdl as ptrs
import src.jobs as jobs
import src.subject as subject

from util.log import log_function
from src.text import get_text
from src.timetable import get_weekday_timetable
from src import time_management as tm, timetable as tt

handlers = {}


@log_function
def start(update: Update, context: CallbackContext):
    """
    adds user into the database, if he was not there
    sets job if new user
    sends greeting message
    """
    language_code = update.effective_user.language_code
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    new_user = database.add_user(user_id, update.effective_user.username, chat_id)

    if new_user:
        jobs.set_mailing_job(user_id=user_id, chat_id=chat_id, context=context, language_code=language_code)

    context.bot.send_message(
        chat_id=chat_id,
        text=get_text('start_text', language_code=language_code).text(),
    )
    return consts.MAIN_STATE


@log_function
def callback(update: Update, context: CallbackContext):
    """
    Handles and parses main callbacks
    callback should be in format name_arg1_arg2_..._argn_button
    """
    data, language_code = cf.manage_callback_query(update)
    parsed_data = data.split('_')
    if parsed_data[0] == consts.TIMETABLE:
        return timetable_callback(update, context, parsed_data, language_code)
    elif parsed_data[0] == consts.SUBJECT:
        return subject.subject_callback(update, context, parsed_data, language_code)
    elif parsed_data[0] == consts.HELP:
        return help_callback(update, context, parsed_data, language_code)
    else:
        return unknown_callback(update, context)


@log_function
def help(update: Update, context: CallbackContext):
    """help command callback"""
    for job in context.job_queue.get_jobs_by_name(consts.MAILING_JOB):
        print(job.name, job.enabled, job.removed, job.next_t)
    language_code = update.effective_user.language_code
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=get_text('help_main_text', language_code).text(),
        reply_markup=keyboard.help_keyboard(consts.MAIN_PAGE, language_code),
    )


@log_function
def help_callback(update: Update, context: CallbackContext, data: list, language_code):
    """change help page"""
    if data[1] in {consts.MAIN_PAGE, consts.ADDITIONAL_PAGE}:
        text = get_text(f'help_{data[1]}_text', language_code).text()
    else:
        raise ValueError(f'Invalid help callback: {data[0]}')
    cf.edit_message(
        update=update,
        text=text,
        reply_markup=keyboard.help_keyboard(data[1], language_code),
    )


@log_function
def unknown_callback(update: Update, context: CallbackContext):
    """handles unknown callbacks"""
    language_code = update.effective_user.language_code
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=get_text('unknown_callback_text', language_code).text()
    )


@log_function
def timetable_callback(update: Update, context: CallbackContext, data: list, language_code):
    """handles timetable callbacks"""
    subject_names = database.get_user_subject_names(user_id=update.effective_user.id)
    attendance, week_parity, weekday = data[1:-1]

    cf.edit_message(
        update=update,
        text=get_weekday_timetable(
            weekday=weekday,
            subject_names=subject_names,
            attendance=attendance,
            week_parity=week_parity,
            language_code=language_code,
        ),
        reply_markup=keyboard.timetable_keyboard(
            weekday=weekday,
            attendance=attendance,
            week_parity=week_parity,
            language_code=language_code,
        )
    )


def timetable_args_error(context: CallbackContext, chat_id, error_type, language_code):
    """send argument error message"""
    context.bot.send_message(
        chat_id=chat_id,
        text=get_text('timetable_args_error_text', language_code).text({'error_type': error_type}),
    )


@log_function
def timetable(update: Update, context: CallbackContext):
    """
    sends timetable main page if no argument specified
    otherwise sends timetable for specified day: 0 - 7 -> monday - sunday
    """
    language_code = update.effective_user.language_code
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    week_parity = tm.get_week_parity()
    attendance = database.get_user_attr(consts.ATTENDANCE, user_id)

    if len(args) > 1:
        # too many args
        return timetable_args_error(context, chat_id, 'many', language_code)
    elif len(args) == 1:
        # check if arg is integer
        try:
            weekday = int(args[0])
        except ValueError:
            return timetable_args_error(context, chat_id, 'type', language_code)
        if weekday > 6 or weekday < 0:
            # wrong day index
            return timetable_args_error(context, chat_id, 'value', language_code)
        # get timetable for specified day
        weekday = tm.weekdays[weekday]
        text = tt.get_weekday_timetable(
            weekday=weekday,
            subject_names=database.get_user_subject_names(user_id),
            attendance=attendance,
            week_parity=week_parity,
            language_code=language_code,
        )
    else:
        # timetable main page
        weekday = tm.get_today_weekday(database.get_user_attr(consts.UTCOFFSET, user_id=user_id))
        text = get_text('timetable_text', language_code).text()
    context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=keyboard.timetable_keyboard(
            weekday=weekday,
            attendance=attendance,
            week_parity=week_parity,
            language_code=language_code,
        ),
    )


@log_function
def today(update: Update, context: CallbackContext):
    """sends today timetable"""
    cf.send_today_timetable(
        context=context,
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        language_code=update.effective_user.language_code,
    )


def error_callback(update: Update, context: CallbackContext):
    """
    Error callback function
    notifies user that error occurred, sends feedback to all admins
    """
    language_code = update.effective_user.language_code

    # notify user
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=get_text('error_handler_user_text', language_code).text()
    )

    # collect data about error
    data = {'trace': "".join(traceback.format_tb(sys.exc_info()[2])), 'error': str(context.error)}
    if update.effective_user:
        data['user'] = mention_html(update.effective_user.id, update.effective_user.first_name)
    else:
        data['user'] = 'unavailable'

    text = get_text('error_handler_dev_text', language_code)

    # send collected data to all admins
    for dev_id in database.get_all_admins_chat_ids():
        try:
            context.bot.send_message(
                chat_id=dev_id,
                text=text.text(data),
            )
        except error.BadRequest:
            data['trace'] = 'Traceback is unavailable'
            context.bot.send_message(
                chat_id=dev_id,
                text=text.text(data),
            )
    raise


@log_function
def admin(update: Update, context: CallbackContext):
    """
    admin's control panel
    current functions:
    '/admin -ls' - list of all users
    '/admin -n < --user [user_nick] | --all >' - send a notification to the specified user or to all users
    '/admin -m [user_nick]' - mute reports from user
    '/admin -um [user_nick]' - unmute reports from user
    """
    language_code = update.effective_user.language_code
    args = context.args
    ret_lvl = consts.MAIN_STATE
    if not database.get_user_attr('admin', user_id=update.effective_user.id):
        text = get_text('unauthorized_user_admin_text', language_code).text()
    elif len(args) == 0:
        text = get_text('no_args_admin_text', language_code).text()
    elif args[0] == '-n':
        if len(args) == 1:
            text = get_text('no_args_notify_admin_text', language_code).text()
        elif args[1] == '--all':
            if len(args) > 2:
                text = get_text('too_many_args_admin_text', language_code).text()
            else:
                text = get_text('all_users_notify_admin_text', language_code).text()
                ret_lvl = consts.ADMIN_NOTIFY_STATE
        elif args[1] == '--user':
            if len(args) == 3:
                user_nick = args[2]
                if database.has_user(user_nick):
                    context.chat_data['notify_username_admin'] = args[2]
                    text = get_text('user_notify_admin_text', language_code).text()
                    ret_lvl = consts.ADMIN_NOTIFY_STATE
                else:
                    text = get_text('invalid_username_admin_text', language_code).text()
            elif len(args) < 3:
                text = get_text('empty_user_id_notify_admin_text', language_code)
            else:
                text = get_text('too_many_args_admin_text', language_code).text()
        else:
            text = get_text('unavailable_flag_notify_admin_text', language_code).text()
    elif args[0] == '-ls':
        if len(args) > 1:
            text = get_text('too_many_args_admin_text', language_code).text()
        else:
            users = database.get_all_users()
            text = get_text('ls_admin_text', language_code).text(
                {'users': '\n'.join(map(lambda pair: mention_html(pair[0], pair[1]), users))}
            )
    elif args[0] == '-m' or args[0] == '-um':
        if len(args) > 2:
            text = get_text('too_many_args_admin_text', language_code).text()
        elif len(args) < 2:
            text = get_text('empty_user_id_admin_text', language_code).text()
        else:
            user_nick = args[1]
            if not database.has_user(user_nick):
                text = get_text('invalid_username_admin_text', language_code).text()
            elif args[0] == '-m':
                database.set_user_attrs(user_nick=user_nick, attrs={consts.MUTED: True})
                text = get_text('mute_user_admin_text', language_code).text()
            else:
                database.set_user_attrs(user_nick=user_nick, attrs={consts.MUTED: False})
                text = get_text('unmute_user_admin_text', language_code).text()
    else:
        text = get_text('unavailable_flag_admin_text', language_code).text()
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
    )
    return ret_lvl


@log_function
def admin_notify(update: Update, context: CallbackContext):
    """sends provided text to specified users"""
    language_code = update.effective_user.language_code
    user_nick = context.chat_data.get('notify_username_admin')
    context.chat_data.pop('notify_username_admin', None)
    notification_text = update.message.text
    if user_nick is not None:
        cf.send_message(context, user_nick=user_nick, text=notification_text, language_code=language_code)
    else:
        cf.send_message_to_all(context, notification_text, update.effective_user.id, language_code)
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=get_text('notification_sent_notify_admin_text', language_code).text()
    )
    return consts.MAIN_STATE


@log_function
def doc(update: Update, context: CallbackContext):
    """
    show documentation
    if argument specified, shows docs for command
    shows special docs for admins
    """
    language_code = update.effective_user.language_code
    args = context.args
    if_admin = database.get_user_attr('admin', user_id=update.effective_user.id)
    if len(args) > 2:
        text = get_text('quantity_error_doc_text', language_code).text()
    else:
        if len(args) == 0:
            text = get_text('doc_text', language_code).text({'command': consts.ALL, 'admin': if_admin})
        else:
            if args[0] not in consts.DOC_COMMANDS:
                text = get_text('wrong_command_error_doc_text', language_code).text()
            else:
                text = get_text('doc_text', language_code).text({'command': args[0], 'admin': if_admin})
                if not if_admin and args[0] == 'admin':
                    text += get_text('doc_unavailable_text', language_code).text()
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
    )


@log_function
def report(update: Update, context: CallbackContext):
    """will wait for message to report if unmuted"""
    language_code = update.effective_user.language_code
    if database.get_user_attr(consts.MUTED, update.effective_user.id):
        text = get_text('cannot_send_report_text', language_code).text()
        ret_lvl = consts.MAIN_STATE
    else:
        text = get_text('report_text', language_code).text()
        ret_lvl = consts.REPORT_MESSAGE_STATE
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
    )
    return ret_lvl


@log_function
def report_sent(update: Update, context: CallbackContext):
    """take message to report and send it to all admins"""
    language_code = update.effective_user.language_code
    chat_id = update.effective_chat.id
    data = {
        'user': mention_html(update.effective_user.id, update.effective_user.first_name),
    }
    for admin_id in database.get_all_admins_chat_ids():
        context.bot.send_message(
            chat_id=admin_id,
            text=get_text('report_template_text', language_code).text(data),
        )
        context.bot.forward_message(
            chat_id=admin_id,
            from_chat_id=chat_id,
            message_id=update.message.message_id,
        )
    context.bot.send_message(
        chat_id=chat_id,
        text=get_text('report_sent_text', language_code).text(),
    )
    return consts.MAIN_STATE


# handler for /cancel commands in main space
cancel_main = cf.simple_handler(name='cancel_main', type=consts.COMMAND, command='cancel', ret_state=consts.MAIN_STATE)

# list of all handlers for MAIN_STATE
main_hdl = []

# add all subject handlers
for sub in subject.SUBJECTS:
    main_hdl.append(subject.subject_handler(sub))

# add all other main handlers
main_hdl.extend([
    CommandHandler(command='parameters', callback=ptrs.parameters),
    CommandHandler(command='help', callback=help),

    CommandHandler(command='timetable', callback=timetable),
    CommandHandler(command='today', callback=today),

    CommandHandler(command='admin', callback=admin),
    CommandHandler(command='doc', callback=doc),
    CommandHandler(command='report', callback=report),

    CallbackQueryHandler(callback=callback),

    cf.simple_handler('echo_command', consts.MESSAGE, filters=Filters.command),
    cf.simple_handler('echo_message', consts.MESSAGE, filters=Filters.all),
])

# make main conversation handler
handlers['main'] = ConversationHandler(
    entry_points=[
        CommandHandler(command='start', callback=start, pass_chat_data=True, pass_job_queue=True),
    ],
    states={
        consts.MAIN_STATE: main_hdl,

        consts.PARAMETERS_MAIN_STATE: [
            CommandHandler(command='parameters', callback=ptrs.parameters),
            CallbackQueryHandler(callback=ptrs.parameters_callback, pass_chat_data=True, pass_job_queue=True),
            ptrs.exit_parameters,
            ptrs.cancel_parameters,
            ptrs.parameters_error('main'),
        ],
        consts.PARAMETERS_NAME_STATE: [
            ptrs.exit_parameters,
            ptrs.cancel_parameters,
            MessageHandler(filters=Filters.all, callback=ptrs.set_new_name_parameters),
        ],
        consts.PARAMETERS_TIME_STATE: [
            ptrs.exit_parameters,
            ptrs.cancel_parameters,
            MessageHandler(filters=Filters.all, callback=ptrs.time_message_parameters, pass_chat_data=True,
                           pass_job_queue=True),
        ],
        consts.PARAMETERS_TZINFO_STATE: [
            ptrs.exit_parameters,
            ptrs.cancel_parameters,
            MessageHandler(filters=Filters.all, callback=ptrs.tzinfo_parameters, pass_chat_data=True,
                           pass_job_queue=True),
        ],
        consts.REPORT_MESSAGE_STATE: [
            cancel_main,
            MessageHandler(filters=Filters.all, callback=report_sent),
        ],
        consts.ADMIN_NOTIFY_STATE: [
            cancel_main,
            MessageHandler(filters=Filters.all, callback=admin_notify),
        ],
    },
    fallbacks=[],
    persistent=True,
    name='main',
    allow_reentry=True,
)

# if /start don't work its a way to report that problem
handlers['extra_report'] = ConversationHandler(
    entry_points=[
        cf.simple_handler(name='report', type=consts.COMMAND, ret_state=consts.REPORT_MESSAGE_STATE),
    ],
    states={
        consts.REPORT_MESSAGE_STATE: [
            MessageHandler(filters=Filters.all, callback=report_sent),
        ],
    },
    fallbacks=[],
    persistent=True,
    name='extra_report',
)

# if somehow /start button was not pressed
handlers['not_start'] = cf.simple_handler(name='not_start', type=consts.MESSAGE, filters=Filters.all)

# Bot father commands
# help - главное меню
# parameters - окно настроек
# today - расписание на сегодня
# timetable - окно расписания
# doc - документация
# report - сообщение разработчикам
# al - алгосики
# dm - дискретка
# df - диффуры
# ma - матан
# bj - я тебе покушать принес
# en - английский
# hs - история
# sp - современная прога
# os - операционки
# pe - физра
