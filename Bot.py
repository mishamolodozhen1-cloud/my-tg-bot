import logging
import sqlite3
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            country TEXT,
            resources INTEGER DEFAULT 1000,
            money INTEGER DEFAULT 10000,
            population INTEGER DEFAULT 10000000,
            military INTEGER DEFAULT 100000,
            economy INTEGER DEFAULT 500,
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            master_id INTEGER DEFAULT NULL,
            is_puppet INTEGER DEFAULT 0
        )
    """)
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]
    for col in ['population', 'military', 'economy', 'last_update', 'master_id', 'is_puppet']:
        if col not in columns:
            if col == 'master_id':
                cur.execute("ALTER TABLE users ADD COLUMN master_id INTEGER DEFAULT NULL")
            elif col == 'is_puppet':
                cur.execute("ALTER TABLE users ADD COLUMN is_puppet INTEGER DEFAULT 0")
            else:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} {'INTEGER' if col != 'last_update' else 'TIMESTAMP'} DEFAULT {'10000000' if col == 'population' else '100000' if col == 'military' else '500' if col == 'economy' else 'CURRENT_TIMESTAMP'}")

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
    conn.commit()
    conn.close()

# ---------- ОБНОВЛЕНИЕ СТАТИСТИКИ ----------
def update_user_stats(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT population, military, economy, resources, money, last_update, master_id, is_puppet FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return
    pop, mil, eco, res, money, last_upd_str, master_id, is_puppet = row
    last_upd = datetime.fromisoformat(last_upd_str)
    now = datetime.now()
    hours = (now - last_upd).total_seconds() / 3600
    if hours < 0.05:
        conn.close()
        return
    pop = int(pop * (1 + 0.0001 * hours))
    mil = max(0, int(mil * (1 - 0.001 * hours)))
    eco = int(eco * (1 + 0.0005 * hours))
    res = int(res * (1 + 0.001 * hours))
    money = int(money * (1 + 0.002 * hours))
    if master_id is not None:
        old_res = row[3]
        gained = res - old_res
        if gained > 0:
            master_share = int(gained * 0.1)
            if master_share > 0:
                cur.execute("UPDATE users SET resources = resources + ? WHERE user_id = ?", (master_share, master_id))
    cur.execute("""
        UPDATE users SET population=?, military=?, economy=?, resources=?, money=?, last_update=?
        WHERE user_id=?
    """, (pop, mil, eco, res, money, now.isoformat(), user_id))
    conn.commit()
    conn.close()

def get_user_stats(user_id: int):
    update_user_stats(user_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT country, resources, money, population, military, economy, master_id, is_puppet FROM users WHERE user_id=?", (user_id,))
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
            'master_id': row[6],
            'is_puppet': row[7]
        }
    return None

def set_user_stats(user_id: int, **kwargs):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    updates = []
    params = []
    for key, value in kwargs.items():
        if key in ['population', 'military', 'economy', 'resources', 'money', 'master_id', 'is_puppet']:
            updates.append(f"{key}=?")
            params.append(value)
    if updates:
        params.append(datetime.now().isoformat())
        params.append(user_id)
        cur.execute(f"UPDATE users SET {', '.join(updates)}, last_update=? WHERE user_id=?", params)
        conn.commit()
    conn.close()

# ---------- ОСНОВНЫЕ ФУНКЦИИ ----------
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
        REPLACE INTO users (user_id, country, resources, money, population, military, economy, last_update, master_id, is_puppet)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, country, data.get('initial_resources', 1000), 10000,
          data.get('population', 10000000), data.get('army', 100000),
          data.get('initial_economy', 500), datetime.now().isoformat(), None, 0))
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
    conn.commit()
    conn.close()

def get_all_users_countries():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT country, user_id, is_puppet FROM users")
    rows = cur.fetchall()
    conn.close()
    return {row[0]: {'user_id': row[1], 'is_puppet': row[2]} for row in rows}

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

def get_country_currency(country: str) -> str:
    return COUNTRIES_DATA.get(country, {}).get("currency", "ден. ед.")

def get_country_power(country: str) -> int:
    data = COUNTRIES_DATA.get(country)
    if not data:
        return 0
    return data.get("army", 0) + data.get("initial_resources", 500)

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
        f"└ Мощность: {get_country_power(country):,}"
    )

# ---------- ФУНКЦИИ ВОЙНЫ ----------
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

def resolve_war(war_id: int):
    info = get_war_info(war_id)
    if not info or info['status'] != 'active':
        return None
    attackers, defenders = get_war_participants(war_id)
    if not attackers or not defenders:
        finish_war(war_id)
        return None

    total_att = sum(get_country_power(get_user_country(u)) for u in attackers if get_user_country(u))
    total_def = sum(get_country_power(get_user_country(u)) for u in defenders if get_user_country(u))

    if total_att >= total_def:
        winner_side = 'attacker'
        winner_ids = attackers
        loser_ids = defenders
    else:
        winner_side = 'defender'
        winner_ids = defenders
        loser_ids = attackers

    # Применяем потери к проигравшим
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

    # Бонус победителям: +10% ресурсов и денег
    for winner_id in winner_ids:
        stats = get_user_stats(winner_id)
        if stats:
            new_res = int(stats['resources'] * 1.1)
            new_money = int(stats['money'] * 1.1)
            set_user_stats(winner_id, resources=new_res, money=new_money)

    winner_id = winner_ids[0] if winner_ids else None
    finish_war(war_id, winner_id)
    return {
        'winner_side': winner_side,
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
            result = resolve_war(war_id)
            if result:
                # уведомление будет отправлено в обработчике
                pass
    conn.close()

# ---------- ТОРГОВЛЯ (состояния) ----------
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

# ---------- ОБРАБОТЧИКИ ТОРГОВЛИ ----------
async def auction_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id):
        await update.message.reply_text("❌ Выберите страну через /country.")
        return ConversationHandler.END
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может торговать.")
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
        await update.message.reply_text("❌ Со всеми доступными игроками у вас санкции.")
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
        await query.edit_message_text("❌ Торговля отменена.")
        return ConversationHandler.END
    partner_id = get_user_id_by_country(data)
    if not partner_id:
        await query.edit_message_text("❌ Партнёр больше не активен.")
        return ConversationHandler.END
    user_id = query.from_user.id
    if is_puppet(partner_id):
        await query.edit_message_text("❌ Нельзя торговать с марионеткой.")
        return ConversationHandler.END
    if is_sanctioned_between(user_id, partner_id):
        await query.edit_message_text("❌ Торговля заблокирована из-за санкций.")
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
        await query.edit_message_text("❌ Отмена.")
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
        await query.edit_message_text("❌ Отмена.")
        return ConversationHandler.END
    user_id = query.from_user.id
    if data == "offer_custom":
        await query.edit_message_text("Введите число (количество) в чат:")
        context.user_data['awaiting_custom_offer'] = True
        return TRADE_OFFER_AMOUNT
    amount = int(data.split('_')[1])
    max_amount = get_resources(user_id) if context.user_data['offer_type'] == 'resources' else get_money(user_id)
    if amount > max_amount:
        await query.edit_message_text(f"❌ У вас всего {max_amount}. Попробуйте снова.")
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
        await query.edit_message_text("❌ Отмена.")
        return ConversationHandler.END
    context.user_data['request_type'] = 'resources' if data == 'request_resources' else 'money'
    partner_id = context.user_data['trade_partner_id']
    max_amount = get_resources(partner_id) if context.user_data['request_type'] == 'resources' else get_money(partner_id)
    unit = 'ресурсов' if context.user_data['request_type'] == 'resources' else get_country_currency(context.user_data['trade_partner'])
    await query.edit_message_text(
        f"Сколько {unit} вы хотите получить? (у партнёра {max_amount})",
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
        await query.edit_message_text("❌ Отмена.")
        return ConversationHandler.END
    user_id = query.from_user.id
    if data == "request_custom":
        await query.edit_message_text("Введите число (количество) в чат:")
        context.user_data['awaiting_custom_request'] = True
        return TRADE_REQUEST_AMOUNT
    amount = int(data.split('_')[1])
    partner_id = context.user_data['trade_partner_id']
    max_amount = get_resources(partner_id) if context.user_data['request_type'] == 'resources' else get_money(partner_id)
    if amount > max_amount:
        await query.edit_message_text(f"❌ У партнёра всего {max_amount}. Попробуйте снова.")
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
        await query.edit_message_text("❌ Ошибка формата.")
        return
    action, from_id, to_id = parts[0], int(parts[1]), int(parts[2])
    if query.from_user.id != to_id:
        await query.answer("Это предложение не для вас!", show_alert=True)
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM trades WHERE from_user=? AND to_user=? AND status='pending'", (from_id, to_id))
    row = cur.fetchone()
    conn.close()
    if not row:
        await query.edit_message_text("❌ Предложение не найдено или уже обработано.")
        return
    trade_id = row[0]
    if action == "accept":
        success = accept_trade(trade_id)
        if success:
            await query.edit_message_text("✅ Торговля принята! Обмен произведён.")
        else:
            await query.edit_message_text("❌ Недостаточно средств у одной стороны. Сделка отклонена.")
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
            await update.message.reply_text("❌ Число должно быть >0.")
            return
        max_amount = get_resources(user_id) if context.user_data['offer_type'] == 'resources' else get_money(user_id)
        if amount > max_amount:
            await update.message.reply_text(f"❌ У вас всего {max_amount}. Попробуйте снова.")
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
            await update.message.reply_text("❌ Число должно быть >0.")
            return
        partner_id = context.user_data['trade_partner_id']
        max_amount = get_resources(partner_id) if context.user_data['request_type'] == 'resources' else get_money(partner_id)
        if amount > max_amount:
            await update.message.reply_text(f"❌ У партнёра всего {max_amount}. Попробуйте снова.")
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

# ---------- ОСНОВНЫЕ КОМАНДЫ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    check_and_resolve_wars()
    await update.message.reply_text(
        "Добро пожаловать в ролевую игру «Завоевание мира 1914»!\n\n"
        "/country — выбрать страну\n"
        "/mystats — ваша статистика\n"
        "/info <страна> — информация о стране\n"
        "/war <страна> — объявить войну (длится 10 мин)\n"
        "/auction — торговать\n"
        "/invest — инвестировать\n"
        "/ally <страна> — предложить союз\n"
        "/break_ally <страна> — разорвать союз\n"
        "/allies — список союзников\n"
        "/sanction <страна> — ввести санкции\n"
        "/remove_sanctions <страна> — снять санкции\n"
        "/sanctions — список ваших санкций\n"
        "/puppets — список марионеток\n"
        "/free_puppet <страна> — освободить марионетку\n"
        "/countries — список стран\n"
        "/reset — сбросить страну\n"
        "/help — помощь"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n"
        "/country — выбрать страну\n"
        "/mystatus — ваша страна\n"
        "/mystats — статистика\n"
        "/info <название> — информация о стране\n"
        "/war <название> — объявить войну (длится 10 мин, кнопка завершения только для инициатора)\n"
        "/auction — торговать\n"
        "/invest — инвестировать\n"
        "/ally <название> — предложить союз\n"
        "/break_ally <название> — разорвать союз\n"
        "/allies — список союзников\n"
        "/sanction <название> — ввести санкции\n"
        "/remove_sanctions <название> — снять санкции\n"
        "/sanctions — список ваших санкций\n"
        "/puppets — список марионеток\n"
        "/free_puppet <название> — освободить марионетку\n"
        "/countries — список стран\n"
        "/reset — сбросить страну\n"
        "/help — эта справка"
    )

async def countries_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users_countries()
    lines = []
    for i, c in enumerate(COUNTRIES_LIST, 1):
        if c in users:
            if users[c]['is_puppet']:
                mark = "🟠 (марионетка)"
            else:
                mark = "🔴 (занята)"
        else:
            mark = "🟢 (свободна)"
        lines.append(f"{i}. {c} {mark}")
    await update.message.reply_text("🌍 Все страны 1914 года:\n\n" + "\n".join(lines))

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
                    label = c + " 🔴"
            else:
                label = c + " 🟢"
            row.append(InlineKeyboardButton(label, callback_data=c))
        keyboard.append(row)
    await update.message.reply_text(
        "👇 Выберите страну (🔴 занята, 🟠 марионетка, 🟢 свободна):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    country_name = query.data
    users = get_all_users_countries()
    if country_name in users:
        if users[country_name]['is_puppet']:
            await query.edit_message_text("❌ Эта страна является марионеткой и не может быть выбрана.")
            return
        await query.edit_message_text("❌ Эта страна уже занята.")
        return
    set_user_country(user_id, country_name)
    await query.edit_message_text(f"✅ Вы выбрали страну:\n\n{format_country_info(country_name)}", parse_mode="Markdown")

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
        f"└ Статус: {'Марионетка' if stats['is_puppet'] else 'Свободна'}"
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
            await update.message.reply_text("❌ Укажите страну: /info <название>")
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

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    delete_user_country(user_id)
    await update.message.reply_text("🔄 Выбор страны сброшен, все связи удалены.")

# ---------- ВОЙНА (команда) ----------
async def war_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может воевать.")
        return
    if get_active_war_for_user(user_id):
        await update.message.reply_text("❌ Вы уже участвуете в войне.")
        return
    attacker = get_user_country(user_id)
    if not attacker:
        await update.message.reply_text("❌ Выберите страну через /country.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /war <название страны>")
        return
    target = " ".join(context.args).strip()
    defender = None
    for c in COUNTRIES_LIST:
        if c.lower() == target.lower():
            defender = c
            break
    if not defender:
        await update.message.reply_text("❌ Страна не найдена.")
        return
    def_id = get_user_id_by_country(defender)
    if not def_id:
        await update.message.reply_text(f"❌ {defender} не занята игроком.")
        return
    if def_id == user_id:
        await update.message.reply_text("❌ Нельзя воевать с собой.")
        return
    if is_puppet(def_id):
        master = get_master(def_id)
        master_country = get_user_country(master) if master else None
        await update.message.reply_text(f"❌ {defender} является марионеткой {master_country}. Воевать нужно с хозяином.")
        return
    if is_ally(user_id, def_id):
        await update.message.reply_text("❌ Нельзя нападать на союзника.")
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM wars w
        JOIN war_participants wp1 ON w.id = wp1.war_id
        JOIN war_participants wp2 ON w.id = wp2.war_id
        WHERE w.status='active' AND wp1.user_id=? AND wp2.user_id=?
    """, (user_id, def_id))
    if cur.fetchone():
        conn.close()
        await update.message.reply_text("❌ Эти страны уже воюют.")
        return
    conn.close()

    war_id = create_war(user_id, def_id)
    chat_id = update.message.chat_id

    # Кнопки для инициатора (он видит кнопку "Завершить войну")
    keyboard_initiator = [
        [InlineKeyboardButton("🕊️ Предложить мир", callback_data=f"peace_{war_id}")],
        [InlineKeyboardButton("⚔️ Завершить войну", callback_data=f"end_war_{war_id}")],
        [InlineKeyboardButton("⚔️ Вступить в войну (союзникам)", callback_data=f"join_war_{war_id}")]
    ]
    # Кнопки для остальных (без "Завершить войну")
    keyboard_others = [
        [InlineKeyboardButton("🕊️ Предложить мир", callback_data=f"peace_{war_id}")],
        [InlineKeyboardButton("⚔️ Вступить в войну (союзникам)", callback_data=f"join_war_{war_id}")]
    ]

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⚔️ **Война началась между {attacker} и {defender}!**\n"
             f"Война продлится 10 минут или до завершения инициатором.\n"
             f"Инициатор: {attacker}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard_initiator)
    )
    # Оповещаем союзников
    for ally_id in get_allies(user_id, 'accepted'):
        ally_country = get_user_country(ally_id)
        if ally_country and ally_id != user_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔔 Ваш союзник {attacker} начал войну с {defender}. Вы можете вступить на стороне {attacker}.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚔️ Вступить", callback_data=f"join_war_{war_id}_{attacker}")]
                ])
            )
    for ally_id in get_allies(def_id, 'accepted'):
        ally_country = get_user_country(ally_id)
        if ally_country and ally_id != def_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔔 Ваш союзник {defender} атакован {attacker}. Вы можете вступить на стороне {defender}.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚔️ Вступить", callback_data=f"join_war_{war_id}_{defender}")]
                ])
            )

