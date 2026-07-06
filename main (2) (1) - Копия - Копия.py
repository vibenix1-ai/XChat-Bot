import telebot
import random
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import sys
import time
import json
import threading
import urllib.request

API_TOKEN = os.environ.get('API_TOKEN')
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL')

bot = telebot.TeleBot(API_TOKEN)

DB_FILE = "database.json"
user_data = {}

# Юзернейм администратора для рассылки и модерации
ADMIN_USERNAME = "VibeNixS"
ADMIN_ID = None

def load_data():
    global user_data, ADMIN_ID
    if os.path.exists(DB_FILE) and os.path.getsize(DB_FILE) > 0:
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                user_data = {int(k): v for k, v in raw_data.items()}
                print("✅ Локальная БД успешно загружена.")
                
                for uid, udata in user_data.items():
                    if udata.get("username") == ADMIN_USERNAME:
                        ADMIN_ID = uid
                        break
        except Exception as e:
            print(f"❌ Ошибка загрузки БД: {e}")
            user_data = {}
    else:
        user_data = {}

def save_data():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(user_data, f, ensure_ascii=False, indent=4)
        print("💾 БД успешно сохранена локально.")
    except Exception as e:
        print(f"❌ Ошибка сохранения БД: {e}")

load_data()

def keep_alive():
    if not RENDER_URL:
        print("Предупреждение: RENDER_EXTERNAL_URL не задан. Само-пинг отключен.")
        return
    while True:
        try:
            urllib.request.urlopen(RENDER_URL, timeout=10)
            print("🚀 Само-пинг выполнен успешно! Бот не уснет.")
        except Exception as e:
            print(f"🤖 Пинг отправлен (сервер поднимается или слушает пуллинг): {e}")
        time.sleep(600)

threading.Thread(target=keep_alive, daemon=True).start()

waiting_users = []
active_chats = {}
user_to_group = {}
groups = {}

pending_reports = {}

waiting_for_name = set()
waiting_for_emoji = set()
waiting_for_photo = set()
waiting_for_broadcast = set()

def init_user(user_id, username=None):
    if user_id not in user_data:
        user_data[user_id] = {
            "name": "Аноним",
            "username": username,
            "referrals": 0,
            "invited_by": None,
            "emoji": "💬",
            "photo": None,
            "referred_users": [],
            "reports": 0,
            "muted": False,
            "banned": False
        }
        save_data()
    else:
        if username and user_data[user_id].get("username") != username:
            user_data[user_id]["username"] = username
            save_data()
        if "reports" not in user_data[user_id]:
            user_data[user_id]["reports"] = 0
        if "muted" not in user_data[user_id]:
            user_data[user_id]["muted"] = False
        if "banned" not in user_data[user_id]:
            user_data[user_id]["banned"] = False

def get_display_name(user_id):
    init_user(user_id)
    return user_data[user_id]["name"]

def get_user_emoji(user_id):
    init_user(user_id)
    return user_data[user_id].get("emoji", "💬")

def send_rating(chat_id):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("👍", callback_data="rate_like"),
        InlineKeyboardButton("Пропуск", callback_data="rate_skip"),
        InlineKeyboardButton("👎", callback_data="rate_dislike")
    )
    bot.send_message(chat_id, "Оцените ваш диалог с собеседником 👇", reply_markup=markup)

def get_main_keyboard(message_or_username):
    username = message_or_username if isinstance(message_or_username, str) else message_or_username.from_user.username
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    if username == ADMIN_USERNAME:
        markup.add('🔍 Начать поиск', '👥 Групповой чат')
        markup.add('📢 Рассылка всем')
    else:
        markup.add('🔍 Начать поиск', '👥 Групповой чат')
    return markup

def get_cancel_keyboard(chat_id=None):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('❌ Отмена')
    if chat_id and (chat_id in active_chats or chat_id in user_to_group):
        markup.add('⚠️ Пожаловаться на собеседника')
    return markup

# Панель быстрого управления (Мут/Размут/Бан/Разбан) под сообщением
def get_action_keyboard(target_id):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🤐 Mute", callback_data=f"panel_mute_{target_id}"),
        InlineKeyboardButton("🔊 Unmute", callback_data=f"panel_unmute_{target_id}")
    )
    markup.row(
        InlineKeyboardButton("🚫 Ban", callback_data=f"panel_ban_{target_id}"),
        InlineKeyboardButton("✅ Unban", callback_data=f"panel_unban_{target_id}")
    )
    return markup

