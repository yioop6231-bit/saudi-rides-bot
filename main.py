import os
import sqlite3
import threading
from datetime import datetime
from flask import Flask
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

TELEGRAM_BOT_TOKEN = "8998678344:AAHJiR37P_XkrFBbaNZlqCPLzh3E_vDNLiE"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

def init_db():
    conn = sqlite3.connect("rides_master.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS rides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ride_type TEXT,
            region TEXT,
            details TEXT,
            contact TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            user_id INTEGER PRIMARY KEY,
            current_region TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

user_states = {}

REGIONS = {
    "reg_riyadh": "الرياض",
    "reg_west": "الغربية (جدة / مكة)",
    "reg_east": "المنطقة الشرقية",
    "reg_qassim": "القصيم",
    "reg_south": "المنطقة الجنوبية",
    "reg_north": "المنطقة الشمالية",
    "reg_travel": "خطوط سفر بين المدن (طريق سفر)"
}

RIDE_TYPES = {
    "type_single": "مشوار مباشر / فوري",
    "type_monthly": "تعاقد شهري / دوام / جامعة",
    "type_intercity": "سفر بين المدن",
    "type_parcel": "توصيل طرد / أمانة"
}

def get_main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("🙋‍♂️ أنا راكب (طلب مشوار جديد)"),
        KeyboardButton("🚗 طلبات مشاوير مدينتي الحالية")
    )
    kb.add(
        KeyboardButton("📍 تحديث مدينتي الحالية (للسائق)"),
        KeyboardButton("🛣️ وضع السفر بين المدن")
    )
    return kb

def get_driver_city(user_id):
    conn = sqlite3.connect("rides_master.db")
    c = conn.cursor()
    c.execute("SELECT current_region FROM drivers WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_driver_city(user_id, city):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = sqlite3.connect("rides_master.db")
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO drivers (user_id, current_region, updated_at)
        VALUES (?, ?, ?)
    """, (user_id, city, now_str))
    conn.commit()
    conn.close()

@bot.message_handler(commands=['start', 'help'])
def start_cmd(message):
    uid = message.from_user.id
    current_city = get_driver_city(uid) or "لم تُحدد بعد"
    welcome_text = (
        "🇸🇦 **شبكة مشاوير السعودية**\n\n"
        f"📍 **مدينتك المسجلة حالياً ككابتن:** `{current_city}`\n\n"
        "• **الراكب:** يحدد موقعه مع كل طلب جديد.\n"
        "• **السائق:** يستقبل طلبات منطقته المحددة فقط.\n\n"
        "👇 اختر الإجراء المطلوب:"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: True, content_types=['text'])
def handle_text(message):
    uid = message.from_user.id
    text = message.text.strip()

    if user_states.get(uid, {}).get("step") == "waiting_details":
        data = user_states.get(uid, {})
        ride_type = data.get("ride_type", "مشوار")
        region = data.get("region", "العامة")
        contact = f"@{message.from_user.username}" if message.from_user.username else f"ID: {uid}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        conn = sqlite3.connect("rides_master.db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO rides (user_id, ride_type, region, details, contact, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, ride_type, region, message.text, contact, now_str)
        )
        conn.commit()
        conn.close()

        user_states.pop(uid, None)
        bot.reply_to(
            message,
            f"✅ **تم نشر طلبك بنجاح في ({region})!**\n📌 النوع: {ride_type}\nسيظهر لكافة كباتن النطاق فوراً.",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
        return

    if "طلب مشوار جديد" in text or "راكب" in text:
        markup = InlineKeyboardMarkup()
        for code, name in RIDE_TYPES.items():
            markup.row(InlineKeyboardButton(name, callback_data=f"rtype_{code}"))
        bot.send_message(message.chat.id, "📋 **اختر نوع المشوار المطلوب:**", reply_markup=markup, parse_mode="Markdown")

    elif "طلبات مشاوير مدينتي الحالية" in text:
        city = get_driver_city(uid)
        if not city:
            markup = InlineKeyboardMarkup()
            for r_code, r_name in REGIONS.items():
                markup.row(InlineKeyboardButton(f"📍 {r_name}", callback_data=f"setcity_{r_code}"))
            bot.send_message(message.chat.id, "🚗 **يا كابتن، في أي مدينة أنت متواجد الآن؟**", reply_markup=markup, parse_mode="Markdown")
            return

        conn = sqlite3.connect("rides_master.db")
        c = conn.cursor()
        c.execute("SELECT id, ride_type, details, contact, created_at FROM rides WHERE region = ? ORDER BY id DESC LIMIT 5", (city,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            bot.send_message(message.chat.id, f"📍 لا توجد طلبات جديدة في **{city}** حالياً.", parse_mode="Markdown")
            return

        out = f"📋 **أحدث طلبات المشاوير في نطاقك ({city}):**\n━━━━━━━━━━━━━━━━━━━\n\n"
        for r in rows:
            out += f"🔹 طلب #{r[0]} ({r[1]})\n📝 {r[2]}\n📞 {r[3]}\n⏰ {r[4]}\n───────────────────\n"
        bot.send_message(message.chat.id, out, parse_mode="Markdown")

    elif "تحديث مدينتي الحالية" in text:
        markup = InlineKeyboardMarkup()
        for r_code, r_name in REGIONS.items():
            markup.row(InlineKeyboardButton(f"📍 {r_name}", callback_data=f"setcity_{r_code}"))
        bot.send_message(message.chat.id, "📍 **اختر مدينتك الجديدة:**", reply_markup=markup, parse_mode="Markdown")

    elif "وضع السفر بين المدن" in text:
        set_driver_city(uid, "خطوط سفر بين المدن (طريق سفر)")
        bot.send_message(
            message.chat.id,
            "🛣️ **تم تفعيل وضع السفر بين المدن!**\nستصلك فقط طلبات السفريات الطويلة والطرود.",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    else:
        bot.reply_to(message, "اختر من القائمة بالأسفل 👇", reply_markup=get_main_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def handle_cb(call):
    uid = call.from_user.id
    cid = call.message.chat.id
    bot.answer_callback_query(call.id)

    if call.data.startswith("setcity_"):
        r_code = call.data.replace("setcity_", "")
        chosen_city = REGIONS.get(r_code)
        set_driver_city(uid, chosen_city)
        bot.send_message(cid, f"✅ **تم تحديث موقعك ككابتن إلى:** `{chosen_city}`", parse_mode="Markdown")

    elif call.data.startswith("rtype_"):
        t_code = call.data.replace("rtype_", "")
        user_states[uid] = {"ride_type": RIDE_TYPES.get(t_code)}
        markup = InlineKeyboardMarkup()
        for r_code, r_name in REGIONS.items():
            markup.row(InlineKeyboardButton(r_name, callback_data=f"pickreg_{r_code}"))
        bot.send_message(cid, "📍 **في أي منطقة تحتاج المشوار؟**", reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("pickreg_"):
        r_code = call.data.replace("pickreg_", "")
        if uid not in user_states:
            user_states[uid] = {}
        user_states[uid]["region"] = REGIONS.get(r_code)
        user_states[uid]["step"] = "waiting_details"
        bot.send_message(
            cid,
            f"✍️ **اكتب تفاصيل مشوارك في ({REGIONS.get(r_code)}) ورقم تواصلك في رسالة واحدة:**",
            parse_mode="Markdown"
        )

app = Flask(__name__)

@app.route('/')
def home():
    return "Ride Matchmaker Bot is Active 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    print("🚀 البوت يعمل سحابياً بنجاح...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
