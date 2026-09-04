import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import smtplib
import time
import random
import threading
import logging
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = '8523492309:AAF1z6AdIrG9sE1BzU_3p7AuRYedOU5edXs'
bot = telebot.TeleBot(TOKEN)

# ==================== 13 ПОЧТ ====================
senders = {
    'dgdihdic@list.ru': 'oOoRNsDos0IOsKLsxKhX',
    'artem2289hd@list.ru': '6swc7w7oZdVoYpOPpKRg',
    'misha228088e@list.ru': 'aTKnJelVld5SMD1ZbBdk',
    'gsudgeudgd@list.ru': 'TLWEfZ2iW28ycUcH5Z79',
    'ospdbcod@list.ru': 'b01NdPamd0XexiZ4q8RA',
    'isoebdod@list.ru': 'g9eCe3CMQfRKEFD6HVAB',
    'kdpdncuf@list.ru': 'u1WqMGIEtFLQCLN7itp2',
    'djdkddddcc@internet.ru': 'KjFYSepvZRCBlVOzHtGH',
    'kldncibc782@internet.ru': 'YuzrHLohJ13GgAIUbmOz',
    'mihail.molodozhen@yandex.ru': 'fnqdjgxihupebqde',
    'michaelmolodozhen@yandex.ru': 'fzdbabvnaiqvxxtz',
    'durovvk@internet.ru': 'VyP9IznKizRg5PYE5LC1',
    'kotakbasss@internet.ru': 'e6H3o5Jje0INZZtgaVMy',
}

telegram_emails = [
    'abuse@telegram.org', 'support@telegram.org', 'stopCA@telegram.org',
    'dmca@telegram.org', 'info@telegram.org', 'sticker@telegram.org', 'recover@telegram.org'
]

user_data = {}
muted = {}

# ===================== АНИМАЦИЯ =====================
def animate_loading(chat_id, message_id, text):
    frames = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷']
    for _ in range(3):
        for f in frames:
            try:
                bot.edit_message_text(f"{f} {text}", chat_id, message_id)
                time.sleep(0.15)
            except:
                pass
    return True

def animate_progress(chat_id, message_id, current, total, step_text='Отправка'):
    bar_length = 15
    filled = int(round(bar_length * current / total))
    bar = '█' * filled + '░' * (bar_length - filled)
    percent = int(round((current / total) * 100))
    frame = random.choice(['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'])
    text = f"{frame} {step_text}\n[{bar}] {percent}%  ({current}/{total})"
    try:
        bot.edit_message_text(text, chat_id, message_id)
    except:
        pass

# ===================== ПАРСИНГ ВРЕМЕНИ =====================
def parse_time(time_str):
    match = re.match(r'(\d+)([smhd])', time_str)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    if unit == 's':
        return value
    elif unit == 'm':
        return value * 60
    elif unit == 'h':
        return value * 3600
    elif unit == 'd':
        return value * 86400
    return None

# ===================== ОТПРАВКА =====================
def send_email(receiver, sender_email, sender_password, subject, body, retries=5):
    for attempt in range(retries):
        try:
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = receiver
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            if any(domain in sender_email for domain in ['outlook.com','hotmail.com','live.com']):
                smtp_server = 'smtp-mail.outlook.com'
            elif any(domain in sender_email for domain in ['yandex.ru','ya.ru','yandex.com']):
                smtp_server = 'smtp.yandex.ru'
            else:
                smtp_server = 'smtp.mail.ru'
            server = smtplib.SMTP(smtp_server, 587, timeout=15)
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver, msg.as_string())
            server.quit()
            return True
        except:
            if attempt < retries - 1:
                time.sleep(random.uniform(3, 8))
    return False

def send_complaints_batch(complaint_text, subject, email_list, chat_id, status_msg_id):
    total_sent = 0
    total_attempts = 0
    delay_between = (2, 5)
    delay_switch = (10, 20)

    sender_list = list(senders.items())
    random.shuffle(sender_list)

    total_emails = len(email_list) * len(sender_list)
    current = 0

    animate_loading(chat_id, status_msg_id, "⚡ Подготовка к отправке...")

    for sender_email, sender_password in sender_list:
        receivers = email_list.copy()
        random.shuffle(receivers)
        for receiver in receivers:
            current += 1
            total_attempts += 1
            date_part = time.strftime("%d.%m")
            prefixes = ['❗', '⚠️', '✉️', '📩', '🔔', '⚡', '🔥', '💢']
            dynamic_subject = f"{subject} [ID:{random.randint(1000,9999)}] {random.choice(prefixes)} {date_part}"
            endings = [
                "С уважением.",
                "Заранее благодарю.",
                "Надеюсь на вашу помощь.",
                "Спасибо за внимание.",
                "Буду признателен.",
                "Рассчитываю на понимание.",
                "Прошу принять меры.",
                "Спасибо, что делаете интернет безопаснее."
            ]
            body_variant = complaint_text + "\n\n" + random.choice(endings)
            if send_email(receiver, sender_email, sender_password, dynamic_subject, body_variant):
                total_sent += 1
            # Обновляем прогресс
            animate_progress(chat_id, status_msg_id, current, total_emails, f"Отправка {sender_email[:8]}... → {receiver}")
            time.sleep(random.uniform(*delay_between))
        time.sleep(random.uniform(*delay_switch))

    return total_sent, total_attempts

