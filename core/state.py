import discord
import wavelink
import os
import time
import json
import asyncio
from datetime import datetime

# Config state shared between cogs
from core.config import ALLOWED_CHANNEL_ID, THEME_COLOR, HISTORY_DIR, EMOJIS
ARTIST_FILE = "artist.txt"
guild_states = {}

def load_configured_artist():
    default_artist = "Lofi Girl"
    if os.path.exists(ARTIST_FILE):
        try:
            with open(ARTIST_FILE, "r", encoding="utf-8") as f:
                artist = f.read().strip()
                if artist:
                    return artist
        except Exception as e:
            print(f"Error loading artist.txt: {e}")
    else:
        try:
            with open(ARTIST_FILE, "w", encoding="utf-8") as f:
                f.write(default_artist)
        except Exception as e:
            print(f"Error creating artist.txt: {e}")
    return default_artist

configured_artist = load_configured_artist()

# ----------------- Formatter Helpers -----------------

def format_elapsed_time(requested_at):
    if not requested_at:
        return ""
    elapsed = int(time.time() - requested_at)
    if elapsed < 60:
        return f"({elapsed}s ago)"
    else:
        m = elapsed // 60
        s = elapsed % 60
        if s > 0:
            return f"({m}m {s}s ago)"
        return f"({m}m ago)"

def get_progress_bar_str(player: wavelink.Player):
    track = player.current if player else None
    if not track:
        return ""
    
    duration = track.length // 1000  # length is in milliseconds
    if not duration:
        return "Live Stream"
        
    elapsed = player.position // 1000  # position is in milliseconds
    elapsed = max(0.0, min(duration, elapsed))
    
    length = 16
    percent = elapsed / duration
    filled_length = int(length * percent)
    
    bar = "█" * filled_length + "░" * (length - filled_length)
    
    def fmt_time(seconds):
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"
        
    return f"{fmt_time(elapsed)}  [{bar}]  {fmt_time(duration)}"

def create_now_playing_embed(state):
    player: wavelink.Player = state.voice_client
    track = player.current if player else None
    if not track:
        return discord.Embed(title="Nothing Playing", description="Use /play to start some tunes.", color=discord.Color.red())
    
    duration = track.length // 1000
    if duration > 0:
        m = duration // 60
        s = duration % 60
        duration_str = f"{m:02d}:{s:02d}"
    else:
        duration_str = "Live Stream"

    # Dynamic status badges for the title
    status_parts = []
    
    extras = dict(track.extras) if hasattr(track, 'extras') and track.extras else {}
    req_mention = extras.get('requester_mention', 'Autoplay')
    
    if player.paused:
        status_parts.append("⏸️ PAUSED")
    elif duration == 0:
        status_parts.append("🔴 LIVE")
    elif req_mention == 'Autoplay':
        status_parts.append("🔄 AUTOPLAY")
    else:
        status_parts.append("▶️ PLAYING")
        
    if player.queue.mode == wavelink.QueueMode.loop:
        status_parts.append("🔁 LOOPING SONG")
        
    if state.nonstop:
        status_parts.append("🎛️ 24/7 MODE")
        
    status_str = " | ".join(status_parts)

    embed = discord.Embed(title=status_str, color=THEME_COLOR)
    
    embed.add_field(
        name="Currently Playing:",
        value=f"[{track.title}]({track.uri}) ({duration_str})",
        inline=False
    )
    
    embed.add_field(
        name="By",
        value=f"{track.author}",
        inline=False
    )
    
    extras = dict(track.extras) if hasattr(track, 'extras') and track.extras else {}
    req_mention = extras.get('requester_mention', 'Autoplay')
    if req_mention == 'Autoplay':
        req_mention = f"Autoplay ({configured_artist})"
    elapsed_str = format_elapsed_time(extras.get('requested_at'))
    embed.add_field(name="Requested By:", value=f"{req_mention} {elapsed_str}", inline=False)
    
    progress_str = get_progress_bar_str(player)
    embed.add_field(name="Playback Position", value=progress_str, inline=False)
    
    if player.queue:
        next_song = player.queue[0]
        embed.add_field(name="Next", value=f"[{next_song.title}]({next_song.uri})", inline=False)
    else:
        if state.autoplay_enabled and state.artist_playlist:
            next_song = state.artist_playlist[state.artist_index]
            embed.add_field(name="Next (Autoplay)", value=f"[{next_song.title}]({next_song.uri})", inline=False)
        else:
            embed.add_field(name="Next", value=f"`Autoplay: {configured_artist} will continue`" if state.autoplay_enabled else "`End of queue`", inline=False)
        
    artwork_url = track.artwork
    if not artwork_url and track.uri and ("youtube.com" in track.uri or "youtu.be" in track.uri):
        artwork_url = f"https://img.youtube.com/vi/{track.identifier}/mqdefault.jpg"
        
    if artwork_url:
        embed.set_thumbnail(url=artwork_url)
        
    req_name = extras.get('requester', 'Autoplay')
    if extras.get('requested_at'):
        dt = datetime.fromtimestamp(extras.get('requested_at'))
        time_str = dt.strftime("%I:%M %p")
        footer_text = f"{req_name} • Today at {time_str}"
    else:
        footer_text = req_name
        
    if extras.get('requester_avatar'):
        embed.set_footer(text=footer_text, icon_url=extras.get('requester_avatar'))
    else:
        embed.set_footer(text=footer_text)
        
    return embed

