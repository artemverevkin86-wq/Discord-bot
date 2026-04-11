import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import random
from datetime import datetime
import os
import asyncio

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ['TOKEN']

# ========== ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ ==========
conn = sqlite3.connect('economy.db')
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    total_earned INTEGER DEFAULT 0,
    total_spent INTEGER DEFAULT 0,
    join_date TIMESTAMP,
    last_daily INTEGER DEFAULT 0,
    daily_streak INTEGER DEFAULT 0
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
    price INTEGER DEFAULT 0,
    duration_hours INTEGER DEFAULT 0,
    created_at TIMESTAMP,
    expires_at TIMESTAMP
)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_items (
    user_id TEXT,
    item_name TEXT,
    quantity INTEGER DEFAULT 1,
    acquired_date TIMESTAMP,
    PRIMARY KEY (user_id, item_name)
)''')
conn.commit()

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_balance(user_id):
    c.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if result:
        return result[0]
    else:
        c.execute('INSERT INTO users (user_id, balance, join_date, last_daily, daily_streak) VALUES (?, 0, datetime("now"), 0, 1)', (user_id,))
        conn.commit()
        return 0

def update_balance(user_id, amount):
    new_balance = get_balance(user_id) + amount
    c.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_balance, user_id))
    conn.commit()
    return new_balance

def check_daily(user_id):
    c.execute('SELECT last_daily, daily_streak FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    today = datetime.now().date().toordinal()
    
    if not result:
        c.execute('INSERT INTO users (user_id, balance, join_date, last_daily, daily_streak) VALUES (?, 0, datetime("now"), ?, 1)', (user_id, today))
        conn.commit()
        return True, 50, 1
    
    last_daily, streak = result
    if last_daily == today:
        return False, 0, streak
    
    if last_daily == today - 1:
        streak += 1
    else:
        streak = 1
    
    reward = 50 + (streak - 1) * 5
    if reward > 150:
        reward = 150
    
    c.execute('UPDATE users SET last_daily = ?, daily_streak = ? WHERE user_id = ?', (today, streak, user_id))
    conn.commit()
    return True, reward, streak

def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

def give_achievement(user_id, ach_name):
    c.execute('SELECT ach_id, reward FROM achievements WHERE name = ?', (ach_name,))
    result = c.fetchone()
    if not result:
        return False, "Достижение не найдено"
    
    ach_id, reward = result
    c.execute('SELECT 1 FROM user_achievements WHERE user_id = ? AND ach_id = ?', (user_id, ach_id))
    if c.fetchone():
        return False, "У игрока уже есть это достижение"
    
    c.execute('INSERT INTO user_achievements (user_id, ach_id, earned_date) VALUES (?, ?, datetime("now"))', (user_id, ach_id))
    update_balance(user_id, reward)
    conn.commit()
    return True, reward

def give_item(user_id, item_name):
    c.execute('SELECT 1 FROM shop_items WHERE name = ?', (item_name,))
    if not c.fetchone():
        return False, "Предмет не найден в магазине"
    
    c.execute('''INSERT INTO user_items (user_id, item_name, quantity, acquired_date) 
                 VALUES (?, ?, 1, datetime("now"))
                 ON CONFLICT(user_id, item_name) DO UPDATE SET quantity = quantity + 1''', (user_id, item_name))
    conn.commit()
    return True, None

# ========== ПАГИНАТОР ДЛЯ МАГАЗИНА ==========
class ShopPaginator(discord.ui.View):
    def __init__(self, items, items_per_page=5):
        super().__init__(timeout=120)
        self.items = items
        self.items_per_page = items_per_page
        self.current_page = 0
        self.total_pages = (len(items) + items_per_page - 1) // items_per_page if items else 1
        self.update_buttons()
    
    def update_buttons(self):
        self.clear_items()
        if self.current_page > 0:
            self.add_item(discord.ui.Button(label="◀ НАЗАД", style=discord.ButtonStyle.secondary, custom_id="prev_page"))
        if self.current_page < self.total_pages - 1:
            self.add_item(discord.ui.Button(label="ВПЕРЕД ▶", style=discord.ButtonStyle.secondary, custom_id="next_page"))
    
    def get_embed(self):
        if not self.items:
            embed = discord.Embed(
                title="🏪 МАГАЗИН",
                description="━━━━━━━━━━━━━━━━━━━━━━\n**Магазин пуст!**",
                color=0xff5555
            )
            return embed
        
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_items = self.items[start:end]
        
        embed = discord.Embed(
            title="🏪 BELFAST SHOP",
            description="━━━━━━━━━━━━━━━━━━━━━━",
            color=0xff5555
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png")
        embed.set_footer(text=f"📄 Страница {self.current_page + 1} из {self.total_pages} | /купить <название>")
        
        for item in page_items:
            embed.add_field(
                name=f"**🛒 {item[0]}**",
                value=f"└ 📝 {item[1]}\n└ 💰 {item[2]} Belfast_coin",
                inline=False
            )
        
        return embed
    
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data["custom_id"] == "prev_page":
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        elif interaction.data["custom_id"] == "next_page":
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            return True
        return False

# ========== ПАГИНАТОР ДЛЯ ДОСТИЖЕНИЙ ==========
class AchievementsPaginator(discord.ui.View):
    def __init__(self, achievements, user_id, items_per_page=4):
        super().__init__(timeout=120)
        self.achievements = achievements
        self.user_id = user_id
        self.items_per_page = items_per_page
        self.current_page = 0
        self.total_pages = (len(achievements) + items_per_page - 1) // items_per_page if achievements else 1
        self._earned = None
        self.update_buttons()
    
    @property
    def earned(self):
        if self._earned is None:
            c.execute('SELECT ach_id FROM user_achievements WHERE user_id = ?', (self.user_id,))
            self._earned = {row[0] for row in c.fetchall()}
        return self._earned
    
    def update_buttons(self):
        self.clear_items()
        if self.current_page > 0:
            self.add_item(discord.ui.Button(label="◀ НАЗАД", style=discord.ButtonStyle.secondary, custom_id="prev_page"))
        if self.current_page < self.total_pages - 1:
            self.add_item(discord.ui.Button(label="ВПЕРЕД ▶", style=discord.ButtonStyle.secondary, custom_id="next_page"))
    
    def get_embed(self):
        if not self.achievements:
            embed = discord.Embed(
                title="🏆 ДОСТИЖЕНИЯ",
                description="━━━━━━━━━━━━━━━━━━━━━━\n**Достижений пока нет!**",
                color=0xffaa77
            )
            return embed
        
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_ach = self.achievements[start:end]
        
        embed = discord.Embed(
            title="🏆 BELFAST ACHIEVEMENTS",
            description="━━━━━━━━━━━━━━━━━━━━━━",
            color=0xffaa77
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/1828/1828884.png")
        embed.set_footer(text=f"📄 Страница {self.current_page + 1} из {self.total_pages}")
        
        for ach in page_ach:
            status_emoji = "✅" if ach[0] in self.earned else "❌"
            status_text = "ПОЛУЧЕНО" if ach[0] in self.earned else "НЕ ПОЛУЧЕНО"
            embed.add_field(
                name=f"{status_emoji} **{ach[1]}**",
                value=f"└ 📝 {ach[2]}\n└ 💰 Награда: {ach[3]} монет\n└ 🏷️ {status_text}",
                inline=False
            )
        
        return embed
    
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data["custom_id"] == "prev_page":
            self.current_page -= 1
            self.update_buttons()
            self._earned = None
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        elif interaction.data["custom_id"] == "next_page":
            self.current_page += 1
            self.update_buttons()
            self._earned = None
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            return True
        return False

# ========== СОБЫТИЯ ==========
@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    await bot.tree.sync()
    print("✅ Слеш-команды синхронизированы!")
    await bot.change_presence(activity=discord.Game(name="/помощь"))

# ========== СЛЕШ-КОМАНДЫ ==========

@bot.tree.command(name="помощь", description="Показать список всех команд")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 BELFAST BOT",
        description="━━━━━━━━━━━━━━━━━━━━━━",
        color=0xff5555
    )
    embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/906/906361.png")
    embed.add_field(name="💰 ЭКОНОМИКА", value="`/баланс` `/ежедневный` `/передать` `/топ`", inline=False)
    embed.add_field(name="🏪 МАГАЗИН", value="`/магазин` `/купить` `/кейс`", inline=False)
    embed.add_field(name="🏆 ДОСТИЖЕНИЯ", value="`/достижения` `/достижение`", inline=False)
    embed.add_field(name="🎒 ИНВЕНТАРЬ", value="`/инвентарь`", inline=False)
    
    if is_admin(interaction):
        embed.add_field(name="🛠️ АДМИН", value="`/add_achievement` `/add_balance` `/remove_balance` `/add_item` `/remove_item` `/give_achievement` `/give_item`", inline=False)
    
    embed.set_footer(text="Belfast Shop | Все команды бесплатны")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="баланс", description="Показать свой баланс или баланс другого игрока")
async def balance(interaction: discord.Interaction, пользователь: discord.User = None):
    target = пользователь or interaction.user
    balance_amount = get_balance(str(target.id))
    
    embed = discord.Embed(
        title="💰 БАЛАНС",
        description=f"━━━━━━━━━━━━━━━━━━━━━━",
        color=0xffaa77
    )
    embed.add_field(name="👤 Игрок", value=target.mention, inline=True)
    embed.add_field(name="💎 Баланс", value=f"**{balance_amount}** Belfast_coin", inline=True)
    embed.set_footer(text="Используйте /ежедневный для получения бонуса")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ежедневный", description="Получить ежедневный бонус (серия увеличивает награду)")
async def daily(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    can_claim, reward, streak = check_daily(user_id)
    
    if not can_claim:
        embed = discord.Embed(
            title="❌ ЕЖЕДНЕВНЫЙ БОНУС",
            description="━━━━━━━━━━━━━━━━━━━━━━",
            color=0xff5555
        )
        embed.add_field(name="Уже получен", value="Вы уже получали бонус сегодня!\nВозвращайтесь завтра.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    update_balance(user_id, reward)
    embed = discord.Embed(
        title="🎁 ЕЖЕДНЕВНЫЙ БОНУС",
        description="━━━━━━━━━━━━━━━━━━━━━━",
        color=0xffaa77
    )
    embed.add_field(name="💰 Награда", value=f"+{reward} Belfast_coin", inline=True)
    embed.add_field(name="🔥 Серия", value=f"{streak} дней", inline=True)
    embed.set_footer(text="Возвращайтесь завтра за новым бонусом!")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="передать", description="Передать монеты другому игроку")
async def transfer(interaction: discord.Interaction, пользователь: discord.User, сумма: int):
    if сумма <= 0:
        await interaction.response.send_message("❌ Сумма должна быть больше 0!", ephemeral=True)
        return
    
    sender_id = str(interaction.user.id)
    receiver_id = str(пользователь.id)
    
    if sender_id == receiver_id:
        await interaction.response.send_message("❌ Нельзя передать монеты самому себе!", ephemeral=True)
        return
    
    sender_balance = get_balance(sender_id)
    if sender_balance < сумма:
        await interaction.response.send_message(f"❌ Не хватает! У вас {sender_balance} Belfast_coin", ephemeral=True)
        return
    
    update_balance(sender_id, -сумма)
    update_balance(receiver_id, сумма)
    
    embed = discord.Embed(
        title="💰 ПЕРЕВОД МОНЕТ",
        description="━━━━━━━━━━━━━━━━━━━━━━",
        color=0x88ff88
    )
    embed.add_field(name="📤 Отправитель", value=interaction.user.mention, inline=True)
    embed.add_field(name="📥 Получатель", value=пользователь.mention, inline=True)
    embed.add_field(name="💎 Сумма", value=f"{сумма} Belfast_coin", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="топ", description="Топ 10 игроков по балансу")
async def leaderboard(interaction: discord.Interaction):
    c.execute('SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10')
    top_users = c.fetchall()
    
    if not top_users:
        await interaction.response.send_message("📊 Нет данных для топа!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🏆 ТОП ИГРОКОВ",
        description="━━━━━━━━━━━━━━━━━━━━━━",
        color=0xffaa77
    )
    embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/1828/1828884.png")
    
    for i, (user_id, balance_amount) in enumerate(top_users, 1):
        try:
            user = await bot.fetch_user(int(user_id))
            name = user.name
        except:
            name = user_id[:8]
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        embed.add_field(name=f"{medal} #{i}", value=f"**{name}** — {balance_amount} монет", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="магазин", description="Показать все предметы в магазине")
async def shop(interaction: discord.Interaction):
    c.execute('SELECT name, description, price FROM shop_items WHERE expires_at > datetime("now") OR duration_hours = 0')
    items = c.fetchall()
    
    view = ShopPaginator(items)
    await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)

@bot.tree.command(name="купить", description="Купить предмет из магазина")
async def buy(interaction: discord.Interaction, название: str):
    user_id = str(interaction.user.id)
    c.execute('SELECT price FROM shop_items WHERE name = ? AND (expires_at > datetime("now") OR duration_hours = 0)', (название,))
    item = c.fetchone()
    
    if not item:
        embed = discord.Embed(title="❌ ОШИБКА", color=0xff5555)
        embed.description = f"Предмет `{название}` не найден в магазине!"
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    price = item[0]
    balance_amount = get_balance(user_id)
    
    if balance_amount < price:
        embed = discord.Embed(title="❌ ОШИБКА", color=0xff5555)
        embed.description = f"Не хватает! Нужно {price}, у вас {balance_amount}"
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    update_balance(user_id, -price)
    give_item(user_id, название)
    
    embed = discord.Embed(
        title="✅ ПОКУПКА",
        description="━━━━━━━━━━━━━━━━━━━━━━",
        color=0x88ff88
    )
    embed.add_field(name="🎁 Предмет", value=название, inline=True)
    embed.add_field(name="💰 Цена", value=f"{price} Belfast_coin", inline=True)
    embed.set_footer(text="Предмет добавлен в ваш инвентарь!")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="инвентарь", description="Показать свои предметы")
async def inventory(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    c.execute('SELECT item_name, quantity FROM user_items WHERE user_id = ? ORDER BY acquired_date DESC', (user_id,))
    items = c.fetchall()
    
    if not items:
        embed = discord.Embed(
            title="🎒 ИНВЕНТАРЬ",
            description="━━━━━━━━━━━━━━━━━━━━━━\n**У вас пока нет предметов!**\nКупите что-нибудь в `/магазин`",
            color=0xffaa77
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🎒 ИНВЕНТАРЬ",
        description="━━━━━━━━━━━━━━━━━━━━━━",
        color=0xffaa77
    )
    
    for item_name, quantity in items[:15]:
        embed.add_field(name=f"📦 {item_name}", value=f"└ Количество: {quantity}", inline=False)
    
    if len(items) > 15:
        embed.set_footer(text=f"и ещё {len(items) - 15} предметов...")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ========== АНИМАЦИЯ ДЛЯ КЕЙСА ==========
class CaseView(discord.ui.View):
    def __init__(self, user_id, price):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.price = price
        self.step = 0
        self.prize = None
        self.prize_amount = 0
        
        self.prizes = [
            ("🥉 Утешительный приз", 10),
            ("🥉 Бронзовая монета", 25),
            ("🥈 Серебряная монета", 50),
            ("🥇 Золотая монета", 100),
            ("💎 Алмазная монета", 250),
            ("👑 Королевский клад", 500),
            ("🎁 Секретный сундук", 750),
            ("✨ Мифический дар", 1000)
        ]
    
    async def start_animation(self, interaction: discord.Interaction):
        self.prize_name, self.prize_amount = random.choice(self.prizes)
        await self.update_message(interaction)
    
    async def update_message(self, interaction: discord.Interaction):
        animations = [
            ("🎲", "Крутим барабан..."),
            ("🎰", "Выпадает..."),
            ("✨", "Почти готово..."),
            ("🎁", "И..."),
        ]
        
        if self.step < len(animations):
            emoji, text = animations[self.step]
            embed = discord.Embed(
                title="🎲 ОТКРЫТИЕ КЕЙСА",
                description=f"━━━━━━━━━━━━━━━━━━━━━━\n{emoji} **{text}**",
                color=0xffaa77
            )
            self.step += 1
            await interaction.edit_original_response(embed=embed, view=self)
            await asyncio.sleep(0.8)
            await self.update_message(interaction)
        else:
            update_balance(self.user_id, -self.price + self.prize_amount)
            
            embed = discord.Embed(
                title="🎲 ОТКРЫТИЕ КЕЙСА",
                description="━━━━━━━━━━━━━━━━━━━━━━",
                color=0xffaa77
            )
            embed.add_field(name="🎁 Выпало", value=f"{self.prize_name} — **{self.prize_amount}** монет!", inline=False)
            embed.set_footer(text="Повезёт в следующий раз!")
            
            for child in self.children:
                child.disabled = True
            await interaction.edit_original_response(embed=embed, view=None)

@bot.tree.command(name="кейс", description="Открыть кейс за 50 монет (рандомный выигрыш)")
async def case(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    price = 50
    balance_amount = get_balance(user_id)
    
    if balance_amount < price:
        await interaction.response.send_message(f"❌ Не хватает! Кейс стоит {price} Belfast_coin", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    view = CaseView(user_id, price)
    await interaction.followup.send(embed=discord.Embed(title="🎲 ОТКРЫТИЕ КЕЙСА", description="━━━━━━━━━━━━━━━━━━━━━━\n🎲 **Начинаем открытие...**", color=0xffaa77), view=view, ephemeral=True)
    await view.start_animation(await interaction.original_response())

@bot.tree.command(name="достижения", description="Показать все достижения и статус их получения")
async def list_achievements(interaction: discord.Interaction):
    c.execute('SELECT ach_id, name, description, reward FROM achievements')
    all_ach = c.fetchall()
    
    view = AchievementsPaginator(all_ach, str(interaction.user.id))
    await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)

@bot.tree.command(name="достижение", description="Показать подробную информацию о достижении")
async def achievement_info(interaction: discord.Interaction, название: str):
    c.execute('SELECT name, description, reward FROM achievements WHERE name LIKE ?', (f'%{название}%',))
    ach = c.fetchone()
    if not ach:
        await interaction.response.send_message(f"❌ Достижение `{название}` не найдено!", ephemeral=True)
        return
    
    user_id = str(interaction.user.id)
    c.execute('''SELECT 1 FROM user_achievements ua 
                 JOIN achievements a ON ua.ach_id = a.ach_id 
                 WHERE ua.user_id = ? AND a.name = ?''', (user_id, ach[0]))
    earned = c.fetchone() is not None
    
    status = "✅ ПОЛУЧЕНО" if earned else "⏳ НЕ ПОЛУЧЕНО"
    embed = discord.Embed(
        title=f"🏆 {ach[0]}",
        description="━━━━━━━━━━━━━━━━━━━━━━",
        color=0xffaa77
    )
    embed.add_field(name="📝 Описание", value=ach[1], inline=False)
    embed.add_field(name="💰 Награда", value=f"{ach[2]} монет", inline=False)
    embed.add_field(name="📌 Статус", value=status, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ========== АДМИН-КОМАНДЫ ==========

@bot.tree.command(name="add_achievement", description="[АДМИН] Создать новое достижение")
async def add_achievement(interaction: discord.Interaction, название: str, награда: int, описание: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ У вас нет прав администратора на этом сервере!", ephemeral=True)
        return
    
    try:
        c.execute('INSERT INTO achievements (name, description, reward) VALUES (?, ?, ?)', (название, описание, награда))
        conn.commit()
        embed = discord.Embed(
            title="✅ ДОСТИЖЕНИЕ СОЗДАНО",
            description="━━━━━━━━━━━━━━━━━━━━━━",
            color=0x88ff88
        )
        embed.add_field(name="🏆 Название", value=название, inline=True)
        embed.add_field(name="💰 Награда", value=f"{награда} монет", inline=True)
        embed.add_field(name="📝 Описание", value=описание, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except sqlite3.IntegrityError:
        await interaction.response.send_message(f"❌ Достижение **{название}** уже существует!", ephemeral=True)

@bot.tree.command(name="add_balance", description="[АДМИН] Добавить монеты игроку")
async def add_balance(interaction: discord.Interaction, пользователь: discord.User, сумма: int):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ У вас нет прав администратора на этом сервере!", ephemeral=True)
        return
    
    user_id = str(пользователь.id)
    update_balance(user_id, сумма)
    
    embed = discord.Embed(title="✅ БАЛАНС ИЗМЕНЁН", color=0x88ff88)
    embed.add_field(name="👤 Игрок", value=пользователь.mention, inline=True)
    embed.add_field(name="💰 Изменение", value=f"+{сумма} Belfast_coin", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="remove_balance", description="[АДМИН] Снять монеты с игрока")
async def remove_balance(interaction: discord.Interaction, пользователь: discord.User, сумма: int):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ У вас нет прав администратора на этом сервере!", ephemeral=True)
        return
    
    user_id = str(пользователь.id)
    update_balance(user_id, -сумма)
    
    embed = discord.Embed(title="✅ БАЛАНС ИЗМЕНЁН", color=0xffaa77)
    embed.add_field(name="👤 Игрок", value=пользователь.mention, inline=True)
    embed.add_field(name="💰 Изменение", value=f"-{сумма} Belfast_coin", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="add_item", description="[АДМИН] Добавить предмет в магазин")
async def add_item(interaction: discord.Interaction, название: str, цена: int, часы: int = 0, описание: str = "Нет описания"):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ У вас нет прав администратора на этом сервере!", ephemeral=True)
        return
    
    expires_at = "NULL"
    if часы > 0:
        expires_at = f"datetime('now', '+{часы} hours')"
    
    c.execute(f'''INSERT INTO shop_items (name, description, price, duration_hours, created_at, expires_at)
                  VALUES (?, ?, ?, ?, datetime('now'), {expires_at})''', (название, описание, цена, часы))
    conn.commit()
    
    duration_text = f"{часы} часов" if часы > 0 else "навсегда"
    embed = discord.Embed(
        title="✅ ПРЕДМЕТ ДОБАВЛЕН",
        description="━━━━━━━━━━━━━━━━━━━━━━",
        color=0x88ff88
    )
    embed.add_field(name="🎁 Название", value=название, inline=True)
    embed.add_field(name="💰 Цена", value=f"{цена} монет", inline=True)
    embed.add_field(name="⏰ Длительность", value=duration_text, inline=True)
    embed.add_field(name="📝 Описание", value=описание, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="remove_item", description="[АДМИН] Удалить предмет из магазина")
async def remove_item(interaction: discord.Interaction, название: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ У вас нет прав администратора на этом сервере!", ephemeral=True)
        return
    
    c.execute('DELETE FROM shop_items WHERE name = ?', (название,))
    conn.commit()
    await interaction.response.send_message(f"✅ Предмет **{название}** удалён из магазина!", ephemeral=True)

@bot.tree.command(name="give_achievement", description="[АДМИН] Выдать достижение игроку")
async def give_achievement_cmd(interaction: discord.Interaction, пользователь: discord.User, название: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ У вас нет прав администратора на этом сервере!", ephemeral=True)
        return
    
    user_id = str(пользователь.id)
    success, result = give_achievement(user_id, название)
    
    if not success:
        await interaction.response.send_message(f"❌ {result}", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🏆 ДОСТИЖЕНИЕ ВЫДАНО",
        description="━━━━━━━━━━━━━━━━━━━━━━",
        color=0x88ff88
    )
    embed.add_field(name="👤 Игрок", value=пользователь.mention, inline=True)
    embed.add_field(name="🏆 Достижение", value=название, inline=True)
    embed.add_field(name="💰 Награда", value=f"+{result} монет", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="give_item", description="[АДМИН] Выдать предмет игроку")
async def give_item_cmd(interaction: discord.Interaction, пользователь: discord.User, название: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ У вас нет прав администратора на этом сервере!", ephemeral=True)
        return
    
    user_id = str(пользователь.id)
    success, error = give_item(user_id, название)
    
    if not success:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🎁 ПРЕДМЕТ ВЫДАН",
        description="━━━━━━━━━━━━━━━━━━━━━━",
        color=0x88ff88
    )
    embed.add_field(name="👤 Игрок", value=пользователь.mention, inline=True)
    embed.add_field(name="🎁 Предмет", value=название, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ========== ЗАПУСК ==========
bot.run(TOKEN)
