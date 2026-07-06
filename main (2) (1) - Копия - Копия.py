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

# Юзернейм администратора для рассылки, модерации и админ-панели (без знака @)
ADMIN_USERNAME = "VibeNixS"

def load_data():
    global user_data
    if os.path.exists(DB_FILE) and os.path.getsize(DB_FILE) > 0:
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                user_data = {int(k): v for k, v in raw_data.items()}
                print("✅ Локальная БД успешно загружена.")
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
            print("🚀 Само-пинг выполнен успешно!")
        except Exception as e:
            print(f"🤖 Пинг отправлен: {e}")
        time.sleep(600)

threading.Thread(target=keep_alive, daemon=True).start()

waiting_users = []
active_chats = {}
user_to_group = {}
groups = {}

# Логирование последних сообщений для контекста жалоб {user_id: [список строк]}
chat_logs = {}

waiting_for_name = set()
waiting_for_emoji = set()
waiting_for_photo = set()
waiting_for_broadcast = set()
waiting_for_admin_search = set() 
waiting_for_report_reason = set() # Состояние ожидания текста жалобы

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
            "warns": 0,         
            "is_banned": False,
            "is_muted": False
        }
        save_data()
    else:
        changed = False
        if "reports" not in user_data[user_id]:
            user_data[user_id]["reports"] = 0
            changed = True
        if "warns" not in user_data[user_id]:
            user_data[user_id]["warns"] = 0
            changed = True
        if "is_banned" not in user_data[user_id]:
            user_data[user_id]["is_banned"] = False
            changed = True
        if "is_muted" not in user_data[user_id]:
            user_data[user_id]["is_muted"] = False
            changed = True
        if username and user_data[user_id].get("username") != username:
            user_data[user_id]["username"] = username
            changed = True
        if changed:
            save_data()

def get_admin_id():
    for u_id, data in user_data.items():
        if data.get("username") == ADMIN_USERNAME:
            return u_id
    return None

def log_message(user_id, text):
    if user_id not in chat_logs:
        chat_logs[user_id] = []
    chat_logs[user_id].append(text)
    if len(chat_logs[user_id]) > 5:
        chat_logs[user_id].pop(0)

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

