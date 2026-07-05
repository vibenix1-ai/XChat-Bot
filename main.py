import telebot
import random
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
import os
import sys
import time
import json

API_TOKEN = os.environ.get('API_TOKEN')
BACKUP_CHAT_ID = os.environ.get('BACKUP_CHAT_ID')

bot = telebot.TeleBot(API_TOKEN)

DB_FILE = "database.json"
user_data = {}

def load_data():
    global user_data
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                user_data = {int(k): v for k, v in raw_data.items()}
                print("БД успешно загружена локально.")
        except Exception as e:
            print(f"Ошибка загрузки БД: {e}")
            user_data = {}
    else:
        user_data = {}

def save_data():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(user_data, f, ensure_ascii=False, indent=4)
        
        if BACKUP_CHAT_ID:
            with open(DB_FILE, "rb") as f:
                bot.send_document(
                    BACKUP_CHAT_ID, 
                    f, 
                    caption=f"📦 Авто-бэкап базы данных\n🕒 Время: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
    except Exception as e:
        print(f"Ошибка сохранения/бэкапа БД: {e}")

load_data()

waiting_users = []
active_chats = {}
user_to_group = {}
groups = {}

waiting_for_name = set()
waiting_for_emoji = set()
waiting_for_photo = set()

def init_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "name": "Аноним",
            "referrals": 0,
            "invited_by": None,
            "emoji": "💬",
            "photo": None,
            "referred_users": []
        }
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

def get_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('❌ Отмена')
    return markup

def get_profile_keyboard(user_id):
    init_user(user_id)
    refs = user_data[user_id]["referrals"]
    markup = InlineKeyboardMarkup()
    
    markup.add(
        InlineKeyboardButton("🔍 Начать поиск", callback_data="action_search"),
        InlineKeyboardButton("👥 Групповой чат", callback_data="action_group")
    )
    markup.add(InlineKeyboardButton("✏️ Изменить имя", callback_data="change_name"))
    
    # Кнопка поделиться профилем доступна всегда (активируется в чатах)
    markup.add(InlineKeyboardButton("🔗 Поделиться профилем в чат", callback_data="share_profile"))
    
    # Эмодзи от 5 человек
    if refs >= 5:
        markup.add(InlineKeyboardButton("⚙️ Изменить эмодзи", callback_data="change_emoji"))
    
    # Картинка от 10 человек
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
    init_user(user_id)
    
    waiting_for_name.discard(user_id)
    waiting_for_emoji.discard(user_id)
    waiting_for_photo.discard(user_id)
    
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

    bot.send_message(user_id, "👋 Привет! Твой профиль и управление чатами ниже:", reply_markup=ReplyKeyboardRemove())
    show_profile_card(user_id, user_id)

@bot.message_handler(commands=['profile'])
def profile_command(message):
    user_id = message.chat.id
    init_user(user_id)
    show_profile_card(user_id, user_id)

@bot.message_handler(commands=['name'])
def ask_name_command(message):
    user_id = message.chat.id
    if user_id in active_chats or user_id in user_to_group or user_id in waiting_users:
        return bot.send_message(user_id, "⚠️ Нельзя менять имя во время поиска или чата.")
    waiting_for_name.add(user_id)
    bot.send_message(user_id, "✍️ Напиши имя, которое будет отображаться в чатах:", reply_markup=get_cancel_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "action_search")
def callback_search(call):
    user_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    process_search(user_id)

@bot.callback_query_handler(func=lambda call: call.data == "action_group")
def callback_group(call):
    user_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    process_group(user_id)

@bot.callback_query_handler(func=lambda call: call.data == "share_profile")
def callback_share_profile(call):
    user_id = call.message.chat.id
    
    if user_id in active_chats:
        target = active_chats[user_id]
        bot.answer_callback_query(call.id, "✅ Профиль отправлен собеседнику!")
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

@bot.message_handler(commands=['chat'])
def chat_command(message):
    process_search(message.chat.id)

@bot.message_handler(commands=['group'])
def group_command(message):
    process_group(message.chat.id)

def process_search(user_id):
    if user_id in active_chats or user_id in user_to_group:
        return bot.send_message(user_id, "⚠️ Вы уже в чате.", reply_markup=get_cancel_keyboard())
    if user_id in waiting_users:
        return bot.send_message(user_id, "🔍 Вы уже в поиске.", reply_markup=get_cancel_keyboard())
    
    waiting_for_name.discard(user_id)
    waiting_for_emoji.discard(user_id)
    waiting_for_photo.discard(user_id)
    
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

