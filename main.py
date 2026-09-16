import os
import io
import json
import random
import asyncio
import uuid
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button, button, Modal, TextInput, Select
from dotenv import load_dotenv

# --- MEMUAT VARIABEL LINGKUNGAN DARI FILE .env ---
load_dotenv()

# ======= PALET WARNA RESMI & AESTHETIC KORPS ADHYAKSA =======
CLR_ADHYAKSA_GREEN = 0x0F5132  # Hijau resmi Kejaksaan RI
CLR_ADHYAKSA_GOLD  = 0xD4AF37  # Emas keagungan Adhyaksa
CLR_NAVY           = 0x1B365D  # Biru formal kepemerintahan
CLR_EMERALD        = 0x2ECC71  # Hijau sukses cerah
CLR_CRIMSON        = 0xE74C3C  # Merah bahaya / tutup
CLR_AMBER          = 0xF39C12  # Kuning peringatan
CLR_CYAN           = 0x00A8FF  # Biru muda modern
CLR_PURPLE         = 0x9B59B6  # Ungu elegan
CLR_DARK           = 0x23272A  # Dark mode elegan

# ======= KONFIGURASI SERVER & CHANNEL =======
GUILD_ID = int(os.getenv("GUILD_ID", 1375444915403751424))
POST_CHANNEL_ID = int(os.getenv("POST_CHANNEL_ID", 1375939507114741872))
DAILY_ANNOUNCEMENT_CHANNEL_ID = int(os.getenv("DAILY_ANNOUNCEMENT_CHANNEL_ID", 1375939507114741872))
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", 1375824875838505020))
VERIFICATION_CHANNEL_ID = int(os.getenv("VERIFICATION_CHANNEL_ID", 1375775766482128906))
GENDER_CHANNEL_ID = int(os.getenv("GENDER_CHANNEL_ID", 1375768360637436005))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", 1375886856188727357))
LOGADMIN_CHANNEL_ID = int(os.getenv("LOGADMIN_CHANNEL_ID", 1376050661199708181))
ANNOUNCEMENT_CHANNEL_ID = int(os.getenv("ANNOUNCEMENT_CHANNEL_ID", 1375821960637845564))
ROLES_CHANNEL_ID = int(os.getenv("ROLES_CHANNEL_ID", 1375444916519440468))

# Nama Role
MUTE_ROLE_NAME = os.getenv("MUTE_ROLE_NAME", "Muted")
ADMIN_PRAKOM_ROLE = os.getenv("ADMIN_PRAKOM_ROLE", "Admin Prakom")
TICKET_CATEGORY_NAME = os.getenv("TICKET_CATEGORY_NAME", "Tiket")
UNVERIFIED_ROLE_NAME = os.getenv("UNVERIFIED_ROLE_NAME", "Unverified")
ANGGOTA_ROLE_NAME = os.getenv("ANGGOTA_ROLE_NAME", "Anggota")
PRAKOM_CANTIK_ROLE_NAME = os.getenv("PRAKOM_CANTIK_ROLE_NAME", "Prakom Cantik")
PRAKOM_GANTENG_ROLE_NAME = os.getenv("PRAKOM_GANTENG_ROLE_NAME", "Prakom Ganteng")

# Pengaturan Moderasi & XP
SPAM_THRESHOLD = int(os.getenv("SPAM_THRESHOLD", 5))
SPAM_INTERVAL = int(os.getenv("SPAM_INTERVAL", 10))   # detik
MUTE_DURATION = int(os.getenv("MUTE_DURATION", 60))   # detik (untuk timeout spam)
XP_COOLDOWN = int(os.getenv("XP_COOLDOWN", 60))       # cooldown perolehan XP (detik)

# File Data Persisten
WARN_DATA_FILE = "warn_data.json"
PRIVATE_REMINDER_DATA_FILE = "private_reminders.json"
ROLE_REMINDER_DATA_FILE = "role_reminders.json"
TICKET_DATA_FILE = "ticket_data.json"
PUBLIC_REMINDER_DATA_FILE = "public_reminders.json"
LEVEL_DATA_FILE = "level_data.json"

# DEFINISI ZONA WAKTU WIB (UTC+7)
WIB = timezone(timedelta(hours=7))
BOT_START_TIME = datetime.now(WIB)

# --- PENGATURAN INTENTS ---
intents = discord.Intents.default()
intents.members = True          # Membaca member join & update member
intents.message_content = True  # Membaca isi pesan
intents.reactions = True        # Membaca reaksi

# ======= GLOBAL VARIABLES (IN-MEMORY CACHE) =======
user_messages = defaultdict(list)
inactive_tickets = {} # {channel_id: datetime}
active_tickets = {}   # {channel_id: {"owner_id": user_id, "claimed_by": admin_id (opsional)}}

warn_data = {}
private_reminders_data = {}
public_reminders_data = defaultdict(list)
role_reminders = []
level_data = {}

# ======= HELPER TIER JABATAN PRAKOM =======
def get_prakom_tier(level: int):
    """Menghasilkan gelar jenjang fungsional Prakom berdasarkan level XP."""
    if level >= 25:
        return "💎 Prakom Ahli Madya", "Senior Systems Architect"
    elif level >= 15:
        return "🥇 Prakom Ahli Muda", "Senior Software / Infra Engineer"
    elif level >= 10:
        return "🥈 Prakom Ahli Pertama", "Systems / Data Specialist"
    elif level >= 5:
        return "🥉 Prakom Terampil / Mahir", "Technical Support Specialist"
    else:
        return "🔰 Prakom Pemula", "Junior IT Personnel"

def create_progress_bar(current: int, total: int, length: int = 12) -> str:
    """Membuat progress bar unicode modern dengan style sleek block."""
    if total <= 0:
        total = 1
    percent = max(0.0, min(1.0, current / total))
    filled_length = int(length * percent)
    empty_length = length - filled_length
    bar = "▰" * filled_length + "▱" * empty_length
    return f"`[{bar}]` **{int(percent * 100)}%**"

# ======= FUNGSI PERSISTENSI DATA AMAN (ATOMIC WRITE) =======
def safe_save_json(filename: str, data: any):
    temp_file = f"{filename}.tmp"
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(temp_file, filename)
    except Exception as e:
        print(f"❌ Gagal menyimpan {filename}: {e}")
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

def safe_load_json(filename: str, default: any = None):
    if default is None:
        default = {}
    if not os.path.exists(filename):
        return default
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Gagal membaca {filename}: {e}")
        return default

def load_warn_data():
    global warn_data
    warn_data = safe_load_json(WARN_DATA_FILE, {})

def save_warn_data():
    safe_save_json(WARN_DATA_FILE, warn_data)

