import discord
from discord.ext import commands
import sqlite3
import random
from datetime import datetime
import os

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ['TOKEN']

# ID администраторов (замени на свои Discord ID)
ADMINS = [1482416918957785290]  # Вставь свой Discord ID сюда!

# ========== ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ ==========
conn = sqlite3.connect('economy.db')
c = conn.cursor()

# Создаём все таблицы
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    total_earned INTEGER DEFAULT 0,
    total_spent INTEGER DEFAULT 0,
    join_date TIMESTAMP
)''')

c.execute('''CREATE TABLE IF NOT EXISTS achievements (
    ach_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    description TEXT,
    reward INTEGER
)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_achievements (
    user_id TEXT,
    ach_id INTEGER,
    earned_date TIMESTAMP,
    FOREIGN KEY (ach_id) REFERENCES achievements(ach_id)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS shop_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    description TEXT,
    price INTEGER,
    duration_hours INTEGER DEFAULT 0,
    created_at TIMESTAMP,
    expires_at TIMESTAMP
)''')
conn.commit()

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_balance(user_id):
    c.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if result:
        return result[0]
    else:
        c.execute('INSERT INTO users (user_id, balance, join_date) VALUES (?, 0, datetime("now"))', (user_id,))
        conn.commit()
        return 0

def update_balance(user_id, amount):
    new_balance = get_balance(user_id) + amount
    c.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_balance, user_id))
    conn.commit()
    return new_balance

def add_achievement_to_user(user_id, ach_id, reward):
    c.execute('INSERT INTO user_achievements (user_id, ach_id, earned_date) VALUES (?, ?, datetime("now"))', (user_id, ach_id))
    update_balance(user_id, reward)
    conn.commit()

# ========== СОБЫТИЯ ==========
@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    await bot.change_presence(activity=discord.Game(name="!помощь | Belfast Shop"))

@bot.command(name='помощь', aliases=['commands'])
async def help_command(ctx):
    embed = discord.Embed(title="🤖 ПОМОЩЬ", description="Список команд", color=0xff5555)
    embed.add_field(name="💰 ЭКОНОМИКА", value="`!баланс` `!ежедневный` `!передать` `!топ`", inline=False)
    embed.add_field(name="🏪 МАГАЗИН", value="`!магазин` `!купить <название>` `!кейс`", inline=False)
    embed.add_field(name="🏆 ДОСТИЖЕНИЯ", value="`!достижения` `!достижение <название>`", inline=False)
    
    if ctx.author.id in ADMINS:
        embed.add_field(name="🛠️ АДМИН (только для вас)", value="`!add_achievement` `!add_balance` `!remove_balance` `!add_item` `!remove_item`", inline=False)
    
    await ctx.send(embed=embed)

# ========== КОМАНДЫ ДЛЯ ИГРОКОВ ==========
@bot.command(name='баланс', aliases=['balance', 'bal'])
async def show_balance(ctx, user: discord.User = None):
    if user is None:
        user = ctx.author
    balance = get_balance(str(user.id))
    await ctx.send(f"💰 {user.mention}, ваш баланс: **{balance}** Belfast_coin")

@bot.command(name='ежедневный', aliases=['daily'])
async def daily_bonus(ctx):
    user_id = str(ctx.author.id)
    c.execute('SELECT last_daily FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    today = datetime.now().date().toordinal()
    
    if result and result[0] == today:
        await ctx.send(f"❌ {ctx.author.mention}, вы уже получали бонус сегодня!")
        return
    
    reward = 50
    update_balance(user_id, reward)
    c.execute('UPDATE users SET last_daily = ? WHERE user_id = ?', (today, user_id))
    conn.commit()
    await ctx.send(f"🎁 {ctx.author.mention}, вы получили **{reward}** Belfast_coin!")

@bot.command(name='передать', aliases=['transfer', 'send'])
async def transfer(ctx, user: discord.User, amount: int):
    if amount <= 0:
        await ctx.send("❌ Сумма должна быть больше 0!")
        return
    
    sender_id = str(ctx.author.id)
    receiver_id = str(user.id)
    
    if sender_id == receiver_id:
        await ctx.send("❌ Нельзя передать монеты самому себе!")
        return
    
    sender_balance = get_balance(sender_id)
    if sender_balance < amount:
        await ctx.send(f"❌ Не хватает! У вас {sender_balance} Belfast_coin")
        return
    
    update_balance(sender_id, -amount)
    update_balance(receiver_id, amount)
    await ctx.send(f"✅ {ctx.author.mention} передал {user.mention} **{amount}** Belfast_coin!")

@bot.command(name='топ', aliases=['top', 'leaderboard'])
async def leaderboard(ctx):
    c.execute('SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10')
    top_users = c.fetchall()
    
    if not top_users:
        await ctx.send("📊 Нет данных для топа!")
        return
    
    embed = discord.Embed(title="🏆 ТОП ИГРОКОВ", color=0xffaa77)
    for i, (user_id, balance) in enumerate(top_users, 1):
        try:
            user = await bot.fetch_user(int(user_id))
            name = user.name
        except:
            name = user_id[:8]
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        embed.add_field(name=f"{medal} #{i}", value=f"{name} — {balance} монет", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='магазин', aliases=['shop'])
async def shop(ctx):
    c.execute('SELECT name, description, price FROM shop_items WHERE expires_at > datetime("now") OR duration_hours = 0')
    items = c.fetchall()
    
    if not items:
        await ctx.send("🏪 Магазин пуст!")
        return
    
    embed = discord.Embed(title="🏪 МАГАЗИН", color=0xff5555)
    for item in items:
        embed.add_field(name=f"{item[0]}", value=f"📝 {item[1]}\n💰 {item[2]} монет", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='купить', aliases=['buy'])
async def buy(ctx, *, item_name):
    user_id = str(ctx.author.id)
    c.execute('SELECT price FROM shop_items WHERE name = ? AND (expires_at > datetime("now") OR duration_hours = 0)', (item_name,))
    item = c.fetchone()
    
    if not item:
        await ctx.send(f"❌ Предмет `{item_name}` не найден в магазине!")
        return
    
    price = item[0]
    balance = get_balance(user_id)
    
    if balance < price:
        await ctx.send(f"❌ Не хватает! Нужно {price}, у вас {balance}")
        return
    
    update_balance(user_id, -price)
    await ctx.send(f"✅ Вы купили **{item_name}** за {price} Belfast_coin!")

@bot.command(name='кейс', aliases=['case'])
async def case(ctx):
    user_id = str(ctx.author.id)
    price = 50
    balance = get_balance(user_id)
    
    if balance < price:
        await ctx.send(f"❌ Не хватает! Кейс стоит {price} Belfast_coin")
        return
    
    prizes = [
        ("🥉 Утешительный приз", 10),
        ("🥉 Бронзовая монета", 25),
        ("🥈 Серебряная монета", 50),
        ("🥇 Золотая монета", 100),
        ("💎 Алмазная монета", 250),
        ("👑 Королевский клад", 500)
    ]
    
    prize_name, prize_amount = random.choice(prizes)
    update_balance(user_id, -price + prize_amount)
    
    embed = discord.Embed(title="🎲 ОТКРЫТИЕ КЕЙСА", color=0xffaa77)
    embed.add_field(name="Выпало", value=f"{prize_name} — **{prize_amount}** монет!", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='достижения', aliases=['achievements', 'ачивки'])
async def list_achievements(ctx):
    c.execute('SELECT ach_id, name, description, reward FROM achievements')
    all_ach = c.fetchall()
    
    if not all_ach:
        await ctx.send("🏆 Достижений пока нет!")
        return
    
    user_id = str(ctx.author.id)
    c.execute('SELECT ach_id FROM user_achievements WHERE user_id = ?', (user_id,))
    earned = {row[0] for row in c.fetchall()}
    
    embed = discord.Embed(title="🏆 ДОСТИЖЕНИЯ", color=0xffaa77)
    for ach in all_ach:
        status = "✅" if ach[0] in earned else "❌"
        embed.add_field(name=f"{status} {ach[1]}", value=f"📝 {ach[2]}\n💰 Награда: {ach[3]}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='достижение', aliases=['achievement'])
async def achievement_info(ctx, *, name):
    c.execute('SELECT name, description, reward FROM achievements WHERE name LIKE ?', (f'%{name}%',))
    ach = c.fetchone()
    if not ach:
        await ctx.send(f"❌ Достижение `{name}` не найдено!")
        return
    
    user_id = str(ctx.author.id)
    c.execute('''SELECT 1 FROM user_achievements ua 
                 JOIN achievements a ON ua.ach_id = a.ach_id 
                 WHERE ua.user_id = ? AND a.name = ?''', (user_id, ach[0]))
    earned = c.fetchone() is not None
    
    status = "✅ ПОЛУЧЕНО" if earned else "⏳ НЕ ПОЛУЧЕНО"
    embed = discord.Embed(title=f"🏆 {ach[0]}", color=0xffaa77)
    embed.add_field(name="Описание", value=ach[1], inline=False)
    embed.add_field(name="Награда", value=f"{ach[2]} монет", inline=False)
    embed.add_field(name="Статус", value=status, inline=False)
    await ctx.send(embed=embed)

# ========== АДМИН-КОМАНДЫ (только для ADMINS) ==========
def is_admin():
    async def predicate(ctx):
        return ctx.author.id in ADMINS
    return commands.check(predicate)

@bot.command(name='add_achievement')
@is_admin()
async def add_achievement(ctx, name, reward: int, *, description):
    try:
        c.execute('INSERT INTO achievements (name, description, reward) VALUES (?, ?, ?)', (name, description, reward))
        conn.commit()
        await ctx.send(f"✅ Достижение **{name}** добавлено! Награда: {reward} монет")
    except sqlite3.IntegrityError:
        await ctx.send(f"❌ Достижение **{name}** уже существует!")

@bot.command(name='add_balance')
@is_admin()
async def add_balance(ctx, user: discord.User, amount: int):
    user_id = str(user.id)
    update_balance(user_id, amount)
    await ctx.send(f"✅ {user.mention} добавлено **{amount}** Belfast_coin!")

@bot.command(name='remove_balance')
@is_admin()
async def remove_balance(ctx, user: discord.User, amount: int):
    user_id = str(user.id)
    update_balance(user_id, -amount)
    await ctx.send(f"✅ У {user.mention} снято **{amount}** Belfast_coin!")

@bot.command(name='add_item')
@is_admin()
async def add_item(ctx, name, price: int, duration_hours: int = 0, *, description="Нет описания"):
    expires_at = "NULL"
    if duration_hours > 0:
        expires_at = f"datetime('now', '+{duration_hours} hours')"
    
    c.execute(f'''INSERT INTO shop_items (name, description, price, duration_hours, created_at, expires_at)
                  VALUES (?, ?, ?, ?, datetime('now'), {expires_at})''', (name, description, price, duration_hours))
    conn.commit()
    
    duration_text = f"{duration_hours} часов" if duration_hours > 0 else "навсегда"
    await ctx.send(f"✅ Предмет **{name}** добавлен!\n💰 Цена: {price}\n⏰ {duration_text}\n📝 {description}")

@bot.command(name='remove_item')
@is_admin()
async def remove_item(ctx, *, name):
    c.execute('DELETE FROM shop_items WHERE name = ?', (name,))
    conn.commit()
    await ctx.send(f"✅ Предмет **{name}** удалён из магазина!")

# ========== ЗАПУСК ==========
bot.run(TOKEN)
