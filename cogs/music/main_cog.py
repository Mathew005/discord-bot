import discord
from discord.ext import commands
import asyncio
import time
import wavelink
from core.filters import is_blacklisted
from core.state import get_guild_state, ALLOWED_CHANNEL_ID, create_now_playing_embed
import core.state as state_module
from core.views import MusicControlView, QueueSelectView

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="play", aliases=["p", "start"], description="Play a song from a YouTube/Spotify URL or a search query.")
    @discord.app_commands.describe(query="The song title, YouTube URL, or playlist link to search and play.")
    async def play(self, ctx: commands.Context, *, query: str = None):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        if not ctx.author.voice:
            await ctx.send("You need to join a voice channel first!", ephemeral=True)
            return

        channel = ctx.author.voice.channel
        state = get_guild_state(ctx.guild.id, self.bot)
        state.text_channel = ctx.channel

        if not state.voice_client:
            if ctx.guild.voice_client:
                state.voice_client = ctx.guild.voice_client
            else:
                try:
                    state.voice_client = await channel.connect(cls=wavelink.Player)
                except discord.Forbidden:
                    await ctx.send("❌ **Permissions Required:** I don't have permission to connect or speak in your voice channel. Please verify that my role has **Connect** and **Speak** permissions in this channel's settings!", ephemeral=True)
                    return
                except Exception as e:
                    await ctx.send(f"Failed to join voice channel: {e}", ephemeral=True)
                    return
        elif state.voice_client.channel != channel:
            if len([m for m in state.voice_client.channel.members if not m.bot]) > 0:
                if ctx.author.voice.channel != state.voice_client.channel:
                    await ctx.send("You must be in the same voice channel as the bot to move it.", ephemeral=True)
                    return
            await state.voice_client.move_to(channel)

        player = state.voice_client

        if query:
            await ctx.defer()
            try:
                tracks = await wavelink.Playable.search(query)
                if not tracks:
                    await ctx.send("Could not find any playable tracks for that query.")
                    return
                
                track = tracks[0]
                if is_blacklisted(track.title, track.uri):
                    await ctx.send(f"⚠️ **Blacklist Filter Triggered:** The track **{track.title}** was skipped because it contains filtered keywords.")
                    return

                track.extras = {
                    'requester': ctx.author.display_name,
                    'requester_mention': ctx.author.mention,
                    'requester_avatar': ctx.author.display_avatar.url if ctx.author.display_avatar else None,
                    'requester_id': ctx.author.id,
                    'requested_at': time.time()
                }

                if player.current:
                    player.queue.put(track)
                    await ctx.send(f"Added to queue: **{track.title}**")
                else:
                    await player.play(track)
                    state.write_to_history(track)
                    await ctx.send(f"Playing **{track.title}**...")
            except Exception as e:
                await ctx.send(f"Error resolving query: {e}")
        else:
            if player.paused:
                await player.pause(False)
                await ctx.send("Resumed playback.")
            elif not player.current:
                await ctx.send(f"Starting configured artist autoplay for: **{state_module.configured_artist}**")
                await state.play_autoplay()
            else:
                await ctx.send("Already playing music! Use `/queue <query>` to add a song.", ephemeral=True)

    @commands.hybrid_command(name="playnext", aliases=["pn"], description="Add a song to the front of the queue to play next.")
    @discord.app_commands.describe(query="The song title or URL to queue next.")
    async def playnext(self, ctx: commands.Context, *, query: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        if state.voice_client:
            if not ctx.author.voice or ctx.author.voice.channel != state.voice_client.channel:
                await ctx.send("You must be in the same voice channel as the bot to control it.", ephemeral=True)
                return
        elif not ctx.author.voice:
            await ctx.send("You need to join a voice channel first!", ephemeral=True)
            return

        await ctx.defer()
        try:
            tracks = await wavelink.Playable.search(query)
            if not tracks:
                await ctx.send("Could not find any playable tracks for that query.")
                return

            track = tracks[0]
            if is_blacklisted(track.title, track.uri):
                await ctx.send(f"⚠️ **Blacklist Filter Triggered:** The track **{track.title}** was skipped because it contains filtered keywords.")
                return

            track.extras = {
                'requester': ctx.author.display_name,
                'requester_mention': ctx.author.mention,
                'requester_avatar': ctx.author.display_avatar.url if ctx.author.display_avatar else None,
                'requester_id': ctx.author.id,
                'requested_at': time.time()
            }

            if not state.voice_client:
                state.voice_client = await ctx.author.voice.channel.connect(cls=wavelink.Player)
                state.text_channel = ctx.channel

            player = state.voice_client
            if player.current:
                player.queue.put_at_front(track)
                await ctx.send(f"Added to play next: **{track.title}**")
            else:
                await player.play(track)
                state.write_to_history(track)
                await ctx.send(f"Playing **{track.title}**...")
        except Exception as e:
            await ctx.send(f"Error resolving query: {e}")

    @commands.hybrid_command(name="queue", aliases=["q"], description="Add a song to the end of the queue, or view the queue if query is empty.")
    @discord.app_commands.describe(query="Optional song title or URL to add to the end of the queue.")
    async def queue(self, ctx: commands.Context, *, query: str = None):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client

        if query:
            if player:
                if not ctx.author.voice or ctx.author.voice.channel != player.channel:
                    await ctx.send("You must be in the same voice channel as the bot to queue music.", ephemeral=True)
                    return
            elif not ctx.author.voice:
                await ctx.send("You need to join a voice channel first!", ephemeral=True)
                return

            await ctx.defer()
            try:
                tracks = await wavelink.Playable.search(query)
                if not tracks:
                    await ctx.send("Could not find any playable tracks.")
                    return

                track = tracks[0]
                if is_blacklisted(track.title, track.uri):
                    await ctx.send(f"⚠️ **Blacklist Filter Triggered:** The track **{track.title}** was skipped because it contains filtered keywords.")
                    return

                track.extras = {
                    'requester': ctx.author.display_name,
                    'requester_mention': ctx.author.mention,
                    'requester_avatar': ctx.author.display_avatar.url if ctx.author.display_avatar else None,
                    'requester_id': ctx.author.id,
                    'requested_at': time.time()
                }

                if not player:
                    state.voice_client = await ctx.author.voice.channel.connect(cls=wavelink.Player)
                    state.text_channel = ctx.channel
                    player = state.voice_client

                if player.current:
                    player.queue.put(track)
                    await ctx.send(f"Added to queue: **{track.title}**")
                else:
                    await player.play(track)
                    state.write_to_history(track)
                    await ctx.send(f"Playing **{track.title}**...")
            except Exception as e:
                await ctx.send(f"Error resolving query: {e}")
        else:
            if not player or not player.current:
                await ctx.send("Nothing is currently playing.", ephemeral=True)
                return

            embed = discord.Embed(title="Current Music Queue", color=state_module.THEME_COLOR)
            embed.description = f"**Now Playing:** [{player.current.title}]({player.current.uri})\n\n"
            
            queue_list = list(player.queue)
            if queue_list:
                upcoming_list = []
                for idx, track in enumerate(queue_list[:10], 1):
                    upcoming_list.append(f"`{idx}.` **{track.title}**")
                if len(queue_list) > 10:
                    upcoming_list.append(f"*...and {len(queue_list) - 10} more songs*")
                embed.add_field(name="Upcoming Queue:", value="\n".join(upcoming_list), inline=False)
            else:
                if state.autoplay_enabled and state.artist_playlist:
                    next_song = state.artist_playlist[state.artist_index]
                    embed.add_field(name="Upcoming Queue:", value=f"🎶 **Autoplay Next:** [{next_song.title}]({next_song.uri})", inline=False)
                else:
                    embed.add_field(name="Upcoming Queue:", value="Queue is empty.", inline=False)

            view = QueueSelectView(self.bot, ctx.guild.id, queue_list) if queue_list else None
            await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="skip", aliases=["s"], description="Skip the currently playing song.")
    async def skip(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player or not player.current:
            await ctx.send("Nothing is currently playing.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            await ctx.send("You must be in the same voice channel to skip tracks.", ephemeral=True)
            return

        await player.skip(force=True)
        await ctx.send("Skipped current song.")

    @commands.hybrid_command(name="nowplaying", aliases=["np"], description="Display details of the currently playing song.")
    async def nowplaying(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player or not player.current:
            await ctx.send("Nothing is currently playing.", ephemeral=True)
            return

        embed = create_now_playing_embed(state)
        view = MusicControlView(self.bot, ctx.guild.id)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="pause", description="Pause playback.")
    async def pause(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player or not player.current:
            await ctx.send("Nothing is currently playing.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            await ctx.send("You must be in the same voice channel to pause music.", ephemeral=True)
            return

        if not player.paused:
            await player.pause(True)
            await state.update_controller()
            await ctx.send("Paused playback.")
        else:
            await ctx.send("Playback is already paused.", ephemeral=True)

    @commands.hybrid_command(name="resume", description="Resume playback.")
    async def resume(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player or not player.current:
            await ctx.send("Nothing is currently playing.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            await ctx.send("You must be in the same voice channel to resume music.", ephemeral=True)
            return

        if player.paused:
            await player.pause(False)
            await state.update_controller()
            await ctx.send("Resumed playback.")
        else:
            await ctx.send("Playback is not currently paused.", ephemeral=True)

    @commands.hybrid_command(name="summon", aliases=["move", "join"], description="Summon or move the bot to your current voice channel.")
    async def summon(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return
            
        if not ctx.author.voice:
            await ctx.send("You need to join a voice channel first!", ephemeral=True)
            return
            
        channel = ctx.author.voice.channel
        state = get_guild_state(ctx.guild.id, self.bot)
        state.text_channel = ctx.channel
        
        if not state.voice_client:
            if ctx.guild.voice_client:
                state.voice_client = ctx.guild.voice_client
            else:
                try:
                    state.voice_client = await channel.connect(cls=wavelink.Player)
                except discord.Forbidden:
                    await ctx.send("❌ **Permissions Required:** I don't have permission to connect or speak in your voice channel. Please verify that my role has **Connect** and **Speak** permissions in this channel's settings!", ephemeral=True)
                    return
                except Exception as e:
                    await ctx.send(f"Failed to join voice channel: {e}", ephemeral=True)
                    return
            await ctx.send(f"Joined **{channel.name}**.")
        else:
            await state.voice_client.move_to(channel)
            await ctx.send(f"Moved to **{channel.name}**.")

    @commands.hybrid_command(name="leave", aliases=["l", "stop", "disconnect", "dc"], description="Disconnect the bot from the voice channel.")
    async def leave(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player:
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            non_bots = [m for m in player.channel.members if not m.bot]
            if len(non_bots) > 0:
                await ctx.send("You must be in the same voice channel as the bot to disconnect it.", ephemeral=True)
                return

        await state.handle_disconnect()
        await player.disconnect()
        await ctx.send("Disconnected from voice channel.")
