import telebot
import requests
import time
import threading
import os
import pyqrcode
import io
from telebot import types
from flask import Flask

# --- CONFIGURATION ---
BOT_TOKEN = "8392625389:AAEAxhr2cQAsIBy7lpTX_LSvvgNDBndVDJ0"
DB_URL = "https://earning-a9b0c-default-rtdb.firebaseio.com"
UPI_ID = "7897803277@freecharge"
FIXED_PASSWORD = "ZZZXXX"
NODE = "NUM_CRSH"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- SAFE FIREBASE HELPERS ---
def db_get(path):
    try:
        r = requests.get(f"{DB_URL}/{NODE}/{path}.json")
        return r.json() if r.ok else None
    except:
        return None

def db_put(path, data):
    try: requests.put(f"{DB_URL}/{NODE}/{path}.json", json=data)
    except: pass

def db_patch(path, data):
    try: requests.patch(f"{DB_URL}/{NODE}/{path}.json", json=data)
    except: pass

active_tasks = {}

# --- 100% REAL LOGIN LOOP (Browser Simulation) ---
def login_loop(number, chat_id):
    print(f"Started Login Loop for: {number}")
    login_url = "https://gainadda.com/login"
    
    # 100% Real Browser Headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/javascript, */*; q=0.01"
    }
    
    # Real Form Data
    payload = {
        "mobile": number, 
        "password": FIXED_PASSWORD
    }
    
    while active_tasks.get(number) == "on":
        try:
            # Check if admin blocked this number
            if db_get(f"blocks/{number}"):
                bot.send_message(chat_id, f"🚫 Your number {number} has been BLOCKED by Admin!")
                active_tasks[number] = "off"
                db_patch(f"tasks/{number}", {"status": "off"})
                break
            
            # Real Login Hit
            requests.post(login_url, headers=headers, data=payload, timeout=5)
        except:
            pass # Ignore network drops
        
        time.sleep(3) # Exact 3 seconds wait

# --- AUTO-PAYMENT MONITOR (Admin Success = Auto Unlock) ---
def payment_monitor():
    while True:
        try:
            payments = db_get("payments") or {}
            for utr, data in payments.items():
                if data.get("status") == "success" and not data.get("notified"):
                    user_id = data.get("user_id")
                    
                    # Mark as notified so it doesn't loop
                    db_patch(f"payments/{utr}", {"notified": True})
                    
                    # Auto Auth User
                    db_patch(f"users/{user_id}", {"auth": True})
                    
                    # Send VIP Success SMS
                    bot.send_message(user_id, "🎉 Your request successfully key automatically summit!\nEnjoy 😉")
                    
                    # Show Main Menu Automatically
                    main_menu_by_id(user_id)
        except Exception as e:
            pass
        time.sleep(4) # Check every 4 seconds

# --- HELPERS ---
def is_blocked(user_id):
    u_data = db_get(f"users/{user_id}")
    return u_data and u_data.get("blocked")

