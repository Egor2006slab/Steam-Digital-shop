import os
import uuid
import telebot

from supabase import create_client
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# =====================================
# 1. ПОДКЛЮЧЕНИЕ
# =====================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    raise ValueError("Не задан BOT_TOKEN в GitHub Secrets.")

if not ADMIN_ID_RAW:
    raise ValueError("Не задан ADMIN_ID в GitHub Secrets.")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Не заданы SUPABASE_URL или SUPABASE_KEY.")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise ValueError("ADMIN_ID должен быть числом.")

bot = telebot.TeleBot(TOKEN)
db = create_client(SUPABASE_URL, SUPABASE_KEY)


# =====================================
# 2. НАСТРОЙКИ МАГАЗИНА
# =====================================

PAYMENT_NETWORK = "TRC20 (TRON)"

# ДЕМОНСТРАЦИОННАЯ ЗАГЛУШКА.
# Это НЕ настоящий адрес криптокошелька.
# Не принимай на него платежи.
PAYMENT_ADDRESS = "DEMO_ONLY_REPLACE_WITH_REAL_TRON_ADDRESS"

PRODUCT_PRICE = 10.0

orders_db = {}
users_db = {}
support_users = set()

active_admin_chat = None
waiting_price = False


# =====================================
# 3. ЗАГРУЗКА ДАННЫХ ИЗ SUPABASE
# =====================================

def load_data():
    global PRODUCT_PRICE

    print("Загружаю данные из Supabase...")

    # Покупатели
    users = db.table("users").select("*").execute().data

    for user in users:
        user_id = int(user["user_id"])

        users_db[user_id] = {
            "username": user.get("username") or "без username",
            "first_name": user.get("first_name") or "Покупатель"
        }

    # Заказы
    orders = db.table("orders").select("*").execute().data

    for order in orders:
        order_id = str(order["order_id"])
        user_id = int(order["user_id"])

        orders_db[order_id] = {
            "user_id": user_id,
            "chat_id": user_id,
            "product": order["product"],
            "price": float(order["price"]),
            "status": order["status"]
        }

    # Открытые диалоги поддержки
    chats = (
        db.table("support_chats")
        .select("*")
        .eq("is_open", True)
        .execute()
        .data
    )

    for chat in chats:
        support_users.add(int(chat["user_id"]))

    # Цена товара
    settings = (
        db.table("shop_settings")
        .select("*")
        .eq("setting_name", "product_price")
        .execute()
        .data
    )

    if settings:
        PRODUCT_PRICE = float(settings[0]["setting_value"])

    print("Данные успешно загружены.")
    print("Покупателей:", len(users_db))
    print("Заказов:", len(orders_db))


# =====================================
# 4. СОХРАНЕНИЕ ДАННЫХ
# =====================================

def save_user(user):
    users_db[user.id] = {
        "username": user.username or "без username",
        "first_name": user.first_name or "Покупатель"
    }

    db.table("users").upsert({
        "user_id": user.id,
        "username": user.username or "без username",
        "first_name": user.first_name or "Покупатель"
    }).execute()


def save_order(order_id):
    order = orders_db[order_id]

    db.table("orders").upsert({
        "order_id": order_id,
        "user_id": order["user_id"],
        "product": order["product"],
        "price": order["price"],
        "status": order["status"]
    }).execute()


def save_message(user_id, sender, message):
    db.table("support_messages").insert({
        "user_id": user_id,
        "sender": sender,
        "message": message
    }).execute()


def save_chat(user_id, is_open):
    db.table("support_chats").upsert({
        "user_id": user_id,
        "is_open": is_open
    }).execute()


# =====================================
# 5. ГЛАВНОЕ МЕНЮ
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    try:
        save_user(message.from_user)

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

    except Exception as error:
        print("Ошибка start:", error)
        bot.send_message(
            message.chat.id,
            "Произошла ошибка. Попробуйте позже."
        )


# =====================================
# 6. АДМИН-ПАНЕЛЬ
# =====================================

def admin_keyboard():
    keyboard = InlineKeyboardMarkup()

    buttons = [
        ("📋 Заказы", "admin_orders"),
        ("👥 Покупатели", "admin_users"),
        ("💬 Диалоги", "admin_chats"),
        ("📊 Статистика", "admin_stats"),
        ("⚙️ Товары и цены", "admin_products")
    ]

    for title, data in buttons:
        keyboard.add(
            InlineKeyboardButton(
                title,
                callback_data=data
            )
        )

    return keyboard