# ---------- ОБРАБОТЧИКИ ВОЙНЫ ----------
async def join_war_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split('_')
    if len(parts) < 3:
        await query.edit_message_text("❌ Ошибка.")
        return
    war_id = int(parts[2])
    side = parts[3] if len(parts) > 3 else None
    user_id = query.from_user.id
    if is_puppet(user_id):
        await query.answer("Марионетка не может воевать.", show_alert=True)
        return
    if get_active_war_for_user(user_id):
        await query.answer("Вы уже участвуете в войне.", show_alert=True)
        return
    if not side:
        await query.edit_message_text("Выберите сторону:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("За нападающего", callback_data=f"join_war_{war_id}_attacker")],
            [InlineKeyboardButton("За защитника", callback_data=f"join_war_{war_id}_defender")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_join_{war_id}")]
        ]))
        return
    attackers, defenders = get_war_participants(war_id)
    if side == 'attacker':
        if not any(is_ally(user_id, a) for a in attackers) and user_id not in attackers:
            await query.answer("Вы не союзник нападающей стороны.", show_alert=True)
            return
        add_participant(war_id, user_id, 'attacker')
        await query.edit_message_text("✅ Вы вступили в войну на стороне нападающих.")
    else:
        if not any(is_ally(user_id, d) for d in defenders) and user_id not in defenders:
            await query.answer("Вы не союзник защищающейся стороны.", show_alert=True)
            return
        add_participant(war_id, user_id, 'defender')
        await query.edit_message_text("✅ Вы вступили в войну на стороне защитников.")