def get_cancel_keyboard(in_chat=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if in_chat:
        markup.add('❌ Отмена', '⚠️ Подать жалобу')
    else:
        markup.add('❌ Отмена')
    return markup

def get_report_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('❌ Отмена жалобы')
    return markup

def get_profile_keyboard(target_user_id, viewer_username=None, is_own_profile=False):
    init_user(target_user_id)
    data = user_data[target_user_id]
    refs = data["referrals"]
    markup = InlineKeyboardMarkup()
    
    # Сценарий 1: Профиль просматривает Админ и это ЧУЖОЙ профиль -> Панель модерации
    if viewer_username == ADMIN_USERNAME and not is_own_profile:
        if data.get("is_banned"):
            markup.add(InlineKeyboardButton("🟢 Разбанить", callback_data=f"admin_unban_{target_user_id}"))
        else:
            markup.add(InlineKeyboardButton("🔴 Забанить", callback_data=f"admin_ban_{target_user_id}"))
            
        if data.get("is_muted"):
            markup.add(InlineKeyboardButton("🔊 Размутить", callback_data=f"admin_unmute_{target_user_id}"))
        else:
            markup.add(InlineKeyboardButton("🔇 Мутить", callback_data=f"admin_mute_{target_user_id}"))
            
        markup.add(
            InlineKeyboardButton("➕ Выдать варн (+1)", callback_data=f"admin_warn_{target_user_id}"),
            InlineKeyboardButton("➖ Снять варн (-1)", callback_data=f"admin_unwarn_{target_user_id}")
        )
        markup.add(InlineKeyboardButton("⚠️ Подтвердить жалобу (+1)", callback_data=f"admin_report_{target_user_id}"))
        return markup

    # Сценарий 2: Дефолтные настройки для юзеров, либо для админа в СВОЕМ личном профиле
    markup.add(InlineKeyboardButton("✏️ Изменить имя", callback_data="change_name"))
    markup.add(InlineKeyboardButton("🔗 Поделиться профилем в чат", callback_data="share_profile"))
    if refs >= 5:
        markup.add(InlineKeyboardButton("⚙️ Изменить эмодзи", callback_data="change_emoji"))
    if refs >= 10:
        markup.add(InlineKeyboardButton("🖼 Поставить картинку", callback_data="change_photo"))
        
    # Дополнительная кнопка входа в Админ-Панель только для админа в его профиле
    if viewer_username == ADMIN_USERNAME and is_own_profile:
        markup.add(InlineKeyboardButton("⚙️ Открыть Админ-Панель", callback_data="admin_open_panel"))
        
    return markup

def show_profile_card(chat_id, target_user_id, send_share_btn=False, viewer_username=None):
    init_user(target_user_id)
    data = user_data[target_user_id]
    
    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start=profile_{target_user_id}"
    
    if data.get("is_banned") or data.get("is_muted"):
        status_text = "Есть 🔴"
    else:
        status_text = "Нет ⚫"
    
    profile_text = (
        f"ℹ️ Профиль\n"
        f"🆔 ID: {target_user_id}\n"
        f"👤 Имя: {data['name']}\n"
        f"🌐 Юзернейм: @{data.get('username') if data.get('username') else 'Нет'}\n"
        f"✨ Эмодзи чата: {data.get('emoji', '💬')}\n"
        f"👥 Приглашено друзей: {data['referrals']}\n"
        f"⚠️ Жалобы: {data.get('reports', 0)}/5\n"
        f"🚫 Предупреждения (варны): {data.get('warns', 0)}/3\n"
        f"📊 Статус ограничений: {status_text}\n\n"
    )
    
    if chat_id == target_user_id:
        profile_text += f"🔗 Твоя ссылка для приглашений:\n{ref_link}"

    # Флаг: проверяем, смотрит ли юзер карточку самого себя
    is_own_profile = (chat_id == target_user_id)

    if is_own_profile:
        markup = get_profile_keyboard(target_user_id, viewer_username=viewer_username, is_own_profile=True)
    elif viewer_username == ADMIN_USERNAME:
        markup = get_profile_keyboard(target_user_id, viewer_username=ADMIN_USERNAME, is_own_profile=False)
    else:
        markup = InlineKeyboardMarkup()
        if send_share_btn:
            markup.add(InlineKeyboardButton("👤 Посмотреть профиль", callback_data=f"view_{target_user_id}"))

    if data.get("photo"):
        try:
            bot.send_photo(chat_id, data["photo"], caption=profile_text, reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, profile_text, reply_markup=markup)
    else:
        bot.send_message(chat_id, profile_text, reply_markup=markup)

# Перехват кнопки вызова админ-панели
@bot.callback_query_handler(func=lambda call: call.data == "admin_open_panel")
def callback_admin_panel(call):
    if call.from_user.username != ADMIN_USERNAME:
        bot.answer_callback_query(call.id, "❌ Доступ запрещен!")
        return
    bot.answer_callback_query(call.id)
    waiting_for_admin_search.add(call.message.chat.id)
    bot.send_message(call.message.chat.id, "⚙️ **Добро пожаловать в Админ-Панель!**\n\nВведите Telegram ID пользователя, профилем которого хотите управлять:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())

@bot.message_handler(commands=['user'])
def admin_get_user(message):
    if message.from_user.username != ADMIN_USERNAME: return
    args = message.text.split()
    if len(args) < 2:
        bot.send_message(message.chat.id, "⚠️ Использование: `/user ID`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        if target_id not in user_data:
            bot.send_message(message.chat.id, "❌ Пользователь не найден.")
            return
        show_profile_card(message.chat.id, target_id, viewer_username=ADMIN_USERNAME)
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ ID должен быть числом.")

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    username = message.from_user.username
    init_user(user_id, username)
    
    if user_data[user_id].get("is_banned"):
        bot.send_message(user_id, "❌ Вы забанены в этом боте.")
        return

    waiting_for_name.discard(user_id)
    waiting_for_emoji.discard(user_id)
    waiting_for_photo.discard(user_id)
    waiting_for_broadcast.discard(user_id)
    waiting_for_admin_search.discard(user_id)
    waiting_for_report_reason.discard(user_id)
    
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
    show_profile_card(user_id, user_id, viewer_username=username)

@bot.message_handler(commands=['profile'])
def profile_command(message):
    user_id = message.chat.id
    username = message.from_user.username
    init_user(user_id, username)
    if user_data[user_id].get("is_banned"): return
    show_profile_card(user_id, user_id, viewer_username=username)

@bot.message_handler(func=lambda message: message.text == '📢 Рассылка всем')
def broadcast_command(message):
    user_id = message.chat.id
    if message.from_user.username != ADMIN_USERNAME: return
    waiting_for_broadcast.add(user_id)
    bot.send_message(user_id, "📝 Напишите text сообщения для рассылки:", reply_markup=get_cancel_keyboard())

@bot.message_handler(commands=['name'])
def ask_name_command(message):
    user_id = message.chat.id
    if user_data[user_id].get("is_banned"): return
    if user_id in active_chats or user_id in user_to_group or user_id in waiting_users:
        return bot.send_message(user_id, "⚠️ Нельзя менять имя во время чата.")
    waiting_for_name.add(user_id)
    bot.send_message(user_id, "✍️ Напиши имя:", reply_markup=get_cancel_keyboard())

@bot.message_handler(commands=['chat'], func=lambda message: True)
@bot.message_handler(func=lambda message: message.text == '🔍 Начать поиск')
def search_handler(message):
    if user_data[message.chat.id].get("is_banned"): return
    process_search(message.chat.id)

@bot.message_handler(commands=['group'], func=lambda message: True)
@bot.message_handler(func=lambda message: message.text == '👥 Групповой чат')
def group_handler(message):
    if user_data[message.chat.id].get("is_banned"): return
    process_group(message.chat.id)

def process_search(user_id):
    if user_id in active_chats or user_id in user_to_group:
        return bot.send_message(user_id, "⚠️ Вы уже в чате.")
    if user_id in waiting_users:
        return bot.send_message(user_id, "🔍 Вы уже в поиске.")
    
    if waiting_users:
        partner_id = waiting_users.pop(0)
        active_chats[user_id], active_chats[partner_id] = partner_id, user_id
        chat_logs[user_id] = []
        chat_logs[partner_id] = []
        bot.send_message(user_id, "✅ Собеседник найден!", reply_markup=get_cancel_keyboard(in_chat=True))
        bot.send_message(partner_id, "✅ Собеседник найден!", reply_markup=get_cancel_keyboard(in_chat=True))
    else:
        waiting_users.append(user_id)
        bot.send_message(user_id, "🔍 Поиск начат... Ожидайте.", reply_markup=get_cancel_keyboard())

def process_group(user_id):
    name = get_display_name(user_id)
    if user_id in user_to_group or user_id in active_chats:
        return bot.send_message(user_id, "⚠️ Вы уже в чате.")
    
    found_gid = next((gid for gid, m in groups.items() if len(m) < 5), None)
    if found_gid:
        groups[found_gid].append(user_id)
        user_to_group[user_id] = found_gid
        chat_logs[user_id] = []
        for member in groups[found_gid]:
            if member != user_id: bot.send_message(member, f"👤 {name} вошел в группу!")
        bot.send_message(user_id, f"✅ Вы в группе. Участников: {len(groups[found_gid])}", reply_markup=get_cancel_keyboard(in_chat=True))
    else:
        new_gid = random.randint(10000, 99999)
        groups[new_gid] = [user_id]
        user_to_group[user_id] = new_gid
        chat_logs[user_id] = []
        bot.send_message(user_id, "✨ Создана новая группа. Ожидаем участников...", reply_markup=get_cancel_keyboard(in_chat=True))

@bot.message_handler(func=lambda message: message.text == '⚠️ Подать жалобу')
def report_init_handler(message):
    user_id = message.chat.id
    if user_id not in active_chats and user_id not in user_to_group:
        return bot.send_message(user_id, "⚠️ Подать жалобу можно только во время активного диалога.")
    
    waiting_for_report_reason.add(user_id)
    bot.send_message(user_id, "📋 Пожалуйста, опишите причину жалобы на собеседника:\n*(Вы можете отменить это действие кнопкой ниже)*", parse_mode="Markdown", reply_markup=get_report_cancel_keyboard())

@bot.message_handler(func=lambda message: message.text == '❌ Отмена жалобы')
def report_cancel_handler(message):
    user_id = message.chat.id
    if user_id in waiting_for_report_reason:
        waiting_for_report_reason.discard(user_id)
        bot.send_message(user_id, "↩️ Отправка жалобы отменена. Вы возвращены в чат.", reply_markup=get_cancel_keyboard(in_chat=True))
    else:
        bot.send_message(user_id, "Главное меню:", reply_markup=get_main_keyboard(message.from_user.username))

@bot.callback_query_handler(func=lambda call: call.data == "share_profile")
def callback_share_profile(call):
    user_id = call.message.chat.id
    username = call.from_user.username
    if user_id in active_chats:
        target = active_chats[user_id]
        bot.answer_callback_query(call.id, "✅ Профиль отправлен!")
        show_profile_card(target, user_id, send_share_btn=True, viewer_username=username)
    elif user_id in user_to_group:
        gid = user_to_group[user_id]
        bot.answer_callback_query(call.id, "✅ Профиль отправлен в группу!")
        for member in groups.get(gid, []):
            if member != user_id:
                show_profile_card(member, user_id, send_share_btn=True, viewer_username=username)

# Хэндлеры обработки действий кнопок админа
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_actions(call):
    if call.from_user.username != ADMIN_USERNAME:
        bot.answer_callback_query(call.id, "❌ Отказано в доступе!", show_alert=True)
        return
        
    action_data = call.data.split("_")
    action = action_data[1]
    target_id = int(action_data[2])
    init_user(target_id)
    
    if action == "ban":
        user_data[target_id]["is_banned"] = True
        bot.answer_callback_query(call.id, "🔴 Забанен!")
        try: bot.send_message(target_id, "❌ Вы были забанены администратором.")
        except: pass
    elif action == "unban":
        user_data[target_id]["is_banned"] = False
        bot.answer_callback_query(call.id, "🟢 Разбанен!")
        try: bot.send_message(target_id, "🟢 Вы разбанены администратором.")
        except: pass
    elif action == "mute":
        user_data[target_id]["is_muted"] = True
        bot.answer_callback_query(call.id, "🔇 Выдан мут!")
        try: bot.send_message(target_id, "🔇 Вам выдали ограничение чата (мут).")
        except: pass
    elif action == "unmute":
        user_data[target_id]["is_muted"] = False
        bot.answer_callback_query(call.id, "🔊 Мут снят!")
        try: bot.send_message(target_id, "🔊 С вас сняли мут.")
        except: pass
    elif action == "warn":
        user_data[target_id]["warns"] = min(user_data[target_id].get("warns", 0) + 1, 3)
        bot.answer_callback_query(call.id, f"⚠️ Выдан варн ({user_data[target_id]['warns']}/3)")
        try: bot.send_message(target_id, f"⚠️ Вы получили предупреждение (варн)! Всего: {user_data[target_id]['warns']}/3")
        except: pass
        if user_data[target_id]["warns"] >= 3:
            user_data[target_id]["is_muted"] = True
            try: bot.send_message(target_id, "🔇 Вы автоматически получили мут за 3/3 предупреждений.")
            except: pass
    elif action == "unwarn":
        user_data[target_id]["warns"] = max(user_data[target_id].get("warns", 0) - 1, 0)
        bot.answer_callback_query(call.id, f"➖ | Снят варн! ({user_data[target_id]['warns']}/3)")
        try: bot.send_message(target_id, f"✅ С вас сняли одно предупреждение. Текущие варны: {user_data[target_id]['warns']}/3")
        except: pass
    elif action == "report":
        user_data[target_id]["reports"] = min(user_data[target_id].get("reports", 0) + 1, 5)
        bot.answer_callback_query(call.id, f"Жалоба засчитана ({user_data[target_id]['reports']}/5)")
        if user_data[target_id]["reports"] >= 5:
            user_data[target_id]["is_banned"] = True
            try: bot.send_message(target_id, "❌ Вы автоматически забанены за жалобы 5/5.")
            except: pass
            
    save_data()
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    show_profile_card(call.message.chat.id, target_id, viewer_username=ADMIN_USERNAME)

@bot.callback_query_handler(func=lambda call: call.data == "change_name")
def ask_name_callback(call):
    user_id = call.message.chat.id
    if user_id in active_chats or user_id in user_to_group or user_id in waiting_users: 
        bot.answer_callback_query(call.id, "Нельзя изменять имя во время диалога!", show_alert=True)
        return
    waiting_for_name.add(user_id)
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, "✍️ Напиши новое имя:")

@bot.callback_query_handler(func=lambda call: call.data == "change_emoji")
def ask_emoji_callback(call):
    user_id = call.message.chat.id
    if user_data[user_id]["referrals"] < 5: return
    waiting_for_emoji.add(user_id)
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, "✍️ Отправь один эмодзи:")

@bot.callback_query_handler(func=lambda call: call.data == "change_photo")
def ask_photo_callback(call):
    user_id = call.message.chat.id
    if user_data[user_id]["referrals"] < 10: return
    waiting_for_photo.add(user_id)
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, "🖼 Отправь фото профиля:")

