import os
import re
import html
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

import telebot
from telebot import types
from supabase import create_client


# =========================================================
# НАСТРОЙКИ
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

WALLET = "TNYOixEzXVbuAxOpVmoXGvAFFMxn4NKgKl"
NETWORK = "TRC20"
ASSET = "USDT"

if not all([BOT_TOKEN, ADMIN_ID, SUPABASE_URL, SUPABASE_KEY]):
    raise RuntimeError("Не заданы BOT_TOKEN, ADMIN_ID, SUPABASE_URL или SUPABASE_KEY")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
db = create_client(SUPABASE_URL, SUPABASE_KEY)

# Временные состояния диалогов.
# При перезапуске бота они сбрасываются, но заказы и оплаты хранятся в Supabase.
states = {}

# Для ответов поддержки администратором в рамках одного запуска.
support_replies = {}


# =========================================================
# ОБЩИЕ ФУНКЦИИ
# =========================================================

def esc(value):
    return html.escape(str(value or ""))


def money(value):
    try:
        return f"{Decimal(str(value)):,.2f}".replace(",", " ")
    except Exception:
        return "0.00"


def rpc(name, params):
    result = db.rpc(name, params).execute()
    return result.data


def first_row(data):
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def save_user(user):
    db.table("users").upsert({
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name
    }, on_conflict="user_id").execute()


def is_admin(user_id):
    return int(user_id) == ADMIN_ID


def clear_state(user_id):
    states.pop(user_id, None)


def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )

    markup.row("🛍 Каталог", "📦 Мои заказы")
    markup.row("💳 История платежей", "👤 Профиль")
    markup.row("🆘 Поддержка")

    if is_admin(user_id):
        markup.row("⚙️ Админ-панель")

    return markup


def send_home(chat_id, text="Главное меню"):
    clear_state(chat_id)
    bot.send_message(chat_id, text, reply_markup=main_menu(chat_id))


def get_product(product_id):
    result = (
        db.table("products")
        .select("*")
        .eq("product_id", str(product_id))
        .limit(1)
        .execute()
    )
    return first_row(result.data)


def get_payment(payment_ref):
    result = (
        db.table("crypto_payments")
        .select("*")
        .eq("payment_ref", payment_ref)
        .limit(1)
        .execute()
    )
    return first_row(result.data)


def payment_keyboard(payment_ref):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "✅ Я оплатил",
        callback_data=f"report:{payment_ref}"
    ))
    return markup


# =========================================================
# СТАРТ И ПРОФИЛЬ
# =========================================================

@bot.message_handler(commands=["start"])
def start(message):
    save_user(message.from_user)
    send_home(
        message.chat.id,
        "Добро пожаловать в магазин цифровых товаров!"
    )


@bot.message_handler(commands=["cancel"])
def cancel(message):
    clear_state(message.from_user.id)
    send_home(message.chat.id, "Действие отменено.")


@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile(message):
    save_user(message.from_user)

    user = message.from_user
    username = f"@{esc(user.username)}" if user.username else "Не указан"

    text = (
        "<b>👤 Ваш профиль</b>\n\n"
        f"ID: <code>{user.id}</code>\n"
        f"Имя: {esc(user.first_name)}\n"
        f"Username: {username}\n\n"
        "Все цены магазина указаны в USDT."
    )

    bot.send_message(message.chat.id, text)


# =========================================================
# КАТАЛОГ И КАРТОЧКИ ТОВАРОВ
# =========================================================

@bot.message_handler(func=lambda m: m.text == "🛍 Каталог")
def catalog(message):
    save_user(message.from_user)

    result = (
        db.table("products")
        .select("product_id,name,category,price")
        .eq("active", True)
        .order("name")
        .execute()
    )

    products = result.data or []

    markup = types.InlineKeyboardMarkup(row_width=1)

    for product in products:
        title = (
            f"{product['name']} — "
            f"{money(product['price'])} USDT"
        )
        markup.add(types.InlineKeyboardButton(
            title,
            callback_data=f"product:{product['product_id']}"
        ))

    markup.add(types.InlineKeyboardButton(
        "🔄 Перепродажа",
        callback_data="resale_catalog"
    ))

    bot.send_message(
        message.chat.id,
        "<b>🛍 Каталог товаров</b>\n\nВыберите товар:",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("product:"))
