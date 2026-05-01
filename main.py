import aiohttp
import asyncio
import telebot
import json
import os
import time
from urllib.parse import urlparse
import threading

# ================= CONFIG =================
BOT_TOKEN = "6288193781:AAGrBx3qgv1H_Bz3FL-BgW19gpXbgVL-M-Y"
ADMIN_ID = 1890133465

API_KEYS = ["0d93e34216ca44", "19483d5e1bd54c", "f7f62ee1e9224d"]

MONITOR_INTERVAL = 90
ALERT_THRESHOLD = 0.01

bot = telebot.TeleBot(BOT_TOKEN)
DATA_FILE = "data.json"

# ================= DATA =================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"approved_users": [], "banned_users": [], "users": {}}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

data = load_data()

# ================= UTIL =================
def is_approved(uid):
    uid = str(uid)
    if uid in data.get("banned_users", []):
        return False
    return uid in data.get("approved_users", []) or int(uid) == ADMIN_ID

def get_slug(url):
    try:
        parts = urlparse(url).path.strip('/').split('/')
        if parts[0] == "collection":
            return parts[1]
    except:
        pass
    return None

# ================= ADMIN =================
@bot.message_handler(commands=['approve'])
def approve(msg):
    if msg.chat.id != ADMIN_ID:
        return
    uid = msg.text.split()[1]
    data["approved_users"].append(uid)
    save_data()
    bot.reply_to(msg, f"✅ Approved {uid}")

@bot.message_handler(commands=['ban'])
def ban(msg):
    if msg.chat.id != ADMIN_ID:
        return
    uid = msg.text.split()[1]
    data["banned_users"].append(uid)
    save_data()
    bot.reply_to(msg, f"🚫 Banned {uid}")

@bot.message_handler(commands=['unban'])
def unban(msg):
    if msg.chat.id != ADMIN_ID:
        return
    uid = msg.text.split()[1]
    if uid in data["banned_users"]:
        data["banned_users"].remove(uid)
    save_data()
    bot.reply_to(msg, f"✅ Unbanned {uid}")

# ================= START =================
@bot.message_handler(commands=['start'])
def start(msg):
    uid = str(msg.chat.id)

    if uid not in data["users"]:
        data["users"][uid] = {
            "collections": {},
            "mode": "normal"
        }
        save_data()

    bot.reply_to(
        msg,
        f"🚀 *Bot Active!*\n\n"
        f"📌 Your ID:\n```{uid}```\n\n"
        f"📌 Mode: `{data['users'][uid]['mode']}`\n\n"
        f"📋 *Commands:*\n"
        f"➕ /add <link>\n"
        f"📋 /list\n"
        f"❌ /remove <slug>\n"
        f"🗑️ /removeall\n"
        f"🔁 /mode normal | spam",
        parse_mode="Markdown"
    )

# ================= MODE =================
@bot.message_handler(commands=['mode'])
def set_mode(msg):
    uid = str(msg.chat.id)
    try:
        mode = msg.text.split()[1].lower()
        if mode not in ["normal", "spam"]:
            return bot.reply_to(msg, "Use: /mode normal or /mode spam")

        data["users"][uid]["mode"] = mode
        save_data()
        bot.reply_to(msg, f"🔔 Mode → {mode}")
    except:
        bot.reply_to(msg, "Usage: /mode normal or /mode spam")

# ================= PRICE =================
async def fetch_price(session, slug):
    url = f"https://api.opensea.io/api/v2/collections/{slug}/stats"

    for key in API_KEYS:
        try:
            async with session.get(url, headers={"X-API-KEY": key}) as r:
                if r.status == 200:
                    js = await r.json()
                    return js.get("total", {}).get("floor_price")
        except:
            continue
    return None

async def get_price(session, slug, retries=3):
    for _ in range(retries):
        try:
            p = await fetch_price(session, slug)
            if p:
                return float(p)
        except:
            pass
        await asyncio.sleep(1)
    return None

