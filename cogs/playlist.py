import discord
from discord.ext import commands
import os
import json
import time
import wavelink
from core.state import get_guild_state, ALLOWED_CHANNEL_ID
from core.filters import is_blacklisted

class Playlist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="playlist", invoke_without_command=True, description="Manage custom local server playlists.")
    async def playlist(self, ctx: commands.Context):
        await ctx.send("Use `/playlist save`, `/playlist load`, `/playlist list`, or `/playlist delete`.", ephemeral=True)

    @playlist.command(name="save", description="Save the currently playing song and queue as a new playlist.")
    async def save(self, ctx: commands.Context, name: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        player = state.voice_client
        
        if not player or (not player.current and not player.queue):
            await ctx.send("There is no music playing or queued to save.", ephemeral=True)
            return

        os.makedirs("playlists", exist_ok=True)
        guild_dir = f"playlists/{ctx.guild.id}"
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
    async def load(self, ctx: commands.Context, name: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        if not ctx.author.voice:
            await ctx.send("You need to join a voice channel first!", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        state.text_channel = ctx.channel

        guild_dir = f"playlists/{ctx.guild.id}"
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
                    player = state.voice_client
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

        guild_dir = f"playlists/{ctx.guild.id}"
        if not os.path.exists(guild_dir) or not os.listdir(guild_dir):
            await ctx.send("No playlists have been saved on this server yet.", ephemeral=True)
            return

        files = [f for f in os.listdir(guild_dir) if f.endswith(".json")]
        if not files:
            await ctx.send("No playlists have been saved on this server yet.", ephemeral=True)
            return

        embed = discord.Embed(title="Saved Server Playlists", color=discord.Color.blurple())
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
        await ctx.send(embed=embed)

    @playlist.command(name="delete", description="Delete a saved server playlist.")
    async def delete(self, ctx: commands.Context, name: str):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        guild_dir = f"playlists/{ctx.guild.id}"
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