def product_card(call):
    product_id = call.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product or not product.get("active"):
        bot.answer_callback_query(call.id, "Товар недоступен.")
        return

    text = (
        f"<b>{esc(product.get('name'))}</b>\n\n"
        f"ID: <code>{esc(product.get('product_id'))}</code>\n"
        f"Категория: {esc(product.get('category'))}\n"
        f"Стоимость: <b>{money(product.get('price'))} USDT</b>\n\n"
        f"<b>Информация:</b>\n"
        f"{esc(product.get('description'))}\n\n"
        f"Происхождение: {esc(product.get('origin_status'))}\n"
        f"Владелец: {esc(product.get('owner_status'))}\n"
        f"Передача: {esc(product.get('transfer_status'))}\n"
    )

    verification = product.get("verification_info") or ""

    markup = types.InlineKeyboardMarkup()
    if verification.strip():
        markup.add(types.InlineKeyboardButton(
            "🔎 Проверить сведения",
            callback_data=f"verify:{product_id}"
        ))

    markup.add(types.InlineKeyboardButton(
        "🛒 Купить",
        callback_data=f"buy:{product_id}"
    ))

    markup.add(types.InlineKeyboardButton(
        "⬅️ В каталог",
        callback_data="back_catalog"
    ))

    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("verify:"))
def verify_product(call):
    product_id = call.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product:
        bot.answer_callback_query(call.id, "Товар не найден.")
        return

    info = product.get("verification_info") or "Дополнительные сведения не указаны."

    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "<b>🔎 Дополнительные сведения</b>\n\n" + esc(info)
    )


@bot.callback_query_handler(func=lambda c: c.data == "back_catalog")
def back_catalog(call):
    bot.answer_callback_query(call.id)

    result = (
        db.table("products")
        .select("product_id,name,price")
        .eq("active", True)
        .order("name")
        .execute()
    )

    markup = types.InlineKeyboardMarkup(row_width=1)

    for p in result.data or []:
        markup.add(types.InlineKeyboardButton(
            f"{p['name']} — {money(p['price'])} USDT",
            callback_data=f"product:{p['product_id']}"
        ))

    markup.add(types.InlineKeyboardButton(
        "🔄 Перепродажа",
        callback_data="resale_catalog"
    ))

    bot.send_message(
        call.message.chat.id,
        "<b>🛍 Каталог</b>",
        reply_markup=markup
    )


# =========================================================
# ПОКУПКА И ОПЛАТА
# =========================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy:"))
def buy_product(call):
    user_id = call.from_user.id
    product_id = call.data.split(":", 1)[1]

    save_user(call.from_user)

    try:
        data = rpc("create_purchase_payment", {
            "p_user_id": user_id,
            "p_product_id": product_id
        })

        row = first_row(data)

        if not row:
            bot.answer_callback_query(
                call.id,
                "Не удалось создать заказ. Проверьте наличие товара.",
                show_alert=True
            )
            return

        payment_ref = row["payment_ref"]
        order_id = row["order_id"]
        product_name = row.get("product_name", "Цифровой товар")
        price = row["price"]
        wallet = row.get("wallet_address") or WALLET

        text = (
            "<b>🧾 Заказ создан</b>\n\n"
            f"Товар: {esc(product_name)}\n"
            f"Номер заказа: <code>{esc(order_id)}</code>\n"
            f"Сумма: <b>{money(price)} USDT</b>\n\n"
            f"<b>Сеть:</b> {NETWORK}\n"
            f"<b>Монета:</b> {ASSET}\n"
            f"<b>Кошелёк для оплаты:</b>\n"
            f"<code>{esc(wallet)}</code>\n\n"
            "Переведите точную сумму в USDT по сети TRC20.\n"
            "После перевода нажмите «Я оплатил».\n\n"
            "Код товара будет выдан только после проверки оплаты администратором."
        )

        bot.answer_callback_query(call.id, "Заказ создан.")
        bot.send_message(
            call.message.chat.id,
            text,
            reply_markup=payment_keyboard(payment_ref)
        )

    except Exception:
        logging.exception("Ошибка создания покупки")
        bot.answer_callback_query(
            call.id,
            "Ошибка создания заказа. Попробуйте позже.",
            show_alert=True
        )