@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(
            message.chat.id,
            "⛔ Нет доступа."
        )
        return

    bot.send_message(
        message.chat.id,
        "⚙️ АДМИНИСТРАТИВНАЯ ПАНЕЛЬ\n\n"
        "Выберите нужный раздел:",
        reply_markup=admin_keyboard()
    )


# =====================================
# 7. КАТАЛОГ
# =====================================

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
        "🛍 КАТАЛОГ МАГАЗИНА\n\n"
        "Выберите категорию:",
        reply_markup=catalog_keyboard()
    )


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("cat_")
)
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
            "Steam Gift Card\n"
            f"Цена: {PRODUCT_PRICE:g} USDT\n"
            "Регион: демонстрационный\n\n"
            "⚠️ Демонстрационный товар."
        )

    elif call.data == "cat_games":

        text = (
            "🎮 КЛЮЧИ ИГР\n\n"
            "Пока товаров нет."
        )

    else:

        text = (
            "⭐ ПОДПИСКИ\n\n"
            "Пока товаров нет."
        )

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


@bot.callback_query_handler(
    func=lambda c: c.data == "back_catalog"
)
def back_catalog(call):
    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        "🛍 ВЫБЕРИТЕ КАТЕГОРИЮ:",
        reply_markup=catalog_keyboard()
    )


# =====================================
# 8. СОЗДАНИЕ ЗАКАЗА
# =====================================

@bot.callback_query_handler(
    func=lambda c: c.data == "buy_steam"
)
def buy(call):
    bot.answer_callback_query(call.id)

    user = call.from_user
    save_user(user)

    order_id = uuid.uuid4().hex[:8].upper()

    orders_db[order_id] = {
        "user_id": user.id,
        "chat_id": call.message.chat.id,
        "product": "Steam Gift Card",
        "price": PRODUCT_PRICE,
        "status": "Ожидает оплаты"
    }

    save_order(order_id)

    bot.send_message(
        call.message.chat.id,
        f"✅ Заказ №{order_id} создан!\n\n"
        "🎁 Steam Gift Card\n"
        f"💰 Сумма: {PRODUCT_PRICE:g} USDT\n"
        f"🌐 Сеть: {PAYMENT_NETWORK}\n\n"
        "💳 Адрес для демонстрации:\n"
        f"{PAYMENT_ADDRESS}\n\n"
        "⚠️ ВНИМАНИЕ!\n"
        "Это тестовая заглушка, а не настоящий адрес.\n"
        "Не отправляйте на него криптовалюту.\n\n"
        "После реальной оплаты администратор сможет "
        "вручную подтвердить заказ."
    )

    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            "✅ Подтвердить оплату",
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
        "🎁 Steam Gift Card\n"
        f"💰 {PRODUCT_PRICE:g} USDT\n"
        f"🌐 Сеть: {PAYMENT_NETWORK}\n\n"
        "⚠️ Оплату нужно проверять вручную.",
        reply_markup=keyboard
    )


# =====================================
# 9. ПОДТВЕРЖДЕНИЕ И ОТКЛОНЕНИЕ ЗАКАЗА
# =====================================

