import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
import random
from dotenv import load_dotenv

# ---------- ЗАГРУЗКА ТОКЕНА ----------
load_dotenv("token.env")

# ---------- НАСТРОЙКИ ----------
DELETE_DELAY = 20

YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "default_search": "ytsearch",
}

ffmpeg_opts = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# ---------- BOT ----------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
tree = bot.tree

# ---------- СОСТОЯНИЕ ----------
class MusicState:
    def __init__(self):
        self.queue = []
        self.loop = "off"
        self.volume = 0.5
        self.current_msg = None
        self.history = []

guild_states = {}

def get_state(guild_id: int) -> MusicState:
    if guild_id not in guild_states:
        guild_states[guild_id] = MusicState()
    return guild_states[guild_id]

def format_time(sec: int) -> str:
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"

async def send_msg(ctx, text=None, embed=None, delete=True):
    msg = await ctx.send(content=text, embed=embed)
    if delete and DELETE_DELAY:
        await msg.delete(delay=DELETE_DELAY)
    return msg

def get_track(query: str) -> dict:
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(query, download=False)
        if "entries" in info:
            info = info["entries"][0]
    return {
        "title": info.get("title", "Unknown"),
        "duration": format_time(info.get("duration", 0)),
        "thumb": info.get("thumbnail"),
        "stream": info["url"],
    }

