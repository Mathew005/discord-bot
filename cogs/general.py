import discord
from discord.ext import commands
from core.state import ALLOWED_CHANNEL_ID
from core.config import THEME_COLOR

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Displays the help menu showing all available commands and options.")
    async def help(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        embed = discord.Embed(
            title="PP Bot Help Menu",
            description="Welcome! This bot plays music and includes loops, queues, and persistent filters. Below are all the commands you can use:",
            color=THEME_COLOR
        )
        
        embed.add_field(
            name="Music Playback",
            value=(
                "- `/play [query]` - Play a song/query (or resume if paused).\n"
                "- `/pp [query]` - Start 24/7 stream for playlist, artist, genre or similar songs.\n"
                "- `/playnext <query>` - Add a song to play next.\n"
                "- `/queue [query]` - Add a song to the end, or view the current queue.\n"
                "- `/skip` - Skip the current song.\n"
                "- `/pause` / `/resume` - Pause or resume playback.\n"
                "- `/nowplaying` - View details of the current song."
            ),
            inline=False
        )
        
        embed.add_field(
            name="Custom Playlists & Favorites",
            value=(
                "- `/playlist save <name>` - Save the current queue as a playlist.\n"
                "- `/playlist load <name>` - Load a saved playlist into the queue.\n"
                "- `/playlist list` - View and select from saved playlists.\n"
                "- `/playlist delete <name>` - Delete a saved playlist.\n"
                "- `/favorites load` - Load your personal favorites list into the queue.\n"
                "- `/favorites list` - Manage and select from your personal favorites."
            ),
            inline=False
        )

        embed.add_field(
            name="Controls & Queues",
            value=(
                "- `/volume [vol]` - Set volume percentage, or view current volume level.\n"
                "- `/loop [song/off]` - Set loop mode, or view current loop mode.\n"
                "- `/shuffle` - Randomize the upcoming queue list.\n"
                "- `/remove [index]` - Remove a specific song from queue, or view usage.\n"
                "- `/clear` - Remove all songs from the queue.\n"
                "- `/setartist [artist]` - Set the autoplay artist, or view current configuration.\n"
                "- `/autoplay [on/off]` - Toggle autoplay on or off, or view current status.\n"
                "- `/nonstop [on/off]` - Toggle 24/7 nonstop mode, or view current status.\n"
                "- `/leave` - Disconnect from voice and clean up."
            ),
            inline=False
        )

        embed.add_field(
            name="Blacklist Filters",
            value=(
                "- `/blacklist [keyword]` - Blacklist a keyword (or current song) from playing.\n"
                "- `/unblacklist <keyword>` - Remove a keyword from the blacklist.\n"
                "- `/viewblacklist` - View all blacklisted keywords."
            ),
            inline=False
        )

        embed.add_field(
            name="General",
            value=(
                "- `/help` - Show this help menu.\n"
                "- `/ping` - Check bot latency to Discord."
            ),
            inline=False
        )

        embed.set_footer(text="All commands support prefix (e.g. !play) and slash commands (e.g. /play).")
        
        # Delete user command message if it was a prefix command
        if ctx.interaction is None:
            try:
                await ctx.message.delete()
            except Exception:
                pass
                
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="ping", description="Check the bot's latency/ping to Discord.")
    async def ping(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Latency is **{latency}ms**.")

async def setup(bot):
    await bot.add_cog(General(bot))
