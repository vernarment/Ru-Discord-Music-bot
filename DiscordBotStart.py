import discord
import os
from discord.ext import commands
import yt_dlp
import asyncio

# ---------- НАСТРОЙКИ ----------
AUTO_DELETE_AFTER = 20  # секунд (0 = не удалять)

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": True,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# ---------- BOT ----------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- СОСТОЯНИЕ ----------
class GuildMusicState:
    def __init__(self):
        self.queue = []            # [(url, info)]
        self.loop = "off"          # off | track | queue
        self.volume = 0.5

states: dict[int, GuildMusicState] = {}


def get_state(guild_id: int) -> GuildMusicState:
    return states.setdefault(guild_id, GuildMusicState())


def format_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


async def send(ctx, content=None, embed=None):
    msg = await ctx.send(content=content, embed=embed)
    if AUTO_DELETE_AFTER > 0:
        await msg.delete(delay=AUTO_DELETE_AFTER)


# ---------- ПРОИГРЫВАНИЕ ----------
async def play_next(ctx):
    state = get_state(ctx.guild.id)
    vc = ctx.voice_client

    if not vc or not state.queue:
        if vc:
            await vc.disconnect()
        return

    if state.loop == "track":
        url, info = state.queue[0]
    else:
        url, info = state.queue.pop(0)
        if state.loop == "queue":
            state.queue.append((url, info))

    source = discord.PCMVolumeTransformer(
        discord.FFmpegPCMAudio(info["audio_url"], **FFMPEG_OPTIONS),
        volume=state.volume
    )

    vc.play(
        source,
        after=lambda _: asyncio.run_coroutine_threadsafe(
            play_next(ctx), bot.loop
        )
    )

    embed = discord.Embed(
        title="🎶 Сейчас играет",
        description=f"**{info['title']}**",
        color=discord.Color.green()
    )
    embed.add_field(name="⏱ Длительность", value=info["duration"], inline=True)
    embed.set_thumbnail(url=info["thumbnail"])

    await send(ctx, embed=embed)


def extract_info(url: str) -> dict:
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        data = ydl.extract_info(url, download=False)

    return {
        "title": data.get("title", "Unknown"),
        "duration": format_time(data.get("duration", 0)),
        "thumbnail": data.get("thumbnail"),
        "audio_url": data["url"],
    }


# ---------- КОМАНДЫ ----------
@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        return await send(ctx, "❌ Ты не в голосовом канале")

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()
        await send(ctx, "✅ Подключился")


@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        states.pop(ctx.guild.id, None)
        await ctx.voice_client.disconnect()
        await send(ctx, "👋 Я вышел")


@bot.command()
async def play(ctx, url: str):
    if not ctx.author.voice:
        return await send(ctx, "❌ Сначала зайди в голосовой канал")

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    state = get_state(ctx.guild.id)
    info = extract_info(url)
    state.queue.append((url, info))

    await send(ctx, f"➕ Добавлено: **{info['title']}**")

    if not ctx.voice_client.is_playing():
        await play_next(ctx)


@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await send(ctx, "⏸ Пауза")


@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await send(ctx, "▶️ Продолжено")


@bot.command()
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await send(ctx, "⏭ Пропущено")


@bot.command()
async def volume(ctx, value: int):
    if not 0 <= value <= 100:
        return await send(ctx, "❌ Громкость 0–100")

    state = get_state(ctx.guild.id)
    state.volume = value / 100

    if ctx.voice_client and ctx.voice_client.source:
        ctx.voice_client.source.volume = state.volume

    await send(ctx, f"🔊 Громкость: {value}%")


@bot.command()
async def loop(ctx, mode: str):
    if mode not in ("off", "track", "queue"):
        return await send(ctx, "❌ off / track / queue")

    get_state(ctx.guild.id).loop = mode
    await send(ctx, f"🔁 Loop: **{mode}**")


@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}")


bot.run(os.getenv("DISCORD_TOKEN"))
