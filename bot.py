bot.py
import logging
import json
import os
from datetime import datetime
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

TOKEN = "7912032778:AAFcbxezfsJ5jgXqxglwM8wisZoW2jEB33w"
ADMIN_ID = 1818907334
DATA_FILE = "users_data.json"

WELCOME_BALANCE = 50
WELCOME_ROLLS = 10
REF_BONUS_BAL = 10
REF_BONUS_ROLLS = 1
MIN_WITHDRAW = 300

state = {
    "users": {},
    "channels": ["@OneStoreHai"],
    "qr_file_id": None
}

def load_state():
    global state
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                state = json.load(f)
            state.setdefault("users", {})
            state.setdefault("channels", [])
            state.setdefault("qr_file_id", None)
        except Exception:
            state = {"users": {}, "channels": [], "qr_file_id": None}

def save_state():
    with open(DATA_FILE, "w") as f:
        json.dump(state, f, indent=2)

def get_user(user_id: int):
    uid = str(user_id)
    u = state["users"].get(uid)
    if not u:
        u = {
            "balance": WELCOME_BALANCE,
            "premium_rolls": WELCOME_ROLLS,
            "referrals": [],
            "referred_by": None,
            "withdraw_requested": False,
            "created_at": datetime.utcnow().isoformat()
        }
        state["users"][uid] = u
        save_state()
    return u

async def is_subscribed(user_id: int, bot) -> bool:
    for ch in state.get("channels", []):
        try:
            member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status not in ["member", "creator", "administrator"]:
                return False
        except Exception:
            return False
    return True

def channel_join_keyboard():
    buttons = []
    for ch in state.get("channels", []):
        buttons.append([InlineKeyboardButton(text=ch, url=f"https://t.me/{ch.lstrip('@')}")])
    buttons.append([InlineKeyboardButton(text="I have joined", callback_data="check_join")])
    return InlineKeyboardMarkup(buttons)

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Dice Roll"), KeyboardButton("Balance")],
            [KeyboardButton("Buy Rolls"), KeyboardButton("Withdraw")],
            [KeyboardButton("Refer & Earn"), KeyboardButton("Help")],
        ],
        resize_keyboard=True,
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None:
        return
    uid = str(user.id)

    user_data = get_user(user.id)

    if context.args:
        arg = context.args[0].strip()
        if arg.isdigit():
            ref_uid = arg
            if ref_uid != uid and user_data.get("referred_by") is None:
                ref_user = get_user(int(ref_uid))
                ref_user["balance"] += REF_BONUS_BAL
                ref_user["premium_rolls"] += REF_BONUS_ROLLS
                ref_user.setdefault("referrals", []).append(uid)
                user_data["referred_by"] = ref_uid
                save_state()
                try:
                    await context.bot.send_message(
                        int(ref_uid),
                        f"You received referral bonus for inviting {user.first_name}!"
                    )
                except:
                    pass

    if state.get("channels"):
        if not await is_subscribed(user.id, context.bot):
            await context.bot.send_message(
                chat_id=user.id,
                text="Please join required channels",
                reply_markup=channel_join_keyboard()
            )
            return

    await context.bot.send_message(
        chat_id=user.id,
        text="Welcome!",
        reply_markup=main_menu_keyboard()
    )

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if await is_subscribed(uid, context.bot):
        await q.edit_message_text("Verified! Send /start again.")
    else:
        await q.edit_message_text("You have not joined all channels.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    user = update.effective_user
    uid = str(user.id)
    user_data = get_user(user.id)
    text = (update.message.text or "").strip()

    if state.get("channels"):
        if not await is_subscribed(user.id, context.bot):
            await update.message.reply_text(
                "Join channels first",
                reply_markup=channel_join_keyboard(),
            )
            return

    if text == "Dice Roll":
        if user_data["premium_rolls"] <= 0:
            await update.message.reply_text("No rolls left.")
            return
        dice_msg = await update.message.reply_dice()
        value = dice_msg.dice.value
        user_data["premium_rolls"] -= 1
        user_data["balance"] += value
        save_state()
        await update.message.reply_text(f"You rolled {value} and won ₹{value}")

    elif text == "Balance":
        await update.message.reply_text(
            f"Balance: ₹{user_data['balance']}\n"
            f"Rolls: {user_data['premium_rolls']}"
        )

    elif text == "Buy Rolls":
        if state.get("qr_file_id"):
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=state["qr_file_id"],
                caption="Pay ₹50 for 30 rolls."
            )
        else:
            await update.message.reply_text("QR not set by admin.")
        try:
            await context.bot.send_message(ADMIN_ID, f"User {uid} wants to buy rolls.")
        except:
            pass

    elif text == "Withdraw":
        if user_data["balance"] >= MIN_WITHDRAW:
            user_data["withdraw_requested"] = True
            save_state()
            await update.message.reply_text("Withdrawal request sent. Send UPI screenshot.")
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    f"Withdraw request from {uid} for ₹{user_data['balance']}"
                )
            except:
                pass
        else:
            await update.message.reply_text(f"Minimum withdrawal is ₹{MIN_WITHDRAW}")

    elif text == "Refer & Earn":
        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={uid}"
        await update.message.reply_text(f"Your referral link:\n{link}")

    elif text == "Help":
        await update.message.reply_text("Use the menu buttons.")

    else:
        await update.message.reply_text("Use the menu buttons.")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or not update.message.photo:
        return
    user = update.effective_user
    photo = update.message.photo[-1]
    caption = (update.message.caption or "").lower()

    if user.id == ADMIN_ID and "#qr" in caption:
        state["qr_file_id"] = photo.file_id
        save_state()
        await update.message.reply_text("QR updated.")
    else:
        try:
            await context.bot.send_photo(ADMIN_ID, photo.file_id, caption=f"From {user.id}")
        except:
            pass
        await update.message.reply_text("Sent to admin.")

