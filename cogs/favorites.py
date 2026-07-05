import discord
from discord.ext import commands
import os
import json
import time
import wavelink
from core.state import get_guild_state, ALLOWED_CHANNEL_ID
from core.config import FAVORITES_DIR, THEME_COLOR
from core.filters import is_blacklisted

class FavoritesSelect(discord.ui.Select):
    def __init__(self, user_id, favorites, bot, start_idx):
        self.user_id = user_id
        self.favorites = favorites
        self.bot = bot
        self.start_idx = start_idx
        
        options = []
        for i, item in enumerate(favorites, start=start_idx + 1):
            options.append(
                discord.SelectOption(
                    label=f"{i}. {item['title'][:50]}",
                    description=f"by {item.get('author', 'Unknown')[:50]}",
                    value=str(i - 1)
                )
            )
        super().__init__(placeholder="Select a song to play...", options=options, custom_id="favorites_select_menu")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the command requester can select songs.", ephemeral=True)
            return

        idx = int(self.values[0])
        track_data = self.favorites[idx]
        guild_id = interaction.guild_id
        state = get_guild_state(guild_id, self.bot)
        
        if not interaction.user.voice:
            await interaction.response.send_message("You must be in a voice channel to play music.", ephemeral=True)
            return
            
        if state.voice_client and interaction.user.voice.channel.id != state.voice_client.channel.id:
            await interaction.response.send_message("You must be in the same voice channel to play music.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        if not state.voice_client:
            try:
                state.voice_client = await interaction.user.voice.channel.connect(cls=wavelink.Player)
            except discord.Forbidden:
                await interaction.followup.send("❌ **Permissions Required:** I don't have permission to connect or speak in your voice channel. Please verify that my role has **Connect** and **Speak** permissions in this channel's settings!", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"Error connecting to voice: {e}", ephemeral=True)
                return
                
        player = state.voice_client
        url = track_data['uri']
        
        if is_blacklisted(track_data['title'], url):
            await interaction.followup.send("⚠️ This song matches your blacklist filters and cannot be played.", ephemeral=True)
            return
            
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
                    await interaction.followup.send(f"Added to queue: **{track.title}**", ephemeral=True)
                else:
                    await player.play(track)
                    state.write_to_history(track)
                    await interaction.followup.send(f"Playing **{track.title}**...", ephemeral=True)
            else:
                await interaction.followup.send("Could not find this track on YouTube.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error playing track: {e}", ephemeral=True)

class FavoritesListView(discord.ui.View):
    def __init__(self, user_id, favorites, bot):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.favorites = favorites
        self.bot = bot
        self.page = 0
        self.per_page = 10
        self.max_pages = (len(favorites) - 1) // self.per_page + 1
        self.update_components()

    def update_components(self):
        self.clear_items()
        
        if self.max_pages > 1:
            prev_btn = discord.ui.Button(label="◀️ Previous", style=discord.ButtonStyle.secondary, disabled=(self.page == 0))
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)
            
            next_btn = discord.ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, disabled=(self.page == self.max_pages - 1))
            next_btn.callback = self.next_page
            self.add_item(next_btn)

        start_idx = self.page * self.per_page
        end_idx = start_idx + self.per_page
        page_favs = self.favorites[start_idx:end_idx]
        
        if page_favs:
            self.add_item(FavoritesSelect(self.user_id, self.favorites, self.bot, start_idx))

    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the command requester can browse pages.", ephemeral=True)
            return
        self.page -= 1
        self.update_components()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the command requester can browse pages.", ephemeral=True)
            return
        self.page += 1
        self.update_components()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def create_embed(self):
        embed = discord.Embed(title="⭐ My Favorite Songs", color=THEME_COLOR)
        start_idx = self.page * self.per_page
        end_idx = start_idx + self.per_page
        page_favs = self.favorites[start_idx:end_idx]
        
        lines = []
        for i, item in enumerate(page_favs, start=start_idx + 1):
            lines.append(f"`{i}.` **[{item['title']}]({item['uri']})** (by {item.get('author', 'Unknown')})")
            
        embed.description = "\n".join(lines) if lines else "No favorites saved yet."
        embed.set_footer(text=f"Page {self.page + 1} of {self.max_pages} ({len(self.favorites)} total)")
        return embed

