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
BACKUP_CHAT_ID = os.environ.get('BACKUP_CHAT_ID')  # ID чата/канала бэкапов (например, -100xxxxxxxxx)
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL')

bot = telebot.TeleBot(API_TOKEN)

DB_FILE = "database.json"
user_data = {}

# Юзернейм администратора, у которого будет кнопка рассылки
ADMIN_USERNAME = "VibeNixS"

def load_data():
    global user_data
    
    # 1. Если локального файла нет или он пустой (например, после деплоя на Render)
    if not os.path.exists(DB_FILE) or os.path.getsize(DB_FILE) == 0:
        if BACKUP_CHAT_ID:
            print("🔄 Локальная БД не найдена. Попытка восстановить из закрепленного сообщения Telegram...")
            try:
                # Получаем информацию о чате бэкапа и ищем закрепленное сообщение
                chat = bot.get_chat(BACKUP_CHAT_ID)
                pinned_msg = chat.pinned_message
                
                if pinned_msg and pinned_msg.document:
                    file_info = bot.get_file(pinned_msg.document.file_id)
                    downloaded_file = bot.download_file(file_info.file_path)
                    
                    with open(DB_FILE, 'wb') as new_file:
                        new_file.write(downloaded_file)
                    print("📥 БД успешно восстановлена и скачана из закрепленного сообщения!")
                else:
                    print("⚠️ В чате бэкапа нет закрепленного сообщения с файлом database.json")
            except Exception as e:
                print(f"❌ Не удалось автоматически скачать бэкап из TG: {e}")

    # 2. Стандартная загрузка локального файла в память бота
    if os.path.exists(DB_FILE) and os.path.getsize(DB_FILE) > 0:
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                user_data = {int(k): v for k, v in raw_data.items()}
                print("✅ БД успешно загружена в память.")
        except Exception as e:
            print(f"❌ Ошибка чтения JSON: {e}")
            user_data = {}
    else:
        user_data = {}

