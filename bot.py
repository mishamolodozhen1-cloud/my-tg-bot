import logging
import sqlite3
import random
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes,
    ChatMemberHandler
)

TOKEN = "8841865153:AAHxbALDI8EIdyk0DpRC0wshkvlS1w1Ds7w"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
DB_FILE = "game.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        country TEXT,
        resources INTEGER DEFAULT 1000,
        money INTEGER DEFAULT 10000,
        population INTEGER DEFAULT 10000000,
        military INTEGER DEFAULT 100000,
        economy INTEGER DEFAULT 500,
        fleet INTEGER DEFAULT 0,
        inflation REAL DEFAULT 0.0,
        last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        master_id INTEGER DEFAULT NULL,
        is_puppet INTEGER DEFAULT 0,
        neutral INTEGER DEFAULT 0,
        mobilized INTEGER DEFAULT 0,
        base_military INTEGER DEFAULT 100000,
        mobilized_until TIMESTAMP DEFAULT NULL,
        is_bot INTEGER DEFAULT 0,
        fortifications INTEGER DEFAULT 0,
        occupied_territory TEXT DEFAULT '[]'
    )""")
    cur.execute("PRAGMA table_info(users)")
    columns = [c[1] for c in cur.fetchall()]
    for col in ['fleet','inflation','fortifications','occupied_territory']:
        if col not in columns:
            if col=='inflation': cur.execute("ALTER TABLE users ADD COLUMN inflation REAL DEFAULT 0.0")
            elif col=='fleet': cur.execute("ALTER TABLE users ADD COLUMN fleet INTEGER DEFAULT 0")
            elif col=='fortifications': cur.execute("ALTER TABLE users ADD COLUMN fortifications INTEGER DEFAULT 0")
            elif col=='occupied_territory': cur.execute("ALTER TABLE users ADD COLUMN occupied_territory TEXT DEFAULT '[]'")
    cur.execute("""CREATE TABLE IF NOT EXISTS technologies (user_id INTEGER, tech_name TEXT, level INTEGER DEFAULT 0, last_upgrade TIMESTAMP, PRIMARY KEY (user_id, tech_name))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS research_queue (user_id INTEGER, tech_name TEXT, start_time TIMESTAMP, finish_time TIMESTAMP, PRIMARY KEY (user_id, tech_name))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS spy_operations (id INTEGER PRIMARY KEY AUTOINCREMENT, from_user INTEGER, target_user INTEGER, action TEXT, date TIMESTAMP, success INTEGER)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS events_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, event_type TEXT, description TEXT, date TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS treaties (user_id INTEGER, partner_id INTEGER, type TEXT, until TIMESTAMP, PRIMARY KEY (user_id, partner_id))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS colonies (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, income INTEGER DEFAULT 10, loyalty INTEGER DEFAULT 50, invested INTEGER DEFAULT 0, last_update TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, from_user INTEGER, to_user INTEGER, status TEXT, offered_type TEXT, offered_amount INTEGER, requested_type TEXT, requested_amount INTEGER, date TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS allies (user_id INTEGER, ally_id INTEGER, status TEXT, date TIMESTAMP, PRIMARY KEY (user_id, ally_id))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS sanctions (from_user INTEGER, target_user INTEGER, date TIMESTAMP, PRIMARY KEY (from_user, target_user))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS wars (id INTEGER PRIMARY KEY AUTOINCREMENT, start_time TIMESTAMP, status TEXT, winner_id INTEGER DEFAULT NULL, initiator_id INTEGER, target_id INTEGER)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS war_participants (war_id INTEGER, user_id INTEGER, side TEXT, joined_at TIMESTAMP, PRIMARY KEY (war_id, user_id))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS peace_requests (war_id INTEGER, from_user INTEGER, to_user INTEGER, status TEXT, date TIMESTAMP, PRIMARY KEY (war_id, from_user, to_user))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS currency_rates (currency TEXT PRIMARY KEY, rate REAL DEFAULT 1.0, last_update TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS votes (id INTEGER PRIMARY KEY AUTOINCREMENT, proposer_id INTEGER, proposal TEXT, description TEXT, status TEXT, until TIMESTAMP, votes_for INTEGER DEFAULT 0, votes_against INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS vote_records (vote_id INTEGER, user_id INTEGER, choice TEXT, PRIMARY KEY (vote_id, user_id))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS occupations (occupier_id INTEGER, occupied_country TEXT, since TIMESTAMP, resistance INTEGER DEFAULT 0, PRIMARY KEY (occupier_id, occupied_country))""")
    conn.commit()
    conn.close()

COUNTRIES_DATA = {
    "Российская империя": {"capital":"Санкт-Петербург","population":170000000,"army":1500000,"initial_resources":1000,"initial_economy":700,"currency":"рубль"},
    "Германская империя": {"capital":"Берлин","population":67000000,"army":800000,"initial_resources":900,"initial_economy":800,"currency":"марка"},
    "Австро-Венгрия": {"capital":"Вена","population":52000000,"army":500000,"initial_resources":800,"initial_economy":650,"currency":"крона"},
    "Османская империя": {"capital":"Константинополь","population":25000000,"army":400000,"initial_resources":700,"initial_economy":500,"currency":"лира"},
    "Великобритания": {"capital":"Лондон","population":45000000,"army":250000,"initial_resources":900,"initial_economy":850,"currency":"фунт стерлингов"},
    "Франция": {"capital":"Париж","population":40000000,"army":800000,"initial_resources":800,"initial_economy":750,"currency":"франк"},
    "Италия": {"capital":"Рим","population":35000000,"army":300000,"initial_resources":700,"initial_economy":600,"currency":"лира"},
    "Испания": {"capital":"Мадрид","population":20000000,"army":150000,"initial_resources":600,"initial_economy":550,"currency":"песета"},
    "Португалия": {"capital":"Лиссабон","population":6000000,"army":80000,"initial_resources":500,"initial_economy":450,"currency":"эскудо"},
    "Нидерланды": {"capital":"Амстердам","population":6000000,"army":100000,"initial_resources":600,"initial_economy":600,"currency":"гульден"},
    "Бельгия": {"capital":"Брюссель","population":7500000,"army":150000,"initial_resources":600,"initial_economy":550,"currency":"франк"},
    "Швейцария": {"capital":"Берн","population":4000000,"army":150000,"initial_resources":500,"initial_economy":600,"currency":"франк"},
    "Швеция": {"capital":"Стокгольм","population":5500000,"army":60000,"initial_resources":500,"initial_economy":550,"currency":"крона"},
    "Норвегия": {"capital":"Осло","population":2500000,"army":20000,"initial_resources":400,"initial_economy":500,"currency":"крона"},
    "Дания": {"capital":"Копенгаген","population":2800000,"army":20000,"initial_resources":400,"initial_economy":500,"currency":"крона"},
    "Греция": {"capital":"Афины","population":5000000,"army":100000,"initial_resources":500,"initial_economy":450,"currency":"драхма"},
    "Болгария": {"capital":"София","population":4500000,"army":80000,"initial_resources":500,"initial_economy":450,"currency":"лев"},
    "Румыния": {"capital":"Бухарест","population":7500000,"army":100000,"initial_resources":600,"initial_economy":500,"currency":"лей"},
    "Сербия": {"capital":"Белград","population":4500000,"army":100000,"initial_resources":500,"initial_economy":400,"currency":"динар"},
    "Черногория": {"capital":"Цетинье","population":500000,"army":20000,"initial_resources":300,"initial_economy":300,"currency":"перпер"},
    "Албания": {"capital":"Тирана","population":800000,"army":10000,"initial_resources":300,"initial_economy":250,"currency":"франк"},
    "Люксембург": {"capital":"Люксембург","population":300000,"army":2000,"initial_resources":200,"initial_economy":300,"currency":"франк"},
    "Лихтенштейн": {"capital":"Вадуц","population":10000,"army":500,"initial_resources":100,"initial_economy":200,"currency":"франк"},
    "Монако": {"capital":"Монако","population":20000,"army":0,"initial_resources":100,"initial_economy":200,"currency":"франк"},
    "Сан-Марино": {"capital":"Сан-Марино","population":10000,"army":0,"initial_resources":100,"initial_economy":200,"currency":"лира"},
    "Андорра": {"capital":"Андорра-ла-Велья","population":5000,"army":0,"initial_resources":100,"initial_economy":200,"currency":"франк"},
    "Япония": {"capital":"Токио","population":55000000,"army":300000,"initial_resources":700,"initial_economy":650,"currency":"иена"},
    "Китай (Китайская республика)": {"capital":"Пекин","population":450000000,"army":500000,"initial_resources":800,"initial_economy":600,"currency":"юань"},
    "Монголия (Богдо-ханство)": {"capital":"Урга","population":800000,"army":10000,"initial_resources":300,"initial_economy":250,"currency":"тугрик"},
    "Сиам (Таиланд)": {"capital":"Бангкок","population":8000000,"army":50000,"initial_resources":500,"initial_economy":400,"currency":"тиккаль"},
    "Персия (Иран)": {"capital":"Тегеран","population":14000000,"army":50000,"initial_resources":500,"initial_economy":400,"currency":"риал"},
    "Афганистан": {"capital":"Кабул","population":6000000,"army":30000,"initial_resources":400,"initial_economy":300,"currency":"афгани"},
    "Неджд (Саудовская Аравия)": {"capital":"Эр-Рияд","population":1000000,"army":20000,"initial_resources":400,"initial_economy":300,"currency":"риал"},
    "Бутан": {"capital":"Тхимпху","population":200000,"army":2000,"initial_resources":200,"initial_economy":200,"currency":"нгултрум"},
    "Непал": {"capital":"Катманду","population":5000000,"army":20000,"initial_resources":300,"initial_economy":250,"currency":"рупия"},
    "США": {"capital":"Вашингтон","population":95000000,"army":100000,"initial_resources":1000,"initial_economy":900,"currency":"доллар"},
    "Канада": {"capital":"Оттава","population":7000000,"army":10000,"initial_resources":700,"initial_economy":700,"currency":"доллар"},
    "Мексика": {"capital":"Мехико","population":15000000,"army":100000,"initial_resources":600,"initial_economy":550,"currency":"песо"},
    "Куба": {"capital":"Гавана","population":2000000,"army":10000,"initial_resources":500,"initial_economy":450,"currency":"песо"},
    "Гаити": {"capital":"Порт-о-Пренс","population":2000000,"army":5000,"initial_resources":300,"initial_economy":250,"currency":"гурд"},
    "Доминиканская республика": {"capital":"Санто-Доминго","population":800000,"army":3000,"initial_resources":300,"initial_economy":300,"currency":"песо"},
    "Коста-Рика": {"capital":"Сан-Хосе","population":500000,"army":2000,"initial_resources":300,"initial_economy":300,"currency":"колон"},
    "Гватемала": {"capital":"Гватемала","population":1500000,"army":5000,"initial_resources":400,"initial_economy":350,"currency":"кетсаль"},
    "Гондурас": {"capital":"Тегусигальпа","population":600000,"army":2000,"initial_resources":300,"initial_economy":300,"currency":"лемпира"},
    "Никарагуа": {"capital":"Манагуа","population":800000,"army":3000,"initial_resources":300,"initial_economy":300,"currency":"кордоба"},
    "Панама": {"capital":"Панама","population":400000,"army":1000,"initial_resources":300,"initial_economy":300,"currency":"бальбоа"},
    "Сальвадор": {"capital":"Сан-Сальвадор","population":1000000,"army":3000,"initial_resources":300,"initial_economy":300,"currency":"колон"},
    "Бразилия": {"capital":"Рио-де-Жанейро","population":25000000,"army":100000,"initial_resources":800,"initial_economy":700,"currency":"реал"},
    "Аргентина": {"capital":"Буэнос-Айрес","population":8000000,"army":50000,"initial_resources":700,"initial_economy":650,"currency":"песо"},
    "Чили": {"capital":"Сантьяго","population":3500000,"army":30000,"initial_resources":600,"initial_economy":600,"currency":"песо"},
    "Колумбия": {"capital":"Богота","population":5000000,"army":20000,"initial_resources":600,"initial_economy":550,"currency":"песо"},
    "Венесуэла": {"capital":"Каракас","population":2500000,"army":10000,"initial_resources":500,"initial_economy":500,"currency":"боливар"},
    "Перу": {"capital":"Лима","population":4000000,"army":15000,"initial_resources":500,"initial_economy":500,"currency":"соль"},
    "Боливия": {"capital":"Ла-Пас","population":2500000,"army":10000,"initial_resources":400,"initial_economy":400,"currency":"боливиано"},
    "Парагвай": {"capital":"Асунсьон","population":800000,"army":5000,"initial_resources":300,"initial_economy":300,"currency":"гуарани"},
    "Уругвай": {"capital":"Монтевидео","population":1200000,"army":5000,"initial_resources":400,"initial_economy":400,"currency":"песо"},
    "Эквадор": {"capital":"Кито","population":1500000,"army":5000,"initial_resources":400,"initial_economy":400,"currency":"сукре"},
    "Либерия": {"capital":"Монровия","population":600000,"army":2000,"initial_resources":200,"initial_economy":200,"currency":"доллар"},
    "Эфиопия (Абиссиния)": {"capital":"Аддис-Абеба","population":10000000,"army":100000,"initial_resources":500,"initial_economy":400,"currency":"бырр"},
    "Южно-Африканский Союз": {"capital":"Претория","population":6000000,"army":10000,"initial_resources":600,"initial_economy":600,"currency":"фунт"},
    "Австралия": {"capital":"Канберра","population":5000000,"army":10000,"initial_resources":600,"initial_economy":600,"currency":"фунт"},
    "Новая Зеландия": {"capital":"Веллингтон","population":1000000,"army":5000,"initial_resources":500,"initial_economy":500,"currency":"фунт"},
    "Ньюфаундленд": {"capital":"Сент-Джонс","population":200000,"army":1000,"initial_resources":300,"initial_economy":300,"currency":"доллар"}
}
COUNTRIES_LIST = list(COUNTRIES_DATA.keys())

def get_country_currency(country: str) -> str:
    return COUNTRIES_DATA.get(country, {}).get("currency", "ден. ед.")

def get_user_country(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT country FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def set_user_country(user_id: int, country: str):
    data = COUNTRIES_DATA.get(country, {})
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""REPLACE INTO users (user_id, country, resources, money, population, military, economy, fleet, inflation,
                 last_update, master_id, is_puppet, neutral, mobilized, base_military, is_bot, fortifications)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (user_id, country, data.get('initial_resources',1000), 10000,
                  data.get('population',10000000), data.get('army',100000),
                  data.get('initial_economy',500), 0, 0.0,
                  datetime.now().isoformat(), None, 0, 0, 0, data.get('army',100000), 0, 0))
    conn.commit()
    conn.close()

def delete_user_country(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM allies WHERE user_id=? OR ally_id=?", (user_id, user_id))
    cur.execute("DELETE FROM sanctions WHERE from_user=? OR target_user=?", (user_id, user_id))
    cur.execute("DELETE FROM technologies WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM research_queue WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM colonies WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM treaties WHERE user_id=? OR partner_id=?", (user_id, user_id))
    cur.execute("DELETE FROM wars WHERE initiator_id=? OR target_id=?", (user_id, user_id))
    cur.execute("DELETE FROM war_participants WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM peace_requests WHERE from_user=? OR to_user=?", (user_id, user_id))
    cur.execute("DELETE FROM spy_operations WHERE from_user=? OR target_user=?", (user_id, user_id))
    cur.execute("DELETE FROM occupations WHERE occupier_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_all_users_countries():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT country, user_id, is_puppet, is_bot FROM users")
    rows = cur.fetchall()
    conn.close()
    return {row[0]: {'user_id': row[1], 'is_puppet': row[2], 'is_bot': row[3]} for row in rows}

def get_user_id_by_country(country: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE country=?", (country,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def get_resources(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT resources FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def set_resources(user_id: int, amount: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET resources=? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def add_resources(user_id: int, amount: int):
    set_resources(user_id, get_resources(user_id) + amount)

def deduct_resources(user_id: int, amount: int) -> bool:
    if get_resources(user_id) < amount: return False
    set_resources(user_id, get_resources(user_id) - amount)
    return True

def get_money(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT money FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def set_money(user_id: int, amount: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET money=? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def add_money(user_id: int, amount: int):
    set_money(user_id, get_money(user_id) + amount)

def deduct_money(user_id: int, amount: int) -> bool:
    if get_money(user_id) < amount: return False
    set_money(user_id, get_money(user_id) - amount)
    return True

def get_user_stats(user_id: int):
    update_user_stats(user_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""SELECT country, resources, money, population, military, economy, fleet, inflation,
                   master_id, is_puppet, neutral, mobilized, base_military, fortifications
                   FROM users WHERE user_id=?""", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {'country': row[0], 'resources': row[1], 'money': row[2], 'population': row[3],
                'military': row[4], 'economy': row[5], 'fleet': row[6], 'inflation': row[7],
                'master_id': row[8], 'is_puppet': row[9], 'neutral': row[10], 'mobilized': row[11],
                'base_military': row[12], 'fortifications': row[13]}
    return None

def set_user_stats(user_id: int, **kwargs):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    updates = []
    params = []
    for key, value in kwargs.items():
        if key in ['resources','money','population','military','economy','fleet','inflation',
                   'master_id','is_puppet','neutral','mobilized','base_military','fortifications']:
            updates.append(f"{key}=?")
            params.append(value)
    if updates:
        params.append(datetime.now().isoformat())
        params.append(user_id)
        cur.execute(f"UPDATE users SET {', '.join(updates)}, last_update=? WHERE user_id=?", params)
        conn.commit()
    conn.close()

def get_inflation(user_id: int) -> float:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT inflation FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0.0

def set_inflation(user_id: int, value: float):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET inflation=? WHERE user_id=?", (value, user_id))
    conn.commit()
    conn.close()

def increase_inflation(user_id: int, amount: float):
    current = get_inflation(user_id)
    set_inflation(user_id, current + amount)

def get_fortifications(user_id: int) -> int:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT fortifications FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def is_puppet(user_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT is_puppet FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row and row[0] == 1

def get_master(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT master_id FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def get_puppets(master_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT country FROM users WHERE master_id=? AND is_puppet=1", (master_id,))
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]

TECH_LIST = ['infantry', 'artillery', 'aviation', 'medicine', 'economy']
TECH_NAMES = {'infantry':'Пехота','artillery':'Артиллерия','aviation':'Авиация','medicine':'Медицина','economy':'Экономика'}
TECH_PRICES = [100,200,300,400,500]

def get_tech_level(user_id: int, tech: str) -> int:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT level FROM technologies WHERE user_id=? AND tech_name=?", (user_id, tech))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def set_tech_level(user_id: int, tech: str, level: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("REPLACE INTO technologies (user_id, tech_name, level, last_upgrade) VALUES (?, ?, ?, ?)",
                (user_id, tech, level, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def start_research(user_id: int, tech: str):
    current_level = get_tech_level(user_id, tech)
    if current_level >= 5:
        return False, "Технология уже максимального уровня."
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM research_queue WHERE user_id=? AND tech_name=?", (user_id, tech))
    if cur.fetchone():
        conn.close()
        return False, "Эта технология уже исследуется."
    cost = TECH_PRICES[current_level] * 2
    if get_resources(user_id) < cost:
        conn.close()
        return False, f"Недостаточно ресурсов. Нужно {cost}."
    deduct_resources(user_id, cost)
    now = datetime.now()
    finish = now + timedelta(hours=1)
    cur.execute("INSERT INTO research_queue (user_id, tech_name, start_time, finish_time) VALUES (?, ?, ?, ?)",
                (user_id, tech, now.isoformat(), finish.isoformat()))
    conn.commit()
    conn.close()
    return True, f"Исследование {TECH_NAMES[tech]} начато! Завершится через 1 час."

def check_research_queue():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, tech_name, finish_time FROM research_queue")
    rows = cur.fetchall()
    now = datetime.now()
    for user_id, tech, finish_str in rows:
        finish = datetime.fromisoformat(finish_str)
        if now >= finish:
            current_level = get_tech_level(user_id, tech)
            set_tech_level(user_id, tech, current_level + 1)
            cur.execute("DELETE FROM research_queue WHERE user_id=? AND tech_name=?", (user_id, tech))
    conn.commit()
    conn.close()

def spy_action(from_user: int, target_user: int, action: str) -> dict:
    if get_money(from_user) < 500:
        return {'success': False, 'message': 'Недостаточно денег (нужно 500).'}
    deduct_money(from_user, 500)
    avia_level = get_tech_level(from_user, 'aviation')
    success_chance = 0.6 + avia_level * 0.05
    success = random.random() < success_chance
    result = {'success': success}
    if success:
        if action == 'разведка':
            target_stats = get_user_stats(target_user)
            if target_stats:
                result['message'] = f"Разведка успешна! Данные о {target_stats['country']}:\n" \
                                    f"Население: {target_stats['population']:,}\nАрмия: {target_stats['military']:,}\n" \
                                    f"Экономика: {target_stats['economy']}\nРесурсы: {target_stats['resources']}\n" \
                                    f"Деньги: {target_stats['money']}\nМобилизован: {'Да' if target_stats['mobilized'] else 'Нет'}"
            else:
                result['message'] = "Цель не найдена."
        elif action == 'саботаж':
            target_res = get_resources(target_user)
            new_res = int(target_res * 0.95)
            set_resources(target_user, new_res)
            result['message'] = f"Саботаж успешен! У {get_user_country(target_user)} украдено {target_res - new_res} ресурсов."
        else:
            result['message'] = "Неизвестное действие."
    else:
        result['message'] = "Операция провалилась. Деньги потрачены."
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT INTO spy_operations (from_user, target_user, action, date, success) VALUES (?, ?, ?, ?, ?)",
                (from_user, target_user, action, datetime.now().isoformat(), 1 if success else 0))
    conn.commit()
    conn.close()
    return result

def get_allies(user_id: int, status='accepted'):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT ally_id FROM allies WHERE user_id=? AND status=?", (user_id, status))
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_ally_countries(user_id: int):
    ally_ids = get_allies(user_id, 'accepted')
    countries = []
    for uid in ally_ids:
        country = get_user_country(uid)
        if country:
            countries.append(country)
    return countries

def is_ally(user_id: int, other_id: int) -> bool:
    if user_id == other_id:
        return False
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM allies WHERE user_id=? AND ally_id=? AND status='accepted'", (user_id, other_id))
    row = cur.fetchone()
    conn.close()
    return row is not None

def create_ally_request(from_user: int, to_user: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO allies (user_id, ally_id, status, date) VALUES (?, ?, ?, ?)",
                (from_user, to_user, 'pending', datetime.now().isoformat()))
    cur.execute("INSERT OR REPLACE INTO allies (user_id, ally_id, status, date) VALUES (?, ?, ?, ?)",
                (to_user, from_user, 'pending', datetime.now().isoformat()))
    conn.commit()
    conn.close()

def accept_ally(user_id: int, ally_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE allies SET status='accepted' WHERE user_id=? AND ally_id=?", (user_id, ally_id))
    cur.execute("UPDATE allies SET status='accepted' WHERE user_id=? AND ally_id=?", (ally_id, user_id))
    conn.commit()
    conn.close()

def break_ally(user_id: int, ally_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM allies WHERE user_id=? AND ally_id=?", (user_id, ally_id))
    cur.execute("DELETE FROM allies WHERE user_id=? AND ally_id=?", (ally_id, user_id))
    conn.commit()
    conn.close()

def create_sanction(from_user: int, target_user: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO sanctions (from_user, target_user, date) VALUES (?, ?, ?)",
                (from_user, target_user, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def remove_sanction(from_user: int, target_user: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM sanctions WHERE from_user=? AND target_user=?", (from_user, target_user))
    conn.commit()
    conn.close()

def has_sanction(from_user: int, target_user: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT date FROM sanctions WHERE from_user=? AND target_user=?", (from_user, target_user))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    date = datetime.fromisoformat(row[0])
    if (datetime.now() - date) >= timedelta(hours=24):
        remove_sanction(from_user, target_user)
        return False
    return True

def get_sanctioned_countries(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT target_user, date FROM sanctions WHERE from_user=?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    countries = []
    now = datetime.now()
    for target_id, date_str in rows:
        date = datetime.fromisoformat(date_str)
        if (now - date) < timedelta(hours=24):
            country = get_user_country(target_id)
            if country:
                countries.append(country)
        else:
            remove_sanction(user_id, target_id)
    return countries

def is_sanctioned_between(user1: int, user2: int) -> bool:
    return has_sanction(user1, user2) or has_sanction(user2, user1)

def create_napt(user_id: int, partner_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM treaties WHERE user_id=? AND partner_id=? AND type='napt' AND until > datetime('now')",
                (user_id, partner_id))
    if cur.fetchone():
        conn.close()
        return False, "Договор о ненападении уже действует."
    until = datetime.now() + timedelta(days=7)
    cur.execute("INSERT OR REPLACE INTO treaties (user_id, partner_id, type, until) VALUES (?, ?, ?, ?)",
                (user_id, partner_id, 'napt', until.isoformat()))
    cur.execute("INSERT OR REPLACE INTO treaties (user_id, partner_id, type, until) VALUES (?, ?, ?, ?)",
                (partner_id, user_id, 'napt', until.isoformat()))
    conn.commit()
    conn.close()
    return True, "Договор о ненападении заключён на 7 дней."

def has_napt(user_id: int, other_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM treaties WHERE user_id=? AND partner_id=? AND type='napt' AND until > datetime('now')",
                (user_id, other_id))
    row = cur.fetchone()
    conn.close()
    return row is not None

def break_napt_penalty(user_id: int):
    stats = get_user_stats(user_id)
    if not stats:
        return False, "Страна не найдена."
    new_res = int(stats['resources'] * 0.85)
    new_money = int(stats['money'] * 0.85)
    new_eco = int(stats['economy'] * 0.9)
    set_user_stats(user_id, resources=new_res, money=new_money, economy=new_eco)
    increase_inflation(user_id, 0.05)
    return True, f"За разрыв пакта вы потеряли 15% ресурсов и денег, экономика упала на 10%, инфляция выросла на 5%."

def cancel_napt(user_id: int, partner_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM treaties WHERE user_id=? AND partner_id=? AND type='napt'", (user_id, partner_id))
    cur.execute("DELETE FROM treaties WHERE user_id=? AND partner_id=? AND type='napt'", (partner_id, user_id))
    conn.commit()
    conn.close()

def mobilize(user_id: int):
    stats = get_user_stats(user_id)
    if not stats:
        return False, "Страна не найдена."
    if stats['mobilized']:
        return False, "Уже мобилизованы."
    if get_money(user_id) < 1000:
        return False, "Недостаточно денег (нужно 1000)."
    deduct_money(user_id, 1000)
    base_mil = stats['base_military']
    new_mil = int(base_mil * 1.5)
    eco = stats['economy']
    pop = stats['population']
    eco_new = int(eco * 0.8)
    pop_new = int(pop * 0.95)
    until = datetime.now() + timedelta(hours=24)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""UPDATE users SET military=?, economy=?, population=?, mobilized=1, mobilized_until=?
                   WHERE user_id=?""", (new_mil, eco_new, pop_new, until.isoformat(), user_id))
    conn.commit()
    conn.close()
    return True, f"Мобилизация проведена! Армия увеличена до {new_mil}, экономика снижена на 20%, население на 5%."

def demobilize(user_id: int):
    stats = get_user_stats(user_id)
    if not stats or not stats['mobilized']:
        return False, "Вы не мобилизованы."
    base_mil = stats['base_military']
    eco = stats['economy']
    pop = stats['population']
    eco_new = int(eco / 0.8)
    pop_new = int(pop / 0.95)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""UPDATE users SET military=?, economy=?, population=?, mobilized=0, mobilized_until=NULL
                   WHERE user_id=?""", (base_mil, eco_new, pop_new, user_id))
    conn.commit()
    conn.close()
    return True, "Демобилизация проведена. Армия возвращена к базе."

def init_colonies():
    colonial_powers = {
        'Великобритания': ['Индия', 'Канада', 'Австралия', 'Новая Зеландия', 'Южная Африка'],
        'Франция': ['Алжир', 'Марокко', 'Вьетнам'],
        'Российская империя': ['Польша', 'Финляндия', 'Кавказ'],
        'Османская империя': ['Месопотамия', 'Палестина'],
        'Германская империя': ['Камерун', 'Того'],
        'Италия': ['Ливия', 'Эритрея'],
        'Португалия': ['Ангола', 'Мозамбик'],
        'Нидерланды': ['Индонезия'],
        'Бельгия': ['Конго'],
        'Испания': ['Марокко (часть)'],
    }
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    for country, colonies in colonial_powers.items():
        uid = get_user_id_by_country(country)
        if uid:
            for colony in colonies:
                cur.execute("SELECT id FROM colonies WHERE user_id=? AND name=?", (uid, colony))
                if not cur.fetchone():
                    cur.execute("INSERT INTO colonies (user_id, name, income, loyalty, invested, last_update) VALUES (?, ?, ?, ?, ?, ?)",
                                (uid, colony, random.randint(5,20), random.randint(40,80), 0, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def update_colonies():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, income, loyalty, last_update FROM colonies")
    rows = cur.fetchall()
    now = datetime.now()
    for col_id, uid, income, loyalty, last_upd_str in rows:
        last_upd = datetime.fromisoformat(last_upd_str)
        minutes = (now - last_upd).total_seconds() / 60
        if minutes >= 10:
            if loyalty > 30:
                earned = income * (minutes // 10)
                add_resources(uid, int(earned))
            loyalty -= random.randint(0,5)
            if loyalty < 0: loyalty = 0
            cur.execute("UPDATE colonies SET loyalty=?, last_update=? WHERE id=?", (loyalty, now.isoformat(), col_id))
            if loyalty == 0:
                cur.execute("DELETE FROM colonies WHERE id=?", (col_id,))
                event_desc = f"Колония {row[2]} восстала и отделилась!"
                cur.execute("INSERT INTO events_log (user_id, event_type, description, date) VALUES (?, ?, ?, ?)",
                            (uid, 'rebellion', event_desc, now.isoformat()))
    conn.commit()
    conn.close()

def invest_colony(user_id: int, colony_name: str, amount: int):
    if get_money(user_id) < amount:
        return False, "Недостаточно денег."
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, income, loyalty, invested FROM colonies WHERE user_id=? AND name=?", (user_id, colony_name))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "Колония не найдена."
    col_id, income, loyalty, invested = row
    deduct_money(user_id, amount)
    new_invested = invested + amount
    new_income = income + int(amount // 100)
    new_loyalty = min(100, loyalty + int(amount // 200))
    cur.execute("UPDATE colonies SET income=?, loyalty=?, invested=? WHERE id=?", (new_income, new_loyalty, new_invested, col_id))
    conn.commit()
    conn.close()
    return True, f"Инвестиции в {colony_name} успешны! Доход +{new_income-income}, лояльность +{new_loyalty-loyalty}."

def create_war(initiator_id: int, target_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute("""INSERT INTO wars (start_time, status, initiator_id, target_id)
                   VALUES (?, ?, ?, ?)""", (now, 'active', initiator_id, target_id))
    war_id = cur.lastrowid
    cur.execute("INSERT INTO war_participants (war_id, user_id, side, joined_at) VALUES (?, ?, ?, ?)",
                (war_id, initiator_id, 'attacker', now))
    cur.execute("INSERT INTO war_participants (war_id, user_id, side, joined_at) VALUES (?, ?, ?, ?)",
                (war_id, target_id, 'defender', now))
    conn.commit()
    conn.close()
    return war_id

def get_active_war_for_user(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""SELECT w.id FROM wars w JOIN war_participants wp ON w.id = wp.war_id
                   WHERE wp.user_id = ? AND w.status = 'active'""", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def get_war_participants(war_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, side FROM war_participants WHERE war_id=?", (war_id,))
    rows = cur.fetchall()
    conn.close()
    attackers = [r[0] for r in rows if r[1] == 'attacker']
    defenders = [r[0] for r in rows if r[1] == 'defender']
    return attackers, defenders

def get_war_info(war_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT start_time, status, winner_id, initiator_id FROM wars WHERE id=?", (war_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {'start_time': datetime.fromisoformat(row[0]), 'status': row[1], 'winner_id': row[2], 'initiator_id': row[3]}
    return None

def add_participant(war_id: int, user_id: int, side: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO war_participants (war_id, user_id, side, joined_at) VALUES (?, ?, ?, ?)",
                (war_id, user_id, side, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def finish_war(war_id: int, winner_id: int = None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE wars SET status='finished', winner_id=? WHERE id=?", (winner_id, war_id))
    conn.commit()
    conn.close()

def get_country_power(user_id: int) -> int:
    stats = get_user_stats(user_id)
    if not stats:
        return 0
    mil = stats['military']
    res = stats['resources']
    eco = stats['economy']
    pop = stats['population']
    fort = stats['fortifications']
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT tech_name, level FROM technologies WHERE user_id=?", (user_id,))
    techs = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    infantry_bonus = 1 + (techs.get('infantry', 0) * 0.02)
    artillery_bonus = 1 + (techs.get('artillery', 0) * 0.03)
    power = int(mil * infantry_bonus * artillery_bonus) + res + eco + pop // 1000 + fort
    return power

def resolve_war(war_id: int):
    info = get_war_info(war_id)
    if not info or info['status'] != 'active':
        return None
    attackers, defenders = get_war_participants(war_id)
    if not attackers or not defenders:
        finish_war(war_id)
        return None
    total_att = sum(get_country_power(u) for u in attackers if get_user_country(u))
    total_def = sum(get_country_power(u) for u in defenders if get_user_country(u))
    if total_att >= total_def:
        winner_ids = attackers
        loser_ids = defenders
    else:
        winner_ids = defenders
        loser_ids = attackers
    for loser_id in loser_ids:
        stats = get_user_stats(loser_id)
        if stats:
            new_pop = int(stats['population'] * 0.95)
            new_mil = int(stats['military'] * 0.8)
            new_eco = int(stats['economy'] * 0.9)
            new_res = int(stats['resources'] * 0.7)
            new_money = int(stats['money'] * 0.8)
            set_user_stats(loser_id, population=new_pop, military=new_mil, economy=new_eco,
                           resources=new_res, money=new_money)
    for winner_id in winner_ids:
        stats = get_user_stats(winner_id)
        if stats:
            new_res = int(stats['resources'] * 1.1)
            new_money = int(stats['money'] * 1.1)
            set_user_stats(winner_id, resources=new_res, money=new_money)
    winner_id = winner_ids[0] if winner_ids else None
    finish_war(war_id, winner_id)
    return {
        'winner_side': 'attacker' if winner_id in attackers else 'defender',
        'winner_ids': winner_ids,
        'loser_ids': loser_ids,
        'winner_countries': [get_user_country(u) for u in winner_ids if get_user_country(u)],
        'loser_countries': [get_user_country(u) for u in loser_ids if get_user_country(u)]
    }

def check_and_resolve_wars():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, start_time FROM wars WHERE status='active'")
    rows = cur.fetchall()
    now = datetime.now()
    for war_id, start_str in rows:
        start = datetime.fromisoformat(start_str)
        if (now - start) >= timedelta(minutes=10):
            resolve_war(war_id)
    conn.close()

TRADE_SELECT_PARTNER, TRADE_SELECT_OFFER_TYPE, TRADE_OFFER_AMOUNT, TRADE_SELECT_REQUEST_TYPE, TRADE_REQUEST_AMOUNT = range(5)

def create_trade(from_user, to_user, offered_type, offered_amount, requested_type, requested_amount):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""INSERT INTO trades (from_user, to_user, status, offered_type, offered_amount,
                   requested_type, requested_amount, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                   (from_user, to_user, 'pending', offered_type, offered_amount,
                    requested_type, requested_amount, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def accept_trade(trade_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT from_user, to_user, offered_type, offered_amount, requested_type, requested_amount FROM trades WHERE id=? AND status='pending'", (trade_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False
    from_u, to_u, off_type, off_amt, req_type, req_amt = row
    ok = True
    if off_type == 'resources':
        if get_resources(from_u) < off_amt:
            ok = False
    else:
        if get_money(from_u) < off_amt:
            ok = False
    if ok and req_type == 'resources':
        if get_resources(to_u) < req_amt:
            ok = False
    elif ok and req_type == 'money':
        if get_money(to_u) < req_amt:
            ok = False
    if not ok:
        cur.execute("UPDATE trades SET status='rejected' WHERE id=?", (trade_id,))
        conn.commit()
        conn.close()
        return False
    if off_type == 'resources':
        deduct_resources(from_u, off_amt)
        add_resources(to_u, off_amt)
    else:
        deduct_money(from_u, off_amt)
        add_money(to_u, off_amt)
    if req_type == 'resources':
        deduct_resources(to_u, req_amt)
        add_resources(from_u, req_amt)
    else:
        deduct_money(to_u, req_amt)
        add_money(from_u, req_amt)
    cur.execute("UPDATE trades SET status='accepted' WHERE id=?", (trade_id,))
    conn.commit()
    conn.close()
    return True

def reject_trade(trade_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE trades SET status='rejected' WHERE id=?", (trade_id,))
    conn.commit()
    conn.close()

def economic_crisis(user_id: int):
    stats = get_user_stats(user_id)
    if stats:
        new_eco = int(stats['economy'] * 0.8)
        new_money = int(stats['money'] * 0.9)
        increase_inflation(user_id, 0.05)
        set_user_stats(user_id, economy=new_eco, money=new_money)
        return True
    return False

def get_logistics_cost(attacker_id: int, defender_id: int) -> int:
    dist = abs(attacker_id - defender_id) % 100
    return dist * 2

def build_fortifications(user_id: int, amount: int):
    cost = amount * 10
    if get_money(user_id) < cost:
        return False, "Недостаточно денег."
    deduct_money(user_id, cost)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET fortifications = fortifications + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()
    return True, f"Укрепления построены (+{amount})."

def occupy_territory(occupier_id: int, occupied_country: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT occupied_territory FROM users WHERE user_id=?", (occupier_id,))
    row = cur.fetchone()
    if row:
        occ_list = json.loads(row[0])
        if occupied_country not in occ_list:
            occ_list.append(occupied_country)
            cur.execute("UPDATE users SET occupied_territory=? WHERE user_id=?", (json.dumps(occ_list), occupier_id))
            cur.execute("INSERT OR REPLACE INTO occupations (occupier_id, occupied_country, since, resistance) VALUES (?, ?, ?, ?)",
                        (occupier_id, occupied_country, datetime.now().isoformat(), 50))
    conn.commit()
    conn.close()

def get_resistance(occupier_id: int, occupied_country: str) -> int:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT resistance FROM occupations WHERE occupier_id=? AND occupied_country=?", (occupier_id, occupied_country))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def update_resistance():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT occupier_id, occupied_country, resistance FROM occupations")
    rows = cur.fetchall()
    for occ_id, country, res in rows:
        new_res = min(100, res + random.randint(0, 5))
        cur.execute("UPDATE occupations SET resistance=? WHERE occupier_id=? AND occupied_country=?", (new_res, occ_id, country))
        if new_res >= 80 and random.random() < 0.3:
            cur.execute("DELETE FROM occupations WHERE occupier_id=? AND occupied_country=?", (occ_id, country))
            cur.execute("SELECT occupied_territory FROM users WHERE user_id=?", (occ_id,))
            row2 = cur.fetchone()
            if row2:
                occ_list = json.loads(row2[0])
                if country in occ_list:
                    occ_list.remove(country)
                    cur.execute("UPDATE users SET occupied_territory=? WHERE user_id=?", (json.dumps(occ_list), occ_id))
            cur.execute("INSERT INTO events_log (user_id, event_type, description, date) VALUES (?, ?, ?, ?)",
                        (occ_id, 'rebellion', f"Восстание в {country}! Оккупация снята.", datetime.now().isoformat()))
    conn.commit()
    conn.close()

def update_currency_rates():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT country FROM users")
    countries = [row[0] for row in cur.fetchall()]
    for country in countries:
        currency = COUNTRIES_DATA.get(country, {}).get("currency", "ден. ед.")
        if currency:
            change = random.uniform(-0.05, 0.05)
            cur.execute("SELECT rate FROM currency_rates WHERE currency=?", (currency,))
            row = cur.fetchone()
            if row:
                new_rate = max(0.1, row[0] * (1 + change))
                cur.execute("UPDATE currency_rates SET rate=?, last_update=? WHERE currency=?", (new_rate, datetime.now().isoformat(), currency))
            else:
                cur.execute("INSERT INTO currency_rates (currency, rate, last_update) VALUES (?, ?, ?)",
                            (currency, 1.0 + random.uniform(-0.1, 0.1), datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_currency_rate(currency: str) -> float:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT rate FROM currency_rates WHERE currency=?", (currency,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 1.0

def build_fleet(user_id: int, amount: int):
    cost_per_ship = 1000
    total_cost = amount * cost_per_ship
    if get_money(user_id) < total_cost:
        return False, f"Недостаточно денег. Нужно {total_cost}, у вас {get_money(user_id)}."
    deduct_money(user_id, total_cost)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET fleet = fleet + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()
    return True, f"Построено {amount} кораблей за {total_cost} денег."

def blockade(blockader_id: int, target_id: int):
    stats_b = get_user_stats(blockader_id)
    stats_t = get_user_stats(target_id)
    if not stats_b or not stats_t:
        return False, "Ошибка данных."
    if stats_b['fleet'] < stats_t['fleet'] * 1.2:
        return False, "Недостаточно флота для блокады."
    lost_res = int(stats_t['resources'] * 0.05)
    lost_money = int(stats_t['money'] * 0.05)
    deduct_resources(target_id, lost_res)
    deduct_money(target_id, lost_money)
    return True, f"Блокада успешна! {get_user_country(target_id)} потерял {lost_res} ресурсов и {lost_money} денег."

def create_vote(proposer_id: int, proposal: str, description: str, duration_hours: int = 24):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    until = datetime.now() + timedelta(hours=duration_hours)
    cur.execute("""INSERT INTO votes (proposer_id, proposal, description, status, until)
                   VALUES (?, ?, ?, ?, ?)""", (proposer_id, proposal, description, 'active', until.isoformat()))
    vote_id = cur.lastrowid
    conn.commit()
    conn.close()
    return vote_id

def vote(vote_id: int, user_id: int, choice: str):
    if choice not in ['for', 'against']:
        return False
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT status FROM votes WHERE id=?", (vote_id,))
    row = cur.fetchone()
    if not row or row[0] != 'active':
        conn.close()
        return False
    cur.execute("SELECT 1 FROM vote_records WHERE vote_id=? AND user_id=?", (vote_id, user_id))
    if cur.fetchone():
        conn.close()
        return False
    cur.execute("INSERT INTO vote_records (vote_id, user_id, choice) VALUES (?, ?, ?)", (vote_id, user_id, choice))
    if choice == 'for':
        cur.execute("UPDATE votes SET votes_for = votes_for + 1 WHERE id=?", (vote_id,))
    else:
        cur.execute("UPDATE votes SET votes_against = votes_against + 1 WHERE id=?", (vote_id,))
    conn.commit()
    conn.close()
    return True

def check_votes():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, votes_for, votes_against, until FROM votes WHERE status='active'")
    rows = cur.fetchall()
    now = datetime.now()
    for vote_id, v_for, v_against, until_str in rows:
        until = datetime.fromisoformat(until_str)
        if now >= until:
            status = 'accepted' if v_for > v_against else 'rejected'
            cur.execute("UPDATE votes SET status=? WHERE id=?", (status, vote_id))
    conn.commit()
    conn.close()

def update_user_stats(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""SELECT population, military, economy, resources, money, fleet, inflation,
                   last_update, master_id, is_puppet, neutral, mobilized, base_military,
                   mobilized_until, fortifications, occupied_territory
                   FROM users WHERE user_id=?""", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return
    (pop, mil, eco, res, money, fleet, inf, last_upd_str,
     master_id, is_puppet, neutral, mobilized, base_mil, mob_until,
     fort, occ_terr) = row
    last_upd = datetime.fromisoformat(last_upd_str)
    now = datetime.now()
    hours = (now - last_upd).total_seconds() / 3600
    if hours < 0.05:
        conn.close()
        return
    inflation_factor = 1.0 / (1.0 + inf)
    cur.execute("SELECT tech_name, level FROM technologies WHERE user_id=?", (user_id,))
    techs = {row[0]: row[1] for row in cur.fetchall()}
    eco_bonus = 1 + (techs.get('economy', 0) * 0.02)
    med_bonus = 1 - (techs.get('medicine', 0) * 0.05)
    month = now.month
    if 12 <= month <= 2:
        season = 'winter'
    elif 3 <= month <= 5:
        season = 'spring'
    elif 6 <= month <= 8:
        season = 'summer'
    else:
        season = 'autumn'
    if season == 'winter':
        eco_growth_mod = 0.5
        mil_growth_mod = 0.7
    elif season == 'spring':
        eco_growth_mod = 1.0
        mil_growth_mod = 1.0
    elif season == 'summer':
        eco_growth_mod = 1.2
        mil_growth_mod = 1.1
    else:
        eco_growth_mod = 0.8
        mil_growth_mod = 0.9
    pop_growth = 0.0001 * hours * (1 + (techs.get('economy', 0) * 0.01))
    pop = int(pop * (1 + pop_growth))
    mil = max(0, int(mil * (1 - 0.001 * hours * mil_growth_mod)))
    eco_growth = 0.0005 * hours * eco_bonus * inflation_factor * eco_growth_mod
    eco = int(eco * (1 + eco_growth))
    res_growth = 0.001 * hours * eco_bonus * inflation_factor * eco_growth_mod
    res = int(res * (1 + res_growth))
    money_growth = 0.002 * hours * eco_bonus * inflation_factor * eco_growth_mod
    money = int(money * (1 + money_growth))
    fleet = max(0, int(fleet * (1 - 0.002 * hours)))
    if mobilized and mob_until:
        mob_until_dt = datetime.fromisoformat(mob_until)
        if now < mob_until_dt:
            mil = int(base_mil * 1.5)
            eco = int(eco * 0.8)
            pop = int(pop * 0.95)
        else:
            cur.execute("UPDATE users SET mobilized=0, military=base_military WHERE user_id=?", (user_id,))
            mil = base_mil
            eco = int(eco / 0.8)
            pop = int(pop / 0.95)
            cur.execute("UPDATE users SET economy=?, population=? WHERE user_id=?", (eco, pop, user_id))
    if neutral:
        eco = int(eco * 1.1)
    if master_id is not None:
        old_res = row[3]
        gained = res - old_res
        if gained > 0:
            master_share = int(gained * 0.1)
            if master_share > 0:
                cur.execute("UPDATE users SET resources = resources + ? WHERE user_id = ?", (master_share, master_id))
    cur.execute("""UPDATE users SET population=?, military=?, economy=?, resources=?, money=?, fleet=?, last_update=?
                   WHERE user_id=?""", (pop, mil, eco, res, money, fleet, now.isoformat(), user_id))
    conn.commit()
    conn.close()

def create_bots_if_needed():
    occupied = get_all_users_countries()
    for country in COUNTRIES_LIST:
        if country not in occupied:
            bot_id = -random.randint(1000, 999999)
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM users WHERE user_id=?", (bot_id,))
            if cur.fetchone():
                conn.close()
                continue
            data = COUNTRIES_DATA.get(country, {})
            cur.execute("""INSERT INTO users (user_id, country, resources, money, population, military, economy, fleet, inflation,
                           last_update, master_id, is_puppet, neutral, mobilized, base_military, is_bot, fortifications)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (bot_id, country, data.get('initial_resources',1000), 10000,
                            data.get('population',10000000), data.get('army',100000),
                            data.get('initial_economy',500), 0, 0.0,
                            datetime.now().isoformat(), None, 0, 0, 0, data.get('army',100000), 1, 0))
            conn.commit()
            conn.close()
            logger.info(f"Бот создан для страны {country} (ID {bot_id})")

def get_bot_ids():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE is_bot=1")
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]

async def bot_actions(context: ContextTypes.DEFAULT_TYPE):
    bot_ids = get_bot_ids()
    if not bot_ids:
        return
    for bot_id in bot_ids:
        if random.random() < 0.5:
            continue
        actions = ['research','invest','mobilize','demobilize','spy','napt','sanction','ally','break_ally','war','invest_colony','trade']
        action = random.choice(actions)
        bot_country = get_user_country(bot_id)
        if not bot_country:
            continue
        all_users = get_all_users_countries()
        available = [uid for uid in all_users.values() if uid['user_id'] != bot_id and not uid['is_puppet']]
        if not available:
            continue
        target = random.choice(available)['user_id']
        target_country = get_user_country(target)
        try:
            if action == 'research':
                tech = random.choice(TECH_LIST)
                result, msg = start_research(bot_id, tech)
                if result:
                    logger.info(f"Бот {bot_country} начал исследование {tech}")
            elif action == 'invest':
                amount = random.randint(100,1000)
                if get_money(bot_id) >= amount:
                    stats = get_user_stats(bot_id)
                    if stats:
                        if random.random() < 0.5:
                            add = int(amount * 0.5)
                            new_military = stats['military'] + add
                            set_user_stats(bot_id, military=new_military)
                        else:
                            add = int(amount * 0.3)
                            new_economy = stats['economy'] + add
                            set_user_stats(bot_id, economy=new_economy)
                        deduct_money(bot_id, amount)
                        logger.info(f"Бот {bot_country} инвестировал {amount}")
            elif action == 'mobilize':
                if not get_user_stats(bot_id)['mobilized']:
                    success, msg = mobilize(bot_id)
                    if success:
                        logger.info(f"Бот {bot_country} мобилизовался")
            elif action == 'demobilize':
                if get_user_stats(bot_id)['mobilized']:
                    success, msg = demobilize(bot_id)
                    if success:
                        logger.info(f"Бот {bot_country} демобилизовался")
            elif action == 'spy':
                act = random.choice(['разведка','саботаж'])
                result = spy_action(bot_id, target, act)
                if result['success']:
                    logger.info(f"Бот {bot_country} провёл {act} против {target_country}")
            elif action == 'napt':
                if not has_napt(bot_id, target):
                    success, msg = create_napt(bot_id, target)
                    if success:
                        logger.info(f"Бот {bot_country} заключил NAPT с {target_country}")
            elif action == 'sanction':
                if not has_sanction(bot_id, target) and not is_ally(bot_id, target):
                    create_sanction(bot_id, target)
                    logger.info(f"Бот {bot_country} ввёл санкции против {target_country}")
            elif action == 'ally':
                if not is_ally(bot_id, target) and len(get_allies(bot_id, 'accepted')) < 3:
                    create_ally_request(bot_id, target)
                    accept_ally(target, bot_id)
                    logger.info(f"Бот {bot_country} заключил союз с {target_country}")
            elif action == 'break_ally':
                allies = get_allies(bot_id, 'accepted')
                if allies:
                    ally_id = random.choice(allies)
                    break_ally(bot_id, ally_id)
                    logger.info(f"Бот {bot_country} разорвал союз с {get_user_country(ally_id)}")
            elif action == 'war':
                if not get_active_war_for_user(bot_id) and not is_ally(bot_id, target) and not has_napt(bot_id, target):
                    t_stats = get_user_stats(target)
                    if t_stats and not t_stats['neutral'] and not t_stats['is_puppet']:
                        war_id = create_war(bot_id, target)
                        result = resolve_war(war_id)
                        if result:
                            logger.info(f"Бот {bot_country} начал войну с {target_country}")
            elif action == 'invest_colony':
                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()
                cur.execute("SELECT name FROM colonies WHERE user_id=?", (bot_id,))
                colonies = cur.fetchall()
                conn.close()
                if colonies:
                    colony_name = random.choice(colonies)[0]
                    amount = random.randint(100,500)
                    if get_money(bot_id) >= amount:
                        success, msg = invest_colony(bot_id, colony_name, amount)
                        if success:
                            logger.info(f"Бот {bot_country} инвестировал в колонию {colony_name}")
            elif action == 'trade':
                if not is_sanctioned_between(bot_id, target):
                    offered_type = random.choice(['resources','money'])
                    requested_type = random.choice(['resources','money'])
                    offered_amount = random.randint(10,200) if offered_type=='resources' else random.randint(100,1000)
                    requested_amount = random.randint(10,200) if requested_type=='resources' else random.randint(100,1000)
                    if offered_type == 'resources' and get_resources(bot_id) < offered_amount:
                        continue
                    if offered_type == 'money' and get_money(bot_id) < offered_amount:
                        continue
                    create_trade(bot_id, target, offered_type, offered_amount, requested_type, requested_amount)
                    conn = sqlite3.connect(DB_FILE)
                    cur = conn.cursor()
                    cur.execute("SELECT id FROM trades WHERE from_user=? AND to_user=? AND status='pending'", (bot_id, target))
                    row = cur.fetchone()
                    conn.close()
                    if row:
                        trade_id = row[0]
                        success = accept_trade(trade_id)
                        if success:
                            logger.info(f"Бот {bot_country} успешно обменялся с {target_country}")
        except Exception as e:
            logger.error(f"Ошибка бота {bot_id}: {e}")

# ============ НОВАЯ КОМАНДА ДЛЯ ИНВЕСТИЦИЙ В НАСЕЛЕНИЕ ============
async def invest_population_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может инвестировать.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Использование: /invest_population <сумма>")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Сумма должна быть числом.")
        return
    if amount < 1000:
        await update.message.reply_text("❌ Минимальная сумма инвестиции – 1000 денег.")
        return
    money = get_money(user_id)
    if money < amount:
        await update.message.reply_text(f"❌ У вас недостаточно денег. Нужно {amount}, у вас {money}.")
        return
    stats = get_user_stats(user_id)
    pop = stats['population']
    # Стоимость одного человека растёт с населением: 0.01 + pop/1_000_000_000
    cost_per_unit = 0.01 + (pop / 1_000_000_000)
    gain = int(amount / cost_per_unit)
    if gain == 0:
        await update.message.reply_text("❌ Сумма слишком мала для прироста населения.")
        return
    deduct_money(user_id, amount)
    new_pop = pop + gain
    set_user_stats(user_id, population=new_pop)
    await update.message.reply_text(
        f"✅ Вложили {amount} денег в развитие населения.\n"
        f"Прирост: +{gain} человек\n"
        f"Население теперь: {new_pop:,}\n"
        f"Стоимость одного человека: {cost_per_unit:.4f} денег."
    )

# ============ ОБРАБОТЧИКИ КОМАНД ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах. Добавьте меня в группу, чтобы начать игру.")
        return
    await update.message.reply_text(
        "Добро пожаловать в игру «Завоевание мира 1914»!\n\n"
        "🇪🇺 /country – выбрать страну\n"
        "📊 /mystats – моя статистика\n"
        "🔍 /info <страна> – информация о стране\n"
        "⚔️ /war <страна> – объявить войну\n"
        "🤝 /ally <страна> – предложить союз\n"
        "📋 /allies – список союзников\n"
        "📜 /napt <страна> – договор о ненападении\n"
        "🚫 /sanction <страна> – ввести санкции\n"
        "🔬 /research – технологии\n"
        "🕵️ /spy <страна> – шпионаж\n"
        "💰 /invest <army|economy> <сумма> – инвестировать\n"
        "📈 /invest_population <сумма> – увеличить население (дорого, прогрессивная шкала)\n"
        "⚔️ /mobilize – мобилизация\n"
        "🛡️ /demobilize – демобилизация\n"
        "🌍 /colonies – мои колонии\n"
        "⚓ /build_fleet <число> – построить флот\n"
        "🚫 /blockade <страна> – морская блокада\n"
        "🗳️ /vote <предложение> <описание> – создать голосование\n"
        "🗳️ /vote_cast <id> for/against – проголосовать\n"
        "🧭 /season – текущий сезон\n"
        "💱 /currency – курс валюты\n"
        "🏆 /top – рейтинг\n"
        "🔄 /reset – сбросить страну"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def country_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    users = get_all_users_countries()
    keyboard = []
    for i in range(0, len(COUNTRIES_LIST), 2):
        row = []
        for c in COUNTRIES_LIST[i:i+2]:
            if c in users:
                if users[c]['is_puppet']: label = c + " 🟠"
                elif users[c]['is_bot']: label = c + " 🤖"
                else: label = c + " 🔴"
            else:
                label = c + " 🟢"
            row.append(InlineKeyboardButton(label, callback_data=f"select_{c}"))
        keyboard.append(row)
    await update.message.reply_text("👇 Выберите страну (🔴 занята, 🤖 бот, 🟠 марионетка, 🟢 свободна):", reply_markup=InlineKeyboardMarkup(keyboard))

async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    stats = get_user_stats(user_id)
    if not stats:
        await update.message.reply_text("Вы не выбрали страну. Используйте /country.")
        return
    currency = get_country_currency(stats['country'])
    text = (
        f"📊 *{stats['country']}*\n"
        f"├ Население: {stats['population']:,}\n"
        f"├ Армия: {stats['military']:,}\n"
        f"├ Экономика: {stats['economy']}\n"
        f"├ Ресурсы: {stats['resources']}\n"
        f"├ Деньги: {stats['money']} {currency}\n"
        f"├ Флот: {stats['fleet']}\n"
        f"├ Инфляция: {stats['inflation']*100:.1f}%\n"
        f"├ Укрепления: {stats['fortifications']}\n"
        f"└ Статус: {'Марионетка' if stats['is_puppet'] else ('Нейтрал' if stats['neutral'] else 'Активна')}"
    )
    if stats['is_puppet']:
        master = get_user_country(stats['master_id'])
        text += f"\n👑 Хозяин: {master}" if master else ""
    await update.message.reply_text(text, parse_mode="Markdown")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    if not context.args:
        await update.message.reply_text("Укажите страну: /info <название>")
        return
    name = " ".join(context.args)
    found = None
    for c in COUNTRIES_LIST:
        if c.lower() == name.lower():
            found = c
            break
    if not found:
        for c in COUNTRIES_LIST:
            if name.lower() in c.lower():
                found = c
                break
    if found:
        data = COUNTRIES_DATA[found]
        await update.message.reply_text(
            f"🏛️ *{found}*\n"
            f"├ Столица: {data['capital']}\n"
            f"├ Население: {data['population']:,}\n"
            f"├ Армия: {data['army']:,}\n"
            f"├ Ресурсы: {data['initial_resources']}\n"
            f"├ Экономика: {data['initial_economy']}\n"
            f"└ Валюта: {data['currency']}", parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("Страна не найдена.")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    delete_user_country(user_id)
    await update.message.reply_text("✅ Ваша страна сброшена. Используйте /country для выбора новой.")

async def war_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может воевать.")
        return
    if get_active_war_for_user(user_id):
        await update.message.reply_text("❌ Вы уже участвуете в войне.")
        return
    stats = get_user_stats(user_id)
    if not stats:
        await update.message.reply_text("❌ Вы не выбрали страну. Используйте /country.")
        return
    if stats['neutral']:
        await update.message.reply_text("❌ Нейтральная страна не может воевать.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Укажите страну-противника: /war <название>")
        return
    target_name = " ".join(context.args)
    defender = None
    for c in COUNTRIES_LIST:
        if c.lower() == target_name.lower():
            defender = c
            break
    if not defender:
        await update.message.reply_text("❌ Страна не найдена. Список стран: /countries")
        return
    def_id = get_user_id_by_country(defender)
    if not def_id:
        await update.message.reply_text(f"❌ {defender} не занята игроком.")
        return
    if def_id == user_id:
        await update.message.reply_text("❌ Нельзя воевать с собой.")
        return
    if has_napt(user_id, def_id) or has_napt(def_id, user_id):
        await update.message.reply_text("❌ Действует договор о ненападении. Нарушение пакта приведёт к серьёзным штрафам.")
        return
    if is_puppet(def_id):
        master = get_master(def_id)
        master_country = get_user_country(master) if master else None
        await update.message.reply_text(f"❌ {defender} является марионеткой {master_country}. Воевать нужно с хозяином.")
        return
    if is_ally(user_id, def_id):
        await update.message.reply_text("❌ Нельзя нападать на союзника.")
        return
    target_stats = get_user_stats(def_id)
    if target_stats and target_stats['neutral']:
        await update.message.reply_text(f"❌ {defender} – нейтральная страна.")
        return
    war_id = create_war(user_id, def_id)
    await update.message.reply_text(f"⚔️ Война объявлена {defender}! Война длится 10 минут.\n"
                                     f"Команды: /peace <страна> – предложить мир, /war_end – завершить войну.")

async def peace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    war_id = get_active_war_for_user(user_id)
    if not war_id:
        await update.message.reply_text("❌ Вы не участвуете в войне.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Укажите страну для мирного договора: /peace <страна>")
        return
    target_name = " ".join(context.args)
    target_id = get_user_id_by_country(target_name)
    if not target_id:
        await update.message.reply_text(f"❌ Страна {target_name} не найдена.")
        return
    attackers, defenders = get_war_participants(war_id)
    if user_id in attackers and target_id not in defenders:
        await update.message.reply_text("❌ Это не противник.")
        return
    if user_id in defenders and target_id not in attackers:
        await update.message.reply_text("❌ Это не противник.")
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO peace_requests (war_id, from_user, to_user, status, date) VALUES (?, ?, ?, ?, ?)",
                (war_id, user_id, target_id, 'pending', datetime.now().isoformat()))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🕊️ Предложение мира отправлено {target_name}.")

async def war_end_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    war_id = get_active_war_for_user(user_id)
    if not war_id:
        await update.message.reply_text("❌ Вы не участвуете в войне.")
        return
    info = get_war_info(war_id)
    if info['initiator_id'] != user_id:
        await update.message.reply_text("❌ Только инициатор может завершить войну.")
        return
    result = resolve_war(war_id)
    if not result:
        await update.message.reply_text("❌ Ошибка при завершении войны.")
        return
    winner_ids = result['winner_ids']
    loser_ids = result['loser_ids']
    winner_countries = result['winner_countries']
    loser_countries = result['loser_countries']
    
    if len(winner_ids) == 1:
        winner_id = winner_ids[0]
        loser_id = loser_ids[0]
        loser_country = loser_countries[0]
        keyboard = [
            [InlineKeyboardButton("💀 Захватить", callback_data=f"conquer_{war_id}_{winner_id}_{loser_id}")],
            [InlineKeyboardButton("🤝 Сделать марионеткой", callback_data=f"puppet_{war_id}_{winner_id}_{loser_id}")]
        ]
        await context.bot.send_message(
            chat_id=winner_id,
            text=f"🏆 Вы победили в войне!\nЧто сделать с {loser_country}?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await update.message.reply_text(
            f"⚔️ **Война завершена!**\n"
            f"🏆 Победитель: {winner_countries[0]}\n"
            f"📉 Проигравший: {loser_countries[0]}\n"
            f"Победитель получил +10% ресурсов и денег.\n"
            f"Проигравший потерял 5% населения, 20% армии, 10% экономики, 30% ресурсов и 20% денег.\n\n"
            f"📩 Победителю отправлен выбор в личные сообщения.",
            parse_mode="Markdown"
        )
    else:
        winner_str = ", ".join(winner_countries)
        loser_str = ", ".join(loser_countries)
        await update.message.reply_text(
            f"⚔️ **Война завершена!**\n"
            f"🏆 Победители: {winner_str}\n"
            f"📉 Проигравшие: {loser_str}\n"
            f"Победители получили +10% ресурсов и денег.\n"
            f"Проигравшие потеряли 5% населения, 20% армии, 10% экономики, 30% ресурсов и 20% денег.",
            parse_mode="Markdown"
        )

async def ally_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может заключать союзы.")
        return
    stats = get_user_stats(user_id)
    if not stats:
        await update.message.reply_text("❌ Вы не выбрали страну. Используйте /country.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Укажите страну-союзника: /ally <название>")
        return
    target_name = " ".join(context.args)
    target_id = get_user_id_by_country(target_name)
    if not target_id:
        await update.message.reply_text(f"❌ Страна {target_name} не найдена.")
        return
    if target_id == user_id:
        await update.message.reply_text("❌ Нельзя заключить союз с собой.")
        return
    if is_puppet(target_id):
        await update.message.reply_text("❌ Нельзя заключить союз с марионеткой.")
        return
    if is_ally(user_id, target_id):
        await update.message.reply_text("❌ Вы уже союзники.")
        return
    if len(get_allies(user_id, 'accepted')) >= 3:
        await update.message.reply_text("❌ У вас уже 3 союзника.")
        return
    if len(get_allies(target_id, 'accepted')) >= 3:
        await update.message.reply_text(f"❌ У {target_name} уже 3 союзника.")
        return
    create_ally_request(user_id, target_id)
    keyboard = [
        [InlineKeyboardButton("✅ Принять", callback_data=f"ally_accept_{user_id}_{target_id}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"ally_reject_{user_id}_{target_id}")]
    ]
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🤝 {stats['country']} предлагает союз {target_name}!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("✅ Запрос на союз отправлен.")

async def allies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    allies = get_ally_countries(user_id)
    if not allies:
        await update.message.reply_text("❌ У вас нет союзников.")
        return
    await update.message.reply_text("🤝 Ваши союзники:\n" + "\n".join(f"- {c}" for c in allies))

async def napt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может заключать договоры.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Укажите страну: /napt <название>")
        return
    target_name = " ".join(context.args)
    target_id = get_user_id_by_country(target_name)
    if not target_id:
        await update.message.reply_text(f"❌ Страна {target_name} не найдена.")
        return
    if target_id == user_id:
        await update.message.reply_text("❌ Нельзя заключить договор с собой.")
        return
    if is_ally(user_id, target_id):
        await update.message.reply_text("❌ Вы уже союзники, договор не нужен.")
        return
    success, msg = create_napt(user_id, target_id)
    await update.message.reply_text(msg)

async def break_napt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может разрывать договоры.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Укажите страну: /break_napt <название>")
        return
    target_name = " ".join(context.args)
    target_id = get_user_id_by_country(target_name)
    if not target_id:
        await update.message.reply_text(f"❌ Страна {target_name} не найдена.")
        return
    if target_id == user_id:
        await update.message.reply_text("❌ Нельзя разорвать договор с собой.")
        return
    if not has_napt(user_id, target_id):
        await update.message.reply_text("❌ У вас нет действующего договора о ненападении с этой страной.")
        return
    keyboard = [
        [InlineKeyboardButton("✅ Да, разорвать (со штрафом)", callback_data=f"break_napt_confirm_{user_id}_{target_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data="break_napt_cancel")]
    ]
    await update.message.reply_text(
        "⚠️ Разрыв договора о ненападении приведёт к серьёзным штрафам:\n"
        "- Потеря 15% ресурсов и денег\n"
        "- Экономика падает на 10%\n"
        "- Инфляция растёт на 5%\n\n"
        "Вы уверены?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def sanction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может вводить санкции.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Укажите страну: /sanction <название>")
        return
    target_name = " ".join(context.args)
    target_id = get_user_id_by_country(target_name)
    if not target_id:
        await update.message.reply_text(f"❌ Страна {target_name} не найдена.")
        return
    if target_id == user_id:
        await update.message.reply_text("❌ Нельзя ввести санкции против себя.")
        return
    if is_ally(user_id, target_id):
        await update.message.reply_text("❌ Нельзя вводить санкции против союзника.")
        return
    if is_puppet(target_id):
        await update.message.reply_text("❌ Нельзя вводить санкции против марионетки.")
        return
    if has_sanction(user_id, target_id):
        await update.message.reply_text("❌ Санкции уже действуют.")
        return
    create_sanction(user_id, target_id)
    await update.message.reply_text(f"🚫 Санкции против {target_name} введены на 24 часа.")

async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может исследовать технологии.")
        return
    keyboard = []
    for tech in TECH_LIST:
        level = get_tech_level(user_id, tech)
        status = f"Уровень {level}/5"
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM research_queue WHERE user_id=? AND tech_name=?", (user_id, tech))
        in_queue = cur.fetchone() is not None
        conn.close()
        if in_queue:
            status += " ⏳"
        elif level < 5:
            cost = TECH_PRICES[level] * 2
            status += f" (стоимость {cost} ресурсов)"
        else:
            status += " ✅"
        keyboard.append([InlineKeyboardButton(f"{TECH_NAMES[tech]} — {status}", callback_data=f"research_{tech}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="research_cancel")])
    await update.message.reply_text("🔬 Выберите технологию:", reply_markup=InlineKeyboardMarkup(keyboard))

async def spy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может шпионить.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Укажите страну: /spy <название>")
        return
    target_name = " ".join(context.args)
    target_id = get_user_id_by_country(target_name)
    if not target_id:
        await update.message.reply_text(f"❌ Страна {target_name} не найдена.")
        return
    if target_id == user_id:
        await update.message.reply_text("❌ Нельзя шпионить за собой.")
        return
    keyboard = [
        [InlineKeyboardButton("🔍 Разведка", callback_data=f"spy_{target_id}_разведка")],
        [InlineKeyboardButton("💥 Саботаж", callback_data=f"spy_{target_id}_саботаж")],
        [InlineKeyboardButton("❌ Отмена", callback_data="spy_cancel")]
    ]
    await update.message.reply_text(f"🕵️ Выберите действие против {target_name}:", reply_markup=InlineKeyboardMarkup(keyboard))

async def invest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может инвестировать.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Использование: /invest <army|economy> <сумма>")
        return
    invest_type = context.args[0].lower()
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Сумма должна быть числом.")
        return
    if amount <= 0:
        await update.message.reply_text("❌ Сумма должна быть положительной.")
        return
    money = get_money(user_id)
    if money < amount:
        await update.message.reply_text(f"❌ У вас недостаточно денег. Нужно {amount}, у вас {money}.")
        return
    deduct_money(user_id, amount)
    stats = get_user_stats(user_id)
    if invest_type == "army":
        add = int(amount * 0.5)
        new_military = stats['military'] + add
        set_user_stats(user_id, military=new_military)
        await update.message.reply_text(f"✅ Вложили {amount} в армию. Армия +{add}, теперь {new_military}.")
    elif invest_type == "economy":
        add = int(amount * 0.3)
        new_economy = stats['economy'] + add
        set_user_stats(user_id, economy=new_economy)
        await update.message.reply_text(f"✅ Вложили {amount} в экономику. Экономика +{add}, теперь {new_economy}.")
    else:
        add_money(user_id, amount)
        await update.message.reply_text("❌ Неверный параметр. Используйте army или economy.")

async def mobilize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может мобилизовать армию.")
        return
    success, msg = mobilize(user_id)
    await update.message.reply_text(msg)

async def demobilize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может демобилизовать армию.")
        return
    success, msg = demobilize(user_id)
    await update.message.reply_text(msg)

async def colonies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT name, income, loyalty, invested FROM colonies WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("У вас нет колоний.")
        return
    text = "🌍 Ваши колонии:\n\n"
    for name, income, loyalty, invested in rows:
        text += f"• {name}: доход {income}/час, лояльность {loyalty}%, вложено {invested}\n"
    await update.message.reply_text(text)

async def build_fleet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может строить флот.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ /build_fleet <число>")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Введите число.")
        return
    if amount <= 0:
        await update.message.reply_text("❌ Количество должно быть >0.")
        return
    success, msg = build_fleet(user_id, amount)
    await update.message.reply_text(msg)

async def blockade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может блокировать.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /blockade <страна>")
        return
    target_name = " ".join(context.args)
    target_id = get_user_id_by_country(target_name)
    if not target_id:
        await update.message.reply_text(f"❌ Страна {target_name} не найдена.")
        return
    if target_id == user_id:
        await update.message.reply_text("❌ Нельзя блокировать себя.")
        return
    success, msg = blockade(user_id, target_id)
    await update.message.reply_text(msg)

async def vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ /vote <предложение> <описание>")
        return
    proposal = context.args[0]
    description = " ".join(context.args[1:])
    vote_id = create_vote(user_id, proposal, description)
    await update.message.reply_text(f"✅ Голосование создано! ID: {vote_id}\n"
                                     f"Предложение: {proposal}\n"
                                     f"Описание: {description}\n"
                                     f"Голосование активно 24 часа. /vote_cast {vote_id} for/against")

async def vote_cast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ /vote_cast <id> for/against")
        return
    try:
        vote_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return
    choice = context.args[1].lower()
    if choice not in ['for', 'against']:
        await update.message.reply_text("❌ Выбор: for или against.")
        return
    if vote(vote_id, user_id, choice):
        await update.message.reply_text(f"✅ Ваш голос учтён: {choice}.")
    else:
        await update.message.reply_text("❌ Не удалось проголосовать (голосование завершено или вы уже голосовали).")

async def season_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    month = datetime.now().month
    if 12 <= month <= 2:
        season = '❄️ Зима'
    elif 3 <= month <= 5:
        season = '🌸 Весна'
    elif 6 <= month <= 8:
        season = '☀️ Лето'
    else:
        season = '🍂 Осень'
    await update.message.reply_text(f"🧭 Текущий сезон: {season}")

async def currency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    user_id = update.effective_user.id
    country = get_user_country(user_id)
    if not country:
        await update.message.reply_text("Вы не выбрали страну.")
        return
    currency = get_country_currency(country)
    rate = get_currency_rate(currency)
    await update.message.reply_text(f"💱 Курс валюты {currency}: {rate:.2f} (относительно базовой)")

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Бот работает только в группах.")
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = cur.fetchall()
    conn.close()
    scores = []
    for (user_id,) in rows:
        power = get_country_power(user_id)
        country = get_user_country(user_id)
        if country:
            scores.append((country, power))
    scores.sort(key=lambda x: x[1], reverse=True)
    text = "🏆 **Топ-10 игроков по мощи**\n\n"
    for i, (country, power) in enumerate(scores[:10], 1):
        text += f"{i}. {country} — {power}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ============ ОБРАБОТЧИКИ CALLBACK ============
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("select_"):
        country = data[7:]
        set_user_country(user_id, country)
        await query.edit_message_text(f"✅ Вы выбрали страну {country}!")
        return

    if data.startswith("ally_accept_"):
        parts = data.split('_')
        if len(parts) != 4:
            await query.edit_message_text("❌ Ошибка формата.")
            return
        from_id = int(parts[2])
        to_id = int(parts[3])
        if user_id != to_id:
            await query.answer("Это предложение не для вас!", show_alert=True)
            return
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM allies WHERE user_id=? AND ally_id=? AND status='pending'", (to_id, from_id))
        if not cur.fetchone():
            await query.edit_message_text("❌ Запрос уже обработан.")
            conn.close()
            return
        conn.close()
        if len(get_allies(to_id, 'accepted')) >= 3:
            await query.edit_message_text(f"❌ У {get_user_country(to_id)} уже 3 союзника.")
            return
        if len(get_allies(from_id, 'accepted')) >= 3:
            await query.edit_message_text(f"❌ У {get_user_country(from_id)} уже 3 союзника.")
            return
        accept_ally(to_id, from_id)
        await query.edit_message_text("✅ Союз принят!")
        return

    if data.startswith("ally_reject_"):
        parts = data.split('_')
        if len(parts) != 4:
            await query.edit_message_text("❌ Ошибка формата.")
            return
        from_id = int(parts[2])
        to_id = int(parts[3])
        if user_id != to_id:
            await query.answer("Это предложение не для вас!", show_alert=True)
            return
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("DELETE FROM allies WHERE user_id=? AND ally_id=? AND status='pending'", (from_id, to_id))
        cur.execute("DELETE FROM allies WHERE user_id=? AND ally_id=? AND status='pending'", (to_id, from_id))
        conn.commit()
        conn.close()
        await query.edit_message_text("❌ Союз отклонён.")
        return

    if data.startswith("conquer_"):
        parts = data.split('_')
        if len(parts) != 4:
            await query.edit_message_text("❌ Ошибка формата.")
            return
        war_id = int(parts[1])
        winner_id = int(parts[2])
        loser_id = int(parts[3])
        if user_id != winner_id:
            await query.answer("Это не ваша победа!", show_alert=True)
            return
        loser_stats = get_user_stats(loser_id)
        if loser_stats:
            add_resources(winner_id, loser_stats['resources'])
            add_money(winner_id, loser_stats['money'])
        loser_country = get_user_country(loser_id)
        delete_user_country(loser_id)
        await query.edit_message_text(f"💀 {get_user_country(winner_id)} захватил {loser_country}!\n"
                                       f"Все ресурсы и деньги проигравшего перешли победителю.")
        chat_id = query.message.chat_id
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"💀 {get_user_country(winner_id)} захватил {loser_country}!"
        )
        return

    if data.startswith("puppet_"):
        parts = data.split('_')
        if len(parts) != 4:
            await query.edit_message_text("❌ Ошибка формата.")
            return
        war_id = int(parts[1])
        winner_id = int(parts[2])
        loser_id = int(parts[3])
        if user_id != winner_id:
            await query.answer("Это не ваша победа!", show_alert=True)
            return
        loser_country = get_user_country(loser_id)
        set_user_stats(loser_id, master_id=winner_id, is_puppet=1)
        await query.edit_message_text(f"🤝 {get_user_country(winner_id)} сделал {loser_country} марионеткой!\n"
                                       f"Марионетка не может воевать, торговать или заключать союзы.\n"
                                       f"Хозяин получает 10% от прироста ресурсов марионетки.")
        chat_id = query.message.chat_id
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🤝 {get_user_country(winner_id)} сделал {loser_country} марионеткой!"
        )
        return

    if data.startswith("break_napt_confirm_"):
        parts = data.split('_')
        if len(parts) != 4:
            await query.edit_message_text("❌ Ошибка формата.")
            return
        from_user = int(parts[3])
        to_user = int(parts[4])
        if user_id != from_user:
            await query.answer("Это не ваша операция!", show_alert=True)
            return
        if not has_napt(from_user, to_user):
            await query.edit_message_text("❌ Договор уже не действует.")
            return
        success, msg = break_napt_penalty(from_user)
        if success:
            cancel_napt(from_user, to_user)
            await query.edit_message_text(f"✅ Договор разорван.\n{msg}")
        else:
            await query.edit_message_text("❌ Ошибка при разрыве.")
        return

    if data.startswith("break_napt_cancel"):
        await query.edit_message_text("❌ Разрыв договора отменён.")
        return

    if data.startswith("research_"):
        tech = data[9:]
        if tech == "cancel":
            await query.edit_message_text("❌ Исследование отменено.")
            return
        result, msg = start_research(user_id, tech)
        await query.edit_message_text(f"🔬 {msg}")
        return

    if data.startswith("research_cancel"):
        await query.edit_message_text("❌ Исследование отменено.")
        return

    if data.startswith("spy_"):
        parts = data.split('_')
        if len(parts) < 3:
            await query.edit_message_text("❌ Ошибка.")
            return
        target_id = int(parts[1])
        action = parts[2]
        if action == "cancel":
            await query.edit_message_text("❌ Шпионаж отменён.")
            return
        result = spy_action(user_id, target_id, action)
        await query.edit_message_text(f"🕵️ {result['message']}")
        return

    await query.edit_message_text("✅ Действие выполнено.")

# ============ ПРИВЕТСТВИЕ В ГРУППЕ ============
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_chat_member = update.my_chat_member
    if new_chat_member.new_chat_member.user.id != context.bot.id:
        return
    if new_chat_member.new_chat_member.status in ['member', 'administrator']:
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="👋 Привет! Я бот для игры «Завоевание мира 1914».\nИспользуйте /help для списка команд."
        )
        try:
            await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=msg.message_id)
        except:
            pass

# ============ ЗАПУСК ============
def main():
    init_db()
    create_bots_if_needed()
    init_colonies()
    update_currency_rates()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("country", country_command))
    app.add_handler(CommandHandler("mystats", mystats_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("war", war_command))
    app.add_handler(CommandHandler("peace", peace_command))
    app.add_handler(CommandHandler("war_end", war_end_command))
    app.add_handler(CommandHandler("ally", ally_command))
    app.add_handler(CommandHandler("allies", allies_command))
    app.add_handler(CommandHandler("napt", napt_command))
    app.add_handler(CommandHandler("break_napt", break_napt_command))
    app.add_handler(CommandHandler("sanction", sanction_command))
    app.add_handler(CommandHandler("research", research_command))
    app.add_handler(CommandHandler("spy", spy_command))
    app.add_handler(CommandHandler("invest", invest_command))
    app.add_handler(CommandHandler("invest_population", invest_population_command))
    app.add_handler(CommandHandler("mobilize", mobilize_command))
    app.add_handler(CommandHandler("demobilize", demobilize_command))
    app.add_handler(CommandHandler("colonies", colonies_command))
    app.add_handler(CommandHandler("build_fleet", build_fleet_command))
    app.add_handler(CommandHandler("blockade", blockade_command))
    app.add_handler(CommandHandler("vote", vote_command))
    app.add_handler(CommandHandler("vote_cast", vote_cast_command))
    app.add_handler(CommandHandler("season", season_command))
    app.add_handler(CommandHandler("currency", currency_command))
    app.add_handler(CommandHandler("top", top_command))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(ChatMemberHandler(welcome, ChatMemberHandler.MY_CHAT_MEMBER))

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(bot_actions, interval=600, first=60)
        job_queue.run_repeating(lambda ctx: update_resistance(), interval=3600, first=300)
        job_queue.run_repeating(lambda ctx: update_currency_rates(), interval=3600, first=300)
        job_queue.run_repeating(lambda ctx: check_votes(), interval=3600, first=60)
        job_queue.run_repeating(lambda ctx: check_and_resolve_wars(), interval=60, first=10)
        job_queue.run_repeating(lambda ctx: check_research_queue(), interval=60, first=30)
        job_queue.run_repeating(lambda ctx: update_colonies(), interval=600, first=120)

    app.run_polling()

if __name__ == "__main__":
    main()