# =========================================================
# СООБЩЕНИЕ ОБ ОПЛАТЕ
# =========================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("report:"))
def report_payment_start(call):
    payment_ref = call.data.split(":", 1)[1]
    payment = get_payment(payment_ref)

    if not payment or int(payment["user_id"]) != call.from_user.id:
        bot.answer_callback_query(call.id, "Платёж не найден.", show_alert=True)
        return

    if payment["status"] != "awaiting_payment":
        bot.answer_callback_query(
            call.id,
            f"Статус платежа: {payment['status']}",
            show_alert=True
        )
        return

    # Перед отправкой отчёта помечаем просроченные неоплаченные платежи.
    try:
        rpc("expire_unpaid_crypto_payments", {})
    except Exception:
        logging.exception("Не удалось проверить истёкшие платежи")

    payment = get_payment(payment_ref)

    if not payment or payment["status"] != "awaiting_payment":
        bot.answer_callback_query(
            call.id,
            "Время оплаты истекло или платёж уже обработан.",
            show_alert=True
        )
        return

    states[call.from_user.id] = {
        "action": "report_payment",
        "payment_ref": payment_ref
    }

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "Пропустить хеш транзакции",
        callback_data=f"nohash:{payment_ref}"
    ))

    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "Отправьте хеш транзакции (TXID) сообщением.\n"
        "Если не хотите его указывать, нажмите кнопку ниже.",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("nohash:"))
def report_without_hash(call):
    payment_ref = call.data.split(":", 1)[1]
    submit_payment_report(call.from_user.id, payment_ref, None)
    bot.answer_callback_query(call.id)


def submit_payment_report(user_id, payment_ref, tx_hash):
    try:
        rpc("expire_unpaid_crypto_payments", {})
    except Exception:
        logging.exception("Ошибка проверки срока платежа")

    payment = get_payment(payment_ref)

    if not payment or int(payment["user_id"]) != user_id:
        bot.send_message(user_id, "Платёж не найден.")
        clear_state(user_id)
        return

    if payment["status"] != "awaiting_payment":
        bot.send_message(
            user_id,
            "Этот платёж уже обработан или срок его оплаты истёк."
        )
        clear_state(user_id)
        return

    rpc("report_crypto_payment", {
        "p_payment_ref": payment_ref,
        "p_user_id": user_id,
        "p_tx_hash": tx_hash
    })

    clear_state(user_id)

    bot.send_message(
        user_id,
        "✅ Информация об оплате отправлена администратору.\n"
        "После проверки вы получите уведомление о результате."
    )

    try:
        admin_text = (
            "<b>💳 Новое сообщение об оплате</b>\n\n"
            f"Платёж: <code>{esc(payment_ref)}</code>\n"
            f"Пользователь: <code>{user_id}</code>\n"
            f"Сумма: {money(payment['amount'])} USDT\n"
            f"Тип: {esc(payment['payment_type'])}\n"
            f"TXID: <code>{esc(tx_hash or 'Не указан')}</code>"
        )

        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton(
                "✅ Одобрить",
                callback_data=f"review_yes:{payment_ref}"
            ),
            types.InlineKeyboardButton(
                "❌ Отклонить",
                callback_data=f"review_no:{payment_ref}"
            )
        )

        bot.send_message(ADMIN_ID, admin_text, reply_markup=markup)

    except Exception:
        logging.exception("Не удалось отправить уведомление администратору")


# =========================================================
# ПОЛУЧЕНИЕ TXID ОТ ПОЛЬЗОВАТЕЛЯ
# =========================================================

@bot.message_handler(
    func=lambda m: states.get(m.from_user.id, {}).get("action") == "report_payment"
)
def receive_tx_hash(message):
    tx_hash = (message.text or "").strip()

    if not tx_hash:
        bot.send_message(message.chat.id, "Отправьте текстовый TXID или нажмите «Пропустить».")
        return

    if len(tx_hash) > 200:
        bot.send_message(message.chat.id, "Слишком длинный TXID.")
        return

    payment_ref = states[message.from_user.id]["payment_ref"]
    submit_payment_report(message.from_user.id, payment_ref, tx_hash)


