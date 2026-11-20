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

COMMISSION = Decimal("5.00")

admin_states = {}
support_waiting = set()
topup_waiting = set()
resale_states = {}


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


def safe_text(value):
    return html.escape(str(value or ""))


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
    return money(user.get("balance", 0)) if user else Decimal("0.00")


def notify_user(user_id, text):
    try:
        bot.send_message(user_id, text, parse_mode="HTML")
    except Exception as error:
        print("Ошибка отправки пользователю:", error)


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
# ТОВАРЫ
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
            "active": True,
            "resale_allowed": False
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
# ЗАКАЗЫ
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
# БАЛАНС
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
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)

    keyboard.row("🛍 Каталог", "📦 Мои заказы")
    keyboard.row("👤 Мой профиль", "💳 Пополнить баланс")
    keyboard.row("🏪 Вторичный рынок", "🔄 Продать товар")
    keyboard.row("📋 Мои объявления")
    keyboard.row("💬 Поддержка")

    if is_admin(user_id):
        keyboard.row("⚙️ Админ-панель")

    return keyboard


# ==================================================
# ПРОФИЛЬ
# ==================================================

@bot.message_handler(func=lambda m: m.text == "👤 Мой профиль")
def show_profile(message):
    user_id = message.from_user.id
    save_user(message.from_user)

    user = get_user_record(user_id)

    if not user:
        bot.send_message(message.chat.id, "Не удалось загрузить профиль.")
        return

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        "📜 История баланса",
        callback_data="balance_history"
    ))

    bot.send_message(
        message.chat.id,
        "👤 <b>Мой профиль</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💰 Баланс: <b>{money_text(user.get('balance', 0))} USDT</b>\n"
        f"🛍 Покупок: <b>{user.get('purchased_count', 0)}</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda c: c.data == "balance_history")
def show_balance_history(call):
    bot.answer_callback_query(call.id)

    history = get_balance_history(call.from_user.id)

    if history is None:
        bot.send_message(call.message.chat.id, "Не удалось загрузить историю.")
        return

    if not history:
        bot.send_message(call.message.chat.id, "История операций пока пуста.")
        return

    names = {
        "admin_credit": "➕ Начисление администратором",
        "admin_debit": "➖ Списание администратором",
        "purchase": "🛒 Покупка",
        "refund": "↩️ Возврат",
        "resale_purchase": "🛍 Покупка на вторичном рынке",
        "resale_sale": "💰 Продажа на вторичном рынке"
    }

    text = "📜 <b>История баланса</b>\n\n"

    for item in history:
        operation = item.get("operation", "")
        amount = money(item.get("amount", 0))
        description = safe_text(item.get("description"))

        text += (
            f"{names.get(operation, operation)}\n"
            f"Сумма: <b>{amount:+.2f} USDT</b>\n"
            f"{description}\n\n"
        )

    bot.send_message(call.message.chat.id, text, parse_mode="HTML")


# ==================================================
# ПОПОЛНЕНИЕ БАЛАНСА
# ==================================================

@bot.message_handler(func=lambda m: m.text == "💳 Пополнить баланс")
def start_topup(message):
    topup_waiting.add(message.from_user.id)

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Отмена")

    bot.send_message(
        message.chat.id,
        "💳 <b>Пополнение баланса</b>\n\n"
        "Напиши сумму в USDT.\n"
        "Например: <code>25</code>",
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
        amount = Decimal(message.text.replace(",", ".").strip())

        if amount <= 0 or amount > Decimal("100000"):
            raise ValueError

        amount = amount.quantize(Decimal("0.01"))

    except (InvalidOperation, ValueError):
        bot.send_message(message.chat.id, "Введи корректную сумму.")
        return

    topup_waiting.discard(user.id)
    save_user(user)

    bot.send_message(
        ADMIN_ID,
        "💳 <b>Запрос на пополнение</b>\n\n"
        f"Пользователь: {safe_text(user.first_name)}\n"
        f"ID: <code>{user.id}</code>\n"
        f"Сумма: <b>{amount:.2f} USDT</b>\n\n"
        "Свяжись с покупателем и после проверки оплаты "
        "начисли баланс через админ-панель.",
        parse_mode="HTML"
    )

    bot.send_message(
        message.chat.id,
        "✅ Запрос отправлен администратору.",
        reply_markup=main_menu(user.id)
    )


# ==================================================
# КАТАЛОГ
# ==================================================

def catalog_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    for category_id, category_name in CATEGORIES.items():
        keyboard.add(types.InlineKeyboardButton(
            category_name,
            callback_data=f"cat_{category_id}"
        ))

    return keyboard


def products_keyboard(category):
    keyboard = types.InlineKeyboardMarkup()

    for product in get_products(active_only=True):
        if product.get("category") == category:
            keyboard.add(types.InlineKeyboardButton(
                f"{product['name']} — {money_text(product['price'])} USDT",
                callback_data=f"product:{product['product_id']}"
            ))

    keyboard.add(types.InlineKeyboardButton(
        "⬅️ Назад",
        callback_data="catalog"
    ))

    return keyboard


def product_keyboard(product_id, category):
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(types.InlineKeyboardButton(
        "🛒 Купить",
        callback_data=f"buy:{product_id}"
    ))

    keyboard.add(types.InlineKeyboardButton(
        "⬅️ Назад",
        callback_data=f"cat_{category}"
    ))

    return keyboard


@bot.message_handler(commands=["start"])
def start(message):
    save_user(message.from_user)

    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать в <b>Digital Shop</b>!\n\n"
        "Выбирай товары в каталоге или загляни на вторичный рынок.",
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

    if not product or not product.get("active"):
        bot.send_message(call.message.chat.id, "Товар недоступен.")
        return

    text = (
        f"🛍 <b>{safe_text(product['name'])}</b>\n\n"
        f"{safe_text(product.get('description'))}\n\n"
        f"💰 Цена: <b>{money_text(product['price'])} USDT</b>"
    )

    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode="HTML",
        reply_markup=product_keyboard(product_id, product["category"])
    )


# ==================================================
# ПОКУПКА ТОВАРА ИЗ ОСНОВНОГО КАТАЛОГА
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy:"))
def buy_product(call):
    product_id = call.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product or not product.get("active"):
        bot.answer_callback_query(call.id, "Товар недоступен.", show_alert=True)
        return

    user = call.from_user
    save_user(user)

    price = money(product["price"])

    if price <= 0:
        bot.answer_callback_query(call.id, "Некорректная цена.", show_alert=True)
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

        bot.answer_callback_query(
            call.id,
            "Не удалось купить товар. Проверь баланс.",
            show_alert=True
        )
        return

    bot.answer_callback_query(call.id, "Покупка оплачена!")

    bot.send_message(
        user.id,
        "✅ <b>Покупка оплачена!</b>\n\n"
        f"Номер заказа: <code>{order_id}</code>\n"
        f"Товар: {safe_text(product['name'])}\n"
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
        f"Товар: {safe_text(product['name'])}\n"
        f"Цена: {price:.2f} USDT\n"
        f"Остаток покупателя: {new_balance:.2f} USDT",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# ==================================================
# ВЫДАЧА И ВОЗВРАТ ЗАКАЗА
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("order_ok:"))
def confirm_order(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    order_id = call.data.split(":", 1)[1]
    order = get_order(order_id)

    if not order or order.get("status") != "Оплачен, ожидает выдачи":
        bot.answer_callback_query(call.id, "Заказ не найден или уже обработан.", show_alert=True)
        return

    if update_order(order_id, "Выдан покупателю"):
        bot.answer_callback_query(call.id, "Заказ завершён.")

        notify_user(
            order["user_id"],
            "📦 <b>Заказ выдан!</b>\n\n"
            f"Номер: <code>{order_id}</code>\n"
            f"Товар: {safe_text(order['product'])}\n\n"
            "Спасибо за покупку!"
        )

        bot.send_message(ADMIN_ID, f"✅ Заказ {order_id} отмечен как выданный.")
    else:
        bot.answer_callback_query(call.id, "Ошибка обновления.", show_alert=True)


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

        bot.answer_callback_query(call.id, "Средства возвращены.")

        if order:
            notify_user(
                order["user_id"],
                "↩️ <b>Заказ отклонён.</b>\n\n"
                f"Номер: <code>{order_id}</code>\n"
                f"Возвращено: {money_text(order['price'])} USDT\n"
                f"Новый баланс: {new_balance:.2f} USDT"
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
            .data or []
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
            f"Номер: <code>{safe_text(order.get('order_id'))}</code>\n"
            f"Товар: {safe_text(order.get('product'))}\n"
            f"Цена: {money_text(order.get('price'))} USDT\n"
            f"Статус: {safe_text(order.get('status'))}\n\n"
        )

    bot.send_message(message.chat.id, text, parse_mode="HTML")


# ==================================================
# ВТОРИЧНЫЙ РЫНОК: ПОЛУЧЕНИЕ ОБЪЯВЛЕНИЙ
# ==================================================

def get_listing(listing_id):
    try:
        result = (
            db.table("resale_listings")
            .select("*")
            .eq("id", listing_id)
            .eq("status", "active")
            .execute()
            .data
        )
        return result[0] if result else None
    except Exception as error:
        print("Ошибка получения объявления:", error)
        return None


def get_good(good_id):
    try:
        result = (
            db.table("resale_goods")
            .select("*")
            .eq("id", good_id)
            .execute()
            .data
        )
        return result[0] if result else None
    except Exception as error:
        print("Ошибка получения товара перепродажи:", error)
        return None


def get_resale_product(good):
    if not good:
        return None
    return get_product(good.get("product_id"))


# ==================================================
# ВТОРИЧНЫЙ РЫНОК: СПИСОК ОБЪЯВЛЕНИЙ
# ==================================================

@bot.message_handler(func=lambda m: m.text == "🏪 Вторичный рынок")
def resale_market(message):
    try:
        listings = (
            db.table("resale_listings")
            .select("*")
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(30)
            .execute()
            .data or []
        )
    except Exception as error:
        print("Ошибка рынка:", error)
        bot.send_message(message.chat.id, "Не удалось загрузить вторичный рынок.")
        return

    if not listings:
        bot.send_message(message.chat.id, "🏪 Пока нет активных объявлений.")
        return

    bot.send_message(
        message.chat.id,
        "🏪 <b>Вторичный рынок</b>\n\nВыбери объявление:",
        parse_mode="HTML"
    )

    for listing in listings:
        good = get_good(listing["good_id"])
        product = get_resale_product(good)

        if not good or not product:
            continue

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton(
            "👀 Посмотреть объявление",
            callback_data=f"resale_view:{listing['id']}"
        ))

        bot.send_message(
            message.chat.id,
            f"🛍 <b>{safe_text(product['name'])}</b>\n"
            f"💰 Цена: <b>{money_text(listing['asking_price'])} USDT</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )


# ==================================================
# ВТОРИЧНЫЙ РЫНОК: ПРОСМОТР ОБЪЯВЛЕНИЯ
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("resale_view:"))
def resale_view(call):
    listing_id = int(call.data.split(":", 1)[1])
    listing = get_listing(listing_id)

    if not listing:
        bot.answer_callback_query(call.id, "Объявление недоступно.", show_alert=True)
        return

    if listing["seller_id"] == call.from_user.id:
        bot.answer_callback_query(call.id, "Нельзя купить собственное объявление.", show_alert=True)
        return

    good = get_good(listing["good_id"])
    product = get_resale_product(good)

    if not good or not product:
        bot.answer_callback_query(call.id, "Товар не найден.", show_alert=True)
        return

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        "🛒 Купить за внутренний баланс",
        callback_data=f"resale_buy:{listing_id}"
    ))

    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        "🏪 <b>Объявление вторичного рынка</b>\n\n"
        f"Товар: <b>{safe_text(product['name'])}</b>\n"
        f"Цена: <b>{money_text(listing['asking_price'])} USDT</b>\n"
        f"Комиссия магазина: <b>{COMMISSION:.0f}%</b>\n\n"
        "После успешной оплаты цифровой код будет отправлен тебе в личные сообщения.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# ==================================================
