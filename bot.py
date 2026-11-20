import os
import uuid
import telebot

from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# =========================
# НАСТРОЙКИ
# =========================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = telebot.TeleBot(TOKEN)

# Временные данные
orders_db = {}
users_db = {}
support_users = set()

active_admin_chat = None
waiting_price = False

PRODUCT_PRICE = 10.0


# =========================
# ГЛАВНОЕ МЕНЮ
# =========================

@bot.message_handler(commands=['start'])
def start(message):

    user = message.from_user

    users_db[user.id] = {
        "username": user.username or "без username",
        "first_name": user.first_name or "Покупатель"
    }

    menu = ReplyKeyboardMarkup(resize_keyboard=True)

    menu.add(KeyboardButton("🛒 Каталог"))
    menu.add(KeyboardButton("📦 Мои заказы"))
    menu.add(KeyboardButton("💬 Поддержка"))

    bot.send_message(
        message.chat.id,
        "🛍 Добро пожаловать в Steam Digital Shop!\n\n"
        "Выберите раздел:",
        reply_markup=menu
    )


# =========================
# АДМИН-ПАНЕЛЬ
# =========================

def admin_keyboard():

    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            "📋 Заказы",
            callback_data="admin_orders"
        )
    )

    keyboard.add(
        InlineKeyboardButton(
            "👥 Покупатели",
            callback_data="admin_users"
        )
    )

    keyboard.add(
        InlineKeyboardButton(
            "💬 Диалоги",
            callback_data="admin_chats"
        )
    )

    keyboard.add(
        InlineKeyboardButton(
            "📊 Статистика",
            callback_data="admin_stats"
        )
    )

    keyboard.add(
        InlineKeyboardButton(
            "⚙️ Товары и цены",
            callback_data="admin_products"
        )
    )

    return keyboard