@bot.callback_query_handler(
    func=lambda c: (
        c.data.startswith("approve:")
        or c.data.startswith("reject:")
    )
)
def manage_order(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "⛔ Нет доступа."
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

    if order["status"] != "Ожидает оплаты":
        bot.answer_callback_query(
            call.id,
            "Заказ уже обработан."
        )
        return

    if action == "approve":

        order["status"] = "Оплата подтверждена"

        text = "✅ Оплата подтверждена администратором!"

    else:

        order["status"] = "Отклонён"

        text = "❌ Заказ отклонён."

    save_order(order_id)

    bot.answer_callback_query(
        call.id,
        "Статус изменён."
    )

    bot.send_message(
        order["chat_id"],
        f"📦 ОБНОВЛЕНИЕ ЗАКАЗА №{order_id}\n\n{text}"
    )

    bot.edit_message_text(
        f"📋 ЗАКАЗ №{order_id}\n\n{text}",
        call.message.chat.id,
        call.message.message_id
    )


# =====================================
# 10. МОИ ЗАКАЗЫ
# =====================================

@bot.message_handler(
    func=lambda m: m.text == "📦 Мои заказы"
)
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

    bot.send_message(
        message.chat.id,
        text
    )


# =====================================
# 11. ПОДДЕРЖКА
# =====================================

@bot.message_handler(
    func=lambda m: m.text == "💬 Поддержка"
)
def support(message):

    save_user(message.from_user)

    support_users.add(message.from_user.id)

    save_chat(
        message.from_user.id,
        True
    )

    bot.send_message(
        message.chat.id,
        "💬 ПОДДЕРЖКА\n\n"
        "Напишите свой вопрос. "
        "Администратор получит сообщение."
    )


# =====================================
# 12. АДМИН: ЗАКАЗЫ
# =====================================

@bot.callback_query_handler(
    func=lambda c: c.data == "admin_orders"
)
def admin_orders(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "Нет доступа."
        )
        return

    bot.answer_callback_query(call.id)

    if not orders_db:
        bot.send_message(
            ADMIN_ID,
            "📋 Заказов пока нет."
        )
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


# =====================================
# 13. АДМИН: ПОКУПАТЕЛИ
# =====================================

@bot.callback_query_handler(
    func=lambda c: c.data == "admin_users"
)
def admin_users(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "Нет доступа."
        )
        return

    bot.answer_callback_query(call.id)

    if not users_db:
        bot.send_message(
            ADMIN_ID,
            "Покупателей пока нет."
        )
        return

    bot.send_message(
        ADMIN_ID,
        "👥 СПИСОК ПОКУПАТЕЛЕЙ"
    )

    for user_id, user in users_db.items():

        bot.send_message(
            ADMIN_ID,
            f"👤 {user['first_name']}\n"
            f"Username: @{user['username']}\n"
            f"ID: {user_id}"
        )


# =====================================
# 14. АДМИН: ДИАЛОГИ
# =====================================

@bot.callback_query_handler(
    func=lambda c: c.data == "admin_chats"
)
def admin_chats(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "Нет доступа."
        )
        return

    bot.answer_callback_query(call.id)

    if not support_users:
        bot.send_message(
            ADMIN_ID,
            "💬 Открытых диалогов нет."
        )
        return

    for user_id in support_users:

        user = users_db.get(user_id, {})

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
            f"Покупатель: @{user.get('username', 'без username')}\n"
            f"ID: {user_id}",
            reply_markup=keyboard
        )


# =====================================
# 15. АДМИН: СТАТИСТИКА
# =====================================

@bot.callback_query_handler(
    func=lambda c: c.data == "admin_stats"
)
def admin_stats(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "Нет доступа."
        )
        return

    bot.answer_callback_query(call.id)

    total = len(orders_db)

    pending = sum(
        1 for order in orders_db.values()
        if order["status"] == "Ожидает оплаты"
    )

    approved = sum(
        1 for order in orders_db.values()
        if order["status"] == "Оплата подтверждена"
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
        f"🕒 Ожидают оплаты: {pending}\n"
        f"✅ Оплата подтверждена: {approved}\n"
        f"❌ Отклонены: {rejected}\n"
        f"💬 Открытые диалоги: {len(support_users)}"
    )


# =====================================
# 16. АДМИН: ТОВАРЫ И ЦЕНЫ
# =====================================

@bot.callback_query_handler(
    func=lambda c: c.data == "admin_products"
)
def admin_products(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "Нет доступа."
        )
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
        "🎁 Steam Gift Card\n"
        f"Текущая цена: {PRODUCT_PRICE:g} USDT\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )


@bot.callback_query_handler(
    func=lambda c: c.data == "change_price"
)
def change_price(call):
    global waiting_price

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "Нет доступа."
        )
        return

    waiting_price = True

    bot.answer_callback_query(call.id)

    bot.send_message(
        ADMIN_ID,
        "✏️ Отправьте новую цену числом.\n\n"
        "Например: 15 или 12.5"
    )


# =====================================
# 17. ОТВЕТЫ ПОДДЕРЖКИ
# =====================================