def load_private_reminders():
    global private_reminders_data
    raw = safe_load_json(PRIVATE_REMINDER_DATA_FILE, {})
    private_reminders_data = {}
    for uid, reminders in raw.items():
        parsed = []
        for rem in reminders:
            try:
                dt = datetime.fromisoformat(rem["time"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=WIB)
                parsed.append({
                    "id": rem.get("id", str(uuid.uuid4())[:8]),
                    "time": dt,
                    "message": rem["message"]
                })
            except Exception:
                pass
        private_reminders_data[uid] = parsed

def save_private_reminders():
    data_to_save = {
        uid: [
            {
                "id": rem.get("id", str(uuid.uuid4())[:8]),
                "time": rem["time"].isoformat() if isinstance(rem["time"], datetime) else rem["time"],
                "message": rem["message"]
            } for rem in reminders
        ] for uid, reminders in private_reminders_data.items()
    }
    safe_save_json(PRIVATE_REMINDER_DATA_FILE, data_to_save)

def load_public_reminders():
    global public_reminders_data
    raw = safe_load_json(PUBLIC_REMINDER_DATA_FILE, {})
    public_reminders_data = defaultdict(list)
    for cid, rem_list in raw.items():
        public_reminders_data[int(cid)] = rem_list

def save_public_reminders():
    data_to_save = {str(cid): rem_list for cid, rem_list in public_reminders_data.items()}
    safe_save_json(PUBLIC_REMINDER_DATA_FILE, data_to_save)

def load_role_reminders():
    global role_reminders
    raw = safe_load_json(ROLE_REMINDER_DATA_FILE, [])
    role_reminders = []
    for rem in raw:
        temp = rem.copy()
        if "waktu" in temp and isinstance(temp["waktu"], str):
            try:
                dt = datetime.fromisoformat(temp["waktu"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=WIB)
                temp["waktu"] = dt
            except Exception:
                pass
        if "id" not in temp:
            temp["id"] = str(uuid.uuid4())[:8]
        role_reminders.append(temp)

def save_role_reminders():
    data_to_save = []
    for rem in role_reminders:
        temp = rem.copy()
        if "waktu" in temp and isinstance(temp["waktu"], datetime):
            temp["waktu"] = temp["waktu"].isoformat()
        data_to_save.append(temp)
    safe_save_json(ROLE_REMINDER_DATA_FILE, data_to_save)

def load_ticket_data():
    global active_tickets, inactive_tickets
    raw = safe_load_json(TICKET_DATA_FILE, {})
    active_tickets = {int(k): v for k, v in raw.items()}
    now = datetime.now(WIB)
    for cid in active_tickets:
        inactive_tickets[cid] = now

def save_ticket_data():
    safe_save_json(TICKET_DATA_FILE, active_tickets)

def load_level_data():
    global level_data
    level_data = safe_load_json(LEVEL_DATA_FILE, {})

def save_level_data():
    safe_save_json(LEVEL_DATA_FILE, level_data)

# ======= KUTIPAN & TEMPLAT =======
DAILY_QUOTES = [
    "Satya Adhi Wicaksana: Bekerja dengan jujur, sempurna dalam tugas, dan bijaksana dalam setiap keputusan.",
    "Langkah kecil hari ini dalam mengelola sistem informasi adalah pondasi kokoh bagi penegakan hukum modern.",
    "Teknologi hanyalah alat, dedikasi dan integritas Insan Prakom adalah motor penggerak peradaban.",
    "Jangan menyerah saat menghadapi kendala teknis; setiap bug dan tantangan adalah guru terbaik.",
    "Fokus pada kemajuan dan transparansi pelayanan hukum berbasis digital di seluruh penjuru negeri.",
    "Setiap hari adalah kesempatan baru untuk memberikan karya terbaik bagi Kejaksaan Republik Indonesia.",
    "Jadilah pribadi yang berani berinovasi, membawa transformasi positif di era digitalisasi birokrasi.",
    "Kesuksesan sejati diraih dari ketekunan, dedikasi tanpa pamrih, dan kebersamaan tim yang solid."
]

# ======= FUNGSI BANTUAN & CHECK =======
def is_admin_prakom():
    async def predicate(interaction: discord.Interaction):
        if not interaction.guild:
            return False
        if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
            return True
        role = discord.utils.get(interaction.user.roles, name=ADMIN_PRAKOM_ROLE)
        if role:
            return True
        embed = discord.Embed(
            title="🚫 Akses Ditolak",
            description=(
                "Perintah ini hanya dapat dijalankan oleh **Administrator Server** atau "
                f"anggota yang memiliki role **{ADMIN_PRAKOM_ROLE}**."
            ),
            color=CLR_CRIMSON
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return False
    return app_commands.check(predicate)

async def generate_ticket_transcript(channel: discord.TextChannel) -> io.BytesIO:
    buffer = io.StringIO()
    buffer.write("╔" + "═" * 68 + "╗\n")
    buffer.write(f"║ TRANSKRIP RESMI TIKET BANTUAN TEKNIS PRAKOM{' ' * 24}║\n")
    buffer.write(f"║ Channel: #{channel.name:<58}║\n")
    buffer.write(f"║ Server : {channel.guild.name:<58}║\n")
    buffer.write(f"║ Waktu  : {datetime.now(WIB).strftime('%d %B %Y, %H:%M:%S WIB'):<58}║\n")
    buffer.write("╚" + "═" * 68 + "╝\n\n")

    messages = []
    async for msg in channel.history(limit=500, oldest_first=True):
        messages.append(msg)

    for msg in messages:
        ts = msg.created_at.astimezone(WIB).strftime('%Y-%m-%d %H:%M:%S')
        author = f"{msg.author.display_name} ({msg.author.name})"
        content = msg.clean_content or "[Lampiran/Media tanpa teks]"
        buffer.write(f"[{ts}] {author}:\n{content}\n")
        if msg.attachments:
            for att in msg.attachments:
                buffer.write(f"   📎 Lampiran: {att.filename} -> {att.url}\n")
        buffer.write("-" * 50 + "\n")

    buffer.seek(0)
    bytes_io = io.BytesIO(buffer.getvalue().encode('utf-8'))
    bytes_io.seek(0)
    return bytes_io

async def create_ticket_channel(guild: discord.Guild, user: discord.Member):
    safe_username = "".join(c for c in user.name.lower() if c.isalnum() or c in "-_")[:18]
    ticket_name = f"tiket-{safe_username}"

    existing_channel = discord.utils.get(guild.channels, name=ticket_name)
    if existing_channel:
        return None, "❗ Anda sudah memiliki tiket bantuan aktif yang belum ditutup. Silakan gunakan channel tiket tersebut."

    category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
    if not category:
        try:
            category = await guild.create_category(TICKET_CATEGORY_NAME)
        except discord.Forbidden:
            return None, "❌ Bot tidak memiliki izin untuk membuat kategori tiket baru."

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }

    admin_role = discord.utils.get(guild.roles, name=ADMIN_PRAKOM_ROLE)
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)

    try:
        channel = await guild.create_text_channel(
            name=ticket_name,
            category=category,
            overwrites=overwrites
        )
    except discord.Forbidden:
        return None, "❌ Bot tidak memiliki izin `Manage Channels` untuk membuat channel tiket."
    except Exception as e:
        return None, f"❌ Terjadi kesalahan teknis saat membuat channel: {e}"

    active_tickets[channel.id] = {"owner_id": user.id, "claimed_by": None}
    save_ticket_data()
    inactive_tickets[channel.id] = datetime.now(WIB)
    return channel, None

# ======= VIEWS & MODALS (PREMIUM DISCORD UI) =======

class VerificationModal(Modal, title="Formulir Verifikasi Anggota"):
    nama_lengkap = TextInput(
        label="Nama Lengkap & Gelar",
        placeholder="Contoh: Budi Santoso, S.Kom., M.T.I.",
        required=True,
        max_length=60
    )
    instansi = TextInput(
        label="Satker / Instansi & Jabatan",
        placeholder="Contoh: Kejari Tanjungpinang / Prakom Ahli Pertama",
        required=True,
        max_length=60
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user

        nama = self.nama_lengkap.value.strip()
        satker = self.instansi.value.strip()

        # Format nickname maksimal 32 karakter Discord
        new_nick = f"{nama} [{satker}]"
        if len(new_nick) > 32:
            new_nick = nama[:32]

        nick_success = True
        try:
            await member.edit(nick=new_nick)
        except Exception:
            nick_success = False

        role_unverified = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE_NAME)
        role_anggota = discord.utils.get(guild.roles, name=ANGGOTA_ROLE_NAME)

        try:
            if role_unverified and role_unverified in member.roles:
                await member.remove_roles(role_unverified)
            if role_anggota and role_anggota not in member.roles:
                await member.add_roles(role_anggota)
        except discord.Forbidden:
            await interaction.followup.send("❌ Bot tidak memiliki izin `Manage Roles` yang cukup. Hubungi Admin.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎉 Verifikasi Berhasil!",
            description=(
                f"Selamat bergabung di komunitas **Pranata Komputer Kejaksaan RI**, {member.mention}!\n\n"
                f"📛 **Nama Server:** `{new_nick}`\n"
                f"🏷️ **Status Role:** Diberikan role **{ANGGOTA_ROLE_NAME}**\n\n"
                f"👉 **Langkah Selanjutnya:**\n"
                f"Silakan kunjungi channel <#{GENDER_CHANNEL_ID}> untuk mengambil role identitas **Prakom Cantik** atau **Prakom Ganteng**."
            ),
            color=CLR_EMERALD,
            timestamp=datetime.now(WIB)
        )
        embed.set_footer(text="Kejaksaan Republik Indonesia • Satya Adhi Wicaksana")
        await interaction.followup.send(embed=embed, ephemeral=True)

        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="🟢 Anggota Terverifikasi",
                color=CLR_ADHYAKSA_GREEN,
                timestamp=datetime.now(WIB)
            )
            log_embed.set_thumbnail(url=member.display_avatar.url)
            log_embed.add_field(name="👤 Akun", value=f"{member.mention}\n`{member.id}`", inline=True)
            log_embed.add_field(name="📛 Nama & Gelar", value=f"**{nama}**", inline=True)
            log_embed.add_field(name="🏛️ Satker / Jabatan", value=f"**{satker}**", inline=False)
            log_embed.add_field(name="🏷️ Nickname Diterapkan", value=f"`{new_nick}`" if nick_success else "*Gagal diset (Hierarchy)*", inline=False)
            log_embed.set_footer(text="Sistem Verifikasi Otomatis Prakom")
            await log_channel.send(embed=log_embed)


