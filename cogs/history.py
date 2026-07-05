import discord
from discord.ext import commands
import os
import json
from core.state import ALLOWED_CHANNEL_ID
from core.config import HISTORY_DIR, THEME_COLOR

class History(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="history", description="Show the song playback history of this server, optionally filtered by requester.")
    @discord.app_commands.describe(member="The server member to filter history by.")
    async def history(self, ctx: commands.Context, member: discord.Member = None):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        history_file = f"{HISTORY_DIR}/{ctx.guild.id}.json"
        if not os.path.exists(history_file):
            await ctx.send("No songs have been played on this server yet.", ephemeral=True)
            return

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history_list = json.load(f)
        except Exception as e:
            await ctx.send(f"Error reading history file: {e}", ephemeral=True)
            return

        if not history_list:
            await ctx.send("History is currently empty.", ephemeral=True)
            return

        if member:
            title_text = f"Playback History for {member.display_name}"
            filtered_list = [track for track in history_list if track.get('requester_id') == member.id]
        else:
            title_text = "Server Playback History"
            filtered_list = history_list

        if not filtered_list:
            await ctx.send(f"No playback history found requested by {member.display_name if member else 'anyone'}.", ephemeral=True)
            return

        embed = discord.Embed(title=title_text, color=THEME_COLOR)
        
        lines = []
        for idx, track in enumerate(filtered_list[:15], 1):
            title = track.get('title', 'Unknown')
            url = track.get('url', '')
            req_mention = track.get('requester_mention', 'Autoplay')
            played_at = track.get('played_at')
            
            if played_at:
                time_str = f"<t:{int(played_at)}:R>"
            else:
                time_str = "some time ago"
                
            lines.append(f"`{idx}.` **[{title}]({url})** - requested by {req_mention} {time_str}")

        embed.description = "\n".join(lines)
        if len(filtered_list) > 15:
            embed.set_footer(text=f"Showing recent 15 out of {len(filtered_list)} total tracks.")
            
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(History(bot))
