import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ConversationHandler, 
    MessageHandler, Filters, CallbackContext
)
from datetime import datetime, timedelta
import schedule
import time
import threading
import os

# تنظیمات لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# مراحل گفتگو
(
    NAME, LAST_NAME, PHONE, MAIN_MENU, CREDIT_MENU, SELECT_CUSTOMER, SELECT_FOOD, 
    SELECT_PRICE, CUSTOM_PRICE, PAYMENT_MENU, PAYMENT_AMOUNT
) = range(11)

# اتصال به پایگاه داده
def init_db():
    conn = sqlite3.connect('accounting_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS customers 
                 (id INTEGER PRIMARY KEY, name TEXT, last_name TEXT, phone TEXT, balance REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY, customer_id INTEGER, food TEXT, amount REAL, date TEXT)''')
    conn.commit()
    conn.close()

# شروع ربات
async def start(update: Update, context: CallbackContext):
    init_db()
    await update.message.reply_text("خوش آمدید! لطفاً اطلاعات مشتری را ثبت کنید یا از منو انتخاب کنید.")
    return await show_main_menu(update, context)

# نمایش منوی اصلی
async def show_main_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("ثبت مشتری", callback_data='register_customer')],
        [InlineKeyboardButton("نسیه کردن", callback_data='credit')],
        [InlineKeyboardButton("پرداخت", callback_data='payment')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("لطفاً یک گزینه انتخاب کنید:", reply_markup=reply_markup)
    else:
        await update.callback_query.message.edit_text("لطفاً یک گزینه انتخاب کنید:", reply_markup=reply_markup)
    return MAIN_MENU

# ثبت مشتری
async def register_customer(update: Update, context: CallbackContext):
    await update.callback_query.message.edit_text("لطفاً نام مشتری را وارد کنید:")
    return NAME

async def get_name(update: Update, context: CallbackContext):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("لطفاً نام خانوادگی را وارد کنید:")
    return LAST_NAME

async def get_last_name(update: Update, context: CallbackContext):
    context.user_data['last_name'] = update.message.text
    await update.message.reply_text("لطفاً شماره تلفن را وارد کنید:")
    return PHONE

async def get_phone(update: Update, context: CallbackContext):
    phone = update.message.text
    conn = sqlite3.connect('accounting_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO customers (name, last_name, phone, balance) VALUES (?, ?, ?, ?)",
              (context.user_data['name'], context.user_data['last_name'], phone, 0.0))
    conn.commit()
    conn.close()
    await update.message.reply_text("مشتری با موفقیت ثبت شد!")
    return await show_main_menu(update, context)

# نسیه کردن
async def credit(update: Update, context: CallbackContext):
    conn = sqlite3.connect('accounting_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, name, last_name FROM customers")
    customers = c.fetchall()
    conn.close()
    
    if not customers:
        await update.callback_query.message.edit_text("هیچ مشتری ثبت نشده است!")
        return await show_main_menu(update, context)
    
    keyboard = [[InlineKeyboardButton(f"{c[1]} {c[2]}", callback_data=f"cust_{c[0]}")] for c in customers]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.edit_text("لطفاً مشتری را انتخاب کنید:", reply_markup=reply_markup)
    return SELECT_CUSTOMER

async def select_customer(update: Update, context: CallbackContext):
    query = update.callback_query
    customer_id = query.data.split('_')[1]
    context.user_data['customer_id'] = customer_id
    
    # لیست خوراکی‌های پیش‌فرض
    foods = [("ساندویچ", 50000), ("پیتزا", 100000), ("نوشابه", 20000)]
    keyboard = [[InlineKeyboardButton(f"{f[0]} ({f[1]} تومان)", callback_data=f"food_{f[0]}_{f[1]}")] for f in foods]
    keyboard.append([InlineKeyboardButton("قیمت دستی", callback_data='custom_price')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("لطفاً خوراکی را انتخاب کنید:", reply_markup=reply_markup)
    return SELECT_FOOD

async def select_food(update: Update, context: CallbackContext):
    query = update.callback_query
    if query.data == 'custom_price':
        await query.message.edit_text("لطفاً نام خوراکی را وارد کنید:")
        return CUSTOM_PRICE
    else:
        food, price = query.data.split('_')[1], float(query.data.split('_')[2])
        customer_id = context.user_data['customer_id']
        
        conn = sqlite3.connect('accounting_bot.db')
        c = conn.cursor()
        c.execute("UPDATE customers SET balance = balance + ? WHERE id = ?", (price, customer_id))
        c.execute("INSERT INTO transactions (customer_id, food, amount, date) VALUES (?, ?, ?, ?)",
                  (customer_id, food, price, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        
        await query.message.edit_text(f"نسیه {food} با قیمت {price} تومان ثبت شد.")
        return await show_main_menu(update, context)

async def custom_price(update: Update, context: CallbackContext):
    context.user_data['food'] = update.message.text
    await update.message.reply_text("لطفاً قیمت خوراکی را وارد کنید (به تومان):")
    return SELECT_PRICE

async def select_price(update: Update, context: CallbackContext):
    price = float(update.message.text)
    customer_id = context.user_data['customer_id']
    food = context.user_data['food']
    
    conn = sqlite3.connect('accounting_bot.db')
    c = conn.cursor()
    c.execute("UPDATE customers SET balance = balance + ? WHERE id = ?", (price, customer_id))
    c.execute("INSERT INTO transactions (customer_id, food, amount, date) VALUES (?, ?, ?, ?)",
              (customer_id, food, price, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"نسیه {food} با قیمت {price} تومان ثبت شد.")
    return await show_main_menu(update, context)

# پرداخت
async def payment(update: Update, context: CallbackContext):
    conn = sqlite3.connect('accounting_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, name, last_name FROM customers")
    customers = c.fetchall()
    conn.close()
    
    if not customers:
        await update.callback_query.message.edit_text("هیچ مشتری ثبت نشده است!")
        return await show_main_menu(update, context)
    
    keyboard = [[InlineKeyboardButton(f"{c[1]} {c[2]}", callback_data=f"pay_{c[0]}")] for c in customers]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.edit_text("لطفاً مشتری را انتخاب کنید:", reply_markup=reply_markup)
    return PAYMENT_MENU

async def payment_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    customer_id = query.data.split('_')[1]
    context.user_data['customer_id'] = customer_id
    await query.message.edit_text("لطفاً مبلغ پرداخت را وارد کنید (به تومان):")
    return PAYMENT_AMOUNT

async def payment_amount(update: Update, context: CallbackContext):
    amount = float(update.message.text)
    customer_id = context.user_data['customer_id']
    
    conn = sqlite3.connect('accounting_bot.db')
    c = conn.cursor()
    c.execute("UPDATE customers SET balance = balance - ? WHERE id = ?", (amount, customer_id))
    c.execute("INSERT INTO transactions (customer_id, food, amount, date) VALUES (?, ?, ?, ?)",
              (customer_id, "پرداخت", -amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"پرداخت {amount} تومان ثبت شد.")
    return await show_main_menu(update, context)

# ارسال پیام دوره‌ای و شمارش معکوس
def send_periodic_messages(app: Application):
    conn = sqlite3.connect('accounting_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, name, last_name, balance FROM customers WHERE balance > 0")
    customers = c.fetchall()
    conn.close()
    
    # محاسبه روزهای باقی‌مانده تا پایان ماه
    today = datetime.today()
    next_month = today.replace(day=28) + timedelta(days=4)
    last_day_of_month = next_month - timedelta(days=next_month.day)
    days_left = (last_day_of_month - today).days
    
    for customer in customers:
        customer_id, name, last_name, balance = customer
        message = f"مشتری گرامی {name} {last_name}\n"
        message += f"مبلغ بدهی شما: {balance} تومان\n"
        message += f"روزهای باقی‌مانده تا پایان ماه: {days_left} روز"
        app.bot.send_message(chat_id=customer_id, text=message)

def schedule_messages(app: Application):
    schedule.every(3).days.do(send_periodic_messages, app=app)
    while True:
        schedule.run_pending()
        time.sleep(60)

# لغو عملیات
async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("عملیات لغو شد.")
    return await show_main_menu(update, context)

def main():
    # توکن ربات خود را وارد کنید
    application = Application.builder().token(os.getenv("BOT_TOKEN")).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [CallbackQueryHandler(register_customer, pattern='register_customer'),
                        CallbackQueryHandler(credit, pattern='credit'),
                        CallbackQueryHandler(payment, pattern='payment')],
            NAME: [MessageHandler(Filters.text & ~Filters.command, get_name)],
            LAST_NAME: [MessageHandler(Filters.text & ~Filters.command, get_last_name)],
            PHONE: [MessageHandler(Filters.text & ~Filters.command, get_phone)],
            SELECT_CUSTOMER: [CallbackQueryHandler(select_customer)],
            SELECT_FOOD: [CallbackQueryHandler(select food)],
            CUSTOM_PRICE: [MessageHandler(Filters.text & ~Filters.command, custom_price)],
            SELECT_PRICE: [MessageHandler(Filters.text & ~Filters.command, select_price)],
            PAYMENT_MENU: [CallbackQueryHandler(payment_menu)],
            PAYMENT_AMOUNT: [MessageHandler(Filters.text & ~Filters.command, payment_amount)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    application.add_handler(conv_handler)
    
    # شروع线程 برای ارسال پیام‌های دوره‌ای
    threading.Thread(target=schedule_messages, args=(application,), daemon=True).start()
    
    application.run_polling()

if __name__ == '__main__':
    main()