class VerificationView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="Verifikasi Sekarang", style=discord.ButtonStyle.success, emoji="📝", custom_id="btn_verify_modal")
    async def verify_button_callback(self, interaction: discord.Interaction, btn: Button):
        role_anggota = discord.utils.get(interaction.guild.roles, name=ANGGOTA_ROLE_NAME)
        if role_anggota and role_anggota in interaction.user.roles:
            embed = discord.Embed(
                title="ℹ️ Sudah Terverifikasi",
                description="Akun Anda sudah terdaftar dan memiliki akses penuh sebagai **Anggota**.",
                color=CLR_CYAN
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.send_modal(VerificationModal())

    @button(label="Bantuan & Ketentuan", style=discord.ButtonStyle.secondary, emoji="❓", custom_id="btn_verify_help")
    async def verify_help_callback(self, interaction: discord.Interaction, btn: Button):
        embed = discord.Embed(
            title="💡 Panduan Verifikasi Identitas",
            description=(
                "**Mengapa verifikasi diperlukan?**\n"
                "Server ini adalah wadah komunikasi resmi Pranata Komputer di lingkungan Kejaksaan RI. "
                "Verifikasi memastikan seluruh interaksi berlangsung tertib, profesional, dan akuntabel.\n\n"
                "**Ketentuan Pengisian:**\n"
                "• **Nama Lengkap:** Sertakan gelar akademik (contoh: *Ahmad Dani, S.Kom.*)\n"
                "• **Satker:** Cantumkan Kejaksaan Negeri / Tinggi / Agung tempat Anda bertugas.\n\n"
                "Jika mengalami kendala, silakan gunakan perintah `/create_ticket` untuk bantuan teknis."
            ),
            color=CLR_ADHYAKSA_GOLD
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class GenderRoleView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="Prakom Cantik", style=discord.ButtonStyle.secondary, emoji="👩", custom_id="btn_gender_cantik")
    async def cantik_callback(self, interaction: discord.Interaction, btn: Button):
        await self.process_gender(interaction, PRAKOM_CANTIK_ROLE_NAME, PRAKOM_GANTENG_ROLE_NAME, "👩")

    @button(label="Prakom Ganteng", style=discord.ButtonStyle.primary, emoji="👨", custom_id="btn_gender_ganteng")
    async def ganteng_callback(self, interaction: discord.Interaction, btn: Button):
        await self.process_gender(interaction, PRAKOM_GANTENG_ROLE_NAME, PRAKOM_CANTIK_ROLE_NAME, "👨")

    async def process_gender(self, interaction: discord.Interaction, target_role_name: str, opposite_role_name: str, emoji: str):
        guild = interaction.guild
        member = interaction.user
        target_role = discord.utils.get(guild.roles, name=target_role_name)
        opposite_role = discord.utils.get(guild.roles, name=opposite_role_name)

        if not target_role:
            await interaction.response.send_message(f"❌ Role `{target_role_name}` belum dibuat di server.", ephemeral=True)
            return

        if target_role in member.roles:
            embed = discord.Embed(
                description=f"ℹ️ Anda saat ini sudah memiliki role **{emoji} {target_role_name}**.",
                color=CLR_CYAN
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            if opposite_role and opposite_role in member.roles:
                await member.remove_roles(opposite_role)
            await member.add_roles(target_role)

            embed = discord.Embed(
                title="✨ Role Berhasil Disematkan",
                description=f"Selamat! Anda kini telah memiliki role **{emoji} {target_role_name}**.",
                color=CLR_PURPLE if "Cantik" in target_role_name else CLR_NAVY
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot tidak memiliki izin untuk mengelola role Anda.", ephemeral=True)


class PersistentTicketButtons(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="Tutup Tiket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_btn_close")
    async def close_callback(self, interaction: discord.Interaction, btn: Button):
        channel = interaction.channel
        ticket_info = active_tickets.get(channel.id)

        admin_role = discord.utils.get(interaction.guild.roles, name=ADMIN_PRAKOM_ROLE)
        is_admin = (
            interaction.user.id == interaction.guild.owner_id or
            interaction.user.guild_permissions.administrator or
            (admin_role and admin_role in interaction.user.roles)
        )
        is_owner = (ticket_info and ticket_info.get("owner_id") == interaction.user.id)

        if not (is_admin or is_owner):
            await interaction.response.send_message("❌ Hanya pemilik tiket atau Admin Prakom yang dapat menutup tiket ini.", ephemeral=True)
            return

        closing_embed = discord.Embed(
            title="🔒 Menutup Tiket Bantuan",
            description="Tiket ini sedang diarsipkan. Seluruh log percakapan akan diekspor dan channel akan dihapus dalam 5 detik...",
            color=CLR_CRIMSON
        )
        await interaction.response.send_message(embed=closing_embed)
        await asyncio.sleep(5)

        transcript_bytes = None
        try:
            transcript_bytes = await generate_ticket_transcript(channel)
        except Exception as e:
            print(f"Gagal generate transcript: {e}")

        owner_id = ticket_info.get("owner_id") if ticket_info else None
        if channel.id in active_tickets:
            del active_tickets[channel.id]
            save_ticket_data()
        if channel.id in inactive_tickets:
            del inactive_tickets[channel.id]

        log_admin_channel = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin_channel:
            owner_mention = f"<@{owner_id}>" if owner_id else "Tidak Diketahui"
            embed = discord.Embed(
                title="📁 Arsip Tiket Bantuan Ditutup",
                color=CLR_DARK,
                timestamp=datetime.now(WIB)
            )
            embed.add_field(name="🏷️ Nama Tiket", value=f"`{channel.name}`", inline=True)
            embed.add_field(name="👤 Pembuat", value=owner_mention, inline=True)
            embed.add_field(name="🛡️ Ditutup Oleh", value=interaction.user.mention, inline=True)
            embed.set_footer(text="Transkrip percakapan terlampir di bawah")

            file = None
            if transcript_bytes:
                file = discord.File(transcript_bytes, filename=f"transkrip-{channel.name}.txt")
            await log_admin_channel.send(embed=embed, file=file)

        try:
            await channel.delete(reason=f"Tiket ditutup oleh {interaction.user.name}")
        except Exception as e:
            print(f"Gagal menghapus channel tiket: {e}")

    @button(label="Klaim Tiket", style=discord.ButtonStyle.primary, emoji="🙋", custom_id="ticket_btn_claim")
    async def claim_callback(self, interaction: discord.Interaction, btn: Button):
        admin_role = discord.utils.get(interaction.guild.roles, name=ADMIN_PRAKOM_ROLE)
        is_admin = (
            interaction.user.id == interaction.guild.owner_id or
            interaction.user.guild_permissions.administrator or
            (admin_role and admin_role in interaction.user.roles)
        )
        if not is_admin:
            await interaction.response.send_message("❌ Hanya Admin Prakom yang dapat mengklaim tiket.", ephemeral=True)
            return

        channel = interaction.channel
        if channel.id not in active_tickets:
            await interaction.response.send_message("❗ Data tiket tidak ditemukan atau sudah ditutup.", ephemeral=True)
            return

        current_claim = active_tickets[channel.id].get("claimed_by")
        if current_claim:
            claimed_user = interaction.guild.get_member(current_claim)
            mention_str = claimed_user.mention if claimed_user else f"<@{current_claim}>"
            await interaction.response.send_message(f"❗ Tiket ini sudah diklaim oleh {mention_str}.", ephemeral=True)
            return

        active_tickets[channel.id]["claimed_by"] = interaction.user.id
        save_ticket_data()

        try:
            await channel.set_permissions(interaction.user, read_messages=True, send_messages=True, attach_files=True)
        except Exception:
            pass

        claim_embed = discord.Embed(
            title="➡️ Tiket Telah Diklaim",
            description=f"Tiket ini sekarang sedang ditangani secara langsung oleh {interaction.user.mention}.",
            color=CLR_CYAN
        )
        await interaction.response.send_message(embed=claim_embed)

        log_admin_channel = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin_channel:
            await log_admin_channel.send(f"➡️ **Tiket Diklaim:** Tiket `{channel.name}` telah diklaim oleh {interaction.user.mention}.")


# ======= VIEW MENU HELP DINAMIS (SELECT DROPDOWN) =======
class HelpSelect(Select):
    def __init__(self, is_admin: bool):
        options = [
            discord.SelectOption(
                label="Ringkasan & Beranda",
                value="home",
                emoji="🏛️",
                description="Tentang Bot Prakom dan informasi umum"
            ),
            discord.SelectOption(
                label="Anggota & Komunitas",
                value="community",
                emoji="👥",
                description="Perintah level/rank, profil, dan leaderboard"
            ),
            discord.SelectOption(
                label="Layanan Tiket Bantuan",
                value="tickets",
                emoji="🎫",
                description="Panduan membuat dan mengelola tiket konsultasi"
            ),
            discord.SelectOption(
                label="Sistem Pengingat",
                value="reminders",
                emoji="⏰",
                description="Pengingat pribadi, publik, dan role"
            ),
            discord.SelectOption(
                label="Portal & Adhyaksa",
                value="adhyaksa",
                emoji="⚖️",
                description="Mars Adhyaksa, Tri Krama, dan tautan kedinasan"
            ),
        ]
        if is_admin:
            options.append(
                discord.SelectOption(
                    label="Panel Moderasi (Admin)",
                    value="admin",
                    emoji="🛡️",
                    description="Perintah moderasi, setup panel, dan pengumuman"
                )
            )
        super().__init__(placeholder="🔍 Pilih Kategori Perintah...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]

        if choice == "home":
            embed = discord.Embed(
                title="🏛️ Pusat Bantuan Bot Prakom Kejaksaan RI",
                description=(
                    "Selamat datang di sistem asisten virtual resmi komunitas **Pranata Komputer Kejaksaan RI**.\n\n"
                    "Gunakan menu pilihan dropdown di bawah untuk menjelajahi seluruh modul dan fungsi perintah bot.\n\n"
                    "**Kategori Perintah:**\n"
                    "• 👥 **Anggota & Komunitas:** Sistem level, XP, dan papan peringkat.\n"
                    "• 🎫 **Tiket Bantuan:** Konsultasi kendala teknis dan administrasi.\n"
                    "• ⏰ **Pengingat:** Pengingat agenda dan tenggat waktu kegiatan.\n"
                    "• ⚖️ **Portal & Adhyaksa:** Tautan cepat layanan BKN & Mars Adhyaksa.\n"
                    "• 🛡️ **Moderasi (Khusus Admin):** Pengelolaan keamanan dan ketertiban server."
                ),
                color=CLR_ADHYAKSA_GOLD
            )
            embed.set_footer(text="Kejaksaan RI • Satya Adhi Wicaksana")

        elif choice == "community":
            embed = discord.Embed(
                title="👥 Perintah Anggota & Aktivitas Komunitas",
                description="Tingkatkan aktivitas positif Anda untuk menaikkan level dan membuka gelar jenjang Prakom!",
                color=CLR_CYAN
            )
            embed.add_field(
                name="`/rank [member]`",
                value="Menampilkan kartu profil aktivitas, perolehan XP, level saat ini, dan progress bar visual.",
                inline=False
            )
            embed.add_field(
                name="`/leaderboard`",
                value="Menampilkan papan peringkat 10 besar anggota teraktif di server.",
                inline=False
            )
            embed.add_field(
                name="`/ping`",
                value="Memeriksa latensi jaringan gateway Discord dan waktu aktif bot (uptime).",
                inline=False
            )

        elif choice == "tickets":
            embed = discord.Embed(
                title="🎫 Layanan Tiket Konsultasi Teknis",
                description="Media komunikasi privat antara anggota dengan tim Admin/Moderator Prakom.",
                color=CLR_EMERALD
            )
            embed.add_field(
                name="`/create_ticket`",
                value="Membuka channel tiket bantuan khusus secara privat. Tim admin akan segera merespon dan mendampingi Anda.",
                inline=False
            )
            embed.add_field(
                name="🔒 Fitur Auto-Archive",
                value="Tiket yang tidak memiliki aktivitas percakapan selama 3 jam akan otomatis diarsipkan dan ditutup demi kerapian server.",
                inline=False
            )

        elif choice == "reminders":
            embed = discord.Embed(
                title="⏰ Sistem Pengingat Jadwal & Tugas",
                description="Pastikan tidak ada agenda, rapat dinas, atau tenggat pelaporan SKP yang terlewatkan.",
                color=CLR_AMBER
            )
            embed.add_field(
                name="`/set_reminder [tipe] [waktu] [pesan]`",
                value=(
                    "Membuat pengingat otomatis:\n"
                    "• `pribadi` : Dikirim via DM bot pada waktu yang ditentukan.\n"
                    "• `publik`  : Dikirim setiap hari pada jam tertentu di channel.\n"
                    "• `sekali`  : Dikirim satu kali pada tanggal & jam tertentu di channel.\n"
                    "• `role`    : Men-tag role tertentu pada tanggal & jam terjadwal."
                ),
                inline=False
            )
            embed.add_field(
                name="`/list_reminders`",
                value="Melihat seluruh daftar pengingat aktif Anda beserta ID pengingat.",
                inline=False
            )
            embed.add_field(
                name="`/cancel_reminder [reminder_id]`",
                value="Membatalkan pengingat yang telah dibuat berdasarkan ID-nya.",
                inline=False
            )

        elif choice == "adhyaksa":
            embed = discord.Embed(
                title="⚖️ Portal Kedinasan & Nilai Luhur Adhyaksa",
                description="Tautan penting dan pedoman moral bagi seluruh Insan Kejaksaan RI:",
                color=CLR_ADHYAKSA_GREEN
            )
            embed.add_field(
                name="`/prakom_portal`",
                value="Akses cepat satu pintu ke MOLA BKN, SIASN/MyASN, E-Kinerja, dan JDIH Kejaksaan RI.",
                inline=False
            )
            embed.add_field(
                name="`/mars_adhyaksa`",
                value="Menampilkan teks lirik resmi Mars Adhyaksa.",
                inline=False
            )
            embed.add_field(
                name="`/tri_karma_adhyaksa`",
                value="Menampilkan butir pedoman kehormatan Tri Krama Adhyaksa (Satya, Adhi, Wicaksana).",
                inline=False
            )

        elif choice == "admin":
            embed = discord.Embed(
                title="🛡️ Panel Perintah Moderasi & Manajemen Server",
                description="*Perintah di bawah ini hanya dapat dieksekusi oleh Administrator & Admin Prakom:*",
                color=CLR_CRIMSON
            )
            embed.add_field(
                name="⚙️ Inisialisasi Panel",
                value=(
                    "`/setup_verification` - Kirim panel verifikasi interaktif ber-tombol\n"
                    "`/setup_gender` - Kirim panel pemilihan role Prakom Cantik/Ganteng"
                ),
                inline=False
            )
            embed.add_field(
                name="🔨 Penindakan & Keamanan",
                value=(
                    "`/warn` | `/warnings` | `/clear_warnings` - Manajemen sanksi peringatan\n"
                    "`/mute` | `/unmute` - Timeout anggota sementara (native Discord)\n"
                    "`/kick` | `/ban` | `/unban` - Pengeluaran & pemblokiran anggota\n"
                    "`/clear [jumlah]` - Hapus pesan massal (maks. 100)"
                ),
                inline=False
            )
            embed.add_field(
                name="📢 Pengumuman Resmi",
                value=(
                    "`/announcement` - Kirim pengumuman resmi ber-embed emas\n"
                    "`/scheduled_announcement` - Jadwalkan pengumuman otomatis"
                ),
                inline=False
            )

        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(View):
    def __init__(self, is_admin: bool):
        super().__init__(timeout=180)
        self.add_item(HelpSelect(is_admin))


# ======= VIEW PORTAL DENGAN LINK BUTTONS =======
class PortalLinksView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="MOLA BKN", url="https://mola.bkn.go.id/", emoji="🔍", style=discord.ButtonStyle.link))
        self.add_item(Button(label="MyASN / SIASN", url="https://myasn.bkn.go.id/", emoji="👤", style=discord.ButtonStyle.link))
        self.add_item(Button(label="E-Kinerja BKN", url="https://kinerja.bkn.go.id/", emoji="📊", style=discord.ButtonStyle.link))
        self.add_item(Button(label="Kejaksaan RI", url="https://www.kejaksaan.go.id/", emoji="⚖️", style=discord.ButtonStyle.link))
        self.add_item(Button(label="JDIH Kejaksaan", url="https://jdih.kejaksaan.go.id/", emoji="📜", style=discord.ButtonStyle.link))


# ======= BOT CLASS DENGAN SETUP HOOK PERSISTEN =======
class PrakomBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(VerificationView())
        self.add_view(GenderRoleView())
        self.add_view(PersistentTicketButtons())
        print("✅ Persistent Views (Verifikasi, Gender, Tiket) berhasil diinisialisasi.")

bot = PrakomBot()
tree = bot.tree

# ======= BACKGROUND TASKS =======

@tasks.loop(minutes=30)
async def close_inactive_tickets():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    current_time = datetime.now(WIB)
    channels_to_close = []

    for channel_id, last_activity in list(inactive_tickets.items()):
        if (current_time - last_activity).total_seconds() > (3 * 3600):
            channel = guild.get_channel(channel_id)
            if channel and channel.category and channel.category.name == TICKET_CATEGORY_NAME:
                channels_to_close.append(channel)

    for channel in channels_to_close:
        try:
            owner_id = active_tickets.get(channel.id, {}).get("owner_id")
            owner_mention = f"<@{owner_id}>" if owner_id else "Pengguna Tidak Diketahui"

            auto_close_embed = discord.Embed(
                title="🕒 Tiket Ditutup Otomatis",
                description="Tiket ini otomatis diarsipkan karena tidak ada aktivitas selama 3 jam.",
                color=CLR_CRIMSON
            )
            await channel.send(embed=auto_close_embed)

            transcript_bytes = None
            try:
                transcript_bytes = await generate_ticket_transcript(channel)
            except Exception:
                pass

            if channel.id in active_tickets:
                del active_tickets[channel.id]
                save_ticket_data()
            if channel.id in inactive_tickets:
                del inactive_tickets[channel.id]

            log_admin_channel = guild.get_channel(LOGADMIN_CHANNEL_ID)
            if log_admin_channel:
                embed = discord.Embed(
                    title="🕒 Arsip Tiket (Inaktivitas 3 Jam)",
                    color=CLR_DARK,
                    timestamp=datetime.now(WIB)
                )
                embed.add_field(name="🏷️ Tiket", value=f"`{channel.name}`", inline=True)
                embed.add_field(name="👤 Pembuat", value=owner_mention, inline=True)
                file = None
                if transcript_bytes:
                    file = discord.File(transcript_bytes, filename=f"transkrip-auto-{channel.name}.txt")
                await log_admin_channel.send(embed=embed, file=file)

            await asyncio.sleep(5)
            await channel.delete(reason="Inaktivitas 3 jam")
        except Exception as e:
            print(f"Gagal menutup tiket otomatis {channel.name}: {e}")

@tasks.loop(minutes=1)
async def public_reminder_task():
    now_hm = datetime.now(WIB).strftime("%H:%M")
    for channel_id, reminders in list(public_reminders_data.items()):
        channel = bot.get_channel(channel_id)
        if channel:
            for rem in reminders:
                if rem.get("time") == now_hm:
                    embed = discord.Embed(
                        title="🔔 Pengingat Publik Terjadwal",
                        description=rem['message'],
                        color=CLR_AMBER,
                        timestamp=datetime.now(WIB)
                    )
                    embed.set_footer(text=f"Jadwal Rutin: Pukul {rem['time']} WIB")
                    try:
                        await channel.send(embed=embed)
                    except Exception as e:
                        print(f"Error mengirim public reminder: {e}")

@tasks.loop(minutes=1)
async def check_private_reminders():
    now = datetime.now(WIB)
    modified = False

    for user_id_str, reminders in list(private_reminders_data.items()):
        user = bot.get_user(int(user_id_str))
        if not user:
            try:
                user = await bot.fetch_user(int(user_id_str))
            except Exception:
                user = None

        to_remove = []
        for rem in list(reminders):
            rem_time = rem["time"]
            if isinstance(rem_time, str):
                rem_time = datetime.fromisoformat(rem_time)
                if rem_time.tzinfo is None:
                    rem_time = rem_time.replace(tzinfo=WIB)
                rem["time"] = rem_time

            if rem_time <= now:
                if user:
                    embed = discord.Embed(
                        title="🔔 Pengingat Pribadi",
                        description=rem['message'],
                        color=CLR_CYAN,
                        timestamp=now
                    )
                    embed.set_footer(text="Komunitas Prakom Kejaksaan RI")
                    try:
                        await user.send(embed=embed)
                    except discord.Forbidden:
                        pass
                to_remove.append(rem)
                modified = True

        for item in to_remove:
            if item in reminders:
                reminders.remove(item)

        if not reminders:
            if user_id_str in private_reminders_data:
                del private_reminders_data[user_id_str]
                modified = True

    if modified:
        save_private_reminders()

@tasks.loop(minutes=1)
async def check_role_reminders():
    now = datetime.now(WIB)
    indices_to_remove = []

    for i, rem in enumerate(role_reminders):
        rem_time = rem["waktu"]
        if isinstance(rem_time, str):
            rem_time = datetime.fromisoformat(rem_time)
            if rem_time.tzinfo is None:
                rem_time = rem_time.replace(tzinfo=WIB)
            rem["waktu"] = rem_time

        if rem_time <= now:
            tipe = rem.get("tipe")
            channel = bot.get_channel(rem["channel_id"])
            if channel:
                try:
                    if tipe == "sekali_channel":
                        embed = discord.Embed(
                            title="🔔 Pengingat Terjadwal",
                            description=rem['pesan'],
                            color=CLR_AMBER,
                            timestamp=now
                        )
                        await channel.send(embed=embed)
                    elif tipe == "scheduled_announcement":
                        embed = discord.Embed(
                            title="📢 PENGUMUMAN RESMI TERJADWAL",
                            description=rem['pesan'],
                            color=CLR_ADHYAKSA_GOLD,
                            timestamp=now
                        )
                        embed.set_footer(text="Kejaksaan Republik Indonesia")
                        await channel.send(embed=embed)
                    elif tipe == "role":
                        guild = bot.get_guild(GUILD_ID)
                        if guild:
                            role_target = discord.utils.get(guild.roles, name=rem.get("role_name"))
                            mention = role_target.mention if role_target else f"@{rem.get('role_name')}"
                            embed = discord.Embed(
                                title=f"🔔 Pengingat Khusus",
                                description=f"Perhatian untuk {mention}:\n\n{rem['pesan']}",
                                color=CLR_NAVY,
                                timestamp=now
                            )
                            await channel.send(content=mention, embed=embed)
                except Exception as e:
                    print(f"Error role reminder: {e}")
            indices_to_remove.append(i)

    if indices_to_remove:
        for i in sorted(indices_to_remove, reverse=True):
            del role_reminders[i]
        save_role_reminders()

@tasks.loop(time=time(hour=7, minute=0, tzinfo=WIB))
async def daily_reminder_task():
    channel = bot.get_channel(DAILY_ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        quote = random.choice(DAILY_QUOTES)
        embed = discord.Embed(
            title="🌅 Selamat Pagi Insan Adhyaksa! 🌞",
            description=(
                "Awali hari dengan semangat profesionalisme dan integritas tinggi.\n\n"
                "**📌 Agenda & Pengingat Pagi Ini:**\n"
                "• Lakukan absensi pagi sesuai ketentuan satker masing-masing.\n"
                "• Cek dashboard **MOLA BKN** untuk pemutakhiran layanan kepegawaian.\n"
                "• Siapkan laporan kinerja harian pada aplikasi **E-Kinerja BKN**.\n"
                "• Jaga kesehatan dan utamakan keselamatan kerja."
            ),
            color=CLR_ADHYAKSA_GOLD,
            timestamp=datetime.now(WIB)
        )
        embed.add_field(
            name="✨ Motivasi Adhyaksa Hari Ini",
            value=f"*{quote}*",
            inline=False
        )
        embed.set_footer(text="Kejaksaan Republik Indonesia • Satya Adhi Wicaksana")
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

# ======= EVENTS =======

@bot.event
async def on_ready():
    print(f"✅ Bot Prakom aktif sebagai {bot.user} (ID: {bot.user.id})")
    load_warn_data()
    load_private_reminders()
    load_public_reminders()
    load_role_reminders()
    load_ticket_data()
    load_level_data()

    try:
        guild_obj = discord.Object(id=GUILD_ID)
        synced = await tree.sync(guild=guild_obj)
        print(f"Slash commands synced: {len(synced)}")
    except Exception as e:
        print(f"Gagal sync slash commands: {e}")

    loop_tasks = [
        daily_reminder_task,
        public_reminder_task,
        close_inactive_tickets,
        check_role_reminders,
        check_private_reminders
    ]
    for t in loop_tasks:
        if not t.is_running():
            t.start()

@bot.event
async def on_member_join(member: discord.Member):
    if member.guild.id != GUILD_ID:
        return

    guild = member.guild

    role_unverified = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE_NAME)
    if role_unverified:
        try:
            await member.add_roles(role_unverified)
        except Exception:
            pass

    try:
        dm_embed = discord.Embed(
            title=f"Selamat Datang di {guild.name}! 🏛️",
            description=(
                f"Halo {member.mention}! Selamat datang di komunitas resmi **Pranata Komputer Kejaksaan RI**.\n\n"
                f"Agar dapat berinteraksi dan mengakses seluruh channel, silakan buka channel <#{VERIFICATION_CHANNEL_ID}> "
                f"dan klik tombol **'Verifikasi Sekarang'** untuk mengisi nama dan unit kerja Anda."
            ),
            color=CLR_ADHYAKSA_GREEN
        )
        dm_embed.set_footer(text="Kejaksaan Republik Indonesia • Satya Adhi Wicaksana")
        await member.send(embed=dm_embed)
    except discord.Forbidden:
        pass

    welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
    if welcome_channel:
        embed = discord.Embed(
            title=f"👋 Selamat Datang, {member.display_name}!",
            description=(
                f"Selamat datang di server komunitas **Pranata Komputer Kejaksaan RI**! 🎉\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"**📌 3 Langkah Awal Bergabung:**\n"
                f"**1.** Lakukan verifikasi identitas resmi di <#{VERIFICATION_CHANNEL_ID}>.\n"
                f"**2.** Ambil peran gender identitas Anda di <#{GENDER_CHANNEL_ID}>.\n"
                f"**3.** Pahami tata tertib dan etika komunitas di <#{ROLES_CHANNEL_ID}>.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*Mari berkontribusi nyata demi kemajuan teknologi informasi Korps Adhyaksa!*"
            ),
            color=CLR_NAVY,
            timestamp=datetime.now(WIB)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Kejaksaan Republik Indonesia • Satya Adhi Wicaksana")
        await welcome_channel.send(content=f"Selamat datang {member.mention}!", embed=embed)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    if message.channel.id in active_tickets:
        inactive_tickets[message.channel.id] = datetime.now(WIB)

    now = datetime.now(WIB)

    # Anti-Spam
    timestamps = user_messages[message.author.id]
    timestamps = [ts for ts in timestamps if (now - ts).total_seconds() < SPAM_INTERVAL]
    timestamps.append(now)
    user_messages[message.author.id] = timestamps

    if len(user_messages) > 300:
        stale = [uid for uid, tss in user_messages.items() if not tss or (now - tss[-1]).total_seconds() > 300]
        for uid in stale:
            del user_messages[uid]

    if len(timestamps) > SPAM_THRESHOLD:
        try:
            await message.delete()
            warn_embed = discord.Embed(
                description=f"⚠️ {message.author.mention}, aktivitas pengiriman pesan terlalu cepat! Anda dimute sementara.",
                color=CLR_CRIMSON
            )
            await message.channel.send(embed=warn_embed, delete_after=5)
            await message.author.timeout(timedelta(seconds=MUTE_DURATION), reason="Anti-Spam otomatis")
        except Exception:
            pass
        return

    # XP & Leveling
    user_id_str = str(message.author.id)
    current_time_sec = now.timestamp()
    user_data = level_data.get(user_id_str, {"xp": 0, "level": 0, "last_xp_time": 0})

    if current_time_sec - user_data.get("last_xp_time", 0) >= XP_COOLDOWN:
        user_data["last_xp_time"] = current_time_sec
        user_data["xp"] = user_data.get("xp", 0) + 15
        current_level = user_data.get("level", 0)
        next_level_xp = (current_level + 1) * 100

        if user_data["xp"] >= next_level_xp:
            user_data["level"] = current_level + 1
            tier_title, tier_role = get_prakom_tier(user_data["level"])
            lvl_embed = discord.Embed(
                title="⭐ Naik Level!",
                description=(
                    f"Selamat {message.author.mention}! Anda telah naik ke **Level {user_data['level']}**!\n"
                    f"🎖️ **Jenjang:** `{tier_title}`\n"
                    f"💼 *{tier_role}*"
                ),
                color=CLR_ADHYAKSA_GOLD
            )
            lvl_embed.set_thumbnail(url=message.author.display_avatar.url)
            try:
                await message.channel.send(embed=lvl_embed, delete_after=12)
            except Exception:
                pass

        level_data[user_id_str] = user_data
        save_level_data()

    # Verifikasi Manual Teks (Fallback)
    if message.guild.id == GUILD_ID and message.channel.id == VERIFICATION_CHANNEL_ID:
        member = message.author
        role_unverified = discord.utils.get(message.guild.roles, name=UNVERIFIED_ROLE_NAME)
        role_anggota = discord.utils.get(message.guild.roles, name=ANGGOTA_ROLE_NAME)

        if (role_unverified and role_unverified in member.roles) or (role_anggota and role_anggota not in member.roles):
            nama_baru = message.content.strip()[:32]
            try:
                await member.edit(nick=nama_baru)
            except Exception:
                pass

            try:
                if role_unverified and role_unverified in member.roles:
                    await member.remove_roles(role_unverified)
                if role_anggota and role_anggota not in member.roles:
                    await member.add_roles(role_anggota)
            except Exception:
                pass

            log_channel = message.guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"🟢 {member.mention} terverifikasi via teks dengan nama **{nama_baru}**.")

            try:
                await message.delete()
            except Exception:
                pass

    await bot.process_commands(message)

# ======= SLASH COMMANDS: INFORMASI & ADHYAKSA =======

@tree.command(name="mars_adhyaksa", description="Menampilkan lirik resmi Mars Adhyaksa.", guild=discord.Object(id=GUILD_ID))
async def mars_adhyaksa(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚔️ MARS ADHYAKSA",
        description=(
            "```text\n"
            "Satya Adi Wicaksana dasar Tripsila Adhyaksa\n"
            "Landasan jiwa Kejaksaan sebagai abdi masyarakat\n"
            "Setia dan sempurna\n"
            "Melaksanakan tugas kewajiban\n"
            "Tanggung jawab pada Tuhan,\n"
            "Keluarga dan sesama manusia\n\n"
            "Abdi negara sebagai penegak hukum\n"
            "Yang berlambangkan pedang nan sakti\n"
            "Insan Adhyaksa sebagai pedamba\n"
            "Keadilan dan perwujudan hukum pasti\n\n"
            "Kita basmi kemungkaran\n"
            "Kebatilan dan kejahatan yang\n"
            "Tersirat dan tersurat imbangan\n"
            "Tegarlah sepanjang zaman..\n"
            "```"
        ),
        color=CLR_ADHYAKSA_GOLD,
        timestamp=datetime.now(WIB)
    )
    embed.set_footer(text="Kejaksaan Republik Indonesia • Satya Adhi Wicaksana")
    await interaction.response.send_message(embed=embed)

@tree.command(name="tri_karma_adhyaksa", description="Menampilkan butir Tri Krama Adhyaksa.", guild=discord.Object(id=GUILD_ID))
async def tri_karma_adhyaksa(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚖️ TRI KRAMA ADHYAKSA",
        description="Doktrin dan pedoman moral bagi seluruh Insan Kejaksaan Republik Indonesia:",
        color=CLR_ADHYAKSA_GREEN,
        timestamp=datetime.now(WIB)
    )
    embed.add_field(
        name="1. 🌟 SATYA",
        value="Kesetiaan yang bersumber pada rasa jujur, baik terhadap Tuhan Yang Maha Esa, diri pribadi, dan keluarga maupun kepada sesama manusia.",
        inline=False
    )
    embed.add_field(
        name="2. ⚔️ ADHI",
        value="Kesempurnaan dalam bertugas dan yang berunsur utama pemilikan rasa tanggung jawab terhadap Tuhan Yang Maha Esa, keluarga, dan sesama manusia.",
        inline=False
    )
    embed.add_field(
        name="3. 📜 WICAKSANA",
        value="Bijaksana dalam tutur kata dan tingkah laku, khususnya dalam penerapan tugas dan kewenangan penegakan hukum.",
        inline=False
    )
    embed.set_footer(text="Kejaksaan Republik Indonesia • Satya Adhi Wicaksana")
    await interaction.response.send_message(embed=embed)

@tree.command(name="prakom_portal", description="Portal tautan resmi aplikasi kedinasan Kejaksaan RI dan BKN.", guild=discord.Object(id=GUILD_ID))
async def prakom_portal(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌐 Portal Layanan & Tautan Resmi Prakom",
        description=(
            "Akses cepat ke portal layanan kepegawaian dan sistem informasi kedinasan. "
            "Klik tombol interaktif di bawah untuk langsung membuka situs resmi di peramban Anda:"
        ),
        color=CLR_NAVY,
        timestamp=datetime.now(WIB)
    )
    embed.add_field(
        name="🏛️ Badan Kepegawaian Negara (BKN)",
        value=(
            "• **MOLA BKN:** Layanan notifikasi & pemantauan berkas usul kenaikan pangkat/SK.\n"
            "• **MyASN / SIASN:** Data profil kepegawaian ASN terpusat nasional.\n"
            "• **E-Kinerja BKN:** Pengelolaan SKP, matriks peran hasil, dan penilaian kinerja ASN."
        ),
        inline=False
    )
    embed.add_field(
        name="⚖️ Kejaksaan Republik Indonesia",
        value=(
            "• **Website Resmi:** Portal berita, publikasi, dan profil Korps Adhyaksa.\n"
            "• **JDIH Kejaksaan:** Jaringan dokumentasi & produk hukum resmi Kejaksaan.\n"
            "• **SIMPEG Kejaksaan:** Sistem Informasi Kepegawaian Internal."
        ),
        inline=False
    )
    embed.add_field(
        name="📜 Regulasi Jabatan Fungsional",
        value="• PermenPAN-RB No. 1 Tahun 2023 tentang Jabatan Fungsional Pegawai Negeri Sipil.",
        inline=False
    )
    embed.set_footer(text="Kejaksaan Republik Indonesia • Satya Adhi Wicaksana")
    view = PortalLinksView()
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="ping", description="Periksa latensi jaringan gateway Discord dan status bot.", guild=discord.Object(id=GUILD_ID))
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    uptime = datetime.now(WIB) - BOT_START_TIME
    days = uptime.days
    hours, rem = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    uptime_str = f"{days}h {hours}j {minutes}m {seconds}d" if days > 0 else f"{hours}j {minutes}m {seconds}d"

    embed = discord.Embed(
        title="🏓 Pong! Status Sistem Bot Prakom",
        color=CLR_EMERALD if latency < 150 else CLR_AMBER,
        timestamp=datetime.now(WIB)
    )
    embed.add_field(name="📶 Latensi Gateway", value=f"`{latency} ms`", inline=True)
    embed.add_field(name="⏱️ Waktu Operasional", value=f"`{uptime_str}`", inline=True)
    embed.add_field(name="👥 Total Anggota", value=f"`{interaction.guild.member_count:,}`", inline=True)
    embed.set_footer(text="Status Operasional Normal • Prakom Bot Kejaksaan")
    await interaction.response.send_message(embed=embed)

@tree.command(name="help", description="Panduan lengkap penggunaan perintah Bot Prakom.", guild=discord.Object(id=GUILD_ID))
async def help_command(interaction: discord.Interaction):
    admin_role = discord.utils.get(interaction.guild.roles, name=ADMIN_PRAKOM_ROLE)
    is_admin = (
        interaction.user.id == interaction.guild.owner_id or
        interaction.user.guild_permissions.administrator or
        (admin_role and admin_role in interaction.user.roles)
    )

    embed = discord.Embed(
        title="🏛️ Pusat Bantuan Bot Prakom Kejaksaan RI",
        description=(
            "Selamat datang di sistem asisten virtual resmi komunitas **Pranata Komputer Kejaksaan RI**.\n\n"
            "Gunakan menu pilihan dropdown di bawah untuk menjelajahi seluruh modul dan fungsi perintah bot.\n\n"
            "**Kategori Perintah:**\n"
            "• 👥 **Anggota & Komunitas:** Sistem level, XP, dan papan peringkat.\n"
            "• 🎫 **Tiket Bantuan:** Konsultasi kendala teknis dan administrasi.\n"
            "• ⏰ **Pengingat:** Pengingat agenda dan tenggat waktu kegiatan.\n"
            "• ⚖️ **Portal & Adhyaksa:** Tautan cepat layanan BKN & Mars Adhyaksa.\n"
            "• 🛡️ **Moderasi (Khusus Admin):** Pengelolaan keamanan dan ketertiban server."
        ),
        color=CLR_ADHYAKSA_GOLD,
        timestamp=datetime.now(WIB)
    )
    embed.set_footer(text="Pilih kategori di bawah untuk melihat rincian perintah")
    view = HelpView(is_admin)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ======= SLASH COMMANDS: LEVEL & RANK =======

@tree.command(name="rank", description="Lihat kartu status level, perolehan XP, dan gelar jenjang Prakom.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Anggota yang ingin dicek rank-nya (kosongkan untuk melihat profil sendiri)")
async def rank(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    user_id_str = str(target.id)
    data = level_data.get(user_id_str, {"xp": 0, "level": 0})
    xp = data.get("xp", 0)
    level = data.get("level", 0)

    base_xp = level * 100
    next_xp = (level + 1) * 100
    needed = next_xp - base_xp
    current_progress = max(0, xp - base_xp)

    bar = create_progress_bar(current_progress, needed, length=12)
    tier_title, tier_role = get_prakom_tier(level)

    sorted_users = sorted(level_data.items(), key=lambda x: (x[1].get("level", 0), x[1].get("xp", 0)), reverse=True)
    rank_pos = 1
    for idx, (uid, _) in enumerate(sorted_users):
        if uid == user_id_str:
            rank_pos = idx + 1
            break

    embed = discord.Embed(
        title=f"📊 Profil Aktivitas — {target.display_name}",
        color=CLR_ADHYAKSA_GOLD,
        timestamp=datetime.now(WIB)
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🎖️ Peringkat Server", value=f"**#{rank_pos}** dari {len(sorted_users)}", inline=True)
    embed.add_field(name="⭐ Level Saat Ini", value=f"**Level {level}**", inline=True)
    embed.add_field(name="✨ Total XP", value=f"**{xp:,} XP**", inline=True)
    embed.add_field(name="💼 Jenjang Fungsional", value=f"**{tier_title}**\n*{tier_role}*", inline=False)
    embed.add_field(
        name="📈 Progres Level Berikutnya",
        value=f"{bar}\n`{current_progress} / {needed} XP` (Butuh {needed - current_progress} XP lagi)",
        inline=False
    )
    embed.set_footer(text="Aktivitas diskusi di server meningkatkan perolehan XP Anda!")
    await interaction.response.send_message(embed=embed)

@tree.command(name="leaderboard", description="Papan peringkat 10 anggota teraktif di server.", guild=discord.Object(id=GUILD_ID))
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    if not level_data:
        await interaction.followup.send("Belum ada data aktivitas anggota.", ephemeral=True)
        return

    sorted_users = sorted(level_data.items(), key=lambda x: (x[1].get("level", 0), x[1].get("xp", 0)), reverse=True)[:10]
    medals = ["👑", "🥈", "🥉"]
    desc = ""

    for idx, (uid, data) in enumerate(sorted_users):
        user = interaction.guild.get_member(int(uid))
        name = user.display_name if user else f"User {uid}"
        icon = medals[idx] if idx < 3 else f"`#{idx+1}`"
        tier_title, _ = get_prakom_tier(data.get("level", 0))
        desc += f"{icon} **{name}**\n   └ Level **{data.get('level', 0)}** • `{data.get('xp', 0):,} XP` • *{tier_title}*\n\n"

    embed = discord.Embed(
        title="🏆 Papan Peringkat Aktivitas Anggota (Top 10)",
        description=desc or "Belum ada catatan aktivitas.",
        color=CLR_ADHYAKSA_GOLD,
        timestamp=datetime.now(WIB)
    )
    embed.set_footer(text="Kejaksaan Republik Indonesia • Komunitas Prakom")
    await interaction.followup.send(embed=embed)

# ======= SLASH COMMANDS: REMINDERS =======

@tree.command(name="set_reminder", description="Pasang pengingat pribadi, publik, atau role.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    tipe="Tipe: pribadi (DM), publik (channel harian), sekali (channel), atau role",
    waktu="Format: HH:MM (publik harian) atau YYYY-MM-DDTHH:MM (pribadi/sekali/role)",
    pesan="Isi pengingat",
    target_role="Nama role jika tipe adalah 'role'",
    target_user="Target pengguna jika tipe adalah 'pribadi' (default: diri sendiri)"
)
async def set_reminder(
    interaction: discord.Interaction,
    tipe: str,
    waktu: str,
    pesan: str,
    target_role: str = None,
    target_user: discord.Member = None
):
    await interaction.response.defer(ephemeral=True)
    now = datetime.now(WIB)
    tipe = tipe.lower().strip()
    rem_id = str(uuid.uuid4())[:6]

    if tipe == "sekali":
        try:
            dt = datetime.fromisoformat(waktu.replace(" ", "T"))
            dt = dt.replace(tzinfo=WIB)
            if dt < now:
                await interaction.followup.send("❌ Waktu reminder harus berada di masa depan.", ephemeral=True)
                return

            role_reminders.append({
                "id": rem_id,
                "tipe": "sekali_channel",
                "waktu": dt,
                "pesan": pesan,
                "channel_id": interaction.channel.id,
                "creator_id": interaction.user.id
            })
            save_role_reminders()

            embed = discord.Embed(
                title="✅ Pengingat Berhasil Diatur",
                description=(
                    f"Pengingat sekali berhasil dijadwalkan:\n\n"
                    f"📅 **Waktu:** {dt.strftime('%d %b %Y, %H:%M WIB')}\n"
                    f"📍 **Channel:** {interaction.channel.mention}\n"
                    f"📝 **Pesan:** {pesan}\n"
                    f"🏷️ **ID Pengingat:** `{rem_id}`"
                ),
                color=CLR_EMERALD
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Format waktu harus `YYYY-MM-DDTHH:MM` (contoh: 2026-05-20T14:30).", ephemeral=True)

    elif tipe == "publik":
        try:
            datetime.strptime(waktu, "%H:%M")
            public_reminders_data[interaction.channel.id].append({
                "id": rem_id,
                "time": waktu,
                "message": pesan,
                "creator_id": interaction.user.id
            })
            save_public_reminders()

            embed = discord.Embed(
                title="✅ Pengingat Publik Rutin Berhasil Diatur",
                description=(
                    f"Pengingat harian berhasil dipasang:\n\n"
                    f"⏰ **Jadwal:** Setiap hari pukul **{waktu} WIB**\n"
                    f"📍 **Channel:** {interaction.channel.mention}\n"
                    f"📝 **Pesan:** {pesan}\n"
                    f"🏷️ **ID Pengingat:** `{rem_id}`"
                ),
                color=CLR_EMERALD
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Format waktu publik harus `HH:MM` (contoh: 14:30).", ephemeral=True)

    elif tipe == "pribadi":
        dest_user = target_user or interaction.user
        try:
            dt = datetime.fromisoformat(waktu.replace(" ", "T"))
            dt = dt.replace(tzinfo=WIB)
            if dt < now:
                await interaction.followup.send("❌ Waktu reminder harus berada di masa depan.", ephemeral=True)
                return

            uid_str = str(dest_user.id)
            if uid_str not in private_reminders_data:
                private_reminders_data[uid_str] = []
            private_reminders_data[uid_str].append({
                "id": rem_id,
                "time": dt,
                "message": pesan
            })
            save_private_reminders()

            embed = discord.Embed(
                title="✅ Pengingat Pribadi Berhasil Diatur",
                description=(
                    f"Pengingat DM berhasil dijadwalkan:\n\n"
                    f"👤 **Penerima:** {dest_user.mention}\n"
                    f"📅 **Waktu:** {dt.strftime('%d %b %Y, %H:%M WIB')}\n"
                    f"📝 **Pesan:** {pesan}\n"
                    f"🏷️ **ID Pengingat:** `{rem_id}`"
                ),
                color=CLR_EMERALD
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Format waktu pribadi harus `YYYY-MM-DDTHH:MM` (contoh: 2026-05-20T14:30).", ephemeral=True)

    elif tipe == "role":
        if not target_role:
            await interaction.followup.send("❌ Untuk pengingat role, Anda harus mengisi parameter `target_role`.", ephemeral=True)
            return

        role_obj = discord.utils.get(interaction.guild.roles, name=target_role)
        if not role_obj:
            await interaction.followup.send(f"❌ Role `{target_role}` tidak ditemukan di server ini.", ephemeral=True)
            return

        try:
            dt = datetime.fromisoformat(waktu.replace(" ", "T"))
            dt = dt.replace(tzinfo=WIB)
            if dt < now:
                await interaction.followup.send("❌ Waktu reminder harus berada di masa depan.", ephemeral=True)
                return

            role_reminders.append({
                "id": rem_id,
                "tipe": "role",
                "waktu": dt,
                "pesan": pesan,
                "channel_id": interaction.channel.id,
                "role_name": target_role,
                "creator_id": interaction.user.id
            })
            save_role_reminders()

            embed = discord.Embed(
                title="✅ Pengingat Role Berhasil Diatur",
                description=(
                    f"Pengingat untuk role berhasil dijadwalkan:\n\n"
                    f"👥 **Target Role:** {role_obj.mention}\n"
                    f"📅 **Waktu:** {dt.strftime('%d %b %Y, %H:%M WIB')}\n"
                    f"📍 **Channel:** {interaction.channel.mention}\n"
                    f"📝 **Pesan:** {pesan}\n"
                    f"🏷️ **ID Pengingat:** `{rem_id}`"
                ),
                color=CLR_EMERALD
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Format waktu role harus `YYYY-MM-DDTHH:MM` (contoh: 2026-05-20T14:30).", ephemeral=True)
    else:
        await interaction.followup.send("❌ Tipe reminder tidak valid. Pilih antara: `pribadi`, `publik`, `sekali`, atau `role`.", ephemeral=True)

@tree.command(name="list_reminders", description="Lihat daftar pengingat aktif milikmu atau di channel ini.", guild=discord.Object(id=GUILD_ID))
async def list_reminders(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    uid_str = str(interaction.user.id)
    now = datetime.now(WIB)

    desc = ""

    user_rems = private_reminders_data.get(uid_str, [])
    if user_rems:
        desc += "🔔 **Pengingat Pribadi Anda:**\n"
        for r in user_rems:
            t = r['time'] if isinstance(r['time'], datetime) else datetime.fromisoformat(r['time'])
            desc += f"• `ID: {r.get('id', 'N/A')}` | **{t.strftime('%d %b %Y %H:%M')}**: {r['message']}\n"
        desc += "\n"

    channel_rems = public_reminders_data.get(interaction.channel.id, [])
    if channel_rems:
        desc += f"📢 **Pengingat Publik Harian ({interaction.channel.mention}):**\n"
        for r in channel_rems:
            desc += f"• `ID: {r.get('id', 'N/A')}` | Pukul **{r['time']} WIB**: {r['message']}\n"
        desc += "\n"

    role_rems_chan = [r for r in role_reminders if r.get("channel_id") == interaction.channel.id]
    if role_rems_chan:
        desc += f"🗓️ **Pengingat Terjadwal ({interaction.channel.mention}):**\n"
        for r in role_rems_chan:
            t = r['waktu'] if isinstance(r['waktu'], datetime) else datetime.fromisoformat(r['waktu'])
            target = f"Role @{r['role_name']}" if r.get('tipe') == 'role' else "Channel"
            desc += f"• `ID: {r.get('id', 'N/A')}` | **{t.strftime('%d %b %Y %H:%M')}** ({target}): {r['pesan']}\n"

    if not desc:
        desc = "Tidak ada pengingat aktif yang ditemukan untuk Anda atau di channel ini."

    embed = discord.Embed(
        title="📋 Daftar Pengingat Aktif",
        description=desc,
        color=CLR_CYAN,
        timestamp=now
    )
    embed.set_footer(text="Gunakan /cancel_reminder [ID] untuk membatalkan pengingat.")
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="cancel_reminder", description="Batalkan pengingat aktif berdasarkan ID-nya.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(reminder_id="ID pengingat yang ingin dibatalkan")
async def cancel_reminder(interaction: discord.Interaction, reminder_id: str):
    await interaction.response.defer(ephemeral=True)
    reminder_id = reminder_id.strip()
    uid_str = str(interaction.user.id)
    found = False

    if uid_str in private_reminders_data:
        for rem in list(private_reminders_data[uid_str]):
            if rem.get("id") == reminder_id:
                private_reminders_data[uid_str].remove(rem)
                if not private_reminders_data[uid_str]:
                    del private_reminders_data[uid_str]
                save_private_reminders()
                found = True
                break

    if not found:
        for cid, rem_list in list(public_reminders_data.items()):
            for rem in list(rem_list):
                if rem.get("id") == reminder_id:
                    admin_role = discord.utils.get(interaction.guild.roles, name=ADMIN_PRAKOM_ROLE)
                    is_admin = (
                        interaction.user.id == interaction.guild.owner_id or
                        interaction.user.guild_permissions.administrator or
                        (admin_role and admin_role in interaction.user.roles)
                    )
                    if rem.get("creator_id") == interaction.user.id or is_admin:
                        rem_list.remove(rem)
                        save_public_reminders()
                        found = True
                        break
            if found:
                break

    if not found:
        for rem in list(role_reminders):
            if rem.get("id") == reminder_id:
                admin_role = discord.utils.get(interaction.guild.roles, name=ADMIN_PRAKOM_ROLE)
                is_admin = (
                    interaction.user.id == interaction.guild.owner_id or
                    interaction.user.guild_permissions.administrator or
                    (admin_role and admin_role in interaction.user.roles)
                )
                if rem.get("creator_id") == interaction.user.id or is_admin:
                    role_reminders.remove(rem)
                    save_role_reminders()
                    found = True
                    break

    if found:
        embed = discord.Embed(
            description=f"✅ Pengingat dengan ID `{reminder_id}` berhasil dibatalkan dan dihapus.",
            color=CLR_EMERALD
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            description=f"❌ Pengingat dengan ID `{reminder_id}` tidak ditemukan atau Anda tidak memiliki hak akses untuk membatalkannya.",
            color=CLR_CRIMSON
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

# ======= SLASH COMMANDS: SETUP PANEL (ADMIN ONLY) =======

@tree.command(name="setup_verification", description="Kirim panel verifikasi interaktif ber-tombol ke channel.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(channel="Channel tujuan (opsional, default: channel verifikasi)")
@is_admin_prakom()
async def setup_verification(interaction: discord.Interaction, channel: discord.TextChannel = None):
    await interaction.response.defer(ephemeral=True)
    target_channel = channel or interaction.guild.get_channel(VERIFICATION_CHANNEL_ID) or interaction.channel

    embed = discord.Embed(
        title="🏛️ GERBANG VERIFIKASI PRAKOM KEJAKSAAN RI",
        description=(
            "Selamat datang di server komunikasi resmi **Pranata Komputer Kejaksaan Republik Indonesia**!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Untuk menjamin keamanan, kenyamanan, serta profesionalitas diskusi antar-insan Adhyaksa, "
            "seluruh anggota diwajibkan melakukan pencatatan identitas resmi sebelum mengakses server.\n\n"
            "**📋 Petunjuk & Alur Verifikasi:**\n"
            "**1.** Klik tombol hijau **`📝 Verifikasi Sekarang`** di bawah.\n"
            "**2.** Masukkan **Nama Lengkap & Gelar Akademik** Anda.\n"
            "**3.** Masukkan **Satuan Kerja / NIP / Jenjang Jabatan** Anda.\n"
            "**4.** Sistem otomatis menyesuaikan nama tampilan Anda dan memberikan akses role **Anggota**.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "*Salam Korps Adhyaksa: Satya Adhi Wicaksana.*"
        ),
        color=CLR_ADHYAKSA_GOLD
    )
    embed.set_footer(text="Kejaksaan Republik Indonesia • Sistem Informasi Manajemen Komunitas")
    view = VerificationView()
    await target_channel.send(embed=embed, view=view)
    await interaction.followup.send(f"✅ Panel verifikasi berhasil dikirimkan ke {target_channel.mention}.", ephemeral=True)

@tree.command(name="setup_gender", description="Kirim panel pemilihan role Prakom Cantik / Ganteng ke channel.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(channel="Channel tujuan (opsional, default: channel gender)")
@is_admin_prakom()
async def setup_gender(interaction: discord.Interaction, channel: discord.TextChannel = None):
    await interaction.response.defer(ephemeral=True)
    target_channel = channel or interaction.guild.get_channel(GENDER_CHANNEL_ID) or interaction.channel

    embed = discord.Embed(
        title="👥 PEMILIHAN IDENTITAS PERAN PRAKOM",
        description=(
            "Silakan sematkan role kebanggaan Anda di komunitas Prakom Kejaksaan RI dengan menekan tombol di bawah:\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👩 **PRAKOM CANTIK**\n"
            "Khusus untuk rekan-rekan Pranata Komputer wanita yang berdedikasi membangun TI Kejaksaan.\n\n"
            "👨 **PRAKOM GANTENG**\n"
            "Khusus untuk rekan-rekan Pranata Komputer pria yang senantiasa menjaga keandalan sistem TI.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "💡 *Anda dapat memperbarui atau mengganti pilihan kapan saja dengan menekan tombol kembali.*"
        ),
        color=CLR_PURPLE
    )
    embed.set_footer(text="Kejaksaan Republik Indonesia • Korps Adhyaksa")
    view = GenderRoleView()
    await target_channel.send(embed=embed, view=view)
    await interaction.followup.send(f"✅ Panel role gender berhasil dikirimkan ke {target_channel.mention}.", ephemeral=True)

# ======= SLASH COMMANDS: TIKET =======

@tree.command(name="create_ticket", description="Buka tiket bantuan teknis atau konsultasi secara privat.", guild=discord.Object(id=GUILD_ID))
async def create_ticket(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    channel, error_msg = await create_ticket_channel(interaction.guild, interaction.user)

    if channel:
        embed = discord.Embed(
            title="🎫 TIKET BANTUAN TEKNIS & KONSULTASI",
            description=(
                f"Halo {interaction.user.mention}! Tiket bantuan Anda telah berhasil dibuat.\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"**📌 Panduan Konsultasi:**\n"
                f"• Jelaskan secara spesifik kendala yang Anda alami (aplikasi, akun, atau regulasi Prakom).\n"
                f"• Sertakan tangkapan layar (screenshot) pesan error atau bukti dokumen bila diperlukan.\n"
                f"• Tim Admin & Moderator Prakom akan segera mendampingi Anda di channel ini.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*Gunakan tombol interaktif di bawah untuk mengelola status tiket.*"
            ),
            color=CLR_EMERALD,
            timestamp=datetime.now(WIB)
        )
        embed.set_footer(text="Arsip transkrip chat akan otomatis dikirimkan ke log admin saat tiket ditutup.")
        view = PersistentTicketButtons()
        await channel.send(embed=embed, view=view)
        await interaction.followup.send(f"✅ Tiket bantuan Anda telah dibuat di {channel.mention}.", ephemeral=True)

        log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin:
            await log_admin.send(f"🆕 **Tiket Baru:** `{channel.name}` dibuat oleh {interaction.user.mention}.")
    else:
        await interaction.followup.send(error_msg or "❌ Gagal membuat tiket.", ephemeral=True)

# ======= SLASH COMMANDS: MODERASI (ADMIN ONLY) =======

@tree.command(name="warn", description="Beri sanksi peringatan resmi kepada anggota.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Anggota yang akan diberi peringatan", reason="Alasan peringatan")
@is_admin_prakom()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "Tidak ada alasan"):
    await interaction.response.defer(ephemeral=True)
    member_id = str(member.id)

    if member_id not in warn_data:
        warn_data[member_id] = []

    warn_entry = {
        "reason": reason,
        "timestamp": datetime.now(WIB).isoformat(),
        "admin": interaction.user.id
    }
    warn_data[member_id].append(warn_entry)
    save_warn_data()

    embed = discord.Embed(
        title="⚠️ Sanksi Peringatan Diberikan",
        description=(
            f"Anggota: {member.mention}\n"
            f"Alasan: **{reason}**\n"
            f"Total Peringatan: **{len(warn_data[member_id])} kali**"
        ),
        color=CLR_AMBER,
        timestamp=datetime.now(WIB)
    )
    embed.set_footer(text=f"Diberikan oleh {interaction.user.display_name}")
    await interaction.followup.send(embed=embed, ephemeral=False)

    log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
    if log_admin:
        await log_admin.send(f"⚠️ **Peringatan:** {member.mention} diberi peringatan oleh {interaction.user.mention}. Alasan: `{reason}`")

    try:
        dm_embed = discord.Embed(
            title=f"⚠️ Peringatan dari Server {interaction.guild.name}",
            description=(
                f"Anda telah menerima peringatan resmi dari staf server.\n\n"
                f"📝 **Alasan:** {reason}\n"
                f"Mohon patuhi peraturan komunitas demi kenyamanan bersama."
            ),
            color=CLR_AMBER
        )
        await member.send(embed=dm_embed)
    except discord.Forbidden:
        pass

@tree.command(name="warnings", description="Lihat riwayat catatan peringatan anggota.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Anggota yang ingin diperiksa")
@is_admin_prakom()
async def warnings(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    member_id = str(member.id)
    warns = warn_data.get(member_id, [])

    if not warns:
        embed = discord.Embed(
            description=f"✅ {member.mention} memiliki catatan bersih tanpa peringatan.",
            color=CLR_EMERALD
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    desc = f"**Total Akumulasi: {len(warns)} Peringatan**\n\n"
    for i, w in enumerate(warns):
        ts = datetime.fromisoformat(w["timestamp"]).strftime('%d %b %Y, %H:%M WIB')
        admin = interaction.guild.get_member(w["admin"])
        admin_name = admin.display_name if admin else f"Admin ({w['admin']})"
        desc += f"**{i+1}.** `{w['reason']}`\n   └ 🗓️ {ts} • Oleh: **{admin_name}**\n\n"

    embed = discord.Embed(
        title=f"📋 Riwayat Peringatan — {member.display_name}",
        description=desc,
        color=CLR_AMBER
    )
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="clear_warnings", description="Bersihkan seluruh catatan peringatan anggota.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Anggota yang ingin dibersihkan peringatannya")
@is_admin_prakom()
async def clear_warnings(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    member_id = str(member.id)

    if member_id in warn_data:
        del warn_data[member_id]
        save_warn_data()
        embed = discord.Embed(
            description=f"✅ Seluruh catatan peringatan untuk {member.mention} berhasil dihapus bersih.",
            color=CLR_EMERALD
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin:
            await log_admin.send(f"🧹 **Peringatan Dihapus:** Riwayat sanksi {member.mention} dibersihkan oleh {interaction.user.mention}.")
    else:
        await interaction.followup.send(f"ℹ️ {member.mention} tidak memiliki catatan peringatan.", ephemeral=True)

@tree.command(name="mute", description="Timeout / Mute anggota untuk sementara waktu.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    member="Anggota target",
    duration_minutes="Durasi mute dalam menit (maksimal 40320 menit / 28 hari)",
    reason="Alasan mute"
)
@is_admin_prakom()
async def mute(interaction: discord.Interaction, member: discord.Member, duration_minutes: int, reason: str = "Tidak ada alasan"):
    await interaction.response.defer(ephemeral=True)

    if duration_minutes <= 0:
        await interaction.followup.send("❌ Durasi mute harus lebih dari 0 menit.", ephemeral=True)
        return
    if member.id == bot.user.id or member.id == interaction.user.id:
        await interaction.followup.send("❌ Tidak dapat memute diri sendiri atau bot.", ephemeral=True)
        return
    if member.top_role >= interaction.guild.me.top_role:
        await interaction.followup.send("❌ Role anggota tersebut setara atau lebih tinggi dari bot.", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.followup.send("❌ Role anggota tersebut setara atau lebih tinggi dari Anda.", ephemeral=True)
        return

    try:
        if duration_minutes <= 40320:
            duration = timedelta(minutes=duration_minutes)
            await member.timeout(duration, reason=reason)
            embed = discord.Embed(
                title="🔇 Anggota Dimute (Timeout)",
                description=(
                    f"Anggota: {member.mention}\n"
                    f"Durasi: **{duration_minutes} Menit**\n"
                    f"Alasan: **{reason}**"
                ),
                color=CLR_CRIMSON,
                timestamp=datetime.now(WIB)
            )
            embed.set_footer(text=f"Dimute oleh {interaction.user.display_name}")
            await interaction.followup.send(embed=embed, ephemeral=False)
        else:
            mute_role = discord.utils.get(interaction.guild.roles, name=MUTE_ROLE_NAME)
            if not mute_role:
                mute_role = await interaction.guild.create_role(name=MUTE_ROLE_NAME)
            await member.add_roles(mute_role, reason=reason)
            await interaction.followup.send(f"✅ {member.mention} telah dimute via role selama **{duration_minutes} menit**.", ephemeral=False)

        log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin:
            await log_admin.send(f"🔇 **Mute:** {member.mention} dimute selama {duration_minutes} menit oleh {interaction.user.mention}. Alasan: `{reason}`")
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot tidak memiliki izin untuk memute anggota ini.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

@tree.command(name="unmute", description="Lepaskan status timeout / mute anggota.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Anggota target yang akan diunmute")
@is_admin_prakom()
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    was_muted = False

    try:
        if member.is_timed_out():
            await member.timeout(None, reason=f"Unmuted oleh {interaction.user.name}")
            was_muted = True

        mute_role = discord.utils.get(interaction.guild.roles, name=MUTE_ROLE_NAME)
        if mute_role and mute_role in member.roles:
            await member.remove_roles(mute_role, reason=f"Unmuted oleh {interaction.user.name}")
            was_muted = True

        if was_muted:
            embed = discord.Embed(
                description=f"🔊 Status mute / timeout untuk {member.mention} berhasil dicabut.",
                color=CLR_EMERALD
            )
            await interaction.followup.send(embed=embed, ephemeral=False)

            log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
            if log_admin:
                await log_admin.send(f"🔊 **Unmute:** {member.mention} telah diunmute oleh {interaction.user.mention}.")
        else:
            await interaction.followup.send(f"ℹ️ {member.mention} tidak sedang dalam kondisi mute atau timeout.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot tidak memiliki izin untuk mengunmute anggota ini.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

@tree.command(name="kick", description="Keluarkan anggota dari server.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Anggota yang akan dikeluarkan", reason="Alasan pengeluaran")
@is_admin_prakom()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Tidak ada alasan"):
    await interaction.response.defer(ephemeral=True)

    if member.id == bot.user.id or member.id == interaction.user.id:
        await interaction.followup.send("❌ Tidak bisa mengeluarkan diri sendiri atau bot.", ephemeral=True)
        return
    if member.top_role >= interaction.guild.me.top_role:
        await interaction.followup.send("❌ Posisi role anggota setara atau lebih tinggi dari bot.", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.followup.send("❌ Posisi role anggota setara atau lebih tinggi dari Anda.", ephemeral=True)
        return

    try:
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="👢 Anggota Dikeluarkan (Kick)",
            description=f"{member.mention} telah dikeluarkan dari server.\nAlasan: **{reason}**",
            color=CLR_AMBER
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

        log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin:
            await log_admin.send(f"👢 **Kick:** {member.mention} dikeluarkan oleh {interaction.user.mention}. Alasan: `{reason}`")
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot tidak memiliki izin untuk mengeluarkan anggota ini.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

@tree.command(name="ban", description="Blokir permanen (Ban) anggota dari server.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Anggota yang akan diban", reason="Alasan pemblokiran")
@is_admin_prakom()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Tidak ada alasan"):
    await interaction.response.defer(ephemeral=True)

    if member.id == bot.user.id or member.id == interaction.user.id:
        await interaction.followup.send("❌ Tidak bisa memban diri sendiri atau bot.", ephemeral=True)
        return
    if member.top_role >= interaction.guild.me.top_role:
        await interaction.followup.send("❌ Posisi role anggota setara atau lebih tinggi dari bot.", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.followup.send("❌ Posisi role anggota setara atau lebih tinggi dari Anda.", ephemeral=True)
        return

    try:
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="🔨 Anggota Diblokir (Ban)",
            description=f"{member.mention} telah diblokir dari server.\nAlasan: **{reason}**",
            color=CLR_CRIMSON
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

        log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin:
            await log_admin.send(f"🔨 **Ban:** {member.mention} diban oleh {interaction.user.mention}. Alasan: `{reason}`")
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot tidak memiliki izin untuk memban anggota ini.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

@tree.command(name="unban", description="Buka blokir (Unban) anggota berdasarkan User ID.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user_id="ID pengguna Discord yang akan diunban")
@is_admin_prakom()
async def unban(interaction: discord.Interaction, user_id: str):
    await interaction.response.defer(ephemeral=True)
    try:
        user_obj = discord.Object(id=int(user_id.strip()))
        await interaction.guild.unban(user_obj)
        embed = discord.Embed(
            description=f"✅ Blokir akun dengan ID `{user_id}` berhasil dicabut.",
            color=CLR_EMERALD
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

        log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin:
            await log_admin.send(f"🔓 **Unban:** User ID `{user_id}` diunban oleh {interaction.user.mention}.")
    except discord.NotFound:
        await interaction.followup.send(f"❗ Akun dengan ID `{user_id}` tidak ditemukan dalam daftar ban server.", ephemeral=True)
    except ValueError:
        await interaction.followup.send("❌ User ID harus berupa rangkaian angka numerik.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot tidak memiliki izin untuk mengunban anggota.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

@tree.command(name="clear", description="Bersihkan sejumlah pesan di channel ini sekaligus.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(amount="Jumlah pesan yang akan dihapus (1 - 100)")
@is_admin_prakom()
async def clear(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)

    if amount <= 0 or amount > 100:
        await interaction.followup.send("❌ Jumlah pesan harus berada di antara 1 dan 100.", ephemeral=True)
        return

    try:
        deleted = await interaction.channel.purge(limit=amount)
        embed = discord.Embed(
            description=f"🗑️ Sebanyak **{len(deleted)} pesan** berhasil dibersihkan dari channel.",
            color=CLR_EMERALD
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin:
            await log_admin.send(f"🗑️ **Pesan Dihapus:** {len(deleted)} pesan di {interaction.channel.mention} dibersihkan oleh {interaction.user.mention}.")
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot tidak memiliki izin `Manage Messages` di channel ini.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan saat menghapus pesan: {e}", ephemeral=True)

@tree.command(name="add_role", description="Berikan role kepada anggota.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Anggota penerima", role_name="Nama role yang diberikan")
@is_admin_prakom()
async def add_role(interaction: discord.Interaction, member: discord.Member, role_name: str):
    await interaction.response.defer(ephemeral=True)
    role = discord.utils.get(interaction.guild.roles, name=role_name)

    if not role:
        await interaction.followup.send(f"❌ Role `{role_name}` tidak ditemukan di server.", ephemeral=True)
        return
    if role in member.roles:
        await interaction.followup.send(f"ℹ️ {member.mention} sudah memiliki role `{role_name}`.", ephemeral=True)
        return
    if role >= interaction.guild.me.top_role:
        await interaction.followup.send("❌ Role tersebut setara atau lebih tinggi dari posisi role bot.", ephemeral=True)
        return

    try:
        await member.add_roles(role)
        embed = discord.Embed(
            description=f"✅ Role **{role.name}** berhasil disematkan kepada {member.mention}.",
            color=CLR_EMERALD
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

        log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin:
            await log_admin.send(f"➕ **Role Diberikan:** Role `{role_name}` diberikan kepada {member.mention} oleh {interaction.user.mention}.")
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot tidak memiliki izin untuk memberikan role ini.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

@tree.command(name="remove_role", description="Cabut role dari anggota.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(member="Anggota target", role_name="Nama role yang dicabut")
@is_admin_prakom()
async def remove_role(interaction: discord.Interaction, member: discord.Member, role_name: str):
    await interaction.response.defer(ephemeral=True)
    role = discord.utils.get(interaction.guild.roles, name=role_name)

    if not role:
        await interaction.followup.send(f"❌ Role `{role_name}` tidak ditemukan.", ephemeral=True)
        return
    if role not in member.roles:
        await interaction.followup.send(f"ℹ️ {member.mention} tidak memiliki role `{role_name}`.", ephemeral=True)
        return

    try:
        await member.remove_roles(role)
        embed = discord.Embed(
            description=f"✅ Role **{role.name}** berhasil dicabut dari {member.mention}.",
            color=CLR_EMERALD
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

        log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin:
            await log_admin.send(f"➖ **Role Dicabut:** Role `{role_name}` dicabut dari {member.mention} oleh {interaction.user.mention}.")
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot tidak memiliki izin untuk mencabut role ini.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

@tree.command(name="announcement", description="Kirim pengumuman resmi ke channel.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(channel="Channel tujuan", message="Isi teks pengumuman")
@is_admin_prakom()
async def announcement(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    await interaction.response.defer(ephemeral=True)

    try:
        embed = discord.Embed(
            title="📢 PENGUMUMAN RESMI",
            description=message,
            color=CLR_ADHYAKSA_GOLD,
            timestamp=datetime.now(WIB)
        )
        embed.set_footer(text=f"Diumumkan oleh: {interaction.user.display_name} • Kejaksaan RI")
        await channel.send(embed=embed)

        await interaction.followup.send(f"✅ Pengumuman berhasil dipublikasikan di {channel.mention}.", ephemeral=True)
        log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin:
            await log_admin.send(f"📣 **Pengumuman:** Diumumkan ke {channel.mention} oleh {interaction.user.mention}.")
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot tidak memiliki izin mengirim pesan di channel tersebut.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

@tree.command(name="scheduled_announcement", description="Jadwalkan pengumuman resmi ke channel tertentu.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    channel="Channel tujuan",
    waktu="Format: YYYY-MM-DDTHH:MM (contoh: 2026-05-20T08:00)",
    message="Isi teks pengumuman"
)
@is_admin_prakom()
async def scheduled_announcement(interaction: discord.Interaction, channel: discord.TextChannel, waktu: str, message: str):
    await interaction.response.defer(ephemeral=True)
    now = datetime.now(WIB)

    try:
        dt = datetime.fromisoformat(waktu.replace(" ", "T"))
        dt = dt.replace(tzinfo=WIB)

        if dt < now:
            await interaction.followup.send("❌ Waktu pengumuman terjadwal harus berada di masa depan.", ephemeral=True)
            return

        rem_id = str(uuid.uuid4())[:6]
        role_reminders.append({
            "id": rem_id,
            "tipe": "scheduled_announcement",
            "waktu": dt,
            "pesan": message,
            "channel_id": channel.id,
            "creator_id": interaction.user.id
        })
        save_role_reminders()

        embed = discord.Embed(
            title="🗓️ Pengumuman Berhasil Dijadwalkan",
            description=(
                f"Pengumuman resmi akan dikirim otomatis:\n\n"
                f"📅 **Waktu:** {dt.strftime('%d %b %Y, %H:%M WIB')}\n"
                f"📍 **Channel:** {channel.mention}\n"
                f"📝 **Isi:** {message}\n"
                f"🏷️ **ID:** `{rem_id}`"
            ),
            color=CLR_ADHYAKSA_GOLD
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        log_admin = interaction.guild.get_channel(LOGADMIN_CHANNEL_ID)
        if log_admin:
            await log_admin.send(f"🗓️ **Pengumuman Dijadwalkan:** Dijadwalkan ke {channel.mention} pada {dt.strftime('%d %b %Y %H:%M WIB')} oleh {interaction.user.mention}.")
    except ValueError:
        await interaction.followup.send("❌ Format waktu harus `YYYY-MM-DDTHH:MM` (contoh: 2026-05-20T08:00).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)

# ======= GLOBAL ERROR HANDLER =======
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        return
    print(f"Unhandled app command error: {error}")
    err_embed = discord.Embed(
        title="❌ Terjadi Kesalahan",
        description=f"Gagal mengeksekusi perintah:\n`{error}`",
        color=CLR_CRIMSON
    )
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=err_embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=err_embed, ephemeral=True)
    except Exception:
        pass

# ======= JALANKAN BOT =======
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")

    if not TOKEN:
        print("❌ ERROR: Variabel lingkungan 'DISCORD_TOKEN' tidak ditemukan.")
        print("Pastikan Anda telah mengatur DISCORD_TOKEN di file .env atau environment server.")
        exit(1)
    else:
        try:
            from keep_alive import keep_alive
            keep_alive()
            print("🌐 Server Keep-Alive Web aktif di port 8080 (Replit / UptimeRobot)")
        except Exception as e:
            print(f"ℹ️ Server Keep-Alive tidak dijalankan: {e}")

        try:
            bot.run(TOKEN)
        except discord.errors.LoginFailure:
            print("❌ ERROR: Token Discord tidak valid. Harap periksa kembali token Anda di file .env.")
            exit(1)
        except Exception as e:
            print(f"❌ Terjadi kesalahan saat menjalankan bot: {e}")
            exit(1)
