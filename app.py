import discord
import aiohttp
import asyncio
import os
import json
import logging
import threading
from flask import Flask
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

GDRIVE_FOLDER_ID = "1vmiX3mBg8fkUTtg6zJvsjsNdls8FGHKO"

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

# 🔹 Google Drive API Authentication
SERVICE_ACCOUNT_FILE = "service_account.json"

def drive_service():
    """Google Drive service authenticate karega."""
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds)

def get_file_id(file_name):
    """Google Drive se file ka ID retrieve karega."""
    service = drive_service()
    results = service.files().list(q=f"name='{file_name}' and '{GDRIVE_FOLDER_ID}' in parents",
                                   fields="files(id)").execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None

async def read_cards_from_drive():
    """Google Drive se `cards.txt` ka content directly read karega."""
    try:
        service = drive_service()
        file_id = get_file_id("cards.txt")
        if not file_id:
            logging.warning("⚠️ cards.txt not found on Google Drive!")
            return []

        request = service.files().get_media(fileId=file_id)
        file_content = request.execute().decode("utf-8")
        cards = file_content.strip().split("\n")

        logging.info(f"✅ {len(cards)} cards found in Google Drive.")
        return cards

    except Exception as e:
        logging.error(f"❌ Error reading cards.txt from Google Drive: {e}")
        return []

async def update_cards_in_drive(updated_cards):
    """Google Drive me `cards.txt` update karega (checked cards remove karne ke liye)."""
    try:
        service = drive_service()
        file_id = get_file_id("cards.txt")

        if not updated_cards:
            if file_id:
                service.files().delete(fileId=file_id).execute()
                logging.info("🗑️ cards.txt deleted from Google Drive (all cards processed).")
            return

        with open("temp_cards.txt", "w", encoding="utf-8") as temp_file:
            temp_file.write("\n".join(updated_cards))

        media = MediaFileUpload("temp_cards.txt", mimetype="text/plain")

        if file_id:
            service.files().update(fileId=file_id, media_body=media).execute()
            logging.info("🔄 cards.txt updated on Google Drive.")

    except Exception as e:
        logging.error(f"❌ Error updating cards.txt in Google Drive: {e}")

async def check_card(card):
    """Card ko CC2 API se check karega, aur agar API error aaye to unlimited retries karega (5-second delay)."""
    logging.info(f"🔍 Checking card: {card}")

    attempt = 0  # Retry counter

    while True:  # Infinite loop for unlimited retries
        attempt += 1
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"https://cc2.ffloveryt.in/api?card={card}", timeout=10) as response:
                    if response.status != 200:
                        logging.warning(f"⚠️ CC2 API Error ({response.status}), Retrying... (Attempt {attempt})")
                        await asyncio.sleep(10)
                        continue  # Retry the same card

                    cc2_data = await response.json()

                    # ✅ Check if card is valid
                    if cc2_data.get("status").strip().upper() in ["SUCCESS", "APPROVED"]:
                        logging.info(f"✅ Card Approved: {card}")
                        return "success", card, json.dumps({"CC2 Response": cc2_data}, indent=4)

                    # ❌ If card is declined, stop retrying
                    if cc2_data.get("status").strip().upper() == "DECLINED":
                        logging.info(f"❌ Card Declined: {card}")
                        return "declined", card, json.dumps({"CC2 Response": cc2_data}, indent=4)

            except Exception as e:
                logging.warning(f"⚠️ API Error: {e}, Retrying... (Attempt {attempt})")
        
        await asyncio.sleep(5)  # 5-second delay after every check

async def process_cards():
    """Google Drive se `cards.txt` ko direct read karega, har card check karega aur remove karega."""
    logging.info("📥 Fetching cards from Google Drive...")
    cards = await read_cards_from_drive()

    if not cards:
        logging.warning("⚠️ cards.txt is empty. Waiting for new data...")
        return

    approved_cards = []

    while cards:
        card = cards.pop(0)  
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

        await update_cards_in_drive(cards)
        await asyncio.sleep(1.5)

@client.event
async def on_ready():
    logging.info(f'✅ Logged in as {client.user}')
    threading.Thread(target=run_flask).start()
    await process_cards()

client.run(TOKEN)
