import os
import discord
from discord.ext import commands, tasks
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
import random

from discord import app_commands
from discord.ext.commands import has_role
from discord.ui import View, Button

# ======= CONFIGURATION =======
GUILD_ID = 1375444915403751424
POST_CHANNEL_ID = 1375939507114741872
DAILY_ANNOUNCEMENT_CHANNEL_ID = 1375939507114741872
VERIFICATION_CHANNEL_ID = 1375775766482128906
GENDER_CHANNEL_ID = 1375768360637436005
LOG_CHANNEL_ID = 1375886856188727357
LOGADMIN_CHANNEL_ID = 1376050661199708181
ANNOUNCEMENT_CHANNEL_ID = 1375821960637845564
MUTE_ROLE_NAME = "Muted"
ADMIN_PRAKOM_ROLE = "Admin Prakom"
TICKET_CATEGORY_NAME = "Tiket"

SPAM_THRESHOLD = 5
SPAM_INTERVAL = 10  # detik
MUTE_DURATION = 60  # detik

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ======= GLOBALS =======
user_messages = defaultdict(list)
user_xp = defaultdict(int)
user_level = defaultdict(int)
personal_reminders = defaultdict(list)  # {user_id: [(remind_time, message), ...]}
daily_reminder_users = set()
weekly_reminders = defaultdict(list)    # {user_id: [(weekday, time, message), ...]}
one_time_reminders = defaultdict(list)  # {user_id: [(datetime, message), ...]}
public_reminders = defaultdict(list)    # {channel_id: [(time, message), ...]}
inactive_tickets = {} 

# ======= QUOTES & TEMPLATES =======
DAILY_QUOTES = [
    "Tetap semangat, hari ini penuh peluang!",
    "Jangan menyerah, kamu lebih kuat dari yang kamu kira.",
    "Langkah kecil hari ini bisa jadi awal dari hal besar.",
    "Kerja kerasmu akan membuahkan hasil.",
    "Hidup memberi kita banyak pelajaran, tergantung pada kita apakah kita mau mempelajarinya",
    "Perjuangan merupakan tanda perjalananmu menuju sukses.",
    "Kesepian terburuk adalah tidak nyaman dengan diri sendiri.",
    "Jadilah pribadi yang menantang masa depan, bukan pengecut yang aman di zona nyaman.",
    "Kesuksesan tidak datang dari kemampuan, tetapi dari kerja keras."
]

DAILY_ANNOUNCEMENT_TEMPLATE = (
    "Selamat pagi semua! 🌞\n\n"
    "📌 Jangan lupa:\n"
    "- Cek dan kerjakan tugas yang ada hari ini.\n"
    "- Buka Mola untuk informasi terbaru dan proges SK KAMU.\n"
    "- Tetap semangat dan jaga kesehatan!"
)

DAILY_DM_TEMPLATE = (
    "Halo {username}! 👋\n\n"
    "Ini pengingat harian khusus untuk kamu:\n"
    "- Sudah cek Mola hari ini?\n"
    "- Jangan lupa buka Mola dan pastikan semua tugas sudah dikerjakan ya.\n"
    "- Semangat terus dan tetap fokus! 💪"
)

# ======= HELPER FUNCTIONS =======
def is_admin_prakom():
    async def predicate(interaction: discord.Interaction):
        role = discord.utils.get(interaction.user.roles, name=ADMIN_PRAKOM_ROLE)
        if role:
            return True
        await interaction.response.send_message(
            "❌ Kamu tidak punya izin untuk menggunakan command ini.",
            ephemeral=True)
        return False
    return app_commands.check(predicate)


async def create_ticket_channel(guild, user):
    existing_channel = discord.utils.get(
        guild.channels, name=f"tiket-{user.name.lower().replace(' ', '-')}")
    if existing_channel:
        return None, "❗ Kamu sudah punya tiket terbuka."

    category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
    if not category:
        category = await guild.create_category(TICKET_CATEGORY_NAME)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }

    admin_role = discord.utils.get(guild.roles, name=ADMIN_PRAKOM_ROLE)
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    channel = await guild.create_text_channel(
        f"tiket-{user.name.lower().replace(' ', '-')}",
        category=category,
        overwrites=overwrites)
    inactive_tickets[channel.id] = datetime.utcnow()
    return channel, None


# ======= EVENTS =======
@bot.event
async def on_ready():
    print(f"✅ Bot aktif sebagai {bot.user}")
    try:
        synced = await tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Slash commands synced: {len(synced)}")
    except Exception as e:
        print(f"Gagal sync slash commands: {e}")

    daily_reminder_task.start()
    weekly_reminder_task.start()
    one_time_reminder_task.start()
    public_reminder_task.start()
    close_inactive_tickets.start()


