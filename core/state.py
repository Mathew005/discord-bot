import discord
import asyncio
import yt_dlp
import os
import time
import json
from datetime import datetime
from core.audio import ytdl, ytdl_format_options, ffmpeg_options, YTDLSource
from core.filters import is_blacklisted

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

def format_views(views):
    if not views:
        return "0"
    try:
        views = int(views)
        if views >= 1_000_000_000:
            return f"{views / 1_000_000_000:.1f}b"
        elif views >= 1_000_000:
            return f"{views / 1_000_000:.1f}m"
        elif views >= 1_000:
            return f"{views / 1_000:.1f}k"
        return str(views)
    except Exception:
        return str(views)

def format_likes(likes):
    if not likes:
        return "0"
    try:
        return f"{int(likes):,}"
    except Exception:
        return str(likes)

def format_upload_date(date_str):
    if not date_str or len(date_str) != 8:
        return "Unknown"
    try:
        dt = datetime.strptime(date_str, "%Y%m%d")
        return f"{dt.month}/{dt.day}/{dt.year}"
    except Exception:
        return date_str

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

def get_progress_bar_str(state):
    track = state.current_track
    if not track:
        return ""
    
    duration = track.get('duration')
    if not duration:
        return "Live Stream"
        
    if state.voice_client and state.voice_client.is_paused():
        elapsed = state.elapsed_offset
    else:
        elapsed = state.elapsed_offset + (time.monotonic() - state.start_time)
    
    elapsed = max(0.0, min(duration, elapsed))
    
    length = 20
    percent = elapsed / duration
    filled_length = int(length * percent)
    
    slider_chars = []
    for i in range(length):
        if i == filled_length:
            slider_chars.append("o")
        else:
            slider_chars.append("-")
    bar = " ".join(slider_chars)
    
    def fmt_time(seconds):
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"
        
    status_emoji = "⏸️" if (state.voice_client and state.voice_client.is_paused()) else "▶️"
    return f"{status_emoji} {fmt_time(elapsed)} - [ {bar} ] - {fmt_time(duration)}"

