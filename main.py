import discord
from discord.ext import commands
import os

# Токен берётся из переменных окружения (НЕ ВИДЕН В КОДЕ)
TOKEN = os.environ['e737a3a642cb30549407820ad2b731025d46220dd7322d952283fca7b49b307e']

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')

@bot.command()
async def привет(ctx):
    await ctx.send(f'Привет, {ctx.author.mention}!')

bot.run(e737a3a642cb30549407820ad2b731025d46220dd7322d952283fca7b49b307e)
