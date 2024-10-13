import os
import base64
import io
from PIL import Image
import telebot
from together import Together
from telebot import types
from dotenv import load_dotenv  # For loading environment variables
import logging
import time
from collections import defaultdict

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot.log"),
              logging.StreamHandler()])
logger = logging.getLogger(__name__)

# Get API keys from environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

if not TELEGRAM_TOKEN or not TOGETHER_API_KEY:
    logger.error(
        "Environment variables TELEGRAM_TOKEN and TOGETHER_API_KEY must be set."
    )
    raise ValueError(
        "Environment variables TELEGRAM_TOKEN and TOGETHER_API_KEY must be set."
    )
else:
    logger.info("Environment variables loaded successfully.")

# Initialize Together API client
client = Together(api_key=TOGETHER_API_KEY)

# Initialize Telegram bot
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Rate limiting settings
user_request_times = defaultdict(list)
RATE_LIMIT = 5  # Maximum 5 requests
TIME_WINDOW = 60  # Within 60 seconds


def is_rate_limited(user_id):
    """
    Checks if the user has exceeded the rate limit.
    """
    current_time = time.time()
    user_request_times[user_id] = [
        t for t in user_request_times[user_id]
        if current_time - t < TIME_WINDOW
    ]
    if len(user_request_times[user_id]) >= RATE_LIMIT:
        return True
    user_request_times[user_id].append(current_time)
    return False


def parse_generate_command(message_text):
    """
    Parses the /generate command to extract the number of images and the prompt.
    Expected formats:
    - /generate [prompt]
    - /generate [number] [prompt]
    """
    parts = message_text.strip().split()
    if len(parts) < 2:
        return None, "Please provide a prompt after the command, like '/generate a beautiful sunset over the sea' or '/generate 5 a beautiful sunset over the sea'."

    # Check if the second part is a number (count)
    try:
        count = int(parts[1])
        if count < 1:
            return None, "The number of images must be at least 1."
        if count > 11:
            count = 10  # Apply maximum limit
        prompt = ' '.join(parts[2:]).strip()
    except ValueError:
        # If the second part is not a number, assume count = 1 and the rest is the prompt
        count = 1
        prompt = ' '.join(parts[1:]).strip()

    if not prompt:
        return None, "Please provide a valid prompt after the command."

    return {'count': count, 'prompt': prompt}, None


@bot.message_handler(commands=['generate'])
def telegram_generate_image(message):
    user_id = message.from_user.id

    # Rate limiting
    if is_rate_limited(user_id):
        bot.reply_to(
            message,
            "You are sending requests too quickly. Please wait a moment and try again."
        )
        return

    # Parse command
    parsed, error = parse_generate_command(message.text)
    if error:
        bot.reply_to(message, error)
        return

    count = parsed['count']
    prompt = parsed['prompt']

    bot.reply_to(
        message,
        f"Generating {count} image(s) for the prompt: '{prompt}'. Please wait..."
    )

    images = []
    try:
        for i in range(count):
            response = client.images.generate(
                prompt=prompt,
                model="black-forest-labs/FLUX.1-schnell",
                width=1024,
                height=768,
                steps=12,
                n=4,
                response_format="b64_json").data

            if response and len(response) > 0:
                # Direct access to 'b64_json' attribute
                b64_json = response[0].b64_json

                if not b64_json:
                    raise ValueError(
                        "Invalid response format: 'b64_json' not found.")

                # Decode base64 string to bytes
                image_data = base64.b64decode(b64_json)
                image_bytes = io.BytesIO(image_data)
                image_bytes.name = f"image_{i+1}.png"  # Naming the image

                images.append(image_bytes)
            else:
                raise ValueError("No image data received from the API.")

        if not images:
            bot.reply_to(message, "No images were generated.")
            return

        if count == 1:
            # Send single image
            bot.send_photo(message.chat.id, images[0])
        else:
            # Send multiple images as an album
            media = [
                types.InputMediaPhoto(image, caption=f"Image {idx + 1}")
                for idx, image in enumerate(images)
            ]
            bot.send_media_group(message.chat.id, media)
    except Exception as e:
        logger.error(f"Error generating images: {str(e)}")
        bot.reply_to(message, f"Error: {str(e)}")


