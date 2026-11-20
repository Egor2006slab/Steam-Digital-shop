import os
import uuid
import html

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

if not BOT_TOKEN or not ADMIN_ID_RAW:
    raise RuntimeError("Не заданы BOT_TOKEN или ADMIN_ID")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Не заданы данные Supabase")

ADMIN_ID = int(ADMIN_ID_RAW)

bot = telebot.TeleBot(BOT_TOKEN)
db = create_client(SUPABASE_URL, SUPABASE_KEY)

USDT_ADDRESS = ""

CATEGORIES = {
    "gifts": "🎁 Подарочные карты",
    "games": "🎮 Игры",
    "subs": "⭐ Подписки"
}

# Состояния действий администратора
admin_states = {}

# Состояния поддержки
support_waiting = set()


# ==================================================
# БАЗА ДАННЫХ: ТОВАРЫ
# ==================================================

def get_products(active_only=False):
    try:
        query = db.table("products").select("*")

        if active_only:
            query = query.eq("active", True)

        return query.order("name").execute().data or []

    except Exception as error:
        print("Ошибка загрузки товаров:", error)
        return []


def get_product(product_id):
    try:
        result = (
            db.table("products")
            .select("*")
            .eq("product_id", product_id)
            .execute()
            .data
        )

        return result[0] if result else None

    except Exception as error:
        print("Ошибка поиска товара:", error)
        return None


def add_product(product_id, category, name, price, description):
    try:
        db.table("products").insert({
            "product_id": product_id,
            "category": category,
            "name": name,
            "price": float(price),
            "description": description,
            "active": True
        }).execute()

        return True

    except Exception as error:
        print("Ошибка добавления товара:", error)
        return False


def change_price(product_id, price):
    try:
        db.table("products").update({
            "price": float(price)
        }).eq("product_id", product_id).execute()

        return True

    except Exception as error:
        print("Ошибка изменения цены:", error)
        return False


def toggle_product(product_id, active):
    try:
        db.table("products").update({
            "active": active
        }).eq("product_id", product_id).execute()

        return True

    except Exception as error:
        print("Ошибка изменения товара:", error)
        return False


def delete_product(product_id):
    try:
        db.table("products").delete().eq(
            "product_id", product_id
        ).execute()

        return True

    except Exception as error:
        print("Ошибка удаления товара:", error)
        return False


# ==================================================
# БАЗА ДАННЫХ: ПОКУПАТЕЛИ И ЗАКАЗЫ
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
        db.table("orders").insert({
            "order_id": order_id,
            "user_id": user_id,
            "product": product,
            "price": float(price),
            "status": status
        }).execute()

        return True

    except Exception as error:
        print("Ошибка сохранения заказа:", error)
        return False


def update_order(order_id, status):
    try:
        db.table("orders").update({
            "status": status
        }).eq("order_id", order_id).execute()

        return True

    except Exception as error:
        print("Ошибка обновления заказа:", error)
        return False


def is_admin(user_id):
    return user_id == ADMIN_ID


# ==================================================
# ГЛАВНОЕ МЕНЮ
# ==================================================

def main_menu(user_id):
    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    keyboard.row("🛍 Каталог", "📦 Мои заказы")
    keyboard.row("💬 Поддержка")

    if is_admin(user_id):
        keyboard.row("⚙️ Админ-панель")

    return keyboard


