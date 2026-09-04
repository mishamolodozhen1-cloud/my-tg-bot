import asyncio
import logging
from email.message import EmailMessage
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    Message
)
import aiosmtplib

# ================== КОНФИГУРАЦИЯ ==================
BOT_TOKEN = "8460346432:AAHMe6vVMXCbocElq2rcXVrMMTpwm5t-l3o"

# Почтовые аккаунты (email: пароль приложения)
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

# Целевые адреса Telegram для жалоб
TARGET_EMAILS = [
    "abuse@telegram.org",
    "dmca@telegram.org",
    "support@telegram.org",
]

# Шаблон жалобы (без даты)
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

# ================== КЛАВИАТУРЫ ==================
# Главное меню — только кнопка подачи жалобы
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📩 Подать жалобу")]
    ],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)

finish_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Повторить", callback_data="restart")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ]
)

# ================== FSM (состояния) ==================
class ComplaintForm(StatesGroup):
    waiting_username = State()
    waiting_id = State()

# ================== НАСТРОЙКА ЛОГИРОВАНИЯ ==================
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================== ФУНКЦИЯ ОТПРАВКИ ОДНОГО ПИСЬМА ==================
async def send_email(from_email: str, password: str, to_emails: list, subject: str, body: str) -> bool:
    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        smtp = aiosmtplib.SMTP(hostname="smtp.mail.ru", port=465, use_tls=True)
        await smtp.login(from_email, password)
        await smtp.send_message(msg)
        await smtp.quit()
        return True
    except Exception as e:
        logging.error(f"Ошибка с {from_email}: {e}")
        return False

# ================== ПАРАЛЛЕЛЬНАЯ ОТПРАВКА (БЫСТРАЯ) ==================
async def send_all_parallel(accounts: dict, targets: list, subject: str, body: str, max_concurrent: int = 5):
    """Отправляет письма параллельно с ограничением числа одновременных сессий."""
    results = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def send_one(email, pwd):
        async with semaphore:
            success = await send_email(email, pwd, targets, subject, body)
            return email, success

    tasks = [send_one(email, pwd) for email, pwd in accounts.items()]
    for future in asyncio.as_completed(tasks):
        email, success = await future
        results[email] = success
    return results

async def attack_fast(message: Message, username: str, user_id: str):
    # Анимация этапов
    status_msg = await message.answer("🔄 **Подготовка системы...**", parse_mode="Markdown")
    await asyncio.sleep(0.5)

    await status_msg.edit_text("🔌 **Инициализация SMTP-соединений...**", parse_mode="Markdown")
    await asyncio.sleep(0.5)

    await status_msg.edit_text("🚀 **Запуск параллельной отправки (11 потоков)...**", parse_mode="Markdown")
    await asyncio.sleep(0.3)

    # Формируем письмо
    subject = TEMPLATE_SUBJECT
    body = TEMPLATE_BODY.format(username=username, id=user_id)

    total = len(ACCOUNTS)

    # Запускаем отправку
    results = await send_all_parallel(ACCOUNTS, TARGET_EMAILS, subject, body, max_concurrent=5)

    successful = sum(1 for v in results.values() if v)
    failed = total - successful

    # Красивое финальное сообщение
    final_text = (
        "⚡⚡⚡ **РАССЫЛКА ЗАВЕРШЕНА!** ⚡⚡⚡\n\n"
        f"📬 **Всего ящиков:** {total}\n"
        f"✅ **Успешно:** {successful}  🟢\n"
        f"❌ **Неудачно:** {failed}  🔴\n\n"
        "⏱️ Время выполнения: < 5 сек.\n"
        "🔥 Мощь технологии Ryzen — полный контроль!\n\n"
        "Вы можете повторить или вернуться в меню."
    )
    await status_msg.edit_text(final_text, reply_markup=finish_kb, parse_mode="Markdown")

# ================== ОБРАБОТЧИКИ КОМАНД И КНОПОК ==================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 **Высокотехнологичный бот** — система массовой отправки официальных жалоб.\n\n"
        "⚙️ Используйте кнопку **«Подать жалобу»** для запуска.\n"
        "💡 Бот работает на движке параллельной отправки (до 5 потоков).",
        reply_markup=main_kb,
        parse_mode="Markdown"
    )

@dp.message(F.text == "📩 Подать жалобу")
async def start_complaint(message: Message, state: FSMContext):
    await message.answer(
        "📝 Введите **username** нарушителя (например, @spammer):",
        reply_markup=cancel_kb,
        parse_mode="Markdown"
    )
    await state.set_state(ComplaintForm.waiting_username)

@dp.message(F.text == "❌ Отмена", StateFilter(ComplaintForm.waiting_username, ComplaintForm.waiting_id))
async def cancel_complaint(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено. Возврат в главное меню.", reply_markup=main_kb)

@dp.message(StateFilter(ComplaintForm.waiting_username))
async def process_username(message: Message, state: FSMContext):
    username = message.text.strip()
    if not username:
        await message.answer("❌ Поле не может быть пустым. Введите username:")
        return
    await state.update_data(username=username)
    await message.answer("🆔 Теперь введите **ID** (числовой идентификатор):", reply_markup=cancel_kb, parse_mode="Markdown")
    await state.set_state(ComplaintForm.waiting_id)

@dp.message(StateFilter(ComplaintForm.waiting_id))
async def process_id(message: Message, state: FSMContext):
    user_id_input = message.text.strip()
    if not user_id_input.isdigit():
        await message.answer("❌ ID должен быть числом. Попробуйте снова:")
        return
    await state.update_data(user_id=user_id_input)
    data = await state.get_data()
    username = data["username"]
    user_id = data["user_id"]
    await state.clear()

    # Запускаем рассылку
    await message.answer(f"⚡ Готовлю отправку на **{username}** (ID: {user_id})...", parse_mode="Markdown")
    await attack_fast(message, username, user_id)

@dp.callback_query(lambda c: c.data == "restart")
async def restart(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer("🔄 Начнём заново. Нажмите «Подать жалобу».", reply_markup=main_kb)

@dp.callback_query(lambda c: c.data == "main_menu")
async def main_menu(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer("🏠 Главное меню:", reply_markup=main_kb)

# ================== ЗАПУСК ==================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