# ВТОРИЧНЫЙ РЫНОК: ПОКУПКА ОБЪЯВЛЕНИЯ
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("resale_buy:"))
def resale_buy(call):
    try:
        listing_id = int(call.data.split(":", 1)[1])
    except ValueError:
        bot.answer_callback_query(call.id, "Некорректное объявление.", show_alert=True)
        return

    listing = get_listing(listing_id)

    if not listing:
        bot.answer_callback_query(call.id, "Объявление уже недоступно.", show_alert=True)
        return

    if listing["seller_id"] == call.from_user.id:
        bot.answer_callback_query(call.id, "Нельзя купить собственный товар.", show_alert=True)
        return

    price = money(listing["asking_price"])

    if get_balance(call.from_user.id) < price:
        bot.answer_callback_query(
            call.id,
            "Недостаточно средств на балансе.",
            show_alert=True
        )
        return

    try:
        result = db.rpc(
            "buy_resale_listing",
            {
                "p_listing_id": listing_id,
                "p_buyer_id": call.from_user.id,
                "p_commission_percent": str(COMMISSION)
            }
        ).execute()

        data = result.data

        if isinstance(data, list):
            data = data[0] if data else {}

        if not isinstance(data, dict):
            raise ValueError("Неожиданный ответ Supabase")

        secret_code = data.get("secret_code")

        if not secret_code:
            raise ValueError("Код не получен от базы данных")

        transaction_id = data.get("transaction_id", "—")

        bot.answer_callback_query(call.id, "Покупка успешна!")

        # Код отправляется только покупателю в личные сообщения.
        try:
            bot.send_message(
                call.from_user.id,
                "✅ <b>Покупка на вторичном рынке успешна!</b>\n\n"
                f"Номер операции: <code>{transaction_id}</code>\n\n"
                "<b>Твой цифровой код:</b>\n"
                f"<code>{safe_text(secret_code)}</code>\n\n"
                "Сохрани код. Не отправляй его посторонним.",
                parse_mode="HTML"
            )
        except Exception as delivery_error:
            print("Ошибка доставки кода:", delivery_error)

            bot.send_message(
                ADMIN_ID,
                "⚠️ <b>Внимание: покупка на вторичном рынке прошла, "
                "но отправка кода покупателю не удалась.</b>\n\n"
                f"Покупатель ID: <code>{call.from_user.id}</code>\n"
                f"Объявление: <code>{listing_id}</code>\n"
                f"Операция: <code>{transaction_id}</code>\n\n"
                "Проверь доставку и свяжись с покупателем.",
                parse_mode="HTML"
            )

        notify_user(
            listing["seller_id"],
            "💰 <b>Твой товар купили!</b>\n\n"
            f"Объявление: <code>{listing_id}</code>\n"
            f"Цена продажи: <b>{price:.2f} USDT</b>\n"
            f"Комиссия магазина: <b>{(price * COMMISSION / 100):.2f} USDT</b>\n"
            f"Твоё начисление: <b>{(price * (100 - COMMISSION) / 100):.2f} USDT</b>"
        )

    except Exception as error:
        print("Ошибка покупки на вторичном рынке:", error)
        bot.answer_callback_query(
            call.id,
            "Покупка не состоялась. Возможно, объявление уже купили.",
            show_alert=True
        )


