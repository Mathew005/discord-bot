import discord
from discord.ext import commands
import yt_dlp
import asyncio
import random
import time
from core.audio import ytdl_format_options, ytdl
from core.filters import is_blacklisted
from core.state import get_guild_state, ALLOWED_CHANNEL_ID, create_now_playing_embed
import core.state as state_module

# ----------------- Interactive Music Playback Controller -----------------

class MusicControlView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        
        state = get_guild_state(guild_id, bot)
        
        is_paused = state.voice_client and state.voice_client.is_paused()
        self.pause_resume.label = "▶️" if is_paused else "⏸️"
        self.pause_resume.style = discord.ButtonStyle.success if is_paused else discord.ButtonStyle.primary

        if state.loop_mode != 'off':
            self.loop_toggle.style = discord.ButtonStyle.success
        else:
            self.loop_toggle.style = discord.ButtonStyle.primary

    @discord.ui.button(label="⏸️", style=discord.ButtonStyle.primary, custom_id="music_ctrl_pause_resume")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        if not state.voice_client or not state.voice_client.is_connected():
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return

        if not interaction.user.voice or interaction.user.voice.channel != state.voice_client.channel:
            await interaction.response.send_message("You must be in the same voice channel to control playback.", ephemeral=True)
            return

        if state.voice_client.is_playing():
            state.voice_client.pause()
            state.elapsed_offset += time.monotonic() - state.start_time
            button.label = "▶️"
            button.style = discord.ButtonStyle.success
        elif state.voice_client.is_paused():
            state.voice_client.resume()
            state.start_time = time.monotonic()
            button.label = "⏸️"
            button.style = discord.ButtonStyle.primary
        else:
            await interaction.response.send_message("Nothing is currently playing.", ephemeral=True)
            return

        embed = create_now_playing_embed(state)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🔁", style=discord.ButtonStyle.primary, custom_id="music_ctrl_loop")
    async def loop_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        if not interaction.user.voice or (state.voice_client and interaction.user.voice.channel != state.voice_client.channel):
            await interaction.response.send_message("You must be in the same voice channel to change loop mode.", ephemeral=True)
            return

        modes = ['off', 'song', 'queue']
        current_idx = modes.index(state.loop_mode)
        state.loop_mode = modes[(current_idx + 1) % len(modes)]

        if state.loop_mode != 'off':
            button.style = discord.ButtonStyle.success
        else:
            button.style = discord.ButtonStyle.primary

        embed = create_now_playing_embed(state)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.primary, custom_id="music_ctrl_skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        if not state.voice_client or not state.voice_client.is_connected():
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return

        if not interaction.user.voice or interaction.user.voice.channel != state.voice_client.channel:
            await interaction.response.send_message("You must be in the same voice channel to skip.", ephemeral=True)
            return

        if not state.voice_client.is_playing() and not state.voice_client.is_paused():
            await interaction.response.send_message("Nothing is playing to skip.", ephemeral=True)
            return

        await interaction.response.defer()
        await state.fade_volume(0.0, duration=0.8)
        if state.voice_client:
            state.voice_client.stop()

    @discord.ui.button(label="⏹️", style=discord.ButtonStyle.danger, custom_id="music_ctrl_stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        if not state.voice_client or not state.voice_client.is_connected():
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return

        if not interaction.user.voice or interaction.user.voice.channel != state.voice_client.channel:
            non_bots = [m for m in state.voice_client.channel.members if not m.bot]
            if len(non_bots) > 0:
                await interaction.response.send_message("You must be in the same voice channel to disconnect the bot.", ephemeral=True)
                return

        await interaction.response.defer()
        await state.fade_volume(0.0, duration=0.8)
        if state.voice_client:
            await state.voice_client.disconnect()
            state.voice_client = None
        state.current_track = None
        state.queue.clear()
        
        for child in self.children:
            child.disabled = True
        
        embed = discord.Embed(title="Stopped", description="Playback stopped and bot disconnected.", color=discord.Color.red())
        await interaction.message.edit(embed=embed, view=self)


# ----------------- Interactive Dropdown Select Menu for Queue -----------------

class QueueSelect(discord.ui.Select):
    def __init__(self, bot, guild_id, options_list):
        super().__init__(placeholder="Select a track to skip directly to it...", min_values=1, max_values=1, options=options_list)
        self.bot = bot
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        selected_index = int(self.values[0])
        state = get_guild_state(self.guild_id, self.bot)
        
        if not interaction.user.voice or (state.voice_client and interaction.user.voice.channel != state.voice_client.channel):
            await interaction.response.send_message("You must be in the same voice channel as the bot to manage the queue.", ephemeral=True)
            return

        if selected_index < 0 or selected_index >= len(state.queue):
            await interaction.response.send_message("This song is no longer in the queue.", ephemeral=True)
            return

        chosen_track = state.queue[selected_index]
        
        # Keep the chosen track at index 0, purge preceding tracks
        state.queue = state.queue[selected_index:]
        if state.voice_client:
            state.voice_client.stop() # Trigger immediate skip to this song
            
        await interaction.response.send_message(f"Skipping directly to: **{chosen_track['title']}**", ephemeral=True)


class QueueSelectView(discord.ui.View):
    def __init__(self, bot, guild_id, queue_list):
        super().__init__(timeout=60.0)
        options = []
        for idx, track in enumerate(queue_list[:25]):
            options.append(discord.SelectOption(
                label=track['title'][:100],
                description=f"Requested by: {track['requester']}",
                value=str(idx)
            ))
        if options:
            self.add_item(QueueSelect(bot, guild_id, options))


# ----------------- Music Commands Cog -----------------

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="play", aliases=["p", "start"], description="Play a song, search query, or resume configured artist.")
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

        if not state.voice_client or not state.voice_client.is_connected():
            try:
                state.voice_client = await channel.connect()
            except Exception as e:
                await ctx.send(f"Failed to join voice channel: {e}", ephemeral=True)
                return
        elif state.voice_client.channel != channel:
            if len([m for m in state.voice_client.channel.members if not m.bot]) > 0:
                if ctx.author.voice.channel != state.voice_client.channel:
                    await ctx.send("You must be in the same voice channel as the bot to move it.", ephemeral=True)
                    return
            await state.voice_client.move_to(channel)

        if query:
            await ctx.defer()
            try:
                opts_flat = {**ytdl_format_options, 'extract_flat': True}
                ytdl_flat = yt_dlp.YoutubeDL(opts_flat)
                search_results = await self.bot.loop.run_in_executor(
                    None, lambda: ytdl_flat.extract_info(f"ytsearch5:{query}" if not query.startswith("http") else query, download=False)
                )
                
                video_url = None
                title = None
                if 'entries' in search_results:
                    for entry in search_results['entries']:
                        if entry.get('ie_key') == 'Youtube':
                            video_url = entry.get('url')
                            title = entry.get('title', 'Unknown')
                            break
                else:
                    video_url = search_results.get('webpage_url')
                    title = search_results.get('title', 'Unknown')

                if not video_url:
                    await ctx.send("Could not find any playable video for that query.")
                    return

                if is_blacklisted(title, video_url):
                    await ctx.send(f"Cannot play **{title}** as it matches blacklisted keywords.")
                    return

                track = {
                    'title': title,
                    'url': video_url,
                    'requester': ctx.author.display_name,
                    'requester_mention': ctx.author.mention,
                    'requester_avatar': ctx.author.display_avatar.url if ctx.author.display_avatar else None,
                    'requested_at': time.time()
                }

                if state.voice_client.is_playing() or state.voice_client.is_paused():
                    state.queue.append(track)
                    await ctx.send(f"Added to queue: **{title}**")
                else:
                    state.queue.append(track)
                    await ctx.send(f"Playing **{title}**...")
                    await state.play_next()
            except Exception as e:
                await ctx.send(f"Error resolving query: {e}")
        else:
            if state.voice_client.is_paused():
                state.voice_client.resume()
                state.start_time = time.monotonic()
                await ctx.send("Resumed playback.")
            elif not state.voice_client.is_playing():
                await ctx.send(f"Starting configured artist autoplay for: **{state_module.configured_artist}**")
                await state.play_next()
            else:
                await ctx.send("Already playing music! Use `/queue <query>` to add a song.", ephemeral=True)

    @commands.hybrid_command(name="playnext", aliases=["pn"], description="Add a song to the front of the queue to play next.")
    async def playnext(self, ctx: commands.Context, *, query: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        if state.voice_client and state.voice_client.is_connected():
            if not ctx.author.voice or ctx.author.voice.channel != state.voice_client.channel:
                await ctx.send("You must be in the same voice channel as the bot to control it.", ephemeral=True)
                return
        elif not ctx.author.voice:
            await ctx.send("You need to join a voice channel first!", ephemeral=True)
            return

        await ctx.defer()
        try:
            opts_flat = {**ytdl_format_options, 'extract_flat': True}
            ytdl_flat = yt_dlp.YoutubeDL(opts_flat)
            search_results = await self.bot.loop.run_in_executor(
                None, lambda: ytdl_flat.extract_info(f"ytsearch5:{query}" if not query.startswith("http") else query, download=False)
            )
            
            video_url = None
            title = None
            if 'entries' in search_results:
                for entry in search_results['entries']:
                    if entry.get('ie_key') == 'Youtube':
                        video_url = entry.get('url')
                        title = entry.get('title', 'Unknown')
                        break
            else:
                video_url = search_results.get('webpage_url')
                title = search_results.get('title', 'Unknown')

            if not video_url:
                await ctx.send("Could not find any playable video for that query.")
                return

            if is_blacklisted(title, video_url):
                await ctx.send(f"Cannot play next **{title}** as it matches blacklisted keywords.")
                return

            track = {
                'title': title,
                'url': video_url,
                'requester': ctx.author.display_name,
                'requester_mention': ctx.author.mention,
                'requester_avatar': ctx.author.display_avatar.url if ctx.author.display_avatar else None,
                'requested_at': time.time()
            }

            if not state.voice_client or not state.voice_client.is_connected():
                state.voice_client = await ctx.author.voice.channel.connect()

            state.queue.insert(0, track)
            await ctx.send(f"Queued to play next: **{title}**")
            
            if not state.voice_client.is_playing() and not state.voice_client.is_paused():
                await state.play_next()
        except Exception as e:
            await ctx.send(f"Error resolving query: {e}")

    @commands.hybrid_command(name="queue", aliases=["q"], description="Add a song to the end of the queue or view the current queue.")
    async def queue(self, ctx: commands.Context, *, query: str = None):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)

        if query:
            if state.voice_client and state.voice_client.is_connected():
                if not ctx.author.voice or ctx.author.voice.channel != state.voice_client.channel:
                    await ctx.send("You must be in the same voice channel as the bot to queue music.", ephemeral=True)
                    return
            elif not ctx.author.voice:
                await ctx.send("You need to join a voice channel first!", ephemeral=True)
                return

            await ctx.defer()
            try:
                opts_flat = {**ytdl_format_options, 'extract_flat': True}
                ytdl_flat = yt_dlp.YoutubeDL(opts_flat)
                search_results = await self.bot.loop.run_in_executor(
                    None, lambda: ytdl_flat.extract_info(f"ytsearch5:{query}" if not query.startswith("http") else query, download=False)
                )
                
                video_url = None
                title = None
                if 'entries' in search_results:
                    for entry in search_results['entries']:
                        if entry.get('ie_key') == 'Youtube':
                            video_url = entry.get('url')
                            title = entry.get('title', 'Unknown')
                            break
                else:
                    video_url = search_results.get('webpage_url')
                    title = search_results.get('title', 'Unknown')

                if not video_url:
                    await ctx.send("Could not find any playable video.")
                    return

                if is_blacklisted(title, video_url):
                    await ctx.send(f"Cannot queue **{title}** as it matches blacklisted keywords.")
                    return

                track = {
                    'title': title,
                    'url': video_url,
                    'requester': ctx.author.display_name,
                    'requester_mention': ctx.author.mention,
                    'requester_avatar': ctx.author.display_avatar.url if ctx.author.display_avatar else None,
                    'requested_at': time.time()
                }

                if not state.voice_client or not state.voice_client.is_connected():
                    state.voice_client = await ctx.author.voice.channel.connect()

                state.queue.append(track)
                await ctx.send(f"Added to queue: **{title}**")
                
                if not state.voice_client.is_playing() and not state.voice_client.is_paused():
                    await state.play_next()
            except Exception as e:
                await ctx.send(f"Error resolving query: {e}")
        else:
            embed = discord.Embed(title="Current Music Queue", color=discord.Color.blurple())
            
            if state.current_track:
                embed.description = f"**Now Playing:** [{state.current_track['title']}]({state.current_track['url']}) (Requested by: {state.current_track['requester']})\n\n"
            else:
                embed.description = "Nothing is currently playing.\n\n"

            if state.queue:
                upcoming_list = []
                for idx, track in enumerate(state.queue[:10], 1):
                    upcoming_list.append(f"`{idx}.` **{track['title']}** (Requested by: {track['requester']})")
                
                if len(state.queue) > 10:
                    upcoming_list.append(f"*...and {len(state.queue) - 10} more songs*")
                
                embed.add_field(name="Upcoming Queue:", value="\n".join(upcoming_list), inline=False)
            else:
                embed.add_field(name="Upcoming Queue:", value="Queue is empty. Autoplay will play tracks from the configured artist.", inline=False)

            embed.add_field(name="Loop Mode", value=f"`{state.loop_mode.capitalize()}`", inline=True)
            embed.add_field(name="Volume", value=f"`{int(state.volume * 100)}%`", inline=True)
            
            if state.queue:
                view = QueueSelectView(self.bot, ctx.guild.id, state.queue)
                await ctx.send(embed=embed, view=view)
            else:
                await ctx.send(embed=embed)

    @commands.hybrid_command(name="skip", aliases=["s"], description="Skip the currently playing song.")
    async def skip(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        if not state.voice_client or not state.voice_client.is_connected():
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != state.voice_client.channel:
            await ctx.send("You must be in the same voice channel as the bot to skip.", ephemeral=True)
            return

        if not state.voice_client.is_playing() and not state.voice_client.is_paused():
            await ctx.send("Nothing is currently playing to skip.", ephemeral=True)
            return

        await ctx.defer()
        await state.fade_volume(0.0, duration=0.8)
        if state.voice_client:
            state.voice_client.stop()
        await ctx.send("Skipped current song.")

    @commands.hybrid_command(name="nowplaying", aliases=["np"], description="Display details of the currently playing song.")
    async def nowplaying(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        if not state.current_track:
            await ctx.send("Nothing is currently playing.", ephemeral=True)
            return

        embed = create_now_playing_embed(state)
        # Send np with interactive controls
        view = MusicControlView(self.bot, ctx.guild.id)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="volume", aliases=["v"], description="Adjust the playback volume (0-100).")
    async def volume(self, ctx: commands.Context, vol: int):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        if not state.voice_client or not state.voice_client.is_connected():
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != state.voice_client.channel:
            await ctx.send("You must be in the same voice channel to change the volume.", ephemeral=True)
            return

        if vol < 0 or vol > 100:
            await ctx.send("Volume must be between 0 and 100.", ephemeral=True)
            return

        state.set_volume(vol)
        await ctx.send(f"Volume adjusted to **{vol}%**")

    @commands.hybrid_command(name="loop", description="Change the loop mode (song, queue, off).")
    async def loop(self, ctx: commands.Context, mode: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        mode = mode.lower().strip()
        if mode not in ['song', 'queue', 'off']:
            await ctx.send("Invalid loop mode. Choose either `song`, `queue`, or `off`.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        if not ctx.author.voice or (state.voice_client and ctx.author.voice.channel != state.voice_client.channel):
            await ctx.send("You must be in the same voice channel to change loop mode.", ephemeral=True)
            return

        state.loop_mode = mode
        await ctx.send(f"Loop mode updated to: **{mode.capitalize()}**")

    @commands.hybrid_command(name="shuffle", description="Shuffle the current user queue.")
    async def shuffle(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        if not ctx.author.voice or (state.voice_client and ctx.author.voice.channel != state.voice_client.channel):
            await ctx.send("You must be in the same voice channel to shuffle the queue.", ephemeral=True)
            return

        if len(state.queue) < 2:
            await ctx.send("Not enough songs in queue to shuffle.", ephemeral=True)
            return

        random.shuffle(state.queue)
        await ctx.send("Queue shuffled successfully!")

    @commands.hybrid_command(name="pause", description="Pause playback.")
    async def pause(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        if not state.voice_client or not state.voice_client.is_connected():
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != state.voice_client.channel:
            await ctx.send("You must be in the same voice channel to pause playback.", ephemeral=True)
            return

        if state.voice_client.is_playing():
            state.voice_client.pause()
            state.elapsed_offset += time.monotonic() - state.start_time
            await ctx.send("Paused playback.")
        else:
            await ctx.send("Audio is not currently playing.", ephemeral=True)

    @commands.hybrid_command(name="resume", description="Resume playback.")
    async def resume(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        if not state.voice_client or not state.voice_client.is_connected():
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != state.voice_client.channel:
            await ctx.send("You must be in the same voice channel to resume playback.", ephemeral=True)
            return

        if state.voice_client.is_paused():
            state.voice_client.resume()
            state.start_time = time.monotonic()
            await ctx.send("Resumed playback.")
        else:
            await ctx.send("Playback is not currently paused.", ephemeral=True)

    @commands.hybrid_command(name="remove", description="Remove a specific song from the queue by its index.")
    async def remove(self, ctx: commands.Context, index: int):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        if not ctx.author.voice or (state.voice_client and ctx.author.voice.channel != state.voice_client.channel):
            await ctx.send("You must be in the same voice channel to remove tracks.", ephemeral=True)
            return

        if index < 1 or index > len(state.queue):
            await ctx.send(f"Invalid index. Specify a number between 1 and {len(state.queue)}.", ephemeral=True)
            return

        removed = state.queue.pop(index - 1)
        await ctx.send(f"Removed from queue: **{removed['title']}**")

    @commands.hybrid_command(name="clear", description="Clear all songs in the queue.")
    async def clear(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        if not ctx.author.voice or (state.voice_client and ctx.author.voice.channel != state.voice_client.channel):
            await ctx.send("You must be in the same voice channel to clear the queue.", ephemeral=True)
            return

        state.queue.clear()
        await ctx.send("Queue cleared.")

    @commands.hybrid_command(name="leave", aliases=["l", "stop", "disconnect", "dc"], description="Disconnect the bot from the voice channel.")
    async def leave(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        if not state.voice_client or not state.voice_client.is_connected():
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != state.voice_client.channel:
            non_bots = [m for m in state.voice_client.channel.members if not m.bot]
            if len(non_bots) > 0:
                await ctx.send("You must be in the same voice channel as the bot to disconnect it.", ephemeral=True)
                return

        await ctx.defer()
        await state.fade_volume(0.0, duration=0.8)
        if state.voice_client:
            await state.voice_client.disconnect()
            state.voice_client = None
        state.current_track = None
        state.queue.clear()
        await ctx.send("Disconnected from voice channel.")

    @commands.hybrid_command(name="setartist", aliases=["sa", "set", "artist"], description="Configure the autoplay artist and update immediately if playing.")
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
        if state.voice_client and state.voice_client.is_connected() and state.voice_client.is_playing():
            if state.current_track and state.current_track['requester'] == 'Autoplay':
                await ctx.send("Updating autoplay playlist and playing the new artist immediately...")
                await state.update_artist_playlist()
                state.voice_client.stop()

async def setup(bot):
    await bot.add_cog(Music(bot))
