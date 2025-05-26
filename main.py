import os
import discord
from discord.ext import commands, tasks
import asyncio
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
import random

from discord import app_commands
from discord.ext.commands import has_role
from discord.ui import View, Button

# ======= KONFIGURASI =======
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

# DEFINISI ZONA WAKTU WIB (UTC+7)
WIB = timezone(timedelta(hours=7))

# ======= GLOBAL =======
user_messages = defaultdict(list)
user_xp = defaultdict(int)
user_level = defaultdict(int)
# personal_reminders dihapus karena tidak ada implementasi loop untuknya
daily_reminder_users = set()
weekly_reminders = defaultdict(list)
one_time_reminders = defaultdict(list)
public_reminders = defaultdict(list)
inactive_tickets = {}

# Tempat menyimpan semua reminder ke role
role_reminders = []  # List berisi dict reminder ke role

# ======= KUTIPAN & TEMPLAT =======
DAILY_QUOTES = [
    "Tetap semangat, hari ini penuh peluang!",
    "Jangan menyerah, kamu lebih kuat dari yang kamu kira.",
    "Langkah kecil hari ini bisa jadi awal dari hal besar.",
    "Kerja kerasmu akan membuahkan hasil.",
    "Hidup memberi kita banyak pelajaran, tergantung pada kita apakah kita mau mempelajarinya",
    "Perjuangan merupakan tanda perjalananmu menuju sukses.",
    "Kesepian terburuk adalah tidak nyaman dengan diri sendiri.",
    "Jadilah pribadi yang menantang masa depan, bukan pengecut yang aman di zona nyaman.",
    "Kesuksesan tidak datang dari kemampuan, tetapi dari kerja keras.",
    "Jangan takut mencoba hal baru. Ingat, kapal tidak akan berlayar jika hanya diam di pelabuhan.",
    "Setiap hari adalah kesempatan baru untuk menjadi versi terbaik dari dirimu.",
    "Kegagalan adalah guru terbaik. Pelajari darinya dan terus melangkah.",
    "Fokus pada kemajuan, bukan kesempurnaan.",
    "Pikiran positif akan menarik hal-hal positif. Percayalah pada dirimu!",
    "Orang sukses tidak pernah menyerah. Mereka terus belajar dan beradaptasi.",
    "Nikmati perjalananmu, bukan hanya tujuan akhirnya.",
    "Berani bermimpi besar, dan berani untuk mewujudkannya.",
    "Keajaiban ada di mana-mana, cukup buka matamu.",
    "Kemarin adalah sejarah, besok adalah misteri, hari ini adalah hadiah. Itu sebabnya disebut saat ini.",
    "Hal terbaik tentang masa depan adalah ia datang satu hari pada satu waktu."
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

# ======= FUNGSI BANTUAN =======
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
    inactive_tickets[channel.id] = datetime.now(WIB)
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
    check_role_reminders.start()


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
        inactive_tickets[message.channel.id] = datetime.now(WIB)

    # ANTI-SPAM
    now = datetime.now(WIB)
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

    # SISTEM LEVELING
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


# ======= PERINTAH =======
@tree.command(name="set_reminder", description="Set reminder: sekali, harian, mingguan, publik", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    tipe="Tipe reminder: sekali, harian, mingguan, publik",
    waktu="Waktu pengingat. Format HH:MM untuk harian/mingguan/publik, ISO datetime untuk sekali",
    pesan="Pesan yang akan dikirim",
    hari="Untuk tipe mingguan: 0=Senin ... 6=Minggu"
)
async def set_reminder(
    interaction: discord.Interaction,
    tipe: str,
    waktu: str,
    pesan: str,
    hari: int = None
):
    await interaction.response.defer(ephemeral=True)
    now = datetime.now(WIB)
    tipe = tipe.lower()
    user_id = interaction.user.id
    guild = interaction.guild
    
    if tipe == "harian":
        try:
            datetime.strptime(waktu, "%H:%M")
            daily_reminder_users.add(user_id)
            await interaction.followup.send(f"Reminder harian set pada jam {waktu}.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Format waktu harian harus HH:MM (24 jam).", ephemeral=True)

    elif tipe == "mingguan":
        if hari is None or not (0 <= hari <= 6):
            await interaction.followup.send("Untuk reminder mingguan, parameter hari harus antara 0 (Senin) sampai 6 (Minggu).", ephemeral=True)
            return
        try:
            datetime.strptime(waktu, "%H:%M")
            weekly_reminders[user_id].append((hari, waktu, pesan))
            await interaction.followup.send(f"Reminder mingguan set pada hari {hari} jam {waktu}.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Format waktu mingguan harus HH:MM (24 jam).", ephemeral=True)

    elif tipe == "sekali":
        try:
            dt = datetime.fromisoformat(waktu)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=WIB)
            
            if dt < datetime.now(WIB):
                await interaction.followup.send("Waktu reminder harus di masa depan.", ephemeral=True)
                return
            one_time_reminders[user_id].append((dt, pesan))
            await interaction.followup.send(f"Reminder sekali set untuk {dt.isoformat()} (WIB).", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Format waktu sekali harus ISO datetime (contoh: 2025-05-26T14:30:00+07:00).", ephemeral=True)

    elif tipe == "publik":
        channel = interaction.channel
        try:
            datetime.strptime(waktu, "%H:%M")
            public_reminders[channel.id].append((waktu, pesan))
            await interaction.followup.send(f"Reminder publik set di channel ini pada jam {waktu}.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Format waktu publik harus HH:MM (24 jam).", ephemeral=True)

    else:
        await interaction.followup.send("Tipe reminder tidak valid. Gunakan 'sekali', 'harian', 'mingguan', atau 'publik'.", ephemeral=True)

### Perintah Khusus Admin dan Informasi

@tree.command(name="reminder", description="Kirim pengingat ke role tertentu pada waktu spesifik.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    role="Role yang akan di-mention",
    waktu="Waktu pengingat (format ISO datetime, contoh: 2025-06-01T10:00:00+07:00)",
    pesan="Pesan pengingat yang akan dikirim"
)
@is_admin_prakom() # Hanya admin yang bisa pakai command ini
async def reminder(
    interaction: discord.Interaction,
    role: discord.Role,
    waktu: str,
    pesan: str
):
    await interaction.response.defer(ephemeral=True)
    now = datetime.now(WIB)
    user_id = interaction.user.id

    try:
        remind_time_obj = datetime.fromisoformat(waktu)
        if remind_time_obj.tzinfo is None:
            remind_time_obj = remind_time_obj.replace(tzinfo=WIB)
        else:
            remind_time_obj = remind_time_obj.astimezone(WIB)

        if remind_time_obj <= now:
            await interaction.followup.send("Waktu pengingat harus di masa depan (menggunakan WIB).", ephemeral=True)
            return
        
        role_reminders.append({
            "tipe": "role",
            "waktu": remind_time_obj,
            "pesan": pesan,
            "role": role,
            "channel_id": interaction.channel.id,
            "creator_id": user_id
        })
        await interaction.followup.send(f"✅ Pengingat untuk **{role.name}** berhasil disimpan pada **{remind_time_obj.strftime('%d %b %Y %H:%M WIB')}** di channel ini.", ephemeral=True)

    except ValueError:
        await interaction.followup.send("❌ Format waktu harus ISO datetime (contoh: `2025-06-01T10:00:00+07:00`).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Terjadi kesalahan: {e}", ephemeral=True)
        print(f"Error di command /reminder: {e}")

@tree.command(name="mars_adhyaksa", description="Menampilkan lirik Mars Adhyaksa.", guild=discord.Object(id=GUILD_ID))
async def mars_adhyaksa(interaction: discord.Interaction):
    mars_text = """
**MARS ADHYAKSA**

Satya Adi Wicaksana dasar Tripsila Adhyaksa
Landasan jiwa Kejaksaan sebagai abdi masyarakat
Setia dan sempurna
Melaksanakan tugas kewajiban
Tanggung jawab pada Tuhan,
Keluarga dan sesama manusia

Abdi negara sebagai penegak hukum
Yang berlambangkan pedang nan sakti
Insan Adhyaksa sebagai pedamba
Keadilan dan perwujudan hukum pasti

Kita basmi kemungkaran
Kebatilan dan kejahatan yang
Tersirat dan tersurat imbangan
Tegarlah sepanjang zaman..
"""
    await interaction.response.send_message(mars_text)

@tree.command(name="tri_karma_adhyaksa", description="Menampilkan Tri Karma Adhyaksa.", guild=discord.Object(id=GUILD_ID))
async def tri_karma_adhyaksa(interaction: discord.Interaction):
    tri_karma_text = """
**TRI KARMA ADHYAKSA**

1.  **Satya**
    Kesetiaan yang tanpa batas terhadap Tuhan Yang Maha Esa, Negara dan Masyarakat.

2.  **Adi**
    Yakni kemampuan dan kemauan mencapai kesempurnaan dalam pelaksanaan tugas dan kewajiban serta senantiasa berpegang teguh pada kebenaran.

3.  **Wicaksana**
    Bijaksana dalam tutur kata dan tingkah laku, baik di dalam maupun di luar kedinasan.
"""
    await interaction.response.send_message(tri_karma_text)

@tree.command(name="userinfo", description="Tampilkan info pengguna", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="User yang ingin dilihat info-nya (opsional)")
async def userinfo(interaction: discord.Interaction, user: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    user = user or interaction.user
    roles = [role.name for role in user.roles if role.name != "@everyone"]
    embed = discord.Embed(title=f"Info User: {user}", color=discord.Color.blue())
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=user.id, inline=True)
    embed.add_field(name="Nama Lengkap", value=str(user), inline=True)
    embed.add_field(name="Bot?", value=user.bot, inline=True)
    embed.add_field(name="Akun dibuat pada", value=user.created_at.strftime("%d %b %Y %H:%M WIB"), inline=False)
    embed.add_field(name="Gabung server pada", value=user.joined_at.strftime("%d %b %Y %H:%M WIB") if user.joined_at else "Tidak diketahui", inline=False)
    embed.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles) if roles else "Tidak ada", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)

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
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(f"Pong! Latensi: {round(bot.latency * 1000)} ms")


