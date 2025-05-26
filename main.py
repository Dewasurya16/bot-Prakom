import os
import discord
from discord.ext import commands, tasks
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
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
    now = datetime.now(timezone.utc)
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
    if reaction.emoji == "👩":
        role = discord.utils.get(user.guild.roles, name="Prakom Cantik")
    elif reaction.emoji == "👨":
        role = discord.utils.get(user.guild.roles, name="Prakom Ganteng")
    else:
        return

    if role:
        try:
            await user.add_roles(role)
            await reaction.message.channel.send(f"{user.mention} sudah memilih {role.name}")
        except:
            pass


# ======= COMMANDS =======
@tree.command(name="userinfo", description="Tampilkan info pengguna", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="User yang ingin dilihat info-nya (opsional)")
async def userinfo(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    roles = [role.name for role in user.roles if role.name != "@everyone"]
    embed = discord.Embed(title=f"Info User: {user}", color=discord.Color.blue())
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=user.id, inline=True)
    embed.add_field(name="Nama Lengkap", value=str(user), inline=True)
    embed.add_field(name="Bot?", value=user.bot, inline=True)
    embed.add_field(name="Akun dibuat pada", value=user.created_at.strftime("%d %b %Y %H:%M UTC"), inline=False)
    embed.add_field(name="Gabung server pada", value=user.joined_at.strftime("%d %b %Y %H:%M UTC") if user.joined_at else "Tidak diketahui", inline=False)
    embed.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles) if roles else "Tidak ada", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="clear", description="Hapus pesan dalam jumlah tertentu", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(jumlah="Jumlah pesan yang ingin dihapus (maks 100)")
