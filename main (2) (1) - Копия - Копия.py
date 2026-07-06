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

# Юзернейм администратора для рассылки и модерации (без знака @)
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
            "reports": 0,       # Жалобы (0/5)
            "warns": 0,         # Варны (0/3)
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

def get_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('❌ Отмена')
    return markup

def get_profile_keyboard(user_id, viewer_username=None):
    init_user(user_id)
    data = user_data[user_id]
    refs = data["referrals"]
    markup = InlineKeyboardMarkup()
    
    if viewer_username != ADMIN_USERNAME:
        markup.add(InlineKeyboardButton("✏️ Изменить имя", callback_data="change_name"))
        markup.add(InlineKeyboardButton("🔗 Поделиться профилем в чат", callback_data="share_profile"))
        if refs >= 5:
            markup.add(InlineKeyboardButton("⚙️ Изменить эмодзи", callback_data="change_emoji"))
        if refs >= 10:
            markup.add(InlineKeyboardButton("🖼 Поставить картинку", callback_data="change_photo"))
    else:
        # Панель управления для тебя (@VibeNixS)
        # Управление Баном
        if data.get("is_banned"):
            markup.add(InlineKeyboardButton("🟢 Разбанить", callback_data=f"admin_unban_{user_id}"))
        else:
            markup.add(InlineKeyboardButton("🔴 Забанить", callback_data=f"admin_ban_{user_id}"))
            
        # Управление Мутом
        if data.get("is_muted"):
            markup.add(InlineKeyboardButton("🔊 Размутить", callback_data=f"admin_unmute_{user_id}"))
        else:
            markup.add(InlineKeyboardButton("🔇 Мутить", callback_data=f"admin_mute_{user_id}"))
            
        # Управление Варнами (Предупреждениями)
        markup.add(
            InlineKeyboardButton("➕ Выдать варн (+1)", callback_data=f"admin_warn_{user_id}"),
            InlineKeyboardButton("➖ Снять варн (-1)", callback_data=f"admin_unwarn_{user_id}")
        )
        
        # Подтверждение жалобы
        markup.add(InlineKeyboardButton("⚠️ Подтвердить жалобу (+1)", callback_data=f"admin_report_{user_id}"))
        
    return markup

def show_profile_card(chat_id, target_user_id, send_share_btn=False, viewer_username=None):
    init_user(target_user_id)
    data = user_data[target_user_id]
    
    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start=profile_{target_user_id}"
    
    status_emoji = "🔴" if (data.get("is_banned") or data.get("is_muted")) else "⚫"
    
    profile_text = (
        f"ℹ️ Профиль\n"
        f"🆔 ID: {target_user_id}\n"
        f"👤 Имя: {data['name']}\n"
        f"🌐 Юзернейм: @{data.get('username') if data.get('username') else 'Нету'}\n"
        f"✨ Эмодзи чата: {data.get('emoji', '💬')}\n"
        f"👥 Приглашено друзей: {data['referrals']}\n"
        f"⚠️ Жалобы: {data.get('reports', 0)}/5\n"
        f"🚫 Предупреждения (варны): {data.get('warns', 0)}/3\n"
        f"📊 Статус ограничений: {status_emoji}\n\n"
    )
    
    if chat_id == target_user_id:
        profile_text += f"🔗 Твоя ссылка для приглашений:\n{ref_link}"

    if chat_id == target_user_id:
        markup = get_profile_keyboard(target_user_id)
    elif viewer_username == ADMIN_USERNAME:
        markup = get_profile_keyboard(target_user_id, viewer_username=ADMIN_USERNAME)
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

# Секретная админ-команда для поиска ЛЮБОГО пользователя по его ID
@bot.message_handler(commands=['user'])
def admin_get_user(message):
    if message.from_user.username != ADMIN_USERNAME:
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.send_message(message.chat.id, "⚠️ Использование команды: `/user ID_ПОЛЬЗОВАТЕЛЯ`", parse_mode="Markdown")
        return
        
    try:
        target_id = int(args[1])
        if target_id not in user_data:
            bot.send_message(message.chat.id, "❌ Пользователь с таким ID не найден в базе данных бота.")
            return
            
        show_profile_card(message.chat.id, target_id, viewer_username=ADMIN_USERNAME)
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ ID должен состоять только из цифр.")

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
    init_user(user_id, message.from_user.username)
    if user_data[user_id].get("is_banned"): return
    show_profile_card(user_id, user_id)