# ==================================================
# КАТАЛОГ
# ==================================================

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

    for product in get_products(active_only=True):
        if product["category"] == category:
            keyboard.add(
                types.InlineKeyboardButton(
                    f'{product["name"]} — {product["price"]} USDT',
                    callback_data=f'product:{product["product_id"]}'
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


@bot.message_handler(commands=["start"])
def start(message):
    save_user(message.from_user)

    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать в <b>Digital Shop</b>!\n\n"
        "Выбирай товары в каталоге и оформляй заказ.",
        parse_mode="HTML",
        reply_markup=main_menu(message.from_user.id)
    )


@bot.message_handler(func=lambda m: m.text == "🛍 Каталог")
def open_catalog(message):
    bot.send_message(
        message.chat.id,
        "🛍 <b>Каталог товаров</b>\n\nВыбери категорию:",
        parse_mode="HTML",
        reply_markup=catalog_keyboard()
    )


@bot.callback_query_handler(func=lambda c: c.data == "catalog")
def back_catalog(call):
    bot.answer_callback_query(call.id)

    bot.edit_message_text(
        "🛍 <b>Каталог товаров</b>\n\nВыбери категорию:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="HTML",
        reply_markup=catalog_keyboard()
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def open_category(call):
    bot.answer_callback_query(call.id)

    category = call.data.replace("cat_", "", 1)

    if category not in CATEGORIES:
        return

    bot.edit_message_text(
        f"<b>{CATEGORIES[category]}</b>\n\nВыбери товар:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="HTML",
        reply_markup=products_keyboard(category)
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("product:"))
def open_product(call):
    bot.answer_callback_query(call.id)

    product_id = call.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product or not product["active"]:
        bot.send_message(
            call.message.chat.id,
            "Этот товар сейчас недоступен."
        )
        return

    text = (
        f"🛍 <b>{html.escape(product['name'])}</b>\n\n"
        f"{html.escape(product.get('description') or '')}\n\n"
        f"💰 Цена: <b>{product['price']} USDT</b>"
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

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy:"))
def buy_product(call):
    product_id = call.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product or not product["active"]:
        bot.answer_callback_query(
            call.id,
            "Товар недоступен.",
            show_alert=True
        )
        return

    user = call.from_user
    save_user(user)

    order_id = uuid.uuid4().hex[:10].upper()
    status = "Ожидает проверки администратором"

    if not save_order(
        order_id,
        user.id,
        product["name"],
        product["price"],
        status
    ):
        bot.answer_callback_query(
            call.id,
            "Ошибка создания заказа.",
            show_alert=True
        )
        return

    bot.answer_callback_query(call.id, "Заказ создан!")

    if USDT_ADDRESS:
        payment_info = (
            f"Сеть: TRON TRC20\n"
            f"Адрес: <code>{USDT_ADDRESS}</code>"
        )
    else:
        payment_info = "Оплата пока не подключена."

    bot.send_message(
        user.id,
        "✅ <b>Заказ создан!</b>\n\n"
        f"Номер: <code>{order_id}</code>\n"
        f"Товар: {html.escape(product['name'])}\n"
        f"Цена: <b>{product['price']} USDT</b>\n"
        f"Статус: {status}\n\n"
        f"{payment_info}\n\n"
        "Автоматическая проверка оплаты и выдача товара "
        "пока не подключены.",
        parse_mode="HTML",
        reply_markup=main_menu(user.id)
    )

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "✅ Подтвердить",
            callback_data=f"order_ok:{order_id}"
        ),
        types.InlineKeyboardButton(
            "❌ Отклонить",
            callback_data=f"order_no:{order_id}"
        )
    )

    bot.send_message(
        ADMIN_ID,
        "🆕 <b>Новый заказ!</b>\n\n"
        f"Номер: <code>{order_id}</code>\n"
        f"Покупатель ID: <code>{user.id}</code>\n"
        f"Товар: {html.escape(product['name'])}\n"
        f"Цена: {product['price']} USDT",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("order_ok:"))
def confirm_order(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    order_id = call.data.split(":", 1)[1]

    if update_order(order_id, "Подтверждён администратором"):
        bot.answer_callback_query(call.id, "Подтверждено")
        bot.send_message(ADMIN_ID, f"Заказ {order_id} подтверждён.")
    else:
        bot.answer_callback_query(call.id, "Ошибка обновления.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("order_no:"))
def reject_order(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    order_id = call.data.split(":", 1)[1]

    if update_order(order_id, "Отклонён администратором"):
        bot.answer_callback_query(call.id, "Отклонено")
        bot.send_message(ADMIN_ID, f"Заказ {order_id} отклонён.")
    else:
        bot.answer_callback_query(call.id, "Ошибка обновления.")


# ==================================================
# МОИ ЗАКАЗЫ
# ==================================================

@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
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
        print("Ошибка заказов:", error)
        bot.send_message(message.chat.id, "Не удалось загрузить заказы.")
        return

    if not orders:
        bot.send_message(message.chat.id, "Заказов пока нет.")
        return

    text = "📦 <b>Мои заказы</b>\n\n"

    for order in orders[-15:]:
        text += (
            f"Номер: <code>{order.get('order_id')}</code>\n"
            f"Товар: {html.escape(str(order.get('product')))}\n"
            f"Цена: {order.get('price')} USDT\n"
            f"Статус: {html.escape(str(order.get('status')))}\n\n"
        )

    bot.send_message(
        message.chat.id,
        text,
        parse_mode="HTML"
    )


# ==================================================
# ПОДДЕРЖКА
# ==================================================

@bot.message_handler(func=lambda m: m.text == "💬 Поддержка")
def support_start(message):
    support_waiting.add(message.from_user.id)

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Отмена")

    bot.send_message(
        message.chat.id,
        "💬 Напиши сообщение для администратора.",
        reply_markup=keyboard
    )


@bot.message_handler(func=lambda m: m.text == "Отмена")
def support_cancel(message):
    support_waiting.discard(message.from_user.id)

    bot.send_message(
        message.chat.id,
        "Поддержка закрыта.",
        reply_markup=main_menu(message.from_user.id)
    )


@bot.message_handler(
    func=lambda m: m.from_user.id in support_waiting
    and bool(m.text)
    and m.text != "Отмена"
)
def support_message(message):
    user = message.from_user
    save_user(user)

    bot.send_message(
        ADMIN_ID,
        "💬 <b>Сообщение в поддержку</b>\n\n"
        f"Пользователь: {html.escape(user.first_name or '')}\n"
        f"ID: <code>{user.id}</code>\n\n"
        f"{html.escape(message.text)}",
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
            "🛍 Управление товарами",
            callback_data="manage_products"
        )
    )

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

    bot.send_message(
        chat_id,
        "⚙️ <b>Админ-панель</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.message_handler(commands=["admin"])
def admin_command(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Нет доступа.")
        return

    admin_panel(message.chat.id)


@bot.message_handler(func=lambda m: m.text == "⚙️ Админ-панель")
def admin_button(message):
    if is_admin(message.from_user.id):
        admin_panel(message.chat.id)


# ==================================================
# УПРАВЛЕНИЕ ТОВАРАМИ
# ==================================================

def show_manage_products(chat_id):
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "➕ Добавить товар",
            callback_data="add_product"
        )
    )

    products = get_products()

    for product in products:
        status = "🟢" if product["active"] else "🔴"

        keyboard.add(
            types.InlineKeyboardButton(
                f"{status} {product['name']}",
                callback_data=f"manage:{product['product_id']}"
            )
        )

    keyboard.add(
        types.InlineKeyboardButton(
            "⬅️ В админ-панель",
            callback_data="admin_back"
        )
    )

    bot.send_message(
        chat_id,
        "🛍 <b>Управление товарами</b>\n\n"
        "🟢 — товар виден покупателям\n"
        "🔴 — товар скрыт\n\n"
        "Выбери товар или добавь новый:",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda c: c.data == "manage_products")
def manage_products(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)
    show_manage_products(ADMIN_ID)


@bot.callback_query_handler(func=lambda c: c.data == "admin_back")
def admin_back(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)
    admin_panel(ADMIN_ID)


@bot.callback_query_handler(func=lambda c: c.data.startswith("manage:"))
def manage_one_product(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    product_id = call.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product:
        bot.send_message(ADMIN_ID, "Товар не найден.")
        return

    status = "🟢 Активен" if product["active"] else "🔴 Скрыт"

    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "✏️ Изменить цену",
            callback_data=f"price:{product_id}"
        )
    )

    if product["active"]:
        toggle_text = "🔴 Скрыть товар"
    else:
        toggle_text = "🟢 Показать товар"

    keyboard.add(
        types.InlineKeyboardButton(
            toggle_text,
            callback_data=f"toggle:{product_id}"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🗑 Удалить товар",
            callback_data=f"delete:{product_id}"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "⬅️ К списку товаров",
            callback_data="manage_products"
        )
    )

    bot.send_message(
        ADMIN_ID,
        f"🛍 <b>{html.escape(product['name'])}</b>\n\n"
        f"Цена: {product['price']} USDT\n"
        f"Статус: {status}\n"
        f"Описание: {html.escape(product.get('description') or '')}",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# ==================================================
# ИЗМЕНЕНИЕ ЦЕНЫ
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("price:"))
def start_price_change(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    product_id = call.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product:
        bot.send_message(ADMIN_ID, "Товар не найден.")
        return

    admin_states[ADMIN_ID] = {
        "action": "price",
        "product_id": product_id
    }

    bot.send_message(
        ADMIN_ID,
        f"✏️ Введи новую цену для товара:\n"
        f"{product['name']}\n\n"
        "Например: 15.50\n\n"
        "Для отмены напиши /cancel"
    )


# ==================================================
# ВКЛЮЧЕНИЕ И ОТКЛЮЧЕНИЕ ТОВАРА
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("toggle:"))
def toggle_product_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    product_id = call.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product:
        bot.answer_callback_query(call.id, "Товар не найден.")
        return

    new_status = not product["active"]

    if toggle_product(product_id, new_status):
        bot.answer_callback_query(call.id, "Статус изменён.")
        show_manage_products(ADMIN_ID)
    else:
        bot.answer_callback_query(call.id, "Ошибка.")


# ==================================================
# УДАЛЕНИЕ ТОВАРА
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("delete:"))
def delete_product_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    product_id = call.data.split(":", 1)[1]

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "Да, удалить",
            callback_data=f"delete_yes:{product_id}"
        ),
        types.InlineKeyboardButton(
            "Отмена",
            callback_data="manage_products"
        )
    )

    bot.answer_callback_query(call.id)

    bot.send_message(
        ADMIN_ID,
        "⚠️ Точно удалить этот товар?",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("delete_yes:"))
