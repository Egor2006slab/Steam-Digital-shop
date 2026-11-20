import os
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    menu = ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add(KeyboardButton("🛒 Каталог"))
    menu.add(KeyboardButton("📦 Мои заказы"))
    menu.add(KeyboardButton("💬 Поддержка"))

    bot.send_message(
        message.chat.id,
        "🛍 Добро пожаловать в Steam Digital Shop!\n\n"
        "Выберите нужный раздел:",
        reply_markup=menu
    )

@bot.message_handler(func=lambda message: message.text == "🛒 Каталог")
def catalog(message):
    bot.send_message(
        message.chat.id,
        "🛒 КАТАЛОГ\n\n"
        "1. Цифровые товары\n"
        "2. Игровые ключи\n\n"
        "Каталог скоро пополнится!"
    )

@bot.message_handler(func=lambda message: message.text == "📦 Мои заказы")
def orders(message):
    bot.send_message(
        message.chat.id,
        "📦 У вас пока нет заказов."
    )

@bot.message_handler(func=lambda message: message.text == "💬 Поддержка")
def support(message):
    bot.send_message(
        message.chat.id,
        "💬 Напишите свой вопрос. Поддержка скоро ответит!"
    )

bot.infinity_polling()
