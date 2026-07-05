import discord
from discord.ext import commands, tasks
import asyncio
import time
import logging
import wavelink
from core.state import get_guild_state, create_now_playing_embed
from core.views import MusicControlView
import core.state as state_module
from core.config import THEME_COLOR

class MusicEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_load(self):
        self.inactivity_check.start()

    def cog_unload(self):
        self.inactivity_check.cancel()

    @tasks.loop(seconds=10)
    async def inactivity_check(self):
        for player in list(self.bot.voice_clients):
            if not isinstance(player, wavelink.Player):
                continue
                
            guild_id = player.guild.id
            state = get_guild_state(guild_id, self.bot)
            if not state:
                continue
                
            # --- Check A: Empty Voice Channel (2-minute countdown) ---
            channel_members = [m for m in player.channel.members if not m.bot]
            if not channel_members:
                if not state.nonstop:
                    if state.alone_since is None:
                        state.alone_since = time.time()
                        logging.info(f"[Inactivity] Bot is alone in voice channel '{player.channel.name}' (Guild: {player.guild.name}). Starting 2-minute countdown.")
                    elif time.time() - state.alone_since >= 120:
                        logging.info(f"[Inactivity] Disconnecting due to empty channel in guild {player.guild.name} (elapsed: 2 minutes).")
                        await state.send_message("Disconnected due to inactivity (everyone left the channel).")
                        try:
                            await player.disconnect()
                        except Exception:
                            pass
                        state.voice_client = None
                        state.stop_progress_loop()
                        state.alone_since = None
                        state.idle_since = None
                else:
                    state.alone_since = None
            else:
                state.alone_since = None
                
            # --- Check B: Idle Player (5-minute countdown) ---
            is_idle = (player.current is None and not player.queue and not state.autoplay_enabled) or player.paused
            if is_idle and not state.nonstop:
                if state.idle_since is None:
                    state.idle_since = time.time()
                    logging.info(f"[Inactivity] Player is idle/paused in guild '{player.guild.name}'. Starting 5-minute countdown.")
                elif time.time() - state.idle_since >= 300:
                    logging.info(f"[Inactivity] Disconnecting due to idle/paused player in guild {player.guild.name} (elapsed: 5 minutes).")
                    await state.send_message("Disconnected due to inactivity (player idle/paused).")
                    try:
                        await player.disconnect()
                    except Exception:
                        pass
                    state.voice_client = None
                    state.stop_progress_loop()
                    state.alone_since = None
                    state.idle_since = None
            else:
                state.idle_since = None

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        if not player or not getattr(player, 'guild', None):
            return
        track = payload.track
        
        state = get_guild_state(player.guild.id, self.bot)
        if state:
            logging.info(f"▶️ Started playing track: '{track.title}' (by {track.author})")
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
            state.start_progress_loop()
            
            # Pre-fetch autoplay playlist if empty
            if state.autoplay_enabled and not state.artist_playlist:
                asyncio.create_task(state.update_artist_playlist())

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if not player or not getattr(player, 'guild', None):
            return
        track = payload.track
        reason = payload.reason
        reason_upper = reason.upper() if reason else ""
        
        state = get_guild_state(player.guild.id, self.bot)
        if state:
            logging.info(f"⏹️ Track ended: '{track.title}' (Reason: {reason})")
            state.stop_progress_loop()
            
            # Edit or delete the last controller message
            if state.last_controller_message:
                if state.nonstop:
                    try:
                        await state.last_controller_message.delete()
                    except Exception:
                        pass
                else:
                    try:
                        small_embed = discord.Embed(
                            description=f"Played: **[{track.title}]({track.uri})**",
                            color=THEME_COLOR
                        )
                        extras = dict(track.extras) if hasattr(track, 'extras') and track.extras else {}
                        req_name = extras.get('requester', 'Autoplay')
                        if extras.get('requester_avatar'):
                            small_embed.set_footer(text=f"Requested by {req_name}", icon_url=extras.get('requester_avatar'))
                        else:
                            small_embed.set_footer(text=f"Requested by {req_name}")
                        await state.last_controller_message.edit(embed=small_embed, view=None)
                    except Exception:
                        pass
                state.last_controller_message = None

            # Save to previous tracks history
            if reason_upper in ['FINISHED', 'STOPPED', 'LOAD_FAILED']:
                if not state.previous_tracks or state.previous_tracks[-1].uri != track.uri:
                    state.previous_tracks.append(track)
                    if len(state.previous_tracks) > 50:
                        state.previous_tracks.pop(0)
                        
            # If finished Normally, stopped (skipped), or failed to load:
            if reason_upper in ['FINISHED', 'STOPPED', 'LOAD_FAILED'] and getattr(player, 'channel', None):
                if player.queue:
                    # Play the next track from the queue
                    try:
                        next_track = player.queue.get()
                        await player.play(next_track)
                        state.write_to_history(next_track)
                    except Exception as e:
                        logging.error(f"Error playing next queued track: {e}")
                elif state.autoplay_enabled:
                    # Queue is empty, trigger artist autoplay
                    if state.voice_client:
                        async def play_later():
                            await asyncio.sleep(0.5)
                            if state.voice_client and getattr(state.voice_client, 'channel', None) and (not state.voice_client.current or state.voice_client.current == track):
                                await state.play_autoplay()
                        asyncio.create_task(play_later())
