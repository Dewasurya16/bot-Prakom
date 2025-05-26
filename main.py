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

# public_reminders tetap ada karena itu pengingat ke channel, bukan DM pribadi
public_reminders = defaultdict(list)
inactive_tickets = {}

# Tempat menyimpan semua reminder ke role (tetap ada)
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

    # Hanya jalankan tugas pengingat yang relevan
    daily_reminder_task.start() # Ini untuk pengumuman harian di channel, bukan DM
    public_reminder_task.start() # Tetap ada untuk pengingat publik di channel
    close_inactive_tickets.start()
    check_role_reminders.start() # Tetap ada untuk pengingat role


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

    guild = reaction.message.guild
    role_to_add = None
    
    if reaction.emoji == "👩":
        role_to_add = discord.utils.get(guild.roles, name="Prakom Cantik")
    elif reaction.emoji == "👨":
        role_to_add = discord.utils.get(guild.roles, name="Prakom Ganteng")
    else:
        # Jika emoji yang direaksikan bukan yang diharapkan, hentikan proses
        return

    if role_to_add:
        try:
            # Tambahkan role baru
            await user.add_roles(role_to_add)
            await reaction.message.channel.send(f"{user.mention} sudah memilih {role_to_add.name}")

            # Hapus role 'Anggota' jika ada
            role_anggota = discord.utils.get(guild.roles, name="Anggota")
            if role_anggota and role_anggota in user.roles:
                await user.remove_roles(role_anggota)
                print(f"Role 'Anggota' dihapus dari {user.display_name}")

        except discord.Forbidden:
            print(f"Bot tidak memiliki izin untuk mengelola role untuk {user}.")
            await reaction.message.channel.send(f"❌ Saya tidak memiliki izin untuk mengatur role.")
        except Exception as e:
            print(f"Terjadi kesalahan saat mengatur role untuk {user}: {e}")
            await reaction.message.channel.send(f"❌ Terjadi kesalahan saat mengatur role Anda.")


# ======= PERINTAH =======
@tree.command(name="set_reminder", description="Set reminder: publik (HH:MM) atau sekali (YYYY-MM-DDTHH:MM)", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    tipe="Tipe reminder: publik atau sekali",
    waktu="Waktu pengingat. Format HH:MM untuk publik, YYYY-MM-DDTHH:MM untuk sekali",
    pesan="Pesan yang akan dikirim"
)
async def set_reminder(
    interaction: discord.Interaction,
    tipe: str,
    waktu: str,
    pesan: str
):
    await interaction.response.defer(ephemeral=True)
    now = datetime.now(WIB)
    tipe = tipe.lower()
    
    if tipe == "sekali":
        try:
            # Parse waktu tanpa timezone, lalu asumsikan WIB
            dt = datetime.fromisoformat(waktu)
            dt = dt.replace(tzinfo=WIB) # Asumsikan WIB
            
            if dt < now:
                await interaction.followup.send("Waktu reminder harus di masa depan.", ephemeral=True)
                return
            
            # Tambahkan ke role_reminders (sekali untuk channel)
            role_reminders.append({
                "tipe": "sekali_channel", # Tipe baru untuk pengingat sekali di channel
                "waktu": dt,
                "pesan": pesan,
                "channel_id": interaction.channel.id,
                "creator_id": interaction.user.id # Simpan siapa yang membuat
            })
            await interaction.followup.send(f"Reminder sekali set untuk **{dt.strftime('%d %b %Y %H:%M WIB')}** di channel ini.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Format waktu sekali harus YYYY-MM-DDTHH:MM (contoh: 2025-05-26T14:30).", ephemeral=True)

    elif tipe == "publik":
        channel = interaction.channel
        try:
            datetime.strptime(waktu, "%H:%M") # Cek format HH:MM
            public_reminders[channel.id].append((waktu, pesan))
            await interaction.followup.send(f"Reminder publik set di channel ini pada jam **{waktu} WIB**.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Format waktu publik harus HH:MM (24 jam, contoh: 14:30).", ephemeral=True)

    else:
        await interaction.followup.send("Tipe reminder tidak valid. Gunakan 'sekali' atau 'publik'.", ephemeral=True)

