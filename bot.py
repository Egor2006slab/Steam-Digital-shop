import os
import uuid

import telebot
from telebot import types
from supabase import create_client


# ==================================================
# НАСТРОЙКИ
# ==================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN")

if not ADMIN_ID_RAW:
    raise RuntimeError("Не задан ADMIN_ID")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Не заданы данные Supabase")

ADMIN_ID = int(ADMIN_ID_RAW)

bot = telebot.TeleBot(BOT_TOKEN)
db = create_client(SUPABASE_URL, SUPABASE_KEY)


# ==================================================
# КАТАЛОГ ТОВАРОВ
# ==================================================

PRODUCTS = {
    "steam10": {
        "category": "gifts",
        "name": "Steam Gift Card $10",
        "price": 11,
        "description": "Подарочная карта Steam на 10 долларов."
    },
    "steam20": {
        "category": "gifts",
        "name": "Steam Gift Card $20",
        "price": 21,
        "description": "Подарочная карта Steam на 20 долларов."
    },
    "steam50": {
        "category": "gifts",
        "name": "Steam Gift Card $50",
        "price": 52,
        "description": "Подарочная карта Steam на 50 долларов."
    },
    "steam100": {
        "category": "gifts",
        "name": "Steam Gift Card $100",
        "price": 103,
        "description": "Подарочная карта Steam на 100 долларов."
    },

    "terraria": {
        "category": "games",
        "name": "Terraria",
        "price": 9,
        "description": "Цифровой ключ игры Terraria."
    },
    "stardew": {
        "category": "games",
        "name": "Stardew Valley",
        "price": 11,
        "description": "Цифровой ключ игры Stardew Valley."
    },
    "portal2": {
        "category": "games",
        "name": "Portal 2",
        "price": 5,
        "description": "Цифровой ключ игры Portal 2."
    },
    "hollow": {
        "category": "games",
        "name": "Hollow Knight",
        "price": 9,
        "description": "Цифровой ключ игры Hollow Knight."
    },
    "celeste": {
        "category": "games",
        "name": "Celeste",
        "price": 8,
        "description": "Цифровой ключ игры Celeste."
    },

    "pcpass": {
        "category": "subs",
        "name": "PC Game Pass — 1 месяц",
        "price": 12,
        "description": "Подписка PC Game Pass на один месяц."
    },
    "xboxpass": {
        "category": "subs",
        "name": "Xbox Game Pass Ultimate — 1 месяц",
        "price": 18,
        "description": "Подписка Xbox Game Pass Ultimate на один месяц."
    },
    "nitro": {
        "category": "subs",
        "name": "Discord Nitro — 1 месяц",
        "price": 10,
        "description": "Подарочный код Discord Nitro на один месяц."
    }
}


CATEGORIES = {
    "gifts": "🎁 Подарочные карты",
    "games": "🎮 Игры",
    "subs": "⭐ Подписки"
}


# Адрес оставлен пустым специально.
# Не указывай случайный или непроверенный адрес кошелька.
USDT_ADDRESS = ""


# ==================================================
# РАБОТА С БАЗОЙ ДАННЫХ
# ==================================================

def save_user(user):
    try:
        data = {
            "user_id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "last_name": user.last_name or ""
        }

        existing = (
            db.table("users")
            .select("user_id")
            .eq("user_id", user.id)
            .execute()
            .data
        )

        if existing:
            db.table("users").update(data).eq(
                "user_id", user.id
            ).execute()
        else:
            db.table("users").insert(data).execute()

    except Exception as error:
        print("Ошибка сохранения пользователя:", error)


def save_order(order_id, user_id, product, price, status):
    try:
        data = {
            "order_id": order_id,
            "user_id": user_id,
            "product": product,
            "price": float(price),
            "status": status
        }

        db.table("orders").insert(data).execute()
        return True

    except Exception as error:
        print("Ошибка сохранения заказа:", error)
        return False


def update_order(order_id, status):
    try:
        db.table("orders").update({
            "status": status
        }).eq("order_id", order_id).execute()

    except Exception as error:
        print("Ошибка обновления заказа:", error)


# ==================================================
# КЛАВИАТУРЫ
# ==================================================

def main_menu(user_id):
    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    keyboard.row("🛍 Каталог", "📦 Мои заказы")
    keyboard.row("💬 Поддержка")

    if user_id == ADMIN_ID:
        keyboard.row("⚙️ Админ-панель")

    return keyboard