@bot.callback_query_handler(func=lambda call: call.data.startswith("view_"))
def view_other_profile(call):
    try:
        target_id = int(call.data.split("_")[1])
        show_profile_card(call.message.chat.id, target_id, viewer_username=call.from_user.username)
        bot.answer_callback_query(call.id)
    except:
        bot.answer_callback_query(call.id, "Ошибка.")

@bot.message_handler(commands=['cancel'], func=lambda message: True)
@bot.message_handler(func=lambda message: message.text == '❌ Отмена')
def stop(message):
    user_id = message.chat.id
    username = message.from_user.username
    
    if user_id in waiting_for_name or user_id in waiting_for_emoji or user_id in waiting_for_photo or user_id in waiting_for_broadcast or user_id in waiting_for_admin_search or user_id in waiting_for_report_reason:
        waiting_for_name.discard(user_id)
        waiting_for_emoji.discard(user_id)
        waiting_for_photo.discard(user_id)
        waiting_for_broadcast.discard(user_id)
        waiting_for_admin_search.discard(user_id)
        waiting_for_report_reason.discard(user_id)
        bot.send_message(user_id, "🚫 Действие отменено.", reply_markup=get_main_keyboard(username))
        return

    if user_id in waiting_users:
        waiting_users.remove(user_id)
        bot.send_message(user_id, "🚫 Поиск отменен.", reply_markup=get_main_keyboard(username))
    elif user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        chat_logs.pop(user_id, None)
        chat_logs.pop(partner_id, None)
        bot.send_message(user_id, "🚫 Диалог завершен.", reply_markup=get_main_keyboard(username))
        bot.send_message(partner_id, "🚫 Собеседник отключился.", reply_markup=get_main_keyboard(user_data.get(partner_id, {}).get("username")))
        send_rating(user_id)
        send_rating(partner_id)
    elif user_id in user_to_group:
        gid = user_to_group.pop(user_id)
        groups[gid].remove(user_id)
        chat_logs.pop(user_id, None)
        for member in groups[gid]: bot.send_message(member, f"👋 {get_display_name(user_id)} покинул группу.")
        if not groups[gid]: del groups[gid]
        bot.send_message(user_id, "🚫 Вы покинули группу.", reply_markup=get_main_keyboard(username))