# ==================================================
# ВТОРИЧНЫЙ РЫНОК: МОИ ОБЪЯВЛЕНИЯ
# ==================================================

@bot.message_handler(func=lambda m: m.text == "📋 Мои объявления")
def my_resale_listings(message):
    try:
        listings = (
            db.table("resale_listings")
            .select("*")
            .eq("seller_id", message.from_user.id)
            .eq("status", "active")
            .order("created_at", desc=True)
            .execute()
            .data or []
        )
    except Exception as error:
        print("Ошибка моих объявлений:", error)
        bot.send_message(message.chat.id, "Не удалось загрузить объявления.")
        return

    if not listings:
        bot.send_message(message.chat.id, "У тебя пока нет активных объявлений.")
        return

    bot.send_message(message.chat.id, "📋 <b>Мои объявления</b>", parse_mode="HTML")

    for listing in listings:
        good = get_good(listing["good_id"])
        product = get_resale_product(good)

        if not good or not product:
            continue

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton(
            "❌ Снять объявление",
            callback_data=f"resale_remove:{listing['id']}"
        ))

        bot.send_message(
            message.chat.id,
            f"🛍 <b>{safe_text(product['name'])}</b>\n"
            f"Цена: <b>{money_text(listing['asking_price'])} USDT</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )


# ==================================================
# ВТОРИЧНЫЙ РЫНОК: СНЯТИЕ ОБЪЯВЛЕНИЯ
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("resale_remove:"))
def resale_remove(call):
    try:
        listing_id = int(call.data.split(":", 1)[1])
    except ValueError:
        bot.answer_callback_query(call.id, "Некорректный номер.")
        return

    listing = get_listing(listing_id)

    if not listing or listing["seller_id"] != call.from_user.id:
        bot.answer_callback_query(call.id, "Объявление не найдено.", show_alert=True)
        return

    try:
        db.table("resale_listings").update({
            "status": "removed"
        }).eq("id", listing_id).eq(
            "seller_id", call.from_user.id
        ).execute()

        db.table("resale_goods").update({
            "status": "removed"
        }).eq("id", listing["good_id"]).eq(
            "seller_id", call.from_user.id
        ).execute()

        bot.answer_callback_query(call.id, "Объявление снято.")
        bot.send_message(call.message.chat.id, "✅ Объявление снято с продажи.")

    except Exception as error:
        print("Ошибка снятия объявления:", error)
        bot.answer_callback_query(call.id, "Не удалось снять объявление.", show_alert=True)


