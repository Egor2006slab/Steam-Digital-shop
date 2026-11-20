import os
import telebot

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "🛍 Добро пожаловать в Steam Digital Shop!\n\n"
        "Выберите раздел:\n"
        "🛒 Каталог\n"
        "📦 Мои заказы\n"
        "💬 Поддержка"
    )

bot.infinity_polling()
