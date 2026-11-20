import os
import uuid
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

# Временное хранение заказов
orders_db = {}


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
        "🌍 Регион: демонстрационный\n"
        "⚠️ Тестовый товар. Оплата не подключена.",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda c: c.data == "buy_steam")
def buy(call):
    bot.answer_callback_query(call.id)

    order_id = uuid.uuid4().hex[:8].upper()

    orders_db[order_id] = {
        "user_id": call.from_user.id,
        "chat_id": call.message.chat.id,
        "product": "Steam Gift Card",
        "price": "10 USDT",
        "status": "Ожидает решения"
    }

    username = call.from_user.username or "без username"

    bot.send_message(
        call.message.chat.id,
        f"✅ Заказ №{order_id} создан!\n\n"
        "🎁 Steam Gift Card\n"
        "💰 10 USDT\n"
        "📌 Статус: ожидает подтверждения.\n"
        "⚠️ Это демонстрационный заказ."
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(
            "✅ Подтвердить",
            callback_data=f"approve:{order_id}"
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            "❌ Отклонить",
            callback_data=f"reject:{order_id}"
        )
    )

    bot.send_message(
        ADMIN_ID,
        f"🆕 НОВЫЙ ЗАКАЗ №{order_id}\n\n"
        f"👤 Покупатель: @{username}\n"
        f"🆔 ID: {call.from_user.id}\n"
        "🎁 Steam Gift Card\n"
        "💰 10 USDT\n"
        "📌 Ожидает решения.",
        reply_markup=keyboard
    )


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("approve:")
    or c.data.startswith("reject:")
)
def manage_order(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    action, order_id = call.data.split(":", 1)

    if order_id not in orders_db:
        bot.answer_callback_query(
            call.id,
            "Заказ не найден."
        )
        return

    order = orders_db[order_id]

    if order["status"] != "Ожидает решения":
        bot.answer_callback_query(
            call.id,
            "Этот заказ уже обработан."
        )
        return

    if action == "approve":
        order["status"] = "Подтверждён"
        text = f"✅ Заказ №{order_id} подтверждён!"
    else:
        order["status"] = "Отклонён"
        text = f"❌ Заказ №{order_id} отклонён."

    bot.answer_callback_query(call.id, "Статус изменён.")

    bot.send_message(
        order["chat_id"],
        f"📦 Обновление заказа №{order_id}\n\n{text}"
    )

    bot.edit_message_text(
        f"Заказ №{order_id}\n\n{text}",
        call.message.chat.id,
        call.message.message_id
    )


@bot.message_handler(commands=['orders'])
def show_orders(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Нет доступа.")
        return

    if not orders_db:
        bot.send_message(message.chat.id, "📋 Заказов пока нет.")
        return

    text = "📋 СПИСОК ЗАКАЗОВ\n\n"

    for order_id, order in orders_db.items():
        text += (
            f"№{order_id}\n"
            f"Товар: {order['product']}\n"
            f"Цена: {order['price']}\n"
            f"Статус: {order['status']}\n\n"
        )

    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
def my_orders(message):
    user_orders = [
        (order_id, order)
        for order_id, order in orders_db.items()
        if order["user_id"] == message.from_user.id
    ]

    if not user_orders:
        bot.send_message(message.chat.id, "📦 У вас пока нет заказов.")
        return

    text = "📦 ВАШИ ЗАКАЗЫ\n\n"

    for order_id, order in user_orders:
        text += (
            f"№{order_id}\n"
            f"{order['product']}\n"
            f"Статус: {order['status']}\n\n"
        )

    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "💬 Поддержка")
def support(message):
    bot.send_message(
        message.chat.id,
        "💬 Напишите свой вопрос."
    )


bot.infinity_polling()
