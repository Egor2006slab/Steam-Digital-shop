import os
import secrets
import telebot
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

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


@bot.message_handler(func=lambda m: m.text == "🛒 Каталог")
def catalog(message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(
            "🎁 Купить — 10 USDT",
            callback_data="buy_steam"
        )
    )

    bot.send_message(
        message.chat.id,
        "🎮 STEAM GIFT CARD\n\n"
        "💰 Цена: 10 USDT\n"
        "🌍 Регион: Global (демо)\n"
        "⚠️ Тестовый товар.",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda c: c.data == "buy_steam")
def buy(call):
    bot.answer_callback_query(call.id)

    order_id = secrets.randbelow(900000) + 100000
    username = call.from_user.username or "без username"

    bot.send_message(
        call.message.chat.id,
        f"✅ Заказ №{order_id} создан!\n\n"
        "🎁 Steam Gift Card\n"
        "💰 10 USDT\n\n"
        "Это демонстрационный заказ. Оплата пока не подключена."
    )

    bot.send_message(
        ADMIN_ID,
        f"🆕 НОВЫЙ ЗАКАЗ №{order_id}\n\n"
        f"👤 Покупатель: @{username}\n"
        f"🆔 Telegram ID: {call.from_user.id}\n"
        "🎁 Товар: Steam Gift Card\n"
        "💰 Сумма: 10 USDT\n"
        "📌 Статус: тестовый заказ"
    )


@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
def orders(message):
    bot.send_message(
        message.chat.id,
        "📦 История заказов пока находится в разработке."
    )


@bot.message_handler(func=lambda m: m.text == "💬 Поддержка")
def support(message):
    bot.send_message(
        message.chat.id,
        "💬 Напишите свой вопрос."
    )


bot.infinity_polling()
