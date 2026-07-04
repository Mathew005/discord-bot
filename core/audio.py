import discord
import yt_dlp
import asyncio

import os

# yt-dlp config
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch1',
    'js_runtimes': {'node': {}, 'deno': {}},
}

if os.path.exists("cookies.txt"):
    ytdl_format_options['cookiefile'] = 'cookies.txt'

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title', 'Unknown')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        print(f"[DEBUG] Extracting info for: {url}")
        loop = loop or asyncio.get_event_loop()
        
        # If it's a search query (not a direct URL), do a flat search first to avoid recursive channel/playlist resolution
        if not url.startswith('http'):
            print(f"[DEBUG] Query is a search term. Doing flat search first...")
            opts_flat = {**ytdl_format_options, 'extract_flat': True}
            ytdl_flat = yt_dlp.YoutubeDL(opts_flat)
            search_results = await loop.run_in_executor(
                None, lambda: ytdl_flat.extract_info(f"ytsearch5:{url}", download=False)
            )
            
            video_url = None
            if 'entries' in search_results:
                for entry in search_results['entries']:
                    if entry.get('ie_key') == 'Youtube':
                        video_url = entry.get('url')
                        break
            
            if not video_url:
                raise Exception("No video found in search results.")
            url = video_url
            print(f"[DEBUG] Resolved search query to video URL: {url}")

        # Now extract the actual playable stream url
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            if not data['entries']:
                raise Exception("No entries found.")
            data = data['entries'][0]

        print(f"[DEBUG] Successfully extracted. Title: {data.get('title')}")
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        
        # Extract User-Agent for FFmpeg connection validation
        user_agent = data.get('http_headers', {}).get('User-Agent')
        before_opts = ffmpeg_options.get('before_options', '')
        if user_agent:
            before_opts += f' -user_agent "{user_agent}"'
            
        custom_ffmpeg_options = {**ffmpeg_options, 'before_options': before_opts}
        
        import sys
        return cls(discord.FFmpegPCMAudio(filename, stderr=sys.stderr, **custom_ffmpeg_options), data=data)