def catalog_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    for category_id, category_name in CATEGORIES.items():
        keyboard.add(
            types.InlineKeyboardButton(
                category_name,
                callback_data=f"cat_{category_id}"
            )
        )

    return keyboard


def products_keyboard(category):
    keyboard = types.InlineKeyboardMarkup()

    for product_id, product in PRODUCTS.items():

        if product["category"] == category:

            keyboard.add(
                types.InlineKeyboardButton(
                    f'{product["name"]} — {product["price"]} USDT',
                    callback_data=f"product:{product_id}"
                )
            )

    keyboard.add(
        types.InlineKeyboardButton(
            "⬅️ Назад",
            callback_data="catalog"
        )
    )

    return keyboard


def product_keyboard(product_id, category):
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "🛒 Купить",
            callback_data=f"buy:{product_id}"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=f"cat_{category}"
        )
    )

    return keyboard


# ==================================================
# СТАРТ
# ==================================================

@bot.message_handler(commands=["start"])
def start(message):

    save_user(message.from_user)

    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать в <b>Digital Shop</b>!\n\n"
        "Здесь ты можешь выбрать цифровые товары "
        "и оформить заказ.\n\n"
        "Нажми «Каталог», чтобы посмотреть ассортимент.",
        parse_mode="HTML",
        reply_markup=main_menu(message.from_user.id)
    )


# ==================================================
# КАТАЛОГ
# ==================================================

@bot.message_handler(func=lambda m: m.text == "🛍 Каталог")
def open_catalog(message):

    bot.send_message(
        message.chat.id,
        "🛍 <b>Каталог товаров</b>\n\n"
        "Выбери категорию:",
        parse_mode="HTML",
        reply_markup=catalog_keyboard()
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "catalog"
)
def back_to_catalog(call):

    bot.answer_callback_query(call.id)

    bot.edit_message_text(
        "🛍 <b>Каталог товаров</b>\n\nВыбери категорию:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="HTML",
        reply_markup=catalog_keyboard()
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("cat_")
)
def open_category(call):

    bot.answer_callback_query(call.id)

    category = call.data.replace("cat_", "")

    if category not in CATEGORIES:
        return

    bot.edit_message_text(
        f"<b>{CATEGORIES[category]}</b>\n\n"
        "Выбери товар:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="HTML",
        reply_markup=products_keyboard(category)
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("product:")
)
def open_product(call):

    bot.answer_callback_query(call.id)

    product_id = call.data.split(":", 1)[1]
    product = PRODUCTS.get(product_id)

    if not product:
        return

    text = (
        f"🛍 <b>{product['name']}</b>\n\n"
        f"{product['description']}\n\n"
        f"💰 Цена: <b>{product['price']} USDT</b>\n\n"
        "ℹ️ Демонстрационная карточка товара. "
        "Перед реальной продажей проверь наличие, регион "
        "и условия активации кода."
    )

    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode="HTML",
        reply_markup=product_keyboard(
            product_id,
            product["category"]
        )
    )


# ==================================================
# ПОКУПКА
# ==================================================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("buy:")
)
def buy_product(call):

    product_id = call.data.split(":", 1)[1]
    product = PRODUCTS.get(product_id)

    if not product:
        bot.answer_callback_query(
            call.id,
            "Товар не найден.",
            show_alert=True
        )
        return

    user = call.from_user
    save_user(user)

    order_id = uuid.uuid4().hex[:10].upper()

    status = "Ожидает проверки администратором"

    saved = save_order(
        order_id,
        user.id,
        product["name"],
        product["price"],
        status
    )

    if not saved:
        bot.answer_callback_query(
            call.id,
            "Не удалось создать заказ.",
            show_alert=True
        )
        return

    bot.answer_callback_query(
        call.id,
        "Заказ создан!"
    )

    if USDT_ADDRESS:

        payment_info = (
            f"Сеть: TRC20\n"
            f"Адрес: <code>{USDT_ADDRESS}</code>"
        )

    else:

        payment_info = (
            "Оплата пока не подключена. "
            "Ожидай инструкции от администратора."
        )

    bot.send_message(
        user.id,
        "✅ <b>Заказ создан!</b>\n\n"
        f"Номер: <code>{order_id}</code>\n"
        f"Товар: {product['name']}\n"
        f"Цена: <b>{product['price']} USDT</b>\n"
        f"Статус: {status}\n\n"
        f"{payment_info}\n\n"
        "Автоматическая проверка оплаты и выдача "
        "цифрового кода пока не подключены.",
        parse_mode="HTML",
        reply_markup=main_menu(user.id)
    )

    admin_keyboard = types.InlineKeyboardMarkup()

    admin_keyboard.row(
        types.InlineKeyboardButton(
            "✅ Подтвердить",
            callback_data=f"order_ok:{order_id}"
        ),
        types.InlineKeyboardButton(
            "❌ Отклонить",
            callback_data=f"order_no:{order_id}"
        )
    )

    username = (
        f"@{user.username}"
        if user.username
        else "не указан"
    )

    bot.send_message(
        ADMIN_ID,
        "🆕 <b>Новый заказ!</b>\n\n"
        f"Номер: <code>{order_id}</code>\n"
        f"Покупатель: {user.first_name}\n"
        f"Username: {username}\n"
        f"ID: <code>{user.id}</code>\n"
        f"Товар: {product['name']}\n"
        f"Цена: {product['price']} USDT",
        parse_mode="HTML",
        reply_markup=admin_keyboard
    )