def delete_product_confirm(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    product_id = call.data.split(":", 1)[1]

    if delete_product(product_id):
        bot.answer_callback_query(call.id, "Удалено.")
        bot.send_message(ADMIN_ID, "🗑 Товар удалён.")
        show_manage_products(ADMIN_ID)
    else:
        bot.answer_callback_query(call.id, "Ошибка удаления.")


# ==================================================
# ДОБАВЛЕНИЕ ТОВАРА
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data == "add_product")
def start_add_product(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    admin_states[ADMIN_ID] = {
        "action": "add_product"
    }

    bot.send_message(
        ADMIN_ID,
        "➕ <b>Добавление товара</b>\n\n"
        "Отправь данные в одном сообщении в таком формате:\n\n"
        "<code>games | Название товара | 10 | Описание товара</code>\n\n"
        "Категории:\n"
        "gifts — подарочные карты\n"
        "games — игры\n"
        "subs — подписки\n\n"
        "Пример:\n"
        "<code>games | Новая игра | 12 | Официальный ключ игры</code>\n\n"
        "Для отмены напиши /cancel",
        parse_mode="HTML"
    )


# ==================================================
# ОБРАБОТКА ДЕЙСТВИЙ АДМИНИСТРАТОРА
# ==================================================

@bot.message_handler(commands=["cancel"])
def cancel_admin_action(message):
    if not is_admin(message.from_user.id):
        return

    admin_states.pop(ADMIN_ID, None)

    bot.send_message(
        ADMIN_ID,
        "Действие отменено."
    )


@bot.message_handler(
    func=lambda m: is_admin(m.from_user.id)
    and m.from_user.id in admin_states
    and bool(m.text)
)
def process_admin_action(message):
    state = admin_states.get(ADMIN_ID)

    if not state:
        return

    action = state["action"]

    if action == "price":
        try:
            price = float(message.text.replace(",", "."))

            if price <= 0:
                raise ValueError

        except ValueError:
            bot.send_message(
                ADMIN_ID,
                "❌ Введи положительную цену, например 12.50"
            )
            return

        product_id = state["product_id"]

        if change_price(product_id, price):
            admin_states.pop(ADMIN_ID, None)

            bot.send_message(
                ADMIN_ID,
                f"✅ Новая цена сохранена: {price} USDT"
            )
        else:
            bot.send_message(
                ADMIN_ID,
                "Не удалось изменить цену."
            )

    elif action == "add_product":
        parts = [part.strip() for part in message.text.split("|", 3)]

        if len(parts) != 4:
            bot.send_message(
                ADMIN_ID,
                "❌ Неверный формат. Используй:\n"
                "games | Название | 10 | Описание"
            )
            return

        category, name, price_text, description = parts

        if category not in CATEGORIES:
            bot.send_message(
                ADMIN_ID,
                "❌ Категория должна быть gifts, games или subs."
            )
            return

        if not name or not description:
            bot.send_message(
                ADMIN_ID,
                "Название и описание не должны быть пустыми."
            )
            return

        try:
            price = float(price_text.replace(",", "."))

            if price <= 0:
                raise ValueError

        except ValueError:
            bot.send_message(
                ADMIN_ID,
                "❌ Цена должна быть положительным числом."
            )
            return

        product_id = "item_" + uuid.uuid4().hex[:12]

        if add_product(
            product_id,
            category,
            name,
            price,
            description
        ):
            admin_states.pop(ADMIN_ID, None)

            bot.send_message(
                ADMIN_ID,
                f"✅ Товар добавлен!\n\n"
                f"{name}\n"
                f"Цена: {price} USDT"
            )

            show_manage_products(ADMIN_ID)

        else:
            bot.send_message(
                ADMIN_ID,
                "❌ Не удалось добавить товар."
            )


# ==================================================
# СПИСОК ЗАКАЗОВ
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data == "admin_orders")
def admin_orders(call):
    if not is_admin(call.from_user.id):
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

        if not orders:
            bot.send_message(ADMIN_ID, "Заказов пока нет.")
            return

        for order in orders[-20:]:
            bot.send_message(
                ADMIN_ID,
                f"📋 Заказ: {order.get('order_id')}\n"
                f"Покупатель: {order.get('user_id')}\n"
                f"Товар: {order.get('product')}\n"
                f"Цена: {order.get('price')} USDT\n"
                f"Статус: {order.get('status')}"
            )

    except Exception as error:
        bot.send_message(ADMIN_ID, f"Ошибка: {error}")


# ==================================================
# ПОКУПАТЕЛИ
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data == "admin_users")
def admin_users(call):
    if not is_admin(call.from_user.id):
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

        if not users:
            bot.send_message(ADMIN_ID, "Покупателей пока нет.")
            return

        text = "👥 <b>Покупатели</b>\n\n"

        for user in users[-30:]:
            text += (
                f"{html.escape(user.get('first_name') or 'Без имени')} "
                f"— ID: <code>{user.get('user_id')}</code>\n"
            )

        bot.send_message(
            ADMIN_ID,
            text,
            parse_mode="HTML"
        )

    except Exception as error:
        bot.send_message(ADMIN_ID, f"Ошибка: {error}")


# ==================================================
# СТАТИСТИКА
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data == "admin_stats")
def admin_stats(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    try:
        users = db.table("users").select("*").execute().data
        orders = db.table("orders").select("*").execute().data

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
        bot.send_message(ADMIN_ID, f"Ошибка: {error}")


# ==================================================
# ПРОЧИЕ СООБЩЕНИЯ
# ==================================================

@bot.message_handler(func=lambda m: True, content_types=["text"])
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
    print("Digital Shop запущен!")
    print("Товары загружаются из Supabase.")

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