# =========================================================
# АДМИН: ПРОВЕРКА И ОДОБРЕНИЕ ОПЛАТ
# =========================================================

def notify_payment_result(payment, approved, secret_code=None):
    user_id = int(payment["user_id"])

    if approved:
        text = (
            "✅ <b>Оплата подтверждена!</b>\n\n"
            "Ваш заказ одобрен администратором."
        )

        if secret_code:
            text += f"\n\nВаш секретный код:\n<code>{esc(secret_code)}</code>"

        bot.send_message(user_id, text)

    else:
        bot.send_message(
            user_id,
            "❌ Оплата отклонена администратором.\n"
            "Если вы считаете, что произошла ошибка, обратитесь в поддержку."
        )


def get_secret_after_approval(payment):
    if payment["payment_type"] == "purchase":
        result = (
            db.table("product_codes")
            .select("secret_code")
            .eq("order_id", payment["order_id"])
            .limit(1)
            .execute()
        )
        row = first_row(result.data)
        return row.get("secret_code") if row else None

    if payment["payment_type"] == "resale":
        listing = (
            db.table("resale_listings")
            .select("good_id")
            .eq("id", payment["listing_id"])
            .limit(1)
            .execute()
        )
        listing_row = first_row(listing.data)

        if not listing_row:
            return None

        good = (
            db.table("resale_goods")
            .select("secret_code")
            .eq("id", listing_row["good_id"])
            .limit(1)
            .execute()
        )
        good_row = first_row(good.data)
        return good_row.get("secret_code") if good_row else None

    return None


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("review_yes:") or c.data.startswith("review_no:")
)
def review_payment(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.", show_alert=True)
        return

    approved = call.data.startswith("review_yes:")
    payment_ref = call.data.split(":", 1)[1]

    payment = get_payment(payment_ref)

    if not payment:
        bot.answer_callback_query(call.id, "Платёж не найден.", show_alert=True)
        return

    if payment["status"] != "payment_reported":
        bot.answer_callback_query(
            call.id,
            "Платёж уже обработан или не ожидает проверки.",
            show_alert=True
        )
        return

    try:
        # RPC сам выполняет атомарную проверку и изменение статусов.
        rpc("review_crypto_payment", {
            "p_payment_ref": payment_ref,
            "p_admin_id": call.from_user.id,
            "p_approve": approved
        })

        if approved:
            # Код запрашивается только после успешного одобрения RPC.
            secret = get_secret_after_approval(payment)
            notify_payment_result(payment, True, secret)
            result_text = "Оплата одобрена."
        else:
            notify_payment_result(payment, False)
            result_text = "Оплата отклонена."

        bot.answer_callback_query(call.id, result_text)

        try:
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None
            )
        except Exception:
            pass

        bot.send_message(ADMIN_ID, result_text)

    except Exception:
        logging.exception("Ошибка проверки платежа")
        bot.answer_callback_query(
            call.id,
            "Не удалось обработать платёж. Проверьте логи.",
            show_alert=True
        )


# =========================================================
# МОИ ЗАКАЗЫ
# =========================================================

@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
def my_orders(message):
    user_id = message.from_user.id

    result = (
        db.table("orders")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(30)
        .execute()
    )

    orders = result.data or []

    if not orders:
        bot.send_message(message.chat.id, "У вас пока нет заказов.")
        return

    lines = ["<b>📦 Ваши заказы</b>\n"]

    for order in orders:
        lines.append(
            f"Заказ: <code>{esc(order['order_id'])}</code>\n"
            f"Товар: {esc(order.get('product'))}\n"
            f"Цена: {money(order.get('price'))} USDT\n"
            f"Статус: {esc(order.get('status'))}\n"
        )

    bot.send_message(message.chat.id, "\n".join(lines))


# =========================================================
# ИСТОРИЯ ПЛАТЕЖЕЙ
# =========================================================