@is_admin_prakom()
async def clear(interaction: discord.Interaction, jumlah: int):
    if jumlah < 1 or jumlah > 100:
        await interaction.response.send_message("❌ Jumlah harus antara 1 sampai 100.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=jumlah)
    await interaction.followup.send(f"✅ Berhasil menghapus {len(deleted)} pesan.", ephemeral=True)

@tree.command(name="ping", description="Cek respons bot", guild=discord.Object(id=GUILD_ID))
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! Latensi: {round(bot.latency * 1000)} ms")


@tree.command(name="buat_tiket", description="Buat channel tiket bantuan", guild=discord.Object(id=GUILD_ID))
async def buat_tiket(interaction: discord.Interaction):
    channel, error = await create_ticket_channel(interaction.guild, interaction.user)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
    else:
        await interaction.response.send_message(f"Channel tiket dibuat: {channel.mention}", ephemeral=True)


@tree.command(name="tutup_tiket", description="Tutup channel tiket ini", guild=discord.Object(id=GUILD_ID))
async def tutup_tiket(interaction: discord.Interaction):
    if interaction.channel.category and interaction.channel.category.name == TICKET_CATEGORY_NAME:
        await interaction.response.send_message("Tiket akan ditutup dalam 5 detik...", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass
    else:
        await interaction.response.send_message("Command ini hanya bisa dipakai di channel tiket.", ephemeral=True)


@tree.command(name="pengumuman", description="Kirim pengumuman ke channel tertentu", guild=discord.Object(id=GUILD_ID))
@is_admin_prakom()
async def pengumuman(interaction: discord.Interaction, pesan: str):
    channel = interaction.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        await channel.send(f"📢 Pengumuman dari Admin:\n\n{pesan}")
        await interaction.response.send_message("Pengumuman terkirim.", ephemeral=True)
    else:
        await interaction.response.send_message("Channel pengumuman tidak ditemukan.", ephemeral=True)


# ======= DAILY ANNOUNCEMENT TASK =======
@tasks.loop(hours=24)
async def daily_reminder_task():
    await bot.wait_until_ready()
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    channel = guild.get_channel(DAILY_ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        quote = random.choice(DAILY_QUOTES)
        await channel.send(f"📅 **Pengingat Harian**\n\n{DAILY_ANNOUNCEMENT_TEMPLATE}\n\n💡 Quote hari ini:\n> {quote}")

    # Kirim DM harian ke user yang subscribe
    for user_id in daily_reminder_users:
        user = guild.get_member(user_id)
        if user:
            try:
                await user.send(DAILY_DM_TEMPLATE.format(username=user.display_name))
            except:
                pass


# ======= WEEKLY REMINDER TASK =======
@tasks.loop(minutes=1)
async def weekly_reminder_task():
    await bot.wait_until_ready()
    now = datetime.utcnow()
    weekday = now.weekday()  # Senin=0 ... Minggu=6
    current_time = now.strftime("%H:%M")

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    for user_id, reminders in weekly_reminders.items():
        user = guild.get_member(user_id)
        if not user:
            continue

        for (rem_weekday, rem_time, rem_message) in reminders:
            if rem_weekday == weekday and rem_time == current_time:
                try:
                    await user.send(f"📅 Reminder Mingguan:\n{rem_message}")
                except:
                    pass


# ======= ONE-TIME REMINDER TASK =======
@tasks.loop(minutes=1)
async def one_time_reminder_task():
    await bot.wait_until_ready()
    now = datetime.utcnow()

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    to_remove = []
    for user_id, reminders in one_time_reminders.items():
        user = guild.get_member(user_id)
        if not user:
            continue
        for dt, message in reminders:
            if dt <= now:
                try:
                    await user.send(f"⏰ Reminder Sekali:\n{message}")
                except:
                    pass
                to_remove.append((user_id, dt))

    # Hapus reminder yang sudah dikirim
    for user_id, dt in to_remove:
        one_time_reminders[user_id] = [
            (rem_dt, msg) for (rem_dt, msg) in one_time_reminders[user_id] if rem_dt != dt
        ]


# ======= PUBLIC REMINDER TASK =======
@tasks.loop(minutes=1)
async def public_reminder_task():
    await bot.wait_until_ready()
    now = datetime.utcnow().strftime("%H:%M")

    for channel_id, reminders in public_reminders.items():
        channel = bot.get_channel(channel_id)
        if not channel:
            continue
        for (time_str, message) in reminders:
            if time_str == now:
                try:
                    await channel.send(f"🔔 Pengingat Publik:\n{message}")
                except:
                    pass


# ======= CLOSE INACTIVE TICKETS =======
@tasks.loop(minutes=30)
async def close_inactive_tickets():
    now = datetime.utcnow()
    to_close = []
    for channel_id, last_active in inactive_tickets.items():
        if (now - last_active).total_seconds() > 900:  # 15 menit
            to_close.append(channel_id)
    for channel_id in to_close:
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                await channel.delete()
            except:
                pass
        inactive_tickets.pop(channel_id, None)


# ======= POLLING SYSTEM =======
@tree.command(name="poll", description="Buat polling dengan beberapa opsi", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    question="Pertanyaan polling",
    option1="Opsi 1",
    option2="Opsi 2",
    option3="Opsi 3 (opsional)",
    option4="Opsi 4 (opsional)",
    option5="Opsi 5 (opsional)"
)
async def poll(
    interaction: discord.Interaction,
    question: str,
    option1: str,
    option2: str,
    option3: str = None,
    option4: str = None,
    option5: str = None
):
    options = [option1, option2]
    if option3:
        options.append(option3)
    if option4:
        options.append(option4)
    if option5:
        options.append(option5)

    reactions = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    
    embed = discord.Embed(title="Polling", description=question, color=discord.Color.green())
    description = ""
    for i, option in enumerate(options):
        description += f"{reactions[i]} {option}\n"
    embed.description = description

    message = await interaction.channel.send(embed=embed)
    for i in range(len(options)):
        await message.add_reaction(reactions[i])

    await interaction.response.send_message("Polling berhasil dibuat!", ephemeral=True)




# ======= REMINDER COMMANDS =======
@tree.command(name="set_reminder", description="Set reminder sekali, harian, atau mingguan", guild=discord.Object(id=GUILD_ID))
async def set_reminder(
    interaction: discord.Interaction,
    tipe: str,  # "sekali", "harian", "mingguan", "publik"
    waktu: str,  # format "HH:MM" atau ISO datetime untuk sekali
    pesan: str,
    hari: int = None  # optional, 0=Senin ... 6=Minggu, untuk mingguan
):
    tipe = tipe.lower()
    user_id = interaction.user.id
    guild = interaction.guild

    if tipe == "harian":
        try:
            datetime.strptime(waktu, "%H:%M")
            daily_reminder_users.add(user_id)
            await interaction.response.send_message(f"Reminder harian set pada jam {waktu}.", ephemeral=True)
        except:
            await interaction.response.send_message("Format waktu harian harus HH:MM (24 jam).", ephemeral=True)

    elif tipe == "mingguan":
        if hari is None or hari < 0 or hari > 6:
            await interaction.response.send_message("Untuk reminder mingguan, parameter hari harus antara 0 (Senin) sampai 6 (Minggu).", ephemeral=True)
            return
        try:
            datetime.strptime(waktu, "%H:%M")
            weekly_reminders[user_id].append((hari, waktu, pesan))
            await interaction.response.send_message(f"Reminder mingguan set pada hari {hari} jam {waktu}.", ephemeral=True)
        except:
            await interaction.response.send_message("Format waktu mingguan harus HH:MM (24 jam).", ephemeral=True)

    elif tipe == "sekali":
        try:
            dt = datetime.fromisoformat(waktu)
            if dt < datetime.utcnow():
                await interaction.response.send_message("Waktu reminder harus di masa depan.", ephemeral=True)
                return
            one_time_reminders[user_id].append((dt, pesan))
            await interaction.response.send_message(f"Reminder sekali set untuk {dt.isoformat()}.", ephemeral=True)
        except:
            await interaction.response.send_message("Format waktu sekali harus ISO datetime (contoh: 2025-05-26T14:30:00).", ephemeral=True)

    elif tipe == "publik":
        channel = interaction.channel
        try:
            datetime.strptime(waktu, "%H:%M")
            public_reminders[channel.id].append((waktu, pesan))
            await interaction.response.send_message(f"Reminder publik set di channel ini pada jam {waktu}.", ephemeral=True)
        except:
            await interaction.response.send_message("Format waktu publik harus HH:MM (24 jam).", ephemeral=True)

    else:
        await interaction.response.send_message("Tipe reminder harus 'sekali', 'harian', 'mingguan', atau 'publik'.", ephemeral=True)


@tree.command(name="list_reminder", description="Lihat daftar reminder kamu", guild=discord.Object(id=GUILD_ID))
async def list_reminder(interaction: discord.Interaction):
    user_id = interaction.user.id
    msg = ""

    if user_id in daily_reminder_users:
        msg += "- Reminder Harian: Aktif\n"
    else:
        msg += "- Reminder Harian: Tidak aktif\n"

    if user_id in weekly_reminders and weekly_reminders[user_id]:
        msg += "- Reminder Mingguan:\n"
        for (hari, waktu, pesan) in weekly_reminders[user_id]:
            msg += f"  Hari {hari}, Jam {waktu}: {pesan}\n"
    else:
        msg += "- Reminder Mingguan: Tidak ada\n"

    if user_id in one_time_reminders and one_time_reminders[user_id]:
        msg += "- Reminder Sekali:\n"
        for (dt, pesan) in one_time_reminders[user_id]:
            msg += f"  {dt.isoformat()}: {pesan}\n"
    else:
        msg += "- Reminder Sekali: Tidak ada\n"

    await interaction.response.send_message(msg, ephemeral=True)


@tree.command(name="remove_reminder", description="Hapus semua reminder harian kamu", guild=discord.Object(id=GUILD_ID))
async def remove_reminder(interaction: discord.Interaction):
    user_id = interaction.user.id
    daily_reminder_users.discard(user_id)
    weekly_reminders.pop(user_id, None)
    one_time_reminders.pop(user_id, None)
    await interaction.response.send_message("Semua reminder kamu sudah dihapus.", ephemeral=True)


# ======= RUN BOT =======
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ Environment variable DISCORD_TOKEN tidak ditemukan!")
    else:
        bot.run(TOKEN)