def main_menu_by_id(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("➕ Add Number", "📱 My Numbers")
    bot.send_message(chat_id, "🚀 *Bot is Ready!* Choose an option:", parse_mode="Markdown", reply_markup=markup)

# --- BOT COMMANDS & LOGIC ---

@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.chat.id)
    bot.clear_step_handler_by_chat_id(message.chat.id) # Fix overlap glitch
    
    if is_blocked(user_id):
        bot.send_message(user_id, "❌ Aapko Admin ne block kar diya hai!")
        return

    u_data = db_get(f"users/{user_id}")
    if not u_data:
        db_put(f"users/{user_id}", {"id": user_id, "username": message.from_user.username, "auth": False})
        u_data = {"auth": False}

    if u_data.get("auth"):
        main_menu_by_id(message.chat.id)
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔑 Enter Key", callback_data="enter_key"))
        markup.add(types.InlineKeyboardButton("💳 Create Key (₹5)", callback_data="buy_key"))
        bot.send_message(user_id, "👋 *Welcome to VIP NUM_CRSH Bot!*\n\nBot chalane ke liye Key zaruri hai.", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    user_id = str(call.message.chat.id)
    bot.answer_callback_query(call.id) # Stop Telegram Loading
    bot.clear_step_handler_by_chat_id(call.message.chat.id) # Fix overlap glitch
    
    if is_blocked(user_id):
        bot.send_message(user_id, "❌ You are blocked!")
        return
    
    if call.data == "buy_key":
        upi_uri = f"upi://pay?pa={UPI_ID}&pn=VIP_BOT&am=5&cu=INR"
        qr = pyqrcode.create(upi_uri)
        
        buffer = io.BytesIO()
        qr.png(buffer, scale=6)
        buffer.seek(0)
        
        msg = bot.send_photo(user_id, buffer, caption=f"💸 *Payment Amount: ₹5*\n\nUPI: `{UPI_ID}`\n\nPay karke 12 anko ka *UTR Number* yahan bhejein.", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_utr)

    elif call.data == "enter_key":
        msg = bot.send_message(user_id, "🔑 Apni Key yahan paste karein:")
        bot.register_next_step_handler(msg, verify_key)

    elif call.data.startswith("stop_"):
        num = call.data.split("_")[1]
        active_tasks[num] = "off"
        db_patch(f"tasks/{num}", {"status": "off"})
        bot.edit_message_text(f"Number {num} Stopped 🛑", user_id, call.message.message_id)

    elif call.data.startswith("on_"):
        num = call.data.split("_")[1]
        if db_get(f"blocks/{num}"):
            bot.send_message(user_id, "❌ Number blocked by Admin!")
            return
        active_tasks[num] = "on"
        db_patch(f"tasks/{num}", {"status": "on"})
        threading.Thread(target=login_loop, args=(num, user_id)).start()
        bot.edit_message_text(f"Number {num} is Active 🚀", user_id, call.message.message_id)

def process_utr(message):
    user_id = str(message.chat.id)
    bot.clear_step_handler_by_chat_id(message.chat.id)
    if is_blocked(user_id): return
    
    utr = message.text
    if utr and len(utr) == 12 and utr.isdigit():
        db_put(f"payments/{utr}", {"user_id": user_id, "utr": utr, "status": "pending"})
        bot.send_message(message.chat.id, "✅ *UTR Received!* Admin check kar raha hai, please wait...", parse_mode="Markdown")
    else:
        msg = bot.send_message(message.chat.id, "❌ Invalid UTR! Sahi 12 digit UTR dalein:")
        bot.register_next_step_handler(msg, process_utr)

def verify_key(message):
    user_id = str(message.chat.id)
    bot.clear_step_handler_by_chat_id(message.chat.id)
    if is_blocked(user_id): return
    
    key = message.text
    keys_data = db_get("keys") or {}
    if key in keys_data and not keys_data[key].get("used"):
        db_patch(f"keys/{key}", {"used": True, "used_by": user_id})
        db_patch(f"users/{user_id}", {"auth": True})
        bot.send_message(message.chat.id, "🎉 VIP Key Activated!")
        main_menu_by_id(message.chat.id)
    else:
        msg = bot.send_message(message.chat.id, "❌ Invalid ya Used Key! Dubara try karein:")
        bot.register_next_step_handler(msg, verify_key)

@bot.message_handler(func=lambda m: m.text == "➕ Add Number")
def ask_number(message):
    user_id = str(message.chat.id)
    bot.clear_step_handler_by_chat_id(message.chat.id)
    if is_blocked(user_id): return
    
    msg = bot.send_message(message.chat.id, "📱 Apna Number dalein (Without +91):")
    bot.register_next_step_handler(msg, start_number)

def start_number(message):
    user_id = str(message.chat.id)
    bot.clear_step_handler_by_chat_id(message.chat.id)
    if is_blocked(user_id): return
    
    num = message.text
    if num and len(num) >= 10 and num.isdigit():
        if db_get(f"blocks/{num}"):
            bot.send_message(message.chat.id, "❌ Ye number admin dwara block ho chuka hai!")
            return
            
        active_tasks[num] = "on"
        db_put(f"tasks/{num}", {"user_id": user_id, "status": "on", "number": num})
        threading.Thread(target=login_loop, args=(num, message.chat.id)).start()
        bot.send_message(message.chat.id, f"🚀 Number {num} Active ho gaya hai!")
    else:
        msg = bot.send_message(message.chat.id, "❌ Sahi number dalein:")
        bot.register_next_step_handler(msg, start_number)

@bot.message_handler(func=lambda m: m.text == "📱 My Numbers")
def my_numbers(message):
    user_id = str(message.chat.id)
    bot.clear_step_handler_by_chat_id(message.chat.id)
    if is_blocked(user_id): return
    
    tasks = db_get("tasks") or {}
    found = False
    for num, data in tasks.items():
        if data.get("user_id") == user_id:
            found = True
            markup = types.InlineKeyboardMarkup()
            if active_tasks.get(num) == "on" or data.get("status") == "on":
                active_tasks[num] = "on" 
                markup.add(types.InlineKeyboardButton("🛑 STOP", callback_data=f"stop_{num}"))
                status_text = "ON 🚀"
            else:
                markup.add(types.InlineKeyboardButton("🚀 ON", callback_data=f"on_{num}"))
                status_text = "OFF 🛑"
            bot.send_message(message.chat.id, f"📱 *Number:* `{num}`\nStatus: {status_text}", parse_mode="Markdown", reply_markup=markup)
    if not found:
        bot.send_message(message.chat.id, "Abhi tak koi number add nahi kiya.")

# --- RENDER WEB SERVER ---
@app.route('/')
def home(): return "VIP NUM_CRSH Bot is Running Smoothly!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    threading.Thread(target=payment_monitor).start() # <--- New Monitor Added!
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            time.sleep(5) 
