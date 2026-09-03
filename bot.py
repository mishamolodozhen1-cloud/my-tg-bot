import logging
import sqlite3
import random
import json
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes,
    ChatMemberHandler
)

# ---------- ТОКЕН ----------
TOKEN = "8841865153:AAHxbALDI8EIdyk0DpRC0wshkvlS1w1Ds7w"

# ---------- ЛОГИРОВАНИЕ ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- БАЗА ДАННЫХ ----------
DB_FILE = "game.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # Таблица users с полным набором полей
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
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
        )
    """)
    # Добавляем недостающие столбцы
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]
    for col in ['fleet', 'inflation', 'fortifications', 'occupied_territory']:
        if col not in columns:
            if col == 'inflation':
                cur.execute("ALTER TABLE users ADD COLUMN inflation REAL DEFAULT 0.0")
            elif col == 'fleet':
                cur.execute("ALTER TABLE users ADD COLUMN fleet INTEGER DEFAULT 0")
            elif col == 'fortifications':
                cur.execute("ALTER TABLE users ADD COLUMN fortifications INTEGER DEFAULT 0")
            elif col == 'occupied_territory':
                cur.execute("ALTER TABLE users ADD COLUMN occupied_territory TEXT DEFAULT '[]'")

    # Остальные таблицы
    cur.execute("""
        CREATE TABLE IF NOT EXISTS technologies (
            user_id INTEGER,
            tech_name TEXT,
            level INTEGER DEFAULT 0,
            last_upgrade TIMESTAMP,
            PRIMARY KEY (user_id, tech_name)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS research_queue (
            user_id INTEGER,
            tech_name TEXT,
            start_time TIMESTAMP,
            finish_time TIMESTAMP,
            PRIMARY KEY (user_id, tech_name)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS spy_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user INTEGER,
            target_user INTEGER,
            action TEXT,
            date TIMESTAMP,
            success INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS events_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_type TEXT,
            description TEXT,
            date TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS treaties (
            user_id INTEGER,
            partner_id INTEGER,
            type TEXT,
            until TIMESTAMP,
            PRIMARY KEY (user_id, partner_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS colonies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            income INTEGER DEFAULT 10,
            loyalty INTEGER DEFAULT 50,
            invested INTEGER DEFAULT 0,
            last_update TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user INTEGER,
            to_user INTEGER,
            status TEXT,
            offered_type TEXT,
            offered_amount INTEGER,
            requested_type TEXT,
            requested_amount INTEGER,
            date TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS allies (
            user_id INTEGER,
            ally_id INTEGER,
            status TEXT,
            date TIMESTAMP,
            PRIMARY KEY (user_id, ally_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sanctions (
            from_user INTEGER,
            target_user INTEGER,
            date TIMESTAMP,
            PRIMARY KEY (from_user, target_user)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TIMESTAMP,
            status TEXT,
            winner_id INTEGER DEFAULT NULL,
            initiator_id INTEGER,
            target_id INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS war_participants (
            war_id INTEGER,
            user_id INTEGER,
            side TEXT,
            joined_at TIMESTAMP,
            PRIMARY KEY (war_id, user_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS peace_requests (
            war_id INTEGER,
            from_user INTEGER,
            to_user INTEGER,
            status TEXT,
            date TIMESTAMP,
            PRIMARY KEY (war_id, from_user, to_user)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS currency_rates (
            currency TEXT PRIMARY KEY,
            rate REAL DEFAULT 1.0,
            last_update TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposer_id INTEGER,
            proposal TEXT,
            description TEXT,
            status TEXT,
            until TIMESTAMP,
            votes_for INTEGER DEFAULT 0,
            votes_against INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vote_records (
            vote_id INTEGER,
            user_id INTEGER,
            choice TEXT,
            PRIMARY KEY (vote_id, user_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS occupations (
            occupier_id INTEGER,
            occupied_country TEXT,
            since TIMESTAMP,
            resistance INTEGER DEFAULT 0,
            PRIMARY KEY (occupier_id, occupied_country)
        )
    """)
    conn.commit()
    conn.close()

# ---------- ДАННЫЕ СТРАН ----------
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

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def get_country_currency(country: str) -> str:
    return COUNTRIES_DATA.get(country, {}).get("currency", "ден. ед.")

def get_country_power_by_name(country: str) -> int:
    uid = get_user_id_by_country(country)
    if uid:
        return get_country_power(uid)
    return 0

# ---------- ОСНОВНЫЕ ФУНКЦИИ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ ----------
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
    cur.execute("""
        REPLACE INTO users (user_id, country, resources, money, population, military, economy, fleet, inflation,
                            last_update, master_id, is_puppet, neutral, mobilized, base_military, is_bot, fortifications)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, country, data.get('initial_resources', 1000), 10000,
          data.get('population', 10000000), data.get('army', 100000),
          data.get('initial_economy', 500), 0, 0.0,
          datetime.now().isoformat(), None, 0, 0, 0, data.get('army', 100000), 0, 0))
    conn.commit()
    conn.close()

def delete_user_country(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    # Удаляем все связи
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
    cur.commit()
    conn.close()

def get_all_users_countries():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT country, user_id, is_puppet, is_bot FROM users")
    rows = cur.fetchall()
    conn.close()
    return {row[0]: {'user_id': row[1], 'is_puppet': row[2], 'is_bot': row[3]} for row in rows}

def is_country_occupied(country: str):
    return country in get_all_users_countries()

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
    if get_resources(user_id) < amount:
        return False
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
    if get_money(user_id) < amount:
        return False
    set_money(user_id, get_money(user_id) - amount)
    return True

def get_user_stats(user_id: int):
    update_user_stats(user_id)  # определена ниже
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        SELECT country, resources, money, population, military, economy, fleet, inflation,
               master_id, is_puppet, neutral, mobilized, base_military, fortifications
        FROM users WHERE user_id=?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            'country': row[0],
            'resources': row[1],
            'money': row[2],
            'population': row[3],
            'military': row[4],
            'economy': row[5],
            'fleet': row[6],
            'inflation': row[7],
            'master_id': row[8],
            'is_puppet': row[9],
            'neutral': row[10],
            'mobilized': row[11],
            'base_military': row[12],
            'fortifications': row[13]
        }
    return None

def set_user_stats(user_id: int, **kwargs):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    updates = []
    params = []
    for key, value in kwargs.items():
        if key in ['resources', 'money', 'population', 'military', 'economy', 'fleet', 'inflation',
                   'master_id', 'is_puppet', 'neutral', 'mobilized', 'base_military', 'fortifications']:
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

# ---------- ТЕХНОЛОГИИ ----------
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

# ---------- ШПИОНАЖ ----------
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

# ---------- СОЮЗЫ ----------
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

# ---------- САНКЦИИ ----------
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

# ---------- ДОГОВОРЫ (NAPT) ----------
def create_napt(user_id: int, partner_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM treaties WHERE user_id=? AND partner_id=? AND type='napt' AND until > ?",
                (user_id, partner_id, datetime.now().isoformat()))
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
    cur.execute("SELECT 1 FROM treaties WHERE user_id=? AND partner_id=? AND type='napt' AND until > ?",
                (user_id, other_id, datetime.now().isoformat()))
    row = cur.fetchone()
    conn.close()
    return row is not None

def cancel_napt(user_id: int, partner_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM treaties WHERE user_id=? AND partner_id=? AND type='napt'", (user_id, partner_id))
    cur.execute("DELETE FROM treaties WHERE user_id=? AND partner_id=? AND type='napt'", (partner_id, user_id))
    conn.commit()
    conn.close()

# ---------- МОБИЛИЗАЦИЯ ----------
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
    cur.execute("""
        UPDATE users SET military=?, economy=?, population=?, mobilized=1, mobilized_until=?
        WHERE user_id=?
    """, (new_mil, eco_new, pop_new, until.isoformat(), user_id))
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
    cur.execute("""
        UPDATE users SET military=?, economy=?, population=?, mobilized=0, mobilized_until=NULL
        WHERE user_id=?
    """, (base_mil, eco_new, pop_new, user_id))
    conn.commit()
    conn.close()
    return True, "Демобилизация проведена. Армия возвращена к базе."

# ---------- КОЛОНИИ ----------
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

# ---------- ВОЙНА ----------
def create_war(initiator_id: int, target_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute("""
        INSERT INTO wars (start_time, status, initiator_id, target_id)
        VALUES (?, ?, ?, ?)
    """, (now, 'active', initiator_id, target_id))
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
    cur.execute("""
        SELECT w.id FROM wars w
        JOIN war_participants wp ON w.id = wp.war_id
        WHERE wp.user_id = ? AND w.status = 'active'
    """, (user_id,))
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

    # Потери проигравших
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

    # Бонус победителям
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

# ---------- ТОРГОВЛЯ ----------
TRADE_SELECT_PARTNER, TRADE_SELECT_OFFER_TYPE, TRADE_OFFER_AMOUNT, TRADE_SELECT_REQUEST_TYPE, TRADE_REQUEST_AMOUNT = range(5)

def create_trade(from_user, to_user, offered_type, offered_amount, requested_type, requested_amount):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trades (from_user, to_user, status, offered_type, offered_amount, requested_type, requested_amount, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (from_user, to_user, 'pending', offered_type, offered_amount, requested_type, requested_amount, datetime.now().isoformat()))
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

# ---------- НОВЫЕ ФУНКЦИИ (ИДЕИ 3,6,7,8,9,10,17,18,19) ----------
# 3. Инфляция и кризис
def economic_crisis(user_id: int):
    stats = get_user_stats(user_id)
    if stats:
        new_eco = int(stats['economy'] * 0.8)
        new_money = int(stats['money'] * 0.9)
        increase_inflation(user_id, 0.05)
        set_user_stats(user_id, economy=new_eco, money=new_money)
        return True
    return False

# 6. Логистика
def get_logistics_cost(attacker_id: int, defender_id: int) -> int:
    dist = abs(attacker_id - defender_id) % 100
    return dist * 2

# 7. Укрепления
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

# 8. Оккупация и сопротивление
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

# 9. Валюты
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

# 17. Диверсии (саботаж)
def sabotage(user_id: int, target_id: int, target_type: str) -> dict:
    if get_money(user_id) < 1000:
        return {'success': False, 'message': 'Недостаточно денег (1000).'}
    deduct_money(user_id, 1000)
    avia_level = get_tech_level(user_id, 'aviation')
    chance = 0.4 + avia_level * 0.06
    if random.random() < chance:
        if target_type == 'resources':
            amount = int(get_resources(target_id) * 0.15)
            deduct_resources(target_id, amount)
            return {'success': True, 'message': f"Диверсия удалась! Уничтожено {amount} ресурсов."}
        elif target_type == 'economy':
            stats = get_user_stats(target_id)
            if stats:
                new_eco = int(stats['economy'] * 0.85)
                set_user_stats(target_id, economy=new_eco)
                return {'success': True, 'message': "Диверсия удалась! Экономика снижена на 15%."}
        elif target_type == 'fleet':
            stats = get_user_stats(target_id)
            if stats and stats['fleet'] > 0:
                new_fleet = int(stats['fleet'] * 0.7)
                set_user_stats(target_id, fleet=new_fleet)
                return {'success': True, 'message': f"Диверсия удалась! Флот уменьшен до {new_fleet}."}
    return {'success': False, 'message': 'Диверсия провалилась.'}

# 18. Флот и блокада
def build_fleet(user_id: int, amount: int):
    cost = amount * 50
    if get_resources(user_id) < cost:
        return False, "Недостаточно ресурсов."
    deduct_resources(user_id, cost)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET fleet = fleet + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()
    return True, f"Построено {amount} кораблей."

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

# 19. Голосования
def create_vote(proposer_id: int, proposal: str, description: str, duration_hours: int = 24):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    until = datetime.now() + timedelta(hours=duration_hours)
    cur.execute("""
        INSERT INTO votes (proposer_id, proposal, description, status, until)
        VALUES (?, ?, ?, ?, ?)
    """, (proposer_id, proposal, description, 'active', until.isoformat()))
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

# ---------- БОТЫ-ИГРОКИ ----------
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
            cur.execute("""
                INSERT INTO users (user_id, country, resources, money, population, military, economy, fleet, inflation,
                                   last_update, master_id, is_puppet, neutral, mobilized, base_military, is_bot, fortifications)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (bot_id, country, data.get('initial_resources', 1000), 10000,
                  data.get('population', 10000000), data.get('army', 100000),
                  data.get('initial_economy', 500), 0, 0.0,
                  datetime.now().isoformat(), None, 0, 0, 0, data.get('army', 100000), 1, 0))
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

# ---------- ОБРАБОТЧИКИ КОМАНД ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    check_and_resolve_wars()
    check_research_queue()
    check_votes()
    await update.message.reply_text(
        "Добро пожаловать в ролевую игру «Завоевание мира 1914»!\n"
        "/country — выбрать страну\n"
        "/mystats — ваша статистика\n"
        "/info <страна> — информация о стране\n"
        "/war <страна> — объявить войну (10 мин)\n"
        "/research — технологии\n"
        "/spy <страна> — шпионаж\n"
        "/top — рейтинг\n"
        "/napt <страна> — договор о ненападении\n"
        "/neutral — нейтралитет\n"
        "/mobilize — мобилизация\n"
        "/colonies — колонии\n"
        "/fortify <число> — построить укрепления\n"
        "/build_fleet <число> — построить флот\n"
        "/blockade <страна> — морская блокада\n"
        "/sabotage <страна> <ресурсы|экономика|флот> — диверсия\n"
        "/vote <предложение> <описание> — создать голосование\n"
        "/vote_cast <id> for/against — проголосовать\n"
        "/season — текущий сезон\n"
        "/currency — курс валюты\n"
        "/crisis — экономическая ситуация\n"
        "/help — помощь"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Список команд:\n"
        "/country — выбор страны\n"
        "/mystats — статистика\n"
        "/info <страна> — информация\n"
        "/war <страна> — война\n"
        "/research — технологии\n"
        "/spy <страна> — шпионаж\n"
        "/top — рейтинг\n"
        "/napt <страна> — договор ненападения\n"
        "/neutral — нейтралитет\n"
        "/mobilize — мобилизация\n"
        "/demobilize — демобилизация\n"
        "/colonies — колонии\n"
        "/invest_colony <название> <сумма> — инвестиция в колонию\n"
        "/fortify <число> — укрепления\n"
        "/build_fleet <число> — флот\n"
        "/blockade <страна> — блокада\n"
        "/sabotage <страна> <ресурсы|экономика|флот> — диверсия\n"
        "/vote <предложение> <описание> — голосование\n"
        "/vote_cast <id> for/against — голос\n"
        "/season — сезон\n"
        "/currency — курс валюты\n"
        "/crisis — экономика\n"
        "/bots — страны-боты\n"
        "/reset — сбросить страну"
    )

async def country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users_countries()
    keyboard = []
    for i in range(0, len(COUNTRIES_LIST), 2):
        row = []
        for c in COUNTRIES_LIST[i:i+2]:
            if c in users:
                if users[c]['is_puppet']:
                    label = c + " 🟠"
                else:
                    if users[c]['is_bot']:
                        label = c + " 🤖"
                    else:
                        label = c + " 🔴"
            else:
                label = c + " 🟢"
            row.append(InlineKeyboardButton(label, callback_data=c))
        keyboard.append(row)
    await update.message.reply_text("👇 Выберите страну:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    country_name = query.data
    users = get_all_users_countries()
    if country_name in users:
        uid = users[country_name]['user_id']
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT is_bot FROM users WHERE user_id=?", (uid,))
        row = cur.fetchone()
        conn.close()
        if row and row[0] == 1:
            # Занимаем страну бота
            delete_user_country(uid)
            set_user_country(user_id, country_name)
            await query.edit_message_text(f"✅ Вы заняли страну {country_name} (освобождена от бота).")
            return
        else:
            if users[country_name]['is_puppet']:
                await query.edit_message_text("❌ Это марионетка.")
            else:
                await query.edit_message_text("❌ Уже занята.")
            return
    else:
        set_user_country(user_id, country_name)
        await query.edit_message_text(f"✅ Вы выбрали {country_name}.")

async def mystatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    country = get_user_country(user_id)
    if country:
        await update.message.reply_text(f"🇺🇳 Ваша страна: **{country}**", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Вы не выбрали страну.")

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    stats = get_user_stats(user_id)
    if not stats:
        await update.message.reply_text("❌ Вы не выбрали страну.")
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
    if not context.args:
        user_id = update.message.from_user.id
        country = get_user_country(user_id)
        if country:
            await update.message.reply_text(format_country_info(country), parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Укажите страну.")
        return
    query = " ".join(context.args).strip()
    found = None
    for c in COUNTRIES_LIST:
        if c.lower() == query.lower():
            found = c
            break
    if not found:
        for c in COUNTRIES_LIST:
            if query.lower() in c.lower():
                found = c
                break
    if found:
        await update.message.reply_text(format_country_info(found), parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Страна не найдена.")

def format_country_info(country: str) -> str:
    data = COUNTRIES_DATA.get(country)
    if not data:
        return f"Данные о стране «{country}» отсутствуют."
    return (
        f"🏛️ *{country}*\n"
        f"├ Столица: {data['capital']}\n"
        f"├ Население: {data['population']:,}\n"
        f"├ Армия: {data['army']:,}\n"
        f"├ Ресурсы: {data['initial_resources']}\n"
        f"├ Экономика: {data['initial_economy']}\n"
        f"├ Валюта: {data['currency']}\n"
        f"└ Мощность: {get_country_power_by_name(country):,}"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    delete_user_country(user_id)
    await update.message.reply_text("🔄 Выбор сброшен.")

# ---------- ВОЙНА (ОБРАБОТЧИКИ) ----------
async def war_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может воевать.")
        return
    if get_active_war_for_user(user_id):
        await update.message.reply_text("❌ Вы уже воюете.")
        return
    stats = get_user_stats(user_id)
    if stats['neutral']:
        await update.message.reply_text("❌ Нейтральная страна не может воевать.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /war <страна>")
        return
    target = " ".join(context.args).strip()
    target_id = get_user_id_by_country(target)
    if not target_id:
        await update.message.reply_text("❌ Страна не найдена.")
        return
    if target_id == user_id:
        await update.message.reply_text("❌ Нельзя воевать с собой.")
        return
    if has_napt(user_id, target_id):
        await update.message.reply_text("❌ Действует договор о ненападении.")
        return
    if is_puppet(target_id):
        master = get_master(target_id)
        master_country = get_user_country(master) if master else None
        await update.message.reply_text(f"❌ {target} — марионетка {master_country}. Воевать с хозяином.")
        return
    if is_ally(user_id, target_id):
        await update.message.reply_text("❌ Нельзя нападать на союзника.")
        return
    t_stats = get_user_stats(target_id)
    if t_stats and t_stats['neutral']:
        await update.message.reply_text(f"❌ {target} — нейтральная страна.")
        return
    # Проверка, не воюют ли уже
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM wars w
        JOIN war_participants wp1 ON w.id = wp1.war_id
        JOIN war_participants wp2 ON w.id = wp2.war_id
        WHERE w.status='active' AND wp1.user_id=? AND wp2.user_id=?
    """, (user_id, target_id))
    if cur.fetchone():
        conn.close()
        await update.message.reply_text("❌ Эти страны уже воюют.")
        return
    conn.close()

    war_id = create_war(user_id, target_id)
    chat_id = update.message.chat_id
    keyboard = [
        [InlineKeyboardButton("🕊️ Мир", callback_data=f"peace_{war_id}")],
        [InlineKeyboardButton("⚔️ Завершить войну", callback_data=f"end_war_{war_id}")],
        [InlineKeyboardButton("⚔️ Вступить (союзникам)", callback_data=f"join_war_{war_id}")]
    ]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⚔️ **Война: {get_user_country(user_id)} vs {target}**\n(10 мин)",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    # Оповещаем союзников
    for ally_id in get_allies(user_id, 'accepted'):
        ally_country = get_user_country(ally_id)
        if ally_country and ally_id != user_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔔 {ally_country}, ваш союзник воюет. Вступите?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚔️ Вступить", callback_data=f"join_war_{war_id}_{get_user_country(user_id)}")]
                ])
            )
    for ally_id in get_allies(target_id, 'accepted'):
        ally_country = get_user_country(ally_id)
        if ally_country and ally_id != target_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔔 {ally_country}, ваш союзник атакован. Вступите?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚔️ Вступить", callback_data=f"join_war_{war_id}_{target}")]
                ])
            )

async def join_war_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split('_')
    if len(parts) < 3:
        await query.edit_message_text("❌ Ошибка.")
        return
    war_id = int(parts[2])
    side_country = parts[3] if len(parts) > 3 else None
    user_id = query.from_user.id
    if is_puppet(user_id):
        await query.answer("Марионетка не может.", show_alert=True)
        return
    if get_active_war_for_user(user_id):
        await query.answer("Вы уже воюете.", show_alert=True)
        return
    if not side_country:
        await query.edit_message_text("Выберите сторону:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("За нападающего", callback_data=f"join_war_{war_id}_attacker")],
            [InlineKeyboardButton("За защитника", callback_data=f"join_war_{war_id}_defender")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_join_{war_id}")]
        ]))
        return
    attackers, defenders = get_war_participants(war_id)
    if side_country == 'attacker' or side_country == attackers[0] and get_user_country(user_id):
        if not any(is_ally(user_id, a) for a in attackers) and user_id not in attackers:
            await query.answer("Вы не союзник атакующих.", show_alert=True)
            return
        add_participant(war_id, user_id, 'attacker')
        await query.edit_message_text("✅ Вы вступили на стороне атакующих.")
    else:
        if not any(is_ally(user_id, d) for d in defenders) and user_id not in defenders:
            await query.answer("Вы не союзник защитников.", show_alert=True)
            return
        add_participant(war_id, user_id, 'defender')
        await query.edit_message_text("✅ Вы вступили на стороне защитников.")

async def end_war_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split('_')
    if len(parts) != 3:
        await query.edit_message_text("❌ Ошибка.")
        return
    war_id = int(parts[2])
    user_id = query.from_user.id
    info = get_war_info(war_id)
    if not info or info['status'] != 'active':
        await query.edit_message_text("❌ Война уже завершена.")
        return
    if info['initiator_id'] != user_id:
        await query.answer("Только инициатор может завершить!", show_alert=True)
        return
    result = resolve_war(war_id)
    if not result:
        await query.edit_message_text("❌ Ошибка.")
        return
    chat_id = query.message.chat_id
    winner_str = ", ".join(result['winner_countries'])
    loser_str = ", ".join(result['loser_countries'])
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⚔️ **Война завершена!**\n🏆 Победители: {winner_str}\n📉 Проигравшие: {loser_str}",
        parse_mode="Markdown"
    )
    await query.edit_message_text("✅ Война завершена.")

async def peace_proposal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split('_')
    if len(parts) != 2:
        await query.edit_message_text("❌ Ошибка.")
        return
    war_id = int(parts[1])
    user_id = query.from_user.id
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM war_participants WHERE war_id=? AND user_id=?", (war_id, user_id))
    if not cur.fetchone():
        await query.answer("Вы не участник.", show_alert=True)
        conn.close()
        return
    conn.close()
    attackers, defenders = get_war_participants(war_id)
    if user_id in attackers:
        targets = defenders
    else:
        targets = attackers
    if not targets:
        await query.edit_message_text("Нет противников.")
        return
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    for target in targets:
        cur.execute("INSERT OR REPLACE INTO peace_requests (war_id, from_user, to_user, status, date) VALUES (?, ?, ?, ?, ?)",
                    (war_id, user_id, target, 'pending', now))
    conn.commit()
    conn.close()
    chat_id = query.message.chat_id
    for target in targets:
        target_country = get_user_country(target)
        if target_country:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🕊️ {get_user_country(user_id)} предлагает мир.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Принять", callback_data=f"accept_peace_{war_id}_{user_id}_{target}")],
                    [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_peace_{war_id}_{user_id}_{target}")]
                ])
            )
    await query.edit_message_text("✅ Мир предложен.")

async def peace_response_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split('_')
    if len(parts) != 4:
        await query.edit_message_text("❌ Ошибка.")
        return
    action, war_id, from_id, to_id = parts[0], int(parts[1]), int(parts[2]), int(parts[3])
    if query.from_user.id != to_id:
        await query.answer("Не для вас.", show_alert=True)
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT status FROM peace_requests WHERE war_id=? AND from_user=? AND to_user=?", (war_id, from_id, to_id))
    row = cur.fetchone()
    if not row or row[0] != 'pending':
        await query.edit_message_text("❌ Запрос уже обработан.")
        conn.close()
        return
    if action == 'accept_peace':
        cur.execute("UPDATE peace_requests SET status='accepted' WHERE war_id=? AND from_user=? AND to_user=?", (war_id, from_id, to_id))
        finish_war(war_id, winner_id=None)
        conn.commit()
        conn.close()
        await query.edit_message_text("🕊️ Мир заключён!")
        await context.bot.send_message(chat_id=query.message.chat_id, text="🕊️ Война окончена мирным договором.")
    else:
        cur.execute("UPDATE peace_requests SET status='rejected' WHERE war_id=? AND from_user=? AND to_user=?", (war_id, from_id, to_id))
        conn.commit()
        conn.close()
        await query.edit_message_text("❌ Мир отклонён.")

# ---------- ОБРАБОТЧИКИ НОВЫХ КОМАНД ----------
async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id) or is_puppet(user_id):
        await update.message.reply_text("❌ Недоступно.")
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
            status += " (в процессе)"
        elif level < 5:
            cost = TECH_PRICES[level] * 2
            status += f" (стоимость {cost} ресурсов)"
        else:
            status += " (макс)"
        keyboard.append([InlineKeyboardButton(f"{TECH_NAMES[tech]} — {status}", callback_data=f"research_{tech}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="research_cancel")])
    await update.message.reply_text("🔬 Выберите технологию:", reply_markup=InlineKeyboardMarkup(keyboard))

async def research_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "research_cancel":
        await query.edit_message_text("Отменено.")
        return
    tech = data.split('_')[1]
    user_id = query.from_user.id
    result, msg = start_research(user_id, tech)
    await query.edit_message_text(f"🔬 {msg}")

async def spy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id) or is_puppet(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /spy <страна>")
        return
    target = " ".join(context.args).strip()
    target_id = get_user_id_by_country(target)
    if not target_id or target_id == user_id:
        await update.message.reply_text("❌ Некорректная цель.")
        return
    keyboard = [
        [InlineKeyboardButton("🔍 Разведка", callback_data=f"spy_{target_id}_разведка")],
        [InlineKeyboardButton("💥 Саботаж", callback_data=f"spy_{target_id}_саботаж")],
        [InlineKeyboardButton("❌ Отмена", callback_data="spy_cancel")]
    ]
    context.user_data['spy_target'] = target_id
    await update.message.reply_text(f"🕵️ Действия против {target}:", reply_markup=InlineKeyboardMarkup(keyboard))

async def spy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "spy_cancel":
        await query.edit_message_text("Отменено.")
        return
    parts = data.split('_')
    target_id = int(parts[1])
    action = parts[2]
    user_id = query.from_user.id
    result = spy_action(user_id, target_id, action)
    await query.edit_message_text(f"🕵️ {result['message']}")

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    text = "🏆 **Топ-10**\n\n"
    for i, (country, power) in enumerate(scores[:10], 1):
        text += f"{i}. {country} — {power}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def napt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id) or is_puppet(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /napt <страна>")
        return
    target = " ".join(context.args).strip()
    target_id = get_user_id_by_country(target)
    if not target_id or target_id == user_id or is_ally(user_id, target_id):
        await update.message.reply_text("❌ Некорректная цель.")
        return
    success, msg = create_napt(user_id, target_id)
    await update.message.reply_text(msg)

async def neutral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id) or is_puppet(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return
    if get_active_war_for_user(user_id):
        await update.message.reply_text("❌ Во время войны нельзя.")
        return
    stats = get_user_stats(user_id)
    if stats['neutral']:
        await update.message.reply_text("❌ Уже нейтральны.")
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET neutral=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Нейтралитет объявлен.")

async def mobilize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id) or is_puppet(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return
    success, msg = mobilize(user_id)
    await update.message.reply_text(msg)

async def demobilize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id) or is_puppet(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return
    success, msg = demobilize(user_id)
    await update.message.reply_text(msg)

async def colonies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id):
        await update.message.reply_text("❌ Выберите страну.")
        return
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

async def invest_colony_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id):
        await update.message.reply_text("❌ Выберите страну.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ /invest_colony <название> <сумма>")
        return
    colony_name = context.args[0]
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Сумма должна быть числом.")
        return
    if amount <= 0:
        await update.message.reply_text("❌ Сумма >0.")
        return
    success, msg = invest_colony(user_id, colony_name, amount)
    await update.message.reply_text(msg)

async def fortify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id) or is_puppet(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ /fortify <число>")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Введите число.")
        return
    if amount <= 0:
        await update.message.reply_text("❌ >0.")
        return
    success, msg = build_fortifications(user_id, amount)
    await update.message.reply_text(msg)

async def blockade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id) or is_puppet(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /blockade <страна>")
        return
    target = " ".join(context.args).strip()
    target_id = get_user_id_by_country(target)
    if not target_id or target_id == user_id:
        await update.message.reply_text("❌ Некорректная цель.")
        return
    success, msg = blockade(user_id, target_id)
    await update.message.reply_text(msg)

async def build_fleet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id) or is_puppet(user_id):
        await update.message.reply_text("❌ Недоступно.")
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
        await update.message.reply_text("❌ >0.")
        return
    success, msg = build_fleet(user_id, amount)
    await update.message.reply_text(msg)

