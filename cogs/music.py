import discord
from discord.ext import commands
import asyncio
import random
import time
import os
import json
import wavelink
from core.filters import is_blacklisted
from core.state import get_guild_state, ALLOWED_CHANNEL_ID, create_now_playing_embed
import core.state as state_module

# EMOJIS definitions from the WebP image links
EMOJIS = {
    "prev": discord.PartialEmoji(name="prev", id=932896641453801493),
    "pause": discord.PartialEmoji(name="pause", id=932896007526707271),
    "next": discord.PartialEmoji(name="next", id=932896007509925918),
    "mute": discord.PartialEmoji(name="mute", id=932898291522367488),
    "vol_down": discord.PartialEmoji(name="vol_down", id=932905272060542996),
    "vol_up": discord.PartialEmoji(name="vol_up", id=932898292084383785),
    "queue": discord.PartialEmoji(name="queue", id=932908430983823370),
    "save_fav": discord.PartialEmoji(name="save_fav", id=1073638059838545951),
    "nonstop": discord.PartialEmoji(name="nonstop", id=1073640166079606935),
    "loop": discord.PartialEmoji(name="loop", id=932908564949925938),
    "stop": discord.PartialEmoji(name="stop", id=932908751940382730),
    "shuffle": discord.PartialEmoji(name="shuffle", id=1073640745774366831),
}

# ----------------- Interactive Music Playback Controller -----------------

