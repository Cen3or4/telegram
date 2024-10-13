import os
import base64
import io
import logging
import time
from collections import defaultdict

import telebot
from together import Together
from dotenv import load_dotenv
from flask import Flask, request
from PIL import Image

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Retrieve API keys from environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

if not TELEGRAM_TOKEN or not TOGETHER_API_KEY:
    logger.error("Environment variables TELEGRAM_TOKEN and TOGETHER_API_KEY must be set.")
    raise ValueError("Environment variables TELEGRAM_TOKEN and TOGETHER_API_KEY must be set.")
else:
    logger.info("Environment variables loaded successfully.")

# Initialize Together API client
client = Together(api_key=TOGETHER_API_KEY)

# Initialize Telegram bot
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Initialize Flask app for webhook
app = Flask(__name__)

# Rate limiting settings
user_request_times = defaultdict(list)
RATE_LIMIT = int(os.getenv("RATE_LIMIT", 5))      # Maximum 5 requests
TIME_WINDOW = int(os.getenv("TIME_WINDOW", 60))  # Within 60 seconds

def is_rate_limited(user_id):
    """
    Check if the user has exceeded the rate limit.
    """
    current_time = time.time()
    # Remove timestamps older than TIME_WINDOW
    user_request_times[user_id] = [
        t for t in user_request_times[user_id]
        if current_time - t < TIME_WINDOW
    ]
    if len(user_request_times[user_id]) >= RATE_LIMIT:
        return True
    user_request_times[user_id].append(current_time)
    return False