class Favorites(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="favorites", invoke_without_command=True, description="Manage and play your personal favorite songs.")
    async def favorites(self, ctx: commands.Context):
        await ctx.send("Use `/favorites list`, `/favorites load`, or `/favorites remove <index>`.", ephemeral=True)

    @favorites.command(name="list", description="List all of your personal saved favorite songs with interactive playback dropdowns.")
    async def list_favs(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        fav_file = f"{FAVORITES_DIR}/{ctx.author.id}.json"
        if not os.path.exists(fav_file):
            await ctx.send("You haven't saved any favorites yet! Click the ⭐ button on the Now Playing card to save some.", ephemeral=True)
            return

        try:
            with open(fav_file, "r", encoding="utf-8") as f:
                fav_list = json.load(f)
        except Exception:
            fav_list = []

        if not fav_list:
            await ctx.send("You haven't saved any favorites yet! Click the ⭐ button on the Now Playing card to save some.", ephemeral=True)
            return

        view = FavoritesListView(ctx.author.id, fav_list, self.bot)
        embed = view.create_embed()
        await ctx.send(embed=embed, view=view)

    @favorites.command(name="load", description="Load all of your favorited songs into the active music queue.")
    async def load_favs(self, ctx: commands.Context):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        if not ctx.author.voice:
            await ctx.send("You need to join a voice channel first!", ephemeral=True)
            return

        state = get_guild_state(ctx.guild.id, self.bot)
        state.text_channel = ctx.channel

        fav_file = f"{FAVORITES_DIR}/{ctx.author.id}.json"
        if not os.path.exists(fav_file):
            await ctx.send("You haven't saved any favorites yet!", ephemeral=True)
            return

        try:
            with open(fav_file, "r", encoding="utf-8") as f:
                fav_list = json.load(f)
        except Exception:
            fav_list = []

        if not fav_list:
            await ctx.send("You haven't saved any favorites yet!", ephemeral=True)
            return

        await ctx.defer()

        if not state.voice_client:
            try:
                state.voice_client = await ctx.author.voice.channel.connect(cls=wavelink.Player)
            except discord.Forbidden:
                await ctx.send("❌ **Permissions Required:** I don't have permission to connect or speak in your voice channel.", ephemeral=True)
                return
            except Exception as e:
                await ctx.send(f"Failed to join voice channel: {e}", ephemeral=True)
                return

        player = state.voice_client
        added_count = 0

        for item in fav_list:
            title = item.get('title')
            url = item.get('uri')

            if is_blacklisted(title, url):
                continue

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
            except Exception:
                pass

        if added_count == 0:
            await ctx.send("All songs in your favorites list were skipped because they match blacklist filters or failed to load.")
        else:
            await ctx.send(f"Loaded {added_count} songs from your favorites list into the queue.")

    @favorites.command(name="remove", description="Remove a specific song from your favorites by its list index.")
    @discord.app_commands.describe(index="The 1-based index number of the favorite song to delete.")
    async def remove_fav(self, ctx: commands.Context, index: int):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send("Commands are not allowed in this channel.", ephemeral=True)
            return

        fav_file = f"{FAVORITES_DIR}/{ctx.author.id}.json"
        if not os.path.exists(fav_file):
            await ctx.send("You haven't saved any favorites yet!", ephemeral=True)
            return

        try:
            with open(fav_file, "r", encoding="utf-8") as f:
                fav_list = json.load(f)
        except Exception:
            fav_list = []

        if not fav_list:
            await ctx.send("You haven't saved any favorites yet!", ephemeral=True)
            return

        if index < 1 or index > len(fav_list):
            await ctx.send(f"Invalid index. Specify a number between 1 and {len(fav_list)}.", ephemeral=True)
            return

        removed = fav_list.pop(index - 1)
        try:
            with open(fav_file, "w", encoding="utf-8") as f:
                json.dump(fav_list, f, indent=4, ensure_ascii=False)
            await ctx.send(f"⭐ Removed **{removed['title']}** from your favorites list.")
        except Exception as e:
            await ctx.send(f"Error removing favorite: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Favorites(bot))