class MusicControlView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        
        state = get_guild_state(guild_id, bot)
        player = state.voice_client
        
        if player:
            self.pause_resume.style = discord.ButtonStyle.success if player.paused else discord.ButtonStyle.secondary
            self.loop_toggle.style = discord.ButtonStyle.success if player.queue.mode == wavelink.QueueMode.loop else discord.ButtonStyle.secondary
            self.mute_toggle.style = discord.ButtonStyle.danger if state.pre_mute_volume is not None else discord.ButtonStyle.secondary
            self.nonstop_toggle.style = discord.ButtonStyle.success if state.nonstop else discord.ButtonStyle.secondary

    # Row 0
    @discord.ui.button(emoji=EMOJIS["prev"], style=discord.ButtonStyle.secondary, row=0, custom_id="music_ctrl_prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel.id != player.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to control playback.", ephemeral=True)
            return
            
        if not state.previous_tracks:
            await interaction.response.send_message("No previous tracks in history.", ephemeral=True)
            return
            
        prev_track = state.previous_tracks.pop()
        if player.current:
            player.queue.put_at_front(player.current)
        player.queue.put_at_front(prev_track)
        await player.skip(force=True)
        await interaction.response.send_message(f"Skipping back to: **{prev_track.title}**", ephemeral=True)

    @discord.ui.button(emoji=EMOJIS["pause"], style=discord.ButtonStyle.secondary, row=0, custom_id="music_ctrl_pause_resume")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel.id != player.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to control playback.", ephemeral=True)
            return
            
        if not player.current:
            await interaction.response.send_message("Nothing is currently playing.", ephemeral=True)
            return
            
        is_paused = player.paused
        await player.pause(not is_paused)
        button.style = discord.ButtonStyle.success if not is_paused else discord.ButtonStyle.secondary
        
        embed = create_now_playing_embed(state)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji=EMOJIS["next"], style=discord.ButtonStyle.secondary, row=0, custom_id="music_ctrl_skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel.id != player.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to control playback.", ephemeral=True)
            return
            
        if not player.current:
            await interaction.response.send_message("Nothing is playing to skip.", ephemeral=True)
            return
            
        await player.skip(force=True)
        await interaction.response.send_message("Skipped current song.", ephemeral=True)

    # Row 1
    @discord.ui.button(emoji=EMOJIS["mute"], style=discord.ButtonStyle.secondary, row=1, custom_id="music_ctrl_mute")
    async def mute_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel.id != player.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to control playback.", ephemeral=True)
            return
            
        if state.pre_mute_volume is None:
            state.pre_mute_volume = player.volume
            await player.set_volume(0)
            button.style = discord.ButtonStyle.danger
            await interaction.response.send_message("Muted playback volume.", ephemeral=True)
        else:
            await player.set_volume(state.pre_mute_volume)
            state.pre_mute_volume = None
            button.style = discord.ButtonStyle.secondary
            await interaction.response.send_message("Unmuted playback volume.", ephemeral=True)
            
        embed = create_now_playing_embed(state)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(emoji=EMOJIS["vol_down"], style=discord.ButtonStyle.secondary, row=1, custom_id="music_ctrl_vol_down")
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel.id != player.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to control playback.", ephemeral=True)
            return
            
        new_vol = max(0, player.volume - 10)
        await player.set_volume(new_vol)
        await interaction.response.send_message(f"Volume reduced to **{new_vol}%**", ephemeral=True)
        
        embed = create_now_playing_embed(state)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(emoji=EMOJIS["vol_up"], style=discord.ButtonStyle.secondary, row=1, custom_id="music_ctrl_vol_up")
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel.id != player.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to control playback.", ephemeral=True)
            return
            
        new_vol = min(100, player.volume + 10)
        await player.set_volume(new_vol)
        await interaction.response.send_message(f"Volume increased to **{new_vol}%**", ephemeral=True)
        
        embed = create_now_playing_embed(state)
        await interaction.message.edit(embed=embed, view=self)

    # Row 2
    @discord.ui.button(emoji=EMOJIS["queue"], style=discord.ButtonStyle.secondary, row=2, custom_id="music_ctrl_queue")
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        embed = discord.Embed(title="Current Music Queue", color=0xe74709)
        
        if player and player.current:
            embed.description = f"**Now Playing:** [{player.current.title}]({player.current.uri})\n\n"
        else:
            embed.description = "Nothing is currently playing.\n\n"
            
        if player and player.queue:
            upcoming_list = []
            for idx, track in enumerate(player.queue[:10], 1):
                upcoming_list.append(f"`{idx}.` **{track.title}**")
            if len(player.queue) > 10:
                upcoming_list.append(f"*...and {len(player.queue) - 10} more songs*")
            embed.add_field(name="Upcoming Queue:", value="\n".join(upcoming_list), inline=False)
        else:
            embed.add_field(name="Upcoming Queue:", value="Queue is empty.", inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji=EMOJIS["save_fav"], style=discord.ButtonStyle.secondary, row=2, custom_id="music_ctrl_save_fav")
    async def save_fav(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        if not player or not player.current:
            await interaction.response.send_message("Nothing is currently playing to save.", ephemeral=True)
            return
            
        user_id = interaction.user.id
        os.makedirs("favorites", exist_ok=True)
        fav_file = f"favorites/{user_id}.json"
        fav_list = []
        if os.path.exists(fav_file):
            try:
                with open(fav_file, "r", encoding="utf-8") as f:
                    fav_list = json.load(f)
            except Exception:
                pass
                
        if any(item.get('uri') == player.current.uri for item in fav_list):
            await interaction.response.send_message(f"**{player.current.title}** is already in your favorites!", ephemeral=True)
            return
            
        fav_list.append({
            'title': player.current.title,
            'uri': player.current.uri,
            'author': player.current.author,
            'saved_at': time.time()
        })
        with open(fav_file, "w", encoding="utf-8") as f:
            json.dump(fav_list, f, indent=4, ensure_ascii=False)
            
        await interaction.response.send_message(f"⭐ Saved **{player.current.title}** to your favorites!", ephemeral=True)

    @discord.ui.button(emoji=EMOJIS["nonstop"], style=discord.ButtonStyle.secondary, row=2, custom_id="music_ctrl_nonstop")
    async def nonstop_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        state.nonstop = not state.nonstop
        status = "enabled" if state.nonstop else "disabled"
        button.style = discord.ButtonStyle.success if state.nonstop else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"24/7 mode is now **{status}**.", ephemeral=True)

    # Row 3
    @discord.ui.button(emoji=EMOJIS["loop"], style=discord.ButtonStyle.secondary, row=3, custom_id="music_ctrl_loop")
    async def loop_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel.id != player.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to control playback.", ephemeral=True)
            return
            
        if player.queue.mode == wavelink.QueueMode.loop:
            player.queue.mode = wavelink.QueueMode.normal
            button.style = discord.ButtonStyle.secondary
            await interaction.response.send_message("Loop mode: **Disabled**.", ephemeral=True)
        else:
            player.queue.mode = wavelink.QueueMode.loop
            button.style = discord.ButtonStyle.success
            await interaction.response.send_message("Loop mode: **Looping current track**.", ephemeral=True)
            
        embed = create_now_playing_embed(state)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(emoji=EMOJIS["stop"], style=discord.ButtonStyle.danger, row=3, custom_id="music_ctrl_stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        if player:
            await player.disconnect()
            state.voice_client = None
            
        for child in self.children:
            child.disabled = True
            
        embed = discord.Embed(title="Stopped", description="Playback stopped and bot disconnected.", color=0xe74709)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji=EMOJIS["shuffle"], style=discord.ButtonStyle.secondary, row=3, custom_id="music_ctrl_shuffle")
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel.id != player.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to control playback.", ephemeral=True)
            return
            
        if len(player.queue) < 2:
            await interaction.response.send_message("Not enough songs in queue to shuffle.", ephemeral=True)
            return
            
        player.queue.shuffle()
        await interaction.response.send_message("Queue shuffled successfully!", ephemeral=True)