@bot.message_handler(func=lambda message: message.text == '📢 Рассылка всем')
def broadcast_command(message):
    user_id = message.chat.id
    if message.from_user.username != ADMIN_USERNAME: return
    waiting_for_broadcast.add(user_id)
    bot.send_message(user_id, "📝 Напишите текст сообщения для рассылки:", reply_markup=get_cancel_keyboard())

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
        bot.send_message(user_id, "✅ Собеседник найден!", reply_markup=get_cancel_keyboard())
        bot.send_message(partner_id, "✅ Собеседник найден!", reply_markup=get_cancel_keyboard())
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
        for member in groups[found_gid]:
            if member != user_id: bot.send_message(member, f"👤 {name} вошел в группу!")
        bot.send_message(user_id, f"✅ Вы в группе. Участников: {len(groups[found_gid])}", reply_markup=get_cancel_keyboard())
    else:
        new_gid = random.randint(10000, 99999)
        groups[new_gid] = [user_id]
        user_to_group[user_id] = new_gid
        bot.send_message(user_id, "✨ Создана новая группа. Ожидаем участников...", reply_markup=get_cancel_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "share_profile")
def callback_share_profile(call):
    user_id = call.message.chat.id
    if user_id in active_chats:
        target = active_chats[user_id]
        bot.answer_callback_query(call.id, "✅ Профиль отправлен!")
        show_profile_card(target, user_id, send_share_btn=True)
    elif user_id in user_to_group:
        gid = user_to_group[user_id]
        bot.answer_callback_query(call.id, "✅ Профиль отправлен в группу!")
        for member in groups.get(gid, []):
            if member != user_id:
                show_profile_card(member, user_id, send_share_btn=True)

# Хэндлеры для тебя (Администратора)
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
        bot.answer_callback_query(call.id, f"➖ Варн снят! ({user_data[target_id]['warns']}/3)")
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
    if user_id in active_chats or user_id in user_to_group or user_id in waiting_users: return
    waiting_for_name.add(user_id)
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, "✍ Presione имя:")

@bot.callback_query_handler(func=lambda call: call.data == "change_emoji")
def ask_emoji_callback(call):
    user_id = call.message.chat.id
    if user_data[user_id]["referrals"] < 5: return
    waiting_for_emoji.add(user_id)
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, "✍ Отправь один эмодзи:")

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
    
    if user_id in waiting_for_name or user_id in waiting_for_emoji or user_id in waiting_for_photo or user_id in waiting_for_broadcast:
        waiting_for_name.discard(user_id)
        waiting_for_emoji.discard(user_id)
        waiting_for_photo.discard(user_id)
        waiting_for_broadcast.discard(user_id)
        bot.send_message(user_id, "🚫 Действие отменено.", reply_markup=get_main_keyboard(username))
        return

    if user_id in waiting_users:
        waiting_users.remove(user_id)
        bot.send_message(user_id, "🚫 Поиск отменен.", reply_markup=get_main_keyboard(username))
    elif user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        bot.send_message(user_id, "🚫 Диалог завершен.", reply_markup=get_main_keyboard(username))
        bot.send_message(partner_id, "🚫 Собеседник отключился.", reply_markup=get_main_keyboard(user_data.get(partner_id, {}).get("username")))
        send_rating(user_id)
        send_rating(partner_id)
    elif user_id in user_to_group:
        gid = user_to_group.pop(user_id)
        groups[gid].remove(user_id)
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
            show_profile_card(user_id, user_id)
        return

    if user_id in waiting_for_emoji:
        if message.content_type == 'text':
            user_data[user_id]["emoji"] = message.text.strip()
            save_data()
            waiting_for_emoji.discard(user_id)
            bot.send_message(user_id, "✅ Эмодзи изменен!", reply_markup=get_main_keyboard(username))
            show_profile_card(user_id, user_id)
        return

    if user_id in waiting_for_photo:
        if message.content_type == 'photo':
            user_data[user_id]["photo"] = message.photo[-1].file_id
            save_data()
            waiting_for_photo.discard(user_id)
            bot.send_message(user_id, "✅ Картинка сохранена!", reply_markup=get_main_keyboard(username))
            show_profile_card(user_id, user_id)
        return

    # Проверка на МУТ перед отправкой в чат
    if user_id in active_chats or user_id in user_to_group:
        if user_data[user_id].get("is_muted"):
            bot.send_message(user_id, "🔇 Вы замучены и не можете отправлять сообщения в чат.")
            return

        if user_id in active_chats:
            target = active_chats[user_id]
            if message.content_type == 'text': bot.send_message(target, message.text)
            else: bot.copy_message(target, user_id, message.message_id)
                
        elif user_id in user_to_group:
            gid = user_to_group[user_id]
            for member in groups.get(gid, []):
                if member != user_id:
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