@bot.callback_query_handler(func=lambda call: call.data.startswith('rate_'))
def handle_rating(call):
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Спасибо за отзыв!")

@bot.message_handler(content_types=['text', 'photo', 'sticker', 'video', 'document', 'voice'])
def chat(message):
    user_id = message.chat.id
    username = message.from_user.username
    init_user(user_id, username)
    
    if user_data[user_id].get("is_banned"):
        bot.send_message(user_id, "❌ Вы забанены.")
        return

    name = get_display_name(user_id)
    user_emoji = get_user_emoji(user_id)
    
    # Обработка написания причины жалобы
    if user_id in waiting_for_report_reason:
        waiting_for_report_reason.discard(user_id)
        reason = message.text if message.content_type == 'text' else "[Медиа-сообщение]"
        
        target_id = None
        # Выясняем, на кого жалоба
        if user_id in active_chats:
            target_id = active_chats[user_id]
        elif user_id in user_to_group:
            # В группе берем последнего, кто писал кроме нас, либо первого встречного для примера
            gid = user_to_group[user_id]
            group_members = [m for m in groups.get(gid, []) if m != user_id]
            if group_members:
                target_id = group_members[-1] # Жалоба на последнего активного в группе
                
        if not target_id:
            bot.send_message(user_id, "❌ Не удалось определить нарушителя. Возможно, чат уже закрыт.", reply_markup=get_cancel_keyboard(in_chat=True))
            return
            
        # Формируем лог чата для админа
        logs_text = "⚠️ Сообщений в логе нет."
        if user_id in chat_logs and chat_logs[user_id]:
            logs_text = "\n".join(chat_logs[user_id])
            
        admin_id = get_admin_id()
        if admin_id:
            admin_markup = InlineKeyboardMarkup()
            admin_markup.add(InlineKeyboardButton("🔨 Профиль нарушителя", callback_data=f"view_{target_id}"))
            
            report_msg = (
                f"🚨 **ПОЛУЧЕНА НОВАЯ ЖАЛОБА!**\n\n"
                f"👤 **Отправитель:** {name} (ID: `{user_id}`)\n"
                f"🎯 **Нарушитель:** {get_display_name(target_id)} (ID: `{target_id}`)\n"
                f"📝 **Причина:** {reason}\n\n"
                f"📜 **Контекст чата (Последние 5 сообщений):**\n"
                f"```\n{logs_text}\n```"
            )
            try:
                bot.send_message(admin_id, report_msg, parse_mode="Markdown", reply_markup=admin_markup)
            except Exception as e:
                print(f"Не удалось отправить жалобу админу в ЛС: {e}")
                
        bot.send_message(user_id, "✅ Ваша жалоба отправлена администрации на рассмотрение. Спасибо!", reply_markup=get_cancel_keyboard(in_chat=True))
        return

    # Обработка ввода ID в Админ-Панели
    if user_id in waiting_for_admin_search:
        waiting_for_admin_search.discard(user_id)
        try:
            target_id = int(message.text.strip())
            if target_id not in user_data:
                bot.send_message(user_id, "❌ Пользователь с таким ID не найден в БД.", reply_markup=get_main_keyboard(username))
                return
            show_profile_card(user_id, target_id, viewer_username=ADMIN_USERNAME)
        except ValueError:
            bot.send_message(user_id, "⚠️ ID должен состоять только из цифр.", reply_markup=get_main_keyboard(username))
        return

    if user_id in waiting_for_broadcast:
        waiting_for_broadcast.discard(user_id)
        bot.send_message(user_id, "⏳ Начинаю рассылку...", reply_markup=get_main_keyboard(username))
        success_count = 0
        broadcast_prefix = "👑 VibeNix: "
        for u_id in list(user_data.keys()):
            try:
                if message.content_type == 'text':
                    bot.send_message(u_id, f"{broadcast_prefix}{message.text}")
                else:
                    bot.send_message(u_id, broadcast_prefix)
                    bot.copy_message(u_id, user_id, message.message_id)
                success_count += 1
                time.sleep(0.04) 
            except: pass
        bot.send_message(user_id, f"✅ Доставлено: {success_count} пользователям.")
        return

    if user_id in waiting_for_name:
        if message.content_type == 'text':
            user_data[user_id]["name"] = message.text
            save_data()
            waiting_for_name.discard(user_id)
            bot.send_message(user_id, "✅ Имя сохранено!", reply_markup=get_main_keyboard(username))
            show_profile_card(user_id, user_id, viewer_username=username)
        return

    if user_id in waiting_for_emoji:
        if message.content_type == 'text':
            user_data[user_id]["emoji"] = message.text.strip()
            save_data()
            waiting_for_emoji.discard(user_id)
            bot.send_message(user_id, "✅ Эмодзи изменен!", reply_markup=get_main_keyboard(username))
            show_profile_card(user_id, user_id, viewer_username=username)
        return

    if user_id in waiting_for_photo:
        if message.content_type == 'photo':
            user_data[user_id]["photo"] = message.photo[-1].file_id
            save_data()
            waiting_for_photo.discard(user_id)
            bot.send_message(user_id, "✅ Картинка сохранена!", reply_markup=get_main_keyboard(username))
            show_profile_card(user_id, user_id, viewer_username=username)
        return

    if user_id in active_chats or user_id in user_to_group:
        if user_data[user_id].get("is_muted"):
            bot.send_message(user_id, "🔇 Вы замучены и не можете отправлять сообщения в чат.")
            return

        msg_log_text = message.text if message.content_type == 'text' else f"[{message.content_type.upper()}]"
        log_message(user_id, f"{name}: {msg_log_text}")

        if user_id in active_chats:
            target = active_chats[user_id]
            log_message(target, f"{name}: {msg_log_text}")
            if message.content_type == 'text': bot.send_message(target, message.text)
            else: bot.copy_message(target, user_id, message.message_id)
                
        elif user_id in user_to_group:
            gid = user_to_group[user_id]
            for member in groups.get(gid, []):
                if member != user_id:
                    log_message(member, f"{name}: {msg_log_text}")
                    if message.content_type == 'text': bot.send_message(member, f"{user_emoji} {name}: {message.text}")
                    else: 
                        bot.send_message(member, f"👤 {name}:")
                        bot.copy_message(member, user_id, message.message_id)

if __name__ == '__main__':
    print("Бот запущен...")
    try:
        bot.polling(none_stop=True, interval=0, timeout=0)
    except Exception as e:
        time.sleep(3)
        os.execv(sys.executable, ['python'] + sys.argv)
