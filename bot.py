import asyncio
import json
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, InlineQueryHandler, CommandHandler, ChosenInlineResultHandler
from telegram.error import BadRequest

API_TOKEN = ""
ADMINS_IDS: list[int] = list()

BLACK_LIST: set[int] = set()
NOTIFICATIONS_LIST: set[int] = set()

CONFIG_LIST = "config.jsonl"
LIST = "list.jsonl"

secret_messages: dict[str, tuple] = {}

SPECIAL_CHARS = set("!&")
FLAG_MAP = {
    '!': "exc_flag",
    '&': "vis_flag"
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
        f.write(json.dumps(list(NOTIFICATIONS_LIST)))

def load() -> None:
    global BLACK_LIST, NOTIFICATIONS_LIST
    try:
        with open(LIST, 'r', encoding="utf-8") as f:
            BLACK_LIST = set(json.loads(f.readline().strip()))
            NOTIFICATIONS_LIST = set(json.loads(f.readline().strip()))
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
    exc_flag, vis_flag = flags["exc_flag"], flags["vis_flag"]

    if exc_flag:
        secret_messages[key] = (user_id, target_id, not_for_you_text, message, exc_flag, vis_flag)
        to_target_desc = f"To anyone but {target_id}: {message}"
        to_others_desc = f"To {target_id}: {not_for_you_text}"
    else:
        secret_messages[key] = (user_id, target_id, message, not_for_you_text, exc_flag, vis_flag)
        to_target_desc = f"To {target_id}: {message}"
        to_others_desc = f"To anyone: {not_for_you_text}"

    keyboard = InlineKeyboardMarkup([ [InlineKeyboardButton("Message", callback_data=key)] ])
    return InlineQueryResultArticle(
        id = key,
        title = "Send message",
        description = f"{to_target_desc}\nText in message: {placeholder_text}\n{to_others_desc}",
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
        input_message_content=InputTextMessageContent(message_text=info_text),
    )

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.inline_query.from_user.id
    if user_id in BLACK_LIST: return

    query = update.inline_query.query
    results = [ ]

    if query.strip().lower() == "info":
        results.append(build_info(update.inline_query.from_user, user_id))
    else:
        message_result = build_utumessage(user_id, query)
        if message_result: results.append(message_result)

    try: await update.inline_query.answer(results, cache_time=10, is_personal=True)
    except BadRequest: return

async def chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = update.chosen_inline_result
    key = result.result_id
    message_data = secret_messages.get(key)
    if not message_data: return
    await notify_admins(context, f"New message sent from: {message_data[0]}")

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    clicker_id = query.from_user.id
    if clicker_id in BLACK_LIST: return
    clicker_username = query.from_user.username

    message_key = query.data
    message_data = secret_messages.get(message_key)

    if not message_data:
        try: await query.answer(text="No message in temp data.", show_alert=True)
        except BadRequest: return
        return

    text = ""

    sender = message_data[0]
    target = message_data[1]

    target_text = message_data[2]
    other_text = message_data[3]

    exc_flag = message_data[4]

    if clicker_id == sender:
        text = f"Message for {target}:\n{target_text}\n\nMessage for anyone:\n{other_text}\n\n\nMessage id is: {message_key}"
    elif clicker_id == target or clicker_username == target[1:]:
        if exc_flag: text = f"Message:\n{target_text}"
        elif message_data[5]: text = f"Message for you:\n{target_text}\n\nMessage for anyone:\n{other_text}\n\n\nMessage id is: {message_key}"
        else: text = f"Message:\n{target_text}\n\n\nMessage id is: {message_key}"
    else:
        if exc_flag and message_data[5]: text = f"Message for anyone:\n{other_text}\n\nMessage for {target}:\n{target_text}"
        else: text = f"Message:\n{other_text}"

    await query.answer(text=text, show_alert=True)
    await notify_admins(context,f"User @{clicker_username} ({clicker_id}) clicked on {message_key}")

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
    app = Application.builder().token(API_TOKEN).connect_timeout(100).read_timeout(100).build()

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
