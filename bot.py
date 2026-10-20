import logging
import random
import string
import requests
import pyotp
import threading
import time
import re
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ================= কনফিগারেশন =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY") # tmailor ব্যবহার করলেও রাখা হলো

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
user_states = {}

# ================= হেল্পার ফাংশন =================
def api_call(action, data):
    try:
        payload = {"action": action}
        payload.update(data)
        response = requests.post(WEB_APP_URL, json=payload, timeout=15)
        return response.json()
    except Exception as e:
        logging.error(f"API Error: {e}")
        return {"status": "error", "message": str(e)}

def get_random_username():
    try:
        with open("usernames.txt", "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        if not lines: return "user_" + ''.join(random.choices(string.digits, k=5))
        chosen = random.choice(lines)
        lines.remove(chosen)
        with open("usernames.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return chosen
    except: return "user_" + ''.join(random.choices(string.digits, k=5))

def generate_random_password():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

# Temp Mail API (RapidAPI Privatix)
TM_HOST = "privatix-temp-mail-v1.p.rapidapi.com"
TM_BASE = f"https://{TM_HOST}"

def get_temp_mail():
    if not RAPIDAPI_KEY: return None, None, None
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": TM_HOST}
    try:
        domains_res = requests.get(f"{TM_BASE}/request/domains/", headers=headers, timeout=15)
        domains = domains_res.json()
        if not isinstance(domains, list) or not domains: return None, None, None
        random_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        domain = random.choice(domains)
        email = f"{random_name}{domain}"
        email_md5 = hashlib.md5(email.lower().encode()).hexdigest()
        return email, email_md5, random_name.capitalize()
    except Exception as e:
        logging.error(f"TempMail Error: {e}")
        return None, None, None

def fetch_email_code(email_md5, is_2fa_code=False):
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": TM_HOST}
    try:
        url = f"{TM_BASE}/request/mail/id/{email_md5}/"
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200: return None
        messages = res.json()
        if isinstance(messages, dict) and "error" in messages: return None
        if not isinstance(messages, list) or len(messages) == 0: return None
        
        for msg in messages:
            subject = msg.get("mail_subject", "").lower()
            if is_2fa_code:
                if "authenticate" in subject or "meta" in subject:
                    combined = (msg.get("mail_html", "") or "") + " " + (msg.get("mail_text", "") or "")
                    combined = re.sub(r'<[^>]+>', ' ', combined)
                    combined = re.sub(r'\s+', ' ', combined).strip()
                    match = re.search(r'\b\d{8}\b', combined)
                    if match: return match.group(0)
            else:
                if "instagram" in subject or "confirmation" in subject:
                    combined = (msg.get("mail_html", "") or "") + " " + (msg.get("mail_text", "") or "")
                    combined = re.sub(r'<[^>]+>', ' ', combined)
                    combined = re.sub(r'\s+', ' ', combined).strip()
                    match = re.search(r'\b\d{6}\b', combined)
                    if match: return match.group(0)
                        
        for msg in messages:
            combined = (msg.get("mail_html", "") or "") + " " + (msg.get("mail_text", "") or "")
            combined = re.sub(r'<[^>]+>', ' ', combined)
            combined = re.sub(r'\s+', ' ', combined).strip()
            if is_2fa_code: match = re.search(r'\b\d{8}\b', combined)
            else: match = re.search(r'\b\d{6}\b', combined)
            if match: return match.group(0)
        return None
    except: return None

def get_main_reply_keyboard():
    keyboard = [
        [KeyboardButton("💰 Balance"), KeyboardButton("📋 Tasks")],
        [KeyboardButton("💸 Withdraw"), KeyboardButton("🎮 Games")],
        [KeyboardButton("🏆 Top"), KeyboardButton("🎁 Promocode")],
        [KeyboardButton("👤 Profile")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================= হ্যান্ডলারস =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    api_call("getUser", {"telegram_id": user.id})
    await update.message.reply_text(f"স্বাগতম {user.first_name}!\nনিচের মেনু থেকে অপশন বেছে নিন:", reply_markup=get_main_reply_keyboard())

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    state = user_states.get(user_id)

    if text == "💰 Balance":
        res = api_call("getUser", {"telegram_id": user_id})
        bal = res["data"]["balance"] if res.get("status") == "success" else 0
        await update.message.reply_text(f"💰 আপনার বর্তমান ব্যালেন্স: **{bal:.3f} tk**", parse_mode="Markdown", reply_markup=get_main_reply_keyboard())

    elif text == "📋 Tasks":
        keyboard = [[InlineKeyboardButton("🚀 Start Task", callback_data="start_task")], [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]]
        await update.message.reply_text("📋 টাস্ক মেনু:\nনতুন টাস্ক শুরু করতে Start Task এ ক্লিক করুন।", reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == "💸 Withdraw":
        user_states[user_id] = {"state": "WAIT_WITHDRAW"}
        await update.message.reply_text(
            "💸 উইথড্র করতে আপনার **বিকাশ নাম্বার** এবং **পরিমাণ** লিখুন।\n(যেমন: 017XXXXXXXX 100)\n\n"
            "⚠️ সর্বনিম্ন উইথড্র ১০০ টাকা এবং প্রতি উইথড্রতে ৫ টাকা ফি কাটা হবে।", 
            reply_markup=ReplyKeyboardRemove()
        )

    elif text == "🎮 Games":
        await update.message.reply_text("🎮 গেমস সেকশনটি খুব শীঘ্রই আসছে!", reply_markup=get_main_reply_keyboard())

    elif text == "🏆 Top":
        res = api_call("getTop", {})
        msg = "🏆 **ডেইলি টপ ৫ ইউজার**\n\n"
        if res.get("status") == "success":
            for i, u in enumerate(res["data"]):
                msg += f"{i+1}. {u['name']} - {u['total']:.2f} tk\n"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_reply_keyboard())

    elif text == "🎁 Promocode":
        await update.message.reply_text("🎁 প্রোমোকোড সেকশনটি খুব শীঘ্রই আসছে!", reply_markup=get_main_reply_keyboard())

    elif text == "👤 Profile":
        res = api_call("getUser", {"telegram_id": user_id})
        if res.get("status") == "success":
            u = res["data"]
            msg = f"👤 **প্রোফাইল**\n\nName: {update.effective_user.first_name}\nUID: `{u['id']}`\nTotal Earning: **{u['total']:.3f} tk**"
        else: msg = "প্রোফাইল লোড করা যায়নি।"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_reply_keyboard())

    elif state:
        if state.get("state") == "WAIT_WITHDRAW":
            parts = text.split()
            if len(parts) != 2:
                await update.message.reply_text("ফরম্যাট ভুল। এভাবে দিন: 017XXXXXXXX 100", reply_markup=ReplyKeyboardRemove())
                return
                
            bkash, amount_str = parts[0], parts[1]
            try: amount = float(amount_str)
            except:
                await update.message.reply_text("টাকার পরিমাণ সঠিক সংখ্যায় দিন।", reply_markup=ReplyKeyboardRemove())
                return
                
            if amount < 100:
                await update.message.reply_text("❌ সর্বনিম্ন ১০০ টাকা উইথড্র করা যাবে।", reply_markup=ReplyKeyboardRemove())
                return
                
            user_res = api_call("getUser", {"telegram_id": user_id})
            current_bal = user_res["data"]["balance"] if user_res.get("status") == "success" else 0
            
            if current_bal < amount:
                await update.message.reply_text(f"❌ আপনার অ্যাকাউন্টে পর্যাপ্ত টাকা নেই।\n\nআপনার বর্তমান ব্যালেন্স: {current_bal:.3f} tk", reply_markup=get_main_reply_keyboard())
                del user_states[user_id]
                return

            final_amount = amount - 5
            api_call("withdraw", {"telegram_id": user_id, "bkash": bkash, "amount": final_amount})
            del user_states[user_id]
            
            await update.message.reply_text(
                f"✅ আপনার অনুরোধটি গ্রহণ করা হয়েছে।\n\n"
                f"বিকাশ: {bkash}\n"
                f"উইথড্র এমাউন্ট: {amount} tk\n"
                f"ফি: 5 tk\n"
                f"আপনি পাবেন: {final_amount} tk\n\n"
                f"২৪ ঘণ্টার মধ্যে আপনার বিকাশে টাকা যুক্ত হয়ে যাবে।", 
                reply_markup=get_main_reply_keyboard()
            )

        # 2FA Key ১ম বার
        elif state.get("state") == "WAIT_2FA_KEY_1":
            two_fa_key = text.strip().replace(" ", "").upper()
            try:
                totp = pyotp.TOTP(two_fa_key)
                generated_code = totp.now()
                state["twoFA"] = two_fa_key
                state["state"] = "WAIT_2FA_KEY_2"
                
                keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]]
                base_text = f"✅ **টাস্ক ডিটেইলস**\n\n📧 Email: `{state['email']}`\n🔑 Password: `{state['password']}`\n👤 First Name: `{state['firstName']}`\n🆔 Login: `{state['login']}`\n\n"
                await update.message.reply_text(base_text + f"✅ আপনার 2FA key থেকে কোড তৈরি হয়েছে: `{generated_code}`\n\n🔑 **নিরাপত্তার জন্য অনুগ্রহ করে আপনার 2FA Key টি আবারও দিন:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception:
                await update.message.reply_text("❌ 2FA Key টি সঠিক নয়। আবার সঠিক Key দিন।", reply_markup=ReplyKeyboardRemove())
                
        # 2FA Key ২য় বার
        elif state.get("state") == "WAIT_2FA_KEY_2":
            two_fa_key_2 = text.strip().replace(" ", "").upper()
            
            if two_fa_key_2 != state["twoFA"]:
                await update.message.reply_text("❌ দুইবারের 2FA Key মিলছে না। অনুগ্রহ করে আবার প্রথম থেকে Key দিন।", reply_markup=ReplyKeyboardRemove())
                state["state"] = "WAIT_2FA_KEY_1"
                return
                
            try:
                totp = pyotp.TOTP(two_fa_key_2)
                generated_code = totp.now()
                state["state"] = "COMPLETE_READY"
                
                # এখানে নতুন 'Get Code' বাটন যোগ করা হয়েছে
                keyboard = [
                    [InlineKeyboardButton("🔄 Get Code", callback_data="refresh_2fa_code")],
                    [InlineKeyboardButton("✅ Complete", callback_data="complete_task")], 
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]
                ]
                base_text = f"✅ **টাস্ক ডিটেইলস**\n\n📧 Email: `{state['email']}`\n🔑 Password: `{state['password']}`\n👤 First Name: `{state['firstName']}`\n🆔 Login: `{state['login']}`\n\n"
                await update.message.reply_text(base_text + f"✅ দুইবারের Key মিলেছে! কোড: `{generated_code}`\n\nকোডটি পরিবর্তন হলে **Get Code** এ ক্লিক করুন অথবা **Complete** এ ক্লিক করুন।", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception:
                await update.message.reply_text("❌ 2FA Key টি সঠিক নয়। আবার সঠিক Key দিন।", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("অনুগ্রহ করে নিচের মেনু থেকে অপশন বেছে নিন।", reply_markup=get_main_reply_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "cancel_task":
        if user_id in user_states: del user_states[user_id]
        await query.edit_message_text("❌ টাস্ক বাতিল করা হলো।")
        await query.message.reply_text("মেইন মেনু:", reply_markup=get_main_reply_keyboard())

    elif data == "start_task":
        email, email_md5, first_name = get_temp_mail()
        if not email:
            await query.edit_message_text("❌ ইমেইল সার্ভারে সমস্যা হচ্ছে। কিছুক্ষণ পর চেষ্টা করুন।")
            return
        password = generate_random_password()
        login = get_random_username()
        user_states[user_id] = {"state": "WAIT_EMAIL_CODE", "email": email, "token": email_md5, "password": password, "firstName": first_name, "login": login, "twoFA": ""}
        
        text = f"✅ **টাস্ক ডিটেইলস**\n\n📧 Email: `{email}`\n🔑 Password: `{password}`\n👤 First Name: `{first_name}`\n🆔 Login: `{login}`\n\nএই তথ্যগুলো ব্যবহার করে লগইন করুন এবং নিচের **Get Code** এ ক্লিক করুন।"
        keyboard = [[InlineKeyboardButton("📩 Get Code", callback_data="get_email_code")], [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "get_email_code":
        state = user_states.get(user_id)
        if not state: return
        await query.message.reply_text("⏳ ইমেইল চেক করা হচ্ছে...")
        code = None
        for _ in range(3):
            code = fetch_email_code(state["token"], is_2fa_code=False)
            if code: break
            await asyncio.sleep(5)
            
        base_text = f"✅ **টাস্ক ডিটেইলস**\n\n📧 Email: `{state['email']}`\n🔑 Password: `{state['password']}`\n👤 First Name: `{state['firstName']}`\n🆔 Login: `{state['login']}`\n\n"
        if code:
            text = base_text + f"✅ আপনার ১ম কোড: `{code}`\n\nএখন **Get Code for 2** এ ক্লিক করুন।"
            keyboard = [[InlineKeyboardButton("📩 Get Code for 2", callback_data="get_2fa_code")], [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]]
        else:
            text = base_text + "❌ এখনো কোনো কোড আসেনি। কিছুক্ষণ পর চেষ্টা করুন।"
            keyboard = [[InlineKeyboardButton("🔄 Try Again", callback_data="get_email_code")], [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]]
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "get_2fa_code":
        state = user_states.get(user_id)
        if not state: return
        await query.message.reply_text("⏳ ৮-ডিজিটের কোড চেক করা হচ্ছে...")
        code = None
        for _ in range(3):
            code = fetch_email_code(state["token"], is_2fa_code=True)
            if code: break
            await asyncio.sleep(5)
            
        base_text = f"✅ **টাস্ক ডিটেইলস**\n\n📧 Email: `{state['email']}`\n🔑 Password: `{state['password']}`\n👤 First Name: `{state['firstName']}`\n🆔 Login: `{state['login']}`\n\n"
        if code:
            text = base_text + f"✅ আপনার ২য় কোড (৮ ডিজিট): `{code}`\n\nএখন **Enter Key** এ ক্লিক করে 2FA key দিন।"
            keyboard = [[InlineKeyboardButton("🔑 Enter Key", callback_data="enter_2fa")], [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]]
        else:
            text = base_text + "❌ ৮-ডিজিটের কোড আসেনি। চেষ্টা আবার করুন।"
            keyboard = [[InlineKeyboardButton("🔄 Try Again", callback_data="get_2fa_code")], [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]]
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "enter_2fa":
        state = user_states.get(user_id)
        if not state: return
        state["state"] = "WAIT_2FA_KEY_1"
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]]
        text = f"✅ **টাস্ক ডিটেইলস**\n\n📧 Email: `{state['email']}`\n🔑 Password: `{state['password']}`\n👤 First Name: `{state['firstName']}`\n🆔 Login: `{state['login']}`\n\n🔑 অনুগ্রহ করে আপনার **2FA Key** দিন (১ম বার):"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        await query.message.reply_text("অনুগ্রহ করে নিচে 2FA Key টাইপ করুন:", reply_markup=ReplyKeyboardRemove())

    # নতুন যোগ করা Get Code বাটনের লজিক
    elif data == "refresh_2fa_code":
        state = user_states.get(user_id)
        if not state or not state.get("twoFA"): return
        try:
            totp = pyotp.TOTP(state["twoFA"])
            new_code = totp.now()
            
            keyboard = [
                [InlineKeyboardButton("🔄 Get Code", callback_data="refresh_2fa_code")],
                [InlineKeyboardButton("✅ Complete", callback_data="complete_task")], 
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]
            ]
            base_text = f"✅ **টাস্ক ডিটেইলস**\n\n📧 Email: `{state['email']}`\n🔑 Password: `{state['password']}`\n👤 First Name: `{state['firstName']}`\n🆔 Login: `{state['login']}`\n\n"
            await query.message.reply_text(base_text + f"🔄 নতুন কোড জেনারেট হয়েছে: `{new_code}`\n\nকোডটি পরিবর্তন হলে আবার **Get Code** এ ক্লিক করুন অথবা **Complete** এ ক্লিক করুন।", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await query.message.reply_text("❌ কোড জেনারেট করা যায়নি।")

    elif data == "complete_task":
        state = user_states.get(user_id)
        if not state: return
        
        payload = {
            "telegram_id": user_id,
            "email": state["email"],
            "password": state["password"],
            "firstName": state["firstName"],
            "login": state["login"],
            "twoFA": state["twoFA"]
        }
        
        res = api_call("addTask", payload)
        print(f"DEBUG RESPONSE: {res}")
        
        if res.get("status") == "success":
            del user_states[user_id]
            await query.edit_message_text("✅ **Your data has received. Soon you will get feedback.**")
            await query.message.reply_text("মেইন মেনু:", reply_markup=get_main_reply_keyboard())
        else:
            await query.edit_message_text("❌ ডেটা সেভ করা যায়নি। অনুগ্রহ করে আবার চেষ্টা করুন বা অ্যাডমিনকে জানান।")

# ================= অটো চেকার থ্রেড =================
def auto_checker(app):
    while True:
        try:
            res = api_call("checkResults", {})
            if res.get("status") == "success" and res.get("data"):
                for item in res["data"]:
                    if item["type"] == "task_approved":
                        msg = f"🎉 Congratulations! You've earned **{item['earning']} tk** for this ID: `{item['login']}`"
                        asyncio.run_coroutine_threadsafe(app.bot.send_message(chat_id=item["telegram_id"], text=msg, parse_mode="Markdown"), app.loop)
                    elif item["type"] == "task_rejected":
                        msg = f"❌ দুঃখিত, আপনার টাস্কটি (ID: `{item['login']}`) বাতিল করা হয়েছে।\n\n**কারণ:** {item['reason']}"
                        asyncio.run_coroutine_threadsafe(app.bot.send_message(chat_id=item["telegram_id"], text=msg, parse_mode="Markdown"), app.loop)
                    elif item["type"] == "withdraw_paid":
                        msg = f"✅ আপনার উইথড্র রিকোয়েস্টটি সফলভাবে পেইড করা হয়েছে!\n\nআপনার বিকাশে **{item['amount']} tk** পাঠানো হয়েছে।"
                        asyncio.run_coroutine_threadsafe(app.bot.send_message(chat_id=item["telegram_id"], text=msg, parse_mode="Markdown"), app.loop)
                    elif item["type"] == "withdraw_rejected":
                        msg = f"❌ দুঃখিত, আপনার উইথড্র রিকোয়েস্টটি বাতিল করা হয়েছে।\n\n**কারণ:** {item['reason']}\n\nআপনি আবার চেষ্টা করতে পারেন।"
                        asyncio.run_coroutine_threadsafe(app.bot.send_message(chat_id=item["telegram_id"], text=msg, parse_mode="Markdown"), app.loop)
        except Exception as e:
            logging.error(f"Auto Check Error: {e}")
        time.sleep(60)

def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN is not set in environment variables!")
        return
        
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    checker_thread = threading.Thread(target=auto_checker, args=(app,), daemon=True)
    checker_thread.start()
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