def initialize_chat_context():
    """
    Initializes a dictionary to store users' conversation history.
    """
    return {}


# Dictionary to store users' conversation history
user_conversations = initialize_chat_context()


@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = (
        "Hello! I am your friendly bot.\n\n"
        "Commands:\n"
        "/generate [number] [prompt] - Generate images based on your request. Example: /generate 3 a beautiful sunset over the sea.\n"
        "/help - Show this help message.\n\n"
        "Or simply send me a message and chat with me!")
    bot.reply_to(message, help_text)


@bot.message_handler(content_types=['photo'])
def handle_user_photo(message):
    """
    Handles user photo messages and sends them to the Together API for description.
    """
    user_id = message.from_user.id

    # Rate limiting
    if is_rate_limited(user_id):
        bot.reply_to(
            message,
            "You are sending images too quickly. Please wait a moment and try again."
        )
        return

    try:
        # Get the largest version of the photo
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Open and resize the image
        image = Image.open(io.BytesIO(downloaded_file))
        image.thumbnail((400, 400))  # Resize to a maximum of 400x400 pixels

        # Convert image to bytes with JPEG compression
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG",
                   quality=70)  # Use JPEG with quality 70
        image_bytes = buffered.getvalue()

        # Encode image to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        # Send request to Together API to describe the image
        response = client.chat.completions.create(
            model="meta-llama/Llama-Vision-Free",
            messages=[{
                "role": "system",
                "content": "You are a helpful assistant."
            }, {
                "role": "user",
                "content": "Describe the following image."
            }, {
                "role": "user",
                "content": f"<image:{image_base64}>"
            }],
            max_tokens=512,  # Set to a reasonable value
            temperature=0.7,
            top_p=0.7,
            top_k=50,
            repetition_penalty=1,
            stop=["<|eot_id|>", "<|eom_id|>"],
            stream=False)

        # Get image description from API response
        description = response.choices[0].message.content.strip()

        # Send description to user
        bot.reply_to(message, description)

    except Exception as e:
        logger.error(f"Error describing image: {str(e)}")
        bot.reply_to(message, f"Error processing image: {str(e)}")


@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_user_message(message):
    """
    Handles general text messages from users and responds using the Together chat API.
    """
    user_id = message.from_user.id
    user_message = message.text

    # Rate limiting
    if is_rate_limited(user_id):
        bot.reply_to(
            message,
            "You are sending messages too quickly. Please wait a moment and try again."
        )
        return

    # Initialize conversation history for the user if not present
    if user_id not in user_conversations:
        user_conversations[user_id] = []

    # Add user message to conversation history
    user_conversations[user_id].append({
        "role": "user",
        "content": user_message
    })

    # Limit conversation history to the last 10 messages
    MAX_HISTORY = 10
    if len(user_conversations[user_id]) > MAX_HISTORY:
        user_conversations[user_id] = user_conversations[user_id][
            -MAX_HISTORY:]

    try:
        # Send chat request to Together API
        response = client.chat.completions.create(
            model="meta-llama/Llama-Vision-Free",
            messages=user_conversations[user_id],
            max_tokens=512,  # Set to a reasonable value
            temperature=0.7,
            top_p=0.7,
            top_k=50,
            repetition_penalty=1,
            stop=["<|eot_id|>", "<|eom_id|>"],
            stream=False  # For simplicity
        )

        # Access 'message' attribute directly
        bot_reply = response.choices[0].message.content.strip()

        # Add bot reply to conversation history
        user_conversations[user_id].append({
            "role": "assistant",
            "content": bot_reply
        })

        # Send reply to user
        bot.send_message(message.chat.id, bot_reply)

    except Exception as e:
        logger.error(f"Error completing chat: {str(e)}")
        bot.reply_to(message, f"Error: {str(e)}")


# Start Telegram bot
if __name__ == "__main__":
    logger.info("Bot is starting...")
    bot.infinity_polling()