@bot.message_handler(func=lambda m: m.text == "💳 История платежей")
def payment_history(message):
    result = (
        db.table("crypto_payments")
        .select("payment_ref,payment_type,amount,status,created_at")
        .eq("user_id", message.from_user.id)
        .order("created_at", desc=True)
        .limit(30)
        .execute()
    )

    payments = result.data or []

    if not payments:
        bot.send_message(message.chat.id, "История платежей пока пуста.")
        return

    lines = ["<b>💳 История платежей</b>\n"]

    for p in payments:
        lines.append(
            f"Платёж: <code>{esc(p['payment_ref'])}</code>\n"
            f"Тип: {esc(p['payment_type'])}\n"
            f"Сумма: {money(p['amount'])} USDT\n"
            f"Статус: {esc(p['status'])}\n"
        )

    bot.send_message(message.chat.id, "\n".join(lines))


# =========================================================
# ПЕРЕПРОДАЖА
# =========================================================

@bot.callback_query_handler(func=lambda c: c.data == "resale_catalog")
def resale_catalog(call):
    bot.answer_callback_query(call.id)

    listings_result = (
        db.table("resale_listings")
        .select("*")
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )

    listings = listings_result.data or []
    markup = types.InlineKeyboardMarkup(row_width=1)
    count = 0

    for listing in listings:
        # Не показываем объявления, для которых уже есть незавершённая оплата.
        pending = (
            db.table("crypto_payments")
            .select("id")
            .eq("listing_id", listing["id"])
            .in_("status", ["awaiting_payment", "payment_reported"])
            .limit(1)
            .execute()
        )

        if pending.data:
            continue

        good_result = (
            db.table("resale_goods")
            .select("product_id,seller_id,status")
            .eq("id", listing["good_id"])
            .limit(1)
            .execute()
        )
        good = first_row(good_result.data)

        if not good or good["status"] != "listed":
            continue

        if int(good["seller_id"]) == call.from_user.id:
            continue

        product = get_product(good["product_id"])
        if not product:
            continue

        markup.add(types.InlineKeyboardButton(
            f"{product['name']} — {money(listing['asking_price'])} USDT",
            callback_data=f"resale_buy:{listing['id']}"
        ))
        count += 1

    markup.add(types.InlineKeyboardButton(
        "➕ Выставить свой товар",
        callback_data="resale_sell"
    ))

    bot.send_message(
        call.message.chat.id,
        f"<b>🔄 Перепродажа</b>\n\nДоступных объявлений: {count}\n"
        "Оплата поступает на кошелёк магазина. Выплата продавцу производится администратором вручную.",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("resale_buy:"))
def resale_buy(call):
    listing_id = int(call.data.split(":", 1)[1])

    try:
        data = rpc("create_resale_payment", {
            "p_user_id": call.from_user.id,
            "p_listing_id": listing_id
        })

        row = first_row(data)

        if not row:
            bot.answer_callback_query(
                call.id,
                "Объявление недоступно.",
                show_alert=True
            )
            return

        payment_ref = row["payment_ref"]
        price = row.get("amount") or row.get("asking_price")

        # Получаем актуальную сумму из созданного платежа.
        payment = get_payment(payment_ref)
        if payment:
            price = payment["amount"]

        bot.answer_callback_query(call.id, "Заказ на перепродажу создан.")

        bot.send_message(
            call.message.chat.id,
            "<b>🧾 Покупка через перепродажу</b>\n\n"
            f"Сумма: <b>{money(price)} USDT</b>\n"
            f"Сеть: {NETWORK}\n"
            f"Кошелёк:\n<code>{WALLET}</code>\n\n"
            "После перевода нажмите «Я оплатил».\n"
            "Код будет выдан только после проверки администратором.\n\n"
            "Выплата продавцу производится администратором вручную.",
            reply_markup=payment_keyboard(payment_ref)
        )

    except Exception:
        logging.exception("Ошибка создания платежа перепродажи")
        bot.answer_callback_query(
            call.id,
            "Не удалось создать платёж. Возможно, объявление уже куплено.",
            show_alert=True
        )


# =========================================================
# ПРОДАЖА СВОЕГО ТОВАРА
# =========================================================

