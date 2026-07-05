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
    @discord.app_commands.describe(artist="The name of the artist to use for autoplay streams.")
    async def setartist(self, ctx: commands.Context, *, artist: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state_module.configured_artist = artist.strip()
        
        # Persist artist selection
        try:
            with open(state_module.ARTIST_FILE, "w", encoding="utf-8") as f:
                f.write(state_module.configured_artist)
        except Exception as e:
            print(f"Error saving artist.txt: {e}")

        await ctx.send(f"Artist configured and saved to: **{state_module.configured_artist}**")

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if player and not player.current and state.autoplay_enabled:
            state.artist_playlist = []
            await state.play_autoplay()

async def setup(bot):
    await bot.add_cog(MusicSettings(bot))
