import discord
from discord.ext import commands
import os
import json
import time
import wavelink
from core.state import get_guild_state, ALLOWED_CHANNEL_ID
from core.filters import is_blacklisted
from core.config import PLAYLIST_DIR, THEME_COLOR

class PlaylistSelect(discord.ui.Select):
    def __init__(self, playlists, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label=name, description=f"Load playlist '{name}'", value=name)
            for name in playlists[:25]
        ]
        super().__init__(placeholder="Select a playlist to load...", options=options, custom_id="playlist_select_menu")

    async def callback(self, interaction: discord.Interaction):
        playlist_name = self.values[0]
        guild_id = interaction.guild_id
        state = get_guild_state(guild_id, self.bot)
        
        if not interaction.user.voice:
            await interaction.response.send_message("You must be in a voice channel to load a playlist.", ephemeral=True)
            return
            
        if state.voice_client and interaction.user.voice.channel.id != state.voice_client.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to load a playlist.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        if not state.voice_client:
            try:
                state.voice_client = await interaction.user.voice.channel.connect(cls=wavelink.Player)
                state.text_channel = interaction.channel
            except discord.Forbidden:
                await interaction.followup.send("❌ **Permissions Required:** I don't have permission to connect or speak in your voice channel. Please verify that my role has **Connect** and **Speak** permissions in this channel's settings!", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"Error connecting to voice: {e}", ephemeral=True)
                return
                
        player = state.voice_client
        guild_dir = f"{PLAYLIST_DIR}/{guild_id}"
        filepath = f"{guild_dir}/{playlist_name}.json"
        
        if not os.path.exists(filepath):
            await interaction.followup.send(f"Playlist **{playlist_name}** does not exist.", ephemeral=True)
            return
            
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                tracks_data = json.load(f)
        except Exception as e:
            await interaction.followup.send(f"Error reading playlist file: {e}", ephemeral=True)
            return
            
        if not tracks_data:
            await interaction.followup.send("Playlist is empty.", ephemeral=True)
            return
            
        added_count = 0
        from core.filters import is_blacklisted
        
        for item in tracks_data:
            title = item.get('title')
            url = item.get('url')
            
            if is_blacklisted(title, url):
                continue
                
            try:
                tracks = await wavelink.Playable.search(url)
                if tracks:
                    track = tracks[0]
                    track.extras = {
                        'requester': interaction.user.display_name,
                        'requester_mention': interaction.user.mention,
                        'requester_avatar': interaction.user.display_avatar.url if interaction.user.display_avatar else None,
                        'requester_id': interaction.user.id,
                        'requested_at': time.time()
                    }
                    if player.current:
                        player.queue.put(track)
                    else:
                        await player.play(track)
                        state.write_to_history(track)
                    added_count += 1
            except Exception:
                pass
                
        if added_count == 0:
            await interaction.followup.send("All songs in the playlist were skipped because they match your blacklist filters.", ephemeral=True)
        else:
            await interaction.followup.send(f"Loaded {added_count} songs from playlist **{playlist_name}** into the queue.", ephemeral=True)

class PlaylistListView(discord.ui.View):
    def __init__(self, playlists, bot):
        super().__init__(timeout=180)
        self.add_item(PlaylistSelect(playlists, bot))