@bot.callback_query_handler(func=lambda c: c.data == "resale_sell")
def resale_sell_start(call):
    user_id = call.from_user.id

    result = (
        db.table("orders")
        .select("order_id,product,status")
        .eq("user_id", user_id)
        .eq("status", "Выдан покупателю")
        .order("created_at", desc=True)
        .execute()
    )

    orders = result.data or []
    markup = types.InlineKeyboardMarkup(row_width=1)
    count = 0

    for order in orders:
        # Исключаем уже выставленные на перепродажу исходные заказы.
        existing = (
            db.table("resale_goods")
            .select("id")
            .eq("original_order_id", order["order_id"])
            .limit(1)
            .execute()
        )

        if existing.data:
            continue

        markup.add(types.InlineKeyboardButton(
            f"{order.get('product')} — заказ {order['order_id']}",
            callback_data=f"sell_order:{order['order_id']}"
        ))
        count += 1

    bot.answer_callback_query(call.id)

    if count == 0:
        bot.send_message(
            call.message.chat.id,
            "У вас нет доступных заказов для перепродажи.\n"
            "Выставить можно только товар, который был выдан вам ранее."
        )
        return

    bot.send_message(
        call.message.chat.id,
        "Выберите заказ, товар из которого хотите выставить на перепродажу:",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("sell_order:"))
def resale_set_price(call):
    order_id = call.data.split(":", 1)[1]

    states[call.from_user.id] = {
        "action": "resale_price",
        "order_id": order_id
    }

    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "Введите цену перепродажи в USDT (например, 25.50).\n"
        "Для отмены отправьте /cancel."
    )


@bot.message_handler(
    func=lambda m: states.get(m.from_user.id, {}).get("action") == "resale_price"
)
def receive_resale_price(message):
    user_id = message.from_user.id
    state = states.get(user_id, {})

    try:
        price = Decimal(message.text.strip().replace(",", "."))
        if price <= 0 or price > Decimal("100000000"):
            raise InvalidOperation
    except (InvalidOperation, AttributeError):
        bot.send_message(message.chat.id, "Введите корректную цену, например 25.50.")
        return

    try:
        data = rpc("create_resale_listing", {
            "p_order_id": state["order_id"],
            "p_seller_id": user_id,
            "p_price": float(price)
        })

        row = first_row(data)

        clear_state(user_id)

        if not row:
            bot.send_message(
                message.chat.id,
                "Не удалось создать объявление. Проверьте, разрешена ли перепродажа этого товара."
            )
            return

        bot.send_message(
            message.chat.id,
            "<b>✅ Объявление создано</b>\n\n"
            f"Товар: {esc(row.get('product_name'))}\n"
            f"Цена: {money(row.get('asking_price', price))} USDT\n"
            "Секретный код взят из первоначального заказа автоматически.\n"
            "Комиссия магазина: 0%."
        )

    except Exception:
        logging.exception("Ошибка создания объявления")
        clear_state(user_id)
        bot.send_message(
            message.chat.id,
            "Не удалось выставить товар. Возможно, он уже выставлен или перепродажа запрещена."
        )


# =========================================================
# ПОДДЕРЖКА
# =========================================================

@bot.message_handler(func=lambda m: m.text == "🆘 Поддержка")
def support_start(message):
    states[message.from_user.id] = {"action": "support"}
    bot.send_message(
        message.chat.id,
        "Напишите сообщение для поддержки. Оно будет передано администратору.\n"
        "Для отмены отправьте /cancel."
    )


@bot.message_handler(
    func=lambda m: states.get(m.from_user.id, {}).get("action") == "support"
)
def support_message(message):
    user_id = message.from_user.id
    text = message.text or ""

    if not text.strip():
        bot.send_message(message.chat.id, "Отправьте текстовое сообщение.")
        return

    sent = bot.send_message(
        ADMIN_ID,
        "<b>🆘 Обращение в поддержку</b>\n\n"
        f"Пользователь: <code>{user_id}</code>\n"
        f"Имя: {esc(message.from_user.first_name)}\n"
        f"Username: @{esc(message.from_user.username or 'не указан')}\n\n"
        f"{esc(text)}\n\n"
        f"Чтобы ответить, отправьте:\n"
        f"<code>/reply {user_id} текст ответа</code>"
    )

    support_replies[sent.message_id] = user_id
    clear_state(user_id)

    bot.send_message(
        message.chat.id,
        "✅ Сообщение передано администратору."
    )


