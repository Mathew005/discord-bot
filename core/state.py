import discord
import wavelink
import os
import time
import json
from datetime import datetime

# Config state shared between cogs
ALLOWED_CHANNEL_ID = int(os.getenv("ALLOWED_CHANNEL_ID", "1523024900602724513"))
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

    embed = discord.Embed(color=0xe74709)
    
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
        embed.add_field(name="Next", value=f"`{next_song.title}`", inline=False)
    else:
        embed.add_field(name="Next", value=f"`Autoplay: {configured_artist} will continue`" if state.autoplay_enabled else "`End of queue`", inline=False)
        
    if track.artwork:
        embed.set_thumbnail(url=track.artwork)
        
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

    async def send_message(self, content):
        if self.text_channel:
            try:
                await self.text_channel.send(content)
            except Exception as e:
                print(f"Error sending message: {e}")

    async def send_message_with_view(self, embed, view):
        if self.text_channel:
            try:
                return await self.text_channel.send(embed=embed, view=view)
            except Exception as e:
                print(f"Error sending message: {e}")
        return None

    def write_to_history(self, track: wavelink.Playable):
        """Append the track details to a local JSON file representing the server playback history."""
        os.makedirs("history", exist_ok=True)
        history_file = f"history/{self.guild_id}.json"
        
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
            
        if self.artist_playlist:
            track = self.artist_playlist[self.artist_index]
            self.artist_index = (self.artist_index + 1) % len(self.artist_playlist)
            await self.voice_client.play(track)
            self.write_to_history(track)

def get_guild_state(guild_id, bot) -> GuildMusicState:
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildMusicState(guild_id, bot)
    return guild_states[guild_id]