def _normalize_channel(arg: str) -> str:
    arg = arg.strip()
    if arg.startswith("https://t.me/"):
        arg = "@" + arg.split("https://t.me/")[-1].strip("/")
    if not arg.startswith("@"):
        arg = "@" + arg
    return arg

async def addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /addchannel @username")
        return
    ch = _normalize_channel(context.args[0])
    if ch not in state["channels"]:
        state["channels"].append(ch)
        save_state()
    await update.message.reply_text(f"Added {ch}")

async def delchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /delchannel @username")
        return
    ch = _normalize_channel(context.args[0])
    if ch in state["channels"]:
        state["channels"].remove(ch)
        save_state()
    await update.message.reply_text(f"Removed {ch}")

async def listchannels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not state["channels"]:
        await update.message.reply_text("No channels set.")
    else:
        await update.message.reply_text("\n".join(state["channels"]))

async def release_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /release <user_id> <count>")
        return
    uid = context.args[0]
    count = int(context.args[1])
    user = get_user(int(uid))
    user["premium_rolls"] += count
    save_state()
    await update.message.reply_text(f"Released {count} rolls to {uid}")
    try:
        await context.bot.send_message(int(uid), f"Admin gave you {count} rolls.")
    except:
        pass

async def approve_withdraw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve_withdraw <user_id>")
        return
    uid = context.args[0]
    u = state["users"].get(uid)
    if not u or not u.get("withdraw_requested"):
        await update.message.reply_text("No withdraw request found.")
        return
    try:
        await context.bot.send_message(int(uid), "Your withdrawal is approved!")
    except:
        pass
    u["withdraw_requested"] = False
    u["balance"] = 0
    save_state()
    await update.message.reply_text(f"Approved withdrawal for {uid}")

def main():
    logging.basicConfig(level=logging.INFO)
    load_state()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="check_join"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    app.add_handler(CommandHandler("addchannel", addchannel))
    app.add_handler(CommandHandler("delchannel", delchannel))
    app.add_handler(CommandHandler("listchannels", listchannels))
    app.add_handler(CommandHandler("release", release_cmd))
    app.add_handler(CommandHandler("approve_withdraw", approve_withdraw_cmd))

    print("Bot Started...")
    app.run_polling()

if __name__ == "__main__":
    main()