async def end_war_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Завершить войну' – доступна только инициатору."""
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
        await query.answer("Только инициатор может завершить войну!", show_alert=True)
        return
    # Завершаем войну
    result = resolve_war(war_id)
    if not result:
        await query.edit_message_text("❌ Ошибка при завершении войны.")
        return
    # Сообщаем результат всем участникам
    chat_id = query.message.chat_id
    winner_str = ", ".join(result['winner_countries'])
    loser_str = ", ".join(result['loser_countries'])
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⚔️ **Война завершена по решению инициатора!**\n\n"
             f"🏆 **Победители:** {winner_str}\n"
             f"📉 **Проигравшие:** {loser_str}\n"
             f"Победители получили +10% ресурсов и денег.\n"
             f"Проигравшие потеряли 5% населения, 20% армии, 10% экономики, 30% ресурсов и 20% денег.",
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
        await query.answer("Вы не участник этой войны.", show_alert=True)
        conn.close()
        return
    conn.close()
    attackers, defenders = get_war_participants(war_id)
    if user_id in attackers:
        targets = defenders
        from_side = 'attacker'
    else:
        targets = attackers
        from_side = 'defender'
    if not targets:
        await query.edit_message_text("❌ Нет противников для мира.")
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
                text=f"🕊️ {get_user_country(user_id)} предлагает мир!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Принять мир", callback_data=f"accept_peace_{war_id}_{user_id}_{target}")],
                    [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_peace_{war_id}_{user_id}_{target}")]
                ])
            )
    await query.edit_message_text("✅ Предложение мира отправлено.")

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
        await query.answer("Это предложение не для вас.", show_alert=True)
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT status FROM peace_requests WHERE war_id=? AND from_user=? AND to_user=?",
                (war_id, from_id, to_id))
    row = cur.fetchone()
    if not row or row[0] != 'pending':
        await query.edit_message_text("❌ Запрос уже обработан.")
        conn.close()
        return
    if action == 'accept_peace':
        cur.execute("UPDATE peace_requests SET status='accepted' WHERE war_id=? AND from_user=? AND to_user=?",
                    (war_id, from_id, to_id))
        finish_war(war_id, winner_id=None)
        conn.commit()
        conn.close()
        await query.edit_message_text("🕊️ Мир заключён! Война окончена без победителя.")
        chat_id = query.message.chat_id
        await context.bot.send_message(chat_id=chat_id, text="🕊️ Война завершена мирным договором.")
    else:
        cur.execute("UPDATE peace_requests SET status='rejected' WHERE war_id=? AND from_user=? AND to_user=?",
                    (war_id, from_id, to_id))
        conn.commit()
        conn.close()
        await query.edit_message_text("❌ Мир отклонён. Война продолжается.")

