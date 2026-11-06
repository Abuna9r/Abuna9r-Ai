import os
import logging
import asyncio
import threading
import time
import requests
from flask import Flask
from google import genai
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- سيرفر Flask لضمان التشغيل 24/7 ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "AI Bot is alive 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

def self_ping():
    time.sleep(10)
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    while True:
        try:
            if render_url:
                requests.get(render_url, timeout=10)
            else:
                requests.get("http://127.0.0.1:10000", timeout=10)
        except Exception:
            pass
        time.sleep(300)

threading.Thread(target=run_web, daemon=True).start()
threading.Thread(target=self_ping, daemon=True).start()
# ----------------------------------------

logging.basicConfig(level=logging.INFO)

# تهيئة عميل جوجل الذكي
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# قاموس لحفظ جلسات المحادثة لكل مستخدم (عشان البوت يتذكر كلامك)
user_chats = {}

def get_user_chat(user_id):
    if user_id not in user_chats:
        # إنشاء جلسة دردشة جديدة متواصلة لكل مستخدم باستخدام نموذج gemini-2.0-flash
        user_chats[user_id] = client.chats.create(model="gemini-2.0-flash")
    return user_chats[user_id]

async def post_init(application: Application):
    commands = [
        BotCommand("start", "بدء المحادثة"),
        BotCommand("new", "مسح الذاكرة وبدء محادثة جديدة"),
        BotCommand("stats", "إحصائيات البوت"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    # مسح الجلسة القديمة عند البدء
    if user_id in user_chats:
        del user_chats[user_id]
        
    await update.message.reply_text(
        "أهلاً بك! 🤖\n"
        "أنا مساعدك الذكي الشبيه بـ ChatGPT.\n"
        "تفضل اطرح أي سؤال أو اسألني عن أي شيء، وسأتذكر سياق حديثنا!\n\n"
        "💡 ملاحظة: إذا أردت مسح الذاكرة وبدء موضوع جديد، استخدم الأمر /new"
    )

async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id in user_chats:
        del user_chats[user_id]
    await update.message.reply_text("🧹 تم مسح الذاكرة بنجاح! نبدأ موضوع جديد، تفضل.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    active_sessions = len(user_chats)
    await update.message.reply_text(f"📊 عدد المحادثات النشطة حالياً في الذاكرة: {active_sessions}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_message = update.message.text

    if not user_message:
        return

    # إرسال رسالة "جاري التفكير..."
    msg = await update.message.reply_text("🧠 جاري الصياغة...")

    try:
        # الحصول على جلسة المحادثة الخاصة بالمستخدم (تحتفظ بالذاكرة)
        chat = get_user_chat(user_id)
        
        # إرسال الرسالة والحصول على الرد مع أخذ المحادثات السابقة بعين الاعتبار
        response = await asyncio.to_thread(chat.send_message, user_message)
        answer = response.text

        # تقسيم الرسالة إذا كانت طويلة جداً لتجنب حدود تليجرام
        if len(answer) > 4000:
            chunks = [answer[i:i+4000] for i in range(0, len(answer), 4000)]
            await msg.edit_text(chunks[0])
            for chunk in chunks[1:]:
                await update.message.reply_text(chunk)
        else:
            await msg.edit_text(answer)

    except Exception as e:
        logging.error(f"Gemini Error: {e}")
        await msg.edit_text(f"❌ حدث خطأ أثناء الاتصال بالذكاء الاصطناعي:\n`{str(e)}`", parse_mode="Markdown")

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("خطأ: لم يتم العثور على BOT_TOKEN!")
        return

    application = Application.builder().token(token).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_chat))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
