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

@bot.message_handler(func=lambda message: mes
