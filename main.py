import discord
from discord.ext import commands
import os
import sys
import asyncio
from dotenv import load_dotenv
from core.state import guild_states

load_dotenv()

# Force UTF-8 encoding for stdout on Windows to support logging titles with emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Intents
intents = discord.Intents.default()
intents.message_content = True

# Disable default help command to use our custom hybrid /help
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ----------------- Events -----------------

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    try:
        # Clear any previously copied guild commands to resolve duplicate listings
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
