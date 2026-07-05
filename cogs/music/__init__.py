from .main_cog import Music
from .settings_cog import MusicSettings
from .events_cog import MusicEvents

async def setup(bot):
    await bot.add_cog(Music(bot))
    await bot.add_cog(MusicSettings(bot))
    await bot.add_cog(MusicEvents(bot))