async def vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id):
        await update.message.reply_text("❌ Выберите страну.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ /vote <предложение> <описание>")
        return
    proposal = context.args[0]
    description = " ".join(context.args[1:])
    vote_id = create_vote(user_id, proposal, description)
    await update.message.reply_text(f"✅ Голосование создано (ID {vote_id})! /vote_cast {vote_id} for/against")

async def vote_cast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id):
        await update.message.reply_text("❌ Выберите страну.")
        return
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
        await update.message.reply_text("❌ Не удалось проголосовать.")

async def season_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    month = datetime.now().month
    if 12 <= month <= 2:
        season = '❄️ Зима'
    elif 3 <= month <= 5:
        season = '🌸 Весна'
    elif 6 <= month <= 8:
        season = '☀️ Лето'
    else:
        season = '🍂 Осень'
    await update.message.reply_text(f"Текущий сезон: {season}")

async def currency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    country = get_user_country(user_id)
    if not country:
        await update.message.reply_text("❌ Выберите страну.")
        return
    currency = get_country_currency(country)
    rate = get_currency_rate(currency)
    await update.message.reply_text(f"Курс {currency}: {rate:.2f}")

async def crisis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    stats = get_user_stats(user_id)
    if not stats:
        await update.message.reply_text("❌ Выберите страну.")
        return
    inf = get_inflation(user_id)
    await update.message.reply_text(
        f"📉 Инфляция: {inf*100:.1f}%\n"
        f"Экономика: {stats['economy']}\n"
        f"Деньги: {stats['money']}\n"
        f"{'⚠️ Кризис близок!' if inf > 0.2 else '✅ Стабильно.'}"
    )

