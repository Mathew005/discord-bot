import discord
from discord.ext import commands
import core.state as state_module
from core.state import get_guild_state, ALLOWED_CHANNEL_ID
from core.config import THEME_COLOR
import wavelink

class MusicSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="volume", aliases=["v"], description="Adjust the playback volume (0-100).")
    @discord.app_commands.describe(vol="The volume level to set, from 0 to 100.")
    async def volume(self, ctx: commands.Context, vol: int):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player:
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            await ctx.send("You must be in the same voice channel to change the volume.", ephemeral=True)
            return

        if vol < 0 or vol > 100:
            await ctx.send("Volume must be between 0 and 100.", ephemeral=True)
            return

        await player.set_volume(vol)
        await ctx.send(f"Volume adjusted to **{vol}%**")

    @commands.hybrid_command(name="loop", description="Change the loop mode (song, off).")
    @discord.app_commands.describe(mode="The loop mode to set: 'song' to loop current track, or 'off' to disable.")
    async def loop(self, ctx: commands.Context, mode: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        mode = mode.lower().strip()
        if mode not in ['song', 'off']:
            await ctx.send("Invalid loop mode. Specify 'song' or 'off'.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player:
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            await ctx.send("You must be in the same voice channel to control looping.", ephemeral=True)
            return

        if mode == 'song':
            player.queue.mode = wavelink.QueueMode.loop
            await ctx.send("Loop mode enabled: **Looping current track**.")
        else:
            player.queue.mode = wavelink.QueueMode.normal
            await ctx.send("Loop mode disabled.")

    @commands.hybrid_command(name="shuffle", description="Shuffle the current queue.")
    async def shuffle(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player:
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            await ctx.send("You must be in the same voice channel to shuffle queue.", ephemeral=True)
            return

        if len(player.queue) < 2:
            await ctx.send("Not enough songs in queue to shuffle.", ephemeral=True)
            return

        player.queue.shuffle()
        await ctx.send("Queue shuffled successfully!")

    @commands.hybrid_command(name="remove", description="Remove a specific song from the queue by its index.")
    @discord.app_commands.describe(index="The 1-based index number of the song to remove from the queue.")
    async def remove(self, ctx: commands.Context, index: int):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player:
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            await ctx.send("You must be in the same voice channel to remove tracks.", ephemeral=True)
            return

        if index < 1 or index > len(player.queue):
            await ctx.send(f"Invalid index. Specify a number between 1 and {len(player.queue)}.", ephemeral=True)
            return

        removed_track = player.queue[index - 1]
        del player.queue[index - 1]
        await ctx.send(f"Removed **{removed_track.title}** from the queue.")

    @commands.hybrid_command(name="clear", description="Clear all songs in the queue.")
    async def clear(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player:
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            await ctx.send("You must be in the same voice channel to clear queue.", ephemeral=True)
            return

        player.queue.clear()
        await ctx.send("Queue cleared.")

    @commands.hybrid_command(name="setartist", aliases=["sa", "set", "artist"], description="Configure the autoplay artist and update immediately if playing autoplay.")
    @discord.app_commands.describe(artist="Optional name of the artist to use for autoplay streams. If empty, shows current configured artist.")
    async def setartist(self, ctx: commands.Context, *, artist: str = None):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        if not artist:
            await ctx.send(f"The current autoplay artist is: **{state_module.configured_artist}**")
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        artist_name = artist.strip()
        await state.change_artist(artist_name)

        await ctx.send(f"Artist configured and saved to: **{artist_name}**")

    @commands.hybrid_command(name="autoplay", description="Toggle autoplay on or off.")
    @discord.app_commands.describe(status="Toggle status: 'on' to enable, or 'off' to disable.")
    async def autoplay(self, ctx: commands.Context, status: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        status = status.lower().strip()
        if status not in ['on', 'off']:
            await ctx.send("Invalid status. Specify 'on' or 'off'.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        enabled = (status == 'on')
        state.autoplay_enabled = enabled
        
        # If enabled and the player is idle, trigger autoplay
        if enabled:
            player = state.voice_client
            if player and not player.current and not player.queue:
                await state.play_autoplay()
                await ctx.send("Autoplay enabled and stream started.")
                return
            await ctx.send("Autoplay enabled.")
        else:
            await ctx.send("Autoplay disabled.")

    @commands.hybrid_command(name="nonstop", aliases=["247"], description="Toggle 24/7 nonprofit mode.")
    @discord.app_commands.describe(status="Toggle status: 'on' to enable, or 'off' to disable.")
    async def nonstop(self, ctx: commands.Context, status: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        status = status.lower().strip()
        if status not in ['on', 'off']:
            await ctx.send("Invalid status. Specify 'on' or 'off'.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        state.nonstop = (status == 'on')
        
        # Update nonstop status badge in the active Now Playing embed if possible
        player = state.voice_client
        if player and player.current:
            try:
                embed = state_module.create_now_playing_embed(state)
                if state.last_controller_message:
                    await state.last_controller_message.edit(embed=embed)
            except Exception:
                pass
                
        await ctx.send(f"24/7 Mode turned **{status.upper()}**.")

async def setup(bot):
    await bot.add_cog(MusicSettings(bot))
