import os
import discord
from discord.ext import commands, tasks
import asyncio
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
import random
import json

from discord import app_commands
from discord.ext.commands import has_role
from discord.ui import View, Button

# ======= KONFIGURASI =======
GUILD_ID = 1375444915403751424
POST_CHANNEL_ID = 1375939507114741872
DAILY_ANNOUNCEMENT_CHANNEL_ID = 1375939507114741872
# Ganti channel ID ini menjadi channel "Selamat Datang" Anda
WELCOME_CHANNEL_ID = 1375824875838505020 
VERIFICATION_CHANNEL_ID = 1375775766482128906
GENDER_CHANNEL_ID = 1375768360637436005
LOG_CHANNEL_ID = 1375886856188727357
LOGADMIN_CHANNEL_ID = 1376050661199708181
ANNOUNCEMENT_CHANNEL_ID = 1375821960637845564
MUTE_ROLE_NAME = "Muted"
ADMIN_PRAKOM_ROLE = "Admin Prakom"
TICKET_CATEGORY_NAME = "Tiket"
UNVERIFIED_ROLE_NAME = "Unverified" 

SPAM_THRESHOLD = 5
SPAM_INTERVAL = 10  # detik
MUTE_DURATION = 60  # detik

# File data untuk persistensi
WARN_DATA_FILE = "warn_data.json"
PRIVATE_REMINDER_DATA_FILE = "private_reminders.json"
ROLE_REMINDER_DATA_FILE = "role_reminders.json"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# DEFINISI ZONA WAKTU WIB (UTC+7)
WIB = timezone(timedelta(hours=7))

# ======= GLOBAL VARIABLES =======
user_messages = defaultdict(list)
user_xp = defaultdict(int)
user_level = defaultdict(int)

public_reminders = defaultdict(list) 
inactive_tickets = {}

# Data yang akan disimpan ke file
warn_data = {}
private_reminders_data = {}
role_reminders = [] 

# ======= FUNGSI LOAD/SAVE DATA =======
def load_warn_data():
    global warn_data
    if os.path.exists(WARN_DATA_FILE):
        with open(WARN_DATA_FILE, 'r') as f:
            warn_data = json.load(f)
    else:
        warn_data = {}

def save_warn_data():
    with open(WARN_DATA_FILE, 'w') as f:
        json.dump(warn_data, f, indent=4)

def load_private_reminders():
    global private_reminders_data
    if os.path.exists(PRIVATE_REMINDER_DATA_FILE):
        with open(PRIVATE_REMINDER_DATA_FILE, 'r') as f:
            data = json.load(f)
            private_reminders_data = {
                user_id: [
                    {
                        "time": datetime.fromisoformat(rem["time"]),
                        "message": rem["message"]
                    } for rem in reminders
                ] for user_id, reminders in data.items()
            }
    else:
        private_reminders_data = {}

def save_private_reminders():
    data_to_save = {
        user_id: [
            {
                "time": rem["time"].isoformat(),
                "message": rem["message"]
            } for rem in reminders
        ] for user_id, reminders in private_reminders_data.items()
    }
    with open(PRIVATE_REMINDER_DATA_FILE, 'w') as f:
        json.dump(data_to_save, f, indent=4)

def load_role_reminders():
    global role_reminders
    if os.path.exists(ROLE_REMINDER_DATA_FILE):
        with open(ROLE_REMINDER_DATA_FILE, 'r') as f:
            data = json.load(f)
            role_reminders = []
            for rem in data:
                if "waktu" in rem:
                    rem["waktu"] = datetime.fromisoformat(rem["waktu"])
                if rem.get("tipe") == "role" and "role_id" in rem:
                    pass
                role_reminders.append(rem)
    else:
        role_reminders = []