async def sabotage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id) or is_puppet(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ /sabotage <страна> <ресурсы|экономика|флот>")
        return
    target = context.args[0]
    target_id = get_user_id_by_country(target)
    if not target_id:
        await update.message.reply_text("❌ Страна не найдена.")
        return
    target_type = context.args[1].lower()
    if target_type not in ['ресурсы', 'экономика', 'флот']:
        await update.message.reply_text("❌ Цель: ресурсы, экономика или флот.")
        return
    result = sabotage(user_id, target_id, target_type)
    await update.message.reply_text(f"💥 {result['message']}")

async def logistics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id):
        await update.message.reply_text("❌ Выберите страну.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /logistics <страна>")
        return
    target = " ".join(context.args).strip()
    target_id = get_user_id_by_country(target)
    if not target_id:
        await update.message.reply_text("❌ Страна не найдена.")
        return
    cost = get_logistics_cost(user_id, target_id)
    await update.message.reply_text(f"Дополнительные ресурсы для войны с {target}: {cost}")

async def bots_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_ids = get_bot_ids()
    if not bot_ids:
        await update.message.reply_text("Нет ботов.")
        return
    countries = [get_user_country(uid) for uid in bot_ids if get_user_country(uid)]
    text = "🤖 Страны-боты:\n" + "\n".join(f"- {c}" for c in countries)
    await update.message.reply_text(text)

