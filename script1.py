import telebot
from telebot import types
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timedelta

# === КОНФИГУРАЦИЯ ===

bot = telebot.TeleBot(TOKEN)
DB_NAME = "vpn_bot.db"

# === ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ===
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            expiry_date DATETIME,
            vless_link TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT expiry_date, vless_link FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_user_subscription(user_id, username, days, link):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now = datetime.now()
    current_data = get_user_data(user_id)

    if current_data and current_data[0]:
        expiry_dt = datetime.strptime(current_data[0], '%Y-%m-%d %H:%M:%S')
        new_expiry = max(now, expiry_dt) + timedelta(days=days)
    else:
        new_expiry = now + timedelta(days=days)

    new_expiry_str = new_expiry.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, expiry_date, vless_link)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, new_expiry_str, link))
    conn.commit()
    conn.close()
    return new_expiry_str

# === ФОНОВАЯ ПРОВЕРКА ===
def auto_delete_expired():
    while True:
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("SELECT user_id, username FROM users WHERE expiry_date < ? AND vless_link IS NOT NULL", (now_str,))
            expired_users = cursor.fetchall()

            for u_id, u_name in expired_users:
                email = f"user_{u_id}"
                subprocess.run(['/usr/local/bin/bot_rmuser.sh', email])
                cursor.execute("UPDATE users SET vless_link = NULL WHERE user_id = ?", (u_id,))
                conn.commit()
                try:
                    bot.send_message(u_id, "🛑 Срок вашей подписки истек. Доступ отключен.")
                except: pass
            conn.close()
        except Exception as e:
            print(f"Ошибка проверки: {e}")
        time.sleep(600)

# === ОБРАБОТКА КОМАНД ===
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👤 Моя подписка", "💳 Купить подписку")
    markup.add("ℹ️ Инфо", "🆘 Поддержка")
    return markup

@bot.message_handler(commands=['start'])
def welcome(message):
    init_db()
    bot.send_message(message.chat.id, f"Привет, {message.from_user.first_name}! Это VPN бот.", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "👤 Моя подписка")
def my_sub(message):
    data = get_user_data(message.from_user.id)
    if data and data[1]:
        expiry, link = data
        bot.send_message(message.chat.id, f"✅ Подписка активна до: {expiry}\n\nТвой ключ:\n<code>{link}</code>", parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, "❌ У вас нет активной подписки.")

@bot.message_handler(func=lambda m: m.text == "💳 Купить подписку")
def buy_menu(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("1 месяц - 200₽ (ТЕСТ)", callback_data="buy_30"))
    bot.send_message(message.chat.id, "Выберите период (сейчас работает в тестовом режиме — сразу выдает ключ):", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_purchase(call):
    days = int(call.data.split("_")[1])
    user_id = call.from_user.id
    email = f"user_{user_id}"

    # Имитация оплаты. В будущем здесь должен быть вызов платежного шлюза
    result = subprocess.run(['/usr/local/bin/bot_newuser.sh', email], capture_output=True, text=True)
    link = result.stdout.strip()

    if "vless://" in link:
        expiry_date = update_user_subscription(user_id, email, days, link)
        bot.edit_message_text(f"🎉 Готово! Подписка активна до {expiry_date}\n\nКлюч:\n<code>{link}</code>",
                              call.message.chat.id, call.message.message_id, parse_mode="HTML")
    else:
        bot.send_message(user_id, "⚠️ Ошибка сервера при создании ключа.")

@bot.message_handler(func=lambda m: m.text == "ℹ️ Инфо")
def info(message):
    bot.send_message(message.chat.id, "Скачайте приложение:\n- Android: v2rayNG\n- iOS: FoXray или Streisand\n- Windows: Nekoray")

@bot.message_handler(func=lambda m: m.text == "🆘 Поддержка")
def support(message):
    bot.send_message(message.chat.id, "По всем вопросам: @твой_ник")

if __name__ == '__main__':
    init_db()
    threading.Thread(target=auto_delete_expired, daemon=True).start()
    bot.polling(non_stop=True)