# ---------- КНОПКИ УПРАВЛЕНИЯ ----------
class PlayerButtons(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="⏮", style=discord.ButtonStyle.primary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_state(self.ctx.guild.id)
        if state.history:
            track = state.history.pop()
            state.queue.insert(0, track)
            if self.ctx.voice_client.is_playing():
                self.ctx.voice_client.stop()
        await interaction.response.defer()

    @discord.ui.button(label="⏹", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if vc:
            vc.stop()
            state = get_state(self.ctx.guild.id)
            state.queue.clear()
        await interaction.response.send_message("⏹ Остановлено", ephemeral=True)

    @discord.ui.button(label="⏭", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if vc and vc.is_playing():
            vc.stop()
        await interaction.response.defer()

# ---------- ПРОИГРЫВАНИЕ ----------
async def play_next(ctx):
    state = get_state(ctx.guild.id)
    vc = ctx.voice_client
    if not vc or not state.queue:
        if vc:
            await vc.disconnect()
        return
    if state.loop == "track":
        url, trackInfo = state.queue[0]
    else:
        url, trackInfo = state.queue.pop(0)
        state.history.append((url, trackInfo))
        if state.loop == "queue":
            state.queue.append((url, trackInfo))
    source = discord.PCMVolumeTransformer(
        discord.FFmpegPCMAudio(trackInfo["stream"], **ffmpeg_opts),
        volume=state.volume
    )
    vc.play(
        source,
        after=lambda _: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
    )
    embed = discord.Embed(
        title="🎶 Сейчас играет",
        description=f"**{trackInfo['title']}**",
        color=discord.Color.green()
    )
    embed.add_field(name="⏱ Длительность", value=trackInfo["duration"], inline=True)
    embed.set_thumbnail(url=trackInfo["thumb"])
    view = PlayerButtons(ctx)
    if state.current_msg:
        try:
            await state.current_msg.edit(embed=embed, view=view)
        except:
            state.current_msg = await ctx.send(embed=embed, view=view)
    else:
        state.current_msg = await ctx.send(embed=embed, view=view)

# ---------- КОМАНДЫ ----------
@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        return await send_msg(ctx, "❌ Ты не в голосовом канале")
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()
        await send_msg(ctx, "✅ Подключился")

@tree.command(name="join", description="Подключить бота к голосовому каналу")
async def join_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ctx = await bot.get_context(interaction)
    await join(ctx)

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        guild_states.pop(ctx.guild.id, None)
        await ctx.voice_client.disconnect()
        await send_msg(ctx, "👋 Я вышел")

@tree.command(name="leave", description="Отключить бота из голосового канала")
async def leave_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ctx = await bot.get_context(interaction)
    await leave(ctx)

@bot.command()
async def play(ctx, *, query: str):
    if not ctx.author.voice:
        return await send_msg(ctx, "❌ Сначала зайди в голосовой канал")
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()
    state = get_state(ctx.guild.id)
    track = get_track(query)
    state.queue.append((query, track))
    await send_msg(ctx, f"➕ Добавлено: **{track['title']}**")
    if not ctx.voice_client.is_playing():
        await play_next(ctx)

@tree.command(name="play", description="Проиграть трек с YouTube по URL или поиску")
async def play_slash(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    ctx = await bot.get_context(interaction)
    await play(ctx, query=query)

@bot.command()
async def pause(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await send_msg(ctx, "⏸ Пауза")

@tree.command(name="pause", description="Поставить текущий трек на паузу")
async def pause_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ctx = await bot.get_context(interaction)
    await pause(ctx)

@bot.command()
async def resume(ctx):
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await send_msg(ctx, "▶️ Продолжено")

@tree.command(name="resume", description="Продолжить проигрывание трека")
async def resume_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ctx = await bot.get_context(interaction)
    await resume(ctx)

@bot.command()
async def skip(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await send_msg(ctx, "⏭ Пропущено")

@tree.command(name="skip", description="Пропустить текущий трек")
async def skip_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ctx = await bot.get_context(interaction)
    await skip(ctx)

@bot.command()
async def volume(ctx, value: int):
    if value < 0 or value > 100:
        return await send_msg(ctx, "❌ Громкость 0–100")
    state = get_state(ctx.guild.id)
    state.volume = value / 100
    if ctx.voice_client and ctx.voice_client.source:
        ctx.voice_client.source.volume = state.volume
    await send_msg(ctx, f"🔊 Громкость: {value}%")

@tree.command(name="volume", description="Установить громкость (0–100)")
@app_commands.describe(value="Громкость 0–100")
async def volume_slash(interaction: discord.Interaction, value: int):
    await interaction.response.defer()
    ctx = await bot.get_context(interaction)
    await volume(ctx, value=value)

@bot.command()
async def loop(ctx, mode: str):
    if mode not in ("off", "track", "queue"):
        return await send_msg(ctx, "❌ off / track / queue")
    get_state(ctx.guild.id).loop = mode
    await send_msg(ctx, f"🔁 Loop: **{mode}**")

@tree.command(name="loop", description="Установить режим повтора (off, track, queue)")
@app_commands.describe(mode="off / track / queue")
async def loop_slash(interaction: discord.Interaction, mode: str):
    await interaction.response.defer()
    ctx = await bot.get_context(interaction)
    await loop(ctx, mode=mode)

@bot.command()
async def shuffle(ctx):
    state = get_state(ctx.guild.id)
    if len(state.queue) > 1:
        random.shuffle(state.queue)
        await send_msg(ctx, "🔀 Очередь перемешана")
    else:
        await send_msg(ctx, "❌ Недостаточно треков для перемешивания")

@tree.command(name="shuffle", description="Перемешать очередь треков")
async def shuffle_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ctx = await bot.get_context(interaction)
    await shuffle(ctx)

@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(title="🎵 Команды бота", color=discord.Color.blue())
    embed.add_field(name="!join / /join", value="Подключить бота к голосовому каналу", inline=False)
    embed.add_field(name="!leave / /leave", value="Отключить бота из голосового канала", inline=False)
    embed.add_field(name="!play <URL или запрос> / /play", value="Добавить трек в очередь", inline=False)
    embed.add_field(name="!pause / /pause", value="Поставить трек на паузу", inline=False)
    embed.add_field(name="!resume / /resume", value="Продолжить проигрывание трека", inline=False)
    embed.add_field(name="!skip / /skip", value="Пропустить текущий трек", inline=False)
    embed.add_field(name="!volume <0–100> / /volume", value="Установить громкость", inline=False)
    embed.add_field(name="!loop <off/track/queue> / /loop", value="Установить режим повтора", inline=False)
    embed.add_field(name="!shuffle / /shuffle", value="Перемешать очередь треков", inline=False)
    await send_msg(ctx, embed=embed)

@tree.command(name="help", description="Показать список команд")
async def help_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ctx = await bot.get_context(interaction)
    await help_command(ctx)

# ---------- ON READY ----------
@bot.event
async def on_ready():
    print(f"Бот запущен: {bot.user}")
    try:
        await tree.sync()
        print("Слэш-команды синхронизированы")
    except Exception as e:
        print(f"Ошибка синхронизации слэш-команд: {e}")

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("DISCORD_TOKEN не найден! Проверьте файл token.env")

bot.run(token)
