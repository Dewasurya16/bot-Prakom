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
from discord.ui import View, Button, button # Import button dari discord.ui

# Tambahkan ini untuk memuat variabel lingkungan dari file .env
from dotenv import load_dotenv
load_dotenv()

# ======= KONFIGURASI =======
# Ganti GUILD_ID dengan ID server Discord Anda
GUILD_ID = 1375444915403751424
POST_CHANNEL_ID = 1375939507114741872
DAILY_ANNOUNCEMENT_CHANNEL_ID = 1375939507114741872
WELCOME_CHANNEL_ID = 1375824875838505020
VERIFICATION_CHANNEL_ID = 1375775766482128906
GENDER_CHANNEL_ID = 1375768360637436005
LOG_CHANNEL_ID = 1375886856188727357
LOGADMIN_CHANNEL_ID = 1376050661199708181
ANNOUNCEMENT_CHANNEL_ID = 1375821960637845564
ROLES_CHANNEL_ID = 1375444916519440468
MUTE_ROLE_NAME = "Muted"
ADMIN_PRAKOM_ROLE = "Admin Prakom"
TICKET_CATEGORY_NAME = "Tiket"
UNVERIFIED_ROLE_NAME = "Unverified"
ANGGOTA_ROLE_NAME = "Anggota" # Pastikan nama role ini sesuai di server Anda
PRAKOM_CANTIK_ROLE_NAME = "Prakom Cantik"
PRAKOM_GANTENG_ROLE_NAME = "Prakom Ganteng"

SPAM_THRESHOLD = 5
SPAM_INTERVAL = 10  # detik
MUTE_DURATION = 60  # detik

# File data untuk persistensi
WARN_DATA_FILE = "warn_data.json"
PRIVATE_REMINDER_DATA_FILE = "private_reminders.json"
ROLE_REMINDER_DATA_FILE = "role_reminders.json"
TICKET_DATA_FILE = "ticket_data.json" # File data untuk tiket

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
inactive_tickets = {} # Dictionary untuk melacak aktivitas tiket
active_tickets = {} # {channel_id: {"owner_id": user_id, "claimed_by": admin_id (opsional)}}

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
                role_reminders.append(rem)
    else:
        role_reminders = []

def save_role_reminders():
    data_to_save = []
    for rem in role_reminders:
        temp_rem = rem.copy()
        if "waktu" in temp_rem and isinstance(temp_rem["waktu"], datetime):
            temp_rem["waktu"] = temp_rem["waktu"].isoformat()
        data_to_save.append(temp_rem)
    with open(ROLE_REMINDER_DATA_FILE, 'w') as f:
        json.dump(data_to_save, f, indent=4)

def load_ticket_data():
    global active_tickets
    if os.path.exists(TICKET_DATA_FILE):
        with open(TICKET_DATA_FILE, 'r') as f:
            data = json.load(f)
            active_tickets = {
                int(channel_id): ticket_info for channel_id, ticket_info in data.items()
            }
            # Re-populate inactive_tickets based on loaded active_tickets
            for channel_id, ticket_info in active_tickets.items():
                inactive_tickets[channel_id] = datetime.now(WIB) # Set waktu aktif terbaru saat bot restart
    else:
        active_tickets = {}

def save_ticket_data():
    with open(TICKET_DATA_FILE, 'w') as f:
        json.dump(active_tickets, f, indent=4)

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
        return None, "❗ Kamu sudah punya tiket terbuka. Silakan gunakan tiket yang sudah ada."

    category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
    if not category:
        try:
            category = await guild.create_category(TICKET_CATEGORY_NAME)
        except discord.Forbidden:
            return None, "❌ Bot tidak memiliki izin untuk membuat kategori tiket."

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }

    admin_role = discord.utils.get(guild.roles, name=ADMIN_PRAKOM_ROLE)
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    try:
        channel = await guild.create_text_channel(
            f"tiket-{user.name.lower().replace(' ', '-')}",
            category=category,
            overwrites=overwrites)
    except discord.Forbidden:
        return None, "❌ Bot tidak memiliki izin untuk membuat channel tiket."
    except Exception as e:
        return None, f"❌ Terjadi kesalahan saat membuat channel: {e}"

    active_tickets[channel.id] = {"owner_id": user.id, "claimed_by": None}
    save_ticket_data()

    inactive_tickets[channel.id] = datetime.now(WIB)
    return channel, None