def get_profile_keyboard(user_id):
    init_user(user_id)
    data = user_data[user_id]
    refs = data["referrals"]
    markup = InlineKeyboardMarkup()
    
    markup.add(InlineKeyboardButton("✏️ Изменить имя", callback_data="change_name"))
    markup.add(InlineKeyboardButton("🔗 Поделиться профилем в чат", callback_data="share_profile"))
    
    if refs >= 5:
        markup.add(InlineKeyboardButton("⚙️ Изменить эмодзи", callback_data="change_emoji"))
    if refs >= 10:
        markup.add(InlineKeyboardButton("🖼 Поставить картинку", callback_data="change_photo"))
        
    if data.get("username") == ADMIN_USERNAME:
        markup.add(InlineKeyboardButton("🗂 Активные жалобы", callback_data="admin_view_reports"))
        
    return markup

def show_profile_card(chat_id, target_user_id, send_share_btn=False):
    init_user(target_user_id)
    data = user_data[target_user_id]
    
    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start=profile_{target_user_id}"
    
    rep_count = min(data.get("reports", 0), 5)
    dots = "⚫" * rep_count + "🔴" * (5 - rep_count)
    
    status_text = ""
    if data.get("banned"):
        status_text = "❌ БАН"
    elif data.get("muted"):
        status_text = "🔇 МУТ"
    else:
        status_text = "🟢 Активен"

    profile_text = (
        f"ℹ️ Профиль\n"
        f"👤 Имя: {data['name']}\n"
        f"✨ Эмодзи чата: {data.get('emoji', '💬')}\n"
        f"👥 Приглашено друзей: {data['referrals']}\n"
        f"📊 Статус: {status_text}\n"
        f"⚠️ Жалобы: {rep_count} из 5\n"
        f"Система: {dots}\n\n"
        f"🔗 Твоя ссылка для приглашений:\n{ref_link}"
    )
    
    markup = get_profile_keyboard(target_user_id) if chat_id == target_user_id else None
    
    if send_share_btn and chat_id != target_user_id:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("👤 Посмотреть профиль", callback_data=f"view_{target_user_id}"))

    if data.get("photo"):
        try:
            bot.send_photo(chat_id, data["photo"], caption=profile_text, reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, profile_text, reply_markup=markup)
    else:
        bot.send_message(chat_id, profile_text, reply_markup=markup)

# --- ХЕНДЛЕРЫ АДМИН-КОМАНД ЧЕРЕЗ REPLY ---
@bot.message_handler(commands=['mute', 'ban', 'unban', 'unmute'])
def admin_action_commands(message):
    if message.from_user.username != ADMIN_USERNAME:
        return bot.reply_to(message, "❌ Недостаточно прав.")
        
    if not message.reply_to_message:
        return bot.reply_to(message, "⚠️ Ответьте этой командой на сообщение пользователя, чтобы вызвать панель управления.")

    target_id = message.reply_to_message.from_user.id
    target_name = message.reply_to_message.from_user.first_name
    
    # Отправляем сообщение-панель прямо под сообщением нарушителя
    bot.send_message(
        message.chat.id,
        f"🛠 **Админ-панель управления**\n"
        f"👤 Нарушитель: {target_name} (ID: `{target_id}`)\n"
        f"👑 Панель вызвал: @{ADMIN_USERNAME}",
        parse_mode="Markdown",
        reply_markup=get_action_keyboard(target_id)
    )

# --- ОБРАБОТКА НАЖАТИЙ НА КНОПКИ АДМИН-ПАНЕЛИ ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("panel_"))
def process_panel_callback(call):
    if call.from_user.username != ADMIN_USERNAME:
        return bot.answer_callback_query(call.id, "❌ Доступ запрещен!", show_alert=True)
        
    data_parts = call.data.split("_")
    action = data_parts[1]
    target_id = int(data_parts[2])
    
    init_user(target_id)
    
    if action == "mute":
        user_data[target_id]["muted"] = True
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"🤐 Пользователь `[ID: {target_id}]` успешно **замучен**.\n👑 Модератор: @{ADMIN_USERNAME}",
            parse_mode="Markdown"
        )
        try: bot.send_message(target_id, "🔇 Вы получили мут от администратора.") 
        except Exception: pass
        
    elif action == "unmute":
        user_data[target_id]["muted"] = False
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"🔊 Пользователь `[ID: {target_id}]` **размучен**.\n👑 Модератор: @{ADMIN_USERNAME}",
            parse_mode="Markdown"
        )
        try: bot.send_message(target_id, "🔊 С вас сняли мут. Вы снова можете писать.") 
        except Exception: pass
        
    elif action == "ban":
        user_data[target_id]["banned"] = True
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"🚫 Пользователь `[ID: {target_id}]` **забанен**.\n👑 Модератор: @{ADMIN_USERNAME}",
            parse_mode="Markdown"
        )
        try: bot.send_message(target_id, "🚫 Вы заблокированы администратором.") 
        except Exception: pass
        
    elif action == "unban":
        user_data[target_id]["banned"] = False
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"✅ Пользователь `[ID: {target_id}]` **разбанен**.\n👑 Модератор: @{ADMIN_USERNAME}",
            parse_mode="Markdown"
        )
        try: bot.send_message(target_id, "✅ Ваш профиль был разбанен администратором.") 
        except Exception: pass

    save_data()
    bot.answer_callback_query(call.id, "Действие выполнено!")

