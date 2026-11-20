import os
import uuid
import html
from decimal import Decimal, InvalidOperation

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

CATEGORIES = {
    "gifts": "🎁 Подарочные карты",
    "games": "🎮 Игры",
    "subs": "⭐ Подписки"
}

admin_states = {}
support_waiting = set()
topup_waiting = set()


# ==================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==================================================

def is_admin(user_id):
    return user_id == ADMIN_ID


def money(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def money_text(value):
    return f"{money(value):.2f}"


def get_user_record(user_id):
    try:
        result = (
            db.table("users")
            .select("*")
            .eq("user_id", user_id)
            .execute()
            .data
        )

        return result[0] if result else None

    except Exception as error:
        print("Ошибка загрузки пользователя:", error)
        return None


def get_balance(user_id):
    user = get_user_record(user_id)

    if not user:
        return Decimal("0.00")

    return money(user.get("balance", 0))


def notify_user(user_id, text):
    try:
        bot.send_message(
            user_id,
            text,
            parse_mode="HTML"
        )
    except Exception as error:
        print("Не удалось отправить сообщение пользователю:", error)


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
# БАЗА ДАННЫХ: ПОКУПАТЕЛИ
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


# ==================================================
# БАЗА ДАННЫХ: ЗАКАЗЫ
# ==================================================

def get_order(order_id):
    try:
        result = (
            db.table("orders")
            .select("*")
            .eq("order_id", order_id)
            .execute()
            .data
        )

        return result[0] if result else None

    except Exception as error:
        print("Ошибка получения заказа:", error)
        return None


def update_order(order_id, status):
    try:
        db.table("orders").update({
            "status": status
        }).eq("order_id", order_id).execute()

        return True

    except Exception as error:
        print("Ошибка обновления заказа:", error)
        return False


# ==================================================
# БАЛАНС: ИСТОРИЯ
# ==================================================

def get_balance_history(user_id):
    try:
        return (
            db.table("balance_transactions")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
            .data or []
        )

    except Exception as error:
        print("Ошибка истории баланса:", error)
        return None


# ==================================================
# ГЛАВНОЕ МЕНЮ
# ==================================================

def main_menu(user_id):
    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    keyboard.row("🛍 Каталог", "📦 Мои заказы")
    keyboard.row("👤 Мой профиль", "💳 Пополнить баланс")
    keyboard.row("💬 Поддержка")

    if is_admin(user_id):
        keyboard.row("⚙️ Админ-панель")

    return keyboard


# ==================================================
# ПРОФИЛЬ ПОКУПАТЕЛЯ
# ==================================================

@bot.message_handler(func=lambda m: m.text == "👤 Мой профиль")
def show_profile(message):
    user_id = message.from_user.id
    save_user(message.from_user)

    user = get_user_record(user_id)

    if not user:
        bot.send_message(
            message.chat.id,
            "Не удалось загрузить профиль."
        )
        return

    balance = money_text(user.get("balance", 0))
    purchased = user.get("purchased_count", 0)

    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "📜 История баланса",
            callback_data="balance_history"
        )
    )

    bot.send_message(
        message.chat.id,
        "👤 <b>Мой профиль</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💰 Баланс: <b>{balance} USDT</b>\n"
        f"🛍 Покупок: <b>{purchased}</b>\n\n"
        "Для пополнения баланса воспользуйся кнопкой "
        "«💳 Пополнить баланс».",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda c: c.data == "balance_history")
def show_balance_history(call):
    bot.answer_callback_query(call.id)

    history = get_balance_history(call.from_user.id)

    if history is None:
        bot.send_message(
            call.message.chat.id,
            "Не удалось загрузить историю."
        )
        return

    if not history:
        bot.send_message(
            call.message.chat.id,
            "📜 История операций пока пуста."
        )
        return

    text = "📜 <b>История баланса</b>\n\n"

    operation_names = {
        "admin_credit": "➕ Начисление администратором",
        "admin_debit": "➖ Списание администратором",
        "purchase": "🛒 Покупка",
        "refund": "↩️ Возврат"
    }

    for item in history:
        operation = item.get("operation", "")
        name = operation_names.get(operation, operation)

        amount = money(item.get("amount", 0))

        sign = "+" if amount > 0 else ""

        description = html.escape(
            str(item.get("description") or "")
        )

        text += (
            f"{name}\n"
            f"Сумма: <b>{sign}{amount:.2f} USDT</b>\n"
            f"{description}\n\n"
        )

    bot.send_message(
        call.message.chat.id,
        text,
        parse_mode="HTML"
    )