def save_data():
    try:
        # Сохраняем данные локально в файл
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(user_data, f, ensure_ascii=False, indent=4)
        
        # Отправляем файл в Telegram и закрепляем его как самый актуальный
        if BACKUP_CHAT_ID:
            with open(DB_FILE, "rb") as f:
                msg = bot.send_document(
                    BACKUP_CHAT_ID, 
                    f, 
                    caption=f"📦 Авто-бэкап базы данных\n🕒 Время: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                try:
                    # Закрепляем новое сообщение, старые откреплять не нужно — бот всегда берет последнее закрепленное
                    bot.pin_chat_message(BACKUP_CHAT_ID, msg.message_id, disable_notification=True)
                except Exception as pin_err:
                    print(f"⚠️ Не удалось закрепить сообщение (проверьте права бота на закрепление): {pin_err}")
                    
    except Exception as e:
        print(f"❌ Ошибка сохранения/бэкапа БД: {e}")

# Запуск первоначальной загрузки данных при старте скрипта
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

waiting_for_name = set()
waiting_for_emoji = set()
waiting_for_photo = set()
waiting_for_broadcast = set()  # Состояние ожидания сообщения для рассылки

def init_user(user_id, username=None):
    if user_id not in user_data:
        user_data[user_id] = {
            "name": "Аноним",
            "username": username,
            "referrals": 0,
            "invited_by": None,
            "emoji": "💬",
            "photo": None,
            "referred_users": []
        }
        save_data()
    elif username and user_data[user_id].get("username") != username:
        user_data[user_id]["username"] = username
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

# Динамическое главное меню: проверяет юзернейм и добавляет кнопку админу
def get_main_keyboard(message_or_username):
    username = message_or_username if isinstance(message_or_username, str) else message_or_username.from_user.username
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    if username == ADMIN_USERNAME:
        markup.add('🔍 Начать поиск', '👥 Групповой чат')
        markup.add('📢 Рассылка всем')  # Эта кнопка появится только у @VibeNixS
    else:
        markup.add('🔍 Начать поиск', '👥 Групповой чат')
    return markup

def get_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('❌ Отмена')
    return markup

def get_profile_keyboard(user_id):
    init_user(user_id)
    refs = user_data[user_id]["referrals"]
    markup = InlineKeyboardMarkup()
    
    markup.add(InlineKeyboardButton("✏️ Изменить имя", callback_data="change_name"))
    markup.add(InlineKeyboardButton("🔗 Поделиться профилем в чат", callback_data="share_profile"))
    
    if refs >= 5:
        markup.add(InlineKeyboardButton("⚙️ Изменить эмодзи", callback_data="change_emoji"))
    
    if refs >= 10:
        markup.add(InlineKeyboardButton("🖼 Поставить картинку", callback_data="change_photo"))
        
    return markup

def show_profile_card(chat_id, target_user_id, send_share_btn=False):
    init_user(target_user_id)
    data = user_data[target_user_id]
    
    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start=profile_{target_user_id}"
    
    profile_text = (
        f"ℹ️ Профиль\n"
        f"👤 Имя: {data['name']}\n"
        f"✨ Эмодзи чата: {data.get('emoji', '💬')}\n"
        f"👥 Приглашено друзей: {data['referrals']}\n\n"
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

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    username = message.from_user.username
    init_user(user_id, username)
    
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
    show_profile_card(user_id, user_id)

# Хэндлер активации режима рассылки (только для @VibeNixS)
@bot.message_handler(func=lambda message: message.text == '📢 Рассылка всем')
def broadcast_command(message):
    user_id = message.chat.id
    username = message.from_user.username
    if username != ADMIN_USERNAME:
        return  # Обычные пользователи игнорируются
        
    waiting_for_broadcast.add(user_id)
    bot.send_message(user_id, "📝 Напишите сообщение (текст, фото, видео или стикер) для рассылки всем пользователям бота:", reply_markup=get_cancel_keyboard())

@bot.message_handler(commands=['name'])
def ask_name_command(message):
    user_id = message.chat.id
    if user_id in active_chats or user_id in user_to_group or user_id in waiting_users:
        return bot.send_message(user_id, "⚠️ Нельзя менять имя во время поиска или чата.")
    waiting_for_name.add(user_id)
    bot.send_message(user_id, "✍️ Напиши имя, которое будет отображаться в чатах:", reply_markup=get_cancel_keyboard())

@bot.message_handler(commands=['chat'], func=lambda message: True)
@bot.message_handler(func=lambda message: message.text == '🔍 Начать поиск')
def search_handler(message):
    process_search(message.chat.id)

@bot.message_handler(commands=['group'], func=lambda message: True)
@bot.message_handler(func=lambda message: message.text == '👥 Групповой чат')
def group_handler(message):
    process_group(message.chat.id)

def process_search(user_id):
    if user_id in active_chats or user_id in user_to_group:
        return bot.send_message(user_id, "⚠️ Вы уже в чате.", reply_markup=get_cancel_keyboard())
    if user_id in waiting_users:
        return bot.send_message(user_id, "🔍 Вы уже в поиске.", reply_markup=get_cancel_keyboard())
    
    waiting_for_name.discard(user_id)
    waiting_for_emoji.discard(user_id)
    waiting_for_photo.discard(user_id)
    waiting_for_broadcast.discard(user_id)
    
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
        return bot.send_message(user_id, "⚠️ Вы уже в чате.", reply_markup=get_cancel_keyboard())
    
    waiting_for_name.discard(user_id)
    waiting_for_emoji.discard(user_id)
    waiting_for_photo.discard(user_id)
    waiting_for_broadcast.discard(user_id)
    
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
        bot.send_message(target, "📥 Собеседник поделился своим профилем:")
        show_profile_card(target, user_id, send_share_btn=True)
    elif user_id in user_to_group:
        gid = user_to_group[user_id]
        bot.answer_callback_query(call.id, "✅ Профиль отправлен в группу!")
        for member in groups.get(gid, []):
            if member != user_id:
                bot.send_message(member, "📥 Участник поделился своим профилем:")
                show_profile_card(member, user_id, send_share_btn=True)
    else:
        bot.answer_callback_query(call.id, "⚠️ Вы должны быть в чате, чтобы поделиться!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "change_name")
def ask_name_callback(call):
    user_id = call.message.chat.id
    if user_id in active_chats or user_id in user_to_group or user_id in waiting_users:
        bot.answer_callback_query(call.id, "⚠️ Нельзя менять имя во время поиска или чата.")
        return
    waiting_for_name.add(user_id)
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, "✍️ Напиши имя, которое будет отображаться в чатах:", reply_markup=get_cancel_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "change_emoji")
def ask_emoji_callback(call):
    user_id = call.message.chat.id
    init_user(user_id)
    if user_data[user_id]["referrals"] < 5:
        bot.answer_callback_query(call.id, "❌ Требуется минимум 5 рефералов!")
        return
    waiting_for_emoji.add(user_id)
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, "✍️ Отправь один любой эмодзи, который заменит значок перед твоим именем:", reply_markup=get_cancel_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "change_photo")
def ask_photo_callback(call):
    user_id = call.message.chat.id
    init_user(user_id)
    if user_data[user_id]["referrals"] < 10:
        bot.answer_callback_query(call.id, "❌ Требуется минимум 10 рефералов!")
        return
    waiting_for_photo.add(user_id)
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, "🖼 Отправь прямоугольную картинку для твоего профиля:", reply_markup=get_cancel_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("view_"))
def view_other_profile(call):
    try:
        target_id = int(call.data.split("_")[1])
        show_profile_card(call.message.chat.id, target_id)
        bot.answer_callback_query(call.id)
    except Exception:
        bot.answer_callback_query(call.id, "Ошибка загрузки профиля.")

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
        for member in groups[gid]: 
            bot.send_message(member, f"👋 {get_display_name(user_id)} покинул группу.")
        if not groups[gid]: 
            del groups[gid]
        bot.send_message(user_id, "🚫 Вы покинули группу.", reply_markup=get_main_keyboard(username))
    else:
        bot.send_message(user_id, "⚠️ Вы не находитесь в активном процессе.", reply_markup=get_main_keyboard(username))