@bot.callback_query_handler(
    func=lambda c: c.data.startswith("support_reply:")
)
def support_reply(call):
    global active_admin_chat

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "Нет доступа."
        )
        return

    user_id = int(call.data.split(":", 1)[1])

    if user_id not in support_users:
        bot.answer_callback_query(
            call.id,
            "Диалог закрыт."
        )
        return

    active_admin_chat = user_id

    bot.answer_callback_query(
        call.id,
        "Диалог выбран."
    )

    bot.send_message(
        ADMIN_ID,
        f"✍️ Вы отвечаете покупателю {user_id}.\n"
        "Следующие текстовые сообщения будут отправляться ему."
    )


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("support_close:")
)
def support_close(call):
    global active_admin_chat

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "Нет доступа."
        )
        return

    user_id = int(call.data.split(":", 1)[1])

    support_users.discard(user_id)

    save_chat(user_id, False)

    if active_admin_chat == user_id:
        active_admin_chat = None

    bot.answer_callback_query(
        call.id,
        "Диалог завершён."
    )

    bot.send_message(
        user_id,
        "🔒 Диалог с поддержкой завершён."
    )

    bot.send_message(
        ADMIN_ID,
        f"Диалог с покупателем {user_id} закрыт."
    )


# =====================================
# 18. ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ
# =====================================

@bot.message_handler(content_types=["text"])
def handle_text(message):
    global active_admin_chat
    global waiting_price
    global PRODUCT_PRICE

    user_id = message.from_user.id
    text = message.text.strip()

    # ---------------------------------
    # Изменение цены администратором
    # ---------------------------------

    if user_id == ADMIN_ID and waiting_price:

        try:
            new_price = float(
                text.replace(",", ".")
            )

            if new_price <= 0 or new_price > 100000:
                raise ValueError

            PRODUCT_PRICE = new_price

            db.table("shop_settings").upsert({
                "setting_name": "product_price",
                "setting_value": str(PRODUCT_PRICE)
            }).execute()

            waiting_price = False

            bot.send_message(
                ADMIN_ID,
                f"✅ Новая цена сохранена: "
                f"{PRODUCT_PRICE:g} USDT"
            )

        except ValueError:

            bot.send_message(
                ADMIN_ID,
                "❌ Неверная цена.\n"
                "Введи положительное число."
            )

        except Exception as error:

            print("Ошибка сохранения цены:", error)

            bot.send_message(
                ADMIN_ID,
                "❌ Не удалось сохранить цену в базе данных."
            )

        return

    # ---------------------------------
    # Ответ администратора покупателю
    # ---------------------------------

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
                "💬 ОТВЕТ ПОДДЕРЖКИ\n\n" + text
            )

            save_message(
                target_id,
                "admin",
                text
            )

            bot.send_message(
                ADMIN_ID,
                "✅ Сообщение отправлено."
            )

        except Exception as error:

            print("Ошибка отправки ответа:", error)

            bot.send_message(
                ADMIN_ID,
                "❌ Не удалось отправить сообщение."
            )

        return

    # ---------------------------------
    # Сообщение от покупателя
    # ---------------------------------

    if user_id in support_users:

        try:
            save_user(message.from_user)

            save_message(
                user_id,
                "user",
                text
            )

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
                f"👤 {message.from_user.first_name}\n"
                f"🆔 ID: {user_id}\n\n"
                f"Сообщение:\n{text}",
                reply_markup=keyboard
            )

            bot.send_message(
                message.chat.id,
                "✅ Сообщение передано администратору."
            )

        except Exception as error:

            print("Ошибка поддержки:", error)

            bot.send_message(
                message.chat.id,
                "❌ Не удалось отправить сообщение. "
                "Попробуйте позже."
            )

        return

    # ---------------------------------
    # Остальные сообщения
    # ---------------------------------

    bot.send_message(
        message.chat.id,
        "Выберите раздел в меню."
    )


# =====================================
# 19. ЗАПУСК БОТА
# =====================================

if __name__ == "__main__":

    try:
        load_data()

        print("Telegram bot started successfully.")

        bot.infinity_polling(
            skip_pending=True,
            timeout=30,
            long_polling_timeout=30
        )

    except Exception as error:

        print("КРИТИЧЕСКАЯ ОШИБКА:", error)

        raise
