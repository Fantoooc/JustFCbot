import asyncio
import json
import uuid
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, InlineQueryHandler, CommandHandler, ChosenInlineResultHandler
from telegram.error import BadRequest, Forbidden

API_TOKEN = ""
ADMINS_IDS: list[int] = list()

BLACK_LIST: set[int] = set()
NOTIFICATIONS_LIST: set[int] = set()
VIPS_LIST: set[int] = set()
EVENTS_LIST: dict[str, tuple] = {}

CONFIG_LIST = "config.jsonl"
LIST = "list.jsonl"

secret_messages: dict[str, tuple] = {}

SPECIAL_CHARS = set("!&$")
FLAG_MAP = {
    '!': "exc_flag",
    '&': "vis_flag",
    '$': "del_flag"
}

def save_config() -> None:
    with open(CONFIG_LIST, 'w', encoding="utf-8") as f:
        f.write(json.dumps(API_TOKEN) + '\n')
        f.write(json.dumps(ADMINS_IDS))

def load_config() -> None:
    global API_TOKEN, ADMINS_IDS
    try:
        with open(CONFIG_LIST, 'r', encoding="utf-8") as f:
            API_TOKEN = json.loads(f.readline().strip())
            ADMINS_IDS = json.loads(f.readline().strip())
    except (FileNotFoundError, json.JSONDecodeError, IndexError):
        save_config()

def save() -> None:
    with open(LIST, 'w', encoding="utf-8") as f:
        f.write(json.dumps(list(BLACK_LIST)) + '\n')
        f.write(json.dumps(list(NOTIFICATIONS_LIST)) + '\n')
        f.write(json.dumps(list(VIPS_LIST)) + '\n')
        event_list = {k: list(v) for k, v in EVENTS_LIST.items()}
        f.write(json.dumps(event_list))

def load() -> None:
    global BLACK_LIST, NOTIFICATIONS_LIST, EVENTS_LIST
    try:
        with open(LIST, 'r', encoding="utf-8") as f:
            BLACK_LIST = set(json.loads(f.readline().strip()))
            NOTIFICATIONS_LIST = set(json.loads(f.readline().strip()))
            VIPS_LIST = set(json.loads(f.readline().strip()))
            EVENTS_LIST = {k: tuple(v) for k, v in json.loads(f.readline()).items()}
    except (FileNotFoundError, json.JSONDecodeError, IndexError):
        save()

def build_utumessage(user_id: int, query: str) -> InlineQueryResultArticle | None:
    parts = [ part.strip() for part in query.split('|') ]
    if not parts or not parts[0]: return None

    main = parts[0].split(maxsplit=1)
    if len(main) < 2: return None

    raw = main[0]
    raw_len = len(raw)
    i = 0
    while i < raw_len and raw[i] in SPECIAL_CHARS:
        i += 1
    prefix_chars = set(raw[:i])
    flags = { name: (char in prefix_chars) for char, name in FLAG_MAP.items() }

    target_id = raw[i:]
    message = main[1].strip()

    if not (target_id and (target_id[0] == '@' or target_id.isdigit()) and message): return None
    placeholder_text = parts[1].strip() if len(parts) >= 2 and parts[1].strip() else "Message hided."
    not_for_you_text = parts[2].strip() if len(parts) >= 3 and parts[2].strip() else "This message is not for you."

    key = uuid.uuid4().hex[:16]
    exc_flag, vis_flag, del_flag = flags["exc_flag"], flags["vis_flag"], flags["del_flag"]

    if exc_flag:
        secret_messages[key] = (user_id, target_id.lower(), not_for_you_text, message, exc_flag, vis_flag, del_flag)
        to_target_desc = f"To anyone but {target_id}: {message}"
        to_others_desc = f"To {target_id}: {not_for_you_text}"
    else:
        secret_messages[key] = (user_id, target_id.lower(), message, not_for_you_text, exc_flag, vis_flag, del_flag)
        to_target_desc = f"To {target_id}: {message}"
        to_others_desc = f"To anyone: {not_for_you_text}"

    keyboard = InlineKeyboardMarkup([ [InlineKeyboardButton("Message", callback_data=f"utumessage:{key}")] ])
    return InlineQueryResultArticle(
        id = key,
        title = "Send message",
        description = f"{to_target_desc[:40]}...\nText in message: {placeholder_text[:40]}...\n{to_others_desc[:40]}...",
        input_message_content = InputTextMessageContent(message_text = placeholder_text),
        reply_markup = keyboard
    )