# ---------- ОСНОВНЫЕ КОМАНДЫ (СОЮЗЫ, САНКЦИИ) ----------
async def ally_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_puppet(user_id) or not get_user_country(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /ally <страна>")
        return
    target = " ".join(context.args).strip()
    target_id = get_user_id_by_country(target)
    if not target_id or target_id == user_id or is_puppet(target_id) or is_ally(user_id, target_id):
        await update.message.reply_text("❌ Некорректная цель.")
        return
    if len(get_allies(user_id, 'accepted')) >= 3:
        await update.message.reply_text("❌ У вас уже 3 союзника.")
        return
    create_ally_request(user_id, target_id)
    chat_id = update.message.chat_id
    keyboard = [
        [InlineKeyboardButton("✅ Принять", callback_data=f"accept_ally_{user_id}_{target_id}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_ally_{user_id}_{target_id}")]
    ]
    await context.bot.send_message(chat_id=chat_id, text=f"🤝 {get_user_country(user_id)} предлагает союз {target}.", reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("✅ Запрос отправлен.")

async def ally_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split('_')
    if len(parts) != 4:
        await query.edit_message_text("❌ Ошибка.")
        return
    action, from_id, to_id = parts[1], int(parts[2]), int(parts[3])
    if query.from_user.id != to_id:
        await query.answer("Не для вас.", show_alert=True)
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM allies WHERE user_id=? AND ally_id=? AND status='pending'", (to_id, from_id))
    if not cur.fetchone():
        await query.edit_message_text("❌ Запрос уже обработан.")
        conn.close()
        return
    conn.close()
    if action == "accept":
        if len(get_allies(to_id, 'accepted')) >= 3 or len(get_allies(from_id, 'accepted')) >= 3:
            await query.edit_message_text("❌ Лимит союзников.")
            return
        accept_ally(to_id, from_id)
        await query.edit_message_text("✅ Союз принят!")
    else:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("DELETE FROM allies WHERE user_id=? AND ally_id=? AND status='pending'", (from_id, to_id))
        cur.execute("DELETE FROM allies WHERE user_id=? AND ally_id=? AND status='pending'", (to_id, from_id))
        conn.commit()
        conn.close()
        await query.edit_message_text("❌ Союз отклонён.")

async def break_ally_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_puppet(user_id) or not get_user_country(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /break_ally <страна>")
        return
    target = " ".join(context.args).strip()
    target_id = get_user_id_by_country(target)
    if not target_id:
        await update.message.reply_text("❌ Страна не найдена.")
        return
    if not is_ally(user_id, target_id):
        await update.message.reply_text("❌ Вы не союзники.")
        return
    break_ally(user_id, target_id)
    await update.message.reply_text(f"✅ Союз с {target} разорван.")

async def allies_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    allies = get_ally_countries(user_id)
    if not allies:
        await update.message.reply_text("❌ Нет союзников.")
        return
    await update.message.reply_text("🤝 Союзники:\n" + "\n".join(f"- {c}" for c in allies))

async def sanction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_puppet(user_id) or not get_user_country(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /sanction <страна>")
        return
    target = " ".join(context.args).strip()
    target_id = get_user_id_by_country(target)
    if not target_id or target_id == user_id or is_ally(user_id, target_id) or is_puppet(target_id):
        await update.message.reply_text("❌ Некорректная цель.")
        return
    if has_sanction(user_id, target_id):
        await update.message.reply_text("❌ Санкции уже действуют.")
        return
    create_sanction(user_id, target_id)
    await update.message.reply_text(f"🚫 Санкции против {target} введены на 24 часа.")

async def remove_sanctions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not context.args:
        await update.message.reply_text("⚠️ /remove_sanctions <страна>")
        return
    target = " ".join(context.args).strip()
    target_id = get_user_id_by_country(target)
    if not target_id:
        await update.message.reply_text("❌ Страна не найдена.")
        return
    if not has_sanction(user_id, target_id):
        await update.message.reply_text("❌ Нет санкций.")
        return
    remove_sanction(user_id, target_id)
    await update.message.reply_text(f"✅ Санкции с {target} сняты.")

async def sanctions_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    countries = get_sanctioned_countries(user_id)
    if not countries:
        await update.message.reply_text("❌ Нет санкций.")
        return
    await update.message.reply_text("🚫 Санкции:\n" + "\n".join(f"- {c}" for c in countries))

# ---------- МАРИОНЕТКИ ----------
async def puppets_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    puppets = get_puppets(user_id)
    if not puppets:
        await update.message.reply_text("❌ Нет марионеток.")
        return
    await update.message.reply_text("👑 Марионетки:\n" + "\n".join(f"- {c}" for c in puppets))

async def free_puppet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not context.args:
        await update.message.reply_text("⚠️ /free_puppet <страна>")
        return
    target = " ".join(context.args).strip()
    target_id = get_user_id_by_country(target)
    if not target_id:
        await update.message.reply_text("❌ Страна не найдена.")
        return
    if get_master(target_id) != user_id:
        await update.message.reply_text("❌ Это не ваша марионетка.")
        return
    set_user_stats(target_id, master_id=None, is_puppet=0)
    await update.message.reply_text(f"✅ {target} освобождена.")

# ---------- ИНВЕСТИЦИИ ----------
async def invest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id) or is_puppet(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return
    stats = get_user_stats(user_id)
    currency = get_country_currency(stats['country'])
    keyboard = [
        [InlineKeyboardButton("⚔️ Армия", callback_data="inv_army")],
        [InlineKeyboardButton("🏭 Экономика", callback_data="inv_economy")],
        [InlineKeyboardButton("❌ Отмена", callback_data="inv_cancel")]
    ]
    await update.message.reply_text(f"💰 У вас {stats['money']} {currency}\nКуда вложить?", reply_markup=InlineKeyboardMarkup(keyboard))

async def invest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if is_puppet(user_id):
        await query.edit_message_text("❌ Марионетка не может.")
        return
    if data == "inv_cancel":
        await query.edit_message_text("❌ Отмена.")
        context.user_data.pop('invest_action', None)
        context.user_data.pop('invest_type', None)
        return
    if data in ("inv_army", "inv_economy"):
        invest_type = "army" if data == "inv_army" else "economy"
        context.user_data['invest_type'] = invest_type
        context.user_data['invest_action'] = 'choose_amount'
        keyboard = [
            [InlineKeyboardButton("100", callback_data="inv_amt_100")],
            [InlineKeyboardButton("500", callback_data="inv_amt_500")],
            [InlineKeyboardButton("1000", callback_data="inv_amt_1000")],
            [InlineKeyboardButton("5000", callback_data="inv_amt_5000")],
            [InlineKeyboardButton("Свой вариант", callback_data="inv_amt_custom")],
            [InlineKeyboardButton("❌ Отмена", callback_data="inv_cancel")]
        ]
        await query.edit_message_text(f"Сумма для {'армии' if invest_type=='army' else 'экономики'}:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if data.startswith("inv_amt_"):
        amount_str = data.split('_')[2]
        if amount_str == "custom":
            await query.edit_message_text("Введите сумму в чат:")
            context.user_data['invest_action'] = 'awaiting_custom'
            return
        amount = int(amount_str)
        await process_invest(update, context, user_id, amount, query)

async def process_invest(update, context, user_id, amount, query=None):
    money = get_money(user_id)
    invest_type = context.user_data.get('invest_type')
    if not invest_type:
        await (query.edit_message_text if query else update.message.reply_text)("❌ Ошибка.")
        return
    if money < amount:
        await (query.edit_message_text if query else update.message.reply_text)(f"❌ У вас {money}. Недостаточно.")
        return
    deduct_money(user_id, amount)
    stats = get_user_stats(user_id)
    if invest_type == "army":
        add = int(amount * 0.5)
        new_military = stats['military'] + add
        set_user_stats(user_id, military=new_military)
        text = f"✅ Вложили {amount}. Армия +{add}, теперь {new_military}."
    else:
        add = int(amount * 0.3)
        new_economy = stats['economy'] + add
        set_user_stats(user_id, economy=new_economy)
        text = f"✅ Вложили {amount}. Экономика +{add}, теперь {new_economy}."
    if query:
        await query.edit_message_text(text)
    else:
        await update.message.reply_text(text)
    context.user_data.pop('invest_action', None)
    context.user_data.pop('invest_type', None)

async def handle_invest_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('invest_action') == 'awaiting_custom':
        user_id = update.message.from_user.id
        try:
            amount = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ Введите число.")
            return
        if amount <= 0:
            await update.message.reply_text("❌ >0.")
            return
        await process_invest(update, context, user_id, amount, query=None)

# ---------- ПРИВЕТСТВИЕ С ПИНОМ ----------
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    new_chat_member = update.my_chat_member
    if new_chat_member.new_chat_member.user.id != context.bot.id:
        return
    if new_chat_member.new_chat_member.status in ['member', 'administrator']:
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="👋 Привет! Я бот «Завоевание мира 1914».\n"
                 "Команды: /help\n"
                 "Выберите страну через /country и начните завоевания! 🌍"
        )
        try:
            await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=msg.message_id)
        except Exception as e:
            logger.error(f"Не удалось закрепить: {e}")

# ---------- ОСНОВНОЙ ЗАПУСК ----------
def main():
    init_db()
    create_bots_if_needed()
    init_colonies()
    update_currency_rates()

    application = Application.builder().token(TOKEN).build()

    # Регистрация команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("country", country))
    application.add_handler(CommandHandler("mystatus", mystatus))
    application.add_handler(CommandHandler("mystats", mystats))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("war", war_command))
    application.add_handler(CommandHandler("research", research_command))
    application.add_handler(CommandHandler("spy", spy_command))
    application.add_handler(CommandHandler("top", top_command))
    application.add_handler(CommandHandler("napt", napt_command))
    application.add_handler(CommandHandler("neutral", neutral_command))
    application.add_handler(CommandHandler("mobilize", mobilize_command))
    application.add_handler(CommandHandler("demobilize", demobilize_command))
    application.add_handler(CommandHandler("colonies", colonies_command))
    application.add_handler(CommandHandler("invest_colony", invest_colony_command))
    application.add_handler(CommandHandler("fortify", fortify_command))
    application.add_handler(CommandHandler("build_fleet", build_fleet_command))
    application.add_handler(CommandHandler("blockade", blockade_command))
    application.add_handler(CommandHandler("sabotage", sabotage_command))
    application.add_handler(CommandHandler("vote", vote_command))
    application.add_handler(CommandHandler("vote_cast", vote_cast_command))
    application.add_handler(CommandHandler("season", season_command))
    application.add_handler(CommandHandler("currency", currency_command))
    application.add_handler(CommandHandler("crisis", crisis_command))
    application.add_handler(CommandHandler("logistics", logistics_command))
    application.add_handler(CommandHandler("bots", bots_list))

    application.add_handler(CommandHandler("ally", ally_command))
    application.add_handler(CommandHandler("break_ally", break_ally_command))
    application.add_handler(CommandHandler("allies", allies_list))
    application.add_handler(CallbackQueryHandler(ally_callback, pattern="^(accept_ally_|reject_ally_)"))

    application.add_handler(CommandHandler("sanction", sanction_command))
    application.add_handler(CommandHandler("remove_sanctions", remove_sanctions_command))
    application.add_handler(CommandHandler("sanctions", sanctions_list))

    application.add_handler(CommandHandler("invest", invest_command))
    application.add_handler(CallbackQueryHandler(invest_callback, pattern="^inv_"))

    application.add_handler(CommandHandler("puppets", puppets_list))
    application.add_handler(CommandHandler("free_puppet", free_puppet_command))

    trade_conv = ConversationHandler(
        entry_points=[CommandHandler("auction", auction_start)],
        states={
            TRADE_SELECT_PARTNER: [CallbackQueryHandler(trade_select_partner)],
            TRADE_SELECT_OFFER_TYPE: [CallbackQueryHandler(trade_select_offer_type)],
            TRADE_OFFER_AMOUNT: [CallbackQueryHandler(trade_offer_amount)],
            TRADE_SELECT_REQUEST_TYPE: [CallbackQueryHandler(trade_select_request_type)],
            TRADE_REQUEST_AMOUNT: [CallbackQueryHandler(trade_request_amount)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        allow_reentry=True
    )
    application.add_handler(trade_conv)

    # Общий обработчик текста (для кастомных сумм в инвестициях и торговле)
    async def handle_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('invest_action') == 'awaiting_custom':
            await handle_invest_text(update, context)
        elif context.user_data.get('awaiting_custom_offer') or context.user_data.get('awaiting_custom_request'):
            # торговля
            await handle_trade_text(update, context)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_text))

    # Callback'и для торговли
    application.add_handler(CallbackQueryHandler(trade_select_partner, pattern="^(?!.*(cancel_trade|offer_|request_|accept_trade_|reject_trade_|inv_|accept_ally_|reject_ally_|join_war_|peace_|end_war_|accept_peace_|reject_peace_|research_|spy_)).*$"))
    application.add_handler(CallbackQueryHandler(trade_select_offer_type, pattern="^offer_resources$|^offer_money$|^cancel_trade$"))
    application.add_handler(CallbackQueryHandler(trade_offer_amount, pattern="^offer_"))
    application.add_handler(CallbackQueryHandler(trade_select_request_type, pattern="^request_resources$|^request_money$|^cancel_trade$"))
    application.add_handler(CallbackQueryHandler(trade_request_amount, pattern="^request_"))
    application.add_handler(CallbackQueryHandler(trade_response_callback, pattern="^(accept_trade_|reject_trade_)"))

    # Другие callback'и
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^(?!accept_trade_|reject_trade_|inv_|accept_ally_|reject_ally_|join_war_|peace_|end_war_|accept_peace_|reject_peace_|research_|spy_)"))
    application.add_handler(CallbackQueryHandler(join_war_callback, pattern="^join_war_"))
    application.add_handler(CallbackQueryHandler(end_war_callback, pattern="^end_war_"))
    application.add_handler(CallbackQueryHandler(peace_proposal, pattern="^peace_"))
    application.add_handler(CallbackQueryHandler(peace_response_callback, pattern="^(accept_peace_|reject_peace_)"))
    application.add_handler(CallbackQueryHandler(research_callback, pattern="^research_"))
    application.add_handler(CallbackQueryHandler(spy_callback, pattern="^spy_"))

    application.add_handler(ChatMemberHandler(welcome, ChatMemberHandler.MY_CHAT_MEMBER))

    # Периодические задачи
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(bot_actions, interval=600, first=60)
        job_queue.run_repeating(lambda ctx: update_resistance(), interval=3600, first=300)
        job_queue.run_repeating(lambda ctx: update_currency_rates(), interval=3600, first=300)
        job_queue.run_repeating(lambda ctx: check_votes(), interval=3600, first=60)
        job_queue.run_repeating(lambda ctx: check_and_resolve_wars(), interval=60, first=10)
        job_queue.run_repeating(lambda ctx: check_research_queue(), interval=60, first=30)
        job_queue.run_repeating(lambda ctx: update_colonies(), interval=600, first=120)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

# ---------- ОБРАБОТЧИКИ ТОРГОВЛИ (ДОПОЛНИТЕЛЬНЫЕ) ----------
async def auction_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id) or is_puppet(user_id):
        await update.message.reply_text("❌ Недоступно.")
        return ConversationHandler.END
    users = get_all_users_countries()
    partners = [c for c, uid in users.items() if uid['user_id'] != user_id and not uid['is_puppet']]
    if not partners:
        await update.message.reply_text("❌ Нет доступных партнёров.")
        return ConversationHandler.END
    filtered = []
    for c in partners:
        pid = get_user_id_by_country(c)
        if not is_sanctioned_between(user_id, pid):
            filtered.append(c)
    if not filtered:
        await update.message.reply_text("❌ Со всеми санкции.")
        return ConversationHandler.END
    keyboard = []
    for c in filtered:
        keyboard.append([InlineKeyboardButton(c, callback_data=c)])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_trade")])
    await update.message.reply_text("📦 Выберите страну для торговли:", reply_markup=InlineKeyboardMarkup(keyboard))
    return TRADE_SELECT_PARTNER

async def trade_select_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cancel_trade":
        await query.edit_message_text("❌ Отменено.")
        return ConversationHandler.END
    partner_id = get_user_id_by_country(data)
    if not partner_id:
        await query.edit_message_text("❌ Партнёр не активен.")
        return ConversationHandler.END
    user_id = query.from_user.id
    if is_sanctioned_between(user_id, partner_id):
        await query.edit_message_text("❌ Санкции.")
        return ConversationHandler.END
    context.user_data['trade_partner'] = data
    context.user_data['trade_partner_id'] = partner_id
    currency = get_country_currency(get_user_country(user_id))
    await query.edit_message_text(
        f"Торговля с *{data}*.\n"
        f"У вас: ресурсов {get_resources(user_id)}, денег {get_money(user_id)} {currency}\n"
        f"У партнёра: ресурсов {get_resources(partner_id)}, денег {get_money(partner_id)} {get_country_currency(data)}\n\n"
        f"Что вы предлагаете?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Ресурсы", callback_data="offer_resources")],
            [InlineKeyboardButton("💰 Деньги", callback_data="offer_money")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_trade")]
        ])
    )
    return TRADE_SELECT_OFFER_TYPE