# ======= VIEWS (Tombol Interaktif) =======
class TicketButtons(View):
    def __init__(self, owner: discord.Member, ticket_channel_id: int):
        super().__init__(timeout=None) # Timeout=None agar view tetap aktif
        self.owner = owner
        self.ticket_channel_id = ticket_channel_id

    @button(label="Tutup Tiket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket_callback(self, interaction: discord.Interaction, button: button):
        # Hanya pemilik tiket atau Admin Prakom yang bisa menutup
        admin_role = discord.utils.get(interaction.guild.roles, name=ADMIN_PRAKOM_ROLE)
        if interaction.user.id == self.owner.id or (admin_role and admin_role in interaction.user.roles):
            channel = bot.get_channel(self.ticket_channel_id)
            if not channel:
                await interaction.response.send_message("❌ Channel tiket tidak ditemukan.", ephemeral=True)
                return

            await interaction.response.send_message("Tiket akan ditutup dalam 5 detik...", ephemeral=True)
            await asyncio.sleep(5)
            try:
                if channel.id in active_tickets:
                    del active_tickets[channel.id]
                    save_ticket_data()
                if channel.id in inactive_tickets:
                    del inactive_tickets[channel.id]

                log_admin_channel = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
                if log_admin_channel:
                    await log_admin_channel.send(f"🔒 **Tiket Ditutup:** Tiket `{channel.name}` (dibuat oleh <@{self.owner.id}>) telah ditutup oleh {interaction.user.mention}.")

                await channel.delete()
            except discord.Forbidden:
                await interaction.channel.send("❌ Gagal menutup tiket. Bot tidak memiliki izin.", ephemeral=True)
            except Exception as e:
                print(f"Gagal menutup tiket: {e}")
                await interaction.channel.send(f"❌ Terjadi kesalahan saat menutup tiket: {e}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Kamu tidak punya izin untuk menutup tiket ini.", ephemeral=True)

    @button(label="Klaim Tiket", style=discord.ButtonStyle.blurple, custom_id="claim_ticket")
    async def claim_ticket_callback(self, interaction: discord.Interaction, button: button):
        admin_role = discord.utils.get(interaction.guild.roles, name=ADMIN_PRAKOM_ROLE)
        if not (admin_role and admin_role in interaction.user.roles):
            await interaction.response.send_message("❌ Kamu tidak punya izin untuk mengklaim tiket ini.", ephemeral=True)
            return

        channel = bot.get_channel(self.ticket_channel_id)
        if not channel:
            await interaction.response.send_message("❌ Channel tiket tidak ditemukan.", ephemeral=True)
            return

        if channel.id in active_tickets:
            if active_tickets[channel.id]["claimed_by"]:
                claimed_by_user = bot.get_user(active_tickets[channel.id]["claimed_by"])
                await interaction.response.send_message(
                    f"❗ Tiket ini sudah diklaim oleh {claimed_by_user.mention if claimed_by_user else 'admin lain'}."
                    f" Jika kamu ingin mengambil alih, silakan koordinasi dengan admin yang mengklaim.",
                    ephemeral=True
                )
                return
            else:
                active_tickets[channel.id]["claimed_by"] = interaction.user.id
                save_ticket_data()

                # Tambahkan izin baca/tulis untuk admin yang mengklaim
                await channel.set_permissions(interaction.user, read_messages=True, send_messages=True)

                await interaction.response.send_message(f"✅ Tiket ini sekarang diklaim oleh {interaction.user.mention}. Silakan bantu pengguna ini.", ephemeral=False)

                log_admin_channel = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
                if log_admin_channel:
                    await log_admin_channel.send(f"➡️ **Tiket Diklaim:** Tiket `{channel.name}` (dibuat oleh <@{self.owner.id}>) telah diklaim oleh {interaction.user.mention}.")

                # Nonaktifkan tombol klaim setelah tiket diklaim
                button.disabled = True
                await interaction.message.edit(view=self)
        else:
            await interaction.response.send_message("❗ Data tiket ini tidak ditemukan, mungkin sudah ditutup.", ephemeral=True)


# ======= EVENTS =======
@bot.event
async def on_ready():
    print(f"✅ Bot aktif sebagai {bot.user}")
    load_warn_data()
    load_private_reminders()
    load_role_reminders()
    load_ticket_data()

    # Tambahkan kembali persistent views untuk tombol tiket yang ada
    guild = bot.get_guild(GUILD_ID)
    if guild:
        for channel_id, ticket_info in active_tickets.items():
            channel = guild.get_channel(channel_id)
            if channel and ticket_info.get("owner_id"):
                owner = guild.get_member(ticket_info["owner_id"])
                if owner:
                    view = TicketButtons(owner, channel.id)
                    # Jika tiket sudah diklaim, nonaktifkan tombol klaim di view awal
                    if ticket_info.get("claimed_by"):
                        for item in view.children:
                            if item.custom_id == "claim_ticket":
                                item.disabled = True
                                break
                    # Kirim pesan dengan tombol agar interaksi aktif kembali
                    try:
                        # Mencoba mencari pesan bot terakhir untuk diedit, jika tidak ada, kirim baru
                        history = [msg async for msg in channel.history(limit=50) if msg.author == bot.user and msg.components]
                        if history:
                            await history[0].edit(view=view)
                            print(f"Updated view in existing ticket channel {channel.name}")
                        else:
                            embed = discord.Embed(
                                title="Tiket Bantuan (Aktif Kembali)",
                                description=f"Halo <@{ticket_info['owner_id']}>! Tiket Anda aktif kembali.\n\n"
                                            f"Seorang admin atau moderator akan segera membantu Anda.\n"
                                            f"Gunakan tombol di bawah untuk mengelola tiket ini.",
                                color=discord.Color.green()
                            )
                            await channel.send(embed=embed, view=view)
                            print(f"Sent new view in existing ticket channel {channel.name}")
                    except discord.Forbidden:
                        print(f"Bot tidak memiliki izin send_messages/edit_messages di channel {channel.name} ({channel.id})")
                else:
                    print(f"Owner tiket {channel.name} ({ticket_info['owner_id']}) tidak ditemukan di guild, menghapus tiket dari data.")
                    del active_tickets[channel.id]
                    save_ticket_data()
            else:
                print(f"Channel tiket {channel_id} tidak ditemukan atau owner ID tidak ada, menghapus tiket dari data.")
                if channel_id in active_tickets:
                    del active_tickets[channel_id]
                    save_ticket_data()


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
            title=f"Halo {member.display_name}! Selamat Datang di {guild.name} 👋",
            description=(
                f"Selamat datang di komunitas Prakom! Kami senang kamu sudah diverifikasi dan siap bergabung. 🎉\n\n"
                f"Untuk memastikan pengalaman yang menyenangkan bagi semua, mohon perhatikan satu hal ini:\n"
                f"1. **Pahami Aturan:** Pastikan kamu membaca dan memahami <#{ROLES_CHANNEL_ID}> agar kita semua bisa berinteraksi dengan nyaman dan positif.\n\n"
                f"Kami tak sabar melihat kontribusimu Untuk Kejaksaan Republik Indonesia!"
            ),
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Ayo bangun komunitas yang aktif dan saling mendukung!")

        await welcome_channel.send(f"Selamat datang {member.mention}!", embed=embed)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Update inactive_tickets for active tickets
    if message.channel.id in active_tickets:
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

    # XP System
    user_xp[message.author.id] += 5
    level = user_level[message.author.id]
    next_level_xp = (level + 1) * 100
    if user_xp[message.author.id] >= next_level_xp:
        user_level[message.author.id] += 1
        await message.channel.send(
            f"🎉 {message.author.mention} naik level ke {user_level[message.author.id]}! Keep it up!"
        )

    # Verification Logic
    if message.guild and message.guild.id == GUILD_ID and message.channel.id == VERIFICATION_CHANNEL_ID:
        member = message.author
        guild = message.guild
        nama_baru = message.content.strip()

        try:
            await member.edit(nick=nama_baru)
        except Exception as e:
            await message.channel.send(f"❌ Tidak bisa ganti nickname: {e}", delete_after=10)
            return

        role_unverified = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE_NAME)
        role_anggota = discord.utils.get(guild.roles, name=ANGGOTA_ROLE_NAME)

        try:
            if role_unverified and role_unverified in member.roles:
                await member.remove_roles(role_unverified)
            if role_anggota and role_anggota not in member.roles:
                await member.add_roles(role_anggota)
        except Exception as e:
            await message.channel.send(f"❌ Tidak bisa mengatur role: {e}", delete_after=10)
            return

        channel_gender = guild.get_channel(GENDER_CHANNEL_ID)
        if channel_gender:
            pesan = await channel_gender.send(
                f"{member.mention}, pilih jenis kelamin dengan reaksi berikut:\n👩 = {PRAKOM_CANTIK_ROLE_NAME}\n👨 = {PRAKOM_GANTENG_ROLE_NAME}"
            )
            await pesan.add_reaction("👩")
            await pesan.add_reaction("👨")

        try:
            await member.send(
                f"✅ Verifikasi berhasil. Nickname kamu: **{nama_baru}**. Sekarang silakan pilih gender di channel yang disebutkan."
            )
        except discord.Forbidden:
            pass # DM tertutup

        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(
                f"🟢 {member} verifikasi dan ganti nama jadi **{nama_baru}**.")

        await asyncio.sleep(5) # Beri waktu untuk bot mengirim pesan gender
        try:
            await message.delete() # Hapus pesan verifikasi pengguna
        except:
            pass # Pesan sudah terhapus atau bot tidak punya izin

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
        role_to_add = discord.utils.get(guild.roles, name=PRAKOM_CANTIK_ROLE_NAME)
    elif reaction.emoji == "👨":
        role_to_add = discord.utils.get(guild.roles, name=PRAKOM_GANTENG_ROLE_NAME)
    else:
        return # Reaksi tidak relevan

    if role_to_add:
        try:
            await user.add_roles(role_to_add)
            await reaction.message.channel.send(f"{user.mention} sudah memilih **{role_to_add.name}**.", delete_after=10)

            # Hapus role Anggota setelah memilih gender
            role_anggota = discord.utils.get(guild.roles, name=ANGGOTA_ROLE_NAME)
            if role_anggota and role_anggota in user.roles:
                await user.remove_roles(role_anggota)
                print(f"Role '{ANGGOTA_ROLE_NAME}' dihapus dari {user.display_name}")

            # Hapus reaksi pengguna agar bisa memilih lagi jika salah
            await reaction.remove(user)

        except discord.Forbidden:
            print(f"Bot tidak memiliki izin untuk mengelola role untuk {user}.")
            await reaction.message.channel.send(f"❌ Saya tidak memiliki izin untuk mengatur role Anda.", delete_after=10)
        except Exception as e:
            print(f"Terjadi kesalahan saat mengatur role untuk {user}: {e}")
            await reaction.message.channel.send(f"❌ Terjadi kesalahan saat mengatur role Anda.", delete_after=10)

