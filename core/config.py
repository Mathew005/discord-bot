import discord
import os

# Allowed Channel for Bot Commands
ALLOWED_CHANNEL_ID = int(os.getenv("ALLOWED_CHANNEL_ID", "1523024900602724513"))

# Embed Customizations
THEME_COLOR = 0xe74709

# Directory Paths
PLAYLIST_DIR = "playlists"
HISTORY_DIR = "history"
FAVORITES_DIR = "favorites"

# EMOJIS definitions from WebP image links
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

# Public Lavalink Nodes Pool (Checked and active)
DEFAULT_LAVALINK_NODES = [
    {
        "uri": "http://lavalink.jirayu.net:13592",
        "password": "youshallnotpass"
    }
]
