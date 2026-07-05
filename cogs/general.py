import discord
from discord.ext import commands
from core.state import ALLOWED_CHANNEL_ID

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
            color=0xe74709
        )
        
        embed.add_field(
            name="Music Playback",
            value=(
                "- `/play [query]` - Play a song/query (or resume if paused).\n"
                "- `/playnext <query>` - Add a song to play next.\n"
                "- `/queue [query]` - Add a song to the end, or view the current queue.\n"
                "- `/skip` - Skip the current song.\n"
                "- `/pause` / `/resume` - Pause or resume playback.\n"
                "- `/nowplaying` - View details of the current song."
            ),
            inline=False
        )

        embed.add_field(
            name="Controls & Queues",
            value=(
                "- `/volume <0-100>` - Set playback volume percentage.\n"
                "- `/loop <song/queue/off>` - Set loop/repeat mode.\n"
                "- `/shuffle` - Randomize the upcoming queue list.\n"
                "- `/remove <index>` - Remove a specific song from queue.\n"
                "- `/clear` - Remove all songs from the queue.\n"
                "- `/setartist <artist>` - Set the autoplay artist.\n"
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