# ----------------- Interactive Dropdown Select Menu for Queue -----------------

class QueueSelect(discord.ui.Select):
    def __init__(self, bot, guild_id, options_list):
        super().__init__(placeholder="Select a track to skip directly to it...", min_values=1, max_values=1, options=options_list)
        self.bot = bot
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        selected_index = int(self.values[0])
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        
        if not interaction.user.voice or (player and interaction.user.voice.channel.id != player.channel.id):
            await interaction.response.send_message("You must be in the same voice channel as the bot to manage the queue.", ephemeral=True)
            return

        if not player or selected_index < 0 or selected_index >= len(player.queue):
            await interaction.response.send_message("This song is no longer in the queue.", ephemeral=True)
            return

        for _ in range(selected_index):
            player.queue.get()
            
        chosen_track = player.queue.get()
        player.queue.put_at_front(chosen_track)
        await player.skip(force=True)
            
        await interaction.response.send_message(f"Skipping directly to: **{chosen_track.title}**", ephemeral=True)


class QueueSelectView(discord.ui.View):
    def __init__(self, bot, guild_id, queue_list):
        super().__init__(timeout=60.0)
        options = []
        for idx, track in enumerate(queue_list[:25]):
            options.append(discord.SelectOption(
                label=track.title[:100],
                description=f"Duration: {int(track.length // 1000)}s",
                value=str(idx)
            ))
        if options:
            self.add_item(QueueSelect(bot, guild_id, options))