# ======= BACKGROUND TASKS =======

@tasks.loop(minutes=30) # Cek setiap 30 menit
async def close_inactive_tickets():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    current_time = datetime.now(WIB)
    channels_to_close = []
    log_admin_channel = guild.get_channel(LOGADMIN_CHANNEL_ID)

    for channel_id, last_activity_time in list(inactive_tickets.items()):
        # Cek jika tiket tidak aktif selama 3 jam (3 * 3600 detik)
        if (current_time - last_activity_time).total_seconds() > (3 * 3600):
            channel = guild.get_channel(channel_id)
            # Pastikan channel ada dan berada di kategori tiket
            if channel and channel.category and channel.category.name == TICKET_CATEGORY_NAME:
                channels_to_close.append(channel)

    for channel in channels_to_close:
        try:
            owner_id = active_tickets.get(channel.id, {}).get("owner_id")
            owner_mention = f"<@{owner_id}>" if owner_id else "pengguna tidak diketahui"
            await channel.send(f"Tiket ini otomatis ditutup karena tidak ada aktivitas selama 3 jam.")
            if log_admin_channel:
                await log_admin_channel.send(f"🕒 **Tiket Otomatis Ditutup:** Tiket `{channel.name}` (dibuat oleh {owner_mention}) ditutup karena tidak aktif selama 3 jam.")

            # Hapus dari active_tickets dan inactive_tickets
            if channel.id in active_tickets:
                del active_tickets[channel.id]
                save_ticket_data()
            if channel.id in inactive_tickets:
                del inactive_tickets[channel.id]

            await asyncio.sleep(5) # Beri waktu pesan terkirim
            await channel.delete()
        except discord.Forbidden:
            print(f"Bot tidak memiliki izin untuk menutup channel {channel.name} secara otomatis.")
        except Exception as e:
            print(f"Gagal menutup tiket otomatis {channel.name}: {e}")

