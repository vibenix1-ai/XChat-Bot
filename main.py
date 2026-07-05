import telebot
import random
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import sys
import time

API_TOKEN = os.environ.get('API_TOKEN')
bot = telebot.TeleBot(API_TOKEN)
PORT = int(os.environ.get('PORT', 8080))

# Данные
waiting_users = []
active_chats = {}
user_to_group = {}
groups = {}
user_names = {}
# Состояние ожидания ввода имени
waiting_for_name = set()

def get_display_name(user_id):
    return user_names.get(user_id, "Аноним")

def send_rating(chat_id):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("👍🏻", callback_data="rate_like"),
        InlineKeyboardButton("Пропуск", callback_data="rate_skip"),
        InlineKeyboardButton("👎🏻", callback_data="rate_dislike")
    )
    bot.send_message(chat_id, "Оцените ваш диалог с собеседником 👇🏻", reply_markup=markup)

# Функции генерации клавиатур для исключения дублирования кода
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('🔍 Начать поиск', '👥 Групповой чат')
    return markup

def get_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('❌ Отмена')
    return markup

def get_name_inline_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("👤 Имя", callback_data="change_name"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    # Сбрасываем флаг ввода имени при перезапуске, если он был
    waiting_for_name.discard(user_id)
    
    bot.send_message(
        user_id, 
        "👋 Привет! Выбери действие:", 
        reply_markup=get_main_keyboard()
    )
    # Отправляем инлайн-кнопку для имени под основным сообщением
    bot.send_message(
        user_id,
        "Вы можете изменить своё имя для чатов 👇",
        reply_markup=get_name_inline_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == "change_name")
def ask_name_callback(call):
    user_id = call.message.chat.id
    
    if user_id in active_chats or user_id in user_to_group or user_id in waiting_users:
        bot.answer_callback_query(call.id, "⚠️ Нельзя менять имя во время поиска или чата.")
        return

    waiting_for_name.add(user_id)
    bot.answer_callback_query(call.id)
    
    # Меняем клавиатуру на "Отмена" на случай, если пользователь передумает вводить имя
    bot.send_message(
        user_id, 
        "✍️ Напиши имя, которое будет отображаться в чатах:", 
        reply_markup=get_cancel_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == '🔍 Начать поиск')
def search(message):
    user_id = message.chat.id
    if user_id in active_chats or user_id in user_to_group:
        return bot.send_message(user_id, "⚠️ Вы уже в чате.", reply_markup=get_cancel_keyboard())
    if user_id in waiting_users:
        return bot.send_message(user_id, "🔍 Вы уже в поиске.", reply_markup=get_cancel_keyboard())
    
    waiting_for_name.discard(user_id) # На всякий случай отменяем ввод имени
    
    if waiting_users:
        partner_id = waiting_users.pop(0)
        active_chats[user_id], active_chats[partner_id] = partner_id, user_id
        bot.send_message(user_id, "✅ Собеседник найден!", reply_markup=get_cancel_keyboard())
        bot.send_message(partner_id, "✅ Собеседник найден!", reply_markup=get_cancel_keyboard())
    else:
        waiting_users.append(user_id)
        bot.send_message(user_id, "🔍 Поиск начат... Ожидайте.", reply_markup=get_cancel_keyboard())

@bot.message_handler(func=lambda message: message.text == '👥 Групповой чат')
def search_group(message):
    user_id = message.chat.id
    name = get_display_name(user_id)
    if user_id in user_to_group or user_id in active_chats:
        return bot.send_message(user_id, "⚠️ Вы уже в чате.", reply_markup=get_cancel_keyboard())
    
    waiting_for_name.discard(user_id) # На всякий случай отменяем ввод имени
    
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

@bot.message_handler(func=lambda message: message.text == '❌ Отмена')
def stop(message):
    user_id = message.chat.id
    
    # 1. Если отменяется ввод имени
    if user_id in waiting_for_name:
        waiting_for_name.discard(user_id)
        bot.send_message(user_id, "🚫 Ввод имени отменен.", reply_markup=get_main_keyboard())
        return

    # 2. Если отменяется поиск или активные чаты
    if user_id in waiting_users:
        waiting_users.remove(user_id)
        bot.send_message(user_id, "🚫 Поиск отменен.", reply_markup=get_main_keyboard())
    elif user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        bot.send_message(user_id, "🚫 Диалог завершен.", reply_markup=get_main_keyboard())
        bot.send_message(partner_id, "🚫 Собеседник отключился.", reply_markup=get_main_keyboard())
        send_rating(user_id); send_rating(partner_id)
    elif user_id in user_to_group:
        gid = user_to_group.pop(user_id)
        groups[gid].remove(user_id)
        for member in groups[gid]: bot.send_message(member, f"👋 {get_display_name(user_id)} покинул группу.")
        if not groups[gid]: del groups[gid]
        bot.send_message(user_id, "🚫 Вы покинули группу.", reply_markup=get_main_keyboard())
    else:
        bot.send_message(user_id, "⚠️ Вы не находитесь в активном процессе.", reply_markup=get_main_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith('rate_'))
def handle_rating(call):
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Спасибо за отзыв!")
    bot.answer_callback_query(call.id, "Спасибо за ваш отзыв!")

@bot.message_handler(content_types=['text', 'photo', 'sticker', 'video', 'document', 'voice'])
def chat(message):
    user_id = message.chat.id
    name = get_display_name(user_id)
    
    # Обработка перехваченного ввода имени
    if user_id in waiting_for_name:
        if message.content_type == 'text':
            user_names[user_id] = message.text
            waiting_for_name.discard(user_id)
            bot.send_message(user_id, f"✅ Имя сохранено: {message.text}!", reply_markup=get_main_keyboard())
        else:
            bot.send_message(user_id, "⚠️ Пожалуйста, введите имя текстом.")
        return

    # Пересылка сообщений в чатах
    if user_id in active_chats:
        target = active_chats[user_id]
        if message.content_type == 'text': bot.send_message(target, f"💬 {name}: {message.text}")
        else: bot.send_message(target, f"👤 {name}:"); bot.copy_message(target, user_id, message.message_id)
    elif user_id in user_to_group:
        gid = user_to_group[user_id]
        for member in groups.get(gid, []):
            if member != user_id:
                if message.content_type == 'text': bot.send_message(member, f"💬 {name}: {message.text}")
                else: bot.send_message(member, f"👤 {name}:"); bot.copy_message(member, user_id, message.message_id)

if __name__ == '__main__':
    print("Бот запущен...")
    try:
        bot.polling(none_stop=True, interval=0, timeout=0)
    except Exception as e:
        print(f"Критическая ошибка: {e}. Перезагрузка...")
        time.sleep(3)
        os.execv(sys.executable, ['python'] + sys.argv)
