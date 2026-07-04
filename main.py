import discord
from discord.ext import commands
import os
import sys
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from core.state import guild_states

load_dotenv()

# Configure Logging
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# File handler with rotation (5 MB per file, max 3 backups)
file_handler = RotatingFileHandler('logs/bot.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Suppress overly verbose discord.py debug logs
logging.getLogger('discord').setLevel(logging.INFO)

# Force UTF-8 encoding for stdout on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    logging.info(f"Bot logged in as {bot.user}")
    try:
        for guild in bot.guilds:
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
            print(f"Cleared command tree duplicates from guild: {guild.name}")
            
        # Sync only globally to keep listings clean
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands globally.")
    except Exception as e:
        print(f"Error syncing command tree: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    # 1. Disconnect / Kick cleanup
    if member.id == bot.user.id:
        if after.channel is None:
            state = guild_states.get(before.channel.guild.id)
            if state:
                print(f"[DEBUG] Bot was disconnected from voice channel in guild {before.channel.guild.name}. Cleaning up.")
                state.voice_client = None
                state.current_track = None
                state.queue.clear()
            return
        elif before.channel and after.channel and before.channel != after.channel:
            state = guild_states.get(after.channel.guild.id)
            if state:
                state.voice_client = after.channel.guild.voice_client
                print(f"[DEBUG] Bot was moved to channel: {after.channel.name}")
            return

    # 2. Leave if voice channel becomes empty (except for the bot itself)
    if before.channel:
        voice_client = before.channel.guild.voice_client
        if voice_client and voice_client.channel == before.channel:
            non_bots = [m for m in before.channel.members if not m.bot]
            if len(non_bots) == 0:
                print(f"[DEBUG] Voice channel {before.channel.name} is empty. Leaving.")
                await voice_client.disconnect()
                state = guild_states.get(before.channel.guild.id)
                if state:
                    state.voice_client = None
                    state.current_track = None
                    state.queue.clear()

# ----------------- Extension Loader -----------------

async def load_extensions():
    # Load cogs
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.blacklist")
    await bot.load_extension("cogs.general")
    await bot.load_extension("cogs.playlist")
    await bot.load_extension("cogs.history")
    print("[DEBUG] Loaded all cogs successfully.")

async def main():
    async with bot:
        await load_extensions()
        token = os.getenv("TOKEN")
        if not token:
            print("Error: TOKEN is missing in .env file.")
            return
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