def save_role_reminders():
    data_to_save = []
    for rem in role_reminders:
        temp_rem = rem.copy()
        if "waktu" in temp_rem and isinstance(temp_rem["waktu"], datetime):
            temp_rem["waktu"] = temp_rem["waktu"].isoformat()
        if temp_rem.get("tipe") == "role" and isinstance(temp_rem.get("role"), discord.Role):
            temp_rem["role_id"] = temp_rem["role"].id
            del temp_rem["role"] 
        data_to_save.append(temp_rem)
    with open(ROLE_REMINDER_DATA_FILE, 'w') as f:
        json.dump(data_to_save, f, indent=4)

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
    load_warn_data()
    load_private_reminders()
    load_role_reminders()
    try:
        synced = await tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Slash commands synced: {len(synced)}")
    except Exception as e:
        print(f"Gagal sync slash commands: {e}")

    daily_reminder_task.start()
    public_reminder_task.start()
    close_inactive_tickets.start()
    check_role_reminders.start()
    check_private_reminders.start()

@bot.event
async def on_member_join(member):
    if member.guild.id != GUILD_ID:
        return
    
    guild = member.guild

    # Beri role "Unverified" secara otomatis saat bergabung
    role_unverified = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE_NAME)
    if role_unverified:
        try:
            await member.add_roles(role_unverified)
            print(f"Role '{UNVERIFIED_ROLE_NAME}' diberikan kepada {member.display_name}")
        except discord.Forbidden:
            print(f"Bot tidak memiliki izin untuk memberikan role '{UNVERIFIED_ROLE_NAME}' kepada {member}.")
        except Exception as e:
            print(f"Terjadi kesalahan saat memberikan role '{UNVERIFIED_ROLE_NAME}' kepada {member}: {e}")

    # Kirim DM ke anggota baru
    try:
        await member.send(
            f"Selamat datang di **{guild.name}**! "
            f"Silakan verifikasi dengan mengirimkan nama asli kamu di channel <#{VERIFICATION_CHANNEL_ID}>."
        )
    except discord.Forbidden:
        print(f"Gagal mengirim DM sambutan ke {member}.")

    # Kirim pesan sambutan ke channel 'Selamat Datang'
   welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
    if welcome_channel:
        embed = discord.Embed(
            title=f"🎉 Welcome, {member.display_name} ke {guild.name}! 🎉",
            description=(
            f"Asik, kamu udah resmi jadi bagian dari komunitas Prakom! 😎\n\n"
            f"Biar makin *smooth* di sini, ada 1 *step* terakhir nih:\n"
            f"**1.** 📖 **Cek Aturan Main:** Jangan lupa baca dan pahami <#{ANNOUNCEMENT_CHANNEL_ID}> ya, demi kenyamanan bareng.\n\n"
            f"Siap buat *ngobrol* & *explore*? Gas! Kami tunggu keseruannya! 🚀"
        ),
        color=discord.Color.teal() # Pilihan warna lain yang modern
    )
    await welcome_channel.send(embed=embed)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Ayo bangun komunitas yang aktif dan saling mendukung!")
        
        # Mengirim pesan sambutan ke channel 'Selamat Datang' tanpa menumpuk
        await welcome_channel.send(f"Selamat datang {member.mention}!", embed=embed)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id in inactive_tickets:
        inactive_tickets[message.channel.id] = datetime.now(WIB)

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

    user_xp[message.author.id] += 5
    level = user_level[message.author.id]
    next_level_xp = (level + 1) * 100
    if user_xp[message.author.id] >= next_level_xp:
        user_level[message.author.id] += 1
        await message.channel.send(
            f"🎉 {message.author.mention} naik level ke {user_level[message.author.id]}! Keep it up!"
        )

    if message.guild and message.guild.id == GUILD_ID and message.channel.id == VERIFICATION_CHANNEL_ID:
        member = message.author
        guild = message.guild
        nama_baru = message.content.strip()

        try:
            await member.edit(nick=nama_baru)
        except:
            await message.channel.send("❌ Tidak bisa ganti nickname.", delete_after=10)
            return

        role_unverified = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE_NAME)
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
        return 

    if role_to_add:
        try:
            await user.add_roles(role_to_add)
            await reaction.message.channel.send(f"{user.mention} sudah memilih {role_to_add.name}")

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


# SLASH COMMANDS