def build_info(user: User, user_id: int) -> InlineQueryResultArticle:
    info_text = (
        f"Your first name: {user.first_name or '-'}\n"
        f"Your last name: {user.last_name or '-'}\n"
        f"Your username: @{user.username or '-'}\n"
        f"Your telegram ID: {user_id}"
    )
    if user_id in ADMINS_IDS: info_text += "\nYou are a bot admin"

    return InlineQueryResultArticle(
        id="info",
        title="Send my info",
        description=info_text.replace("\n", " | "),
        input_message_content=InputTextMessageContent(message_text=info_text)
    )

def build_delete(user_id: int, key: str) -> InlineQueryResultArticle | None:
    if key not in secret_messages: return None

    sender_id = secret_messages[key][0]
    target_id = secret_messages[key][1]
    if not (sender_id == user_id or target_id == user_id): return None

    keyboard = InlineKeyboardMarkup( [[InlineKeyboardButton("Confirm delete", callback_data=f"del:{key}")]] )

    return InlineQueryResultArticle(
        id=f"del-{key}",
        title="Delete message",
        description=f"Message id: {key}",
        input_message_content=InputTextMessageContent( message_text=f"Delete message {key}?" ),
        reply_markup=keyboard
    )

def build_event(user_id: int, query: str):
    if query.lower().startswith("list"):
        events_list = [f"{i}. {v[0]}" for i, (_, v) in enumerate(EVENTS_LIST.items(), start=1)]
        return InlineQueryResultArticle(
            id=f"ev_list",
            title="Send events list",
            input_message_content=InputTextMessageContent( message_text="\n".join(events_list) )
        )
    elif query.lower().startswith("add "):
        if not (user_id in ADMINS_IDS or user_id in VIPS_LIST): return
        event = query[4:86].strip()
        if not event: return
        key = uuid.uuid4().hex[:16]
        keyboard = InlineKeyboardMarkup([ [InlineKeyboardButton(f"Add event *{event}*", callback_data=f"ev_add:{key}:{event}")] ])
        return InlineQueryResultArticle(
            id=f"ev_add-{key}",
            title=f"Add event *{event}*",
            input_message_content=InputTextMessageContent( message_text="Click on button below to add your event" ),
            reply_markup=keyboard
        )
    elif query.lower().startswith("remove "):
        if not (user_id in ADMINS_IDS or user_id in VIPS_LIST): return
        search_key = query[7:86].strip().lower()
        results = []

        for key, event_data in EVENTS_LIST.items():
            event_name = event_data[0]
            if search_key in event_name.lower() and len(results) < 50:
                keyboard = InlineKeyboardMarkup([ [InlineKeyboardButton(f"Remove event *{event_name}*", callback_data=f"ev_remove:{key}:{event_name}")] ])
                results.append(
                    InlineQueryResultArticle(
                        id=f"ev_remove-{key}",
                        title=f"Remove: *{event_name}*",
                        description=f"ID: {key}",
                        input_message_content=InputTextMessageContent( message_text=f"Click the button below to remove event: *{event_name}*" ),
                        reply_markup=keyboard
                    )
                )
        return results

    search_key = query.strip().lower()
    results = []

    for key, event_data in EVENTS_LIST.items():
        event_name = event_data[0]

        if search_key in event_name.lower() and len(results) < 50:
            diff = datetime.now() - datetime.fromisoformat(event_data[1])

            days = diff.days
            hours, remainder = divmod(diff.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            results.append(
                InlineQueryResultArticle(
                    id=f"ev_date:{key}",
                    title=f"{event_name}",
                    description=f"Share *{event_name} event",
                    input_message_content=InputTextMessageContent(
                        message_text=f"С момента *{event_name}* прошло {days}дн. {hours}ч. {minutes}мин. {seconds}с."
                    )
                )
            )
    return results

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.inline_query.from_user.id
    if user_id in BLACK_LIST: return

    query = update.inline_query.query.strip()
    results = [ ]

    if query.lower() == "info":
        results.append(build_info(update.inline_query.from_user, user_id))
    elif query.lower().startswith("delete"):
        delete_result = build_delete(user_id, query[6:].strip())
        if delete_result: results.append(delete_result)
    elif query.lower().startswith("event"):
        event = build_event(user_id, query[5:].strip())
        if event:
            if isinstance(event, list): results.extend(event)
            else: results.append(event)
    else:
        message_result = build_utumessage(user_id, query)
        if message_result: results.append(message_result)

    try: await update.inline_query.answer(results, cache_time=5, is_personal=True)
    except BadRequest: return

async def chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = update.chosen_inline_result
    key = result.result_id
    message_data = secret_messages.get(key)
    if not message_data: return
    await notify_admins(context, f"New message sent from: {message_data[0]}")

def mark_seen(data: tuple) -> tuple:
    if data[2].endswith("  ✓✓"): return data
    return data[:2] + (data[2]+"  ✓✓",) + data[3:]

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    clicker_id = query.from_user.id
    if clicker_id in BLACK_LIST: return
    clicker_username = query.from_user.username

    message = query.data.split(':')
    act = message[0]
    message_key = message[1]
    message_data = secret_messages.get(message_key)

    if clicker_id in ADMINS_IDS or clicker_id in VIPS_LIST:
        if act == "ev_add":
            event = message[2]
            event_time = datetime.now().isoformat()
            EVENTS_LIST[message_key] = (event, event_time)
            save()
            await query.edit_message_text(f"Event *{event}* added and saved\nSaved date in iso format is: {event_time}")
            await query.answer()
            return
        elif act == "ev_remove":
            event = message[2]
            del EVENTS_LIST[message_key]
            save()
            await query.edit_message_text(f"Event *{event}* was removed")
            await query.answer()
            return

    sddm = act == "senddm"
    if not message_data and not sddm:
        try: await query.answer(text="No message in temp data.", show_alert=True, cache_time=3600)
        except BadRequest: return
        return

    text = ""

    sender = message_data[0]
    target = message_data[1]

    target_text = message_data[2]
    other_text = message_data[3]

    exc_flag = message_data[4]
    vis_flag = message_data[5]
    del_flag = message_data[6]

    clicker_sender = clicker_id == sender
    clicker_target = str(clicker_id) == target or (clicker_username and clicker_username.lower() == target[1:])

    key_message = f"\n\n\nMessage id is: {message_key}"

    if clicker_sender: text = f"Message for {target}:\n{target_text}\n\nMessage for anyone:\n{other_text}{key_message}"
    elif clicker_target:
        if exc_flag: text = f"Message:\n{target_text}"
        else:
            if vis_flag:
                text = f"Message for you:\n{target_text}\n\nMessage for anyone:\n{other_text}{key_message}"
            else:
                text = f"Message:\n{target_text}{key_message}"
            secret_messages[message_key] = mark_seen(message_data)
    else:
        if exc_flag and vis_flag: text = f"Message for anyone:\n{other_text}\n\nMessage for {target}:\n{target_text}"
        else: text = f"Message:\n{other_text}"

    if act == "del":
        if del_flag:
            await query.answer("This message cannot be deleted.", show_alert=True, cache_time=3600)
            return
        if not (clicker_sender or (clicker_target and not exc_flag)):
            await query.answer("You can't delete this message.", show_alert=True, cache_time=3600)
            return

        del secret_messages[message_key]
        await query.edit_message_text(f"Message {message_key} burned 🔥.")
        await query.answer()
        return

    if sddm:
        if not (clicker_sender or clicker_target or exc_flag): return
        try:
            await context.bot.send_message(chat_id=clicker_id, text=text)
            await query.answer()
        except Forbidden:
            await query.answer("Couldn't reach that user — they need to start a chat with the bot first.", show_alert=True)
        return

    await notify_admins(context,f"User @{clicker_username} ({clicker_id}) clicked on {message_key}")
    if len(text) <= 200:
        await query.answer(text=text, show_alert=True)
    else:
        if not (clicker_sender or clicker_target or exc_flag): return
        await query.answer(text="Message is too long for a popup.\nTap the button below to send full text in bot chat.\nIf you don't have a chat with the bot you won't get the message.", show_alert=True)
        keyboard = [
            [InlineKeyboardButton("Message", callback_data=f"utumessage:{message_key}")],
            [InlineKeyboardButton("Open full message in DM", callback_data=f"senddm:{message_key}")]
        ]
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            if "Message is not modified" not in str(e): raise



async def notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMINS_IDS: return
    if user_id in NOTIFICATIONS_LIST:
        NOTIFICATIONS_LIST.discard(user_id)
        save()
        await update.message.reply_text("Notifications disabled.")
    else:
        NOTIFICATIONS_LIST.add(user_id)
        save()
        await update.message.reply_text("Notifications enabled.")

async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    for admin_id in NOTIFICATIONS_LIST:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text)
        except Exception as e:
            print(f"Failed to notify admin {admin_id}: {e}")