@tasks.loop(minutes=1)
async def public_reminder_task():
    now_hour_minute = datetime.now(WIB).strftime("%H:%M")
    for channel_id, reminders_list in list(public_reminders.items()):
        channel = bot.get_channel(channel_id)
        if channel:
            # Iterasi salinan list untuk menghindari masalah saat menghapus elemen
            for reminder_time, message in list(reminders_list):
                if now_hour_minute == reminder_time:
                    try:
                        await channel.send(f"🔔 **Pengingat Publik:** {message}")
                    except discord.Forbidden:
                        print(f"Bot tidak memiliki izin kirim pesan di channel {channel.name} untuk pengingat publik.")
                # Jika Anda ingin reminder publik berulang setiap hari, jangan hapus di sini.
                # Jika hanya ingin sekali, Anda bisa menambahkan logika penghapusan.

@tasks.loop(minutes=1)
async def check_private_reminders():
    now = datetime.now(WIB)
    reminders_to_remove_private = []

    # Check for private reminders
    for user_id_str, reminders in list(private_reminders_data.items()):
        user = bot.get_user(int(user_id_str))
        if user:
            for rem in list(reminders): # Iterasi salinan untuk modifikasi saat loop
                if rem["time"] <= now:
                    try:
                        await user.send(f"🔔 **Pengingat Pribadi:** {rem['message']}")
                    except discord.Forbidden:
                        print(f"Gagal mengirim DM ke {user.name} ({user_id_str}) untuk pengingat pribadi.")
                    reminders.remove(rem) # Hapus setelah terkirim
        if not reminders:
            reminders_to_remove_private.append(user_id_str)

    for user_id_str in reminders_to_remove_private:
        del private_reminders_data[user_id_str]
    save_private_reminders()