## Perintah Umum

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
            dt = datetime.fromisoformat(waktu)
            dt = dt.replace(tzinfo=WIB)
            
            if dt < now:
                await interaction.followup.send("Waktu reminder harus di masa depan.", ephemeral=True)
                return
            
            role_reminders.append({
                "tipe": "sekali_channel",
                "waktu": dt,
                "pesan": pesan,
                "channel_id": interaction.channel.id,
                "creator_id": interaction.user.id
            })
            save_role_reminders() 
            await interaction.followup.send(f"Reminder sekali set untuk **{dt.strftime('%d %b %Y %H:%M WIB')}** di channel ini.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Format waktu sekali harus YYYY-MM-DDTHH:MM (contoh: 2025-05-26T14:30).", ephemeral=True)

    elif tipe == "publik":
        channel = interaction.channel
        try:
            datetime.strptime(waktu, "%H:%M") 
            public_reminders[channel.id].append((waktu, pesan))
            await interaction.followup.send(f"Reminder publik set di channel ini pada jam **{waktu} WIB**.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Format waktu publik harus HH:MM (24 jam, contoh: 14:30).", ephemeral=True)

    else:
        await interaction.followup.send("Tipe reminder tidak valid. Gunakan 'sekali' atau 'publik'.", ephemeral=True)

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
    await interaction.response.send_message(tri_krama_text)

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

@tree.command(name="ping", description="Cek respons bot", guild=discord.Object(id=GUILD_ID))
async def ping(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(f"Pong! Latensi: {round(bot.latency * 1000)} ms")



## Perintah Moderasi (Admin Only)

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

@tree.command(name="warn", description="Berikan peringatan kepada pengguna.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    member="Anggota yang akan diberi peringatan",
    reason="Alasan peringatan"
)
@is_admin_prakom()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    await interaction.response.defer(ephemeral=True)
    
    member_id_str = str(member.id)
    if member_id_str not in warn_data:
        warn_data[member_id_str] = []
    
    warn_info = {
        "moderator_id": interaction.user.id,
        "moderator_name": str(interaction.user),
        "reason": reason,
        "timestamp": datetime.now(WIB).isoformat()
    }
    warn_data[member_id_str].append(warn_info)
    save_warn_data()

    log_channel = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"⚠️ **Peringatan:** {member.mention} telah diberi peringatan oleh {interaction.user.mention}. Alasan: **{reason}**")

    try:
        await member.send(f"Anda telah diberi peringatan di **{interaction.guild.name}** dengan alasan: **{reason}**")
    except discord.Forbidden:
        pass 

    await interaction.followup.send(f"✅ {member.mention} berhasil diberi peringatan. Ini adalah peringatan ke-{len(warn_data[member_id_str])} nya.", ephemeral=True)


@tree.command(name="warnings", description="Lihat riwayat peringatan pengguna.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Anggota yang ingin dilihat riwayat peringatannya")
@is_admin_prakom()
async def warnings(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)

    member_id_str = str(member.id)
    if member_id_str not in warn_data or not warn_data[member_id_str]:
        await interaction.followup.send(f"❗ {member.mention} tidak memiliki riwayat peringatan.", ephemeral=True)
        return

    warnings_list = warn_data[member_id_str]
    embed = discord.Embed(
        title=f"Riwayat Peringatan untuk {member.display_name}",
        color=discord.Color.orange()
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    for i, warn_info in enumerate(warnings_list):
        timestamp_wib = datetime.fromisoformat(warn_info["timestamp"]).astimezone(WIB)
        embed.add_field(
            name=f"Peringatan #{i+1}",
            value=(
                f"**Oleh:** {warn_info['moderator_name']}\n"
                f"**Alasan:** {warn_info['reason']}\n"
                f"**Waktu:** {timestamp_wib.strftime('%d %b %Y %H:%M WIB')}"
            ),
            inline=False
        )
    
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="clear_warnings", description="Hapus semua riwayat peringatan pengguna.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Anggota yang riwayat peringatannya akan dihapus")
@is_admin_prakom()
async def clear_warnings(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    member_id_str = str(member.id)
    if member_id_str in warn_data:
        warn_data.pop(member_id_str)
        save_warn_data()
        log_channel = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"🧹 **Log Peringatan Dihapus:** Riwayat peringatan {member.mention} telah dihapus oleh {interaction.user.mention}.")
        await interaction.followup.send(f"✅ Riwayat peringatan {member.mention} telah dihapus.", ephemeral=True)
    else:
        await interaction.followup.send(f"❗ {member.mention} tidak memiliki riwayat peringatan untuk dihapus.", ephemeral=True)