def create_now_playing_embed(state):
    track = state.current_track
    if not track:
        return discord.Embed(title="Nothing Playing", description="Use /play to start some tunes.", color=discord.Color.red())
    
    duration = track.get('duration')
    if duration:
        m = int(duration // 60)
        s = int(duration % 60)
        duration_str = f"{m:02d}:{s:02d}"
    else:
        duration_str = "Live Stream"

    embed = discord.Embed(color=0x2ecc71) # Bright green side bar
    
    embed.add_field(
        name="Currently Playing:",
        value=f"[{track['title']} - ({duration_str})]({track['url']})",
        inline=False
    )
    
    uploader = track.get('uploader', 'Unknown')
    uploader_url = track.get('uploader_url', track['url'])
    embed.add_field(
        name="By",
        value=f"[{uploader}]({uploader_url})",
        inline=False
    )
    
    likes = format_likes(track.get('like_count'))
    views = format_views(track.get('view_count'))
    
    embed.add_field(name="Likes", value=f"👍 {likes}", inline=True)
    embed.add_field(name="Views", value=f"👁️ {views}", inline=True)
    
    upload_date = format_upload_date(track.get('upload_date'))
    embed.add_field(name="Uploaded", value=f"📅 {upload_date}", inline=False)
    
    req_mention = track.get('requester_mention', 'Autoplay')
    if req_mention == 'Autoplay':
        req_mention = f"Autoplay ({configured_artist})"
    elapsed_str = format_elapsed_time(track.get('requested_at'))
    embed.add_field(name="Requested By:", value=f"{req_mention} {elapsed_str}", inline=False)
    
    progress_str = get_progress_bar_str(state)
    embed.add_field(name="Playback Position", value=progress_str, inline=False)
    
    if state.queue:
        next_song = state.queue[0]
        embed.add_field(name="Next", value=f"`{next_song['title']}`", inline=False)
    else:
        embed.add_field(name="Next", value=f"`Autoplay: {configured_artist} will continue`", inline=False)
        
    thumbnail = track.get('thumbnail')
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
        
    req_name = track.get('requester', 'Autoplay')
    if track.get('requested_at'):
        dt = datetime.fromtimestamp(track['requested_at'])
        time_str = dt.strftime("%I:%M %p")
        footer_text = f"{req_name} • Today at {time_str}"
    else:
        footer_text = req_name
        
    if track.get('requester_avatar'):
        embed.set_footer(text=footer_text, icon_url=track['requester_avatar'])
    else:
        embed.set_footer(text=footer_text)
        
    return embed

# ----------------- Guild State Controller -----------------

class GuildMusicState:
    def __init__(self, guild_id, bot):
        self.guild_id = guild_id
        self.bot = bot
        self.queue = []
        self.loop_mode = 'off'
        self.volume = 0.5
        self.artist_playlist = []
        self.artist_index = 0
        self.current_track = None
        self.voice_client = None
        self.text_channel = None
        
        # UI & Time properties
        self.start_time = 0.0
        self.elapsed_offset = 0.0
        self.progress_task = None
        self.last_controller_message = None
        self.fade_task = None
        self.play_lock = asyncio.Lock()
        self.consecutive_errors = 0

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

    async def fade_volume(self, target_volume, duration=1.5):
        """Linearly interpolates active voice client player volume to create a smooth fade."""
        if self.fade_task:
            self.fade_task.cancel()
            self.fade_task = None
            
        async def fade_coro():
            if not self.voice_client or not self.voice_client.source:
                return
            source = self.voice_client.source
            start_volume = getattr(source, 'volume', self.volume)
            steps = int(duration / 0.1)
            if steps <= 0:
                if hasattr(source, 'volume'):
                    source.volume = target_volume
                return
            diff = target_volume - start_volume
            step_diff = diff / steps
            for _ in range(steps):
                if not self.voice_client or not self.voice_client.source:
                    break
                if hasattr(source, 'volume'):
                    source.volume = max(0.0, min(2.0, source.volume + step_diff))
                await asyncio.sleep(0.1)
            if self.voice_client and self.voice_client.source:
                if hasattr(self.voice_client.source, 'volume'):
                    self.voice_client.source.volume = target_volume

        self.fade_task = self.bot.loop.create_task(fade_coro())
        try:
            await self.fade_task
        except asyncio.CancelledError:
            pass
        finally:
            self.fade_task = None

    def write_to_history(self, track):
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
                
        record = {
            'title': track['title'],
            'url': track['url'],
            'requester': track.get('requester', 'Autoplay'),
            'requester_mention': track.get('requester_mention', 'Autoplay'),
            'requester_id': track.get('requester_id'),
            'requested_at': track.get('requested_at', time.time()),
            'played_at': time.time()
        }
        
        # Prevent logging duplicate consecutive plays
        if not history_list or history_list[0].get('url') != track['url']:
            history_list.insert(0, record)
            
        history_list = history_list[:100]
        
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history_list, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error writing history file: {e}")

    async def update_artist_playlist(self):
        global configured_artist
        print(f"[DEBUG] Fetching autoplay playlist for: {configured_artist}")
        try:
            opts_flat = {**ytdl_format_options, 'extract_flat': True}
            ytdl_flat = yt_dlp.YoutubeDL(opts_flat)
            search_results = await self.bot.loop.run_in_executor(
                None, lambda: ytdl_flat.extract_info(f"ytsearch10:{configured_artist}", download=False)
            )
            
            playlist = []
            if 'entries' in search_results:
                for entry in search_results['entries']:
                    if entry.get('ie_key') == 'Youtube':
                        title = entry.get('title', 'Unknown')
                        url = entry.get('url')
                        is_live = entry.get('is_live') is True or entry.get('duration') is None
                        if not is_live and not is_blacklisted(title, url):
                            playlist.append({
                                'title': title,
                                'url': url,
                                'requester': 'Autoplay',
                                'requester_mention': 'Autoplay',
                                'requester_id': None,
                                'requested_at': time.time(),
                                'thumbnail': entry.get('thumbnail'),
                                'duration': entry.get('duration'),
                                'uploader': entry.get('uploader'),
                                'uploader_url': entry.get('uploader_url'),
                                'like_count': entry.get('like_count'),
                                'view_count': entry.get('view_count'),
                                'upload_date': entry.get('upload_date')
                            })
            self.artist_playlist = playlist
            self.artist_index = 0
            print(f"[DEBUG] Autoplay playlist loaded: {len(self.artist_playlist)} songs.")
        except Exception as e:
            print(f"[DEBUG] Error updating artist playlist: {e}")
            self.artist_playlist = []

    async def update_progress_loop(self):
        while self.voice_client and self.voice_client.is_connected() and self.voice_client.is_playing():
            await asyncio.sleep(10)
            if self.last_controller_message and self.current_track:
                if not self.voice_client.is_playing():
                    break
                embed = create_now_playing_embed(self)
                try:
                    await self.last_controller_message.edit(embed=embed)
                except Exception:
                    pass

    async def play_next(self):
        if self.play_lock.locked():
            print("[DEBUG] play_next is already running, skipping duplicate call.")
            return

        async with self.play_lock:
            if self.voice_client and self.voice_client.is_playing():
                print("[DEBUG] Voice client is already playing, skipping play_next.")
                return

            if self.progress_task:
                self.progress_task.cancel()
                self.progress_task = None
                
            if self.last_controller_message:
                try:
                    await self.last_controller_message.delete()
                except Exception:
                    pass
                self.last_controller_message = None

            if not self.voice_client or not self.voice_client.is_connected():
                print("[DEBUG] Not connected to voice. Stopping play loop.")
                self.current_track = None
                return

            next_track = None

            if self.loop_mode == 'song' and self.current_track:
                next_track = self.current_track
            else:
                if self.loop_mode == 'queue' and self.current_track:
                    self.queue.append(self.current_track)

                while self.queue:
                    track = self.queue.pop(0)
                    if not is_blacklisted(track['title'], track['url']):
                        next_track = track
                        break
                    else:
                        await self.send_message(f"Skipped blacklisted song in queue: **{track['title']}**")

                if not next_track:
                    if not self.artist_playlist:
                        await self.update_artist_playlist()
                    
                    attempts = 0
                    while self.artist_playlist and attempts < len(self.artist_playlist):
                        track = self.artist_playlist[self.artist_index]
                        self.artist_index = (self.artist_index + 1) % len(self.artist_playlist)
                        attempts += 1
                        
                        if not is_blacklisted(track['title'], track['url']):
                            next_track = track
                            break

            if not next_track:
                self.current_track = None
                await self.send_message("Queue and autoplay playlist are empty. Stopping playback.")
                return

            self.current_track = next_track
            self.start_time = time.monotonic()
            self.elapsed_offset = 0.0

            try:
                print(f"[DEBUG] Resolving stream URL for: {next_track['title']}")
                data = await self.bot.loop.run_in_executor(
                    None, lambda: ytdl.extract_info(next_track['url'], download=False)
                )
                
                # Robust extraction of direct format stream URL
                stream_url = data.get('url')
                if not stream_url and 'formats' in data:
                    for fmt in data['formats']:
                        if fmt.get('url'):
                            stream_url = fmt['url']
                            break
                            
                if not stream_url:
                    raise Exception("Could not extract direct audio stream URL from video format telemetry.")
                
                self.current_track['thumbnail'] = data.get('thumbnail')
                self.current_track['duration'] = data.get('duration')
                self.current_track['uploader'] = data.get('uploader')
                self.current_track['uploader_url'] = data.get('uploader_url')
                self.current_track['like_count'] = data.get('like_count')
                self.current_track['view_count'] = data.get('view_count')
                self.current_track['upload_date'] = data.get('upload_date')
                
                import sys
                import imageio_ffmpeg
                player = YTDLSource(discord.FFmpegPCMAudio(stream_url, executable=imageio_ffmpeg.get_ffmpeg_exe(), stderr=sys.stderr, **ffmpeg_options), data=data, volume=0.0)
                
                def after_playing(error):
                    if error:
                        print(f"[DEBUG] Player error: {error}")
                    asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)

                self.voice_client.play(player, after=after_playing)
                
                self.consecutive_errors = 0
                self.write_to_history(self.current_track)
                
                from cogs.music import MusicControlView
                embed = create_now_playing_embed(self)
                self.last_controller_message = await self.send_message_with_view(embed, MusicControlView(self.bot, self.guild_id))
                
                self.progress_task = self.bot.loop.create_task(self.update_progress_loop())
                self.bot.loop.create_task(self.fade_volume(self.volume, duration=1.5))
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                
                err_msg = str(e).lower()
                if (
                    "sign in to confirm you" in err_msg 
                    or "confirm you're not a bot" in err_msg 
                    or "no video formats found" in err_msg 
                    or "requested format is not available" in err_msg
                ):
                    await self.send_message(
                        "⚠️ **YouTube Bot Block / Cookie Error Detected!**\n"
                        "YouTube has blocked playback with a format or bot challenge error. "
                        "Please export a fresh `cookies.txt` file from your burner Google account and ensure it is saved in the bot folder."
                    )
                    self.consecutive_errors = 0
                    self.current_track = None
                    return

                self.consecutive_errors += 1
                await self.send_message(f"Error playing track **{next_track['title']}**: {e}")
                
                if self.consecutive_errors >= 3:
                    await self.send_message("Stopped playback due to 3 consecutive playback errors.")
                    self.consecutive_errors = 0
                    self.current_track = None
                    return
                    
                await asyncio.sleep(2.0)
                asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)

def get_guild_state(guild_id, bot) -> GuildMusicState:
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildMusicState(guild_id, bot)
    return guild_states[guild_id]