# ---------- ИНВЕСТИЦИИ ----------
async def invest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not get_user_country(user_id):
        await update.message.reply_text("❌ Выберите страну через /country.")
        return
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может инвестировать.")
        return
    stats = get_user_stats(user_id)
    currency = get_country_currency(stats['country'])
    keyboard = [
        [InlineKeyboardButton("⚔️ Армия", callback_data="inv_army")],
        [InlineKeyboardButton("🏭 Экономика", callback_data="inv_economy")],
        [InlineKeyboardButton("❌ Отмена", callback_data="inv_cancel")]
    ]
    await update.message.reply_text(
        f"💰 У вас {stats['money']} {currency}\nКуда вложить?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['invest_action'] = 'choose_type'

async def invest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if is_puppet(user_id):
        await query.edit_message_text("❌ Марионетка не может инвестировать.")
        return
    if data == "inv_cancel":
        await query.edit_message_text("❌ Инвестиция отменена.")
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
        await query.edit_message_text(
            f"Сумма для {'армии' if invest_type=='army' else 'экономики'}:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    if data.startswith("inv_amt_"):
        amount_str = data.split('_')[2]
        if amount_str == "custom":
            await query.edit_message_text("Введите сумму в чат (число):")
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
        await (query.edit_message_text if query else update.message.reply_text)(f"❌ У вас {money} {get_country_currency(get_user_country(user_id))}. Недостаточно.")
        return
    deduct_money(user_id, amount)
    stats = get_user_stats(user_id)
    if invest_type == "army":
        add = int(amount * 0.5)
        new_military = stats['military'] + add
        set_user_stats(user_id, military=new_military)
        text = f"✅ Вложили {amount} в армию. Армия +{add}, теперь {new_military}."
    else:
        add = int(amount * 0.3)
        new_economy = stats['economy'] + add
        set_user_stats(user_id, economy=new_economy)
        text = f"✅ Вложили {amount} в экономику. Экономика +{add}, теперь {new_economy}."
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
            await update.message.reply_text("❌ Сумма должна быть >0.")
            return
        await process_invest(update, context, user_id, amount, query=None)

# ---------- СОЮЗЫ ----------
async def ally_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может заключать союзы.")
        return
    my_country = get_user_country(user_id)
    if not my_country:
        await update.message.reply_text("❌ Выберите страну через /country.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /ally <название страны>")
        return
    target = " ".join(context.args).strip()
    partner = None
    for c in COUNTRIES_LIST:
        if c.lower() == target.lower():
            partner = c
            break
    if not partner:
        await update.message.reply_text("❌ Страна не найдена.")
        return
    partner_id = get_user_id_by_country(partner)
    if not partner_id:
        await update.message.reply_text("❌ Эта страна не занята игроком.")
        return
    if partner_id == user_id:
        await update.message.reply_text("❌ Нельзя заключить союз с собой.")
        return
    if is_puppet(partner_id):
        await update.message.reply_text("❌ Нельзя заключить союз с марионеткой.")
        return
    if is_ally(user_id, partner_id):
        await update.message.reply_text("❌ Вы уже союзники.")
        return
    if len(get_allies(user_id, 'accepted')) >= 3:
        await update.message.reply_text("❌ У вас уже 3 союзника.")
        return
    if len(get_allies(partner_id, 'accepted')) >= 3:
        await update.message.reply_text(f"❌ У {partner} уже 3 союзника.")
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM allies WHERE user_id=? AND ally_id=? AND status='pending'", (user_id, partner_id))
    if cur.fetchone():
        conn.close()
        await update.message.reply_text("❌ Запрос на союз уже отправлен.")
        return
    conn.close()
    create_ally_request(user_id, partner_id)
    chat_id = update.message.chat_id
    keyboard = [
        [InlineKeyboardButton("✅ Принять", callback_data=f"accept_ally_{user_id}_{partner_id}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_ally_{user_id}_{partner_id}")]
    ]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🤝 {my_country} предлагает союз {partner}!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("✅ Запрос на союз отправлен.")

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
    if action == "accept":
        if len(get_allies(to_id, 'accepted')) >= 3:
            await query.edit_message_text(f"❌ У {get_user_country(to_id)} уже 3 союзника.")
            return
        if len(get_allies(from_id, 'accepted')) >= 3:
            await query.edit_message_text(f"❌ У {get_user_country(from_id)} уже 3 союзника.")
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
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может разорвать союз.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /break_ally <название страны>")
        return
    target = " ".join(context.args).strip()
    partner = None
    for c in COUNTRIES_LIST:
        if c.lower() == target.lower():
            partner = c
            break
    if not partner:
        await update.message.reply_text("❌ Страна не найдена.")
        return
    partner_id = get_user_id_by_country(partner)
    if not partner_id:
        await update.message.reply_text("❌ Страна не занята.")
        return
    if not is_ally(user_id, partner_id):
        await update.message.reply_text("❌ Вы не союзники.")
        return
    break_ally(user_id, partner_id)
    await update.message.reply_text(f"✅ Союз с {partner} разорван.")

async def allies_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    allies = get_ally_countries(user_id)
    if not allies:
        await update.message.reply_text("❌ У вас нет союзников.")
        return
    text = "🤝 Ваши союзники:\n" + "\n".join(f"- {c}" for c in allies)
    await update.message.reply_text(text)

# ---------- САНКЦИИ ----------
async def sanction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_puppet(user_id):
        await update.message.reply_text("❌ Марионетка не может вводить санкции.")
        return
    my_country = get_user_country(user_id)
    if not my_country:
        await update.message.reply_text("❌ Выберите страну через /country.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ /sanction <название страны>")
        return
    target = " ".join(context.args).strip()
    partner = None
    for c in COUNTRIES_LIST:
        if c.lower() == target.lower():
            partner = c
            break
    if not partner:
        await update.message.reply_text("❌ Страна не найдена.")
        return
    partner_id = get_user_id_by_country(partner)
    if not partner_id:
        await update.message.reply_text("❌ Эта страна не занята игроком.")
        return
    if partner_id == user_id:
        await update.message.reply_text("❌ Нельзя ввести санкции против себя.")
        return
    if is_ally(user_id, partner_id):
        await update.message.reply_text("❌ Нельзя вводить санкции против союзника.")
        return
    if is_puppet(partner_id):
        await update.message.reply_text("❌ Нельзя вводить санкции против марионетки.")
        return
    if has_sanction(user_id, partner_id):
        await update.message.reply_text("❌ Санкции уже действуют.")
        return
    create_sanction(user_id, partner_id)
    await update.message.reply_text(f"🚫 Санкции против {partner} введены на 24 часа.")

async def remove_sanctions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not context.args:
        await update.message.reply_text("⚠️ /remove_sanctions <название страны>")
        return
    target = " ".join(context.args).strip()
    partner = None
    for c in COUNTRIES_LIST:
        if c.lower() == target.lower():
            partner = c
            break
    if not partner:
        await update.message.reply_text("❌ Страна не найдена.")
        return
    partner_id = get_user_id_by_country(partner)
    if not partner_id:
        await update.message.reply_text("❌ Страна не занята.")
        return
    if not has_sanction(user_id, partner_id):
        await update.message.reply_text("❌ Нет активных санкций против этой страны.")
        return
    remove_sanction(user_id, partner_id)
    await update.message.reply_text(f"✅ Санкции против {partner} сняты.")

async def sanctions_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    countries = get_sanctioned_countries(user_id)
    if not countries:
        await update.message.reply_text("❌ У вас нет активных санкций.")
        return
    text = "🚫 Страны под вашими санкциями:\n" + "\n".join(f"- {c}" for c in countries)
    await update.message.reply_text(text)

# ---------- МАРИОНЕТКИ ----------
async def puppets_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    puppets = get_puppets(user_id)
    if not puppets:
        await update.message.reply_text("❌ У вас нет марионеток.")
        return
    text = "🤝 Ваши марионетки:\n" + "\n".join(f"- {c}" for c in puppets)
    await update.message.reply_text(text)

async def free_puppet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not context.args:
        await update.message.reply_text("⚠️ /free_puppet <название страны>")
        return
    target = " ".join(context.args).strip()
    puppet = None
    for c in COUNTRIES_LIST:
        if c.lower() == target.lower():
            puppet = c
            break
    if not puppet:
        await update.message.reply_text("❌ Страна не найдена.")
        return
    puppet_id = get_user_id_by_country(puppet)
    if not puppet_id:
        await update.message.reply_text("❌ Страна не занята.")
        return
    if get_master(puppet_id) != user_id:
        await update.message.reply_text("❌ Это не ваша марионетка.")
        return
    set_user_stats(puppet_id, master_id=None, is_puppet=0)
    await update.message.reply_text(f"✅ {puppet} освобождена от статуса марионетки.")

# ---------- ПРИВЕТСТВИЕ ----------
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    new_chat_member = update.my_chat_member
    if new_chat_member.new_chat_member.user.id != context.bot.id:
        return
    if new_chat_member.new_chat_member.status in ['member', 'administrator']:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="👋 Привет! Я бот для ролевой игры «Завоевание мира 1914».\n"
                 "Команды: /help\n"
                 "Выберите страну через /country и начните завоевания! 🌍"
        )

# ---------- ОСНОВНОЙ ЗАПУСК ----------
def main():
    init_db()
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("countries", countries_list))
    application.add_handler(CommandHandler("country", country))
    application.add_handler(CommandHandler("mystatus", mystatus))
    application.add_handler(CommandHandler("mystats", mystats))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("war", war_command))

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

    async def handle_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('invest_action') == 'awaiting_custom':
            await handle_invest_text(update, context)
        elif context.user_data.get('awaiting_custom_offer') or context.user_data.get('awaiting_custom_request'):
            await handle_trade_text(update, context)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_text))

    application.add_handler(CallbackQueryHandler(button_callback, pattern="^(?!accept_trade_|reject_trade_|inv_|accept_ally_|reject_ally_|join_war_|peace_|end_war_|accept_peace_|reject_peace_)"))
    application.add_handler(CallbackQueryHandler(trade_response_callback, pattern="^(accept_trade_|reject_trade_)"))
    application.add_handler(CallbackQueryHandler(join_war_callback, pattern="^join_war_"))
    application.add_handler(CallbackQueryHandler(end_war_callback, pattern="^end_war_"))
    application.add_handler(CallbackQueryHandler(peace_proposal, pattern="^peace_"))
    application.add_handler(CallbackQueryHandler(peace_response_callback, pattern="^(accept_peace_|reject_peace_)"))

    application.add_handler(ChatMemberHandler(welcome, ChatMemberHandler.MY_CHAT_MEMBER))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()