### Perintah Khusus Admin dan Informasi

@tree.command(name="reminder_role", description="Kirim pengingat ke role tertentu pada waktu spesifik (Admin Only).", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    role="Role yang akan di-mention",
    waktu="Waktu pengingat (format YYYY-MM-DDTHH:MM, akan dianggap WIB)",
    pesan="Pesan pengingat yang akan dikirim"
)
@is_admin_prakom() # Hanya admin yang bisa pakai command ini
async def reminder_role(
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
        remind_time_obj = remind_time_obj.replace(tzinfo=WIB) # Asumsikan WIB
        
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
        await interaction.followup.send("❌ Format waktu harus YYYY-MM-DDTHH:MM (contoh: `2025-06-01T10:00`).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Terjadi kesalahan: {e}", ephemeral=True)
        print(f"Error di command /reminder_role: {e}")

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
    tri_krama_text = """
**TRI KRAMA ADHYAKSA**

1.  **Satya**
    Kesetiaan yang bersumber pada rasa jujur, baik terhadap Tuhan Yang Maha Esa, Diri pribadi dan keluarga maupun kepada sesama manusia.

2.  **Adhi**
    Kesempurnaan dalam bertugas dan yang berunsur utama pemilikan rasa tanggung jawab terhadap tuhan yang maha esa, keluarga dan sesama manusia.

3.  **Wicaksana**
    Bijaksana dalam tutur kata dan tingkah laku,khususnya dalam penerapan tugas dan kewenangan.
"""
    await interaction.response.send_message(tri_krama_text) # Variabel sudah benar sekarang

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

---
### Command Manajemen Tiket

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

---
### Command Pengumuman Admin

@tree.command(name="pengumuman", description="Kirim pengumuman ke channel tertentu", guild=discord.Object(id=GUILD_ID))
@is_admin_prakom()
async def pengumuman(interaction: discord.Interaction, pesan: str):
    await interaction.response.defer(ephemeral=True)
    channel = interaction.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        await channel.send(f"📢 Pengumuman dari Admin:\n\n{pesan}")
    await interaction.followup.send("Pengumuman terkirim.", ephemeral=True)

---
### Tugas Berulang Otomatis

# ======= TUGAS PENGINGAT HARIAN (untuk channel umum) =======
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
             
# ======= TUGAS PENGINGAT PUBLIK (HH:MM di channel) =======
@tasks.loop(minutes=1)
async def public_reminder_task():
    await bot.wait_until_ready()
    now = datetime.now(WIB).strftime("%H:%M")

    # Menggunakan list temporary untuk menampung pengingat yang akan dikirim
    # Ini untuk menghindari modifikasi dictionary saat iterasi
    reminders_to_send = [] 

    for channel_id, reminders in public_reminders.items():
        channel = bot.get_channel(channel_id)
        if not channel:
            continue
        
        # Iterasi dan kumpulkan pengingat yang akan dikirim
        for (time_str, message) in reminders:
            if time_str == now:
                reminders_to_send.append((channel, message))
    
    # Kirim pengingat setelah iterasi selesai
    for channel, message in reminders_to_send:
        try:
            # Perhatikan: Pengingat publik HH:MM akan terkirim setiap hari pada waktu yang sama.
            # Jika ingin sekali saja, perlu ditandai dan dihapus setelah terkirim.
            # Untuk saat ini, asumsikan ini adalah pengingat berulang harian.
            await channel.send(f"🔔 Pengingat Publik:\n{message}")
        except Exception as e:
            print(f"Gagal mengirim pengingat publik di channel {channel.name}: {e}")
            
# ======= TUGAS PENGINGAT ROLE & SEKALI (di channel) =======
@tasks.loop(minutes=1)
async def check_role_reminders():
    await bot.wait_until_ready()
    global role_reminders
    now = datetime.now(WIB)
    to_remove_reminders = []

    for reminder in role_reminders:
        remind_time = reminder["waktu"]
        if isinstance(remind_time, datetime) and remind_time <= now:
            channel = bot.get_channel(reminder["channel_id"])
            message = reminder["pesan"]
            
            if channel:
                try:
                    if reminder["tipe"] == "role":
                        role = reminder["role"]
                        if role:
                            await channel.send(f"{role.mention} {message}")
                        else:
                            print(f"Role tidak ditemukan untuk reminder: {reminder}")
                    elif reminder["tipe"] == "sekali_channel":
                        await channel.send(f"⏰ Pengingat Sekali:\n{message}")
                    else:
                        print(f"Tipe reminder tidak dikenal: {reminder['tipe']}")
                except Exception as e:
                    print(f"Gagal mengirim reminder: {e} di channel {channel.name}")
            
            # Tandai pengingat untuk dihapus (sekali dan role)
            to_remove_reminders.append(reminder)
    
    # Hapus pengingat yang sudah dikirim
    role_reminders = [r for r in role_reminders if r not in to_remove_reminders]

---
### Penutupan Tiket Otomatis

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

---
### Sistem Polling

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

---
### Manajemen Pengingat (DIPERBARUI)

@tree.command(name="list_reminder", description="Lihat daftar reminder yang kamu buat (publik dan role)", guild=discord.Object(id=GUILD_ID))
async def list_reminder(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    msg = ""

    # Daftar pengingat publik di channel ini
    current_channel_id = interaction.channel.id
    if current_channel_id in public_reminders and public_reminders[current_channel_id]:
        msg += "- Pengingat Publik di channel ini:\n"
        for (waktu, pesan) in public_reminders[current_channel_id]:
            msg += f"  Setiap hari jam {waktu}: {pesan}\n"
    else:
        msg += "- Pengingat Publik di channel ini: Tidak ada\n"

    # Daftar pengingat sekali atau role yang dibuat oleh user ini
    user_created_reminders = [
        r for r in role_reminders if r.get("creator_id") == user_id
    ]
    if user_created_reminders:
        msg += "- Pengingat Sekali atau Role yang kamu buat:\n"
        for rem in user_created_reminders:
            waktu_str = rem['waktu'].strftime("%d %b %Y %H:%M WIB")
            if rem["tipe"] == "role":
                # Menggunakan try-except untuk mendapatkan nama role, karena objek role bisa tidak valid setelah bot restart
                role_name = "Role Tidak Ditemukan"
                if isinstance(rem['role'], discord.Role):
                    role_name = rem['role'].name
                # Jika role disimpan hanya sebagai ID, Anda perlu fetch role dari guild:
                # guild = interaction.guild
                # fetched_role = guild.get_role(rem['role_id']) # jika anda menyimpan role_id
                # role_name = fetched_role.name if fetched_role else "Role Tidak Ditemukan"
                msg += f"  Untuk role {role_name} pada {waktu_str} di channel <#{rem['channel_id']}>: {rem['pesan']}\n"
            elif rem["tipe"] == "sekali_channel":
                msg += f"  Sekali pada {waktu_str} di channel <#{rem['channel_id']}>: {rem['pesan']}\n"
    else:
        msg += "- Pengingat Sekali atau Role yang kamu buat: Tidak ada\n"

    await interaction.followup.send(msg, ephemeral=True)


@tree.command(name="remove_reminder", description="Hapus semua reminder publik atau role yang kamu buat", guild=discord.Object(id=GUILD_ID))
async def remove_reminder(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    
    # Hapus pengingat publik yang dibuat di channel ini
    # Note: Untuk saat ini, ini akan menghapus SEMUA public reminder di channel tersebut,
    # tidak hanya yang dibuat oleh user tertentu, karena data public_reminders tidak menyimpan creator_id.
    if interaction.channel.id in public_reminders:
        public_reminders[interaction.channel.id] = []
        # Anda bisa juga menggunakan: public_reminders.pop(interaction.channel.id, None)

    global role_reminders
    # Hapus pengingat sekali atau role yang dibuat oleh user ini
    # Ini sudah benar karena role_reminders menyimpan 'creator_id'
    role_reminders = [r for r in role_reminders if r.get("creator_id") != user_id]
    
    await interaction.followup.send("Semua pengingat publik di channel ini dan pengingat role yang kamu buat sudah dihapus.", ephemeral=True)


# ======= JALANKAN BOT =======
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ Environment variable DISCORD_TOKEN tidak ditemukan!")
    else:
        bot.run(TOKEN)
