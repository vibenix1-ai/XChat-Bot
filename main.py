import telebot
import random
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import sys
import time

API_TOKEN = os.environ.get('API_TOKEN')
bot = telebot.TeleBot(API_TOKEN)

# Данные
waiting_users = []
active_chats = {}
user_to_group = {}
groups = {}
user_names = {}

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

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('🔍 Начать поиск', '👥 Групповой чат')
    markup.add('👤 Имя', '❌ Отмена')
    markup.add('⭐ Пожертвовать')
    bot.send_message(message.chat.id, "👋 Привет! Выбери действие:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == '👤 Имя')
def ask_name(message):
    msg = bot.send_message(message.chat.id, "✍️ Напиши имя, которое будет отображаться в чатах:")
    bot.register_next_step_handler(msg, lambda m: [user_names.update({m.chat.id: m.text}), bot.send_message(m.chat.id, "✅ Имя сохранено!")])

@bot.message_handler(func=lambda message: message.text == '🔍 Начать поиск')
def search(message):
    user_id = message.chat.id
    if user_id in active_chats or user_id in user_to_group:
        return bot.send_message(user_id, "⚠️ Вы уже в чате.")
    if user_id in waiting_users:
        return bot.send_message(user_id, "🔍 Вы уже в поиске.")
    
    if waiting_users:
        partner_id = waiting_users.pop(0)
        active_chats[user_id], active_chats[partner_id] = partner_id, user_id
        bot.send_message(user_id, "✅ Собеседник найден!")
        bot.send_message(partner_id, "✅ Собеседник найден!")
    else:
        waiting_users.append(user_id)
        bot.send_message(user_id, "🔍 Поиск начат... Ожидайте.")

@bot.message_handler(func=lambda message: message.text == '👥 Групповой чат')
def search_group(message):
    user_id = message.chat.id
    name = get_display_name(user_id)
    if user_id in user_to_group or user_id in active_chats:
        return bot.send_message(user_id, "⚠️ Вы уже в чате.")
    
    found_gid = next((gid for gid, m in groups.items() if len(m) < 5), None)
    if found_gid:
        groups[found_gid].append(user_id)
        user_to_group[user_id] = found_gid
        for member in groups[found_gid]:
            if member != user_id: bot.send_message(member, f"👤 {name} вошел в группу!")
        bot.send_message(user_id, f"✅ Вы в группе. Участников: {len(groups[found_gid])}")
    else:
        new_gid = random.randint(10000, 99999)
        groups[new_gid] = [user_id]
        user_to_group[user_id] = new_gid
        bot.send_message(user_id, "✨ Создана новая группа. Ожидаем участников...")

@bot.message_handler(func=lambda message: message.text == '❌ Отмена')
def stop(message):
    user_id = message.chat.id
    if user_id in waiting_users:
        waiting_users.remove(user_id)
        bot.send_message(user_id, "🚫 Поиск отменен.")
    elif user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        bot.send_message(user_id, "🚫 Диалог завершен."); bot.send_message(partner_id, "🚫 Собеседник отключился.")
        send_rating(user_id); send_rating(partner_id)
    elif user_id in user_to_group:
        gid = user_to_group.pop(user_id)
        groups[gid].remove(user_id)
        for member in groups[gid]: bot.send_message(member, f"👋 {get_display_name(user_id)} покинул группу.")
        if not groups[gid]: del groups[gid]
        bot.send_message(user_id, "🚫 Вы покинули группу.")
    else:
        bot.send_message(user_id, "⚠️ Вы не в поиске.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('rate_'))
def handle_rating(call):
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Спасибо за отзыв!")
    bot.answer_callback_query(call.id, "Спасибо за ваш отзыв!")

@bot.message_handler(content_types=['text', 'photo', 'sticker', 'video', 'document', 'voice'])
def chat(message):
    user_id = message.chat.id
    name = get_display_name(user_id)
    
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

# Обработка нажатия на кнопку "Пожертвовать"
@bot.message_handler(func=lambda message: message.text == '⭐ Пожертвовать')
def donate_start(message):
    msg = bot.send_message(message.chat.id, "✍️ Введите количество звёзд (⭐), которое вы хотите отправить:")
    bot.register_next_step_handler(msg, process_donate_amount)

# Получение количества звезд и создание инлайн-кнопки
def process_donate_amount(message):
    amount = message.text.strip()
    
    # Простая проверка, что введено число
    if not amount.isdigit():
        msg = bot.send_message(message.chat.id, "⚠️ Пожалуйста, введите корректное число звёзд:")
        bot.register_next_step_handler(msg, process_donate_amount)
        return

    # Создаем инлайн-кнопку для подтверждения отправки
    markup = InlineKeyboardMarkup()
    # Сохраняем сумму прямо в callback_data, чтобы передать в следующий шаг
    markup.add(InlineKeyboardButton("Отправить", callback_data=f"send_stars_{amount}"))
    
    bot.send_message(message.chat.id, f"Запрос на {amount}⭐", reply_markup=markup)

# Обработка нажатия на инлайн-кнопку "Отправить"
@bot.callback_query_handler(func=lambda call: call.data.startswith('send_stars_'))
def handle_send_stars(call):
    # Достаем количество звезд из callback_data
    amount = call.data.split('_')[2]
    user_id = call.message.chat.id
    name = get_display_name(user_id)
    username = f"@{call.from_user.username}" if call.from_user.username else "Нет юзернейма"

    # Текст уведомления для администратора
    admin_message = (
        f"💰 Пользователь {name} (ID: {user_id}, Username: {username})\n"
        f"хочет отправить {amount}⭐!"
    )

    try:
        # Пытаемся отправить сообщение администратору (замени на реальный ID, если имя @vibenix не сработает напрямую)
        # В Telegram API для send_message нужен ID чата. Если бот знает @vibenix, можно указать юзернейм:
        bot.send_message("@vibenix", admin_message)
        
        # Обновляем текст у пользователя
        bot.edit_message_text(
            chat_id=user_id, 
            message_id=call.message.message_id, 
            text=f"✅ Запрос на {amount}⭐ успешно отправлен пользователю @vibenix!"
        )
    except Exception as e:
        # Если бот еще не общался с @vibenix, вылетит ошибка API
        bot.edit_message_text(
            chat_id=user_id, 
            message_id=call.message.message_id, 
            text="❌ Ошибка: Бот не может отправить запрос @vibenix. Администратор должен сначала запустить бота."
        )
    
    bot.answer_callback_query(call.id)

if __name__ == '__main__':
    print("Бот запущен...")
    try:
        bot.polling(none_stop=True, interval=0, timeout=0)
    except Exception as e:
        print(f"Критическая ошибка: {e}. Перезагрузка...")
        time.sleep(3)
        # Это "реальный" перезапуск процесса
        os.execv(sys.executable, ['python'] + sys.argv)