@tasks.loop(minutes=1)
async def check_role_reminders(): # Menggabungkan scheduled_announcement dan sekali_channel
    now = datetime.now(WIB)
    reminders_to_remove_role = []

    for i, rem in enumerate(role_reminders):
        if rem["waktu"] <= now:
            if rem.get("tipe") == "sekali_channel":
                channel = bot.get_channel(rem["channel_id"])
                if channel:
                    try:
                        await channel.send(f"🔔 **Pengingat:** {rem['pesan']}")
                    except discord.Forbidden:
                        print(f"Gagal mengirim pengingat ke channel {channel.name}.")
                reminders_to_remove_role.append(i)
            elif rem.get("tipe") == "scheduled_announcement":
                channel = bot.get_channel(rem["channel_id"])
                if channel:
                    try:
                        await channel.send(f"📢 **Pengumuman Terjadwal:**\n\n{rem['pesan']}")
                    except discord.Forbidden:
                        print(f"Gagal mengirim pengumuman terjadwal ke channel {channel.name}.")
                reminders_to_remove_role.append(i)

    # Hapus reminder secara terbalik untuk menghindari masalah indeks
    for i in sorted(reminders_to_remove_role, reverse=True):
        del role_reminders[i]
    save_role_reminders()


@tasks.loop(time=time(hour=7, minute=0, tzinfo=WIB)) # Setiap jam 7 pagi WIB
async def daily_reminder_task():
    channel = bot.get_channel(DAILY_ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        quote = random.choice(DAILY_QUOTES)
        announcement = DAILY_ANNOUNCEMENT_TEMPLATE + f"\n\n✨ Motivasi hari ini: \"{quote}\""
        try:
            await channel.send(announcement)
        except discord.Forbidden:
            print(f"Bot tidak memiliki izin kirim pesan di channel pengumuman harian {channel.name}.")
    else:
        print(f"Channel pengumuman harian dengan ID {DAILY_ANNOUNCEMENT_CHANNEL_ID} tidak ditemukan.")


# ======= SLASH COMMANDS =======

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

            # Menggunakan role_reminders untuk menyimpan reminder sekali_channel
            role_reminders.append({
                "tipe": "sekali_channel",
                "waktu": dt,
                "pesan": pesan,
                "channel_id": interaction.channel.id,
                "creator_id": interaction.user.id
            })
            save_role_reminders()
            await interaction.followup.send(f"✅ Reminder sekali set untuk **{dt.strftime('%d %b %Y %H:%M WIB')}** di channel ini.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Format waktu sekali harus YYYY-MM-DDTHH:MM (contoh: 2025-05-26T14:30).", ephemeral=True)

    elif tipe == "publik":
        channel = interaction.channel
        try:
            # Hanya validasi format waktu, tidak perlu dibandingkan dengan now
            datetime.strptime(waktu, "%H:%M")
            public_reminders[channel.id].append((waktu, pesan))
            await interaction.followup.send(f"✅ Reminder publik set di channel ini pada jam **{waktu} WIB**.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Format waktu publik harus HH:MM (24 jam, contoh: 14:30).", ephemeral=True)

    else:
        await interaction.followup.send("❌ Tipe reminder tidak valid. Gunakan 'sekali' atau 'publik'.", ephemeral=True)

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
        pass # DM tertutup

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
        view = TicketButtons(interaction.user, channel.id)
        embed = discord.Embed(
            title="Tiket Bantuan Baru",
            description=f"Halo {interaction.user.mention}! Selamat datang di tiket bantuan Anda.\n\n"
                        f"Seorang admin atau moderator akan segera membantu Anda.\n"
                        f"Mohon jelaskan masalah atau pertanyaan Anda di sini.\n\n"
                        f"Gunakan tombol di bawah untuk mengelola tiket ini.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Terima kasih atas kesabaran Anda.")
        try:
            await channel.send(f"{interaction.user.mention}", embed=embed, view=view)
        except discord.Forbidden:
            await interaction.followup.send("❌ Channel tiket dibuat, tetapi bot tidak memiliki izin untuk mengirim pesan di sana. Pastikan izin diatur dengan benar.", ephemeral=True)
            print(f"Bot tidak memiliki izin kirim pesan di tiket {channel.name}.")
            # Lanjutkan dengan pesan sukses ke pengguna, karena channel tetap dibuat
            await interaction.followup.send(f"✅ Channel tiket berhasil dibuat: {channel.mention}. Silakan jelaskan masalah Anda di sana.", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Channel tiket berhasil dibuat: {channel.mention}", ephemeral=True)

        log_admin_channel = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin_channel:
            await log_admin_channel.send(f"🆕 **Tiket Baru:** Tiket `{channel.name}` telah dibuat oleh {interaction.user.mention}. {channel.mention}")


## Command Pengumuman Admin

@tree.command(name="pengumuman", description="Kirim pengumuman ke channel tertentu", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(pesan="Pesan pengumuman")
@is_admin_prakom()
async def pengumuman(interaction: discord.Interaction, pesan: str):
    await interaction.response.defer(ephemeral=True)
    channel = interaction.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        try:
            await channel.send(f"📢 Pengumuman dari Admin:\n\n{pesan}")
            await interaction.followup.send("✅ Pengumuman terkirim.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Saya tidak memiliki izin untuk mengirim pesan di channel pengumuman.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Channel pengumuman tidak ditemukan. Pastikan ID channel diatur dengan benar.", ephemeral=True)


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
            await interaction.followup.send("❌ Waktu pengumuman harus di masa depan (menggunakan WIB).", ephemeral=True)
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
        await interaction.followup.send("❌ Format waktu harus YYYY-MM-DDTHH:MM (contoh: 2025-05-26T14:30).", ephemeral=True)

# ======= JALANKAN BOT =======
if __name__ == "__main__":
    # Mengambil token dari variabel lingkungan bernama DISCORD_TOKEN
    TOKEN = os.getenv("DISCORD_TOKEN")

    if not TOKEN:
        print("❌ ERROR: Variabel lingkungan 'DISCORD_TOKEN' tidak ditemukan.")
        print("Pastikan Anda telah mengatur variabel lingkungan DISCORD_TOKEN sebelum menjalankan bot.")
        exit(1) # Keluar dari program jika token tidak ditemukan
    else:
        bot.run(TOKEN)