@tree.command(name="buat_tiket", description="Buat channel tiket bantuan", guild=discord.Object(id=GUILD_ID))
async def buat_tiket(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    channel, error = await create_ticket_channel(interaction.guild, interaction.user)
    if error:
        await interaction.followup.send(error, ephemeral=True)
    else:
        await interaction.followup.send(f"Channel tiket dibuat: {channel.mention}", ephemeral=True)


@tree.command(name="tutup_tiket", description="Tutup channel tiket ini", guild=discord.Object(id=GUILD_ID))
async def tutup_tiket(interaction: discord.Interaction):
    if interaction.channel.category and interaction.channel.category.name == TICKET_CATEGORY_NAME:
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Tiket akan ditutup dalam 5 detik...", ephemeral=True)
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
    await interaction.response.defer(ephemeral=True)
    channel = interaction.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        await channel.send(f"📢 Pengumuman dari Admin:\n\n{pesan}")
    await interaction.followup.send("Pengumuman terkirim.", ephemeral=True)


# ======= TUGAS PENGINGAT HARIAN =======
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


# ======= TUGAS PENGINGAT MINGGUAN =======
@tasks.loop(minutes=1)
async def weekly_reminder_task():
    await bot.wait_until_ready()
    now = datetime.now(WIB)
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


# ======= TUGAS PENGINGAT SEKALI =======
@tasks.loop(minutes=1)
async def one_time_reminder_task():
    await bot.wait_until_ready()
    now = datetime.now(WIB)

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


# ======= TUGAS PENGINGAT PUBLIK =======
@tasks.loop(minutes=1)
async def public_reminder_task():
    await bot.wait_until_ready()
    now = datetime.now(WIB).strftime("%H:%M")

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

# ======= TUGAS PENGINGAT ROLE =======
@tasks.loop(minutes=1)
async def check_role_reminders():
    await bot.wait_until_ready()
    global role_reminders
    now = datetime.now(WIB)
    to_remove_role_reminders = []

    for reminder in role_reminders:
        if reminder["tipe"] == "role":
            remind_time = reminder["waktu"]
            if isinstance(remind_time, datetime) and remind_time <= now:
                channel = bot.get_channel(reminder["channel_id"])
                role = reminder["role"]
                message = reminder["pesan"]
                if channel and role:
                    try:
                        await channel.send(f"{role.mention} {message}")
                    except Exception as e:
                        print(f"Gagal mengirim reminder role: {e}")
                to_remove_role_reminders.append(reminder)
    
    for rem in to_remove_role_reminders:
        role_reminders = [r for r in role_reminders if r != rem]

# ======= TUTUP TIKET TIDAK AKTIF =======
@tasks.loop(minutes=30)
async def close_inactive_tickets():
    await bot.wait_until_ready()
    global inactive_tickets
    now = datetime.now(WIB)
    to_close = []
    for channel_id, last_active in inactive_tickets.items():
        elapsed = (now - last_active).total_seconds()
        if elapsed > 1800:  # 30 menit = 1800 detik
            to_close.append(channel_id)

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    for channel_id in to_close:
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.send("Tiket ini sudah tidak aktif selama 30 menit dan akan ditutup otomatis.")
                await asyncio.sleep(5)
                await channel.delete()
            except Exception as e:
                print(f"Gagal menutup tiket {channel.name}: {e}")
        inactive_tickets.pop(channel_id, None)


# ======= SISTEM POLLING =======
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
    await interaction.response.defer(ephemeral=True)
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

    await interaction.followup.send("Polling berhasil dibuat!", ephemeral=True)

# ======= PERINTAH PENGINGAT (DIPERBARUI) =======

@tree.command(name="list_reminder", description="Lihat daftar reminder kamu", guild=discord.Object(id=GUILD_ID))
async def list_reminder(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    msg = ""

    if user_id in daily_reminder_users:
        msg += "- Reminder Harian Pribadi: Aktif\n"
    else:
        msg += "- Reminder Harian Pribadi: Tidak aktif\n"

    if user_id in weekly_reminders and weekly_reminders[user_id]:
        msg += "- Reminder Mingguan Pribadi:\n"
        for (hari, waktu, pesan) in weekly_reminders[user_id]:
            msg += f"  Hari {hari}, Jam {waktu}: {pesan}\n"
    else:
        msg += "- Reminder Mingguan Pribadi: Tidak ada\n"

    if user_id in one_time_reminders and one_time_reminders[user_id]:
        msg += "- Reminder Sekali Pribadi:\n"
        for (dt, pesan) in one_time_reminders[user_id]:
            msg += f"  {dt.strftime('%d %b %Y %H:%M WIB')}: {pesan}\n"
    else:
        msg += "- Reminder Sekali Pribadi: Tidak ada\n"

    # Tambahkan daftar reminder role yang dibuat oleh user ini
    user_role_reminders = [
        r for r in role_reminders if r.get("creator_id") == user_id
    ]
    if user_role_reminders:
        msg += "- Reminder Role yang kamu buat:\n"
        for rem in user_role_reminders:
            waktu_str = rem['waktu'].strftime("%d %b %Y %H:%M WIB") if isinstance(rem['waktu'], datetime) else rem['waktu'].strftime("%H:%M")
            role_name = rem['role'].name if isinstance(rem['role'], discord.Role) else "Role Tidak Ditemukan"
            msg += f"  Untuk role {role_name} pada {waktu_str} di channel <#{rem['channel_id']}>: {rem['pesan']}\n"
    else:
        msg += "- Reminder Role yang kamu buat: Tidak ada\n"

    await interaction.followup.send(msg, ephemeral=True)


@tree.command(name="remove_reminder", description="Hapus semua reminder pribadi kamu (harian, mingguan, sekali) dan reminder role yang kamu buat", guild=discord.Object(id=GUILD_ID))
async def remove_reminder(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    daily_reminder_users.discard(user_id)
    weekly_reminders.pop(user_id, None)
    one_time_reminders.pop(user_id, None)
    
    global role_reminders
    role_reminders = [r for r in role_reminders if r.get("creator_id") != user_id]
    
    await interaction.followup.send("Semua reminder pribadi kamu sudah dihapus. Reminder role yang kamu buat juga telah dihapus.", ephemeral=True)


# ======= JALANKAN BOT =======
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ Environment variable DISCORD_TOKEN tidak ditemukan!")
    else:
        bot.run(TOKEN)
