import os
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

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
        "🛍 Добро пожаловать в Steam Digital Shop!",
        reply_markup=menu
    )

@bot.message_handler(func=lambda message: message.text == "🛒 Каталог")
def catalog(message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(
        "🎁 Купить — 10 USDT",
        callback_data="buy_steam"
    ))

    bot.send_message(
        message.chat.id,
        "🎮 STEAM GIFT CARD\n\n"
        "💰 Цена: 10 USDT\n"
        "🌍 Регион: Global (демо)\n\n"
        "⚠️ Демонстрационный товар. Оплата пока не подключена.",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "buy_steam")
def buy(call):
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "🎁 Вы выбрали Steam Gift Card за 10 USDT.\n\n"
        "Это демонстрационный заказ. Оплата пока не подключена."
    )

@bot.message_handler(func=lambda message: message.text == "📦 Мои заказы")
def orders(message):
    bot.send_message(message.chat.id, "📦 У вас пока нет заказов.")

@bot.message_handler(func=lambda message: message.text == "💬 Поддержка")
def support(message):
    bot.send_message(message.chat.id, "💬 Напишите свой вопрос.")

bot.infinity_polling()