# ==================================================
# ВТОРИЧНЫЙ РЫНОК: НАЧАЛО ПРОДАЖИ
# ==================================================

@bot.message_handler(func=lambda m: m.text == "🔄 Продать товар")
def resale_start(message):
    user_id = message.from_user.id
    save_user(message.from_user)

    try:
        orders = (
            db.table("orders")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "Выдан покупателю")
            .order("created_at", desc=True)
            .execute()
            .data or []
        )

        used_goods = (
            db.table("resale_goods")
            .select("original_order_id")
            .eq("seller_id", user_id)
            .execute()
            .data or []
        )

        used_order_ids = {
            item["original_order_id"] for item in used_goods
        }

    except Exception as error:
        print("Ошибка загрузки заказов для перепродажи:", error)
        bot.send_message(message.chat.id, "Не удалось загрузить твои заказы.")
        return

    available_orders = [
        order for order in orders
        if order.get("order_id") not in used_order_ids
    ]

    if not available_orders:
        bot.send_message(
            message.chat.id,
            "Пока нет выданных заказов, которые можно выставить на продажу.\n\n"
            "Также перепродажа должна быть разрешена для самого товара."
        )
        return

    keyboard = types.InlineKeyboardMarkup()

    for order in available_orders[:20]:
        product = None

        for item in get_products():
            if item["name"] == order.get("product"):
                product = item
                break

        if not product or not product.get("resale_allowed", False):
            continue

        keyboard.add(types.InlineKeyboardButton(
            f"{product['name']} — заказ {order['order_id']}",
            callback_data=f"resale_order:{order['order_id']}"
        ))

    if not keyboard.keyboard:
        bot.send_message(
            message.chat.id,
            "Нет заказов с разрешённой перепродажей.\n\n"
            "Администратор должен включить перепродажу для нужных товаров."
        )
        return

    bot.send_message(
        message.chat.id,
        "🔄 <b>Продажа товара</b>\n\n"
        "Выбери выданный заказ, который хочешь выставить на вторичный рынок:",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# ==================================================
# ВТОРИЧНЫЙ РЫНОК: ВЫБОР ЗАКАЗА
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("resale_order:"))
def resale_select_order(call):
    order_id = call.data.split(":", 1)[1]
    order = get_order(order_id)

    if not order:
        bot.answer_callback_query(call.id, "Заказ не найден.", show_alert=True)
        return

    if order.get("user_id") != call.from_user.id:
        bot.answer_callback_query(call.id, "Это не твой заказ.", show_alert=True)
        return

    if order.get("status") != "Выдан покупателю":
        bot.answer_callback_query(call.id, "Заказ ещё не выдан.", show_alert=True)
        return

    product = None

    for item in get_products():
        if item["name"] == order.get("product"):
            product = item
            break

    if not product or not product.get("resale_allowed", False):
        bot.answer_callback_query(
            call.id,
            "Перепродажа этого товара не разрешена.",
            show_alert=True
        )
        return

    resale_states[call.from_user.id] = {
        "step": "code",
        "order_id": order_id
    }

    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        "🔐 <b>Выставление товара на продажу</b>\n\n"
        f"Товар: <b>{safe_text(order['product'])}</b>\n\n"
        "Отправь цифровой код товара одним сообщением.\n\n"
        "Код будет скрыт от других пользователей и передан покупателю "
        "только после успешной оплаты.\n\n"
        "Не отправляй пароли или данные от аккаунтов.\n\n"
        "Для отмены напиши /cancel_resale.",
        parse_mode="HTML"
    )


