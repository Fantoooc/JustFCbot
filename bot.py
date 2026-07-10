import asyncio
import json
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, InlineQueryHandler, CommandHandler, ChosenInlineResultHandler

API_TOKEN = "x"

ADMINS_IDS = [x]
BLACK_LIST = []
BLACKLIST_FILE = "blacklist.json"

secret_messages: dict[str, dict] = {}
notified_admins: set[int] = set()

def load_blacklist() -> None:
    global BLACK_LIST
    try:
        with open(BLACKLIST_FILE, 'r', encoding="utf-8") as f:
            BLACK_LIST[:] = json.load(f)
    except FileNotFoundError:
        save_blacklist()

def save_blacklist() -> None:
    with open(BLACKLIST_FILE, 'w', encoding="utf-8") as f:
        json.dump(BLACK_LIST, f)

async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    for admin_id in notified_admins:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text)
        except Exception as e:
            print(f"Failed to notify admin {admin_id}: {e}")

async def resolve_target(raw: str, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    if raw.lstrip('-').isdigit(): return int(raw)
    if raw.startswith('@'):
        try:
            chat = await context.bot.get_chat(raw)
            return chat.id
        except Exception as e:
            # print(f"No chat with user {raw}, {e}")
            return None
    return None

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.inline_query.from_user.id
    if user_id in BLACK_LIST: return

    results = []

    user = update.inline_query.from_user
    info_text = (
        f"Your first name: {user.first_name or '-'}\n"
        f"Your last name: {user.last_name or '-'}\n"
        f"Your username: @{user.username or '-'}\n"
        f"Your telegram ID: {user_id}"
    )
    if user_id in ADMINS_IDS: info_text += "\nYou are an admin"

    results.append(
        InlineQueryResultArticle(
            id = "info",
            title = "Send my info",
            description = info_text.replace("\n", " | "),
            input_message_content = InputTextMessageContent(message_text = info_text)
        )
    )

    raw = update.inline_query.query
    parts = [ part.strip() for part in raw.split('|') ]

    if len(parts) >= 1 and parts[0]:
        main = parts[0].split(maxsplit = 1)
        if len(main) >= 2:
            raw_id = main[0].strip()
            exc_mode = raw_id.startswith('!')
            id_part = raw_id[1:] if exc_mode else raw_id
            target_id = await resolve_target(id_part, context)
            text = main[1].strip()
            if target_id is not None and text:
                placeholder_text = parts[1].strip() if len(parts) >= 2 and parts[1].strip() else "Message hided."
                not_for_you_text = parts[2].strip() if len(parts) >= 3 and parts[2].strip() else "This message is not for you."

                key = uuid.uuid4().hex[:16]
                if exc_mode:
                    secret_messages[key] = {
                        "sender_id": user_id,
                        "target_id": target_id,
                        "text": not_for_you_text,
                        "not_for_you_text": text
                    }
                else:
                    secret_messages[key] = {
                        "sender_id": user_id,
                        "target_id": target_id,
                        "text": text,
                        "not_for_you_text": not_for_you_text
                    }
                keyboard = InlineKeyboardMarkup([ [InlineKeyboardButton("Message", callback_data=key)] ])

                results.append(
                    InlineQueryResultArticle(
                        id = key,
                        title = "Send message",
                        description = f"To {f'anyone but {target_id}' if exc_mode else target_id}: {text}\nText in message: {placeholder_text}\nTo {target_id if exc_mode else 'anyone'}: {not_for_you_text}",
                        input_message_content = InputTextMessageContent(message_text = placeholder_text),
                        reply_markup = keyboard
                    )
                )
    await update.inline_query.answer(results, cache_time=30, is_personal=True)

async def chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = update.chosen_inline_result
    key = result.result_id
    message_data = secret_messages.get(key)
    if not message_data: return
    await notify_admins(context, f"New message sent from: {message_data['sender_id']}")

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    clicker_id = query.from_user.id
    if clicker_id in BLACK_LIST: return
    clicker_username = query.from_user.username

    message_key = query.data
    message_data = secret_messages.get(message_key)

    if not message_data:
        await query.answer(text="No message in temp data.", show_alert=True)
        return

    if clicker_id == message_data["sender_id"]:
        await query.answer(text=f"Message for {message_data['target_id']}:\n\n{message_data['text']}\n\nMessage for anyone:\n\n{message_data['not_for_you_text']}", show_alert=True)
    elif clicker_id == message_data["target_id"]:
        await query.answer(text=f"Message:\n\n{message_data['text']}", show_alert=True)
    else: await query.answer(text=message_data["not_for_you_text"], show_alert=True)
    await notify_admins(context,f"User @{clicker_username} ({clicker_id}) clicked on {message_key}")

async def notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMINS_IDS:
        return
    if user_id in notified_admins:
        notified_admins.discard(user_id)
        await update.message.reply_text("Notifications disabled.")
    else:
        notified_admins.add(user_id)
        await update.message.reply_text("Notifications enabled.")

async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMINS_IDS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /block <id>")
        return
    try:
        target = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid id.")
        return

    if target in ADMINS_IDS:
        await update.message.reply_text("Can't block an admin.")
        return

    if target not in BLACK_LIST:
        BLACK_LIST.append(target)
        save_blacklist()
        await update.message.reply_text(f"User {target} blocked.")
    else:
        await update.message.reply_text(f"User {target} is already blocked.")


async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMINS_IDS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /unblock <id>")
        return
    try:
        target = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid id.")
        return

    if target in BLACK_LIST:
        BLACK_LIST.remove(target)
        save_blacklist()
        await update.message.reply_text(f"User {target} unblocked.")
    else:
        await update.message.reply_text(f"User {target} is not in the blacklist.")

async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMINS_IDS:
        return
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
    load_blacklist()
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
    main()