# Webhook route for Telegram bot
@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Handle incoming webhook updates from Telegram.
    """
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@bot.message_handler(func=lambda message: True, content_types=['text'])
def generate_image_from_text(message):
    """
    Generate an image based on the user's text prompt.
    """
    user_id = message.from_user.id
    prompt = message.text.strip()

    if is_rate_limited(user_id):
        bot.reply_to(
            message,
            "🚫 شما درخواست‌ها را خیلی سریع ارسال می‌کنید. لطفاً کمی صبر کنید و دوباره تلاش کنید."
        )
        return

    # Indicate that the bot is processing the request
    bot.send_chat_action(message.chat.id, 'upload_photo')
    bot.reply_to(
        message,
        f"🖼️ در حال تولید تصویر برای پرامپت: '{prompt}'. لطفاً صبر کنید..."
    )

    try:
        # Image generation parameters
        WIDTH = int(os.getenv("IMAGE_WIDTH", 736))
        HEIGHT = int(os.getenv("IMAGE_HEIGHT", 1312))
        STEPS = int(os.getenv("IMAGE_STEPS", 4))  # Steps set to 4 as per your requirement
        MODEL = os.getenv("IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell-Free")

        # Generate image using the Together API
        response = client.images.generate(
            prompt=prompt,
            model=MODEL,
            width=WIDTH,
            height=HEIGHT,
            steps=STEPS,
            n=1,
            response_format="b64_json"
        ).data

        if response and len(response) > 0:
            b64_json = response[0].b64_json

            if not b64_json:
                raise ValueError("Invalid response format: 'b64_json' not found.")

            image_data = base64.b64decode(b64_json)
            image_bytes = io.BytesIO(image_data)
            image_bytes.name = "image.png"

            # Send the generated image
            bot.send_photo(message.chat.id, image_bytes)

            # Send sponsor message with logo and additional links
            send_sponsor_message(message.chat.id)

        else:
            raise ValueError("No image data received from the API.")

    except Exception as e:
        logger.error(f"Error generating image: {str(e)}")
        bot.reply_to(
            message, 
            f"⚠️ خطا در تولید تصویر: {str(e)}\n قوانین تولید عکس را بررسی کنید و دوباره تلاش کنید."
        )

def send_sponsor_message(chat_id):
    """
    Send sponsor information along with the logo image and promotional links in Farsi.
    """
    try:
        # Send sponsor logo
        with open('logo.jpg', 'rb') as logo_file:
            logo = logo_file.read()

        caption = (
            "✨ این بات توسط **Odin Account** پشتیبانی می‌شود.\n\n"
            "🔹 پشتیبان: [@Odinshopadmin](https://t.me/Odinshopadmin)\n"
            "🔹 کانال فروش محصولات دیجیتال ما: [@OdinDigitalshop](https://t.me/OdinDigitalshop)\n"
            "🔹 کانال اصلی ما: [@OdinAccounts](https://t.me/OdinAccounts)\n\n"
            "📌 خدمات ما را در لینک‌های زیر مشاهده کنید:\n"
            "1️⃣ **چرا بهترین خدمات “اینترنت بدون محدودیت” رو از ما دریافت می‌کنید و لیست تعرفه‌ها**\n"
            "[لینک](https://t.me/OdinAccounts/3)\n\n"
            "2️⃣ **کلیه نرم‌افزارهای لازم برای اتصال روی تمامی دستگاه‌ها**\n"
            "[لینک](https://t.me/OdinAccounts/5)\n\n"
            "3️⃣ **ثبت‌نام دوره‌های آموزشی در معتبرترین دانشگاه‌های دنیا در سایت Coursera**\n"
            "[لینک](https://t.me/OdinAccounts/44)\n\n"
            "4️⃣ **تلگرام پرمیوم و انواع گیفت‌کارت‌هایی که ما با کمترین قیمت برای شما خریداری می‌کنیم**\n"
            "[لینک](https://t.me/OdinAccounts/35)\n\n"
            "5️⃣ **خرید انواع شماره‌های مجازی معتبر از ما**\n"
            "[لینک](https://t.me/OdinAccounts/37)\n\n"
            "💠👩‍💻 [@OdinShopAdmin](https://t.me/OdinShopAdmin)"
        )

        bot.send_photo(
            chat_id,
            logo,
            caption=caption,
            parse_mode='Markdown'
        )

    except FileNotFoundError:
        logger.error("logo.jpg file not found.")
        # Send sponsor message without the logo
        caption = (
            "✨ این بات توسط **Odin Account** پشتیبانی می‌شود.\n\n"
            "🔹 پشتیبان: [@Odinshopadmin](https://t.me/Odinshopadmin)\n"
            "🔹 کانال فروش محصولات دیجیتال ما: [@OdinDigitalshop](https://t.me/OdinDigitalshop)\n"
            "🔹 کانال اصلی ما: [@OdinAccounts](https://t.me/OdinAccounts)\n\n"
            "📌 خدمات ما را در لینک‌های زیر مشاهده کنید:\n"
            "1️⃣ **چرا بهترین خدمات “اینترنت بدون محدودیت” رو از ما دریافت می‌کنید و لیست تعرفه‌ها**\n"
            "[لینک](https://t.me/OdinAccounts/3)\n\n"
            "2️⃣ **کلیه نرم‌افزارهای لازم برای اتصال روی تمامی دستگاه‌ها**\n"
            "[لینک](https://t.me/OdinAccounts/5)\n\n"
            "3️⃣ **ثبت‌نام دوره‌های آموزشی در معتبرترین دانشگاه‌های دنیا در سایت Coursera**\n"
            "[لینک](https://t.me/OdinAccounts/44)\n\n"
            "4️⃣ **تلگرام پرمیوم و انواع گیفت‌کارت‌هایی که ما با کمترین قیمت برای شما خریداری می‌کنیم**\n"
            "[لینک](https://t.me/OdinAccounts/35)\n\n"
            "5️⃣ **خرید انواع شماره‌های مجازی معتبر از ما**\n"
            "[لینک](https://t.me/OdinAccounts/37)\n\n"
            "💠👩‍💻 [@OdinShopAdmin](https://t.me/OdinShopAdmin)"
        )
        bot.send_message(
            chat_id,
            caption,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error sending sponsor message: {str(e)}")

if __name__ == "__main__":
    logger.info("🔄 Bot is starting...")
    bot.remove_webhook()
    bot.set_webhook(url="https://telegram-2vk6.onrender.com/webhook")  # Set your actual webhook URL here
    logger.info("🔗 Webhook set successfully.")
    app.run(host="0.0.0.0", port=5000)
