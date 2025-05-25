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
personal_reminders = defaultdict(list)
inactive_tickets = {}  # {channel_id: last_message_time}

# ======= QUOTES & TEMPLATES =======
DAILY_QUOTES = [
    "Tetap semangat, hari ini penuh peluang!",
    "Jangan menyerah, kamu lebih kuat dari yang kamu kira.",
    "Langkah kecil hari ini bisa jadi awal dari hal besar.",
    "Kerja kerasmu akan membuahkan hasil."
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
    "- Tetap semangat dan jaga kesehatan!")

DAILY_DM_TEMPLATE = (
    "Halo {username}! 👋\n\n"
    "Ini pengingat harian khusus untuk kamu:\n"
    "- Sudah cek Mola hari ini?\n"
    "- Jangan lupa buka Mola dan pastikan semua tugas sudah dikerjakan ya.\n"
    "- Semangat terus dan tetap fokus! 💪")


# ======= HELPER FUNCTIONS =======
def is_admin_prakom():

    async def predicate(interaction: discord.Interaction):
        role = discord.utils.get(interaction.user.roles,
                                 name=ADMIN_PRAKOM_ROLE)
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
        user: discord.PermissionOverwrite(read_messages=True,
                                          send_messages=True),
    }

    admin_role = discord.utils.get(guild.roles, name=ADMIN_PRAKOM_ROLE)
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(
            read_messages=True, send_messages=True)

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
    timestamps = [
        ts for ts in timestamps if (now - ts).seconds < SPAM_INTERVAL
    ]
    timestamps.append(now)
    user_messages[message.author.id] = timestamps

    if len(timestamps) > SPAM_THRESHOLD:
        try:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} spam terdeteksi.", delete_after=5)
            mute_role = discord.utils.get(message.guild.roles,
                                          name=MUTE_ROLE_NAME)
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
            await message.channel.send("❌ Tidak bisa ganti nickname.",
                                       delete_after=10)
            return

        role_unverified = discord.utils.get(guild.roles, name="Unverified")
        role_anggota = discord.utils.get(guild.roles, name="Anggota")

        try:
            if role_unverified and role_unverified in member.roles:
                await member.remove_roles(role_unverified)
            if role_anggota and role_anggota not in member.roles:
                await member.add_roles(role_anggota)
        except:
            await message.channel.send("❌ Tidak bisa mengatur role.",
                                       delete_after=10)
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
    try:
        if emoji == "👩":
            await member.add_roles(role_cantik)
            await member.remove_roles(role_anggota)
            await reaction.message.channel.send(
                f"{member.mention} kamu sudah terdaftar sebagai Prakom Cantik."
            )
        elif emoji == "👨":
            await member.add_roles(role_ganteng)
            await member.remove_roles(role_anggota)
            await reaction.message.channel.send(
                f"{member.mention} kamu sudah terdaftar sebagai Prakom Ganteng."
            )
    except Exception:
        pass


# ======= SLASH COMMANDS =======
@tree.command(name="clear",
              description="Hapus sejumlah pesan",
              guild=discord.Object(id=GUILD_ID))
@has_role(ADMIN_PRAKOM_ROLE)
async def clear(interaction: discord.Interaction, jumlah: int):
    if jumlah < 1:
        await interaction.response.send_message("Jumlah harus lebih dari 0.",
                                                ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=jumlah + 1)
    await interaction.response.send_message(
        f"🧹 Berhasil menghapus {len(deleted)-1} pesan.", ephemeral=True)


@tree.command(name="dailyquote",
              description="Tampilkan quote motivasi harian (manual)",
              guild=discord.Object(id=GUILD_ID))
async def dailyquote(interaction: discord.Interaction):
    quote = random.choice(DAILY_QUOTES)
    await interaction.response.send_message(f"💡 Quote hari ini:\n\n{quote}",
                                            ephemeral=True)


@tree.command(name="announce",
              description="Kirim pengumuman ke channel",
              guild=discord.Object(id=GUILD_ID))
@is_admin_prakom()
async def announce(interaction: discord.Interaction, *, message: str):
    channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if not channel:
        await interaction.response.send_message(
            "❌ Channel pengumuman tidak ditemukan.", ephemeral=True)
        return
    await channel.send(f"📢 **Pengumuman:** {message}")
    await interaction.response.send_message("✅ Pengumuman telah dikirim.",
                                            ephemeral=True)


@tree.command(name="ticket",
              description="Buka tiket bantuan",
              guild=discord.Object(id=GUILD_ID))
async def ticket(interaction: discord.Interaction):
    guild = interaction.guild
    channel, error = await create_ticket_channel(guild, interaction.user)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return
    await interaction.response.send_message(
        f"✅ Tiket telah dibuat: {channel.mention}", ephemeral=True)

    # Kirim pesan dengan tombol close tiket
    view = View()
    close_button = Button(label="Tutup Tiket",
                          style=discord.ButtonStyle.red,
                          custom_id="close_ticket")
    view.add_item(close_button)
    await channel.send(
        f"{interaction.user.mention} tiket kamu sudah dibuka. Klik tombol dibawah untuk menutup tiket.",
        view=view)


@tree.command(name="userinfo",
              description="Tampilkan info pengguna",
              guild=discord.Object(id=GUILD_ID))
async def userinfo(interaction: discord.Interaction,
                   member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"Info pengguna: {member}",
                          color=discord.Color.blue())
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Nama", value=member.name, inline=True)
    embed.add_field(name="Nickname",
                    value=member.nick or "Tidak ada",
                    inline=True)
    embed.add_field(name="Join Server",
                    value=member.joined_at.strftime("%Y-%m-%d"),
                    inline=True)
    embed.add_field(name="Level",
                    value=user_level.get(member.id, 0),
                    inline=True)
    embed.add_field(name="XP", value=user_xp.get(member.id, 0), inline=True)
    embed.set_thumbnail(
        url=member.avatar.url if member.avatar else member.default_avatar.url)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ======= BUTTON HANDLER =======
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id")
    if custom_id == "close_ticket":
        channel = interaction.channel
        guild = interaction.guild

        if not channel.name.startswith("tiket-"):
            await interaction.response.send_message(
                "❌ Ini bukan channel tiket.", ephemeral=True)
            return

        await interaction.response.send_message(
            "⏳ Tiket akan ditutup dalam 5 detik...", ephemeral=True)

        category_archive = discord.utils.get(guild.categories,
                                             name="Archive Tiket")
        if not category_archive:
            category_archive = await guild.create_category("Archive Tiket")

        await channel.edit(category=category_archive)
        await asyncio.sleep(5)
        await channel.delete()


# ======= RUN BOT =======
bot.run(os.getenv("DISCORD_TOKEN"))
