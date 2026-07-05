import discord
import time
import os
import json
import wavelink
from core.state import get_guild_state, create_now_playing_embed
from core.config import EMOJIS, THEME_COLOR, FAVORITES_DIR

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

    @discord.ui.button(emoji=EMOJIS["next"], style=discord.ButtonStyle.secondary, row=0, custom_id="music_ctrl_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel.id != player.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to control playback.", ephemeral=True)
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
            await interaction.response.send_message("Muted playback.", ephemeral=True)
        else:
            await player.set_volume(state.pre_mute_volume)
            state.pre_mute_volume = None
            button.style = discord.ButtonStyle.secondary
            await interaction.response.send_message("Unmuted playback.", ephemeral=True)
            
        await interaction.message.edit(view=self)

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
        
        # Reset mute visual if manual volume is changed
        if state.pre_mute_volume is not None:
            state.pre_mute_volume = None
            self.mute_toggle.style = discord.ButtonStyle.secondary
            
        await interaction.response.send_message(f"Volume decreased to **{new_vol}%**", ephemeral=True)
        await interaction.message.edit(view=self)

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
        
        # Reset mute visual if manual volume is changed
        if state.pre_mute_volume is not None:
            state.pre_mute_volume = None
            self.mute_toggle.style = discord.ButtonStyle.secondary
            
        await interaction.response.send_message(f"Volume increased to **{new_vol}%**", ephemeral=True)
        await interaction.message.edit(view=self)

    # Row 2
    @discord.ui.button(emoji=EMOJIS["queue"], style=discord.ButtonStyle.secondary, row=2, custom_id="music_ctrl_queue")
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id, self.bot)
        player = state.voice_client
        embed = discord.Embed(title="Current Music Queue", color=THEME_COLOR)
        
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
            if state.autoplay_enabled and state.artist_playlist:
                next_song = state.artist_playlist[state.artist_index]
                embed.add_field(name="Upcoming Queue:", value=f"🎶 **Autoplay Next:** [{next_song.title}]({next_song.uri})", inline=False)
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
        os.makedirs(FAVORITES_DIR, exist_ok=True)
        fav_file = f"{FAVORITES_DIR}/{user_id}.json"
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
        player = state.voice_client
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel.id != player.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to control playback.", ephemeral=True)
            return
            
        state.nonstop = not state.nonstop
        button.style = discord.ButtonStyle.success if state.nonstop else discord.ButtonStyle.secondary
        
        status_text = "enabled. Bot will stay in voice channel 24/7." if state.nonstop else "disabled."
        await interaction.response.send_message(f"Nonstop (24/7) mode **{status_text}**", ephemeral=True)
        
        # Force embed update to refresh the nonstop state badge
        embed = create_now_playing_embed(state)
        await interaction.message.edit(embed=embed, view=self)

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
            await interaction.response.send_message("Loop mode: **Off**.", ephemeral=True)
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
        if not player:
            await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel.id != player.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to control playback.", ephemeral=True)
            return
            
        await player.disconnect()
        state.voice_client = None
            
        for child in self.children:
            child.disabled = True
            
        embed = discord.Embed(title="Stopped", description="Playback stopped and bot disconnected.", color=THEME_COLOR)
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
            
        if not player.queue:
            await interaction.response.send_message("Queue is empty, nothing to shuffle.", ephemeral=True)
            return
            
        player.queue.shuffle()
        await interaction.response.send_message("Shuffled the music queue.", ephemeral=True)


# ----------------- Queue Dropdown Selection Components -----------------

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
