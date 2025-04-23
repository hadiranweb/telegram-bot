import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler
)
from telegram.ext.filters import Text, Command
from datetime import datetime, timedelta
import schedule
import time
import threading
import os
import calendar
import telegram.error

# تنظیم لاگینگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ثابت‌های مراحل
ROLE, SELLER_PASSWORD, CUSTOMER_MENU, CREDIT_PURCHASE, ACCOUNT_MENU, TRACKING_CODE, REMINDER_TYPE, CUSTOMER_NAME, CUSTOMER_PHONE, CUSTOMER_PAYMENT, PAYMENT_AMOUNT, CONFIRM_PAYMENT = range(12)

# اطلاعات فروشگاه
STORE_OWNER = "نام صاحب فروشگاه"
CARD_NUMBER = "1234-5678-9012-3456"
SHABA_NUMBER = "IR123456789012345678901234"
PASSWORD = os.getenv("SELLER_PASSWORD", "your_secure_password")

def init_db():
    conn = sqlite3.connect('/tmp/accounting_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id TEXT UNIQUE,
        first_name TEXT,
        last_name TEXT,
        phone TEXT,
        balance REAL DEFAULT 0,
        reminder_type TEXT,
        reminder_last_sent TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        food TEXT,
        amount REAL,
        date TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS foods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        price REAL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        amount REAL,
        tracking_code TEXT,
        confirmed INTEGER DEFAULT 0,
        date TEXT
    )''')
    c.execute("INSERT OR IGNORE INTO foods (name, price) VALUES (?, ?)", ("ساندویچ", 50000))
    c.execute("INSERT OR IGNORE INTO foods (name, price) VALUES (?, ?)", ("پیتزا", 100000))
    conn.commit()
    conn.close()

async def start(update: Update, context):
    init_db()
    keyboard = [
        [InlineKeyboardButton("مشتری هستم", callback_data='customer')],
        [InlineKeyboardButton("فروشنده هستم", callback_data='seller')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("لطفاً نقش خود را انتخاب کنید:", reply_markup=reply_markup)
    return ROLE

async def select_role(update: Update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['role'] = query.data
    
    if query.data == 'customer':
        telegram_id = str(query.from_user.id)
        conn = sqlite3.connect('/tmp/accounting_bot.db')
        c = conn.cursor()
        c.execute("SELECT id, first_name, last_name FROM customers WHERE telegram_id = ?", (telegram_id,))
        customer = c.fetchone()
        conn.close()
        
        if not customer:
            await query.message.edit_text("شما هنوز ثبت‌نشده‌اید. لطفاً با فروشنده تماس بگیرید.")
            return ConversationHandler.END
        
        context.user_data['customer_id'] = customer[0]
        keyboard = [
            [InlineKeyboardButton("خرید اعتباری", callback_data='credit_purchase')],
            [InlineKeyboardButton("حساب", callback_data='account')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("منوی مشتری:", reply_markup=reply_markup)
        return CUSTOMER_MENU
    else:
        keyboard = [
            [InlineKeyboardButton("ورود با رمز", callback_data='enter_password')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("لطفاً گزینه را انتخاب کنید:", reply_markup=reply_markup)
        return SELLER_PASSWORD

async def check_password(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    # فرض می‌کنیم رمز از قبل در متغیر محیطی تنظیم شده است
    keyboard = [
        [InlineKeyboardButton("مشتری اعتباری جدید", callback_data='new_customer')],
        [InlineKeyboardButton("تأیید/ثبت پرداخت", callback_data='payment')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("منوی فروشنده:", reply_markup=reply_markup)
    return CUSTOMER_NAME

async def customer_menu(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'credit_purchase':
        conn = sqlite3.connect('/tmp/accounting_bot.db')
        c = conn.cursor()
        c.execute("SELECT name, price FROM foods")
        foods = c.fetchall()
        conn.close()
        
        keyboard = [
            [InlineKeyboardButton(f"{f[0]} - {f[1]} تومان", callback_data=f"food_{f[0]}_{f[1]}")]
            for f in foods
        ]
        keyboard.append([InlineKeyboardButton("قیمت دلخواه", callback_data='custom_price')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("لطفاً خوراکی را انتخاب کنید:", reply_markup=reply_markup)
        return CREDIT_PURCHASE
    elif query.data == 'account':
        keyboard = [
            [InlineKeyboardButton("مانده حساب", callback_data='balance')],
            [InlineKeyboardButton("ثبت کد رهگیری پرداخت", callback_data='tracking_code')],
            [InlineKeyboardButton("تنظیم یادآور", callback_data='reminder')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("منوی حساب:", reply_markup=reply_markup)
        return ACCOUNT_MENU

async def credit_purchase(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'custom_price':
        keyboard = [
            [InlineKeyboardButton("ساندویچ", callback_data='custom_sandwich')],
            [InlineKeyboardButton("پیتزا", callback_data='custom_pizza')],
            [InlineKeyboardButton("غذای دیگر", callback_data='custom_other')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("لطفاً نوع خوراکی را انتخاب کنید:", reply_markup=reply_markup)
        return CUSTOMER_NAME
    else:
        food, price = query.data.split('_')[1], float(query.data.split('_')[2])
        customer_id = context.user_data['customer_id']
        
        conn = sqlite3.connect('/tmp/accounting_bot.db')
        c = conn.cursor()
        c.execute("UPDATE customers SET balance = balance + ? WHERE id = ?", (price, customer_id))
        c.execute("INSERT INTO transactions (customer_id, food, amount, date) VALUES (?, ?, ?, ?)",
                  (customer_id, food, price, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        
        await query.message.edit_text(f"نسیه {food} با قیمت {price} تومان ثبت شد.")
        return await show_customer_menu(update, context)

async def custom_price(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    food_name = query.data.split('_')[1]
    context.user_data['food_name'] = food_name.capitalize()
    
    keyboard = [
        [InlineKeyboardButton("50,000 تومان", callback_data='price_50000')],
        [InlineKeyboardButton("100,000 تومان", callback_data='price_100000')],
        [InlineKeyboardButton("200,000 تومان", callback_data='price_200000')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("لطفاً قیمت را انتخاب کنید:", reply_markup=reply_markup)
    return PAYMENT_AMOUNT

async def transaction_amount(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    price = float(query.data.split('_')[1])
    customer_id = context.user_data['customer_id']
    food = context.user_data['food_name']
    
    conn = sqlite3.connect('/tmp/accounting_bot.db')
    c = conn.cursor()
    c.execute("UPDATE customers SET balance = balance + ? WHERE id = ?", (price, customer_id))
    c.execute("INSERT INTO transactions (customer_id, food, amount, date) VALUES (?, ?, ?, ?)",
              (customer_id, food, price, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    await query.message.edit_text(f"نسیه {food} با قیمت {price} تومان ثبت شد.")
    return await show_customer_menu(update, context)

async def account_menu(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    customer_id = context.user_data['customer_id']
    conn = sqlite3.connect('/tmp/accounting_bot.db')
    c = conn.cursor()
    
    if query.data == 'balance':
        c.execute("SELECT first_name, last_name, balance FROM customers WHERE id = ?", (customer_id,))
        customer = c.fetchone()
        await query.message.edit_text(f"مانده حساب {customer[0]} {customer[1]}: {customer[2]} تومان")
    elif query.data == 'tracking_code':
        await query.message.edit_text("لطفاً کد رهگیری پرداخت را وارد کنید:")
        conn.close()
        return TRACKING_CODE
    elif query.data == 'reminder':
        keyboard = [
            [InlineKeyboardButton("روزانه (ساعت ۱۶)", callback_data='daily')],
            [InlineKeyboardButton("هفتگی (چهارشنبه ساعت ۱۶)", callback_data='weekly')],
            [InlineKeyboardButton("ماهانه (چهارشنبه آخر ماه ساعت ۱۶)", callback_data='monthly')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("نوع یادآور را انتخاب کنید:", reply_markup=reply_markup)
        conn.close()
        return REMINDER_TYPE
    
    conn.close()
    return await show_customer_menu(update, context)

async def tracking_code(update: Update, context):
    tracking_code = update.message.text
    customer_id = context.user_data['customer_id']
    
    conn = sqlite3.connect('/tmp/accounting_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO payments (customer_id, tracking_code, date) VALUES (?, ?, ?)",
              (customer_id, tracking_code, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    await update.message.reply_text("کد رهگیری ثبت شد و در انتظار تأیید فروشنده است.")
    return await show_customer_menu(update, context)

async def reminder_type(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    reminder_type = query.data
    customer_id = context.user_data['customer_id']
    
    conn = sqlite3.connect('/tmp/accounting_bot.db')
    c = conn.cursor()
    c.execute("UPDATE customers SET reminder_type = ? WHERE id = ?", (reminder_type, customer_id))
    conn.commit()
    conn.close()
    
    await query.message.edit_text(f"یادآور {reminder_type} تنظیم شد.")
    return await show_customer_menu(update, context)

async def seller_menu(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'new_customer':
        keyboard = [
            [InlineKeyboardButton("ثبت مشتری با اطلاعات پیش‌فرض", callback_data='default_customer')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("لطفاً گزینه را انتخاب کنید:", reply_markup=reply_markup)
        return CUSTOMER_NAME
    elif query.data == 'payment':
        conn = sqlite3.connect('/tmp/accounting_bot.db')
        c = conn.cursor()
        c.execute("SELECT id, first_name, last_name FROM customers")
        customers = c.fetchall()
        conn.close()
        
        if not customers:
            await query.message.edit_text("هیچ مشتری ثبت‌نشده‌ای وجود ندارد.")
            return ConversationHandler.END
        
        keyboard = [
            [InlineKeyboardButton(f"{c[1]} {c[2]}", callback_data=f"customer_{c[0]}")]
            for c in customers
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("لطفاً مشتری را انتخاب کنید:", reply_markup=reply_markup)
        return CUSTOMER_PAYMENT

async def new_customer(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    telegram_id = str(query.from_user.id)  # استفاده از آیدی فروشنده یا مشتری
    first_name = query.from_user.first_name or "مشتری"
    last_name = query.from_user.last_name or ""
    phone = "نامشخص"
    
    conn = sqlite3.connect('/tmp/accounting_bot.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO customers (telegram_id, first_name, last_name, phone) VALUES (?, ?, ?, ?)",
              (telegram_id, first_name, last_name, phone))
    conn.commit()
    conn.close()
    
    await query.message.edit_text(f"مشتری {first_name} {last_name} با موفقیت ثبت شد!")
    return await show_seller_menu(update, context)

async def customer_payment(update: Update, context):
    query = update.callback_query
    await query.answer()
    customer_id = int(query.data.split('_')[1])
    context.user_data['customer_id'] = customer_id
    
    conn = sqlite3.connect('/tmp/accounting_bot.db')
    c = conn.cursor()
    c.execute("SELECT tracking_code, amount FROM payments WHERE customer_id = ? AND confirmed = 0", (customer_id,))
    pending_payments = c.fetchall()
    conn.close()
    
    keyboard = [[InlineKeyboardButton("ثبت مبلغ دستی", callback_data='manual_payment')]]
    if pending_payments:
        for p in pending_payments:
            keyboard.append([InlineKeyboardButton(f"تأیید کد {p[0]} ({p[1]} تومان)", callback_data=f"confirm_{p[0]}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("گزینه پرداخت:", reply_markup=reply_markup)
    return CONFIRM_PAYMENT

async def confirm_payment(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'manual_payment':
        keyboard = [
            [InlineKeyboardButton("50,000 تومان", callback_data='payment_50000')],
            [InlineKeyboardButton("100,000 تومان", callback_data='payment_100000')],
            [InlineKeyboardButton("200,000 تومان", callback_data='payment_200000')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("لطفاً مبلغ پرداختی را انتخاب کنید:", reply_markup=reply_markup)
        return PAYMENT_AMOUNT
    else:
        tracking_code = query.data.split('_')[1]
        customer_id = context.user_data['customer_id']
        
        conn = sqlite3.connect('/tmp/accounting_bot.db')
        c = conn.cursor()
        c.execute("SELECT amount FROM payments WHERE tracking_code = ? AND customer_id = ?", (tracking_code, customer_id))
        amount = c.fetchone()[0]
        c.execute("UPDATE customers SET balance = balance - ? WHERE id = ?", (amount, customer_id))
        c.execute("UPDATE payments SET confirmed = 1 WHERE tracking_code = ?", (tracking_code,))
        conn.commit()
        conn.close()
        
        await query.message.edit_text(f"پرداخت با کد {tracking_code} تأیید شد.")
        return await show_seller_menu(update, context)

async def payment_amount(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    amount = float(query.data.split('_')[1])
    customer_id = context.user_data['customer_id']
    
    conn = sqlite3.connect('/tmp/accounting_bot.db')
    c = conn.cursor()
    c.execute("UPDATE customers SET balance = balance - ? WHERE id = ?", (amount, customer_id))
    c.execute("INSERT INTO payments (customer_id, amount, tracking_code, confirmed, date) VALUES (?, ?, ?, ?, ?)",
              (customer_id, amount, 'manual', 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    await query.message.edit_text(f"پرداخت {amount} تومان ثبت شد.")
    return await show_seller_menu(update, context)

async def show_customer_menu(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("خرید اعتباری", callback_data='credit_purchase')],
        [InlineKeyboardButton("حساب", callback_data='account')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if hasattr(update, 'callback_query'):
        await update.callback_query.message.edit_text("منوی مشتری:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("منوی مشتری:", reply_markup=reply_markup)
    return CUSTOMER_MENU

async def show_seller_menu(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("مشتری اعتباری جدید", callback_data='new_customer')],
        [InlineKeyboardButton("تأیید/ثبت پرداخت", callback_data='payment')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if hasattr(update, 'callback_query'):
        await update.callback_query.message.edit_text("منوی فروشنده:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("منوی فروشنده:", reply_markup=reply_markup)
    return CUSTOMER_NAME

async def cancel(update: Update, context):
    await update.message.reply_text("عملیات لغو شد.")
    if context.user_data.get('role') == 'customer':
        return await show_customer_menu(update, context)
    else:
        return await show_seller_menu(update, context)

def send_reminder(customer_id, telegram_id, first_name, last_name, balance):
    message = (
        f"مشتری عزیز {first_name} {last_name}،\n"
        f"با توجه به جمع حساب شما به مبلغ {balance} تومان، لطفاً نسبت به پرداخت آن اقدام کنید.\n"
        f"شماره کارت: {CARD_NUMBER}\n"
        f"شماره شبا: {SHABA_NUMBER}\n"
        f"به نام: {STORE_OWNER}"
    )
    try:
        bot = Application.builder().token(os.getenv("BOT_TOKEN")).build()
        bot.run_polling([bot.bot.send_message(chat_id=telegram_id, text=message)])
    except:
        logger.error(f"Failed to send reminder to {telegram_id}")

def schedule_reminders():
    conn = sqlite3.connect('/tmp/accounting_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, telegram_id, first_name, last_name, balance, reminder_type, reminder_last_sent FROM customers WHERE reminder_type IS NOT NULL")
    customers = c.fetchall()
    
    for customer in customers:
        customer_id, telegram_id, first_name, last_name, balance, reminder_type, last_sent = customer
        now = datetime.now()
        last_sent = datetime.strptime(last_sent, "%Y-%m-%d %H:%M:%S") if last_sent else None
        
        if balance <= 0:
            continue
        
        should_send = False
        if reminder_type == 'daily' and (not last_sent or (now - last_sent).days >= 1):
            if now.hour == 16:
                should_send = True
        elif reminder_type == 'weekly' and (not last_sent or (now - last_sent).days >= 7):
            if now.weekday() == 2 and now.hour == 16:  # چهارشنبه
                should_send = True
        elif reminder_type == 'monthly' and (not last_sent or (now - last_sent).days >= 28):
            last_week = calendar.monthrange(now.year, now.month)[1] - 7
            if now.day >= last_week and now.weekday() == 2 and now.hour == 16:
                should_send = True
        
        if should_send:
            send_reminder(customer_id, telegram_id, first_name, last_name, balance)
            c.execute("UPDATE customers SET reminder_last_sent = ? WHERE id = ?",
                      (now.strftime("%Y-%m-%d %H:%M:%S"), customer_id))
    
    conn.commit()
    conn.close()

def run_scheduler():
    schedule.every().hour.do(schedule_reminders)
    while True:
        schedule.run_pending()
        time.sleep(60)

def main():
    try:
        application = Application.builder().token(os.getenv("BOT_TOKEN")).build()
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                ROLE: [CallbackQueryHandler(select_role)],
                SELLER_PASSWORD: [CallbackQueryHandler(check_password)],
                CUSTOMER_MENU: [CallbackQueryHandler(customer_menu)],
                CREDIT_PURCHASE: [CallbackQueryHandler(credit_purchase)],
                ACCOUNT_MENU: [CallbackQueryHandler(account_menu)],
                TRACKING_CODE: [MessageHandler(Text() & ~Command(), tracking_code)],
                REMINDER_TYPE: [CallbackQueryHandler(reminder_type)],
                CUSTOMER_NAME: [CallbackQueryHandler(new_customer)],
                CUSTOMER_PHONE: [CallbackQueryHandler(new_customer)],
                CUSTOMER_PAYMENT: [CallbackQueryHandler(customer_payment)],
                CONFIRM_PAYMENT: [CallbackQueryHandler(confirm_payment)],
                PAYMENT_AMOUNT: [CallbackQueryHandler(payment_amount)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        application.add_handler(conv_handler)
        threading.Thread(target=run_scheduler, daemon=True).start()
        application.run_polling()
    except telegram.error.Conflict:
        logger.error("Conflict detected. Retrying in 10 seconds...")
        time.sleep(10)
        main()

if __name__ == '__main__':
    main()