# ==================================================
# ПОДТВЕРЖДЕНИЕ ЗАКАЗОВ
# ==================================================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("order_ok:")
)
def confirm_order(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "Нет доступа.",
            show_alert=True
        )
        return

    order_id = call.data.split(":", 1)[1]

    update_order(
        order_id,
        "Подтверждён администратором"
    )

    bot.answer_callback_query(
        call.id,
        "Заказ подтверждён."
    )

    bot.send_message(
        ADMIN_ID,
        f"✅ Заказ {order_id} подтверждён."
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("order_no:")
)
def reject_order(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "Нет доступа.",
            show_alert=True
        )
        return

    order_id = call.data.split(":", 1)[1]

    update_order(
        order_id,
        "Отклонён администратором"
    )

    bot.answer_callback_query(
        call.id,
        "Заказ отклонён."
    )

    bot.send_message(
        ADMIN_ID,
        f"❌ Заказ {order_id} отклонён."
    )


# ==================================================
# МОИ ЗАКАЗЫ
# ==================================================

@bot.message_handler(
    func=lambda m: m.text == "📦 Мои заказы"
)
def my_orders(message):

    try:

        orders = (
            db.table("orders")
            .select("*")
            .eq("user_id", message.from_user.id)
            .execute()
            .data
        )

    except Exception as error:

        print("Ошибка загрузки заказов:", error)

        bot.send_message(
            message.chat.id,
            "Не удалось загрузить заказы."
        )
        return

    if not orders:

        bot.send_message(
            message.chat.id,
            "У тебя пока нет заказов."
        )
        return

    text = "📦 <b>Мои заказы</b>\n\n"

    for order in orders:

        text += (
            f"Номер: <code>{order.get('order_id')}</code>\n"
            f"Товар: {order.get('product')}\n"
            f"Цена: {order.get('price')} USDT\n"
            f"Статус: {order.get('status')}\n\n"
        )

    bot.send_message(
        message.chat.id,
        text,
        parse_mode="HTML"
    )


# ==================================================
# ПОДДЕРЖКА
# ==================================================

support_waiting = set()


@bot.message_handler(
    func=lambda m: m.text == "💬 Поддержка"
)
def support_start(message):

    support_waiting.add(message.from_user.id)

    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    keyboard.add("Отмена")

    bot.send_message(
        message.chat.id,
        "💬 Напиши сообщение для администратора.",
        reply_markup=keyboard
    )


@bot.message_handler(
    func=lambda m: m.text == "Отмена"
)
def support_cancel(message):

    support_waiting.discard(message.from_user.id)

    bot.send_message(
        message.chat.id,
        "Поддержка закрыта.",
        reply_markup=main_menu(message.from_user.id)
    )


@bot.message_handler(
    func=lambda m: (
        m.from_user.id in support_waiting
        and bool(m.text)
        and m.text != "Отмена"
    )
)
def support_message(message):

    user = message.from_user

    username = (
        f"@{user.username}"
        if user.username
        else "не указан"
    )

    bot.send_message(
        ADMIN_ID,
        "💬 <b>Сообщение в поддержку</b>\n\n"
        f"Пользователь: {user.first_name}\n"
        f"Username: {username}\n"
        f"ID: <code>{user.id}</code>\n\n"
        f"{message.text}",
        parse_mode="HTML"
    )

    support_waiting.discard(user.id)

    bot.send_message(
        message.chat.id,
        "✅ Сообщение отправлено администратору.",
        reply_markup=main_menu(user.id)
    )


