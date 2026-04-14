from credentials import TOKEN
import requests
import discord
from discord.ext import commands
import json
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import pytz

# Payload for RSI website graphQL request
PAYLOAD = json.dumps([
  {
    "operationName": "initShipUpgrade",
    "variables": {},
    "query": "query initShipUpgrade {\n  ships {\n    name\n    msrp\n  }\n}\n"
  },
  {
    "operationName": "filterShips",
    "variables": {
      "fromFilters": [],
      "toFilters": []
    },
    "query": "query filterShips($fromId: Int, $toFilters: [FilterConstraintValues]) {\n  to(from: $fromId, filters: $toFilters) {\n    ships {\n      name\n      skus {\n        price\n        }\n    }\n  }\n}\n"
  }
])

intents = discord.Intents.default()
intents.message_content = True

# Set bot commands start with '!'
bot = commands.Bot(command_prefix='!', intents=intents)

scheduler = AsyncIOScheduler()

# Set bot command for !aled -> return an instant capture to where it is asked
@bot.command()
async def aled(ctx):
    generated = generate()
    new_message = generate_message(generated, datetime.now().strftime("%d/%m/%Y"))
    await ctx.send(new_message)

# Bot execute auto task every day at 18:02 Europe/Paris
@bot.event
async def on_ready():
    print("Bot ready")
    scheduler.start()
    scheduler.add_job(daily_check, 'cron', hour=18, minute=2, timezone=pytz.timezone('Europe/Paris'))


# Json file keep last execution result to avoid sending message when there is no change
last_json = ""

file = open("history.json", "r")
read = file.readline()
if read != "":
    last_json = json.loads(read)
file.close()

# Main function
# Send requests to RSI website to get token and then make graphQL request
# Parse data from json response
def generate():
    session = requests.Session()
    session.post("https://robertsspaceindustries.com/api/account/v2/setAuthToken")
    session.post("https://robertsspaceindustries.com/api/ship-upgrades/setContextToken")
    response = session.post("https://robertsspaceindustries.com/pledge-store/api/upgrade/graphql", data=PAYLOAD, headers={"content-type": "application/json"})

    if response.status_code != 200:
        print("RSI request error : ", end='')
        print(response.status_code)
        return
    json_response = json.loads(response.text)

    ships_table = {}
        
    for upgrade in json_response[1]['data']['to']['ships']:
        if len(upgrade['skus']) > 1:
            ship_name = upgrade['name']
            warbond_price = upgrade['skus'][0]['price']
            standard_price = upgrade['skus'][1]['price']
            best_upgrade_price = 0
            best_upgrades = []
            for ship in json_response[0]['data']['ships']:
                if warbond_price > ship['msrp'] > best_upgrade_price:
                    best_upgrades = []
                    best_upgrade_price = ship['msrp']
                    best_upgrades.append(ship['name'])
                elif ship['msrp'] == best_upgrade_price:
                    best_upgrades.append(ship['name'])
            ships_table[ship_name] = {'warbond_price': warbond_price, 'standard_price': standard_price, 'best_upgrade_price': best_upgrade_price, 'best_upgrades': best_upgrades}
    ships_table = dict(sorted(ships_table.items(), key=lambda item: item[1]['warbond_price']))
    return ships_table

# Generate the message shaped for discord display
def generate_message(ships_table, date):
    new_message = ":rotating_light: " + date + " :rotating_light:\r\n"
    new_message += "```\r\n"
    for ship in ships_table:
        new_message += "- " + ship + " " + str(ships_table[ship]['standard_price']/100) + "$ -> " + str(ships_table[ship]['warbond_price']/100) + "$ | "
        for upgrade in ships_table[ship]['best_upgrades']:
            new_message += upgrade + " / "
        new_message += str((ships_table[ship]['warbond_price']-ships_table[ship]['best_upgrade_price'])/100) + "$\r\n"
    new_message += "\r\nTous les prix sont indiqués en dollar américain hors tax sauf si mentionné\r\n\r\nCette liste a été générée automatiquement. Il se peut qu'elle ne reflète pas la réalité.\r\nVérifiez toujours ces informations avant de vous engager.\r\n```"
    return new_message

# Async function executed daily
# Get data from website, compare with last time, send message to all registered discords if there are changes
async def daily_check():

    ships_table = generate()
    
    global last_json
    date = datetime.now().strftime("%d/%m/%Y")
    if last_json == ships_table:
        print(date, end='')
        print(" No change")
        return
    print("- ", end='')
    print(date, end='')
    print(" - Change")
    last_json = ships_table
    file = open("history.json", "w")
    file.write(json.dumps(last_json))
    file.close()

    new_message = generate_message(ships_table, date)

    # Send to specific named channels : "le-bon-marché" and "le bon marché"
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name="le-bon-marché")
        if channel:
            await channel.send(new_message)
        else:
            channel = discord.utils.get(guild.text_channels, name="le bon marché")
            if channel:
                await channel.send(new_message)

# run the bot with TOKEN set in credentials.py file
bot.run(TOKEN)