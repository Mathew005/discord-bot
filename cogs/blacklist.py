import discord
from discord.ext import commands
from core.filters import blacklist_set, save_blacklist, is_blacklisted
from core.state import get_guild_state, ALLOWED_CHANNEL_ID

class Blacklist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="blacklist", aliases=["bl"], description="Blacklist a title or keyword from playing, and skip if currently playing.")
    @discord.app_commands.describe(keyword="The title, phrase, or keyword to blacklist. Leave empty to blacklist the currently playing track.")
    async def blacklist(self, ctx: commands.Context, *, keyword: str = None):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)

        # If no keyword is provided, blacklist the currently playing track
        if not keyword:
            if not state.current_track:
                await ctx.send("Nothing is currently playing to blacklist. Provide a keyword instead.", ephemeral=True)
                return
            keyword = state.current_track['title']

        keyword_lower = keyword.strip().lower()
        if keyword_lower in blacklist_set:
            await ctx.send(f"**{keyword}** is already blacklisted.", ephemeral=True)
            return

        blacklist_set.add(keyword_lower)
        save_blacklist(blacklist_set)
        await ctx.send(f"Added to blacklist: **{keyword}**")

        # If currently playing matches the new blacklisted keyword, skip it immediately
        if state.current_track and is_blacklisted(state.current_track['title'], state.current_track['url']):
            await ctx.send("Currently playing track matches blacklist. Skipping...")
            if state.voice_client:
                state.voice_client.stop()

    @commands.hybrid_command(name="unblacklist", aliases=["unbl"], description="Remove a keyword or title from the blacklist.")
    @discord.app_commands.describe(keyword="The blacklisted keyword or title to remove.")
    async def unblacklist(self, ctx: commands.Context, *, keyword: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        keyword_lower = keyword.strip().lower()
        if keyword_lower not in blacklist_set:
            await ctx.send(f"**{keyword}** is not in the blacklist.", ephemeral=True)
            return

        blacklist_set.remove(keyword_lower)
        save_blacklist(blacklist_set)
        await ctx.send(f"Removed from blacklist: **{keyword}**")

    @commands.hybrid_command(name="viewblacklist", aliases=["vbl"], description="Display the list of blacklisted items.")
    async def viewblacklist(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        if not blacklist_set:
            await ctx.send("The blacklist is currently empty.")
            return

        items = [f"• {item}" for item in sorted(blacklist_set)]
        list_str = "\n".join(items)
        
        if len(list_str) > 1900:
            list_str = list_str[:1900] + "\n*...and more*"
            
        await ctx.send(f"**Blacklisted Items:**\n{list_str}")

async def setup(bot):
    await bot.add_cog(Blacklist(bot))
