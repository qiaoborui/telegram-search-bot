from telegram.ext import CommandHandler
from app.models import Chat, DBSession
from app.utils import check_control_permission, get_text_func

_ = get_text_func()


def disbale_chat_or_do_nothing(chat_id):
    session = DBSession()
    target_chat = session.query(Chat).get(chat_id)
    if target_chat and target_chat.enable:
        target_chat.enable = False
        session.add(target_chat)
        session.commit()
        msg_text = _('bot stopped, group messages retained, use /delete to remove')
    else:
        msg_text = _('already stopped / not started, use /start to start bot in current group!')
    session.close()
    return msg_text


def stop(update, context):
    from_user_id = update.message.from_user.id
    chat_id = update.effective_chat.id
    chat_member = context.bot.get_chat_member(
        chat_id=chat_id, user_id=from_user_id)
    # Check control permission
    if check_control_permission(from_user_id) is True:
        pass
    elif check_control_permission(from_user_id) is False:
        return
    elif check_control_permission(from_user_id) is None:
        if chat_member.status != 'creator' and chat_member.status != 'administrator':
            return
    else:
        return
    msg_text = disbale_chat_or_do_nothing(chat_id)
    context.bot.send_message(chat_id=update.effective_chat.id, text=msg_text)


handler = CommandHandler('stop', stop)