# ==================================================
# ВТОРИЧНЫЙ РЫНОК: ОТМЕНА
# ==================================================

@bot.message_handler(commands=["cancel_resale"])
def cancel_resale(message):
    resale_states.pop(message.from_user.id, None)

    bot.send_message(
        message.chat.id,
        "Выставление товара на продажу отменено.",
        reply_markup=main_menu(message.from_user.id)
    )


# ==================================================
# ВТОРИЧНЫЙ РЫНОК: ВВОД КОДА И ЦЕНЫ
# ==================================================

@bot.message_handler(
    func=lambda m: m.from_user.id in resale_states
    and bool(m.text)
    and not m.text.startswith("/")
)
def process_resale_input(message):
    user_id = message.from_user.id
    state = resale_states.get(user_id)

    if not state:
        return

    if message.text == "Отмена":
        resale_states.pop(user_id, None)
        bot.send_message(
            message.chat.id,
            "Продажа отменена.",
            reply_markup=main_menu(user_id)
        )
        return

    if state["step"] == "code":
        code = message.text.strip()

        if len(code) < 4 or len(code) > 500:
            bot.send_message(
                message.chat.id,
                "❌ Код должен содержать от 4 до 500 символов. Попробуй ещё раз."
            )
            return

        state["secret_code"] = code
        state["step"] = "price"

        bot.send_message(
            message.chat.id,
            "💰 Теперь отправь цену, за которую хочешь продать товар в USDT.\n\n"
            "Например: <code>15</code> или <code>12.50</code>",
            parse_mode="HTML"
        )
        return

    if state["step"] == "price":
        try:
            price = Decimal(message.text.replace(",", ".").strip())

            if price <= 0 or price > Decimal("100000"):
                raise ValueError

            price = price.quantize(Decimal("0.01"))

        except (InvalidOperation, ValueError):
            bot.send_message(
                message.chat.id,
                "❌ Введи корректную цену. Например: 15 или 12.50"
            )
            return

        try:
            result = db.rpc(
                "create_resale_listing",
                {
                    "p_order_id": state["order_id"],
                    "p_seller_id": user_id,
                    "p_secret_code": state["secret_code"],
                    "p_price": str(price)
                }
            ).execute()

            listing_id = result.data

            resale_states.pop(user_id, None)

            bot.send_message(
                message.chat.id,
                "✅ <b>Товар выставлен на вторичный рынок!</b>\n\n"
                f"Номер объявления: <code>{listing_id}</code>\n"
                f"Цена: <b>{price:.2f} USDT</b>\n"
                f"Комиссия магазина: <b>{COMMISSION:.0f}%</b>\n"
                f"Ты получишь после продажи: "
                f"<b>{(price * (100 - COMMISSION) / 100):.2f} USDT</b>\n\n"
                "Код будет передан покупателю после оплаты.",
                parse_mode="HTML",
                reply_markup=main_menu(user_id)
            )

        except Exception as error:
            print("Ошибка создания объявления:", error)
            resale_states.pop(user_id, None)

            bot.send_message(
                message.chat.id,
                "❌ Не удалось выставить товар.\n\n"
                "Проверь, что заказ выдан, товар разрешён для перепродажи "
                "и этот заказ ещё не выставлялся.",
                reply_markup=main_menu(user_id)
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
    resale_states.pop(message.from_user.id, None)

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
        f"Пользователь: {safe_text(user.first_name)}\n"
        f"ID: <code>{user.id}</code>\n\n"
        f"{safe_text(message.text)}",
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

    buttons = [
        ("💰 Управление балансами", "admin_balances"),
        ("🛍 Управление товарами", "manage_products"),
        ("📋 Заказы", "admin_orders"),
        ("👥 Покупатели", "admin_users"),
        ("📊 Статистика", "admin_stats")
    ]

    for title, callback in buttons:
        keyboard.add(types.InlineKeyboardButton(
            title,
            callback_data=callback
        ))

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
# БАЛАНСЫ: АДМИН
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data == "admin_balances")
def admin_balances(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        "➕ Начислить / списать",
        callback_data="balance_adjust"
    ))
    keyboard.add(types.InlineKeyboardButton(
        "👤 Посмотреть баланс",
        callback_data="balance_lookup"
    ))
    keyboard.add(types.InlineKeyboardButton(
        "⬅️ В админ-панель",
        callback_data="admin_back"
    ))

    bot.send_message(
        ADMIN_ID,
        "💰 <b>Управление балансами</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda c: c.data == "balance_adjust")
def balance_adjust_start(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)
    admin_states[ADMIN_ID] = {"action": "balance_adjust"}

    bot.send_message(
        ADMIN_ID,
        "Отправь Telegram ID и сумму через |.\n\n"
        "Пример: <code>123456789 | 25</code>\n"
        "Списание: <code>123456789 | -5</code>\n\n"
        "Отмена: /cancel",
        parse_mode="HTML"
    )


@bot.callback_query_handler(func=lambda c: c.data == "balance_lookup")
def balance_lookup_start(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)
    admin_states[ADMIN_ID] = {"action": "balance_lookup"}

    bot.send_message(
        ADMIN_ID,
        "Отправь Telegram ID покупателя.\nОтмена: /cancel"
    )


# ==================================================
# ТОВАРЫ: АДМИН
# ==================================================

def show_manage_products(chat_id):
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(types.InlineKeyboardButton(
        "➕ Добавить товар",
        callback_data="add_product"
    ))

    for product in get_products():
        status = "🟢" if product.get("active") else "🔴"
        keyboard.add(types.InlineKeyboardButton(
            f"{status} {product['name']}",
            callback_data=f"manage:{product['product_id']}"
        ))

    keyboard.add(types.InlineKeyboardButton(
        "⬅️ В админ-панель",
        callback_data="admin_back"
    ))

    bot.send_message(
        chat_id,
        "🛍 <b>Управление товарами</b>\n\n"
        "🟢 — активен\n🔴 — скрыт",
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

    status = "🟢 Активен" if product.get("active") else "🔴 Скрыт"
    resale_status = "✅ Разрешена" if product.get("resale_allowed") else "❌ Запрещена"

    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(types.InlineKeyboardButton(
        "✏️ Изменить цену",
        callback_data=f"price:{product_id}"
    ))

    keyboard.add(types.InlineKeyboardButton(
        "🔄 Включить / выключить товар",
        callback_data=f"toggle:{product_id}"
    ))

    keyboard.add(types.InlineKeyboardButton(
        "🗑 Удалить товар",
        callback_data=f"delete:{product_id}"
    ))

    keyboard.add(types.InlineKeyboardButton(
        "⬅️ К списку товаров",
        callback_data="manage_products"
    ))

    bot.send_message(
        ADMIN_ID,
        f"🛍 <b>{safe_text(product['name'])}</b>\n\n"
        f"Цена: {money_text(product['price'])} USDT\n"
        f"Статус: {status}\n"
        f"Перепродажа: {resale_status}\n"
        f"Описание: {safe_text(product.get('description'))}\n\n"
        "Разрешение на перепродажу меняется отдельно через SQL.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("price:"))
def start_price_change(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    product_id = call.data.split(":", 1)[1]

    admin_states[ADMIN_ID] = {
        "action": "price",
        "product_id": product_id
    }

    bot.send_message(ADMIN_ID, "Введи новую цену. Например: 15.50\nОтмена: /cancel")


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

    if toggle_product(product_id, not product.get("active", False)):
        bot.answer_callback_query(call.id, "Статус изменён.")
        show_manage_products(ADMIN_ID)
    else:
        bot.answer_callback_query(call.id, "Ошибка.")


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
    bot.send_message(ADMIN_ID, "⚠️ Точно удалить товар?", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delete_yes:"))
def delete_product_confirm(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    product_id = call.data.split(":", 1)[1]

    if delete_product(product_id):
        bot.answer_callback_query(call.id, "Удалено.")
        show_manage_products(ADMIN_ID)
    else:
        bot.answer_callback_query(call.id, "Ошибка удаления.")


@bot.callback_query_handler(func=lambda c: c.data == "add_product")
def start_add_product(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)
    admin_states[ADMIN_ID] = {"action": "add_product"}

    bot.send_message(
        ADMIN_ID,
        "➕ <b>Добавление товара</b>\n\n"
        "Формат:\n"
        "<code>games | Название | 10 | Описание</code>\n\n"
        "Категории: gifts, games, subs\n"
        "Отмена: /cancel",
        parse_mode="HTML"
    )


# ==================================================
# АДМИН: ОБРАБОТКА ТЕКСТОВЫХ ДЕЙСТВИЙ
# ==================================================

@bot.message_handler(commands=["cancel"])
def cancel_admin_action(message):
    if not is_admin(message.from_user.id):
        return

    admin_states.pop(ADMIN_ID, None)
    bot.send_message(ADMIN_ID, "Действие отменено.")


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

    if action == "balance_adjust":
        parts = message.text.split("|")

        if len(parts) != 2:
            bot.send_message(ADMIN_ID, "Формат: Telegram ID | сумма")
            return

        try:
            target_id = int(parts[0].strip())
            amount = Decimal(parts[1].strip().replace(",", ".")).quantize(Decimal("0.01"))

            if target_id <= 0 or amount == 0:
                raise ValueError

        except (ValueError, InvalidOperation):
            bot.send_message(ADMIN_ID, "Проверь ID и сумму.")
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
                f"Операция: {amount:+.2f} USDT\n"
                f"Новый баланс: {new_balance:.2f} USDT"
            )

        except Exception as error:
            print("Ошибка изменения баланса:", error)
            bot.send_message(ADMIN_ID, "Не удалось изменить баланс.")

    elif action == "balance_lookup":
        try:
            target_id = int(message.text.strip())
        except ValueError:
            bot.send_message(ADMIN_ID, "Введи корректный Telegram ID.")
            return

        user = get_user_record(target_id)

        if not user:
            bot.send_message(ADMIN_ID, "Покупатель не найден.")
            return

        admin_states.pop(ADMIN_ID, None)

        bot.send_message(
            ADMIN_ID,
            "👤 <b>Покупатель</b>\n\n"
            f"ID: <code>{target_id}</code>\n"
            f"Имя: {safe_text(user.get('first_name'))}\n"
            f"Баланс: {money_text(user.get('balance', 0))} USDT\n"
            f"Покупок: {user.get('purchased_count', 0)}",
            parse_mode="HTML"
        )

    elif action == "price":
        try:
            price = Decimal(message.text.replace(",", ".").strip())

            if price <= 0:
                raise ValueError

        except (ValueError, InvalidOperation):
            bot.send_message(ADMIN_ID, "Введи положительную цену.")
            return

        if change_price(state["product_id"], price):
            admin_states.pop(ADMIN_ID, None)
            bot.send_message(ADMIN_ID, f"✅ Цена изменена: {price:.2f} USDT")
        else:
            bot.send_message(ADMIN_ID, "Не удалось изменить цену.")

    elif action == "add_product":
        parts = [p.strip() for p in message.text.split("|", 3)]

        if len(parts) != 4:
            bot.send_message(ADMIN_ID, "Формат: games | Название | 10 | Описание")
            return

        category, name, price_text, description = parts

        if category not in CATEGORIES or not name or not description:
            bot.send_message(ADMIN_ID, "Проверь категорию, название и описание.")
            return

        try:
            price = Decimal(price_text.replace(",", "."))
            if price <= 0:
                raise ValueError
        except (ValueError, InvalidOperation):
            bot.send_message(ADMIN_ID, "Цена должна быть положительным числом.")
            return

        product_id = "item_" + uuid.uuid4().hex[:12]

        if add_product(product_id, category, name, price, description):
            admin_states.pop(ADMIN_ID, None)
            bot.send_message(ADMIN_ID, f"✅ Товар добавлен: {name}")
            show_manage_products(ADMIN_ID)
        else:
            bot.send_message(ADMIN_ID, "Не удалось добавить товар.")


# ==================================================
# АДМИН: ЗАКАЗЫ
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data == "admin_orders")
def admin_orders(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    try:
        orders = db.table("orders").select("*").execute().data or []

        if not orders:
            bot.send_message(ADMIN_ID, "Заказов пока нет.")
            return

        for order in orders[-20:]:
            bot.send_message(
                ADMIN_ID,
                "📋 <b>Заказ</b>\n"
                f"Номер: <code>{safe_text(order.get('order_id'))}</code>\n"
                f"Покупатель: <code>{order.get('user_id')}</code>\n"
                f"Товар: {safe_text(order.get('product'))}\n"
                f"Цена: {money_text(order.get('price'))} USDT\n"
                f"Статус: {safe_text(order.get('status'))}",
                parse_mode="HTML"
            )

    except Exception as error:
        print("Ошибка списка заказов:", error)
        bot.send_message(ADMIN_ID, "Не удалось загрузить заказы.")


# ==================================================
# АДМИН: ПОКУПАТЕЛИ
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data == "admin_users")
def admin_users(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    try:
        users = db.table("users").select("*").execute().data or []

        if not users:
            bot.send_message(ADMIN_ID, "Покупателей пока нет.")
            return

        text = "👥 <b>Покупатели</b>\n\n"

        for user in users[-30:]:
            text += (
                f"{safe_text(user.get('first_name') or 'Без имени')} "
                f"— ID: <code>{user.get('user_id')}</code>\n"
                f"Баланс: {money_text(user.get('balance', 0))} USDT\n"
                f"Покупок: {user.get('purchased_count', 0)}\n\n"
            )

        bot.send_message(ADMIN_ID, text, parse_mode="HTML")

    except Exception as error:
        print("Ошибка списка покупателей:", error)
        bot.send_message(ADMIN_ID, "Не удалось загрузить покупателей.")


# ==================================================
# АДМИН: СТАТИСТИКА
# ==================================================

@bot.callback_query_handler(func=lambda c: c.data == "admin_stats")
def admin_stats(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.")
        return

    bot.answer_callback_query(call.id)

    try:
        users = db.table("users").select("*").execute().data or []
        orders = db.table("orders").select("*").execute().data or []

        total = sum(
            (
                money(order.get("price", 0))
                for order in orders
                if order.get("status") != "Отклонён, средства возвращены"
            ),
            Decimal("0.00")
        )

        total_balance = sum(
            (money(user.get("balance", 0)) for user in users),
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
    print("Каталог и вторичный рынок подключены.")

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
