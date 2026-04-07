import discord
from discord.ext import commands
import os

TOKEN = os.environ['TOKEN']   # Токен берётся из Railway, НЕ ИЗ КОДА

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')

@bot.command()
async def привет(ctx):
    await ctx.send(f'Привет, {ctx.author.mention}!')

bot.run(TOKEN)