@bot.message_handler(commands=["reply"])
def support_reply(message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)

    if len(parts) < 3:
        bot.reply_to(message, "Формат: /reply USER_ID текст ответа")
        return

    try:
        user_id = int(parts[1])
        answer = parts[2]
        bot.send_message(
            user_id,
            "💬 <b>Ответ поддержки</b>\n\n" + esc(answer)
        )
        bot.reply_to(message, "Ответ отправлен.")
    except Exception:
        bot.reply_to(message, "Не удалось отправить ответ.")


# =========================================================
# АДМИН-ПАНЕЛЬ
# =========================================================

@bot.message_handler(func=lambda m: m.text == "⚙️ Админ-панель")
def admin_panel(message):
    if not is_admin(message.from_user.id):
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📦 Управление товарами", callback_data="admin_products"),
        types.InlineKeyboardButton("💳 Ожидающие оплаты", callback_data="admin_payments")
    )

    bot.send_message(
        message.chat.id,
        "<b>⚙️ Панель администратора</b>",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data == "admin_products")
def admin_products(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.", show_alert=True)
        return

    result = (
        db.table("products")
        .select("product_id,name,price,active")
        .order("name")
        .execute()
    )

    markup = types.InlineKeyboardMarkup(row_width=1)

    for p in result.data or []:
        status = "🟢" if p["active"] else "🔴"
        markup.add(types.InlineKeyboardButton(
            f"{status} {p['name']} ({money(p['price'])} USDT)",
            callback_data=f"admin_edit:{p['product_id']}"
        ))

    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "<b>📦 Выберите товар для редактирования:</b>",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_edit:"))
def admin_edit_product(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.", show_alert=True)
        return

    product_id = call.data.split(":", 1)[1]
    product = get_product(product_id)

    if not product:
        bot.answer_callback_query(call.id, "Товар не найден.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)

    fields = [
        ("name", "Название"),
        ("category", "Категория"),
        ("price", "Цена USDT"),
        ("description", "Описание"),
        ("origin_status", "Происхождение"),
        ("owner_status", "Владелец"),
        ("transfer_status", "Передача"),
        ("verification_info", "Сведения для проверки"),
        ("active", "Активность"),
        ("resale_allowed", "Разрешить перепродажу")
    ]

    for field, label in fields:
        markup.add(types.InlineKeyboardButton(
            f"Изменить: {label}",
            callback_data=f"editfield:{product_id}:{field}"
        ))

    markup.add(types.InlineKeyboardButton(
        "➕ Добавить секретный код",
        callback_data=f"addcode:{product_id}"
    ))

    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        f"<b>Редактирование товара:</b> {esc(product['name'])}\n"
        f"ID: <code>{esc(product_id)}</code>",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("editfield:"))
def admin_edit_field(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.", show_alert=True)
        return

    _, product_id, field = call.data.split(":", 2)

    allowed = {
        "name", "category", "price", "description",
        "origin_status", "owner_status", "transfer_status",
        "verification_info", "active", "resale_allowed"
    }

    if field not in allowed:
        bot.answer_callback_query(call.id, "Недопустимое поле.")
        return

    states[call.from_user.id] = {
        "action": "admin_edit",
        "product_id": product_id,
        "field": field
    }

    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        f"Введите новое значение для поля <b>{field}</b>.\n"
        "Для отмены отправьте /cancel."
    )


@bot.message_handler(
    func=lambda m: states.get(m.from_user.id, {}).get("action") == "admin_edit"
)
def admin_save_field(message):
    if not is_admin(message.from_user.id):
        clear_state(message.from_user.id)
        return

    state = states[message.from_user.id]
    field = state["field"]
    value = (message.text or "").strip()

    if not value:
        bot.send_message(message.chat.id, "Значение не должно быть пустым.")
        return

    try:
        if field == "price":
            value = float(Decimal(value.replace(",", ".")))
            if value <= 0:
                raise ValueError("Цена должна быть больше нуля.")

        elif field in ("active", "resale_allowed"):
            normalized = value.lower()
            if normalized in ("да", "yes", "true", "1", "on"):
                value = True
            elif normalized in ("нет", "no", "false", "0", "off"):
                value = False
            else:
                bot.send_message(message.chat.id, "Введите «да» или «нет».")
                return

        db.table("products").update({
            field: value
        }).eq("product_id", state["product_id"]).execute()

        clear_state(message.from_user.id)
        bot.send_message(message.chat.id, "✅ Информация о товаре обновлена.")

    except Exception:
        logging.exception("Ошибка редактирования товара")
        bot.send_message(message.chat.id, "Не удалось обновить поле. Проверьте значение.")


# =========================================================
# ДОБАВЛЕНИЕ СЕКРЕТНЫХ КОДОВ
# =========================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("addcode:"))
def admin_add_code_start(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.", show_alert=True)
        return

    product_id = call.data.split(":", 1)[1]

    states[call.from_user.id] = {
        "action": "admin_add_code",
        "product_id": product_id
    }

    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "Отправьте секретный код одним сообщением.\n"
        "Для отмены отправьте /cancel."
    )


@bot.message_handler(
    func=lambda m: states.get(m.from_user.id, {}).get("action") == "admin_add_code"
)
def admin_add_code(message):
    if not is_admin(message.from_user.id):
        clear_state(message.from_user.id)
        return

    product_id = states[message.from_user.id]["product_id"]
    code = (message.text or "").strip()

    if not code:
        bot.send_message(message.chat.id, "Код не должен быть пустым.")
        return

    try:
        db.table("product_codes").insert({
            "product_id": product_id,
            "secret_code": code,
            "status": "available"
        }).execute()

        clear_state(message.from_user.id)
        bot.send_message(message.chat.id, "✅ Секретный код добавлен на склад.")

    except Exception:
        logging.exception("Ошибка добавления кода")
        bot.send_message(
            message.chat.id,
            "Не удалось добавить код. Возможно, такой код уже существует."
        )


# =========================================================
# СПИСОК ОЖИДАЮЩИХ ОПЛАТ
# =========================================================

@bot.callback_query_handler(func=lambda c: c.data == "admin_payments")
def admin_payments(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.", show_alert=True)
        return

    result = (
        db.table("crypto_payments")
        .select("*")
        .eq("status", "payment_reported")
        .order("reported_at", desc=True)
        .limit(30)
        .execute()
    )

    payments = result.data or []

    bot.answer_callback_query(call.id)

    if not payments:
        bot.send_message(call.message.chat.id, "Нет платежей, ожидающих проверки.")
        return

    for p in payments:
        text = (
            "<b>💳 Платёж ожидает проверки</b>\n\n"
            f"Платёж: <code>{esc(p['payment_ref'])}</code>\n"
            f"Пользователь: <code>{p['user_id']}</code>\n"
            f"Тип: {esc(p['payment_type'])}\n"
            f"Сумма: {money(p['amount'])} USDT\n"
            f"TXID: <code>{esc(p.get('tx_hash') or 'Не указан')}</code>"
        )

        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton(
                "✅ Одобрить",
                callback_data=f"review_yes:{p['payment_ref']}"
            ),
            types.InlineKeyboardButton(
                "❌ Отклонить",
                callback_data=f"review_no:{p['payment_ref']}"
            )
        )

        bot.send_message(call.message.chat.id, text, reply_markup=markup)


# =========================================================
# ОТМЕНА ДЕЙСТВИЙ
# =========================================================

@bot.message_handler(commands=["menu"])
def menu_command(message):
    clear_state(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "Главное меню:",
        reply_markup=main_menu(message.from_user.id)
    )


# =========================================================
# ОБРАБОТКА НЕИЗВЕСТНЫХ СООБЩЕНИЙ
# =========================================================

@bot.message_handler(content_types=["text"])
def unknown_message(message):
    if message.text and message.text.startswith("/"):
        return

    if states.get(message.from_user.id):
        return

    bot.send_message(
        message.chat.id,
        "Выберите действие в меню.",
        reply_markup=main_menu(message.from_user.id)
    )


# =========================================================
# ЗАПУСК
# =========================================================

if __name__ == "__main__":
    logging.info("Бот запускается")

    try:
        bot.infinity_polling(
            skip_pending=True,
            timeout=20,
            long_polling_timeout=20
        )
    except KeyboardInterrupt:
        logging.info("Бот остановлен")
    except Exception:
        logging.exception("Критическая ошибка бота")
        raise