# ===================== ЖЁСТКИЙ ШАБЛОН =====================
def generate_hard_complaint(username, telegram_id):
    return f"""Здравствуйте, уважаемая служба поддержки Telegram!

Я вынужден обратиться к вам с крайне серьёзной жалобой на пользователя @{username} (ID: {telegram_id}).

Данный аккаунт систематически нарушает правила платформы:
- Занимается мошенничеством и обманом пользователей (берёт предоплату и исчезает, распространяет фишинговые ссылки).
- Публикует и распространяет запрещённый контент (включая сцены насилия, порнографию, пропаганду наркотиков и оружия).
- Угрожает другим участникам, оскорбляет, разжигает ненависть.
- Также есть подозрения, что аккаунт был взломан и используется злоумышленниками для противоправных действий.

Всё это создаёт небезопасную среду для тысяч пользователей Telegram. Я прошу вас:
1. Немедленно провести проверку данного аккаунта.
2. Заблокировать его навсегда, чтобы обезопасить сообщество.
3. Перезагрузить все сессии и отозвать облачный пароль (если аккаунт взломан).

Уверен, что вы отнесётесь к этой проблеме с должным вниманием. Telegram должен оставаться безопасным местом для общения.

Спасибо за вашу работу и оперативность!"""

# ===================== ЗАПУСК СНОСА =====================
def start_snus(chat_id, target_username, target_id='не указано'):
    start_msg = bot.send_message(chat_id, "🔄 Инициализация...")
    time.sleep(0.5)
    animate_loading(chat_id, start_msg.message_id, "🚀 Подготовка ракеты...")
    time.sleep(0.5)

    complaint = generate_hard_complaint(target_username, target_id)
    subject = "СРОЧНАЯ ЖАЛОБА на пользователя Telegram"

    progress_msg = bot.send_message(chat_id, "⏳ Запуск процесса...")
    bot.delete_message(chat_id, start_msg.message_id)

    def worker():
        sent, total = send_complaints_batch(complaint, subject, telegram_emails, chat_id, progress_msg.message_id)
        failed = total - sent
        final_text = f"""
🎉 **СНОС ЗАВЕРШЁН!** 🎉

👤 Цель: @{target_username}
📨 Отправлено: {sent} / {total} писем
❌ Не удалось: {failed}

🔥 Ваш аккаунт-мишень получил мощный удар!
💥 Telegram-поддержка получила {sent} жалоб!
🚀 Ожидайте блокировку в ближайшее время!

👑 Создатель: AlternativeHospital
        """
        try:
            bot.edit_message_text(final_text, chat_id, progress_msg.message_id, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Ошибка финала: {e}")

    threading.Thread(target=worker, daemon=True).start()

# ===================== КОМАНДЫ =====================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type == 'private':
        bot.send_message(
            message.chat.id,
            "👋 Привет! Я бот для **ультра-агрессивного сноса** аккаунтов в Telegram.\n\n"
            "⚡ **Быстрый старт:**\n"
            "`.snos <username>` — запускает максимально жёсткую рассылку жалоб.\n\n"
            "🎯 Выберите действие ниже или просто напишите команду.",
            reply_markup=main_menu(),
            parse_mode='Markdown'
        )
    else:
        bot.reply_to(message, "Я работаю только в личных сообщениях. Напишите мне в ЛС.")

@bot.message_handler(func=lambda message: message.chat.type == 'private' and message.text and message.text.startswith('.snos'))
def handle_snos(message):
    chat_id = message.chat.id
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Использование: .snos <username> (без @)")
        return
    username = parts[1].strip().lstrip('@')
    if not username:
        bot.reply_to(message, "❌ Укажите корректный username.")
        return
    bot.reply_to(message, f"🚀 Запущен ультра-агрессивный снос @{username}...")
    start_snus(chat_id, username, 'не указано')

# ===================== МЕНЮ =====================
def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🧑 Снос аккаунта", callback_data="menu_account"),
        InlineKeyboardButton("ℹ️ Создатели", callback_data="menu_creators")
    )
    return markup

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.message.chat.type != 'private':
        bot.answer_callback_query(call.id, "Доступно только в ЛС.")
        return
    chat_id = call.message.chat.id
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass

    if call.data == "menu_account":
        bot.send_message(chat_id, "👤 **Введите username** (без @):", parse_mode='Markdown')
        user_data[call.from_user.id] = {'step': 'awaiting_username'}
        return
    if call.data == "menu_creators":
        bot.send_message(
            chat_id,
            "ℹ️ **Создатель:** AlternativeHospital\n"
            "**Версия:** 28.0 (ультра-жёсткий снос + анимация)\n"
            "**Связь:** @Gisced",
            parse_mode='Markdown',
            reply_markup=main_menu()
        )
        return
    if call.data == "cancel":
        user_data.pop(call.from_user.id, None)
        bot.send_message(chat_id, "❌ Отменено.", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.chat.type == 'private' and message.text and not message.text.startswith('.'))
def handle_private_text(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if user_id in user_data and user_data[user_id].get('step') == 'awaiting_username':
        username = message.text.strip().lstrip('@')
        if not username:
            bot.send_message(chat_id, "❌ Некорректный username. Попробуйте снова.")
            return
        bot.send_message(chat_id, f"🚀 Запущен снос @{username}...")
        start_snus(chat_id, username, 'не указано')
        user_data.pop(user_id, None)
        return
    bot.send_message(chat_id, "Используйте /start для меню или .snos username для быстрого сноса.")

# ===================== ЗАПУСК =====================
def run_bot():
    while True:
        try:
            logger.info("🚀 Бот запущен (ультра-жёсткий режим + анимация)...")
            bot.infinity_polling(timeout=30, long_polling_timeout=10)
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            if "409" in str(e) or "Conflict" in str(e):
                time.sleep(10)
            else:
                time.sleep(5)

if __name__ == '__main__':
    run_bot()