@bot.message_handler(commands=['start'])
def start(message):
    global ADMIN_ID
    user_id = message.chat.id
    username = message.from_user.username
    init_user(user_id, username)
    
    if username == ADMIN_USERNAME:
        ADMIN_ID = user_id

    if user_data[user_id].get("banned"):
        return bot.send_message(user_id, "🚫 Вы заблокированы в этом боте.")

    waiting_for_name.discard(user_id)
    waiting_for_emoji.discard(user_id)
    waiting_for_photo.discard(user_id)
    waiting_for_broadcast.discard(user_id)
    
    start_args = message.text.split()
    if len(start_args) > 1 and start_args[1].startswith("profile_"):
        try:
            inviter_id = int(start_args[1].replace("profile_", ""))
            if user_data[user_id]["invited_by"] is None and inviter_id != user_id:
                init_user(inviter_id)
                if user_id not in user_data[inviter_id]["referred_users"]:
                    user_data[user_id]["invited_by"] = inviter_id
                    user_data[inviter_id]["referrals"] += 1
                    user_data[inviter_id]["referred_users"].append(user_id)
                    save_data()
                    try:
                        bot.send_message(inviter_id, f"🎉 По вашей реферальной ссылке перешел новый пользователь! Всего рефералов: {user_data[inviter_id]['referrals']}")
                    except Exception:
                        pass
        except ValueError:
            pass

    bot.send_message(user_id, "👋 Привет! Выбери действие:", reply_markup=get_main_keyboard(username))
    show_profile_card(user_id, user_id)

@bot.message_handler(commands=['profile'])
def profile_command(message):
    user_id = message.chat.id
    if user_data.get(user_id, {}).get("banned"): return
    init_user(user_id, message.from_user.username)
    show_profile_card(user_id, user_id)

@bot.message_handler(func=lambda message: message.text == '📢 Рассылка всем')
def broadcast_command(message):
    user_id = message.chat.id
    username = message.from_user.username
    if username != ADMIN_USERNAME: return
        
    waiting_for_broadcast.add(user_id)
    bot.send_message(user_id, "📝 Напишите текст сообщения или отправьте любой медиафайл, который нужно разослать ВСЕМ:", reply_markup=get_cancel_keyboard(user_id))

@bot.message_handler(commands=['name'])
def ask_name_command(message):
    user_id = message.chat.id
    if user_data.get(user_id, {}).get("banned"): return
    if user_id in active_chats or user_id in user_to_group or user_id in waiting_users:
        return bot.send_message(user_id, "⚠️ Нельзя менять имя во время поиска или чата.")
    waiting_for_name.add(user_id)
    bot.send_message(user_id, "✍️ Напиши имя, которое будет отображаться в чатах:", reply_markup=get_cancel_keyboard(user_id))

@bot.message_handler(commands=['chat'], func=lambda message: True)
@bot.message_handler(func=lambda message: message.text == '🔍 Начать поиск')
def search_handler(message):
    if user_data.get(message.chat.id, {}).get("banned"): return
    process_search(message.chat.id)

@bot.message_handler(commands=['group'], func=lambda message: True)
@bot.message_handler(func=lambda message: message.text == '👥 Групповой чат')
def group_handler(message):
    if user_data.get(message.chat.id, {}).get("banned"): return
    process_group(message.chat.id)

def process_search(user_id):
    if user_id in active_chats or user_id in user_to_group:
        return bot.send_message(user_id, "⚠️ Вы уже в чате.", reply_markup=get_cancel_keyboard(user_id))
    if user_id in waiting_users:
        return bot.send_message(user_id, "🔍 Вы уже в поиске.", reply_markup=get_cancel_keyboard(user_id))
    
    waiting_for_name.discard(user_id)
    waiting_for_emoji.discard(user_id)
    waiting_for_photo.discard(user_id)
    waiting_for_broadcast.discard(user_id)
    
    if waiting_users:
        partner_id = waiting_users.pop(0)
        active_chats[user_id], active_chats[partner_id] = partner_id, user_id
        bot.send_message(user_id, "✅ Собеседник найден!", reply_markup=get_cancel_keyboard(user_id))
        bot.send_message(partner_id, "✅ Собеседник найден!", reply_markup=get_cancel_keyboard(partner_id))
    else:
        waiting_users.append(user_id)
        bot.send_message(user_id, "🔍 Поиск начат... Ожидайте.", reply_markup=get_cancel_keyboard(user_id))

