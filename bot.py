import os
import html
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta

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

WALLET = "TNYoixEzXVbuAxOpVmoXGvAFFMxn4NKgKl"
NETWORK = "TRC20"
ASSET = "USDT"

if not all([BOT_TOKEN, ADMIN_ID, SUPABASE_URL, SUPABASE_KEY]):
    raise RuntimeError(
        "Не заданы BOT_TOKEN, ADMIN_ID, SUPABASE_URL или SUPABASE_KEY"
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
db = create_client(SUPABASE_URL, SUPABASE_KEY)


# =========================================================
# СИНЯЯ КНОПКА TELEGRAM И КОМАНДЫ
# =========================================================

# Синяя кнопка возле поля ввода открывает список команд.
bot.set_chat_menu_button(
    menu_button=types.MenuButtonCommands()
)

# Команды, которые будут отображаться в списке.
bot.set_my_commands([
    types.BotCommand("start", "Запустить магазин"),
    types.BotCommand("menu", "Главное меню"),
    types.BotCommand("help", "Помощь"),
    types.BotCommand("cancel", "Отменить действие")
])


# =========================================================
# СОСТОЯНИЯ И ИНТЕРФЕЙС
# =========================================================

states = {}
started_users = set()

# Храним ID только основного экрана интерфейса.
ui_messages = {}


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
    return db.rpc(name, params).execute().data


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


def safe_delete(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def delete_user_message(message):
    safe_delete(message.chat.id, message.message_id)


def clear_screen(chat_id):
    message_id = ui_messages.pop(chat_id, None)

    if message_id:
        safe_delete(chat_id, message_id)


def show_screen(chat_id, text, reply_markup=None, parse_mode="HTML"):
    """
    Обычные разделы редактируют существующий экран.
    Если редактирование невозможно, создаётся новый экран.
    """
    old_id = ui_messages.get(chat_id)

    if old_id:
        try:
            bot.edit_message_text(
                text,
                chat_id,
                old_id,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return old_id
        except Exception:
            pass

    sent = bot.send_message(
        chat_id,
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )

    ui_messages[chat_id] = sent.message_id

    if old_id:
        safe_delete(chat_id, old_id)

    return sent.message_id


def edit_screen(call, text, reply_markup=None):
    """
    Редактирует только основной экран интерфейса.
    Не редактирует важные сообщения с реквизитами или кодами.
    """
    chat_id = call.message.chat.id

    show_screen(
        chat_id,
        text,
        reply_markup=reply_markup
    )


def main_menu(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)

    markup.row(
        types.InlineKeyboardButton(
            "🛍 Каталог", callback_data="menu_catalog"
        ),
        types.InlineKeyboardButton(
            "📦 Мои заказы", callback_data="menu_orders"
        )
    )

    markup.row(
        types.InlineKeyboardButton(
            "💳 История платежей", callback_data="menu_history"
        ),
        types.InlineKeyboardButton(
            "👤 Профиль", callback_data="menu_profile"
        )
    )

    markup.row(
        types.InlineKeyboardButton(
            "🆘 Поддержка", callback_data="menu_support"
        ),
        types.InlineKeyboardButton(
            "🔄 Перепродажа", callback_data="menu_resale"
        )
    )

    if is_admin(user_id):
        markup.add(types.InlineKeyboardButton(
            "⚙️ Админ-панель", callback_data="menu_admin"
        ))

    return markup


def back_home_keyboard(back_callback=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []

    if back_callback:
        buttons.append(types.InlineKeyboardButton(
            "⬅️ Назад", callback_data=back_callback
        ))

    buttons.append(types.InlineKeyboardButton(
        "🏠 Главное меню", callback_data="go_home"
    ))

    markup.row(*buttons)
    return markup


def send_home(chat_id, text="Главное меню", new_message=False):
    """
    new_message=False — обновляет существующее меню.
    new_message=True — отправляет новое меню последним сообщением.
    """
    clear_state(chat_id)

    if new_message:
        old_id = ui_messages.get(chat_id)

        sent = bot.send_message(
            chat_id,
            text,
            reply_markup=main_menu(chat_id),
            parse_mode="HTML"
        )

        ui_messages[chat_id] = sent.message_id

        # Удаляем только старый экран интерфейса.
        # Реквизиты, коды и другие важные сообщения не затрагиваются.
        if old_id and old_id != sent.message_id:
            safe_delete(chat_id, old_id)

        return sent.message_id

    return show_screen(
        chat_id,
        text,
        reply_markup=main_menu(chat_id)
    )


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


def get_resale_listing(listing_id):
    result = (
        db.table("resale_listings")
        .select("*")
        .eq("id", listing_id)
        .limit(1)
        .execute()
    )
    return first_row(result.data)


def get_resale_good(good_id):
    result = (
        db.table("resale_goods")
        .select("*")
        .eq("id", good_id)
        .limit(1)
        .execute()
    )
    return first_row(result.data)


def get_listing_for_good(good_id):
    result = (
        db.table("resale_listings")
        .select("*")
        .eq("good_id", good_id)
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

    markup.add(types.InlineKeyboardButton(
        "🏠 Главное меню",
        callback_data="go_home"
    ))

    return markup


def format_date(value):
    if not value:
        return "Не указана"
    return str(value).replace("T", " ").split(".")[0]


def catalog_keyboard():
    result = (
        db.table("products")
        .select("product_id,name,price")
        .eq("active", True)
        .order("name")
        .execute()
    )

    markup = types.InlineKeyboardMarkup(row_width=1)

    for product in result.data or []:
        markup.add(types.InlineKeyboardButton(
            f"{product['name']} — {money(product['price'])} USDT",
            callback_data=f"product:{product['product_id']}"
        ))

    markup.add(types.InlineKeyboardButton(
        "🏠 Главное меню",
        callback_data="go_home"
    ))

    return markup


def show_catalog(chat_id):
    show_screen(
        chat_id,
        "<b>🛍 Каталог товаров</b>\n\nВыберите товар:",
        reply_markup=catalog_keyboard()
    )


# =========================================================
# ГЛАВНОЕ МЕНЮ И CALLBACK-КНОПКИ
# =========================================================

@bot.callback_query_handler(func=lambda c: c.data == "go_home")
def callback_home(call):
    bot.answer_callback_query(call.id)
    send_home(call.message.chat.id, "Главное меню:")


@bot.callback_query_handler(func=lambda c: c.data == "cancel_action")
def callback_cancel_action(call):
    bot.answer_callback_query(call.id, "Действие отменено.")
    clear_state(call.from_user.id)

    edit_screen(
        call,
        "Действие отменено.",
        reply_markup=back_home_keyboard()
    )


@bot.callback_query_handler(func=lambda c: c.data == "menu_catalog")
def menu_catalog_callback(call):
    bot.answer_callback_query(call.id)
    show_catalog(call.message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data == "menu_orders")
def menu_orders_callback(call):
    bot.answer_callback_query(call.id)
    show_orders_screen(call.message.chat.id, call.from_user.id)


@bot.callback_query_handler(func=lambda c: c.data == "menu_history")
def menu_history_callback(call):
    bot.answer_callback_query(call.id)
    show_payment_history_screen(
        call.message.chat.id,
        call.from_user.id
    )


@bot.callback_query_handler(func=lambda c: c.data == "menu_profile")
def menu_profile_callback(call):
    bot.answer_callback_query(call.id)
    show_profile_screen(call.message.chat.id, call.from_user)


@bot.callback_query_handler(func=lambda c: c.data == "menu_support")
def menu_support_callback(call):
    bot.answer_callback_query(call.id)

    states[call.from_user.id] = {"action": "support"}

    edit_screen(
        call,
        "Напишите сообщение для поддержки. "
        "Оно будет передано администратору.\n\n"
        "Для отмены нажмите кнопку ниже или отправьте /cancel.",
        back_home_keyboard("cancel_action")
    )


@bot.callback_query_handler(func=lambda c: c.data == "menu_resale")
def menu_resale_callback(call):
    bot.answer_callback_query(call.id)
    show_resale_menu(call.message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data == "menu_admin")
def menu_admin_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id, "Нет доступа.", show_alert=True
        )
        return

    bot.answer_callback_query(call.id)
    show_admin_panel(call.message.chat.id)


# =========================================================
# СТАРТ И ПРОВЕРКА ДОСТУПА
# =========================================================

@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id

    started_users.add(user_id)
    clear_state(user_id)
    delete_user_message(message)

    try:
        save_user(message.from_user)
    except Exception:
        logging.exception("Не удалось сохранить пользователя")

    send_home(
        message.chat.id,
        "👋 Добро пожаловать в магазин цифровых товаров!",
        new_message=True
    )


@bot.message_handler(
    content_types=["text"],
    func=lambda m: m.from_user.id not in started_users
)
def require_start(message):
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать!\n\n"
        "Чтобы открыть наш магазин, отправьте команду /start."
    )


@bot.callback_query_handler(
    func=lambda c: c.from_user.id not in started_users
)
def require_start_callback(call):
    bot.answer_callback_query(
        call.id,
        "Сначала запустите бота командой /start.",
        show_alert=True
    )


@bot.message_handler(commands=["help"])
def help_command(message):
    delete_user_message(message)

    show_screen(
        message.chat.id,
        "<b>ℹ️ Помощь по магазину</b>\n\n"
        "/start — открыть магазин\n"
        "/menu — открыть главное меню\n"
        "/help — показать эту справку\n"
        "/cancel — отменить текущее действие\n\n"
        "Для покупки выберите товар в каталоге и следуйте инструкциям.",
        reply_markup=back_home_keyboard()
    )


@bot.message_handler(commands=["cancel"])
def cancel(message):
    clear_state(message.from_user.id)
    delete_user_message(message)

    show_screen(
        message.chat.id,
        "Действие отменено.",
        reply_markup=back_home_keyboard()
    )


# =========================================================
# ПРОФИЛЬ
# =========================================================

def show_profile_screen(chat_id, user):
    save_user(user)

    username = f"@{esc(user.username)}" if user.username else "Не указан"

    text = (
        "<b>👤 Ваш профиль</b>\n\n"
        f"ID: <code>{user.id}</code>\n"
        f"Имя: {esc(user.first_name)}\n"
        f"Username: {username}\n\n"
        "Все цены магазина указаны в USDT."
    )

    show_screen(
        chat_id,
        text,
        reply_markup=back_home_keyboard()
    )


@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile(message):
    delete_user_message(message)
    show_profile_screen(message.chat.id, message.from_user)


# =========================================================
# КАТАЛОГ
# =========================================================

@bot.message_handler(func=lambda m: m.text == "🛍 Каталог")
def catalog(message):
    delete_user_message(message)
    save_user(message.from_user)
    show_catalog(message.chat.id)


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
        f"Передача: {esc(product.get('transfer_status') or 'Не указана')}"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "🛒 Купить",
        callback_data=f"buy:{product_id}"
    ))
    markup.add(types.InlineKeyboardButton(
        "⬅️ В каталог",
        callback_data="back_catalog"
    ))
    markup.add(types.InlineKeyboardButton(
        "🏠 Главное меню",
        callback_data="go_home"
    ))

    bot.answer_callback_query(call.id)
    edit_screen(call, text, markup)


@bot.callback_query_handler(func=lambda c: c.data == "back_catalog")
def back_catalog(call):
    bot.answer_callback_query(call.id)

    edit_screen(
        call,
        "<b>🛍 Каталог товаров</b>\n\nВыберите товар:",
        catalog_keyboard()
    )


# =========================================================
# ПОКУПКА
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
                "Не удалось создать заказ.",
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

        # Реквизиты остаются отдельным важным сообщением.
        bot.send_message(
            call.message.chat.id,
            text,
            reply_markup=payment_keyboard(payment_ref)
        )

        # Новое главное меню появляется после реквизитов.
        send_home(
            call.message.chat.id,
            "🏠 Главное меню",
            new_message=True
        )

    except Exception:
        logging.exception("Ошибка создания покупки")
        bot.answer_callback_query(
            call.id,
            "Ошибка создания заказа. Попробуйте позже.",
            show_alert=True
        )


# =========================================================
# КОНЕЦ ЧАСТИ 1
# =========================================================# =========================================================
# СООБЩЕНИЕ ОБ ОПЛАТЕ
# =========================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith("report:"))
def report_payment_start(call):
    payment_ref = call.data.split(":", 1)[1]
    payment = get_payment(payment_ref)

    if not payment or int(payment["user_id"]) != call.from_user.id:
        bot.answer_callback_query(
            call.id, "Платёж не найден.", show_alert=True
        )
        return

    if payment["payment_type"] != "purchase":
        bot.answer_callback_query(
            call.id, "Платёж недоступен.", show_alert=True
        )
        return

    if payment["status"] != "awaiting_payment":
        bot.answer_callback_query(
            call.id,
            f"Статус платежа: {payment['status']}",
            show_alert=True
        )
        return

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
    markup.add(types.InlineKeyboardButton(
        "❌ Отменить",
        callback_data="cancel_action"
    ))

    bot.answer_callback_query(call.id)

    show_screen(
        call.message.chat.id,
        "Отправьте хеш транзакции (TXID) сообщением.\n\n"
        "Если не хотите его указывать, нажмите кнопку ниже.",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("nohash:"))
def report_without_hash(call):
    payment_ref = call.data.split(":", 1)[1]
    bot.answer_callback_query(call.id)
    submit_payment_report(call.from_user.id, payment_ref, None)


def submit_payment_report(user_id, payment_ref, tx_hash):
    try:
        rpc("expire_unpaid_crypto_payments", {})
    except Exception:
        logging.exception("Ошибка проверки срока платежа")

    payment = get_payment(payment_ref)

    if (
        not payment
        or int(payment["user_id"]) != user_id
        or payment["payment_type"] != "purchase"
    ):
        clear_state(user_id)
        show_screen(
            user_id,
            "Платёж не найден.",
            reply_markup=back_home_keyboard()
        )
        return

    if payment["status"] != "awaiting_payment":
        clear_state(user_id)
        show_screen(
            user_id,
            "Этот платёж уже обработан или срок его оплаты истёк.",
            reply_markup=back_home_keyboard()
        )
        return

    rpc("report_crypto_payment", {
        "p_payment_ref": payment_ref,
        "p_user_id": user_id,
        "p_tx_hash": tx_hash
    })

    clear_state(user_id)

    show_screen(
        user_id,
        "✅ Информация об оплате отправлена администратору.\n"
        "После проверки вы получите уведомление о результате.",
        reply_markup=back_home_keyboard()
    )

    try:
        admin_text = (
            "<b>💳 Новое сообщение об оплате</b>\n\n"
            f"Платёж: <code>{esc(payment_ref)}</code>\n"
            f"Пользователь: <code>{user_id}</code>\n"
            f"Сумма: {money(payment['amount'])} USDT\n"
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


@bot.message_handler(
    func=lambda m: states.get(m.from_user.id, {}).get("action")
    == "report_payment"
)
def receive_tx_hash(message):
    tx_hash = (message.text or "").strip()

    if not tx_hash:
        delete_user_message(message)
        show_screen(
            message.chat.id,
            "Отправьте текстовый TXID или нажмите «Пропустить».",
            reply_markup=back_home_keyboard("cancel_action")
        )
        return

    if len(tx_hash) > 200:
        delete_user_message(message)
        show_screen(
            message.chat.id,
            "Слишком длинный TXID. Отправьте корректный хеш.",
            reply_markup=back_home_keyboard("cancel_action")
        )
        return

    payment_ref = states[message.from_user.id]["payment_ref"]

    delete_user_message(message)
    submit_payment_report(message.from_user.id, payment_ref, tx_hash)


# =========================================================
# АДМИН: ПОДТВЕРЖДЕНИЕ ПОКУПКИ
# =========================================================

def notify_payment_result(payment, approved, secret_code=None):
    user_id = int(payment["user_id"])

    if approved:
        text = (
            "✅ <b>Оплата подтверждена!</b>\n\n"
            "Ваш заказ одобрен администратором."
        )

        if secret_code:
            text += (
                "\n\nВаш секретный код:\n"
                f"<code>{esc(secret_code)}</code>"
            )
        else:
            text += (
                "\n\nНе удалось автоматически получить код. "
                "Обратитесь в поддержку."
            )

        # Секретный код отправляется отдельным сообщением.
        sent_message = bot.send_message(user_id, text)

        if secret_code and payment.get("order_id"):
            try:
                db.table("orders").update({
                    "secret_message_id": sent_message.message_id,
                    "secret_chat_id": sent_message.chat.id,
                    "secret_message_sent_at": datetime.now(
                        timezone.utc
                    ).isoformat()
                }).eq(
                    "order_id",
                    payment["order_id"]
                ).execute()

            except Exception:
                logging.exception(
                    "Не удалось сохранить ID сообщения с секретным кодом"
                )

    else:
        bot.send_message(
            user_id,
            "❌ Оплата отклонена администратором.\n"
            "Если вы считаете, что произошла ошибка, обратитесь в поддержку."
        )

    # После результата покупки отправляем новое главное меню.
    send_home(
        user_id,
        "🏠 Главное меню",
        new_message=True
    )


def get_secret_after_approval(payment):
    if payment["payment_type"] != "purchase":
        return None

    result = (
        db.table("product_codes")
        .select("secret_code")
        .eq("order_id", payment["order_id"])
        .limit(1)
        .execute()
    )

    row = first_row(result.data)
    return row.get("secret_code") if row else None


@bot.callback_query_handler(
    func=lambda c: (
        c.data.startswith("review_yes:")
        or c.data.startswith("review_no:")
    )
)
def review_payment(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id, "Нет доступа.", show_alert=True
        )
        return

    approved = call.data.startswith("review_yes:")
    payment_ref = call.data.split(":", 1)[1]
    payment = get_payment(payment_ref)

    if not payment or payment["payment_type"] != "purchase":
        bot.answer_callback_query(
            call.id, "Платёж не найден.", show_alert=True
        )
        return

    if payment["status"] != "payment_reported":
        bot.answer_callback_query(
            call.id,
            "Платёж уже обработан или не ожидает проверки.",
            show_alert=True
        )
        return

    try:
        rpc("review_crypto_payment", {
            "p_payment_ref": payment_ref,
            "p_admin_id": call.from_user.id,
            "p_approve": approved
        })

        if approved:
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

def show_orders_screen(chat_id, user_id):
    result = (
        db.table("orders")
        .select("order_id,product,price,status,created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(30)
        .execute()
    )

    orders = result.data or []

    if not orders:
        show_screen(
            chat_id,
            "У вас пока нет заказов.",
            reply_markup=back_home_keyboard()
        )
        return

    lines = ["<b>📦 Ваши заказы</b>\n"]

    for order in orders:
        lines.append(
            f"Заказ: <code>{esc(order['order_id'])}</code>\n"
            f"Товар: {esc(order.get('product'))}\n"
            f"Цена: {money(order.get('price'))} USDT\n"
            f"Статус: {esc(order.get('status'))}\n"
        )

    show_screen(
        chat_id,
        "\n".join(lines),
        reply_markup=back_home_keyboard()
    )


@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
def my_orders(message):
    delete_user_message(message)
    show_orders_screen(message.chat.id, message.from_user.id)


# =========================================================
# ИСТОРИЯ ПЛАТЕЖЕЙ
# =========================================================

def show_payment_history_screen(chat_id, user_id):
    result = (
        db.table("crypto_payments")
        .select("payment_ref,payment_type,amount,status,created_at")
        .eq("user_id", user_id)
        .eq("payment_type", "purchase")
        .order("created_at", desc=True)
        .limit(30)
        .execute()
    )

    payments = result.data or []

    if not payments:
        show_screen(
            chat_id,
            "История платежей пока пуста.",
            reply_markup=back_home_keyboard()
        )
        return

    lines = ["<b>💳 История платежей</b>\n"]

    for payment in payments:
        lines.append(
            f"Платёж: <code>{esc(payment['payment_ref'])}</code>\n"
            f"Сумма: {money(payment['amount'])} USDT\n"
            f"Статус: {esc(payment['status'])}\n"
        )

    show_screen(
        chat_id,
        "\n".join(lines),
        reply_markup=back_home_keyboard()
    )


@bot.message_handler(func=lambda m: m.text == "💳 История платежей")
def payment_history(message):
    delete_user_message(message)
    show_payment_history_screen(message.chat.id, message.from_user.id)


# =========================================================
# ПЕРЕПРОДАЖА
# =========================================================

def resale_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "➕ Создать закрытое объявление",
            callback_data="resale_sell"
        ),
        types.InlineKeyboardButton(
            "📋 Мои объявления",
            callback_data="resale_my"
        ),
        types.InlineKeyboardButton(
            "🏠 Главное меню",
            callback_data="go_home"
        )
    )
    return markup


def show_resale_menu(chat_id):
    show_screen(
        chat_id,
        "<b>🔄 Перепродажа</b>\n\n"
        "Здесь можно выставить на перепродажу товар, "
        "который ранее был выдан вам в магазине.\n\n"
        "Ваши объявления доступны только вам и администратору.",
        reply_markup=resale_menu_markup()
    )


@bot.message_handler(func=lambda m: m.text == "🔄 Перепродажа")
def resale_menu(message):
    delete_user_message(message)
    save_user(message.from_user)
    show_resale_menu(message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data == "resale_sell")
def resale_sell_start(call):
    user_id = call.from_user.id
    save_user(call.from_user)

    try:
        result = (
            db.table("orders")
            .select("order_id,product,price,status,created_at")
            .eq("user_id", user_id)
            .eq("status", "Выдан покупателю")
            .order("created_at", desc=True)
            .execute()
        )

        orders = result.data or []
        markup = types.InlineKeyboardMarkup(row_width=1)
        count = 0

        for order in orders:
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

        markup.add(types.InlineKeyboardButton(
            "⬅️ Назад", callback_data="resale_back"
        ))
        markup.add(types.InlineKeyboardButton(
            "🏠 Главное меню", callback_data="go_home"
        ))

        bot.answer_callback_query(call.id)

        if count == 0:
            edit_screen(
                call,
                "У вас нет доступных заказов для перепродажи.\n\n"
                "Можно выставить только товар, который был выдан вам ранее "
                "и ещё не выставлялся на перепродажу.",
                back_home_keyboard("resale_back")
            )
            return

        edit_screen(
            call,
            "Выберите свой заказ, товар из которого хотите выставить:",
            markup
        )

    except Exception:
        logging.exception("Ошибка получения заказов для перепродажи")
        bot.answer_callback_query(
            call.id, "Не удалось загрузить заказы.", show_alert=True
        )


@bot.callback_query_handler(func=lambda c: c.data == "resale_back")
def resale_back(call):
    bot.answer_callback_query(call.id)
    edit_screen(
        call,
        "<b>🔄 Перепродажа</b>\n\n"
        "Здесь можно выставить на перепродажу ранее выданный товар.",
        resale_menu_markup()
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("sell_order:"))
def resale_set_price(call):
    order_id = call.data.split(":", 1)[1]

    order_result = (
        db.table("orders")
        .select("order_id")
        .eq("order_id", order_id)
        .eq("user_id", call.from_user.id)
        .eq("status", "Выдан покупателю")
        .limit(1)
        .execute()
    )

    if not order_result.data:
        bot.answer_callback_query(
            call.id, "Этот заказ недоступен.", show_alert=True
        )
        return

    states[call.from_user.id] = {
        "action": "resale_price",
        "order_id": order_id
    }

    bot.answer_callback_query(call.id)

    show_screen(
        call.message.chat.id,
        "Введите желаемую цену перепродажи в USDT.\n\n"
        "Например: <code>25.50</code>\n\n"
        "Для отмены нажмите кнопку ниже или отправьте /cancel.",
        reply_markup=back_home_keyboard("cancel_action")
    )


@bot.message_handler(
    func=lambda m: states.get(m.from_user.id, {}).get("action")
    == "resale_price"
)
def receive_resale_price(message):
    user_id = message.from_user.id
    state = states.get(user_id, {})

    try:
        price = Decimal(message.text.strip().replace(",", "."))

        if (
            not price.is_finite()
            or price <= 0
            or price > Decimal("100000000")
        ):
            raise InvalidOperation

        price = price.quantize(Decimal("0.01"))

    except (InvalidOperation, AttributeError, ValueError):
        delete_user_message(message)
        show_screen(
            message.chat.id,
            "Введите корректную цену, например 25.50.",
            reply_markup=back_home_keyboard("cancel_action")
        )
        return

    order_id = state.get("order_id")
    delete_user_message(message)

    try:
        order_result = (
            db.table("orders")
            .select("order_id")
            .eq("order_id", order_id)
            .eq("user_id", user_id)
            .eq("status", "Выдан покупателю")
            .limit(1)
            .execute()
        )

        if not order_result.data:
            clear_state(user_id)
            show_screen(
                message.chat.id,
                "Заказ не найден или больше не доступен для перепродажи.",
                reply_markup=back_home_keyboard()
            )
            return

        existing = (
            db.table("resale_goods")
            .select("id")
            .eq("original_order_id", order_id)
            .limit(1)
            .execute()
        )

        if existing.data:
            clear_state(user_id)
            show_screen(
                message.chat.id,
                "Этот товар уже выставлялся на перепродажу.",
                reply_markup=back_home_keyboard()
            )
            return

        data = rpc("create_resale_listing", {
            "p_order_id": order_id,
            "p_seller_id": user_id,
            "p_price": float(price)
        })

        row = first_row(data)

        if not row:
            clear_state(user_id)
            show_screen(
                message.chat.id,
                "Не удалось создать объявление. "
                "Возможно, перепродажа этого товара запрещена.",
                reply_markup=back_home_keyboard()
            )
            return

        clear_state(user_id)

        good_result = (
            db.table("resale_goods")
            .select("*")
            .eq("original_order_id", order_id)
            .eq("seller_id", user_id)
            .limit(1)
            .execute()
        )

        good = first_row(good_result.data)

        if not good:
            show_screen(
                message.chat.id,
                "Объявление создано, но не удалось загрузить его сведения.",
                reply_markup=back_home_keyboard()
            )
            return

        listing = get_listing_for_good(good["id"])

        if not listing:
            show_screen(
                message.chat.id,
                "Объявление создано, но не удалось загрузить его сведения.",
                reply_markup=back_home_keyboard()
            )
            return

        send_my_resale_detail(
            message.chat.id,
            user_id,
            listing["id"]
        )

    except Exception:
        logging.exception("Ошибка создания объявления")
        clear_state(user_id)
        show_screen(
            message.chat.id,
            "Не удалось выставить товар. "
            "Возможно, он уже выставлен или перепродажа запрещена.",
            reply_markup=back_home_keyboard()
        )


# =========================================================
# КОНЕЦ ЧАСТИ 2
# =========================================================# =========================================================
# МОИ ОБЪЯВЛЕНИЯ ПЕРЕПРОДАЖИ
# =========================================================

@bot.callback_query_handler(func=lambda c: c.data == "resale_my")
def resale_my_listings(call):
    user_id = call.from_user.id

    try:
        goods_result = (
            db.table("resale_goods")
            .select("id,product_id,status,original_order_id")
            .eq("seller_id", user_id)
            .order("id", desc=True)
            .limit(50)
            .execute()
        )

        goods = goods_result.data or []
        markup = types.InlineKeyboardMarkup(row_width=1)
        count = 0

        for good in goods:
            listing = get_listing_for_good(good["id"])

            if not listing:
                continue

            product = get_product(good["product_id"])
            product_name = (
                product.get("name") if product else good.get("product_id")
            )

            status = (
                "🟢 Активно"
                if listing.get("status") == "active"
                else "⚫ Продано"
            )

            markup.add(types.InlineKeyboardButton(
                f"{status} | {product_name} | "
                f"{money(listing.get('asking_price'))} USDT",
                callback_data=f"myresale:{listing['id']}"
            ))
            count += 1

        markup.add(types.InlineKeyboardButton(
            "⬅️ Назад", callback_data="resale_back"
        ))
        markup.add(types.InlineKeyboardButton(
            "🏠 Главное меню", callback_data="go_home"
        ))

        bot.answer_callback_query(call.id)

        if count == 0:
            edit_screen(
                call,
                "У вас пока нет объявлений.\n\n"
                "Нажмите «Создать закрытое объявление», "
                "чтобы выставить ранее купленный товар.",
                back_home_keyboard("resale_back")
            )
            return

        edit_screen(
            call,
            "<b>📋 Ваши закрытые объявления</b>\n\n"
            "Выберите объявление, чтобы посмотреть подробности:",
            markup
        )

    except Exception:
        logging.exception("Ошибка загрузки собственных объявлений")
        bot.answer_callback_query(
            call.id, "Не удалось загрузить объявления.", show_alert=True
        )


def send_my_resale_detail(chat_id, user_id, listing_id):
    listing = get_resale_listing(listing_id)

    if not listing:
        show_screen(
            chat_id,
            "Объявление не найдено.",
            reply_markup=back_home_keyboard("resale_back")
        )
        return

    good = get_resale_good(listing["good_id"])

    if not good or int(good["seller_id"]) != int(user_id):
        show_screen(
            chat_id,
            "У вас нет доступа к этому объявлению.",
            reply_markup=back_home_keyboard("resale_back")
        )
        return

    product = get_product(good["product_id"])

    order_result = (
        db.table("orders")
        .select("order_id,product,price,status,created_at")
        .eq("order_id", good["original_order_id"])
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    order = first_row(order_result.data)

    if not order:
        show_screen(
            chat_id,
            "Не удалось загрузить сведения об исходном заказе.",
            reply_markup=back_home_keyboard("resale_back")
        )
        return

    product_name = (
        product.get("name")
        if product
        else order.get("product") or good["product_id"]
    )

    category = product.get("category") if product else "Не указана"

    listing_status = (
        "🟢 Активно"
        if listing.get("status") == "active"
        else "⚫ Продано"
    )

    text = (
        "<b>📋 Ваше закрытое объявление</b>\n\n"
        f"<b>Товар:</b> {esc(product_name)}\n"
        f"<b>ID товара:</b> <code>{esc(good.get('product_id'))}</code>\n"
        f"<b>Категория:</b> {esc(category)}\n\n"
        "<b>Информация о первоначальной покупке</b>\n"
        f"Номер заказа: <code>{esc(order.get('order_id'))}</code>\n"
        f"Цена покупки: {money(order.get('price'))} USDT\n"
        f"Дата покупки: {esc(format_date(order.get('created_at')))}\n\n"
        "<b>Ваше объявление</b>\n"
        f"Цена перепродажи: <b>{money(listing.get('asking_price'))} USDT</b>\n"
        f"Статус: {listing_status}\n\n"
        "🔒 Секретный код скрыт."
    )

    show_screen(
        chat_id,
        text,
        reply_markup=back_home_keyboard("resale_my")
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("myresale:"))
def my_resale_detail(call):
    try:
        listing_id = int(call.data.split(":", 1)[1])
        bot.answer_callback_query(call.id)

        send_my_resale_detail(
            call.message.chat.id,
            call.from_user.id,
            listing_id
        )

    except Exception:
        logging.exception("Ошибка просмотра собственного объявления")
        bot.answer_callback_query(
            call.id, "Не удалось открыть объявление.", show_alert=True
        )


# =========================================================
# ПОДДЕРЖКА
# =========================================================

@bot.message_handler(func=lambda m: m.text == "🆘 Поддержка")
def support_start(message):
    delete_user_message(message)

    states[message.from_user.id] = {"action": "support"}

    show_screen(
        message.chat.id,
        "Напишите сообщение для поддержки. "
        "Оно будет передано администратору.\n\n"
        "Для отмены нажмите кнопку ниже или отправьте /cancel.",
        reply_markup=back_home_keyboard("cancel_action")
    )


@bot.message_handler(
    func=lambda m: states.get(m.from_user.id, {}).get("action")
    == "support"
)
def support_message(message):
    user_id = message.from_user.id
    text = message.text or ""

    if not text.strip():
        delete_user_message(message)
        show_screen(
            message.chat.id,
            "Отправьте текстовое сообщение.",
            reply_markup=back_home_keyboard("cancel_action")
        )
        return

    delete_user_message(message)

    try:
        bot.send_message(
            ADMIN_ID,
            "<b>🆘 Обращение в поддержку</b>\n\n"
            f"Пользователь: <code>{user_id}</code>\n"
            f"Имя: {esc(message.from_user.first_name)}\n"
            f"Username: @{esc(message.from_user.username or 'не указан')}\n\n"
            f"{esc(text)}\n\n"
            "Чтобы ответить, отправьте:\n"
            f"<code>/reply {user_id} текст ответа</code>"
        )

        clear_state(user_id)

        show_screen(
            message.chat.id,
            "✅ Сообщение передано администратору.",
            reply_markup=back_home_keyboard()
        )

    except Exception:
        logging.exception("Ошибка отправки обращения")
        show_screen(
            message.chat.id,
            "Не удалось отправить сообщение. Попробуйте позже.",
            reply_markup=back_home_keyboard()
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

def admin_panel_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)

    markup.add(
        types.InlineKeyboardButton(
            "📦 Управление товарами",
            callback_data="admin_products"
        ),
        types.InlineKeyboardButton(
            "💳 Ожидающие оплаты",
            callback_data="admin_payments"
        ),
        types.InlineKeyboardButton(
            "🔄 Все объявления перепродажи",
            callback_data="admin_resale"
        ),
        types.InlineKeyboardButton(
            "🏠 Главное меню",
            callback_data="go_home"
        )
    )

    return markup


def show_admin_panel(chat_id):
    show_screen(
        chat_id,
        "<b>⚙️ Панель администратора</b>",
        reply_markup=admin_panel_markup()
    )


@bot.message_handler(func=lambda m: m.text == "⚙️ Админ-панель")
def admin_panel(message):
    delete_user_message(message)

    if not is_admin(message.from_user.id):
        return

    show_admin_panel(message.chat.id)


# =========================================================
# АДМИН: ВСЕ ОБЪЯВЛЕНИЯ
# =========================================================

@bot.callback_query_handler(func=lambda c: c.data == "admin_resale")
def admin_resale(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.", show_alert=True)
        return

    try:
        result = (
            db.table("resale_listings")
            .select("*")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )

        listings = result.data or []
        markup = types.InlineKeyboardMarkup(row_width=1)
        count = 0

        for listing in listings:
            good = get_resale_good(listing["good_id"])

            if not good:
                continue

            product = get_product(good["product_id"])
            product_name = (
                product.get("name") if product else good["product_id"]
            )

            status = "🟢" if listing.get("status") == "active" else "⚫"

            markup.add(types.InlineKeyboardButton(
                f"{status} {product_name} — "
                f"{money(listing.get('asking_price'))} USDT",
                callback_data=f"admin_resale_item:{listing['id']}"
            ))
            count += 1

        markup.add(types.InlineKeyboardButton(
            "⬅️ Назад", callback_data="admin_back"
        ))
        markup.add(types.InlineKeyboardButton(
            "🏠 Главное меню", callback_data="go_home"
        ))

        bot.answer_callback_query(call.id)

        edit_screen(
            call,
            "<b>🔄 Все объявления перепродажи</b>\n\n"
            f"Всего объявлений: {count}\n\n"
            "🟢 — активно\n"
            "⚫ — продано",
            markup
        )

    except Exception:
        logging.exception("Ошибка загрузки объявлений для администратора")
        bot.answer_callback_query(
            call.id, "Не удалось загрузить объявления.", show_alert=True
        )


@bot.callback_query_handler(func=lambda c: c.data == "admin_back")
def admin_back(call):
    bot.answer_callback_query(call.id)
    edit_screen(
        call,
        "<b>⚙️ Панель администратора</b>",
        admin_panel_markup()
    )


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("admin_resale_item:")
)
def admin_resale_item(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.", show_alert=True)
        return

    try:
        listing_id = int(call.data.split(":", 1)[1])
        listing = get_resale_listing(listing_id)

        if not listing:
            bot.answer_callback_query(call.id, "Объявление не найдено.")
            return

        good = get_resale_good(listing["good_id"])

        if not good:
            bot.answer_callback_query(
                call.id, "Информация о товаре не найдена."
            )
            return

        product = get_product(good["product_id"])

        order_result = (
            db.table("orders")
            .select("*")
            .eq("order_id", good["original_order_id"])
            .limit(1)
            .execute()
        )

        order = first_row(order_result.data) or {}

        seller_result = (
            db.table("users")
            .select("username,first_name")
            .eq("user_id", good["seller_id"])
            .limit(1)
            .execute()
        )

        seller = first_row(seller_result.data) or {}
        username = seller.get("username")

        seller_name = (
            f"@{username}"
            if username
            else seller.get("first_name") or "Не указано"
        )

        product_name = (
            product.get("name") if product else good["product_id"]
        )
        category = product.get("category") if product else "Не указана"
        description = product.get("description") if product else ""
        verification_info = (
            product.get("verification_info") if product else ""
        )

        text = (
            "<b>📋 Информация об объявлении</b>\n\n"
            f"<b>Товар:</b> {esc(product_name)}\n"
            f"ID товара: <code>{esc(good.get('product_id'))}</code>\n"
            f"Категория: {esc(category)}\n\n"
            "<b>Первоначальная покупка</b>\n"
            f"Заказ: <code>{esc(order.get('order_id'))}</code>\n"
            f"Цена покупки: {money(order.get('price'))} USDT\n"
            f"Дата покупки: {esc(format_date(order.get('created_at')))}\n\n"
            f"Описание: {esc(description or 'Не указано')}\n"
            f"Дополнительные сведения: "
            f"{esc(verification_info or 'Не указаны')}\n\n"
            "<b>Объявление</b>\n"
            f"ID объявления: <code>{listing_id}</code>\n"
            f"Цена перепродажи: "
            f"<b>{money(listing.get('asking_price'))} USDT</b>\n"
            f"Продавец: {esc(seller_name)}\n"
            f"ID продавца: <code>{good['seller_id']}</code>\n"
            f"Статус объявления: {esc(listing.get('status'))}\n"
            f"Статус товара: {esc(good.get('status'))}\n\n"
            "<b>🔐 Секретный код (только администратор)</b>\n"
            f"<code>{esc(good.get('secret_code'))}</code>"
        )

        markup = types.InlineKeyboardMarkup()

        if (
            listing.get("status") == "active"
            and good.get("status") == "listed"
        ):
            markup.add(types.InlineKeyboardButton(
                "✅ Отметить как проданный",
                callback_data=f"admin_resale_sold:{listing_id}"
            ))

        markup.add(types.InlineKeyboardButton(
            "⬅️ Ко всем объявлениям",
            callback_data="admin_resale"
        ))
        markup.add(types.InlineKeyboardButton(
            "🏠 Главное меню",
            callback_data="go_home"
        ))

        bot.answer_callback_query(call.id)
        edit_screen(call, text, markup)

    except Exception:
        logging.exception("Ошибка просмотра объявления администратором")
        bot.answer_callback_query(
            call.id, "Не удалось открыть объявление.", show_alert=True
        )


# =========================================================
# УДАЛЕНИЕ СООБЩЕНИЯ С СЕКРЕТНЫМ КОДОМ
# =========================================================

def delete_original_secret_message(original_order_id):
    try:
        order_result = (
            db.table("orders")
            .select(
                "secret_message_id,secret_chat_id,secret_message_sent_at"
            )
            .eq("order_id", original_order_id)
            .limit(1)
            .execute()
        )

        order = first_row(order_result.data)

        if not order:
            return "Не удалось найти исходный заказ."

        message_id = order.get("secret_message_id")
        chat_id = order.get("secret_chat_id")
        sent_at = order.get("secret_message_sent_at")

        if not message_id or not chat_id or not sent_at:
            return (
                "ID сообщения с секретным кодом не сохранён. "
                "Удалить старое сообщение автоматически не удалось."
            )

        sent_time = datetime.fromisoformat(
            str(sent_at).replace("Z", "+00:00")
        )

        if sent_time.tzinfo is None:
            sent_time = sent_time.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - sent_time

        if age > timedelta(hours=48):
            return (
                "Сообщение с кодом не удалено: прошло более 48 часов "
                "с момента отправки."
            )

        bot.delete_message(
            chat_id=int(chat_id),
            message_id=int(message_id)
        )

        return "Исходное сообщение с секретным кодом удалено."

    except Exception:
        logging.exception(
            "Не удалось удалить исходное сообщение с секретным кодом"
        )
        return (
            "Не удалось удалить сообщение с кодом. "
            "Возможно, Telegram не разрешает его удаление."
        )


# =========================================================
# АДМИН: ОТМЕТИТЬ КАК ПРОДАННЫЙ
# =========================================================

@bot.callback_query_handler(
    func=lambda c: c.data.startswith("admin_resale_sold:")
)
def admin_resale_mark_sold(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(
            call.id, "Нет доступа.", show_alert=True
        )
        return

    try:
        listing_id = int(call.data.split(":", 1)[1])

        listing_result = (
            db.table("resale_listings")
            .select("*")
            .eq("id", listing_id)
            .eq("status", "active")
            .limit(1)
            .execute()
        )

        listing = first_row(listing_result.data)

        if not listing:
            bot.answer_callback_query(
                call.id,
                "Объявление уже обработано.",
                show_alert=True
            )
            return

        good_result = (
            db.table("resale_goods")
            .select("*")
            .eq("id", listing["good_id"])
            .eq("status", "listed")
            .limit(1)
            .execute()
        )

        good = first_row(good_result.data)

        if not good:
            bot.answer_callback_query(
                call.id,
                "Товар уже изменён или продан.",
                show_alert=True
            )
            return

        listing_update = (
            db.table("resale_listings")
            .update({
                "status": "sold",
                "sold_at": datetime.now(timezone.utc).isoformat()
            })
            .eq("id", listing_id)
            .eq("status", "active")
            .select("id")
            .execute()
        )

        if not listing_update.data:
            bot.answer_callback_query(
                call.id,
                "Объявление уже изменено.",
                show_alert=True
            )
            return

        try:
            good_update = (
                db.table("resale_goods")
                .update({"status": "sold"})
                .eq("id", listing["good_id"])
                .eq("status", "listed")
                .select("id")
                .execute()
            )

            if not good_update.data:
                raise RuntimeError(
                    "Не удалось изменить статус товара."
                )

        except Exception:
            db.table("resale_listings").update({
                "status": "active",
                "sold_at": None
            }).eq("id", listing_id).execute()
            raise

        deletion_result = delete_original_secret_message(
            good["original_order_id"]
        )

        seller_id = int(good["seller_id"])

        try:
            bot.send_message(
                seller_id,
                "✅ <b>Ваш товар продан!</b>\n\n"
                "Ваше объявление успешно завершено.\n\n"
                "Спасибо за использование нашего магазина!"
            )

            seller_notification = "Уведомление продавцу отправлено."

        except Exception:
            logging.exception(
                "Не удалось отправить уведомление продавцу"
            )

            seller_notification = (
                "Не удалось отправить уведомление продавцу. "
                "Возможно, продавец не запускал бота через /start."
            )

        bot.answer_callback_query(
            call.id,
            "Объявление отмечено как проданное."
        )

        edit_screen(
            call,
            "✅ <b>Объявление и товар отмечены как проданные.</b>\n\n"
            "Статус первоначального заказа не изменён.\n\n"
            f"📩 {esc(seller_notification)}\n\n"
            f"🗑 {esc(deletion_result)}",
            reply_markup=back_home_keyboard("admin_resale")
        )

    except Exception:
        logging.exception("Ошибка изменения статуса объявления")
        bot.answer_callback_query(
            call.id,
            "Ошибка изменения статуса. Проверьте логи.",
            show_alert=True
        )


# =========================================================
# АДМИН: УПРАВЛЕНИЕ ТОВАРАМИ
# =========================================================

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

    for product in result.data or []:
        status = "🟢" if product["active"] else "🔴"
        markup.add(types.InlineKeyboardButton(
            f"{status} {product['name']} "
            f"({money(product['price'])} USDT)",
            callback_data=f"admin_edit:{product['product_id']}"
        ))

    markup.add(types.InlineKeyboardButton(
        "⬅️ Назад", callback_data="admin_back"
    ))
    markup.add(types.InlineKeyboardButton(
        "🏠 Главное меню", callback_data="go_home"
    ))

    bot.answer_callback_query(call.id)

    edit_screen(
        call,
        "<b>📦 Выберите товар для редактирования:</b>",
        markup
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
    markup.add(types.InlineKeyboardButton(
        "⬅️ К товарам",
        callback_data="admin_products"
    ))
    markup.add(types.InlineKeyboardButton(
        "🏠 Главное меню",
        callback_data="go_home"
    ))

    bot.answer_callback_query(call.id)

    edit_screen(
        call,
        f"<b>Редактирование товара:</b> {esc(product['name'])}\n"
        f"ID: <code>{esc(product_id)}</code>",
        markup
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("editfield:"))
def admin_edit_field(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа.", show_alert=True)
        return

    _, product_id, field = call.data.split(":", 2)

    allowed = {
        "name", "category", "price", "description",
        "transfer_status", "verification_info",
        "active", "resale_allowed"
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

    show_screen(
        call.message.chat.id,
        f"Введите новое значение для поля <b>{field}</b>.\n\n"
        "Для отмены нажмите кнопку ниже или отправьте /cancel.",
        reply_markup=back_home_keyboard("cancel_action")
    )


@bot.message_handler(
    func=lambda m: states.get(m.from_user.id, {}).get("action")
    == "admin_edit"
)
def admin_save_field(message):
    if not is_admin(message.from_user.id):
        clear_state(message.from_user.id)
        return

    state = states[message.from_user.id]
    field = state["field"]
    value = (message.text or "").strip()

    if not value:
        delete_user_message(message)
        show_screen(
            message.chat.id,
            "Значение не должно быть пустым.",
            reply_markup=back_home_keyboard("cancel_action")
        )
        return

    delete_user_message(message)

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
                show_screen(
                    message.chat.id,
                    "Введите «да» или «нет».",
                    reply_markup=back_home_keyboard("cancel_action")
                )
                return

        db.table("products").update({
            field: value
        }).eq("product_id", state["product_id"]).execute()

        clear_state(message.from_user.id)

        show_screen(
            message.chat.id,
            "✅ Информация о товаре обновлена.",
            reply_markup=back_home_keyboard("admin_products")
        )

    except Exception:
        logging.exception("Ошибка редактирования товара")
        show_screen(
            message.chat.id,
            "Не удалось обновить поле. Проверьте значение.",
            reply_markup=back_home_keyboard("cancel_action")
        )


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

    show_screen(
        call.message.chat.id,
        "Отправьте секретный код одним сообщением.\n\n"
        "Для отмены нажмите кнопку ниже или отправьте /cancel.",
        reply_markup=back_home_keyboard("cancel_action")
    )


@bot.message_handler(
    func=lambda m: states.get(m.from_user.id, {}).get("action")
    == "admin_add_code"
)
def admin_add_code(message):
    if not is_admin(message.from_user.id):
        clear_state(message.from_user.id)
        return

    product_id = states[message.from_user.id]["product_id"]
    code = (message.text or "").strip()

    if not code:
        delete_user_message(message)
        show_screen(
            message.chat.id,
            "Код не должен быть пустым.",
            reply_markup=back_home_keyboard("cancel_action")
        )
        return

    delete_user_message(message)

    try:
        db.table("product_codes").insert({
            "product_id": product_id,
            "secret_code": code,
            "status": "available"
        }).execute()

        clear_state(message.from_user.id)

        show_screen(
            message.chat.id,
            "✅ Секретный код добавлен на склад.",
            reply_markup=back_home_keyboard("admin_products")
        )

    except Exception:
        logging.exception("Ошибка добавления кода")
        show_screen(
            message.chat.id,
            "Не удалось добавить код. Возможно, такой код уже существует.",
            reply_markup=back_home_keyboard("cancel_action")
        )


# =========================================================
# АДМИН: ОЖИДАЮЩИЕ ОПЛАТЫ
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
        .eq("payment_type", "purchase")
        .order("reported_at", desc=True)
        .limit(30)
        .execute()
    )

    payments = result.data or []
    bot.answer_callback_query(call.id)

    if not payments:
        edit_screen(
            call,
            "Нет платежей, ожидающих проверки.",
            back_home_keyboard("admin_back")
        )
        return

    # Карточки платежей отправляются отдельно.
    for payment in payments:
        text = (
            "<b>💳 Платёж ожидает проверки</b>\n\n"
            f"Платёж: <code>{esc(payment['payment_ref'])}</code>\n"
            f"Пользователь: <code>{payment['user_id']}</code>\n"
            f"Сумма: {money(payment['amount'])} USDT\n"
            f"TXID: <code>{esc(payment.get('tx_hash') or 'Не указан')}</code>"
        )

        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton(
                "✅ Одобрить",
                callback_data=f"review_yes:{payment['payment_ref']}"
            ),
            types.InlineKeyboardButton(
                "❌ Отклонить",
                callback_data=f"review_no:{payment['payment_ref']}"
            )
        )

        bot.send_message(
            call.message.chat.id,
            text,
            reply_markup=markup
        )

    edit_screen(
        call,
        "⬅️ Карточки платежей отправлены выше.\n\n"
        "После проверки вернитесь в админ-панель.",
        reply_markup=back_home_keyboard("admin_back")
    )


# =========================================================
# МЕНЮ И НЕИЗВЕСТНЫЕ СООБЩЕНИЯ
# =========================================================

@bot.message_handler(commands=["menu"])
def menu_command(message):
    user_id = message.from_user.id

    if user_id not in started_users:
        bot.send_message(
            message.chat.id,
            "Сначала запустите магазин командой /start."
        )
        return

    delete_user_message(message)
    send_home(message.chat.id, "Главное меню:")


@bot.message_handler(content_types=["text"])
def unknown_message(message):
    if message.text and message.text.startswith("/"):
        return

    if message.from_user.id not in started_users:
        bot.send_message(
            message.chat.id,
            "👋 Добро пожаловать!\n\n"
            "Чтобы открыть магазин, отправьте команду /start."
        )
        return

    if states.get(message.from_user.id):
        return

    delete_user_message(message)

    show_screen(
        message.chat.id,
        "👋 Чтобы открыть раздел магазина, используйте кнопки меню.",
        reply_markup=back_home_keyboard()
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