async def trade_select_offer_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cancel_trade":
        await query.edit_message_text("❌ Отменено.")
        return ConversationHandler.END
    context.user_data['offer_type'] = 'resources' if data == 'offer_resources' else 'money'
    user_id = query.from_user.id
    max_amount = get_resources(user_id) if context.user_data['offer_type'] == 'resources' else get_money(user_id)
    unit = 'ресурсов' if context.user_data['offer_type'] == 'resources' else get_country_currency(get_user_country(user_id))
    await query.edit_message_text(
        f"Сколько {unit} предлагаете? (у вас {max_amount})",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("10", callback_data="offer_10")],
            [InlineKeyboardButton("50", callback_data="offer_50")],
            [InlineKeyboardButton("100", callback_data="offer_100")],
            [InlineKeyboardButton("500", callback_data="offer_500")],
            [InlineKeyboardButton("Свой вариант", callback_data="offer_custom")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_trade")]
        ])
    )
    return TRADE_OFFER_AMOUNT

async def trade_offer_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cancel_trade":
        await query.edit_message_text("❌ Отменено.")
        return ConversationHandler.END
    user_id = query.from_user.id
    if data == "offer_custom":
        await query.edit_message_text("Введите число в чат:")
        context.user_data['awaiting_custom_offer'] = True
        return TRADE_OFFER_AMOUNT
    amount = int(data.split('_')[1])
    max_amount = get_resources(user_id) if context.user_data['offer_type'] == 'resources' else get_money(user_id)
    if amount > max_amount:
        await query.edit_message_text(f"❌ У вас {max_amount}.")
        return TRADE_OFFER_AMOUNT
    context.user_data['offer_amount'] = amount
    partner_id = context.user_data['trade_partner_id']
    partner_currency = get_country_currency(context.user_data['trade_partner'])
    await query.edit_message_text(
        f"Что вы хотите получить от партнёра?\n"
        f"У партнёра: ресурсов {get_resources(partner_id)}, денег {get_money(partner_id)} {partner_currency}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Ресурсы", callback_data="request_resources")],
            [InlineKeyboardButton("💰 Деньги", callback_data="request_money")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_trade")]
        ])
    )
    return TRADE_SELECT_REQUEST_TYPE