@bot.message_handler(commands=['admin'])
def admin_panel(message):

    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Нет доступа.")
        return

    bot.send_message(
        message.chat.id,
        "⚙️ АДМИНИСТРАТИВНАЯ ПАНЕЛЬ\n\n"
        "Выберите нужный раздел:",
        reply_markup=admin_keyboard()
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
                f"🎁 Steam Gift Card — {PRODUCT_PRICE:g} USDT",
                callback_data="buy_steam"
            )
        )

        text = (
            "🎁 ПОДАРОЧНЫЕ КАРТЫ\n\n"
            f"Steam Gift Card\n"
            f"Цена: {PRODUCT_PRICE:g} USDT\n"
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

    user = call.from_user

    users_db[user.id] = {
        "username": user.username or "без username",
        "first_name": user.first_name or "Покупатель"
    }

    orders_db[order_id] = {
        "user_id": user.id,
        "chat_id": call.message.chat.id,
        "product": "Steam Gift Card",
        "price": PRODUCT_PRICE,
        "status": "Ожидает решения"
    }

    bot.send_message(
        call.message.chat.id,
        f"✅ Заказ №{order_id} создан!\n\n"
        "🎁 Steam Gift Card\n"
        f"💰 Цена: {PRODUCT_PRICE:g} USDT\n"
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
        f"👤 Покупатель: @{user.username or 'без username'}\n"
        f"🆔 ID: {user.id}\n"
        f"🎁 Steam Gift Card\n"
        f"💰 {PRODUCT_PRICE:g} USDT",
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
        text = "✅ Заказ подтверждён!"
    else:
        order["status"] = "Отклонён"
        text = "❌ Заказ отклонён."

    bot.answer_callback_query(call.id, "Статус изменён.")

    bot.send_message(
        order["chat_id"],
        f"📦 ОБНОВЛЕНИЕ ЗАКАЗА №{order_id}\n\n{text}"
    )

    bot.edit_message_text(
        f"📋 ЗАКАЗ №{order_id}\n\n{text}",
        call.message.chat.id,
        call.message.message_id
    )


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
            f"Товар: {order['product']}\n"
            f"Цена: {order['price']:g} USDT\n"
            f"Статус: {order['status']}\n\n"
        )

    bot.send_message(message.chat.id, text)


# =========================
# ПОДДЕРЖКА
# =========================

@bot.message_handler(func=lambda m: m.text == "💬 Поддержка")
def support(message):

    support_users.add(message.from_user.id)

    bot.send_message(
        message.chat.id,
        "💬 ПОДДЕРЖКА\n\n"
        "Напишите свой вопрос. Администратор получит сообщение."
    )


# =========================
# АДМИН: ЗАКАЗЫ
# =========================

@bot.callback_query_handler(func=lambda c: c.data == "admin_orders")
def admin_orders(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    if not orders_db:
        bot.send_message(ADMIN_ID, "📋 Заказов пока нет.")
        return

    for order_id, order in orders_db.items():

        bot.send_message(
            ADMIN_ID,
            f"📋 ЗАКАЗ №{order_id}\n\n"
            f"Товар: {order['product']}\n"
            f"Цена: {order['price']:g} USDT\n"
            f"Статус: {order['status']}\n"
            f"ID покупателя: {order['user_id']}"
        )


# =========================
# АДМИН: ПОКУПАТЕЛИ
# =========================

@bot.callback_query_handler(func=lambda c: c.data == "admin_users")
def admin_users(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    if not users_db:
        bot.send_message(ADMIN_ID, "Покупателей пока нет.")
        return

    bot.send_message(ADMIN_ID, "👥 СПИСОК ПОКУПАТЕЛЕЙ")

    for user_id, user in users_db.items():

        bot.send_message(
            ADMIN_ID,
            f"👤 {user['first_name']}\n"
            f"Username: @{user['username']}\n"
            f"ID: {user_id}"
        )


# =========================
# АДМИН: ДИАЛОГИ
# =========================

@bot.callback_query_handler(func=lambda c: c.data == "admin_chats")
def admin_chats(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    if not support_users:
        bot.send_message(ADMIN_ID, "💬 Открытых диалогов нет.")
        return

    for user_id in support_users:

        user = users_db.get(user_id, {})
        username = user.get("username", "без username")

        keyboard = InlineKeyboardMarkup()

        keyboard.add(
            InlineKeyboardButton(
                "✍️ Ответить",
                callback_data=f"support_reply:{user_id}"
            )
        )

        keyboard.add(
            InlineKeyboardButton(
                "🔒 Завершить",
                callback_data=f"support_close:{user_id}"
            )
        )

        bot.send_message(
            ADMIN_ID,
            f"💬 Диалог\n\n"
            f"Покупатель: @{username}\n"
            f"ID: {user_id}",
            reply_markup=keyboard
        )


# =========================
# АДМИН: СТАТИСТИКА
# =========================

@bot.callback_query_handler(func=lambda c: c.data == "admin_stats")
def admin_stats(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    total = len(orders_db)

    pending = sum(
        1 for order in orders_db.values()
        if order["status"] == "Ожидает решения"
    )

    approved = sum(
        1 for order in orders_db.values()
        if order["status"] == "Подтверждён"
    )

    rejected = sum(
        1 for order in orders_db.values()
        if order["status"] == "Отклонён"
    )

    bot.send_message(
        ADMIN_ID,
        "📊 СТАТИСТИКА МАГАЗИНА\n\n"
        f"👥 Покупателей: {len(users_db)}\n"
        f"📦 Всего заказов: {total}\n"
        f"🕒 Ожидают решения: {pending}\n"
        f"✅ Подтверждены: {approved}\n"
        f"❌ Отклонены: {rejected}\n"
        f"💬 Открытые диалоги: {len(support_users)}"
    )


# =========================
# АДМИН: ТОВАРЫ И ЦЕНЫ
# =========================

@bot.callback_query_handler(func=lambda c: c.data == "admin_products")
def admin_products(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            "✏️ Изменить цену",
            callback_data="change_price"
        )
    )

    bot.send_message(
        ADMIN_ID,
        "⚙️ УПРАВЛЕНИЕ ТОВАРАМИ\n\n"
        f"🎁 Steam Gift Card\n"
        f"Текущая цена: {PRODUCT_PRICE:g} USDT\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda c: c.data == "change_price")
def change_price(call):

    global waiting_price

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    waiting_price = True

    bot.answer_callback_query(call.id)

    bot.send_message(
        ADMIN_ID,
        "✏️ Отправьте новую цену числом.\n\n"
        "Например: 15 или 12.5"
    )


# =========================
# ВЫБОР ДИАЛОГА
# =========================

@bot.callback_query_handler(
    func=lambda c: c.data.startswith("support_reply:")
)
def support_reply(call):

    global active_admin_chat

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    user_id = int(call.data.split(":", 1)[1])

    if user_id not in support_users:
        bot.answer_callback_query(call.id, "Диалог закрыт.")
        return

    active_admin_chat = user_id

    bot.answer_callback_query(call.id, "Диалог выбран.")

    bot.send_message(
        ADMIN_ID,
        f"✍️ Вы отвечаете покупателю {user_id}.\n"
        "Все следующие текстовые сообщения будут отправляться ему.\n\n"
        "Чтобы переключиться на другого покупателя, выберите его в разделе «Диалоги»."
    )


# =========================
# ЗАКРЫТИЕ ДИАЛОГА
# =========================

@bot.callback_query_handler(
    func=lambda c: c.data.startswith("support_close:")
)
def support_close(call):

    global active_admin_chat

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    user_id = int(call.data.split(":", 1)[1])

    support_users.discard(user_id)

    if active_admin_chat == user_id:
        active_admin_chat = None

    bot.answer_callback_query(call.id, "Диалог завершён.")

    try:
        bot.send_message(
            user_id,
            "🔒 Диалог с поддержкой завершён.\n"
            "Если понадобится помощь, снова нажмите «💬 Поддержка»."
        )
    except Exception:
        pass

    bot.send_message(
        ADMIN_ID,
        f"Диалог с покупателем {user_id} закрыт."
    )


# =========================
# ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ
# =========================

@bot.message_handler(content_types=['text'])
def handle_text(message):

    global active_admin_chat
    global waiting_price
    global PRODUCT_PRICE

    user_id = message.from_user.id
    text = message.text.strip()

    # Администратор меняет цену
    if user_id == ADMIN_ID and waiting_price:

        try:
            new_price = float(text.replace(",", "."))

            if new_price <= 0 or new_price > 100000:
                raise ValueError

            PRODUCT_PRICE = new_price
            waiting_price = False

            bot.send_message(
                ADMIN_ID,
                f"✅ Новая цена установлена: {PRODUCT_PRICE:g} USDT"
            )

        except ValueError:

            bot.send_message(
                ADMIN_ID,
                "❌ Неверная цена. Введи положительное число, например 15."
            )

        return

    # Администратор отвечает покупателю
    if user_id == ADMIN_ID and active_admin_chat is not None:

        target_id = active_admin_chat

        if target_id not in support_users:
            active_admin_chat = None
            bot.send_message(ADMIN_ID, "Диалог уже закрыт.")
            return

        try:
            bot.send_message(
                target_id,
                "💬 ОТВЕТ ПОДДЕРЖКИ\n\n" + text
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

        user = message.from_user

        users_db[user_id] = {
            "username": user.username or "без username",
            "first_name": user.first_name or "Покупатель"
        }

        keyboard = InlineKeyboardMarkup()

        keyboard.add(
            InlineKeyboardButton(
                "✍️ Ответить",
                callback_data=f"support_reply:{user_id}"
            )
        )

        keyboard.add(
            InlineKeyboardButton(
                "🔒 Завершить",
                callback_data=f"support_close:{user_id}"
            )
        )

        bot.send_message(
            ADMIN_ID,
            f"💬 НОВОЕ СООБЩЕНИЕ\n\n"
            f"👤 {user.first_name}\n"
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