# ----------------- Guild State Controller -----------------

class GuildMusicState:
    def __init__(self, guild_id, bot):
        self.guild_id = guild_id
        self.bot = bot
        self.voice_client = None  # Holds the wavelink.Player instance when connected
        self.text_channel = None
        self.last_controller_message = None
        self.previous_tracks = []
        self.pre_mute_volume = None
        self.nonstop = False
        self.autoplay_enabled = True
        self.artist_playlist = []
        self.artist_index = 0
        self.update_task = None
        self.alone_since = None
        self.idle_since = None

    def start_progress_loop(self):
        self.stop_progress_loop()
        
        async def loop():
            while self.voice_client and self.voice_client.current:
                await asyncio.sleep(10)
                if self.voice_client and self.voice_client.current and not self.voice_client.paused:
                    if self.last_controller_message:
                        try:
                            embed = create_now_playing_embed(self)
                            await self.last_controller_message.edit(embed=embed)
                        except Exception:
                            pass
        
        self.update_task = self.bot.loop.create_task(loop())

    def stop_progress_loop(self):
        if self.update_task and not self.update_task.done():
            self.update_task.cancel()
        self.update_task = None

    async def send_message(self, content):
        if not self.text_channel:
            try:
                self.text_channel = self.bot.get_channel(ALLOWED_CHANNEL_ID) or await self.bot.fetch_channel(ALLOWED_CHANNEL_ID)
            except Exception:
                pass
        if self.text_channel:
            try:
                await self.text_channel.send(content)
            except Exception as e:
                print(f"Error sending message: {e}")

    async def send_message_with_view(self, embed, view):
        if not self.text_channel:
            try:
                self.text_channel = self.bot.get_channel(ALLOWED_CHANNEL_ID) or await self.bot.fetch_channel(ALLOWED_CHANNEL_ID)
            except Exception:
                pass
        if self.text_channel:
            try:
                return await self.text_channel.send(embed=embed, view=view)
            except Exception as e:
                print(f"Error sending message: {e}")
        return None

    def write_to_history(self, track: wavelink.Playable):
        """Append the track details to a local JSON file representing the server playback history."""
        os.makedirs(HISTORY_DIR, exist_ok=True)
        history_file = f"{HISTORY_DIR}/{self.guild_id}.json"
        
        history_list = []
        if os.path.exists(history_file):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    history_list = json.load(f)
            except Exception as e:
                print(f"Error reading history file: {e}")
                
        extras = dict(track.extras) if hasattr(track, 'extras') and track.extras else {}
        record = {
            'title': track.title,
            'url': track.uri,
            'requester': extras.get('requester', 'Autoplay'),
            'requester_mention': extras.get('requester_mention', 'Autoplay'),
            'requester_id': extras.get('requester_id'),
            'requested_at': extras.get('requested_at', time.time()),
            'played_at': time.time()
        }
        
        # Prevent logging duplicate consecutive plays
        if not history_list or history_list[0].get('url') != track.uri:
            history_list.insert(0, record)
            
        history_list = history_list[:100]
        
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history_list, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error writing history file: {e}")

    async def update_artist_playlist(self):
        global configured_artist
        print(f"[DEBUG] Fetching autoplay playlist via Wavelink for: {configured_artist}")
        try:
            tracks = await wavelink.Playable.search(f"ytsearch10:{configured_artist}")
            if tracks:
                for track in tracks:
                    track.extras = {
                        'requester': 'Autoplay',
                        'requester_mention': 'Autoplay',
                        'requested_at': time.time()
                    }
                self.artist_playlist = list(tracks)
                self.artist_index = 0
                print(f"[DEBUG] Autoplay playlist loaded: {len(self.artist_playlist)} songs.")
            else:
                self.artist_playlist = []
        except Exception as e:
            print(f"[DEBUG] Error updating artist playlist: {e}")
            self.artist_playlist = []

    async def play_autoplay(self):
        if not self.voice_client:
            return
            
        if not self.artist_playlist:
            await self.update_artist_playlist()
            
        # Fallback if autoplay query resolved to an empty playlist
        if not self.artist_playlist:
            default_artist = load_configured_artist()
            # If the saved artist is the one that just failed, or is a temporary radio stream, fallback to Lofi Girl
            if default_artist.lower() == configured_artist.lower() or "radio" in default_artist.lower():
                default_artist = "Lofi Girl"
                
            print(f"[DEBUG] Autoplay returned empty. Falling back to stream: {default_artist}")
            await self.change_artist(default_artist)
            
        if self.artist_playlist:
            track = self.artist_playlist[self.artist_index]
            self.artist_index = (self.artist_index + 1) % len(self.artist_playlist)
            await self.voice_client.play(track)
            self.write_to_history(track)

    async def change_artist(self, new_artist: str):
        global configured_artist
        configured_artist = new_artist
        
        # Persist artist selection
        try:
            with open(ARTIST_FILE, "w", encoding="utf-8") as f:
                f.write(new_artist)
        except Exception as e:
            print(f"Error saving artist.txt: {e}")
            
        # Clear existing playlist so it is forced to reload
        self.artist_playlist = []
        self.artist_index = 0
        
        # Fetch the new playlist immediately
        await self.update_artist_playlist()
        
        # Update the currently active controller message embed if there is one
        await self.update_controller()

    async def update_controller(self):
        if self.last_controller_message and self.voice_client and self.voice_client.current:
            try:
                embed = create_now_playing_embed(self)
                await self.last_controller_message.edit(embed=embed)
            except Exception:
                pass

    async def handle_disconnect(self):
        # 1. Clean up active controller message
        if self.last_controller_message:
            if self.nonstop:
                try:
                    await self.last_controller_message.delete()
                except Exception:
                    pass
            else:
                try:
                    player = self.voice_client
                    if player and player.current:
                        small_embed = discord.Embed(
                            description=f"Played: **[{player.current.title}]({player.current.uri})**",
                            color=THEME_COLOR
                        )
                        extras = dict(player.current.extras) if hasattr(player.current, 'extras') and player.current.extras else {}
                        req_name = extras.get('requester', 'Autoplay')
                        if extras.get('requester_avatar'):
                            small_embed.set_footer(text=f"Requested by {req_name}", icon_url=extras.get('requester_avatar'))
                        else:
                            small_embed.set_footer(text=f"Requested by {req_name}")
                        await self.last_controller_message.edit(embed=small_embed, view=None)
                    else:
                        await self.last_controller_message.delete()
                except Exception:
                    pass
            self.last_controller_message = None

        # 2. Stop progress loop
        self.stop_progress_loop()

        # 3. Clear voice client state and reset defaults
        self.voice_client = None
        self.nonstop = False
        self.autoplay_enabled = True

def get_guild_state(guild_id, bot) -> GuildMusicState:
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildMusicState(guild_id, bot)
    return guild_states[guild_id]