@bot.event
async def on_member_join(member):
    if member.guild.id != GUILD_ID:
        return
    try:
        await member.send(
            f"Selamat datang di **{member.guild.name}**! "
            f"Silakan verifikasi dengan mengirimkan nama asli kamu di channel <#{VERIFICATION_CHANNEL_ID}>."
        )
    except discord.Forbidden:
        print(f"Gagal mengirim DM ke {member}.")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Update last activity for tickets
    if message.channel.id in inactive_tickets:
        inactive_tickets[message.channel.id] = datetime.utcnow()

    # ANTI-SPAM
    now = datetime.utcnow()
    timestamps = user_messages[message.author.id]
    timestamps = [ts for ts in timestamps if (now - ts).seconds < SPAM_INTERVAL]
    timestamps.append(now)
    user_messages[message.author.id] = timestamps

    if len(timestamps) > SPAM_THRESHOLD:
        try:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} spam terdeteksi.", delete_after=5)
            mute_role = discord.utils.get(message.guild.roles, name=MUTE_ROLE_NAME)
            if mute_role and mute_role not in message.author.roles:
                await message.author.add_roles(mute_role)
                await message.channel.send(
                    f"{message.author.mention} telah dimute.", delete_after=5)
                await asyncio.sleep(MUTE_DURATION)
                if mute_role in message.author.roles:
                    await message.author.remove_roles(mute_role)
        except Exception:
            pass
        return

    # LEVELING SYSTEM
    user_xp[message.author.id] += 5
    level = user_level[message.author.id]
    next_level_xp = (level + 1) * 100
    if user_xp[message.author.id] >= next_level_xp:
        user_level[message.author.id] += 1
        await message.channel.send(
            f"🎉 {message.author.mention} naik level ke {user_level[message.author.id]}! Keep it up!"
        )

    # VERIFIKASI
    if message.guild and message.guild.id == GUILD_ID and message.channel.id == VERIFICATION_CHANNEL_ID:
        member = message.author
        guild = message.guild
        nama_baru = message.content.strip()

        try:
            await member.edit(nick=nama_baru)
        except:
            await message.channel.send("❌ Tidak bisa ganti nickname.", delete_after=10)
            return

        role_unverified = discord.utils.get(guild.roles, name="Unverified")
        role_anggota = discord.utils.get(guild.roles, name="Anggota")

        try:
            if role_unverified and role_unverified in member.roles:
                await member.remove_roles(role_unverified)
            if role_anggota and role_anggota not in member.roles:
                await member.add_roles(role_anggota)
        except:
            await message.channel.send("❌ Tidak bisa mengatur role.", delete_after=10)
            return

        channel_gender = guild.get_channel(GENDER_CHANNEL_ID)
        if channel_gender:
            pesan = await channel_gender.send(
                f"{member.mention}, pilih jenis kelamin dengan reaksi berikut:\n👩 = Prakom Cantik\n👨 = Prakom Ganteng"
            )
            await pesan.add_reaction("👩")
            await pesan.add_reaction("👨")

        try:
            await member.send(
                f"✅ Verifikasi berhasil. Nickname kamu: **{nama_baru}**. Pilih gender di channel yang disebut."
            )
        except:
            pass

        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(
                f"🟢 {member} verifikasi dan ganti nama jadi **{nama_baru}**.")

        await asyncio.sleep(10)
        try:
            await message.delete()
        except:
            pass

    await bot.process_commands(message)


@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    if reaction.message.channel.id != GENDER_CHANNEL_ID:
        return
    guild = reaction.message.guild
    member = guild.get_member(user.id)
    if not member:
        return

    role_anggota = discord.utils.get(guild.roles, name="Anggota")
    role_cantik = discord.utils.get(guild.roles, name="Prakom Cantik")
    role_ganteng = discord.utils.get(guild.roles, name="Prakom Ganteng")

    if role_anggota not in member.roles:
        return

    emoji = reaction.emoji
    if emoji == "👩":
        if role_cantik and role_cantik not in member.roles:
            await member.add_roles(role_cantik)
        if role_ganteng and role_ganteng in member.roles:
            await member.remove_roles(role_ganteng)
    elif emoji == "👨":
        if role_ganteng and role_ganteng not in member.roles:
            await member.add_roles(role_ganteng)
        if role_cantik and role_cantik in member.roles:
            await member.remove_roles(role_cantik)


