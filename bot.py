import telebot
from telebot import types
import smtplib
from email.message import EmailMessage
import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================== КОНФИГ ==================
BOT_TOKEN = "8460346432:AAHMe6vVMXCbocElq2rcXVrMMTpwm5t-l3o"

ACCOUNTS = {
    "dgdihdic@list.ru": "oOoRNsDos0IOsKLsxKhX",
    "artem2289hd@list.ru": "6swc7w7oZdVoYpOPpKRg",
    "misha228088e@list.ru": "aTKnJelVld5SMD1ZbBdk",
    "gsudgeudgd@list.ru": "TLWEfZ2iW28ycUcH5Z79",
    "ospdbcod@list.ru": "b01NdPamd0XexiZ4q8RA",
    "isoebdod@list.ru": "g9eCe3CMQfRKEFD6HVAB",
    "kdpdncuf@list.ru": "u1WqMGIEtFLQCLN7itp2",
    "djdkddddcc@internet.ru": "KjFYSepvZRCBlVOzHtGH",
    "kldncibc782@internet.ru": "YuzrHLohJ13GgAIUbmOz",
    "durovvk@internet.ru": "VyP9IznKizRg5PYE5LC1",
    "kotakbasss@internet.ru": "e6H3o5Jje0INZZtgaVMy",
}

TARGET_EMAILS = [
    "abuse@telegram.org",
    "dmca@telegram.org",
    "support@telegram.org",
]

DELAY_BETWEEN_EMAILS = 3  # секунды между письмами с одного ящика

TEMPLATE_SUBJECT = "Официальная жалоба на нарушение правил Telegram (ст. 152, 128.1 УК РФ)"
TEMPLATE_BODY = """
Уважаемые сотрудники службы поддержки Telegram!

Я, нижеподписавшийся, обращаюсь с официальной жалобой на действия пользователя/канала:

🔹 @{username} (ID: {id})

Указанный аккаунт систематически нарушает правила платформы и законодательство Российской Федерации, а именно:
- Распространяет материалы экстремистского характера (ст. 280 УК РФ);
- Содержит призывы к насилию и разжиганию ненависти (ст. 282 УК РФ);
- Осуществляет мошеннические действия и фишинг (ст. 159 УК РФ);
- Нарушает авторские и смежные права (ст. 146 УК РФ).

На основании вышеизложенного, руководствуясь Федеральным законом № 149-ФЗ «Об информации» и правилами Telegram, требую:
1. Немедленно провести проверку указанного аккаунта.
2. Заблокировать его за грубые нарушения.
3. Уведомить меня о результатах проверки по данному адресу электронной почты.

В случае бездействия я буду вынужден обратиться в Роскомнадзор, прокуратуру и МВД с заявлением о привлечении виновных к ответственности.

С уважением,
гражданин РФ
"""

# ================== НАСТРОЙКА ЛОГИРОВАНИЯ ==================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

bot = telebot.TeleBot(BOT_TOKEN)

# ================== ХРАНЕНИЕ СОСТОЯНИЙ ПОЛЬЗОВАТЕЛЕЙ ==================
user_states = {}

# ================== ФУНКЦИЯ ОТПРАВКИ ОДНОГО ПИСЬМА ==================
def send_email(from_email: str, password: str, to_email: str, subject: str, body: str) -> bool:
    try:
        msg = EmailMessage()
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP_SSL("smtp.mail.ru", 465, timeout=30) as smtp:
            smtp.login(from_email, password)
            smtp.send_message(msg)
        logging.info(f"✅ {from_email} -> {to_email} успешно")
        return True
    except Exception as e:
        logging.error(f"❌ {from_email} -> {to_email} ошибка: {e}")
        return False

# ================== ОТПРАВКА С ОДНОГО ЯЩИКА НА ВСЕ ЦЕЛИ ==================
def send_emails_for_account(email: str, password: str, targets: list, subject: str, body: str, delay: float) -> dict:
    results = {}
    for target in targets:
        results[target] = send_email(email, password, target, subject, body)
        time.sleep(delay)
    return results

# ================== ПАРАЛЛЕЛЬНАЯ ОТПРАВКА ДЛЯ ВСЕХ ЯЩИКОВ ==================
def send_all_parallel(accounts: dict, targets: list, subject: str, body: str, max_workers: int = 5, delay: float = 3) -> dict:
    overall_results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_email = {
            executor.submit(send_emails_for_account, email, pwd, targets, subject, body, delay): email
            for email, pwd in accounts.items()
        }
        for future in as_completed(future_to_email):
            email = future_to_email[future]
            try:
                overall_results[email] = future.result()
            except Exception as e:
                logging.error(f"Необработанная ошибка для {email}: {e}")
                overall_results[email] = {target: False for target in targets}
    return overall_results