# ==================================================
# РУЧНОЕ ПОПОЛНЕНИЕ: ЗАПРОС ПОКУПАТЕЛЯ
# ==================================================

@bot.message_handler(func=lambda m: m.text == "💳 Пополнить баланс")
def start_topup(message):
    user_id = message.from_user.id

    topup_waiting.add(user_id)

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Отмена")

    bot.send_message(
        message.chat.id,
        "💳 <b>Пополнение баланса</b>\n\n"
        "Напиши сумму пополнения в USDT.\n\n"
        "Например: <code>25</code>\n\n"
        "После этого администратор получит запрос "
        "и сообщит тебе порядок оплаты.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.message_handler(
    func=lambda m: m.from_user.id in topup_waiting
    and bool(m.text)
    and m.text != "Отмена"
)
def process_topup_request(message):
    user = message.from_user

    try:
        amount = Decimal(
            message.text.replace(",", ".").strip()
        )

        if amount <= 0 or amount > Decimal("100000"):
            raise ValueError

        amount = amount.quantize(Decimal("0.01"))

    except (InvalidOperation, ValueError):
        bot.send_message(
            message.chat.id,
            "❌ Введи корректную сумму, например 25 или 10.50."
        )
        return

    topup_waiting.discard(user.id)

    save_user(user)

    bot.send_message(
        ADMIN_ID,
        "💳 <b>Запрос на пополнение баланса</b>\n\n"
        f"Покупатель: {html.escape(user.first_name or '')}\n"
        f"Telegram ID: <code>{user.id}</code>\n"
        f"Запрошенная сумма: <b>{amount:.2f} USDT</b>\n\n"
        "Свяжись с покупателем через поддержку. "
        "После проверки оплаты начисли средства через админ-панель.",
        parse_mode="HTML"
    )

    bot.send_message(
        message.chat.id,
        "✅ Запрос отправлен администратору.\n\n"
        "Дождись ответа по поводу оплаты.",
        reply_markup=main_menu(user.id)
    )


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
        "Выбирай товары в каталоге, проверяй баланс "
        "и оформляй покупки.",
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
        f"💰 Цена: <b>{money_text(product['price'])} USDT</b>"
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
# ПОКУПКА С БАЛАНСА
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

    price = money(product["price"])

    if price <= 0:
        bot.answer_callback_query(
            call.id,
            "Некорректная цена товара.",
            show_alert=True
        )
        return

    order_id = uuid.uuid4().hex[:10].upper()

    try:
        result = db.rpc(
            "create_paid_order",
            {
                "p_order_id": order_id,
                "p_user_id": user.id,
                "p_product": product["name"],
                "p_price": str(price)
            }
        ).execute()

        new_balance = money(result.data)

    except Exception as error:
        print("Ошибка покупки:", error)

        current_balance = get_balance(user.id)

        bot.answer_callback_query(
            call.id,
            "Не удалось купить товар. Проверь баланс.",
            show_alert=True
        )

        bot.send_message(
            user.id,
            "❌ <b>Не удалось оформить покупку.</b>\n\n"
            f"Текущий баланс: <b>{current_balance:.2f} USDT</b>\n"
            f"Цена товара: <b>{price:.2f} USDT</b>\n\n"
            "Возможно, недостаточно средств. "
            "Если баланс достаточный, обратись в поддержку.",
            parse_mode="HTML"
        )
        return

    bot.answer_callback_query(call.id, "Покупка оплачена!")

    bot.send_message(
        user.id,
        "✅ <b>Покупка успешно оплачена!</b>\n\n"
        f"Номер заказа: <code>{order_id}</code>\n"
        f"Товар: {html.escape(product['name'])}\n"
        f"Списано: <b>{price:.2f} USDT</b>\n"
        f"Остаток: <b>{new_balance:.2f} USDT</b>\n\n"
        "Заказ ожидает выдачи администратором.",
        parse_mode="HTML",
        reply_markup=main_menu(user.id)
    )

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "📦 Выдать / завершить",
            callback_data=f"order_ok:{order_id}"
        ),
        types.InlineKeyboardButton(
            "↩️ Отклонить и вернуть",
            callback_data=f"order_no:{order_id}"
        )
    )

    bot.send_message(
        ADMIN_ID,
        "🆕 <b>Новая оплаченная покупка!</b>\n\n"
        f"Номер: <code>{order_id}</code>\n"
        f"Покупатель ID: <code>{user.id}</code>\n"
        f"Товар: {html.escape(product['name'])}\n"
        f"Цена: {price:.2f} USDT\n"
        f"Остаток покупателя: {new_balance:.2f} USDT\n\n"
        "Оплата списана с внутреннего баланса.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# ==================================================
# ПОДТВЕРЖДЕНИЕ ВЫДАЧИ ЗАКАЗА
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("order_ok:"))
def confirm_order(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    order_id = call.data.split(":", 1)[1]
    order = get_order(order_id)

    if not order:
        bot.answer_callback_query(
            call.id,
            "Заказ не найден.",
            show_alert=True
        )
        return

    if order.get("status") != "Оплачен, ожидает выдачи":
        bot.answer_callback_query(
            call.id,
            "Заказ уже обработан.",
            show_alert=True
        )
        return

    if update_order(order_id, "Выдан покупателю"):
        bot.answer_callback_query(call.id, "Заказ завершён.")

        notify_user(
            order["user_id"],
            "📦 <b>Заказ выдан!</b>\n\n"
            f"Номер: <code>{order_id}</code>\n"
            f"Товар: {html.escape(str(order['product']))}\n\n"
            "Спасибо за покупку!",
        )

        bot.send_message(
            ADMIN_ID,
            f"✅ Заказ {order_id} отмечен как выданный."
        )
    else:
        bot.answer_callback_query(
            call.id,
            "Ошибка обновления.",
            show_alert=True
        )


# ==================================================
# ОТКЛОНЕНИЕ ЗАКАЗА И ВОЗВРАТ
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("order_no:"))
def reject_order(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    order_id = call.data.split(":", 1)[1]

    try:
        result = db.rpc(
            "refund_paid_order",
            {
                "p_order_id": order_id,
                "p_admin_id": ADMIN_ID
            }
        ).execute()

        new_balance = money(result.data)

        order = get_order(order_id)

        bot.answer_callback_query(
            call.id,
            "Средства возвращены."
        )

        if order:
            notify_user(
                order["user_id"],
                "↩️ <b>Заказ отклонён.</b>\n\n"
                f"Номер: <code>{order_id}</code>\n"
                f"Возвращено: <b>{money_text(order['price'])} USDT</b>\n"
                f"Новый баланс: <b>{new_balance:.2f} USDT</b>",
            )

        bot.send_message(
            ADMIN_ID,
            f"↩️ Заказ {order_id} отклонён. Средства возвращены."
        )

    except Exception as error:
        print("Ошибка возврата:", error)

        bot.answer_callback_query(
            call.id,
            "Не удалось вернуть средства. Возможно, заказ уже обработан.",
            show_alert=True
        )


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

        bot.send_message(
            message.chat.id,
            "Не удалось загрузить заказы."
        )
        return

    if not orders:
        bot.send_message(
            message.chat.id,
            "Заказов пока нет."
        )
        return

    text = "📦 <b>Мои заказы</b>\n\n"

    for order in orders[-15:]:
        text += (
            f"Номер: <code>{order.get('order_id')}</code>\n"
            f"Товар: {html.escape(str(order.get('product')))}\n"
            f"Цена: {money_text(order.get('price'))} USDT\n"
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
    topup_waiting.discard(message.from_user.id)

    bot.send_message(
        message.chat.id,
        "Действие отменено.",
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
            "💰 Управление балансами",
            callback_data="admin_balances"
        )
    )

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
# УПРАВЛЕНИЕ БАЛАНСАМИ
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data == "admin_balances")
def admin_balances(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "➕ Начислить / списать",
            callback_data="balance_adjust"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "👤 Посмотреть баланс",
            callback_data="balance_lookup"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "⬅️ В админ-панель",
            callback_data="admin_back"
        )
    )

    bot.send_message(
        ADMIN_ID,
        "💰 <b>Управление балансами</b>\n\n"
        "Здесь можно вручную начислять и списывать USDT.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda c: c.data == "balance_adjust")
def balance_adjust_start(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    admin_states[ADMIN_ID] = {
        "action": "balance_adjust"
    }

    bot.send_message(
        ADMIN_ID,
        "💰 <b>Изменение баланса</b>\n\n"
        "Отправь Telegram ID и сумму через символ |.\n\n"
        "Примеры:\n"
        "<code>123456789 | 25</code> — начислить 25 USDT\n"
        "<code>123456789 | -5</code> — списать 5 USDT\n\n"
        "Для отмены: /cancel",
        parse_mode="HTML"
    )


@bot.callback_query_handler(func=lambda c: c.data == "balance_lookup")
def balance_lookup_start(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    admin_states[ADMIN_ID] = {
        "action": "balance_lookup"
    }

    bot.send_message(
        ADMIN_ID,
        "👤 Отправь Telegram ID покупателя.\n\n"
        "Для отмены: /cancel"
    )


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

    toggle_text = (
        "🔴 Скрыть товар"
        if product["active"]
        else "🟢 Показать товар"
    )

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
        f"Цена: {money_text(product['price'])} USDT\n"
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
        "Отправь данные в одном сообщении:\n\n"
        "<code>games | Название товара | 10 | Описание товара</code>\n\n"
        "Категории:\n"
        "gifts — подарочные карты\n"
        "games — игры\n"
        "subs — подписки\n\n"
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

    # ----------------------------------------------
    # ИЗМЕНЕНИЕ БАЛАНСА
    # ----------------------------------------------

    if action == "balance_adjust":
        parts = message.text.split("|")

        if len(parts) != 2:
            bot.send_message(
                ADMIN_ID,
                "❌ Формат: Telegram ID | сумма\n"
                "Например: 123456789 | 25"
            )
            return

        try:
            target_id = int(parts[0].strip())
            amount = Decimal(
                parts[1].strip().replace(",", ".")
            ).quantize(Decimal("0.01"))

            if target_id <= 0 or amount == 0:
                raise ValueError

        except (ValueError, InvalidOperation):
            bot.send_message(
                ADMIN_ID,
                "❌ Проверь Telegram ID и сумму."
            )
            return

        try:
            result = db.rpc(
                "admin_adjust_balance",
                {
                    "p_user_id": target_id,
                    "p_amount": str(amount),
                    "p_admin_id": ADMIN_ID,
                    "p_description": "Ручная корректировка администратором"
                }
            ).execute()

            new_balance = money(result.data)

            admin_states.pop(ADMIN_ID, None)

            bot.send_message(
                ADMIN_ID,
                "✅ <b>Баланс изменён!</b>\n\n"
                f"Покупатель: <code>{target_id}</code>\n"
                f"Операция: {amount:+.2f} USDT\n"
                f"Новый баланс: <b>{new_balance:.2f} USDT</b>",
                parse_mode="HTML"
            )

            notify_user(
                target_id,
                "💰 <b>Изменение баланса</b>\n\n"
                f"Операция: <b>{amount:+.2f} USDT</b>\n"
                f"Новый баланс: <b>{new_balance:.2f} USDT</b>"
            )

        except Exception as error:
            print("Ошибка изменения баланса:", error)

            bot.send_message(
                ADMIN_ID,
                "❌ Не удалось изменить баланс.\n\n"
                "Проверь, существует ли покупатель и "
                "достаточно ли средств для списания."
            )

    # ----------------------------------------------
    # ПРОСМОТР БАЛАНСА
    # ----------------------------------------------

    elif action == "balance_lookup":
        try:
            target_id = int(message.text.strip())

            if target_id <= 0:
                raise ValueError

        except ValueError:
            bot.send_message(
                ADMIN_ID,
                "❌ Введи корректный Telegram ID."
            )
            return

        user = get_user_record(target_id)

        if not user:
            bot.send_message(
                ADMIN_ID,
                "Покупатель не найден."
            )
            return

        admin_states.pop(ADMIN_ID, None)

        bot.send_message(
            ADMIN_ID,
            "👤 <b>Информация о покупателе</b>\n\n"
            f"ID: <code>{target_id}</code>\n"
            f"Имя: {html.escape(user.get('first_name') or '')}\n"
            f"Баланс: <b>{money_text(user.get('balance', 0))} USDT</b>\n"
            f"Покупок: <b>{user.get('purchased_count', 0)}</b>",
            parse_mode="HTML"
        )

    # ----------------------------------------------
    # ИЗМЕНЕНИЕ ЦЕНЫ
    # ----------------------------------------------

    elif action == "price":
        try:
            price = Decimal(
                message.text.replace(",", ".").strip()
            )

            if price <= 0:
                raise ValueError

        except (ValueError, InvalidOperation):
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
                f"✅ Новая цена сохранена: {price:.2f} USDT"
            )
        else:
            bot.send_message(
                ADMIN_ID,
                "Не удалось изменить цену."
            )

    # ----------------------------------------------
    # ДОБАВЛЕНИЕ ТОВАРА
    # ----------------------------------------------

    elif action == "add_product":
        parts = [
            part.strip()
            for part in message.text.split("|", 3)
        ]

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
            price = Decimal(
                price_text.replace(",", ".")
            )

            if price <= 0:
                raise ValueError

        except (ValueError, InvalidOperation):
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
                f"Цена: {price:.2f} USDT"
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
                "📋 <b>Заказ</b>\n"
                f"Номер: <code>{html.escape(str(order.get('order_id')))}</code>\n"
                f"Покупатель: <code>{order.get('user_id')}</code>\n"
                f"Товар: {html.escape(str(order.get('product')))}\n"
                f"Цена: {money_text(order.get('price'))} USDT\n"
                f"Статус: {html.escape(str(order.get('status')))}",
                parse_mode="HTML"
            )

    except Exception as error:
        print("Ошибка списка заказов:", error)
        bot.send_message(ADMIN_ID, "Не удалось загрузить заказы.")


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
                f"Баланс: {money_text(user.get('balance', 0))} USDT\n"
                f"Покупок: {user.get('purchased_count', 0)}\n\n"
            )

        bot.send_message(
            ADMIN_ID,
            text,
            parse_mode="HTML"
        )

    except Exception as error:
        print("Ошибка списка покупателей:", error)
        bot.send_message(ADMIN_ID, "Не удалось загрузить покупателей.")


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
            (
                money(order.get("price", 0))
                for order in orders
                if order.get("status") != "Отклонён, средства возвращены"
            ),
            Decimal("0.00")
        )

        total_balance = sum(
            (
                money(user.get("balance", 0))
                for user in users
            ),
            Decimal("0.00")
        )

        bot.send_message(
            ADMIN_ID,
            "📊 <b>Статистика магазина</b>\n\n"
            f"Покупателей: {len(users)}\n"
            f"Заказов: {len(orders)}\n"
            f"Сумма заказов без возвратов: {total:.2f} USDT\n"
            f"Баланс всех покупателей: {total_balance:.2f} USDT",
            parse_mode="HTML"
        )

    except Exception as error:
        print("Ошибка статистики:", error)
        bot.send_message(ADMIN_ID, "Не удалось загрузить статистику.")


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