# ======= SLASH COMMANDS =======
@tree.command(name="pengumuman_harian", description="Kirim pengumuman harian di channel tertentu", guild=discord.Object(id=GUILD_ID))
@is_admin_prakom()
async def pengumuman_harian(interaction: discord.Interaction):
    channel = bot.get_channel(DAILY_ANNOUNCEMENT_CHANNEL_ID)
    if not channel:
        await interaction.response.send_message("Channel pengumuman tidak ditemukan.", ephemeral=True)
        return

    quote = random.choice(DAILY_QUOTES)
    message = f"{DAILY_ANNOUNCEMENT_TEMPLATE}\n\n💡 Quote hari ini:\n*{quote}*"
    await channel.send(message)
    await interaction.response.send_message("Pengumuman harian telah dikirim.", ephemeral=True)


@tree.command(name="reminder_harian", description="Aktifkan atau nonaktifkan reminder harian lewat DM", guild=discord.Object(id=GUILD_ID))
async def reminder_harian(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id in daily_reminder_users:
        daily_reminder_users.remove(user_id)
        await interaction.response.send_message("Reminder harian dimatikan.", ephemeral=True)
    else:
        daily_reminder_users.add(user_id)
        await interaction.response.send_message("Reminder harian diaktifkan.", ephemeral=True)


@tree.command(name="buat_tiket", description="Buat tiket bantuan baru", guild=discord.Object(id=GUILD_ID))
async def buat_tiket(interaction: discord.Interaction):
    channel, error = await create_ticket_channel(interaction.guild, interaction.user)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
    else:
        await interaction.response.send_message(f"Tiket dibuat: {channel.mention}", ephemeral=True)


@tree.command(name="close_tiket", description="Tutup tiket bantuan ini", guild=discord.Object(id=GUILD_ID))
async def close_tiket(interaction: discord.Interaction):
    channel = interaction.channel
    if channel.name.startswith("tiket-"):
        await channel.delete()
        await interaction.response.send_message("Tiket ditutup dan channel dihapus.", ephemeral=True)
    else:
        await interaction.response.send_message("Command ini hanya bisa digunakan di channel tiket.", ephemeral=True)


# ======= POLLING COMMANDS =======
class PollView(View):
    def __init__(self, options):
        super().__init__(timeout=None)
        self.options = options
        self.votes = defaultdict(set)  # {option: set(user_ids)}

        for idx, option in enumerate(options):
            button = Button(label=option, style=discord.ButtonStyle.primary, custom_id=f"poll_option_{idx}")
            button.callback = self.vote_callback
            self.add_item(button)

    async def vote_callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        # Remove user's previous votes
        for option in self.votes:
            if user_id in self.votes[option]:
                self.votes[option].remove(user_id)
        # Add new vote
        clicked_option = interaction.data['custom_id'].replace("poll_option_", "")
        option_idx = int(clicked_option)
        option_label = self.options[option_idx]
        self.votes[option_label].add(user_id)

        # Count votes
        results = "\n".join(f"**{opt}**: {len(voters)} vote(s)" for opt, voters in self.votes.items())
        await interaction.response.edit_message(content=f"Polling:\n{results}", view=self)


@tree.command(name="poll", description="Buat polling dengan beberapa opsi", guild=discord.Object(id=GUILD_ID))
@is_admin_prakom()
@app_commands.describe(question="Pertanyaan polling", options="Opsi-opsi polling, pisahkan dengan koma")
async def poll(interaction: discord.Interaction, question: str, options: str):
    options_list = [opt.strip() for opt in options.split(",") if opt.strip()]
    if len(options_list) < 2:
        await interaction.response.send_message("Minimal 2 opsi diperlukan.", ephemeral=True)
        return
    if len(options_list) > 10:
        await interaction.response.send_message("Maksimal 10 opsi diperbolehkan.", ephemeral=True)
        return

    view = PollView(options_list)
    description = f"**{question}**\nPilih opsi dengan klik tombol di bawah."
    await interaction.response.send_message(description, view=view)


# ======= REMINDER COMMANDS =======
@tree.command(name="reminder_tambah", description="Tambah reminder satu kali", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(waktu="Waktu reminder (YYYY-MM-DD HH:MM)", pesan="Pesan reminder")
async def reminder_tambah(interaction: discord.Interaction, waktu: str, pesan: str):
    try:
        remind_time = datetime.strptime(waktu, "%Y-%m-%d %H:%M")
        if remind_time < datetime.utcnow():
            await interaction.response.send_message("Waktu reminder harus di masa depan.", ephemeral=True)
            return
    except:
        await interaction.response.send_message("Format waktu salah. Gunakan: YYYY-MM-DD HH:MM", ephemeral=True)
        return
    user_id = interaction.user.id
    one_time_reminders[user_id].append((remind_time, pesan))
    await interaction.response.send_message(f"Reminder satu kali ditambahkan untuk {remind_time}.", ephemeral=True)


@tree.command(name="reminder_hapus_semua", description="Hapus semua reminder kamu", guild=discord.Object(id=GUILD_ID))
async def reminder_hapus_semua(interaction: discord.Interaction):
    user_id = interaction.user.id
    personal_reminders[user_id] = []
    daily_reminder_users.discard(user_id)
    weekly_reminders[user_id] = []
    one_time_reminders[user_id] = []
    await interaction.response.send_message("Semua reminder kamu telah dihapus.", ephemeral=True)


@tree.command(name="reminder_tambah_mingguan", description="Tambah reminder mingguan", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(hari="Hari (misal Senin)", jam="Jam (HH:MM)", pesan="Pesan reminder")
async def reminder_tambah_mingguan(interaction: discord.Interaction, hari: str, jam: str, pesan: str):
    hari_map = {
        "senin": 0, "selasa": 1, "rabu": 2, "kamis": 3,
        "jumat": 4, "sabtu": 5, "minggu": 6
    }
    hari_lower = hari.lower()
    if hari_lower not in hari_map:
        await interaction.response.send_message("Hari tidak valid. Gunakan Senin, Selasa, ... Minggu.", ephemeral=True)
        return
    try:
        jam_time = datetime.strptime(jam, "%H:%M").time()
    except:
        await interaction.response.send_message("Format jam salah. Gunakan HH:MM", ephemeral=True)
        return
    user_id = interaction.user.id
    weekly_reminders[user_id].append((hari_map[hari_lower], jam_time, pesan))
    await interaction.response.send_message(f"Reminder mingguan ditambahkan setiap {hari} jam {jam}.", ephemeral=True)


@tree.command(name="reminder_tambah_publik", description="Tambah reminder publik di channel", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(channel="Channel tujuan", waktu="Waktu reminder (HH:MM)", pesan="Pesan reminder")
@is_admin_prakom()
async def reminder_tambah_publik(interaction: discord.Interaction, channel: discord.TextChannel, waktu: str, pesan: str):
    try:
        jam_time = datetime.strptime(waktu, "%H:%M").time()
    except:
        await interaction.response.send_message("Format waktu salah. Gunakan HH:MM", ephemeral=True)
        return
    public_reminders[channel.id].append((jam_time, pesan))
    await interaction.response.send_message(f"Reminder publik ditambahkan di {channel.mention} jam {waktu}.", ephemeral=True)


# ======= TASKS =======
@tasks.loop(minutes=1)
async def daily_reminder_task():
    now = datetime.utcnow()
    if now.hour == 3 and now.minute == 45:  # Jam 6 pagi UTC bisa disesuaikan
        for user_id in list(daily_reminder_users):
            user = bot.get_user(user_id)
            if user:
                try:
                    await user.send(DAILY_DM_TEMPLATE.format(username=user.name))
                except:
                    pass


@tasks.loop(minutes=1)
async def weekly_reminder_task():
    now = datetime.utcnow()
    weekday = now.weekday()
    for user_id, reminders in weekly_reminders.items():
        for day, time_, msg in reminders:
            if day == weekday and now.hour == time_.hour and now.minute == time_.minute:
                user = bot.get_user(user_id)
                if user:
                    try:
                        await user.send(f"Reminder mingguan: {msg}")
                    except:
                        pass


@tasks.loop(minutes=1)
async def one_time_reminder_task():
    now = datetime.utcnow()
    for user_id, reminders in list(one_time_reminders.items()):
        remaining = []
        for remind_time, msg in reminders:
            if remind_time <= now:
                user = bot.get_user(user_id)
                if user:
                    try:
                        await user.send(f"Reminder: {msg}")
                    except:
                        pass
            else:
                remaining.append((remind_time, msg))
        one_time_reminders[user_id] = remaining


@tasks.loop(minutes=1)
async def public_reminder_task():
    now = datetime.utcnow()
    for channel_id, reminders in public_reminders.items():
        for time_, msg in reminders:
            if now.hour == time_.hour and now.minute == time_.minute:
                channel = bot.get_channel(channel_id)
                if channel:
                    await channel.send(f"🔔 Reminder publik: {msg}")


@tasks.loop(minutes=5)
async def close_inactive_tickets():
    now = datetime.utcnow()
    for channel_id, last_active in list(inactive_tickets.items()):
        if (now - last_active).total_seconds() > 3600:  # 1 jam
            channel = bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.delete()
                except:
                    pass
            del inactive_tickets[channel_id]


# ======= RUN BOT =======
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("Error: DISCORD_BOT_TOKEN environment variable not set!")
else:
    bot.run(TOKEN)

