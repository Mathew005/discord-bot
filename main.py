import discord
from discord.ext import commands
import os
import sys
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
import wavelink
from core.state import guild_states

load_dotenv()

# Startup Dependency Checks
try:
    import nacl
except ImportError:
    print("CRITICAL ERROR: 'PyNaCl' is not installed! Discord voice support will fail. Please run: pip install PyNaCl")
    sys.exit(1)

try:
    import davey
except ImportError:
    print("CRITICAL ERROR: 'davey' is not installed! Discord voice E2EE support will fail. Please run: pip install davey")
    sys.exit(1)

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
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Suppress overly verbose library debug logs
logging.getLogger('discord').setLevel(logging.WARNING)
logging.getLogger('wavelink').setLevel(logging.WARNING)

# Force UTF-8 encoding for stdout on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

async def setup_hook():
    custom_uri = os.getenv("LAVALINK_URI")
    custom_password = os.getenv("LAVALINK_PASSWORD")
    
    nodes = []
    if custom_uri:
        logging.info(f"Connecting to custom Lavalink node ({custom_uri})...")
        nodes.append(wavelink.Node(uri=custom_uri, password=custom_password or ""))
    else:
        logging.info("Connecting to public Lavalink failover pool...")
        from core.config import DEFAULT_LAVALINK_NODES
        for node_data in DEFAULT_LAVALINK_NODES:
            nodes.append(wavelink.Node(uri=node_data["uri"], password=node_data["password"]))
            
    await wavelink.Pool.connect(nodes=nodes, client=bot)
    logging.info("Wavelink pool connection requests sent.")

bot.setup_hook = setup_hook

@bot.event
async def on_ready():
    logging.info(f"Bot logged in as {bot.user}")
    try:
        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            print(f"Synced command tree instantly to guild: {guild.name}")
            
        # Also sync globally for long-term consistency
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
                await state.handle_disconnect()
            return
        elif before.channel and after.channel and before.channel != after.channel:
            state = guild_states.get(after.channel.guild.id)
            if state:
                state.voice_client = after.channel.guild.voice_client
                print(f"[DEBUG] Bot was moved to channel: {after.channel.name}")
            return

# ----------------- Extension Loader -----------------

async def load_extensions():
    # Load cogs
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.blacklist")
    await bot.load_extension("cogs.general")
    await bot.load_extension("cogs.playlist")
    await bot.load_extension("cogs.history")
    await bot.load_extension("cogs.favorites")
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