def process_group(user_id):
    name = get_display_name(user_id)
    if user_id in user_to_group or user_id in active_chats:
        return bot.send_message(user_id, "⚠️ Вы уже в чате.", reply_markup=get_cancel_keyboard(user_id))
    
    waiting_for_name.discard(user_id)
    waiting_for_emoji.discard(user_id)
    waiting_for_photo.discard(user_id)
    waiting_for_broadcast.discard(user_id)
    
    found_gid = next((gid for gid, m in groups.items() if len(m) < 5), None)
    if found_gid:
        groups[found_gid].append(user_id)
        user_to_group[user_id] = found_gid
        for member in groups[found_gid]:
            if member != user_id: 
                bot.send_message(member, f"👤 {name} вошел в группу!", reply_markup=get_cancel_keyboard(member))
        bot.send_message(user_id, f"✅ Вы в группе. Участников: {len(groups[found_gid])}", reply_markup=get_cancel_keyboard(user_id))
    else:
        new_gid = random.randint(10000, 99999)
        groups[new_gid] = [user_id]
        user_to_group[user_id] = new_gid
        bot.send_message(user_id, "✨ Создана новая группа. Ожидаем участников...", reply_markup=get_cancel_keyboard(user_id))

@bot.message_handler(func=lambda message: message.text == '⚠️ Пожаловаться на собеседника')
def report_handler(message):
    user_id = message.chat.id
    target_id = None
    
    if user_id in active_chats:
        target_id = active_chats[user_id]
    elif user_id in user_to_group:
        gid = user_to_group[user_id]
        other_members = [m for m in groups.get(gid, []) if m != user_id]
        if other_members:
            target_id = other_members[-1]
            
    if not target_id:
        return bot.send_message(user_id, "⚠️ Ошибка: Собеседник не найден.")
        
    bot.send_message(user_id, "⏳ Жалоба отправлена администрации на рассмотрение.")
    
    if target_id not in pending_reports:
        pending_reports[target_id] = []
    if user_id not in pending_reports[target_id]:
        pending_reports[target_id].append(user_id)

    if ADMIN_ID:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🗂 Посмотреть жалобу", callback_data=f"adm_manage_{target_id}"))
        bot.send_message(ADMIN_ID, f"🚨 Новая жалоба на пользователя {get_display_name(target_id)} (ID: `{target_id}`). Поступило жалоб: {len(pending_reports[target_id])}", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_view_reports")
def admin_view_reports_list(call):
    if call.from_user.username != ADMIN_USERNAME: return
    
    if not pending_reports:
        return bot.answer_callback_query(call.id, "🗂 Активных жалоб нет!", show_alert=True)
        
    markup = InlineKeyboardMarkup()
    for target_id, reporters in pending_reports.items():
        markup.add(InlineKeyboardButton(f"👤 {get_display_name(target_id)} (Жалоб: {len(reporters)})", callback_data=f"adm_manage_{target_id}"))
        
    bot.send_message(call.message.chat.id, "🗂 Список пользователей с активными жалобами:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_manage_"))
def admin_manage_user_report(call):
    if call.from_user.username != ADMIN_USERNAME: return
    target_id = int(call.data.split("_")[2])
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("⚠️ Предупреждение", callback_data=f"verdict_warn_{target_id}"),
        InlineKeyboardButton("🔇 Мут", callback_data=f"verdict_mute_{target_id}")
    )
    markup.add(
        InlineKeyboardButton("🚫 Бан", callback_data=f"verdict_ban_{target_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"verdict_decline_{target_id}")
    )
    
    bot.send_message(
        call.message.chat.id, 
        f"⚙️ Выберите вердикт для пользователя *{get_display_name(target_id)}* (ID: `{target_id}`):", 
        reply_markup=markup, 
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("verdict_"))
def admin_execute_verdict(call):
    if call.from_user.username != ADMIN_USERNAME: return
    
    data_parts = call.data.split("_")
    action = data_parts[1]
    target_id = int(data_parts[2])
    
    init_user(target_id)
    
    if action == "warn":
        user_data[target_id]["reports"] = user_data[target_id].get("reports", 0) + 1
        bot.send_message(call.message.chat.id, f"✅ Выдано предупреждение. Теперь жалоб: {user_data[target_id]['reports']}/5")
        try: bot.send_message(target_id, "⚠️ Администратор выдал вам предупреждение за нарушение правил чата!")
        except Exception: pass
        
    elif action == "mute":
        user_data[target_id]["muted"] = True
        bot.send_message(call.message.chat.id, f"🔇 Пользователь временно ограничен в отправке сообщений (Мут).")
        try: bot.send_message(target_id, "🔇 Вы получили мут от администратора и больше не можете писать в чаты.")
        except Exception: pass
        
    elif action == "ban":
        user_data[target_id]["banned"] = True
        bot.send_message(call.message.chat.id, f"🚫 Пользователь полностью заблокирован в системе.")
        try: bot.send_message