async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMINS_IDS: return
    if not context.args:
        await update.message.reply_text("Usage: /block <id>")
        return

    try: target = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid id.")
        return

    if target in ADMINS_IDS:
        await update.message.reply_text("Can't block an admin.")
        return

    if target not in BLACK_LIST:
        BLACK_LIST.add(target)
        save()
        await update.message.reply_text(f"User {target} blocked.")
    else:
        await update.message.reply_text(f"User {target} is already blocked.")

async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMINS_IDS: return
    if not context.args:
        await update.message.reply_text("Usage: /unblock <id>")
        return

    try: target = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid id.")
        return

    if target in BLACK_LIST:
        BLACK_LIST.discard(target)
        save()
        await update.message.reply_text(f"User {target} unblocked.")
    else:
        await update.message.reply_text(f"User {target} is not in the blacklist.")

async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMINS_IDS: return
    if not BLACK_LIST:
        await update.message.reply_text("Blacklist is empty.")
        return
    await update.message.reply_text("Blacklist:\n" + "\n".join(str(i) for i in BLACK_LIST))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = (
        f"Your first name: {update.effective_user.first_name}\n"+
        f"Your last name: {update.effective_user.last_name}\n"
        f"Your username: @{update.effective_user.username}\n"
        f"Your telegram ID: {user_id}"
    )
    if (user_id in ADMINS_IDS): text += "\nYou are an admin"
    await update.message.reply_text(text)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    photos = await update.effective_user.get_profile_photos(limit=1)
    text = (
        f"Your first name: {update.effective_user.first_name}\n"
        f"Your last name: {update.effective_user.last_name}\n"
        f"Your username: @{update.effective_user.username}\n"
        f"Your telegram ID: {user_id}"
    )
    if (user_id in ADMINS_IDS): text+="\nYou are an admin"

    if photos.total_count > 0:
        photo = photos.photos[0][-1].file_id
        await update.message.reply_photo(photo=photo, caption=text)
    else: await update.message.reply_text(text)

def main():
    app = Application.builder().token(API_TOKEN).connect_timeout(60).read_timeout(60).build()

    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(ChosenInlineResultHandler(chosen_inline_result))
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    app.add_handler(CommandHandler("notifications", notifications_command))
    app.add_handler(CommandHandler("block", block_command))
    app.add_handler(CommandHandler("unblock", unblock_command))
    app.add_handler(CommandHandler("blacklist", blacklist_command))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    load_config()
    load()
    main()