async def trade_select_request_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cancel_trade":
        await query.edit_message_text("❌ Отменено.")
        return ConversationHandler.END
    context.user_data['request_type'] = 'resources' if data == 'request_resources' else 'money'
    partner_id = context.user_data['trade_partner_id']
    max_amount = get_resources(partner_id) if context.user_data['request_type'] == 'resources' else get_money(partner_id)
    unit = 'ресурсов' if context.user_data['request_type'] == 'resources' else get_country_currency(context.user_data['trade_partner'])
    await query.edit_message_text(
        f"Сколько {unit} вы хотите? (у партнёра {max_amount})",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("10", callback_data="request_10")],
            [InlineKeyboardButton("50", callback_data="request_50")],
            [InlineKeyboardButton("100", callback_data="request_100")],
            [InlineKeyboardButton("500", callback_data="request_500")],
            [InlineKeyboardButton("Свой вариант", callback_data="request_custom")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_trade")]
        ])
    )
    return TRADE_REQUEST_AMOUNT

async def trade_request_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cancel_trade":
        await query.edit_message_text("❌ Отменено.")
        return ConversationHandler.END
    user_id = query.from_user.id
    if data == "request_custom":
        await query.edit_message_text("Введите число в чат:")
        context.user_data['awaiting_custom_request'] = True
        return TRADE_REQUEST_AMOUNT
    amount = int(data.split('_')[1])
    partner_id = context.user_data['trade_partner_id']
    max_amount = get_resources(partner_id) if context.user_data['request_type'] == 'resources' else get_money(partner_id)
    if amount > max_amount:
        await query.edit_message_text(f"❌ У партнёра {max_amount}.")
        return TRADE_REQUEST_AMOUNT
    context.user_data['request_amount'] = amount
    offered_type = context.user_data['offer_type']
    offered_amount = context.user_data['offer_amount']
    requested_type = context.user_data['request_type']
    requested_amount = context.user_data['request_amount']
    create_trade(user_id, partner_id, offered_type, offered_amount, requested_type, requested_amount)
    my_currency = get_country_currency(get_user_country(user_id))
    partner_currency = get_country_currency(context.user_data['trade_partner'])
    await query.edit_message_text(
        f"✅ Предложение отправлено!\n"
        f"Вы предлагаете: {offered_amount} {'ресурсов' if offered_type=='resources' else my_currency}\n"
        f"Вы просите: {requested_amount} {'ресурсов' if requested_type=='resources' else partner_currency}"
    )
    chat_id = query.message.chat_id
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📦 *{get_user_country(user_id)}* предлагает торговлю!\n"
             f"Предлагает: {offered_amount} {'ресурсов' if offered_type=='resources' else my_currency}\n"
             f"Просит: {requested_amount} {'ресурсов' if requested_type=='resources' else partner_currency}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Принять", callback_data=f"accept_trade_{user_id}_{partner_id}")],
            [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_trade_{user_id}_{partner_id}")]
        ])
    )
    return ConversationHandler.END