@tree.command(name="kick", description="Keluarkan pengguna dari server.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    member="Anggota yang akan dikeluarkan",
    reason="Alasan kick"
)
@is_admin_prakom()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Tidak ada alasan"):
    await interaction.response.defer(ephemeral=True)
    
    if member.id == interaction.user.id:
        await interaction.followup.send("❌ Kamu tidak bisa mengeluarkan diri sendiri.", ephemeral=True)
        return
    if member.top_role.position >= interaction.user.top_role.position:
        await interaction.followup.send("❌ Kamu tidak bisa mengeluarkan anggota dengan role yang sama atau lebih tinggi.", ephemeral=True)
        return

    try:
        await member.kick(reason=reason)
        log_channel = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"👢 **Kick:** {member.mention} telah dikeluarkan oleh {interaction.user.mention}. Alasan: **{reason}**")
        await interaction.followup.send(f"✅ {member.mention} berhasil dikeluarkan. Alasan: {reason}", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Saya tidak memiliki izin untuk mengeluarkan anggota ini.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

@tree.command(name="ban", description="Larangan pengguna dari server.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    member="Anggota yang akan dilarang",
    reason="Alasan ban"
)
@is_admin_prakom()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Tidak ada alasan"):
    await interaction.response.defer(ephemeral=True)
    
    if member.id == interaction.user.id:
        await interaction.followup.send("❌ Kamu tidak bisa melarang diri sendiri.", ephemeral=True)
        return
    if member.top_role.position >= interaction.user.top_role.position:
        await interaction.followup.send("❌ Kamu tidak bisa melarang anggota dengan role yang sama atau lebih tinggi.", ephemeral=True)
        return

    try:
        await member.ban(reason=reason)
        log_channel = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"🚫 **Ban:** {member.mention} telah dilarang oleh {interaction.user.mention}. Alasan: **{reason}**")
        await interaction.followup.send(f"✅ {member.mention} berhasil dilarang. Alasan: {reason}", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Saya tidak memiliki izin untuk melarang anggota ini.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

@tree.command(name="unban", description="Batalkan larangan pengguna.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    user_id="ID pengguna yang akan dibatalkan larangannya",
    reason="Alasan unban"
)
@is_admin_prakom()
async def unban(interaction: discord.Interaction, user_id: str, reason: str = "Tidak ada alasan"):
    await interaction.response.defer(ephemeral=True)
    
    try:
        user_id_int = int(user_id) 
    except ValueError:
        await interaction.followup.send("❌ ID pengguna harus berupa angka.", ephemeral=True)
        return

    try:
        user = discord.Object(id=user_id_int) 
        await interaction.guild.unban(user, reason=reason)
        log_channel = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"✅ **Unban:** Pengguna dengan ID `{user_id}` telah dibatalkan larangannya oleh {interaction.user.mention}. Alasan: **{reason}**")
        await interaction.followup.send(f"✅ Pengguna dengan ID `{user_id}` berhasil dibatalkan larangannya. Alasan: {reason}", ephemeral=True)
    except discord.NotFound:
        await interaction.followup.send("❌ Pengguna dengan ID tersebut tidak ditemukan dalam daftar larangan.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Saya tidak memiliki izin untuk membatalkan larangan anggota ini.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)



## Command Manajemen Tiket

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
        except Exception as e:
            print(f"Gagal menutup tiket: {e}")
            await interaction.channel.send("❌ Gagal menutup tiket. Periksa izin bot.")
    else:
        await interaction.response.send_message("Command ini hanya bisa dipakai di channel tiket.", ephemeral=True)



## Command Pengumuman Admin

@tree.command(name="pengumuman", description="Kirim pengumuman ke channel tertentu", guild=discord.Object(id=GUILD_ID))
@is_admin_prakom()
async def pengumuman(interaction: discord.Interaction, pesan: str):
    await interaction.response.defer(ephemeral=True)
    channel = interaction.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        await channel.send(f"📢 Pengumuman dari Admin:\n\n{pesan}")
        await interaction.followup.send("Pengumuman terkirim.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Channel pengumuman tidak ditemukan.", ephemeral=True)


@tree.command(name="schedule_announcement", description="Jadwalkan pengumuman ke channel tertentu.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    channel="Channel untuk mengirim pengumuman",
    waktu="Waktu pengumuman (format YYYY-MM-DDTHH:MM, akan dianggap WIB)",
    pesan="Pesan pengumuman"
)
@is_admin_prakom()
async def schedule_announcement(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    waktu: str,
    pesan: str
):
    await interaction.response.defer(ephemeral=True)
    now = datetime.now(WIB)
    user_id = interaction.user.id

    try:
        announce_time_obj = datetime.fromisoformat(waktu)
        announce_time_obj = announce_time_obj.replace(tzinfo=WIB)
        
        if announce_time_obj <= now:
            await interaction.followup.send("Waktu pengumuman harus di masa depan (menggunakan WIB).", ephemeral=True)
            return
        
        role_reminders.append({
            "tipe": "scheduled_announcement",
            "waktu": announce_time_obj,
            "pesan": pesan,
            "channel_id": channel.id,
            "creator_id": user_id
        })
        save_role_reminders() 
        
        await interaction.followup.send(f"✅ Pengumuman terjadwal berhasil disimpan untuk **{announce_time_obj.strftime('%d %b %Y %H:%M WIB')}** di {channel.mention}.", ephemeral=True)

    except ValueError:
        await interaction.followup.send("❌ Format waktu harus YYYY-MM-DDTHH:MM (contoh: `2025-06-01T10:00`).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Terjadi kesalahan: {e}", ephemeral=True)
        print(f"Error di command /schedule_announcement: {e}")


## Command Pengingat Pribadi

@tree.command(name="remindme", description="Set pengingat pribadi yang akan dikirim via DM.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    waktu="Waktu pengingat (format YYYY-MM-DDTHH:MM, akan dianggap WIB)",
    pesan="Pesan pengingat"
)
async def remindme(interaction: discord.Interaction, waktu: str, pesan: str):
    await interaction.response.defer(ephemeral=True)
    now = datetime.now(WIB)
    user_id_str = str(interaction.user.id)

    try:
        remind_time_obj = datetime.fromisoformat(waktu)
        remind_time_obj = remind_time_obj.replace(tzinfo=WIB)
        
        if remind_time_obj <= now:
            await interaction.followup.send("Waktu pengingat harus di masa depan.", ephemeral=True)
            return
        
        if user_id_str not in private_reminders_data:
            private_reminders_data[user_id_str] = []
        
        private_reminders_data[user_id_str].append({
            "time": remind_time_obj,
            "message": pesan
        })
        save_private_reminders()
        await interaction.followup.send(f"✅ Pengingat pribadi berhasil disimpan untuk **{remind_time_obj.strftime('%d %b %Y %H:%M WIB')}**.", ephemeral=True)

    except ValueError:
        await interaction.followup.send("❌ Format waktu harus YYYY-MM-DDTHH:MM (contoh: `2025-06-01T10:00`).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Terjadi kesalahan: {e}", ephemeral=True)
        print(f"Error di command /remindme: {e}")

@tree.command(name="list_my_reminders", description="Lihat daftar pengingat pribadi kamu.", guild=discord.Object(id=GUILD_ID))
async def list_my_reminders(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id_str = str(interaction.user.id)

    if user_id_str not in private_reminders_data or not private_reminders_data[user_id_str]:
        await interaction.followup.send("❗ Kamu tidak punya pengingat pribadi.", ephemeral=True)
        return

    reminders_list = private_reminders_data[user_id_str]
    embed = discord.Embed(
        title=f"Pengingat Pribadi untuk {interaction.user.display_name}",
        color=discord.Color.blue()
    )

    for i, rem_info in enumerate(reminders_list):
        timestamp_wib = rem_info["time"].astimezone(WIB)
        embed.add_field(
            name=f"Pengingat #{i+1}",
            value=(
                f"**Pesan:** {rem_info['message']}\n"
                f"**Waktu:** {timestamp_wib.strftime('%d %b %Y %H:%M WIB')}"
            ),
            inline=False
        )
    
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="remove_my_reminder", description="Hapus pengingat pribadi berdasarkan nomor.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    nomor_pengingat="Nomor pengingat yang ingin dihapus (dari /list_my_reminders)"
)
async def remove_my_reminder(interaction: discord.Interaction, nomor_pengingat: int):
    await interaction.response.defer(ephemeral=True)
    user_id_str = str(interaction.user.id)

    if user_id_str not in private_reminders_data or not private_reminders_data[user_id_str]:
        await interaction.followup.send("❗ Kamu tidak punya pengingat pribadi untuk dihapus.", ephemeral=True)
        return

    if not (1 <= nomor_pengingat <= len(private_reminders_data[user_id_str])):
        await interaction.followup.send("❌ Nomor pengingat tidak valid.", ephemeral=True)
        return
    
    removed_reminder = private_reminders_data[user_id_str].pop(nomor_pengingat - 1)
    save_private_reminders()
    await interaction.followup.send(f"✅ Pengingat pribadi **'{removed_reminder['message']}'** berhasil dihapus.", ephemeral=True)



## Command Pengingat Role (Admin Only)

@tree.command(name="reminder_role", description="Kirim pengingat ke role tertentu pada waktu spesifik (Admin Only).", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    role="Role yang akan di-mention",
    waktu="Waktu pengingat (format YYYY-MM-DDTHH:MM, akan dianggap WIB)",
    pesan="Pesan pengingat yang akan dikirim"
)
@is_admin_prakom()
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
        remind_time_obj = remind_time_obj.replace(tzinfo=WIB)
        
        if remind_time_obj <= now:
            await interaction.followup.send("Waktu pengingat harus di masa depan (menggunakan WIB).", ephemeral=True)
            return
        
        role_reminders.append({
            "tipe": "role",
            "waktu": remind_time_obj,
            "pesan": pesan,
            "role_id": role.id, 
            "channel_id": interaction.channel.id,
            "creator_id": user_id
        })
        save_role_reminders() 
        await interaction.followup.send(f"✅ Pengingat untuk **{role.name}** berhasil disimpan pada **{remind_time_obj.strftime('%d %b %Y %H:%M WIB')}** di channel ini.", ephemeral=True)

    except ValueError:
        await interaction.followup.send("❌ Format waktu harus YYYY-MM-DDTHH:MM (contoh: `2025-06-01T10:00`).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Terjadi kesalahan: {e}", ephemeral=True)
        print(f"Error di command /reminder_role: {e}")

@tree.command(name="list_reminder", description="Lihat daftar reminder yang kamu buat (publik dan role)", guild=discord.Object(id=GUILD_ID))
async def list_reminder(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    msg = ""

    current_channel_id = interaction.channel.id
    if current_channel_id in public_reminders and public_reminders[current_channel_id]:
        msg += "**Pengingat Publik di channel ini:**\n"
        for (waktu, pesan) in public_reminders[current_channel_id]:
            msg += f"  - Setiap hari jam {waktu}: {pesan}\n"
    else:
        msg += "**Pengingat Publik di channel ini:** Tidak ada\n"

    user_created_reminders = [
        r for r in role_reminders if r.get("creator_id") == user_id
    ]
    if user_created_reminders:
        msg += "\n**Pengingat Sekali, Role, atau Pengumuman Terjadwal yang kamu buat:**\n"
        for rem in user_created_reminders:
            waktu_str = rem['waktu'].strftime("%d %b %Y %H:%M WIB")
            if rem["tipe"] == "role":
                guild = interaction.guild
                fetched_role = guild.get_role(rem['role_id']) 
                role_name = fetched_role.name if fetched_role else "Role Tidak Ditemukan"
                msg += f"  - Untuk role **{role_name}** pada {waktu_str} di channel <#{rem['channel_id']}>: {rem['pesan']}\n"
            elif rem["tipe"] == "sekali_channel":
                msg += f"  - Sekali pada {waktu_str} di channel <#{rem['channel_id']}>: {rem['pesan']}\n"
            elif rem["tipe"] == "scheduled_announcement":
                 msg += f"  - Pengumuman Terjadwal pada {waktu_str} di channel <#{rem['channel_id']}>: {rem['pesan']}\n"
    else:
        msg += "\n**Pengingat Sekali, Role, atau Pengumuman Terjadwal yang kamu buat:** Tidak ada\n"

    await interaction.followup.send(msg, ephemeral=True)


@tree.command(name="remove_reminder", description="Hapus semua reminder publik atau role yang kamu buat.", guild=discord.Object(id=GUILD_ID))
async def remove_reminder(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    
    if interaction.channel.id in public_reminders:
        public_reminders.pop(interaction.channel.id, None) 

    global role_reminders
    role_reminders = [r for r in role_reminders if r.get("creator_id") != user_id]
    save_role_reminders() 

    await interaction.followup.send("✅ Semua pengingat publik di channel ini dan pengingat sekali/role/pengumuman terjadwal yang kamu buat sudah dihapus.", ephemeral=True)



## Sistem Polling

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

# TASKS BERULANG OTOMATIS

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
             
@tasks.loop(minutes=1)
async def public_reminder_task():
    await bot.wait_until_ready()
    now = datetime.now(WIB).strftime("%H:%M")

    reminders_to_send = [] 

    for channel_id, reminders in public_reminders.items():
        channel = bot.get_channel(channel_id)
        if not channel:
            continue
        
        for (time_str, message) in reminders:
            if time_str == now:
                reminders_to_send.append((channel, message))
    
    for channel, message in reminders_to_send:
        try:
            await channel.send(f"🔔 Pengingat Publik:\n{message}")
        except Exception as e:
            print(f"Gagal mengirim pengingat publik di channel {channel.name}: {e}")
            
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
                        guild = channel.guild 
                        role = guild.get_role(reminder["role_id"]) 
                        if role:
                            await channel.send(f"{role.mention} {message}")
                        else:
                            print(f"Role tidak ditemukan untuk reminder (ID: {reminder.get('role_id')}): {reminder}")
                    elif reminder["tipe"] == "sekali_channel":
                        await channel.send(f"⏰ Pengingat Sekali:\n{message}")
                    elif reminder["tipe"] == "scheduled_announcement":
                        await channel.send(f"📢 **PENGUMUMAN TERJADWAL**\n\n{message}")
                    else:
                        print(f"Tipe reminder tidak dikenal: {reminder['tipe']}")
                except Exception as e:
                    print(f"Gagal mengirim reminder: {e} di channel {channel.name}")
            
            to_remove_reminders.append(reminder)
    
    role_reminders = [r for r in role_reminders if r not in to_remove_reminders]
    if to_remove_reminders:
        save_role_reminders()

@tasks.loop(minutes=1)
async def check_private_reminders():
    await bot.wait_until_ready()
    global private_reminders_data
    now = datetime.now(WIB)
    
    users_to_update = set()

    for user_id_str, reminders in list(private_reminders_data.items()):
        user = bot.get_user(int(user_id_str))
        if not user:
            continue
        
        reminders_to_keep = []
        for reminder in reminders:
            remind_time = reminder["time"]
            if remind_time <= now:
                try:
                    await user.send(f"⏰ Pengingat Pribadi:\n{reminder['message']}")
                    users_to_update.add(user_id_str)
                except discord.Forbidden:
                    print(f"Gagal mengirim DM pengingat ke {user.display_name}.")
                except Exception as e:
                    print(f"Error saat mengirim DM pengingat ke {user.display_name}: {e}")
            else:
                reminders_to_keep.append(reminder)
        
        private_reminders_data[user_id_str] = reminders_to_keep
    
    if users_to_update:
        save_private_reminders()

@tasks.loop(minutes=30)
async def close_inactive_tickets():
    await bot.wait_until_ready()
    global inactive_tickets
    now = datetime.now(WIB)
    to_close = []
    for channel_id, last_active in inactive_tickets.items():
        elapsed = (now - last_active).total_seconds()
        if elapsed > 1800:
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

# ======= JALANKAN BOT =======
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ Environment variable DISCORD_TOKEN tidak ditemukan!")
    else:
        bot.run(TOKEN)