async def get_eth_usd(session):
    try:
        async with session.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
        ) as r:
            return (await r.json())["ethereum"]["usd"]
    except:
        return None

# ================= ADD =================
@bot.message_handler(commands=['add'])
def add(msg):
    uid = str(msg.chat.id)

    if not is_approved(uid):
        return bot.reply_to(
            msg,
            "❌ *You are not approved!*\n\n"
            "📞 Contact Developer: @SK1Z0V41",
            parse_mode="Markdown"
        )

    try:
        slug = get_slug(msg.text.split()[1])

        if slug in data["users"][uid]["collections"]:
            return bot.reply_to(msg, f"⚠️ {slug} already listed")

        async def run():
            async with aiohttp.ClientSession() as session:
                price = await get_price(session, slug)
                eth = await get_eth_usd(session)

                usd = f" (${round(price*eth,2):,})" if price and eth else ""

                data["users"][uid]["collections"][slug] = {"last": price or 0}
                save_data()

                bot.send_message(uid, f"✅ {slug}\n💰 {price} ETH{usd}")

        asyncio.run(run())

    except:
        bot.reply_to(msg, "Usage: /add <link>")

# ================= LIST =================
@bot.message_handler(commands=['list'])
def list_cmd(msg):
    uid = str(msg.chat.id)
    cols = data["users"][uid]["collections"]

    if not cols:
        return bot.reply_to(msg, "📭 Empty")

    text = "📋 Your Collections:\n\n"
    for slug in cols:
        text += f"• {slug}\n"

    bot.reply_to(msg, text)

# ================= REMOVE =================
@bot.message_handler(commands=['remove'])
def remove(msg):
    uid = str(msg.chat.id)
    try:
        slug = msg.text.split()[1]

        if slug not in data["users"][uid]["collections"]:
            return bot.reply_to(msg, "❌ Not found")

        del data["users"][uid]["collections"][slug]
        save_data()

        bot.reply_to(msg, f"🗑️ Removed {slug}")

    except:
        bot.reply_to(msg, "Usage: /remove <slug>")

# ================= REMOVE ALL =================
@bot.message_handler(commands=['removeall'])
def removeall(msg):
    uid = str(msg.chat.id)
    data["users"][uid]["collections"] = {}
    save_data()
    bot.reply_to(msg, "🗑️ All removed")

# ================= MONITOR =================
async def monitor():
    async with aiohttp.ClientSession() as session:
        while True:
            eth = await get_eth_usd(session)

            for uid, udata in data["users"].items():
                if not is_approved(uid):
                    continue

                mode = udata.get("mode", "normal")
                slugs = list(udata["collections"].keys())

                tasks = [get_price(session, slug) for slug in slugs]
                prices = await asyncio.gather(*tasks)

                for slug, price in zip(slugs, prices):

                    if not price:
                        bot.send_message(int(uid), f"⚠️ {slug}\nNo data")
                        continue

                    last = udata["collections"][slug].get("last", 0)
                    change = ((price - last) / last * 100) if last else 0
                    emoji = "📈" if change > 0 else "📉"
                    usd = f" (${round(price*eth,2):,})" if price and eth else ""

                    link = f"https://opensea.io/collection/{slug}"

                    message = (
                        f"🔔 *{slug}*\n"
                        f"💰 {price} ETH{usd}\n"
                        f"{emoji} {change:+.4f}%\n\n"
                        f"🔗 [View on OpenSea]({link})"
                    )

                    if mode == "spam":
                        bot.send_message(int(uid), message, parse_mode="Markdown", disable_web_page_preview=True)

                    elif mode == "normal":
                        if abs(change) >= ALERT_THRESHOLD:
                            bot.send_message(int(uid), message, parse_mode="Markdown", disable_web_page_preview=True)

                    data["users"][uid]["collections"][slug]["last"] = price

                save_data()

            await asyncio.sleep(MONITOR_INTERVAL)

# ================= RUN =================
def run_async():
    asyncio.run(monitor())

threading.Thread(target=run_async, daemon=True).start()
bot.infinity_polling()
