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

# Временное хранение
orders_db = {}

# Покупатели, у которых открыт диалог
support_users = set()

# Покупатель, которому сейчас отвечает администратор
active_admin_chat = None


# =========================
# ГЛАВНОЕ МЕНЮ
# =========================

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


# =========================
# КАТАЛОГ
# =========================

def catalog_keyboard():
    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            "🎁 Подарочные карты",
            callback_data="cat_gifts"
        )
    )

    keyboard.add(
        InlineKeyboardButton(
            "🎮 Ключи игр",
            callback_data="cat_games"
        )
    )

    keyboard.add(
        InlineKeyboardButton(
            "⭐ Подписки",
            callback_data="cat_subs"
        )
    )

    return keyboard


@bot.message_handler(func=lambda m: m.text == "🛒 Каталог")
def catalog(message):
    bot.send_message(
        message.chat.id,
        "🛍 КАТАЛОГ МАГАЗИНА\n\nВыберите категорию:",
        reply_markup=catalog_keyboard()
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def show_category(call):
    bot.answer_callback_query(call.id)

    keyboard = InlineKeyboardMarkup()

    if call.data == "cat_gifts":
        keyboard.add(
            InlineKeyboardButton(
                "🎁 Steam Gift Card — 10 USDT",
                callback_data="buy_steam"
            )
        )

        text = (
            "🎁 ПОДАРОЧНЫЕ КАРТЫ\n\n"
            "Steam Gift Card\n"
            "Цена: 10 USDT\n"
            "Регион: демонстрационный\n\n"
            "⚠️ Тестовый товар. Оплата не подключена."
        )

    elif call.data == "cat_games":
        text = "🎮 КЛЮЧИ ИГР\n\nПока товаров нет."

    else:
        text = "⭐ ПОДПИСКИ\n\nПока товаров нет."

    keyboard.add(
        InlineKeyboardButton(
            "⬅️ Назад",
            callback_data="back_catalog"
        )
    )

    bot.send_message(
        call.message.chat.id,
        text,
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda c: c.data == "back_catalog")
def back_catalog(call):
    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        "🛍 ВЫБЕРИТЕ КАТЕГОРИЮ:",
        reply_markup=catalog_keyboard()
    )


# =========================
# СОЗДАНИЕ ЗАКАЗА
# =========================

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
        "💰 Цена: 10 USDT\n"
        "📌 Ожидает подтверждения.\n\n"
        "⚠️ Демонстрационный заказ. Оплата не подключена."
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
        "💰 10 USDT",
        reply_markup=keyboard
    )


# =========================
# УПРАВЛЕНИЕ ЗАКАЗАМИ
# =========================

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
        bot.answer_callback_query(call.id, "Заказ не найден.")
        return

    order = orders_db[order_id]

    if order["status"] != "Ожидает решения":
        bot.answer_callback_query(call.id, "Заказ уже обработан.")
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
        f"📦 ОБНОВЛЕНИЕ ЗАКАЗА\n\n{text}"
    )

    bot.edit_message_text(
        f"📋 ЗАКАЗ №{order_id}\n\n{text}",
        call.message.chat.id,
        call.message.message_id
    )


# =========================
# СПИСОК ЗАКАЗОВ
# =========================

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


# =========================
# МОИ ЗАКАЗЫ
# =========================

@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
def my_orders(message):

    user_orders = [
        (order_id, order)
        for order_id, order in orders_db.items()
        if order["user_id"] == message.from_user.id
    ]

    if not user_orders:
        bot.send_message(
            message.chat.id,
            "📦 У вас пока нет заказов."
        )
        return

    text = "📦 ВАШИ ЗАКАЗЫ\n\n"

    for order_id, order in user_orders:
        text += (
            f"№{order_id}\n"
            f"{order['product']}\n"
            f"Цена: {order['price']}\n"
            f"Статус: {order['status']}\n\n"
        )

    bot.send_message(message.chat.id, text)


# =========================
# НАЧАЛО ПОДДЕРЖКИ
# =========================

@bot.message_handler(func=lambda m: m.text == "💬 Поддержка")
def support(message):

    support_users.add(message.from_user.id)

    bot.send_message(
        message.chat.id,
        "💬 ПОДДЕРЖКА\n\n"
        "Напишите сообщение. Администратор скоро ответит.\n"
        "Можете отправлять несколько сообщений подряд."
    )


# =========================
# КНОПКИ АДМИНИСТРАТОРА
# =========================

@bot.callback_query_handler(
    func=lambda c: c.data.startswith("support_reply:")
)
def support_reply(call):

    global active_admin_chat

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    user_id = int(call.data.split(":", 1)[1])

    if user_id not in support_users:
        bot.answer_callback_query(
            call.id,
            "Диалог уже закрыт."
        )
        return

    active_admin_chat = user_id

    bot.answer_callback_query(
        call.id,
        "Вы можете отвечать."
    )

    bot.send_message(
        ADMIN_ID,
        f"✍️ Вы отвечаете покупателю {user_id}.\n\n"
        "Отправьте сообщение."
    )


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("support_close:")
)
def support_close(call):

    global active_admin_chat

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    user_id = int(call.data.split(":", 1)[1])

    support_users.discard(user_id)

    if active_admin_chat == user_id:
        active_admin_chat = None

    bot.answer_callback_query(
        call.id,
        "Диалог завершён."
    )

    bot.send_message(
        user_id,
        "🔒 Диалог с поддержкой завершён.\n"
        "Если понадобится помощь, нажмите «💬 Поддержка»."
    )

    bot.send_message(
        ADMIN_ID,
        f"✅ Диалог с покупателем {user_id} завершён."
    )


# =========================
# ОБРАБОТКА ВСЕХ СООБЩЕНИЙ
# =========================

@bot.message_handler(content_types=['text'])
def handle_text(message):

    global active_admin_chat

    user_id = message.from_user.id
    text = message.text

    # Администратор пишет покупателю
    if user_id == ADMIN_ID and active_admin_chat is not None:

        target_id = active_admin_chat

        if target_id not in support_users:
            active_admin_chat = None
            bot.send_message(
                ADMIN_ID,
                "Диалог уже закрыт."
            )
            return

        try:
            bot.send_message(
                target_id,
                "💬 ПОДДЕРЖКА:\n\n" + text
            )

            bot.send_message(
                ADMIN_ID,
                "✅ Сообщение отправлено."
            )

        except Exception:
            bot.send_message(
                ADMIN_ID,
                "❌ Не удалось отправить сообщение."
            )

        return

    # Покупатель пишет поддержке
    if user_id in support_users:

        username = message.from_user.username or "без username"

        keyboard = InlineKeyboardMarkup()

        keyboard.add(
            InlineKeyboardButton(
                "✍️ Ответить",
                callback_data=f"support_reply:{user_id}"
            )
        )

        keyboard.add(
            InlineKeyboardButton(
                "🔒 Завершить диалог",
                callback_data=f"support_close:{user_id}"
            )
        )

        bot.send_message(
            ADMIN_ID,
            f"💬 СООБЩЕНИЕ ОТ ПОКУПАТЕЛЯ\n\n"
            f"👤 @{username}\n"
            f"🆔 ID: {user_id}\n\n"
            f"Сообщение:\n{text}",
            reply_markup=keyboard
        )

        bot.send_message(
            message.chat.id,
            "✅ Сообщение передано администратору."
        )

        return

    bot.send_message(
        message.chat.id,
        "Выберите раздел в меню."
    )


# =========================
# ЗАПУСК
# =========================

bot.infinity_polling()