# ================== ОСНОВНАЯ ФУНКЦИЯ АТАКИ ==================
def attack_fast(chat_id, message_id, username, user_id):
    # Красивая анимация запуска
    animation_steps = [
        ("🔍 Сканирование целей...", 0.5),
        ("🔑 Авторизация на почтовых серверах...", 0.6),
        ("📨 Формирование шаблонов писем...", 0.5),
        ("⚡ Запуск параллельных потоков...", 0.7),
        ("🚀 Отправка в процессе...", 0.5),
    ]

    try:
        for text, delay in animation_steps:
            bot.edit_message_text(f"⏳ {text}", chat_id, message_id, parse_mode="Markdown")
            time.sleep(delay)
    except Exception:
        pass

    subject = TEMPLATE_SUBJECT
    body = TEMPLATE_BODY.format(username=username, id=user_id)

    results = send_all_parallel(ACCOUNTS, TARGET_EMAILS, subject, body, max_workers=5, delay=DELAY_BETWEEN_EMAILS)

    # Подсчёт статистики
    total_accounts = len(ACCOUNTS)
    successful_accounts = 0
    partial_accounts = 0
    failed_accounts = 0
    total_sent = 0
    total_success = 0

    for email, target_results in results.items():
        success_count = sum(1 for v in target_results.values() if v)
        total_for_account = len(target_results)
        total_sent += total_for_account
        total_success += success_count
        if success_count == total_for_account:
            successful_accounts += 1
        elif success_count == 0:
            failed_accounts += 1
        else:
            partial_accounts += 1

    # Финальное сообщение (без почтовых ящиков)
    final_text = (
        "⚡⚡⚡ **РАССЫЛКА ЗАВЕРШЕНА!** ⚡⚡⚡\n\n"
        f"📬 **Всего ящиков:** {total_accounts}\n"
        f"📨 **Отправлено писем:** {total_sent}\n"
        f"✅ **Успешно доставлено:** {total_success}\n"
        f"❌ **Неудачно:** {total_sent - total_success}\n\n"
        f"📊 **Статистика по ящикам:**\n"
        f"  ✅ Полностью успешных: {successful_accounts}\n"
        f"  ⚠️ Частично успешных: {partial_accounts}\n"
        f"  ❌ Полностью неудачных: {failed_accounts}\n\n"
        f"⏱️ Время выполнения: ~{total_accounts * DELAY_BETWEEN_EMAILS + 3} сек.\n"
        "🔥 Мощь технологии Ryzen — полный контроль!\n\n"
        "Вы можете повторить или вернуться в меню."
    )

    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("🔄 Повторить", callback_data="restart"))
    keyboard.row(types.InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"))

    try:
        bot.edit_message_text(final_text, chat_id, message_id, reply_markup=keyboard, parse_mode="Markdown")
    except Exception:
        bot.send_message(chat_id, final_text, reply_markup=keyboard, parse_mode="Markdown")

# ================== ОБРАБОТЧИКИ ==================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_states[message.chat.id] = {}
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("📩 Подать жалобу")
    bot.send_message(
        message.chat.id,
        "👋 **Высокотехнологичный бот**",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text == "📩 Подать жалобу")
def start_complaint(message):
    user_states[message.chat.id] = {'step': 'waiting_username'}
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("❌ Отмена")
    bot.send_message(
        message.chat.id,
        "📝 Введите **username** нарушителя (например, @spammer):",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id, {})
    step = state.get('step')

    if step == 'waiting_username':
        username = message.text.strip()
        if not username:
            bot.send_message(chat_id, "❌ Поле не может быть пустым. Введите username:")
            return
        if username == "❌ Отмена":
            user_states[chat_id] = {}
            keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.row("📩 Подать жалобу")
            bot.send_message(chat_id, "❌ Отменено. Возврат в главное меню.", reply_markup=keyboard)
            return
        state['username'] = username
        state['step'] = 'waiting_id'
        user_states[chat_id] = state
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.row("❌ Отмена")
        bot.send_message(chat_id, "🆔 Теперь введите **ID** (числовой идентификатор):", reply_markup=keyboard, parse_mode="Markdown")

    elif step == 'waiting_id':
        user_id_input = message.text.strip()
        if user_id_input == "❌ Отмена":
            user_states[chat_id] = {}
            keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.row("📩 Подать жалобу")
            bot.send_message(chat_id, "❌ Отменено. Возврат в главное меню.", reply_markup=keyboard)
            return
        if not user_id_input.isdigit():
            bot.send_message(chat_id, "❌ ID должен быть числом. Попробуйте снова:")
            return
        state['id'] = user_id_input
        username = state['username']
        user_id = state['id']
        user_states[chat_id] = {}

        msg = bot.send_message(chat_id, f"⚡ Готовлю отправку на **{username}** (ID: {user_id})...", parse_mode="Markdown")
        thread = threading.Thread(target=attack_fast, args=(chat_id, msg.message_id, username, user_id))
        thread.start()

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    if call.data == "restart":
        bot.answer_callback_query(call.id, "Перезапуск...")
        bot.delete_message(chat_id, message_id)
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.row("📩 Подать жалобу")
        bot.send_message(chat_id, "🔄 Начнём заново. Нажмите «Подать жалобу».", reply_markup=keyboard)

    elif call.data == "main_menu":
        bot.answer_callback_query(call.id, "Главное меню")
        bot.delete_message(chat_id, message_id)
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.row("📩 Подать жалобу")
        bot.send_message(chat_id, "🏠 Главное меню:", reply_markup=keyboard)

# ================== ЗАПУСК ==================
if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()