@bot.callback_query_handler(func=lambda call: call.data.startswith('rate_'))
def handle_rating(call):
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Спасибо за отзыв!")
    bot.answer_callback_query(call.id, "Спасибо за ваш отзыв!")

@bot.message_handler(content_types=['text', 'photo', 'sticker', 'video', 'document', 'voice'])
def chat(message):
    user_id = message.chat.id
    username = message.from_user.username
    init_user(user_id, username)
    name = get_display_name(user_id)
    user_emoji = get_user_emoji(user_id)
    
    # Логика отправки массовой рассылки
    if user_id in waiting_for_broadcast:
        waiting_for_broadcast.discard(user_id)
        bot.send_message(user_id, "⏳ Начинаю рассылку для всех пользователей...", reply_markup=get_main_keyboard(username))
        
        success_count = 0
        all_users = list(user_data.keys())
        
        for u_id in all_users:
            try:
                if message.content_type == 'text':
                    bot.send_message(u_id, message.text)
                else:
                    bot.copy_message(u_id, user_id, message.message_id)
                success_count += 1
                time.sleep(0.05)  # Небольшая задержка во избежание спам-лимитов
            except Exception:
                pass  # Игнорируем тех, кто заблокировал бота
                
        bot.send_message(user_id, f"✅ Рассылка завершена!\nДоставлено: {success_count} пользователям.")
        return

    if user_id in waiting_for_name:
        if message.content_type == 'text':
            user_data[user_id]["name"] = message.text
            save_data()
            waiting_for_name.discard(user_id)
            bot.send_message(user_id, f"✅ Имя сохранено: {message.text}!", reply_markup=get_main_keyboard(username))
            show_profile_card(user_id, user_id)
        else:
            bot.send_message(user_id, "⚠️ Пожалуйста, введите имя текстом.")
        return

    if user_id in waiting_for_emoji:
        if message.content_type == 'text' and len(message.text.strip()) <= 4:
            user_data[user_id]["emoji"] = message.text.strip()
            save_data()
            waiting_for_emoji.discard(user_id)
            bot.send_message(user_id, f"✅ Эмодзи изменен на: {message.text.strip()}", reply_markup=get_main_keyboard(username))
            show_profile_card(user_id, user_id)
        else:
            bot.send_message(user_id, "⚠️ Пожалуйста, отправьте один корректный эмодзи.")
        return

    if user_id in waiting_for_photo:
        if message.content_type == 'photo':
            photo_id = message.photo[-1].file_id
            user_data[user_id]["photo"] = photo_id
