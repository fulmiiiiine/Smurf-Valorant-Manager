import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import aiohttp
import logging
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageColor

from pilmoji import Pilmoji
from pilmoji.source import TwitterEmojiSource
from io import BytesIO
import os
from datetime import datetime, timedelta
import json
import time
import random
import numpy as np
from zoneinfo import ZoneInfo
import re
import ssl
from imapclient import IMAPClient, exceptions as imap_exceptions
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv
import traceback 
import psutil 

load_dotenv()

with open('config.json', 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

DISCORD_TOKEN = CONFIG['discord_token']
CHANNEL_ID = CONFIG['channels']['main_channel_id']
LEADERBOARD_CHANNEL_ID = CONFIG['channels']['leaderboard_channel_id']
LEADERBOARD_MESSAGE_ID = CONFIG['messages']['leaderboard_message_id']
ERROR_LOG_CHANNEL_ID = CONFIG['channels']['error_log_channel_id']
API_KEYS = CONFIG['api']['keys']
API_KEY = API_KEYS[0]
REGION = CONFIG['api']['region']
ADMIN_USER_ID = CONFIG['admin_user_id']
AUTH_GUILD_ID = CONFIG['guilds']['auth_guild_id']
GUILD_ID = AUTH_GUILD_ID
CODES_CHANNEL_ID = CONFIG['channels']['codes_channel_id']
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", CONFIG['email']['address'])
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", CONFIG['email']['password'])
IMAP_SERVER = os.getenv("IMAP_SERVER", CONFIG['email']['imap_server'])
IMAP_PORT = int(os.getenv("IMAP_PORT", CONFIG['email']['imap_port']))
CHECK_INTERVAL = CONFIG['email']['check_interval']
CODE_MAX_AGE_MINUTES = CONFIG['email']['code_max_age_minutes']
CARD_WIDTH, CARD_HEIGHT = CONFIG['settings']['card_width'], CONFIG['settings']['card_height']
UPDATE_INTERVAL = CONFIG['settings']['update_interval']
CACHE_FILE = CONFIG['file_paths']['cache_file']
CODES_HISTORY_FILE = CONFIG['file_paths']['codes_history_file']
HARDCODED_MESSAGE_IDS = CONFIG['messages']['hardcoded_slot_ids']
RANK_COLORS = CONFIG['rank_colors']
USERS = CONFIG['users']


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("valorant_tracker.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('ValorantTracker')


CACHED_BACKGROUND = None


BACKGROUND_CACHE = {}

def get_rank_background(rank_color_hex):
    
    global BACKGROUND_CACHE
    if rank_color_hex in BACKGROUND_CACHE:
        return BACKGROUND_CACHE[rank_color_hex].copy()
    
    
    try:
        base_rgb = ImageColor.getcolor(rank_color_hex, "RGB")
    except:
        base_rgb = (40, 40, 50) 

    
    
    color1 = (
        int(base_rgb[0] * 0.2),
        int(base_rgb[1] * 0.2),
        int(base_rgb[2] * 0.2)
    )
    
    color2 = (
        int(base_rgb[0] * 0.1), 
        int(base_rgb[1] * 0.1), 
        int(base_rgb[2] * 0.1)
    )
    
    width, height = CARD_WIDTH, CARD_HEIGHT
    base = Image.new('RGB', (width, height), color1)
    draw = ImageDraw.Draw(base)
    
    
    for i in range(width):
        r = int(color1[0] + (color2[0] - color1[0]) * i / width)
        g = int(color1[1] + (color2[1] - color1[1]) * i / width)
        b = int(color1[2] + (color2[2] - color1[2]) * i / width)
        draw.line([(i, 0), (i, height)], fill=(r, g, b))
        
    BACKGROUND_CACHE[rank_color_hex] = base
    return base.copy()

def get_rank_color(rank_name):
    
    rank_name_upper = rank_name.upper()
    for rank, color in RANK_COLORS.items():
        if rank in rank_name_upper:
            return color
    return RANK_COLORS["UNRANKED"]


def get_dominant_color(pil_img, default_color="#FFFFFF"):
    
    if not pil_img:
        return default_color
        
    try:
        
        
        img = pil_img.copy()
        img = img.resize((1, 1), resample=0) 
        
        
        
        
        img = pil_img.copy().convert("RGBA")
        img.thumbnail((50, 50))
        
        
        
        
        
        
        
        
        
        qtp = img.quantize(colors=5, method=2) 
        dominant = qtp.getpalette()[:3] 
        return (dominant[0], dominant[1], dominant[2])
    except Exception as e:
        
        return default_color




def get_rome_time():
    
    try:
        
        return datetime.now(ZoneInfo("Europe/Rome"))
    except Exception:
        
        
        
        
        
        utc_now = datetime.utcnow()
        
        
        month = utc_now.month
        is_dst = 3 < month < 11 
        offset = 2 if is_dst else 1
        return utc_now + timedelta(hours=offset)


class AsyncAssetManager:
    
    def __init__(self):
        self._cache = {} 
        self._locks = {} 

    async def get_image(self, session, url, width=None, height=None):
        
        if not url:
            return None
            
        
        
        cache_key = (url, width, height)
        
        if cache_key in self._cache:
            return self._cache[cache_key]

        
        if url not in self._locks:
            self._locks[url] = asyncio.Lock()
            
        async with self._locks[url]:
            
            if cache_key in self._cache:
                return self._cache[cache_key]
                
            try:
                
                
                original_key = (url, None, None)
                base_img = self._cache.get(original_key)
                
                if not base_img:
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.read()
                            base_img = Image.open(BytesIO(data)).convert("RGBA")
                            
                            self._cache[original_key] = base_img
                        else:
                            logger.error(f"Asset download failed: {response.status} for {url}")
                            return None
            
                
                if width and height:
                    
                    final_img = base_img.resize((width, height), Image.Resampling.LANCZOS)
                else:
                    final_img = base_img

                self._cache[cache_key] = final_img
                return final_img
                
            except Exception as e:
                logger.error(f"Error processing asset {url}: {e}")
                return None


ASSETS = AsyncAssetManager()


class FontManager:
    def __init__(self):
        try:
            self.header = ImageFont.truetype("fonts/arialbd.ttf", 32)
            self.name = ImageFont.truetype("fonts/arialbd.ttf", 22)
            self.stats = ImageFont.truetype("fonts/arial.ttf", 18)
            self.card_large = ImageFont.truetype("fonts/arialbd.ttf", 20)
            self.card_medium = ImageFont.truetype("fonts/arial.ttf", 16)
            self.card_small = ImageFont.truetype("fonts/arial.ttf", 12)
            self.card_ban = ImageFont.truetype("fonts/arialbd.ttf", 14)
        except:
            logger.warning("⚠️ Font Arial non trovati, uso default.")
            self.header = ImageFont.load_default()
            self.name = ImageFont.load_default()
            self.stats = ImageFont.load_default()
            self.card_large = ImageFont.load_default()
            self.card_medium = ImageFont.load_default()
            self.card_small = ImageFont.load_default()
            self.card_ban = ImageFont.load_default()


FONTS = FontManager()


def create_leaderboard_image(users_data_list):
    
    if not users_data_list:
        return None
        
    row_height = 70
    header_height = 80
    width = 650
    total_height = header_height + (len(users_data_list) * row_height) + 20
    
    
    base_color = (25, 25, 35)
    img = Image.new('RGB', (width, total_height), base_color)
    
    
    draw = ImageDraw.Draw(img)
    
    
    with Pilmoji(img, source=TwitterEmojiSource) as pilmoji:
        
        
        draw.rectangle([(0, 0), (width, header_height)], fill=(40, 40, 55))
        
        
        pilmoji.text((20, 25), "🏆 SERVER LEADERBOARD", fill="white", font=FONTS.header)
        
        
        update_time = get_rome_time().strftime("%H:%M")
        draw.text((width - 100, 30), f"Agg: {update_time}", fill="#888888", font=FONTS.stats)

        for idx, user in enumerate(users_data_list):
            y = header_height + (idx * row_height) + 10
            
            
            is_first = (idx == 0)
            is_last = (idx == len(users_data_list) - 1) and (len(users_data_list) > 1)
            
            row_bg = (35, 35, 45)
            text_color = (220, 220, 220)
            rank_text_color = get_rank_color(user['rank'])
            
            if is_first:
                row_bg = (255, 215, 0)  
                text_color = (0, 0, 0)
                
                rank_text_color = (50, 50, 50) 
            elif is_last:
                row_bg = (80, 20, 20)   
                text_color = (255, 200, 200)
            
            
            draw.rounded_rectangle([(10, y), (width-10, y + row_height - 5)], radius=10, fill=row_bg)
            
            
            pos_text = f"#{idx + 1}"
            draw.text((30, y + 22), pos_text, fill=text_color, font=FONTS.name)
            
            
            icon_x = 100
            if user.get('rank_icon'):
                try:
                    
                    
                    
                    
                    
                    img.paste(user['rank_icon'], (icon_x, y + 8), user['rank_icon'])
                except Exception as e:
                    logger.error(f"Err icona leaderboard {user['name']}: {e}")
            
            
            name_x = 170
            display_name = user['name']
            if is_first: display_name += " 👑"
            if is_last: display_name += " 🤡"
            
            
            pilmoji.text((name_x, y + 22), display_name, fill=text_color, font=FONTS.name)
            
            
            stats_text = f"{user['rank']} - {user['elo']} RR"
            
            stats_width = draw.textlength(stats_text, font=FONTS.stats)
            draw.text((width - stats_width - 40, y + 25), stats_text, fill=rank_text_color, font=FONTS.stats)

    bio = BytesIO()
    img.save(bio, format="PNG", optimize=True)
    bio.seek(0)
    return bio

def create_rank_card(user_data, rank_name="ERROR", elo=0, ranking_in_tier=0, rank_icon=None, agent_img=None, account_level=0, ban_text=None):
    
    
    rank_color = get_rank_color(rank_name)
    
    
    base = get_rank_background(rank_color)
    draw = ImageDraw.Draw(base)
    
    
    if agent_img:
        try:
            
            
            
            agent = agent_img 
            
            mask = Image.new('L', (80, 80), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, 80, 80), fill=255)
            agent_circle = Image.new('RGBA', (80, 80), (0,0,0,0))
            agent_circle.paste(agent, (0,0), mask)
            
            border_size = 3
            border_img = Image.new('RGBA', (80 + border_size*2, 80 + border_size*2), (0,0,0,0))
            border_draw = ImageDraw.Draw(border_img)
            
            
            try:
                
                if hasattr(agent, 'dominant_color'):
                    dom_color = agent.dominant_color
                else:
                    
                    dom_color = get_dominant_color(agent)
                    agent.dominant_color = dom_color 
                    
                border_draw.ellipse((0, 0, 80 + border_size*2, 80 + border_size*2), fill=dom_color)
            except Exception:
                border_draw.ellipse((0, 0, 80 + border_size*2, 80 + border_size*2), fill="#FFFFFF")
                
            
            
            
            border_draw.ellipse((border_size, border_size, 80 + border_size, 80 + border_size), fill="#202025") 
            
            border_img.paste(agent_circle, (border_size, border_size), agent_circle)
            base.paste(border_img, (20, (CARD_HEIGHT - 80 - border_size*2) // 2), border_img)
        except Exception as e:
            logger.error(f"Errore processamento immagine agent: {e}")
    
    
    
    if rank_icon:
        try:
            
            rank_img = rank_icon 
            
            glow = Image.new('RGBA', (80, 80), (0,0,0,0))
            glow_draw = ImageDraw.Draw(glow)
            for i in range(5):
                alpha = max(0, 100 - i * 20)
                try:
                    rgb_color = ImageColor.getcolor(rank_color, "RGB")
                except Exception:
                    rgb_color = (255,255,255)
                glow_draw.ellipse((5-i, 5-i, 75+i, 75+i), outline=(*rgb_color, alpha))
            
            base.paste(glow, (CARD_WIDTH - 85, (CARD_HEIGHT - 80) // 2), glow)
            
            base.paste(rank_img, (CARD_WIDTH - 80, (CARD_HEIGHT - 70) // 2), rank_img)
        except Exception as e:
            logger.error(f"Errore processamento icona rank: {e}")
    elif rank_name in ("ERROR", "UNRANKED"):
        try:
            unrated_icon = Image.new('RGBA', (70,70), (0,0,0,0))
            unrated_draw = ImageDraw.Draw(unrated_icon)
            unrated_draw.ellipse((0,0,70,70), outline=rank_color, width=3)
            unrated_draw.text((30,25), "?", fill=rank_color, font=FONTS.card_large)
            base.paste(unrated_icon, (CARD_WIDTH - 80, (CARD_HEIGHT - 70)//2), unrated_icon)
        except Exception as e:
            logger.error(f"Errore creazione icona unrated: {e}")
    
    
    
    with Pilmoji(base, source=TwitterEmojiSource) as pilmoji:
        pilmoji.text((112, 22), user_data['name'], fill='#000000', font=FONTS.card_large)
        pilmoji.text((110, 20), user_data['name'], fill='white', font=FONTS.card_large)
    
    rank_text = f"{rank_name}"
    
    
    if rank_name in ["ERROR", "UNRANKED"] and 0 < account_level < 20:
        rank_text = "UNRANKABLE"
        
    if ranking_in_tier > -1 and rank_name not in ["ERROR", "UNRANKED"]:
        rank_text += f" ({ranking_in_tier}/100)"
        
    draw.text((112, 52), rank_text, fill='#000000', font=FONTS.card_medium)
    draw.text((110, 50), rank_text, fill=rank_color, font=FONTS.card_medium)
    
    
    if ban_text:
        
        rank_w = draw.textlength(rank_text, font=FONTS.card_medium)
        ban_x = int(112 + rank_w + 15) 
        
        
        with Pilmoji(base, source=TwitterEmojiSource) as pilmoji:
            pilmoji.text((ban_x, 52), ban_text, fill='#000000', font=FONTS.card_ban) 
            pilmoji.text((ban_x - 1, 51), ban_text, fill='#FF3333', font=FONTS.card_ban) 

    
    
    
    
    time_str = get_rome_time().strftime("%H:%M")
    
    time_w = draw.textlength(time_str, font=FONTS.card_small)
    draw.text((CARD_WIDTH - time_w - 10, CARD_HEIGHT - 20), time_str, fill="#AAAAAA", font=FONTS.card_small)

    
    if rank_name in ["UNRANKED", "ERROR"] and account_level > 0:
        level_text = f"Level: {account_level}"
        draw.text((112, 82), level_text, fill='#000000', font=FONTS.card_medium)
        draw.text((110, 80), level_text, fill='#FFD700', font=FONTS.card_medium)  
    elif elo > 0 and rank_name not in ["ERROR", "UNRANKED"]:
        draw.text((112, 82), f"ELO: {elo}", fill='#000000', font=FONTS.card_medium)
        draw.text((110, 80), f"ELO: {elo}", fill='#CCCCCC', font=FONTS.card_medium)
    
    login_text = f"Username: {user_data['login']}"
    
    draw.text((112, 118), login_text, fill='#000000', font=FONTS.card_medium)
    draw.text((110, 116), login_text, fill='#7289DA', font=FONTS.card_medium)
    
    
    
    draw.rounded_rectangle([(5,5),(CARD_WIDTH-6, CARD_HEIGHT-6)], radius=10, outline='#444444', width=2)
    
    bio = BytesIO()
    base.save(bio, format="PNG", optimize=True)
    bio.seek(0)
    return bio


class ValorantBot(commands.Bot):
    def __init__(self):
        
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        intents.members = True 
        super().__init__(
            command_prefix='!',  
            intents=intents,
            help_command=None
        )
        
        
        self.message_cache = self.load_message_cache()
        self.session = None
        self.is_updating = False
        self.channel = None
        
        
        self.email_client = None
        self.email_lock = asyncio.Lock() 
        self.codes_channel = None
        self.last_email_check_time = 0 
        
        
        self.codes_history = self.load_codes_history()
        
        
        
        self.last_data_cache = {}
        
        
        self.users_data_cache = []
        
        
        self.watchdog_metrics = {
            'update_restarts': 0,
            'email_restarts': 0,
            'last_latency': 0,
            'start_time': time.time()
        }
        
        
        self.update_task = None
        self.email_task = None
        
        self.watchdog_task = None
        
        
        self.commands_synced = False

        
        self.skip_initial_update = False

        
        self.next_update_time = None
        
        
        self.api_key_index = 0
        
    def get_headers(self):
        
        key = API_KEYS[self.api_key_index % len(API_KEYS)]
        return {'Authorization': key}
    
    def rotate_api_key(self):
        
        self.api_key_index = (self.api_key_index + 1) % len(API_KEYS)
        new_key = API_KEYS[self.api_key_index % len(API_KEYS)]
        
        safe_key = "..." + new_key[-4:] if len(new_key) > 4 else "???"
        logger.warning(f"🔄 Rate Limit o Errore: Rotazione API Key. Nuova Key: {safe_key}")

    
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        
        if interaction.user.id == ADMIN_USER_ID:
            return True
        
        
        auth_guild = self.get_guild(AUTH_GUILD_ID)
        
        
        if not auth_guild:
            
            return False
            
        
        member = auth_guild.get_member(interaction.user.id)
        
        if member is not None:
            return True
        else:
            
            await interaction.response.send_message("❌ Accesso Negato: Devi essere nel server ufficiale per usare questo bot.", ephemeral=True)
            return False

    def load_message_cache(self):
        
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    logger.info("✅ Cache messaggi caricata da file")
                    return data
        except Exception as e:
            logger.error(f"❌ Errore caricamento cache: {e}")
        return {}
    
    def save_message_cache(self):
        
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump(self.message_cache, f)
                logger.info("✅ Cache messaggi salvata su file")
        except Exception as e:
            logger.error(f"❌ Errore salvataggio cache: {e}")
    
    
    def load_codes_history(self):
        
        try:
            if os.path.exists(CODES_HISTORY_FILE):
                with open(CODES_HISTORY_FILE, 'r') as f:
                    data = json.load(f)
                    
                    logger.info(f"✅ Storico codici caricato ({len(data)} codici)")
                    return set(data)
        except Exception as e:
            logger.error(f"❌ Errore caricamento storico codici: {e}")
        return set()

    def save_code_to_history(self, code):
        
        try:
            self.codes_history.add(code)
            
            with open(CODES_HISTORY_FILE, 'w') as f:
                json.dump(list(self.codes_history), f)
            logger.info(f"💾 Codice {code} salvato nello storico JSON")
        except Exception as e:
            logger.error(f"❌ Errore salvataggio storico codici: {e}")

    def get_user_message_id(self, puuid):
        return self.message_cache.get(puuid)
    
    def set_user_message_id(self, puuid, message_id):
        self.message_cache[puuid] = message_id
        self.save_message_cache()
    
    async def setup_hook(self):
        
        logger.info("🔧 Esecuzione setup hook...")
        
        
        if self.session is None or getattr(self.session, "closed", False):
            self.session = aiohttp.ClientSession()
            logger.info("✅ Sessione HTTP creata")
        
        
        try:
            logger.info("🔄 Avvio sincronizzazione comandi slash GLOBALE...")
            
            
            if GUILD_ID:
                guild_obj = discord.Object(id=GUILD_ID)
                self.tree.clear_commands(guild=guild_obj)

            
            synced = await self.tree.sync()
            logger.info(f"✅ {len(synced)} comandi sincronizzati GLOBALMENTE.")
            self.commands_synced = True
                    
        except Exception as e:
            logger.error(f"❌ Errore critico durante sync: {e}")
    
    async def on_ready(self):
        
        logger.info(f'✅ Bot connesso come {self.user} (ID: {self.user.id})')
        
        
        if self.commands_synced:
            logger.info("✅ Comandi slash sincronizzati e pronti all'uso")
        else:
            logger.warning("⚠️ Comandi slash potrebbero non essere sincronizzati")
        
        
        self.channel = self.get_channel(CHANNEL_ID)
        self.codes_channel = self.get_channel(CODES_CHANNEL_ID)
        
        if not self.channel:
            logger.error(f"❌ Canale ID {CHANNEL_ID} non trovato")
            return
        
        if not self.codes_channel:
            logger.error(f"❌ Canale codici ID {CODES_CHANNEL_ID} non trovato")
        else:
            logger.info(f"✅ Canale codici configurato: {self.codes_channel.name}")
        
        
        await self.initialize_hardcoded_cache()
        
        
        await self.preload_message_cache()
        
        
        self.start_background_tasks()

        
        if not self.watchdog_task or self.watchdog_task.done():
            self.watchdog_task = self.watchdog_loop.start()
            logger.info("🐕 Watchdog Supervisor avviato!")
    
    async def initialize_hardcoded_cache(self):
        
        
        if not self.message_cache:
            for i, user in enumerate(USERS):
                if i < len(HARDCODED_MESSAGE_IDS):
                    self.message_cache[user['puuid']] = HARDCODED_MESSAGE_IDS[i]
            self.save_message_cache()
            logger.info("✅ Cache inizializzata con IDs hardcoded")
    
    async def preload_message_cache(self):
        
        if not self.channel:
            return
            
        logger.info("🔍 Verifica cache messaggi...")
        to_delete = []
        
        for puuid, msg_id in list(self.message_cache.items()):
            try:
                await self.channel.fetch_message(msg_id)
                logger.info(f"✅ Messaggio {msg_id} trovato per PUUID {puuid}")
            except discord.NotFound:
                logger.warning(f"⚠️ Messaggio {msg_id} non trovato - sarà ricreato")
                to_delete.append(puuid)
            except Exception as e:
                logger.warning(f"⚠️ Errore verifica messaggio {msg_id}: {e}")
        
        for puuid in to_delete:
            self.message_cache.pop(puuid, None)
        
        if to_delete:
            self.save_message_cache()
            logger.info("✅ Cache aggiornata dopo verifica")

    
    async def send_crash_log(self, source, error):
        
        try:
            error_channel = self.get_channel(ERROR_LOG_CHANNEL_ID)
            if not error_channel:
                logger.critical(f"❌ Canale Log Errori {ERROR_LOG_CHANNEL_ID} non trovato!")
                return

            
            
            tb_list = traceback.format_exception(type(error), error, error.__traceback__, limit=20)
            tb_str = "".join(tb_list)
            
            
            if len(tb_str) > 1800:
                tb_str = f"... (TRUNCATED)\n{tb_str[-1750:]}"
            
            msg = f"🚨 **CRASH DETECTED IN {source}** 🚨\n```python\n{tb_str}\n```"
            
            try:
                await error_channel.send(msg)
            except Exception:
                
                await error_channel.send(f"⚠️ <@{ADMIN_USER_ID}> CRASH CRITICO IN {source} MA IMPOSSIBILE INVIARE TESTO.")
                
                
                try:
                    full_tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
                    file = discord.File(BytesIO(full_tb.encode('utf-8')), filename="crash_log_full.txt")
                    await error_channel.send(file=file)
                except Exception as file_err:
                    logger.critical(f"Impossibile inviare nemmeno il file di log: {file_err}")

        except Exception as e:
            
            logger.critical(f"IMPOSSIBILE INVIARE CRASH LOG A DISCORD: {e}")
            traceback.print_exc()

    def start_background_tasks(self):
        
        logger.info("🚀 Avvio task in background...")
        
        
        if not self.update_task or self.update_task.done():
            self.update_task = asyncio.create_task(self.update_loop_with_restart())
        
        
        if EMAIL_ADDRESS and EMAIL_PASSWORD:
            if not self.email_task or self.email_task.done():
                self.email_task = asyncio.create_task(self.email_loop_with_restart())
        else:
            logger.warning("⚠️ Credenziali Gmail non configurate")

        
        if not self.watchdog_task or self.watchdog_task.done():
            self.watchdog_task = self.watchdog_loop.start()
            logger.info("🐕 Watchdog Supervisor avviato da start_background_tasks")

    def restart_update_timer(self):
        
        try:
            
            self.skip_initial_update = True
            
            self.is_updating = False 
            if self.update_task and not self.update_task.done():
                self.update_task.cancel()
                logger.info("⏹️ Update task cancellato per riavvio timer")
        except Exception as e:
            logger.error(f"❌ Errore cancellazione update task: {e}")
        
        self.update_task = asyncio.create_task(self.update_loop_with_restart())
        logger.info("✅ Timer di aggiornamento riavviato (countdown ripartito)")

    
    def get_next_update_countdown(self):
        
        if not self.next_update_time:
            return "Sconosciuto"
        
        current_time = time.time()
        remaining_time = max(0, self.next_update_time - current_time)
        
        hours = int(remaining_time // 3600)
        minutes = int((remaining_time % 3600) // 60)
        seconds = int(remaining_time % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
        
    async def fetch_with_retry(self, url, description="API Call"):
        
        max_retries = len(API_KEYS) 
        for i in range(max_retries):
            headers = self.get_headers()
            try:
                async with self.session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:
                        self.rotate_api_key()
                        logger.warning(f"⚠️ 429 Rate Limit su {description}. Tentativo {i+1}/{max_retries}. Ruoto Key...")
                        await asyncio.sleep(0.5) 
                        continue 
                    elif response.status == 404:
                         logger.warning(f"❌ 404 Not Found su {description}")
                         return None
                    else:
                        logger.error(f"❌ Errore {response.status} su {description}")
                        return None
            except asyncio.TimeoutError:
                logger.error(f"❌ Timeout su {description}")
                return None
            except Exception as e:
                logger.error(f"❌ Eccezione su {description}: {e}")
                return None
        
        logger.error(f"❌ Falliti tutti i retry per {description}")
        return None

    
    async def update_loop_with_restart(self):
        
        while not self.is_closed():
            try:
                await self.update_loop()
            except asyncio.CancelledError:
                logger.info("Update Loop Cancellato manualmente.")
                
                self.is_updating = False
                break 
            except Exception as e:
                logger.error(f"❌ CRASH Update Loop: {e}")
                self.is_updating = False 
                await self.send_crash_log("UPDATE LOOP", e)
                logger.info("🔄 Resurrezione Update Loop in 60 secondi...")
                await asyncio.sleep(60)
    
    
    async def email_loop_with_restart(self):
        
        while not self.is_closed():
            try:
                await self.check_email_for_codes()
            except asyncio.CancelledError:
                logger.info("Email Loop Cancellato manualmente.")
                break
            except Exception as e:
                logger.error(f"❌ CRASH Email Loop: {e}")
                await self.send_crash_log("EMAIL LOOP", e)
                logger.info("🔄 Resurrezione Email Loop in 60 secondi...")
                self.email_client = None 
                await asyncio.sleep(60)

    
    async def run_watchdog_checks(self, report_channel=False):
        
        
        status_report = [] 
        issues_found = False
        repaired_actions = []
        
        
        self.watchdog_metrics['last_latency'] = round(self.latency * 1000, 2)
        
        
        status_channel = self.get_channel(ERROR_LOG_CHANNEL_ID)
        
        
        update_state = "UNKNOWN"
        update_detail = ""
        
        if not self.update_task or self.update_task.done():
            
            update_state = "DEAD 💀"
            issues_found = True
            self.watchdog_metrics['update_restarts'] += 1
            
            
            exc_msg = "Nessuna eccezione registrata."
            if self.update_task and self.update_task.done():
                try:
                    exc = self.update_task.exception()
                    if exc: exc_msg = f"{type(exc).__name__}: {exc}"
                except: pass
            
            update_detail = f"Task Crashato. Err: {exc_msg}"
            repaired_actions.append(f"🛠️ **Update Loop**: Riavviato (Crash #{self.watchdog_metrics['update_restarts']})")
            
            
            self.is_updating = False
            self.update_task = asyncio.create_task(self.update_loop_with_restart())
            
        elif self.next_update_time and (time.time() - self.next_update_time > 300):
            
            update_state = "STUCK 🥶"
            issues_found = True
            self.watchdog_metrics['update_restarts'] += 1
            
            overdue_sec = int(time.time() - self.next_update_time)
            update_detail = f"Loop bloccato da {overdue_sec}s"
            repaired_actions.append(f"🔨 **Update Loop**: Kill & Riavvio forzato (Stuck)")
            
            
            if self.update_task: self.update_task.cancel()
            self.is_updating = False
            self.update_task = asyncio.create_task(self.update_loop_with_restart())
            self.next_update_time = time.time() + UPDATE_INTERVAL 
            
        else:
            update_state = "OPERATIONAL 🟢"
            
            if self.next_update_time:
                remaining = int(self.next_update_time - time.time())
                update_detail = f"Prossimo ciclo in {remaining // 60}m {remaining % 60}s"
            else:
                update_detail = "In attesa di schedulazione"

        
        email_state = "UNKNOWN"
        email_detail = ""
        
        if EMAIL_ADDRESS:
            if not self.email_task or self.email_task.done():
                
                email_state = "DEAD 💀"
                issues_found = True
                self.watchdog_metrics['email_restarts'] += 1
                repaired_actions.append(f"🛠️ **Email Loop**: Riavviato (Crash #{self.watchdog_metrics['email_restarts']})")
                
                
                self.email_task = asyncio.create_task(self.email_loop_with_restart())
                
            elif self.last_email_check_time > 0 and (time.time() - self.last_email_check_time > 300):
                
                email_state = "FROZEN ❄️"
                issues_found = True
                self.watchdog_metrics['email_restarts'] += 1
                
                frozen_sec = int(time.time() - self.last_email_check_time)
                email_detail = f"Heartbeat fermo da {frozen_sec}s"
                repaired_actions.append(f"🔨 **Email Loop**: Riavvio forzato (Frozen)")
                
                
                if self.email_task: self.email_task.cancel()
                self.email_task = asyncio.create_task(self.email_loop_with_restart())
                self.last_email_check_time = time.time()
            else:
                email_state = "OPERATIONAL 🟢"
                if self.last_email_check_time > 0:
                     ago = int(time.time() - self.last_email_check_time)
                     email_detail = f"Ultimo heartbeat: {ago}s fa"
        else:
            email_state = "DISABLED ⚪"
            email_detail = "Credenziali non configurate"

        
        latency_str = f"{self.watchdog_metrics['last_latency']} ms"
        uptime_sec = int(time.time() - self.watchdog_metrics['start_time'])
        uptime_str = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m"
        
        
        
        if issues_found or report_channel:
            
            color = 0x2ECC71 if not issues_found else 0xE67E22 
            title = "🛡️ Watchdog Status Report" if not issues_found else "🚑 Watchdog Intervention"
            
            embed = discord.Embed(title=title, color=color, timestamp=datetime.utcnow())
            
            
            embed.add_field(
                name=f"🔄 Update Module [{update_state}]", 
                value=f"Status: {update_detail}\nRestarts: {self.watchdog_metrics['update_restarts']}", 
                inline=False 
            )
            
            
            embed.add_field(
                name=f"📧 Email Module [{email_state}]", 
                value=f"Status: {email_detail}\nRestarts: {self.watchdog_metrics['email_restarts']}", 
                inline=False
            )
            
            
            embed.add_field(
                name="📈 System Vitals", 
                value=f"Latency: `{latency_str}`\nUptime: `{uptime_str}`", 
                inline=True
            )
            
            
            if repaired_actions:
                embed.add_field(
                    name="🔧 Actions Taken", 
                    value="\n".join(repaired_actions), 
                    inline=False
                )
            
            
            if status_channel:
                try:
                    await status_channel.send(embed=embed)
                except Exception as e:
                    logger.error(f"Watchdog failed to send embed: {e}")
            
            
            return f"Status: {update_state} / {email_state} | Actions: {len(repaired_actions)}"
            
        return "All Systems Operational"

    
    @tasks.loop(seconds=120)
    async def watchdog_loop(self):
        
        await self.wait_until_ready()
        await self.run_watchdog_checks()

    
    async def safe_discord_request(self, func, *args, max_retries=3, **kwargs):
        
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except discord.HTTPException as e:
                if e.status == 429:  
                    retry_after = getattr(e, 'retry_after', None) or 2.0
                    logger.warning(f"⚠️ Rate limit, attesa {retry_after}s (tentativo {attempt+1}/{max_retries})")
                    await asyncio.sleep(min(retry_after * 1.5, 30))  
                    continue
                elif e.status >= 500:  
                    logger.warning(f"⚠️ Errore server Discord {e.status}, retry in {2**(attempt+1)}s")
                    await asyncio.sleep(2**(attempt+1))
                    continue
                else:
                    raise
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"⚠️ Errore richiesta Discord: {e}, retry in {2**(attempt+1)}s")
                await asyncio.sleep(2**(attempt+1))
        
        raise Exception(f"Fallimento dopo {max_retries} tentativi")
    
    async def get_valorant_rank(self, puuid, name="User"):
        
        url = f'https://api.henrikdev.xyz/valorant/v2/by-puuid/mmr/{REGION}/{puuid}'
        
        data = await self.fetch_with_retry(url, f"get_valorant_rank({name})")
        
        if data:
            current_data = data.get('data', {}).get('current_data', {})
            rank_name = current_data.get('currenttierpatched', 'UNRANKED')
            icon_url = current_data.get('images', {}).get('large')
            elo = current_data.get('elo', 0)
            mmr_change = current_data.get('mmr_change_to_last_game', 0)
            ranking_in_tier = current_data.get('ranking_in_tier', 0)
            current_tier = current_data.get('currenttier', 0) 
            
            logger.info(f"Dati estratti - Rank: {rank_name}, Tier: {current_tier}, RR: {ranking_in_tier}, Elo: {elo}")
            return rank_name, icon_url, elo, ranking_in_tier, current_tier
            
        
        
        
        cached_sig = self.last_data_cache.get(puuid)
        if cached_sig:
            
            if len(cached_sig) >= 7:
                 rank_name, elo, ranking_in_tier, current_tier = cached_sig[0], cached_sig[1], cached_sig[2], cached_sig[6]
            else:
                 rank_name, elo, ranking_in_tier = cached_sig[0], cached_sig[1], cached_sig[2]
                 current_tier = 0 
                 
            logger.info(f"🛡️ Graceful Degradation attiva per {puuid}: Uso dati cache ({rank_name})")
            
            return rank_name, None, elo, ranking_in_tier, current_tier
        
        return "ERROR", None, 0, 0, 0

    async def get_last_match_agent(self, puuid):
        
        url = f'https://api.henrikdev.xyz/valorant/v3/by-puuid/matches/{REGION}/{puuid}?size=1'
        
        data = await self.fetch_with_retry(url, f"get_matches({puuid})")
        
        if data:
            matches = data.get('data', [])
            if matches:
                last_match = matches[0]
                
                all_players = last_match.get('players', {}).get('all_players', [])
                for p in all_players:
                    if p.get('puuid') == puuid:
                        agent_name = p.get('character', 'Unknown')
                        
                        agent_icon = p.get('assets', {}).get('agent', {}).get('small')
                        logger.info(f"🕵️ Last Agent per {puuid}: {agent_name}")
                        return agent_name, agent_icon
                            
        return None, None

    async def get_account_level(self, puuid):
        
        logger.debug(f"🔍 get_account_level chiamato per {puuid}")
        url = f'https://api.henrikdev.xyz/valorant/v2/by-puuid/account/{puuid}'
        
        data = await self.fetch_with_retry(url, f"get_account_level({puuid})")
        
        if data:
            account_level = data.get('data', {}).get('account_level', 0)
            logger.info(f"Livello account per {puuid}: {account_level}")
            return account_level
            
        return 0

    async def download_image(self, url):
        
        try:
            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    return BytesIO(await response.read())
                else:
                    logger.error(f"Fallimento download immagine da {url} - status {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Errore download immagine: {e}")
            return None

    
    async def check_active_bans(self, channel):
        
        active_bans = {}
        if not channel:
            return active_bans
            
        try:
            
            messages_to_delete = []
            
            async for message in channel.history(limit=50):
                
                
                match = re.search(r"^(.+?#\w+)\s+ban\s+(\d+)h", message.content, re.IGNORECASE)
                
                if match:
                    username_tag = match.group(1).strip()
                    hours_duration = int(match.group(2))
                    
                    
                    target_user = next((u for u in USERS if u['name'].lower() == username_tag.lower()), None)
                    
                    if target_user:
                        message_time = message.created_at
                        
                        if message_time.tzinfo is None:
                            message_time = message_time.replace(tzinfo=ZoneInfo("UTC"))
                            
                        ban_end_time = message_time + timedelta(hours=hours_duration)
                        now = datetime.now(ZoneInfo("UTC"))
                        
                        remaining_time = ban_end_time - now
                        
                        if remaining_time.total_seconds() > 0:
                            
                            hours_left = int(remaining_time.total_seconds() // 3600)
                            minutes_left = int((remaining_time.total_seconds() % 3600) // 60)
                            
                            active_bans[target_user['puuid']] = f"⛔ BANNED: {hours_left}h {minutes_left}m"
                            logger.info(f"🚨 Ban attivo trovato per {target_user['name']}: {hours_left}h {minutes_left}m rimanenti")
                        else:
                            
                            logger.info(f"🗑️ Ban scaduto per {target_user['name']}, elimino messaggio...")
                            messages_to_delete.append(message)
            
            
            for msg in messages_to_delete:
                try:
                    await msg.delete()
                    logger.info("✅ Messaggio ban scaduto eliminato.")
                except Exception as e:
                    logger.error(f"❌ Errore eliminazione messaggio ban: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Errore durante il check dei ban: {e}")
            
        return active_bans

    async def edit_or_send_message(self, user_data, message_id, rank_name="ERROR", elo=0, ranking_in_tier=0, rank_icon=None, agent_img=None, account_level=0, ban_text=None):
        
        
        try:
            img_bio = await asyncio.to_thread(
                create_rank_card, 
                user_data, rank_name, elo, ranking_in_tier, rank_icon, agent_img, account_level, ban_text
            )
        except Exception as e:
            logger.error(f"❌ CRASH inside create_rank_card for {user_data['name']}: {e}")
            raise e
        
        
        
        ban_str = str(ban_text) if ban_text else "None"
        last_agent = user_data.get('last_agent_name', 'Unknown')
        metadata = f"||data:{rank_name}:{elo}:{ranking_in_tier}:{ban_str}:{last_agent}||"
        
        
        
        message_content = (
            f"**{user_data['name']}**\n"
            f"Username: `{user_data['login']}`\n"
            f"Password: ||{user_data['password']}||"
            
        )
        file = discord.File(img_bio, filename="valorant_rank.png")
        
        try:
            if message_id:
                try:
                    message = await self.safe_discord_request(self.channel.fetch_message, message_id)
                    
                    try:
                        await self.safe_discord_request(message.edit, content=message_content, attachments=[file])
                        logger.info(f"✅ Modificato messaggio per {user_data['name']} (id {message_id})")
                        return message_id
                    except Exception as e_edit:
                        
                        logger.warning(f"⚠️ Modifica attachment fallita per {message_id}: {e_edit}. Ricreazione messaggio.")
                        try:
                            await self.safe_discord_request(message.delete)
                        except Exception:
                            pass
                        new_msg = await self.safe_discord_request(self.channel.send, content=message_content, file=file)
                        self.set_user_message_id(user_data['puuid'], new_msg.id)
                        logger.info(f"✅ Ricreato messaggio per {user_data['name']} (nuovo id {new_msg.id})")
                        return new_msg.id
                except discord.NotFound:
                    logger.warning(f"⚠️ Messaggio id {message_id} non trovato per {user_data['name']}, invio nuovo.")
                except discord.Forbidden:
                    logger.error(f"❌ Errore permessi modifica messaggio per {user_data['name']}")
                except Exception as e:
                    logger.error(f"❌ Errore modifica messaggio per {user_data['name']}: {e}")
            
            
            message = await self.safe_discord_request(self.channel.send, content=message_content, file=file)
            logger.info(f"✅ Inviato nuovo messaggio per {user_data['name']} (id {message.id})")
            return message.id
        except Exception as e:
            logger.error(f"❌ Fallimento invio/modifica messaggio per {user_data['name']}: {e}")
            return None

    
    async def update_leaderboard(self):
        
        logger.info("🏆 Inizio aggiornamento Leaderboard...")
        
        if not LEADERBOARD_CHANNEL_ID:
            logger.warning("⚠️ LEADERBOARD_CHANNEL_ID non configurato.")
            return

        if not self.users_data_cache:
            logger.warning("⚠️ Cache utenti vuota, salto aggiornamento leaderboard.")
            return

        channel = self.get_channel(LEADERBOARD_CHANNEL_ID)
        if not channel:
            logger.error(f"❌ Canale Leaderboard {LEADERBOARD_CHANNEL_ID} non trovato!")
            return

        
        
        sorted_users = sorted(
            self.users_data_cache, 
            key=lambda x: (x.get('current_tier', 0) * 100) + x.get('ranking_in_tier', 0), 
            reverse=True
        )
        
        
        try:
            img_bio = await asyncio.to_thread(create_leaderboard_image, sorted_users)
        except Exception as e:
            logger.error(f"❌ Errore generazione immagine leaderboard: {e}")
            return

        file = discord.File(img_bio, filename="leaderboard.png")
        
        
        message_sent = False
        
        if LEADERBOARD_MESSAGE_ID != 0:
            try:
                message = await channel.fetch_message(LEADERBOARD_MESSAGE_ID)
                await message.edit(attachments=[file])
                logger.info(f"✅ Leaderboard aggiornata (ID: {LEADERBOARD_MESSAGE_ID})")
                message_sent = True
            except discord.NotFound:
                logger.warning(f"⚠️ Messaggio Leaderboard {LEADERBOARD_MESSAGE_ID} non trovato. Ne creo uno nuovo.")
            except Exception as e:
                logger.error(f"❌ Errore edit leaderboard: {e}")

        if not message_sent:
            try:
                new_msg = await channel.send(file=file)
                logger.critical(f"⚠️ NUOVO MESSAGGIO LEADERBOARD CREATO: ID {new_msg.id}")
                logger.critical(f"⚠️ >>> AGGIORNARE LA COSTANTE 'LEADERBOARD_MESSAGE_ID' NEL CODICE CON: {new_msg.id} <<<")
            except Exception as e:
                logger.error(f"❌ Errore invio nuova leaderboard: {e}")

    async def update_all_users(self):
        
        if self.is_updating:
            logger.warning("⚠️ Aggiornamento già in corso, skip")
            return False
        
        
        self.is_updating = True
        
        try:
            logger.info("🔄 Inizio aggiornamento per tutti gli utenti")
            success_count = 0

            
            
            
            any_update = False 
            
            
            
            active_bans = {}
            if self.channel:
                logger.info("🕵️ Controllo ban attivi nel canale...")
                active_bans = await self.check_active_bans(self.channel)

            
            fetched_users = []
            
            for i, user in enumerate(USERS):
                try:
                    
                    await asyncio.sleep(5)
                    
                    logger.info(f"🔄 Fetching data per {user['name']} ({i+1}/{len(USERS)})...")
                    
                    
                    rank_name, icon_url, elo, ranking_in_tier, current_tier = await self.get_valorant_rank(user['puuid'], name=user['name'])
                    
                    
                    account_level = 0
                    if rank_name in ["UNRANKED", "ERROR"]:
                        account_level = await self.get_account_level(user['puuid'])

                    
                    last_agent_name, last_agent_icon_url = await self.get_last_match_agent(user['puuid'])
                    
                    
                    if not last_agent_icon_url:
                        last_agent_name = "Unknown"
                        last_agent_icon_url = None

                    
                    user_ban_text = active_bans.get(user['puuid'])
                    data_signature = (rank_name, elo, ranking_in_tier, account_level, user_ban_text, last_agent_name, current_tier)
                    
                    needs_update = True  
                    
                    
                    if self.last_data_cache.get(user['puuid']) == data_signature:
                        needs_update = False
                        logger.info(f"💤 Nessun cambiamento per {user['name']} (Agent: {last_agent_name})")
                    else:
                        logger.info(f"🔄 Rilevato cambiamento per {user['name']} (Agent: {last_agent_name})")
                        self.last_data_cache[user['puuid']] = data_signature
                    
                    

                    
                    rank_icon_card = None
                    rank_icon_leaderboard = None
                    if icon_url:
                        try:
                             rank_icon_card = await ASSETS.get_image(self.session, icon_url, width=70, height=70)
                             rank_icon_leaderboard = await ASSETS.get_image(self.session, icon_url, width=50, height=50)
                        except Exception as e:
                            logger.error(f"Err download rank icon {user['name']}: {e}")

                    
                    agent_img_card = None
                    if last_agent_icon_url:
                        try:
                            agent_img_card = await ASSETS.get_image(self.session, last_agent_icon_url, width=80, height=80)
                        except Exception as e:
                            logger.error(f"Err download agent {user['name']}: {e}")
                    
                    
                    user_data = user.copy()
                    user_data.update({
                        'rank_name': rank_name,
                        'elo': elo,
                        'ranking_in_tier': ranking_in_tier,
                        'current_tier': current_tier, 
                        'account_level': account_level,
                        'rank_icon_cache': rank_icon_card,
                        'rank_icon_lb': rank_icon_leaderboard,
                        'agent_img_cache': agent_img_card,
                        'last_agent_name': last_agent_name,
                        'needs_update': needs_update,
                        'timestamp': get_rome_time().strftime("%H:%M %d/%m")
                    })
                    
                    fetched_users.append(user_data)
                    
                    logger.info(f"📊 Dati recuperati per {user['name']} - Tier: {current_tier} - ELO: {elo}")

                except Exception as e:
                    logger.error(f"❌ Errore fetch dati utente {user['name']}: {e}")
                    
                    user_data = user.copy()
                    user_data.update({
                        'rank_name': 'ERROR', 'elo': -1, 'ranking_in_tier': 0, 'current_tier': 0, 'account_level': 0, 
                        'rank_icon_cache': None, 'rank_icon_lb': None, 'agent_img_cache': None, 
                        'needs_update': False
                    })
                    fetched_users.append(user_data)

            
            
            fetched_users.sort(key=lambda x: (x.get('current_tier', 0) * 100) + x.get('ranking_in_tier', 0), reverse=True)
            
            
            self.users_data_cache = []
            for u in fetched_users:
                self.users_data_cache.append({
                    'name': u['name'].split('#')[0],
                    'rank': u['rank_name'],
                    'elo': u['elo'],
                    'ranking_in_tier': u.get('ranking_in_tier', 0),
                    'current_tier': u.get('current_tier', 0), 
                    'agent_img': u['agent_img_cache'],
                    'rank_icon': u['rank_icon_lb']
                })

            
            for i, user_data in enumerate(fetched_users):
                try:
                    
                    
                    
                    
                    

                    
                    await asyncio.sleep(4)

                    
                    
                    
                    
                    
                        
                    
                    any_update = True 
                    
                    
                    if i < len(HARDCODED_MESSAGE_IDS):
                        msg_id = HARDCODED_MESSAGE_IDS[i]
                        logger.info(f"📍 User {user_data['name']} assegnato allo Slot #{i+1} (ID: {msg_id})")
                    else:
                        logger.warning(f"⚠️ Nessun slot disponibile per {user_data['name']} (Posizione {i+1})")
                        continue
                    
                    
                    try:
                        
                        await self.edit_or_send_message(
                            user_data, msg_id, 
                            rank_name=user_data['rank_name'], 
                            elo=user_data['elo'], 
                            ranking_in_tier=user_data.get('ranking_in_tier', 0),
                            rank_icon=user_data.get('rank_icon_cache'),
                            agent_img=user_data.get('agent_img_cache'),
                            account_level=user_data.get('account_level', 0),
                            ban_text=active_bans.get(user_data['puuid'])
                        )
                        
                        
                        self.set_user_message_id(user_data['puuid'], msg_id)
                        logger.info(f"✅ Slot {i+1} aggiornato con {user_data['name']}")
                            
                    except Exception as e:
                        logger.error(f"Errore update message loop {user_data['name']}: {e}")

                except Exception as e:
                    logger.error(f"Errore ciclo finale update per {user_data['name']}: {e}")
            
            
            
            if any_update:
                await self.update_leaderboard()
            else:
                logger.info("💤 Leaderboard skip update (nessun cambiamento)")
                    
            logger.info(f"✅ Aggiornamento completato. Processati con successo {len(fetched_users)}/{len(USERS)} utenti")

        except Exception as e:
            logger.error(f"❌ CRASH Update Routine: {e}")
            await self.send_crash_log("UPDATE ROUTINE", e)
        finally:
            self.is_updating = False
            logger.info("🔓 Update Lock rilasciato.")
            
            
            jitter =  np.random.randint(0, 30)
            wait_time = UPDATE_INTERVAL + jitter
            self.next_update_time = time.time() + wait_time
            
            
            next_run_dt = datetime.now() + timedelta(seconds=wait_time)
            logger.info(f"⏰ Prossimo aggiornamento in {wait_time // 3600}h {(wait_time % 3600) // 60}m (Jitter: {jitter}s)")

    
    async def restore_state_from_discord(self):
        
        logger.info("🧠 Avvio ripristino memoria da Discord (Zero-Storage Persistence)...")
        if not self.channel:
            return

        restored_count = 0
        try:
            
            async for message in self.channel.history(limit=30):
                
                
                
                content = message.content
                
                match = re.search(r"\|\|data:(.+?):(\d+):(\d+):(.+?)(?::(.+?))?\|\|", content)
                
                if match:
                    rank_name = match.group(1)
                    elo = int(match.group(2))
                    ranking_in_tier = int(match.group(3))
                    ban_text = match.group(4)
                    if ban_text == "None": ban_text = None
                    last_agent_name = match.group(5) if match.group(5) else "Unknown" 
                    
                    
                    
                    name_match = re.search(r"\*\*(.+?)\*\*", content)
                    if name_match:
                        user_name = name_match.group(1)
                        
                        
                        target_user = next((u for u in USERS if u['name'].lower() == user_name.lower()), None)
                        
                        if target_user:
                            
                            
                            
                            
                            signature = (rank_name, elo, ranking_in_tier, 0, ban_text, last_agent_name)
                            
                            
                            self.last_data_cache[target_user['puuid']] = signature
                            
                            
                            self.set_user_message_id(target_user['puuid'], message.id)
                            
                            restored_count += 1
                            logger.info(f"🧠 Memoria ripristinata per {user_name}: {rank_name} {elo}RR ({last_agent_name})")

        except Exception as e:
            logger.error(f"❌ Errore durante restore memory da Discord: {e}")

        logger.info(f"🧠 Ripristino completato. Recuperati {restored_count}/{len(USERS)} utenti.")

    async def update_loop(self):
        
        await self.wait_until_ready()
        
        if not self.channel:
            try:
                self.channel = await self.fetch_channel(CHANNEL_ID)
                logger.info(f"✅ Canale recuperato via API: {self.channel}")
            except Exception as e:
                logger.error(f"❌ Impossibile trovare canale {CHANNEL_ID}: {e}")
                logger.warning("⚠️ Update loop in pausa per 60s prima di riprovare...")
                await asyncio.sleep(60)
                return
            
        
        
        await self.restore_state_from_discord()
        
        
        if self.skip_initial_update:
            logger.info("⏭️ Skip primo aggiornamento (riavvio post forceupdate)")
            self.skip_initial_update = False
        else:
            logger.info("🚀 Primo aggiornamento all'avvio...")
            await self.update_all_users()
        
        
        self.next_update_time = time.time() + UPDATE_INTERVAL
        
        
        while not self.is_closed():
            
            
            
            current_time = time.time() 
            jitter = random.gauss(0, 120) 
            
            
            target_time = self.next_update_time + jitter
            sleep_time = max(0, target_time - current_time)
            
            hours = int(sleep_time // 3600)
            minutes = int((sleep_time % 3600) // 60)
            logger.info(f"⏰ Prossimo aggiornamento in {hours}h {minutes}m (Jitter: {int(jitter)}s)")
            
            await asyncio.sleep(sleep_time)
            
            logger.info("🔄 Avvio aggiornamento programmato...")
            await self.update_all_users()
            
            
            self.next_update_time = time.time() + UPDATE_INTERVAL

    
    async def connect_email(self):
        
        try:
            return await asyncio.to_thread(self._connect_email_blocking)
        except Exception as e:
            logger.error(f"❌ Errore connessione IMAP Gmail: {e}")
            return None

    def _connect_email_blocking(self):
        
        ssl_context = ssl.create_default_context()
        client = IMAPClient(IMAP_SERVER, port=IMAP_PORT, ssl=True, ssl_context=ssl_context)
        client.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        client.select_folder("INBOX")
        logger.info("🔐 IMAP Gmail connesso per monitoraggio codici")
        return client

    def extract_code(self, text: str) -> str | None:
        
        if not text:
            return None
        
        
        
        patterns = [
            r"(?:verification\s*code|security\s*code|authentication\s*code|access\s*code)(?:\s*is)?[:;\s]*(\d{6})",
            r"(?:your|il\s*tuo)\s*(?:verification|security|authentication|access)?\s*code(?:\s*is)?[:;\s]*(\d{6})",
            r"(?:codice\s*di\s*(?:verifica|sicurezza|accesso))[:;\s]*(\d{6})",
            r"use\s*(?:this\s*)?code[:;\s]*(\d{6})",
            r"enter\s*(?:this\s*)?code[:;\s]*(\d{6})",
            
            r"رمز\s+تسجيل\s+الدخول[:\s]*(\d{6})", 
            r"إليك\s+رمز\s+تسجيل\s+الدخول[:\s]*(\d{6})", 
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                code = match.group(1)
                logger.info(f"🔢 Codice autenticazione trovato con pattern '{pattern}': {code}")
                return code
        
        return None

    def is_riot_games_email(self, text: str) -> bool:
        
        if not text:
            return False
        
        text_lower = text.lower()
        
        
        explicit_riot_patterns = [
            r"riot\s+games",            
            r"from\s+riot\s+games",     
            r"team\s+riot\s+games",     
            r"riot\s+games\s+(?:inc|team|support)",  
        ]
        
        
        has_explicit_riot = any(re.search(pattern, text_lower) for pattern in explicit_riot_patterns)
        
        if not has_explicit_riot:
            return False
        
        
        exclude_patterns = [
            r"monitor\s+is\s+(?:up|down)",
            r"uptime\s+monitor",
            r"status\s+change",
            r"service\s+monitor",
            r"ping\s+monitor",
            r"healthcheck",
            r"alert\s*:",
            r"notification\s+from",
            r"automated\s+alert",
        ]
        
        
        if any(re.search(pattern, text_lower) for pattern in exclude_patterns):
            logger.info(f"🚫 Email ignorata - sembra essere un monitor/alert automatico")
            return False
        
        return True

    async def send_code_to_discord(self, code: str):
        
        try:
            if not self.codes_channel:
                return
                
            try:
                
                now_rome = get_rome_time()
            except Exception:
                now_rome = datetime.now()
            
            embed = discord.Embed(
                title="🎮 Nuovo Codice Riot Games Trovato!",
                description=f"**🔢 Codice di Autenticazione:** `{code}`\n\n",
                color=0xA020F0,
                timestamp=now_rome
            )
            embed.set_footer(text="Bot Codici Riot Games", icon_url="https://i.imgur.com/Mrn3y3V.png")
            embed.set_thumbnail(url="https://logos-world.net/wp-content/uploads/2020/10/Riot-Games-Logo.png")
            
            await self.codes_channel.send(embed=embed)
            logger.info(f"✅ Codice Riot Games {code} inviato su Discord!")
            
        except Exception as e:
            logger.error(f"❌ Errore invio codice su Discord: {e}")

    
    async def check_email_once(self):
        
        
        async with self.email_lock:
            
            if not self.email_client:
                self.email_client = await self.connect_email()
                
            if not self.email_client:
                return None

            try:
                
                today_rome = get_rome_time().date()
                search_date_str = today_rome.strftime("%d-%b-%Y")
                
                
                
                try:
                    uids = await asyncio.to_thread(self.email_client.search, ['SINCE', search_date_str])
                except (imap_exceptions.IMAPClientError, ssl.SSLError, EOFError, OSError) as e:
                    logger.error(f"❌ Errore ricerca email (connessione persa?): {e}")
                    
                    try:
                        await asyncio.to_thread(self.email_client.logout)
                    except:
                        pass
                    self.email_client = None
                    return None
                
                if uids:
                    
                    last_uids = sorted(uids)[-15:]
                    
                    last_uids.reverse() 
                    
                    for uid in last_uids:
                        try:
                            
                            if not self.email_client:
                                break

                            
                            def fetch_message():
                                
                                return self.email_client.fetch(uid, ['RFC822'])[uid][b'RFC822']
                            
                            msg_data = await asyncio.to_thread(fetch_message)
                            msg = email.message_from_bytes(msg_data)
                            
                            
                            if 'Date' in msg:
                                email_date = parsedate_to_datetime(msg['Date'])
                                
                                if email_date.tzinfo is None:
                                    email_date = email_date.replace(tzinfo=ZoneInfo("UTC"))
                                
                                now = datetime.now(email_date.tzinfo)
                                age = now - email_date
                                age_minutes = age.total_seconds() / 60
                                
                                if age_minutes > CODE_MAX_AGE_MINUTES:
                                    logger.debug(f"⏳ Email ignorata perché vecchia di {int(age_minutes)} min")
                                    continue 
                            
                            
                            subject_parts = decode_header(msg['Subject'])
                            subject = ''
                            for part, enc in subject_parts:
                                if isinstance(part, bytes):
                                    subject += part.decode(enc or 'utf-8', errors='ignore')
                                else:
                                    subject += str(part)
                            
                            sender = msg.get('From', '')
                            body = ''
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == 'text/plain':
                                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                            
                            text_combined = f"From: {sender}\nSubject: {subject}\n{body}"
                            
                            if self.is_riot_games_email(text_combined):
                                body_code = self.extract_code(body)
                                subject_code = self.extract_code(subject)
                                code = body_code or subject_code
                                
                                if code:
                                    logger.info(f"✅ Trovato codice valido e recente: {code}")
                                    return code
                                    
                        except Exception as e:
                            logger.error(f"Errore parsing email {uid}: {e}")
                            
                            if "EOF" in str(e) or "socket" in str(e).lower():
                                logger.error("💀 Socket moruto durante fetch, abort loop.")
                                self.email_client = None
                                break
                            continue
                            
            except Exception as e:
                logger.error(f"❌ Errore check_email_once (generico): {e}")
                
                self.email_client = None 
        
        return None

    
    async def check_email_for_codes(self):
        
        while not self.is_closed():
            
            
            
            self.last_email_check_time = time.time()
            
            code = await self.check_email_once()
            
            
            if code and code not in self.codes_history:
                logger.info(f"🆕 NUOVO CODICE TROVATO: {code}")
                
                self.save_code_to_history(code)
                await self.send_code_to_discord(code)
            elif code:
                
                logger.debug(f"🔇 Codice {code} ignorato (già inviato in passato)")
                
            await asyncio.sleep(CHECK_INTERVAL)
    

class RefreshView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None) 
        self.bot = bot

    @discord.ui.button(label="Force Update", style=discord.ButtonStyle.primary, custom_id="force_refresh_all", emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        if interaction.guild_id != AUTH_GUILD_ID:
            return await interaction.response.send_message("❌ Comando non autorizzato in questo server.", ephemeral=True)
            
        if self.bot.is_updating:
            return await interaction.response.send_message("⚠️ Update già in corso, attendere...", ephemeral=True)
        
        await interaction.response.send_message("🚀 Update manuale avviato!", ephemeral=True)
        
        asyncio.create_task(self.bot.update_all_users())

    async def close(self):
        
        logger.info("🔄 Chiusura bot...")
        
        
        if self.update_task and not self.update_task.done():
            self.update_task.cancel()
        if self.email_task and not self.email_task.done():
            self.email_task.cancel()
        if self.watchdog_task and not self.watchdog_task.done():
             self.watchdog_task.cancel()
        
        
        if self.session and not getattr(self.session, "closed", False):
            await self.session.close()
            logger.info("✅ Sessione HTTP chiusa")
        
        
        if self.email_client:
            try:
                
                await asyncio.to_thread(self.email_client.logout)
                logger.info("✅ Client email chiuso")
            except Exception as e:
                logger.error(f"❌ Errore chiusura email: {e}")
        
        await super().close()


bot = ValorantBot()




@bot.tree.command(name="forcewatchdog", description="[ADMIN] Esegue manualmente tutti i controlli del Watchdog")
async def forcewatchdog(interaction: discord.Interaction):
    
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message("❌ Solo l'admin può usare questo comando!", ephemeral=True)
        return

    try:
        await interaction.response.defer(ephemeral=True)
        
        
        report = await bot.run_watchdog_checks(report_channel=True)
        
        embed = discord.Embed(
            title="🐕 Watchdog Manuale",
            description=f"**Report Esecuzione Forzata:**\n\n{report}",
            color=0xFFA500, 
            timestamp=datetime.utcnow()
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"❌ Errore comando forcewatchdog: {e}")
        try:
            await interaction.followup.send(f"❌ Errore critico: {str(e)}", ephemeral=True)
        except: pass

@bot.tree.command(name="forceupdate", description="Forza l'aggiornamento di tutti i rank")
async def forceupdate(interaction: discord.Interaction):
    
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message("❌ Solo l'admin può usare questo comando!", ephemeral=True)
        return
    
    try:
        await interaction.response.defer(ephemeral=True)
        
        if bot.is_updating:
            
            logger.warning("⚠️ Forceupdate chiamato con update già in corso. Forzo il reset della flag e procedo.")
            bot.is_updating = False
            
        
        if not bot.channel:
            await interaction.followup.send("❌ Impossibile trovare il canale configurato.", ephemeral=True)
            return
        
        success = await bot.update_all_users()
        
        if success:
            try:
                await interaction.followup.send("✅ Aggiornamento forzato completato con successo!", ephemeral=True)
            except discord.HTTPException as e:
                if e.status == 429 or "Too Many Requests" in str(e):
                    logger.warning("⚠️ Rate limit su followup dopo forceupdate, skip messaggio")
                elif "2000 or fewer" in str(e):
                    await interaction.followup.send("✅ Aggiornamento completato!", ephemeral=True)
                else:
                    raise
        else:
            await interaction.followup.send("❌ Aggiornamento forzato fallito. Controlla i log.", ephemeral=True)
    
    except discord.NotFound:
        logger.error("❌ Interaction scaduta durante forceupdate")
    except Exception as e:
        logger.error(f"❌ Errore comando forceupdate: {e}")
        try:
            
            error_msg = f"❌ Errore durante l'aggiornamento: {str(e)[:100]}..."
            await interaction.followup.send(error_msg, ephemeral=True)
        except:
            pass
    finally:
        
        try:
            bot.restart_update_timer()
        except Exception as e:
            logger.error(f"❌ Errore riavvio timer dopo forceupdate: {e}")

@bot.tree.command(name="fastcodice", description="Forza controllo email immediato (ultime 24h)")
async def fast_codice(interaction: discord.Interaction):
    
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message("❌ Solo l'admin può usare questo comando!", ephemeral=True)
        return
    
    try:
        await interaction.response.defer(ephemeral=True)
        
        
        code = await bot.check_email_once()
        
        if code:
             
            if code not in bot.codes_history:
                
                bot.save_code_to_history(code)
                await bot.send_code_to_discord(code)
                await interaction.followup.send(f"✅ **Found and sent!** Code: `{code}`", ephemeral=True)
            else:
                await interaction.followup.send(f"⚠️ Code found `{code}`, but already sent (in History).", ephemeral=True)
        else:
            
            if bot.codes_channel:
                
                embed = discord.Embed(
                    title="🚫 No Code Found",
                    description="**No valid code found**\n\nNo email with valid code in the last 24h.",
                    color=0xFF0000, 
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text="Riot Games Codes Bot", icon_url="https://i.imgur.com/Mrn3y3V.png")
                embed.set_thumbnail(url="https://logos-world.net/wp-content/uploads/2020/10/Riot-Games-Logo.png")
                
                await bot.codes_channel.send(embed=embed)
                
            await interaction.followup.send("❌ No *valid* code (max 15 min) found. Channel has been notified.", ephemeral=True)
        
    except discord.NotFound:
        logger.error("❌ Interaction scaduta durante FastCodice")
    except Exception as e:
        logger.error(f"❌ Errore comando FastCodice: {e}")
        try:
            await interaction.followup.send(f"❌ Errore: {str(e)}", ephemeral=True)
        except:
            pass

@bot.tree.command(name="status", description="Mostra lo stato del bot")
async def status(interaction: discord.Interaction):
    
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message("❌ Solo l'admin può usare questo comando!", ephemeral=True)
        return
    
    try:
        
        embed = discord.Embed(
            title="🤖 Stato Bot Valorant",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        
        embed.add_field(
            name="📊 Generale", 
            value=f"✅ Online\n🔄 Aggiornamento: {'In corso' if bot.is_updating else 'Idle'}", 
            inline=True
        )
        
        
        next_update_countdown = bot.get_next_update_countdown()
        embed.add_field(
            name="⏰ Prossimo Update", 
            value=f"{next_update_countdown}", 
            inline=True
        )
        
        
        sync_status = "✅ Sincronizzati" if bot.commands_synced else "❌ Non sincronizzati"
        embed.add_field(
            name="⚡ Comandi Slash", 
            value=sync_status, 
            inline=True
        )
        
        
        session_status = "✅ Attiva" if bot.session and not getattr(bot.session, "closed", False) else "❌ Chiusa"
        embed.add_field(
            name="🌐 Sessione HTTP", 
            value=session_status, 
            inline=True
        )
        
        
        email_status = "✅ Connesso" if bot.email_client else "❌ Disconnesso"
        embed.add_field(
            name="📧 Monitoraggio Email", 
            value=email_status, 
            inline=True
        )
        
        
        email_heartbeat = "Mai"
        if bot.last_email_check_time > 0:
            secs_ago = int(time.time() - bot.last_email_check_time)
            email_heartbeat = f"{secs_ago}s fa"
        
        embed.add_field(
            name="❤️ Email Heartbeat", 
            value=email_heartbeat, 
            inline=True
        )
        
        
        update_task_status = "✅ Attivo" if bot.update_task and not bot.update_task.done() else "❌ Inattivo"
        email_task_status = "✅ Attivo" if bot.email_task and not bot.email_task.done() else "❌ Inattivo"
        watchdog_status = "✅ Attivo" if bot.watchdog_task and not bot.watchdog_task.done() else "❌ Inattivo"
        
        embed.add_field(
            name="🔄 Task Status", 
            value=f"Update: {update_task_status}\nEmail: {email_task_status}\nWatchdog: {watchdog_status}", 
            inline=True
        )
        
        
        cache_count = len(bot.message_cache)
        embed.add_field(
            name="💾 Cache Messaggi", 
            value=f"{cache_count} messaggi salvati", 
            inline=True
        )
        
        
        history_count = len(bot.codes_history)
        embed.add_field(
            name="📚 History Codici", 
            value=f"{history_count} salvati", 
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except discord.NotFound:
        logger.error("❌ Interaction scaduta durante status")
    except Exception as e:
        logger.error(f"❌ Errore comando status: {e}")
        try:
            await interaction.response.send_message(f"❌ Errore durante il controllo stato: {str(e)}", ephemeral=True)
        except discord.NotFound:
            logger.error("❌ Impossibile inviare risposta - interaction scaduta")

@bot.tree.command(name="sendtest", description="[ADMIN] Invia un messaggio di test nel canale corrente")
async def sendtest(interaction: discord.Interaction):
    
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message("❌ Solo l'admin può usare questo comando!", ephemeral=True)
        return

    try:
        await interaction.channel.send(",")
        await interaction.response.send_message("✅ Messaggio di test inviato!", ephemeral=True)
    except Exception as e:
        logger.error(f"❌ Errore comando sendtest: {e}")
        await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)

@bot.tree.command(name="restart", description="Riavvia i task in background")
async def restart(interaction: discord.Interaction):
    
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message("❌ Solo l'admin può usare questo comando!", ephemeral=True)
        return
    
    try:
        await interaction.response.defer(ephemeral=True)
        
        
        bot.is_updating = False

        
        if bot.update_task and not bot.update_task.done():
            bot.update_task.cancel()
        if bot.email_task and not bot.email_task.done():
            bot.email_task.cancel()
        if bot.watchdog_task and not bot.watchdog_task.done():
             bot.watchdog_task.cancel()
        
        
        bot.email_client = None
        bot.last_email_check_time = 0
        
        
        if not bot.session or getattr(bot.session, "closed", False):
            if bot.session:
                await bot.session.close() 
            bot.session = aiohttp.ClientSession()
        
        
        bot.start_background_tasks()
        
        await interaction.followup.send("✅ Task in background riavviati con successo!", ephemeral=True)
        
    except discord.NotFound:
        logger.error("❌ Interaction scaduta durante restart")
    except Exception as e:
        logger.error(f"❌ Errore comando restart: {e}")
        try:
            await interaction.followup.send(f"❌ Errore durante il restart: {str(e)}", ephemeral=True)
        except discord.NotFound:
            logger.error("❌ Impossibile inviare risposta - interaction scaduta")

@bot.tree.command(name="sync", description="Risincronizza manualmente i comandi slash")
async def sync_commands(interaction: discord.Interaction):
    
    if interaction.user.id != ADMIN_USER_ID:
        await interaction.response.send_message("❌ Solo l'admin può usare questo comando!", ephemeral=True)
        return
    
    try:
        await interaction.response.defer(ephemeral=True)
        
        try:
            
            logger.info("🔄 Sincronizzazione manuale globale...")
            synced = await bot.tree.sync()
            bot.commands_synced = True
            await interaction.followup.send(f"✅ {len(synced)} comandi sincronizzati GLOBALMENTE! (Potrebbe richiedere fino a 1 ora per propagarsi ovunque)", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Permissions insufficienti per sincronizzare comandi", ephemeral=True)
        except Exception as sync_error:
            await interaction.followup.send(f"❌ Errore sync: {str(sync_error)}", ephemeral=True)
        
    except discord.NotFound:
        logger.error("❌ Interaction scaduta durante sync")
    except Exception as e:
        logger.error(f"❌ Errore comando sync: {e}")
        try:
            await interaction.followup.send(f"❌ Errore durante la sincronizzazione: {str(e)}", ephemeral=True)
        except discord.NotFound:
            logger.error("❌ Impossibile inviare risposta - interaction scaduta")


if __name__ == "__main__":
    try:
        logger.info("🚀 Avvio Bot Valorant Tracker...")
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("🛑 Bot fermato dall'utente")
    except Exception as e:
        logger.error(f"❌ Errore avvio bot: {e}")
    finally:
        logger.info("🔄 Procedura di shutdown completata")