@bot.callback_query_handler(func=lambda call: call.data == "change_name")
def ask_name_callback(call):
    user_id = call.message.chat.id
    if user_id in active_chats or user_id in user_to_group or user_id in waiting_users:
        bot.answer_callback_query(call.id, "⚠️ Нельзя менять имя во время поиска или чата.")
        return
    waiting_for_name.add(user_id)
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, "✍️ Напиши имя, которое будет отображаться в групповых чатах:", reply_markup=get_cancel_keyboard())

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
    
    if user_id in waiting_for_name or user_id in waiting_for_emoji or user_id in waiting_for_photo:
        waiting_for_name.discard(user_id)
        waiting_for_emoji.discard(user_id)
        waiting_for_photo.discard(user_id)
        bot.send_message(user_id, "🚫 Изменение профиля отменено.", reply_markup=ReplyKeyboardRemove())
        show_profile_card(user_id, user_id)
        return

    if user_id in waiting_users:
        waiting_users.remove(user_id)
        bot.send_message(user_id, "🚫 Поиск отменен.", reply_markup=ReplyKeyboardRemove())
        show_profile_card(user_id, user_id)
    elif user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        bot.send_message(user_id, "🚫 Диалог завершен.", reply_markup=ReplyKeyboardRemove())
        bot.send_message(partner_id, "🚫 Собеседник отключился.", reply_markup=ReplyKeyboardRemove())
        send_rating(user_id); send_rating(partner_id)
        show_profile_card(user_id, user_id)
        show_profile_card(partner_id, partner_id)
    elif user_id in user_to_group:
        gid = user_to_group.pop(user_id)
        groups[gid].remove(user_id)
        for member in groups[gid]: bot.send_message(member, f"👋 {get_display_name(user_id)} покинул группу.")
        if not groups[gid]: del groups[gid]
        bot.send_message(user_id, "🚫 Вы покинули группу.", reply_markup=ReplyKeyboardRemove())
        show_profile_card(user_id, user_id)
    else:
        bot.send_message(user_id, "⚠️ Вы не находитесь в активном процессе.", reply_markup=ReplyKeyboardRemove())

@bot.callback_query_handler(func=lambda call: call.data.startswith('rate_'))
def handle_rating(call):
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Спасибо за отзыв!")
    bot.answer_callback_query(call.id, "Спасибо за ваш отзыв!")

@bot.message_handler(content_types=['text', 'photo', 'sticker', 'video', 'document', 'voice'])
def chat(message):
    user_id = message.chat.id
    init_user(user_id)
    name = get_display_name(user_id)
    user_emoji = get_user_emoji(user_id)
    
    if user_id in waiting_for_name:
        if message.content_type == 'text':
            user_data[user_id]["name"] = message.text
            save_data()
            waiting_for_name.discard(user_id)
            bot.send_message(user_id, f"✅ Имя сохранено: {message.text}!", reply_markup=ReplyKeyboardRemove())
            show_profile_card(user_id, user_id)
        else:
            bot.send_message(user_id, "⚠️ Пожалуйста, введите имя текстом.")
        return

    if user_id in waiting_for_emoji:
        if message.content_type == 'text' and len(message.text.strip()) <= 4:
            user_data[user_id]["emoji"] = message.text.strip()
            save_data()
            waiting_for_emoji.discard(user_id)
            bot.send_message(user_id, f"✅ Эмодзи изменен на: {message.text.strip()}", reply_markup=ReplyKeyboardRemove())
            show_profile_card(user_id, user_id)
        else:
            bot.send_message(user_id, "⚠️ Пожалуйста, отправьте один корректный эмодзи.")
        return

    if user_id in waiting_for_photo:
        if message.content_type == 'photo':
            photo_id = message.photo[-1].file_id
            user_data[user_id]["photo"] = photo_id
            save_data()
            waiting_for_photo.discard(user_id)
            bot.send_message(user_id, "✅ Картинка профиля успешно установлена!", reply_markup=ReplyKeyboardRemove())
            show_profile_card(user_id, user_id)
        else:
            bot.send_message(user_id, "⚠️ Пожалуйста, отправьте изображение как фото.")
        return

    if user_id in active_chats:
        target = active_chats[user_id]
        if message.content_type == 'text': 
            bot.send_message(target, message.text)
        else: 
            bot.copy_message(target, user_id, message.message_id)
            
    elif user_id in user_to_group:
        gid = user_to_group[user_id]
        share_markup = InlineKeyboardMarkup()
        share_markup.add(InlineKeyboardButton("👤 Посмотреть профиль", callback_data=f"view_{user_id}"))
        
        for member in groups.get(gid, []):
            if member != user_id:
                if message.content_type == 'text': 
                    bot.send_message(member, f"{user_emoji} {name}: {message.text}", reply_markup=share_markup)
                else: 
                    bot.send_message(member, f"👤 {name}:", reply_markup=share_markup)
                    bot.copy_message(member, user_id, message.message_id)

if __name__ == '__main__':
    print("Бот запущен...")
    try:
        bot.polling(none_stop=True, interval=0, timeout=0)
    except Exception as e:
        print(f"Критическая ошибка: {e}. Перезагрузка...")
        time.sleep(3)
        os.execv(sys.executable, ['python'] + sys.argv)