class Playlist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Autocomplete for playlist name argument
    async def playlist_name_autocomplete(self, interaction: discord.Interaction, current: str):
        guild_id = interaction.guild_id
        if not guild_id:
            return []
        guild_dir = f"{PLAYLIST_DIR}/{guild_id}"
        if not os.path.exists(guild_dir):
            return []
        playlists = [f[:-5] for f in os.listdir(guild_dir) if f.endswith(".json")]
        choices = [
            discord.app_commands.Choice(name=name, value=name)
            for name in playlists if current.lower() in name.lower()
        ]
        return choices[:25]

    @commands.hybrid_group(name="playlist", invoke_without_command=True, description="Manage custom local server playlists.")
    async def playlist(self, ctx: commands.Context):
        await ctx.send("Use `/playlist save`, `/playlist load`, `/playlist list`, or `/playlist delete`.", ephemeral=True)

    @playlist.command(name="save", description="Save the currently playing song and queue as a new playlist.")
    @discord.app_commands.describe(name="The name of the new playlist to save.")
    async def save(self, ctx: commands.Context, name: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        
        if not player or (not player.current and not player.queue):
            await ctx.send("There is no music playing or queued to save.", ephemeral=True)
            return

        os.makedirs(PLAYLIST_DIR, exist_ok=True)
        guild_dir = f"{PLAYLIST_DIR}/{ctx.guild.id}"
        os.makedirs(guild_dir, exist_ok=True)
        
        safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
        if not safe_name:
            await ctx.send("Invalid playlist name. Use alphanumeric characters only.", ephemeral=True)
            return

        playlist_tracks = []
        if player.current:
            playlist_tracks.append({
                'title': player.current.title,
                'url': player.current.uri
            })
        for track in player.queue:
            playlist_tracks.append({
                'title': track.title,
                'url': track.uri
            })

        filepath = f"{guild_dir}/{safe_name}.json"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(playlist_tracks, f, indent=4, ensure_ascii=False)
            await ctx.send(f"Playlist **{safe_name}** successfully saved with {len(playlist_tracks)} songs!")
        except Exception as e:
            await ctx.send(f"Error saving playlist: {e}", ephemeral=True)

    @playlist.command(name="load", description="Load a saved playlist and append it to the queue.")
    @discord.app_commands.describe(name="The name of the playlist to load.")
    @discord.app_commands.autocomplete(name=playlist_name_autocomplete)
    async def load(self, ctx: commands.Context, name: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        if not ctx.author.voice:
            await ctx.send("You need to join a voice channel first!", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        state.text_channel = ctx.channel

        guild_dir = f"{PLAYLIST_DIR}/{ctx.guild.id}"
        safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
        filepath = f"{guild_dir}/{safe_name}.json"

        if not os.path.exists(filepath):
            await ctx.send(f"Playlist **{safe_name}** does not exist.", ephemeral=True)
            return

        await ctx.defer()
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                loaded_tracks = json.load(f)
        except Exception as e:
            await ctx.send(f"Error reading playlist file: {e}", ephemeral=True)
            return

        if not loaded_tracks:
            await ctx.send(f"Playlist **{safe_name}** is empty.", ephemeral=True)
            return

        channel = ctx.author.voice.channel
        player = state.voice_client
        if not player:
            if ctx.guild.voice_client:
                state.voice_client = ctx.guild.voice_client
                player = state.voice_client
            else:
                try:
                    state.voice_client = await channel.connect(cls=wavelink.Player)
                    state.text_channel = ctx.channel
                    player = state.voice_client
                except discord.Forbidden:
                    await ctx.send("❌ **Permissions Required:** I don't have permission to connect or speak in your voice channel. Please verify that my role has **Connect** and **Speak** permissions in this channel's settings!", ephemeral=True)
                    return
                except Exception as e:
                    await ctx.send(f"Failed to join voice channel: {e}")
                    return
        elif player.channel != channel:
            await player.move_to(channel)

        added_count = 0
        for track_data in loaded_tracks:
            title = track_data.get('title', 'Unknown')
            url = track_data.get('url')
            if url and not is_blacklisted(title, url):
                try:
                    tracks = await wavelink.Playable.search(url)
                    if tracks:
                        track = tracks[0]
                        track.extras = {
                            'requester': ctx.author.display_name,
                            'requester_mention': ctx.author.mention,
                            'requester_avatar': ctx.author.display_avatar.url if ctx.author.display_avatar else None,
                            'requester_id': ctx.author.id,
                            'requested_at': time.time()
                        }
                        if player.current:
                            player.queue.put(track)
                        else:
                            await player.play(track)
                            state.write_to_history(track)
                        added_count += 1
                except Exception as e:
                    print(f"Error loading track {title} from playlist: {e}")

        if added_count == 0:
            await ctx.send("All songs in the playlist were skipped because they match your blacklist filters.")
            return

        await ctx.send(f"Loaded {added_count} songs from playlist **{safe_name}** into the queue.")

    @playlist.command(name="list", description="List all saved playlists for this server.")
    async def list_playlists(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        guild_dir = f"{PLAYLIST_DIR}/{ctx.guild.id}"
        if not os.path.exists(guild_dir) or not os.listdir(guild_dir):
            await ctx.send("No playlists have been saved on this server yet.", ephemeral=True)
            return

        files = [f for f in os.listdir(guild_dir) if f.endswith(".json")]
        if not files:
            await ctx.send("No playlists have been saved on this server yet.", ephemeral=True)
            return

        embed = discord.Embed(title="Saved Server Playlists", color=THEME_COLOR)
        playlist_names = []
        for file in files:
            name = file[:-5]
            try:
                with open(f"{guild_dir}/{file}", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    count = len(data)
            except Exception:
                count = 0
            playlist_names.append(f"- **{name}** ({count} songs)")

        embed.description = "\n".join(playlist_names)
        playlist_list = [f[:-5] for f in os.listdir(guild_dir) if f.endswith(".json")]
        view = PlaylistListView(playlist_list, self.bot) if playlist_list else None
        await ctx.send(embed=embed, view=view)

    @playlist.command(name="delete", description="Delete a saved server playlist.")
    @discord.app_commands.describe(name="The name of the playlist to delete.")
    @discord.app_commands.autocomplete(name=playlist_name_autocomplete)
    async def delete(self, ctx: commands.Context, name: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        guild_dir = f"{PLAYLIST_DIR}/{ctx.guild.id}"
        safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
        filepath = f"{guild_dir}/{safe_name}.json"

        if not os.path.exists(filepath):
            await ctx.send(f"Playlist **{safe_name}** does not exist.", ephemeral=True)
            return

        try:
            os.remove(filepath)
            await ctx.send(f"Playlist **{safe_name}** successfully deleted.")
        except Exception as e:
            await ctx.send(f"Error deleting playlist: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Playlist(bot))