async def trade_response_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split('_')
    if len(parts) != 3:
        await query.edit_message_text("❌ Ошибка.")
        return
    action, from_id, to_id = parts[0], int(parts[1]), int(parts[2])
    if query.from_user.id != to_id:
        await query.answer("Не для вас.", show_alert=True)
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM trades WHERE from_user=? AND to_user=? AND status='pending'", (from_id, to_id))
    row = cur.fetchone()
    conn.close()
    if not row:
        await query.edit_message_text("❌ Предложение не найдено.")
        return
    trade_id = row[0]
    if action == "accept":
        success = accept_trade(trade_id)
        if success:
            await query.edit_message_text("✅ Торговля принята!")
        else:
            await query.edit_message_text("❌ Недостаточно средств.")
    else:
        reject_trade(trade_id)
        await query.edit_message_text("❌ Торговля отклонена.")

async def handle_trade_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if context.user_data.get('awaiting_custom_offer'):
        try:
            amount = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ Введите число.")
            return
        if amount <= 0:
            await update.message.reply_text("❌ >0.")
            return
        max_amount = get_resources(user_id) if context.user_data['offer_type'] == 'resources' else get_money(user_id)
        if amount > max_amount:
            await update.message.reply_text(f"❌ У вас {max_amount}.")
            return
        context.user_data['offer_amount'] = amount
        context.user_data['awaiting_custom_offer'] = False
        partner_id = context.user_data['trade_partner_id']
        partner_currency = get_country_currency(context.user_data['trade_partner'])
        await update.message.reply_text(
            f"Что вы хотите получить от партнёра?\n"
            f"У партнёра: ресурсов {get_resources(partner_id)}, денег {get_money(partner_id)} {partner_currency}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 Ресурсы", callback_data="request_resources")],
                [InlineKeyboardButton("💰 Деньги", callback_data="request_money")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_trade")]
            ])
        )
        return
    elif context.user_data.get('awaiting_custom_request'):
        try:
            amount = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ Введите число.")
            return
        if amount <= 0:
            await update.message.reply_text("❌ >0.")
            return
        partner_id = context.user_data['trade_partner_id']
        max_amount = get_resources(partner_id) if context.user_data['request_type'] == 'resources' else get_money(partner_id)
        if amount > max_amount:
            await update.message.reply_text(f"❌ У партнёра {max_amount}.")
            return
        context.user_data['request_amount'] = amount
        context.user_data['awaiting_custom_request'] = False
        offered_type = context.user_data['offer_type']
        offered_amount = context.user_data['offer_amount']
        requested_type = context.user_data['request_type']
        requested_amount = context.user_data['request_amount']
        create_trade(user_id, partner_id, offered_type, offered_amount, requested_type, requested_amount)
        my_currency = get_country_currency(get_user_country(user_id))
        partner_currency = get_country_currency(context.user_data['trade_partner'])
        await update.message.reply_text(
            f"✅ Предложение отправлено!\n"
            f"Вы предлагаете: {offered_amount} {'ресурсов' if offered_type=='resources' else my_currency}\n"
            f"Вы просите: {requested_amount} {'ресурсов' if requested_type=='resources' else partner_currency}"
        )
        chat_id = update.message.chat_id
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📦 *{get_user_country(user_id)}* предлагает торговлю!\n"
                 f"Предлагает: {offered_amount} {'ресурсов' if offered_type=='resources' else my_currency}\n"
                 f"Просит: {requested_amount} {'ресурсов' if requested_type=='resources' else partner_currency}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Принять", callback_data=f"accept_trade_{user_id}_{partner_id}")],
                [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_trade_{user_id}_{partner_id}")]
            ])
        )
        context.user_data.clear()
        return

# ---------- ЗАПУСК ----------
if __name__ == "__main__":
    main()