# ----------------- Music Commands Cog -----------------

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        if not player or not getattr(player, 'guild', None):
            return
        track = payload.track
        
        state = get_guild_state(player.guild.id, self.bot)
        if state:
            # Delete old controller message to prevent chat clutter
            if state.last_controller_message:
                try:
                    await state.last_controller_message.delete()
                except Exception:
                    pass
                state.last_controller_message = None
                
            embed = create_now_playing_embed(state)
            view = MusicControlView(self.bot, player.guild.id)
            state.last_controller_message = await state.send_message_with_view(embed, view)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if not player or not getattr(player, 'guild', None):
            return
        track = payload.track
        reason = payload.reason
        
        state = get_guild_state(player.guild.id, self.bot)
        if state:
            # Save to previous tracks history
            if reason in ['FINISHED', 'STOPPED']:
                if not state.previous_tracks or state.previous_tracks[-1].uri != track.uri:
                    state.previous_tracks.append(track)
                    if len(state.previous_tracks) > 50:
                        state.previous_tracks.pop(0)
                        
            # If finished Normally or stopped (skipped) and queue is empty, trigger artist autoplay
            if reason in ['FINISHED', 'STOPPED'] and not player.queue and state.autoplay_enabled:
                if state.voice_client:
                    async def play_later():
                        await asyncio.sleep(0.5)
                        if state.voice_client and not state.voice_client.current:
                            await state.play_autoplay()
                    asyncio.create_task(play_later())

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

        if not state.voice_client:
            if ctx.guild.voice_client:
                state.voice_client = ctx.guild.voice_client
            else:
                try:
                    state.voice_client = await channel.connect(cls=wavelink.Player)
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
                    await ctx.send(f"Cannot play **{track.title}** as it matches blacklisted keywords.")
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
                await ctx.send(f"Cannot play next **{track.title}** as it matches blacklisted keywords.")
                return

            track.extras = {
                'requester': ctx.author.display_name,
                'requester_mention': ctx.author.mention,
                'requester_avatar': ctx.author.display_avatar.url if ctx.author.display_avatar else None,
                'requester_id': ctx.author.id,
                'requested_at': time.time()
            }

            if not state.voice_client:
                if ctx.guild.voice_client:
                    state.voice_client = ctx.guild.voice_client
                else:
                    state.voice_client = await ctx.author.voice.channel.connect(cls=wavelink.Player)

            player = state.voice_client
            if player.current:
                player.queue.put_at_front(track)
                await ctx.send(f"Queued to play next: **{track.title}**")
            else:
                await player.play(track)
                state.write_to_history(track)
                await ctx.send(f"Playing **{track.title}**...")
        except Exception as e:
            await ctx.send(f"Error resolving query: {e}")

    @commands.hybrid_command(name="queue", aliases=["q"], description="Add a song to the end of the queue or view the current queue.")
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
                    await ctx.send(f"Cannot queue **{track.title}** as it matches blacklisted keywords.")
                    return

                track.extras = {
                    'requester': ctx.author.display_name,
                    'requester_mention': ctx.author.mention,
                    'requester_avatar': ctx.author.display_avatar.url if ctx.author.display_avatar else None,
                    'requester_id': ctx.author.id,
                    'requested_at': time.time()
                }

                if not state.voice_client:
                    if ctx.guild.voice_client:
                        state.voice_client = ctx.guild.voice_client
                    else:
                        state.voice_client = await ctx.author.voice.channel.connect(cls=wavelink.Player)
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
            embed = discord.Embed(title="Current Music Queue", color=0xe74709)
            
            if player and player.current:
                embed.description = f"**Now Playing:** [{player.current.title}]({player.current.uri}) (Requested by: {player.current.extras.get('requester', 'Autoplay')})\n\n"
            else:
                embed.description = "Nothing is currently playing.\n\n"

            if player and player.queue:
                upcoming_list = []
                for idx, track in enumerate(player.queue[:10], 1):
                    upcoming_list.append(f"`{idx}.` **{track.title}**")
                
                if len(player.queue) > 10:
                    upcoming_list.append(f"*...and {len(player.queue) - 10} more songs*")
                
                embed.add_field(name="Upcoming Queue:", value="\n".join(upcoming_list), inline=False)
            else:
                embed.add_field(name="Upcoming Queue:", value="Queue is empty. Autoplay will play tracks from the configured artist.", inline=False)

            loop_str = "Looping song" if (player and player.queue.mode == wavelink.QueueMode.loop) else "Off"
            embed.add_field(name="Loop Mode", value=f"`{loop_str}`", inline=True)
            embed.add_field(name="Volume", value=f"`{player.volume if player else 100}%`", inline=True)
            
            if player and player.queue:
                view = QueueSelectView(self.bot, ctx.guild.id, list(player.queue))
                await ctx.send(embed=embed, view=view)
            else:
                await ctx.send(embed=embed)

    @commands.hybrid_command(name="skip", aliases=["s"], description="Skip the currently playing song.")
    async def skip(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player:
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            await ctx.send("You must be in the same voice channel as the bot to skip.", ephemeral=True)
            return

        if not player.current:
            await ctx.send("Nothing is currently playing to skip.", ephemeral=True)
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

    @commands.hybrid_command(name="volume", aliases=["v"], description="Adjust the playback volume (0-100).")
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
    async def loop(self, ctx: commands.Context, mode: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        mode = mode.lower().strip()
        if mode not in ['song', 'off']:
            await ctx.send("Invalid loop mode. Choose either `song` or `off`.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player:
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            await ctx.send("You must be in the same voice channel to change loop mode.", ephemeral=True)
            return

        if mode == 'song':
            player.queue.mode = wavelink.QueueMode.loop
        else:
            player.queue.mode = wavelink.QueueMode.normal
            
        await ctx.send(f"Loop mode updated to: **{mode.capitalize()}**")

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
            await ctx.send("You must be in the same voice channel to shuffle the queue.", ephemeral=True)
            return

        if len(player.queue) < 2:
            await ctx.send("Not enough songs in queue to shuffle.", ephemeral=True)
            return

        player.queue.shuffle()
        await ctx.send("Queue shuffled successfully!")

    @commands.hybrid_command(name="pause", description="Pause playback.")
    async def pause(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player:
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            await ctx.send("You must be in the same voice channel to pause playback.", ephemeral=True)
            return

        if not player.paused:
            await player.pause(True)
            await ctx.send("Paused playback.")
        else:
            await ctx.send("Audio is already paused.", ephemeral=True)

    @commands.hybrid_command(name="resume", description="Resume playback.")
    async def resume(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        if not player:
            await ctx.send("I'm not in a voice channel.", ephemeral=True)
            return

        if not ctx.author.voice or ctx.author.voice.channel != player.channel:
            await ctx.send("You must be in the same voice channel to resume playback.", ephemeral=True)
            return

        if player.paused:
            await player.pause(False)
            await ctx.send("Resumed playback.")
        else:
            await ctx.send("Playback is not currently paused.", ephemeral=True)

    @commands.hybrid_command(name="remove", description="Remove a specific song from the queue by its index.")
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

        removed = player.queue.pop(index - 1)
        await ctx.send(f"Removed from queue: **{removed.title}**")

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
            await ctx.send("You must be in the same voice channel to clear the queue.", ephemeral=True)
            return

        player.queue.clear()
        await ctx.send("Queue cleared.")

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

        await player.disconnect()
        state.voice_client = None
        await ctx.send("Disconnected from voice channel.")

    @commands.hybrid_command(name="setartist", aliases=["sa", "set", "artist"], description="Configure the autoplay artist and update immediately if playing autoplay.")
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
        if player and player.current:
            extras = player.current.extras if hasattr(player.current, 'extras') and player.current.extras else {}
            if extras.get('requester') == 'Autoplay':
                await ctx.send("Updating autoplay playlist and playing the new artist immediately...")
                await state.update_artist_playlist()
                await player.skip(force=True)

async def setup(bot):
    await bot.add_cog(Music(bot))