# ==================================================
# АДМИН-ПАНЕЛЬ
# ==================================================

def admin_panel(chat_id):

    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "📋 Заказы",
            callback_data="admin_orders"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "👥 Покупатели",
            callback_data="admin_users"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "📊 Статистика",
            callback_data="admin_stats"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🛍 Товары и цены",
            callback_data="admin_products"
        )
    )

    bot.send_message(
        chat_id,
        "⚙️ <b>Админ-панель</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.message_handler(
    commands=["admin"]
)
def admin_command(message):

    if message.from_user.id != ADMIN_ID:

        bot.send_message(
            message.chat.id,
            "⛔ Нет доступа."
        )
        return

    admin_panel(message.chat.id)


@bot.message_handler(
    func=lambda m: m.text == "⚙️ Админ-панель"
)
def admin_button(message):

    if message.from_user.id == ADMIN_ID:
        admin_panel(message.chat.id)


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_products"
)
def admin_products(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "Нет доступа.",
            show_alert=True
        )
        return

    bot.answer_callback_query(call.id)

    text = "🛍 <b>Товары магазина</b>\n\n"

    for product in PRODUCTS.values():

        text += (
            f"• {product['name']}\n"
            f"Цена: {product['price']} USDT\n\n"
        )

    text += (
        "Чтобы изменить цену, открой файл bot.py "
        "и измени значение price у нужного товара."
    )

    bot.send_message(
        ADMIN_ID,
        text,
        parse_mode="HTML"
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_orders"
)
def admin_orders(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    try:

        orders = (
            db.table("orders")
            .select("*")
            .execute()
            .data
        )

    except Exception as error:

        bot.send_message(
            ADMIN_ID,
            f"Ошибка: {error}"
        )
        return

    if not orders:

        bot.send_message(
            ADMIN_ID,
            "Заказов пока нет."
        )
        return

    for order in orders[-20:]:

        bot.send_message(
            ADMIN_ID,
            f"Заказ: {order.get('order_id')}\n"
            f"Покупатель ID: {order.get('user_id')}\n"
            f"Товар: {order.get('product')}\n"
            f"Цена: {order.get('price')} USDT\n"
            f"Статус: {order.get('status')}"
        )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_users"
)
def admin_users(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    try:

        users = (
            db.table("users")
            .select("*")
            .execute()
            .data
        )

    except Exception as error:

        bot.send_message(
            ADMIN_ID,
            f"Ошибка: {error}"
        )
        return

    if not users:

        bot.send_message(
            ADMIN_ID,
            "Покупателей пока нет."
        )
        return

    text = "👥 <b>Покупатели</b>\n\n"

    for user in users[-30:]:

        text += (
            f"{user.get('first_name', 'Без имени')} "
            f"— ID: <code>{user.get('user_id')}</code>\n"
        )

    bot.send_message(
        ADMIN_ID,
        text,
        parse_mode="HTML"
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_stats"
)
def admin_stats(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    try:

        orders = (
            db.table("orders")
            .select("*")
            .execute()
            .data
        )

        users = (
            db.table("users")
            .select("*")
            .execute()
            .data
        )

        total = sum(
            float(order.get("price") or 0)
            for order in orders
        )

        bot.send_message(
            ADMIN_ID,
            "📊 <b>Статистика магазина</b>\n\n"
            f"Покупателей: {len(users)}\n"
            f"Заказов: {len(orders)}\n"
            f"Сумма заказов: {total:.2f} USDT",
            parse_mode="HTML"
        )

    except Exception as error:

        bot.send_message(
            ADMIN_ID,
            f"Ошибка статистики: {error}"
        )


# ==================================================
# НЕИЗВЕСТНЫЕ СООБЩЕНИЯ
# ==================================================

@bot.message_handler(
    func=lambda m: True,
    content_types=["text"]
)
def other_messages(message):

    bot.send_message(
        message.chat.id,
        "Выбери действие в меню.",
        reply_markup=main_menu(message.from_user.id)
    )


# ==================================================
# ЗАПУСК
# ==================================================

if __name__ == "__main__":

    print("Бот запускается...")
    print("Товаров в каталоге:", len(PRODUCTS))

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
