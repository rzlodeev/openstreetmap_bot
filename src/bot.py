import decimal
import pprint
import statistics
import math
import overpy
import logging
import telebot
import os
from dotenv import load_dotenv
from telebot import types

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(f'{BOT_TOKEN}')  # Insert Bot Token here

LOGS_PWD = os.getenv('LOGS_PWD')  # Custom password for checking logs from bot

logging.basicConfig(filename='../logs/logs.log', encoding='utf-8', level=logging.INFO)

# Global variables to remember user choice
lan = 'UA'


@bot.message_handler(commands=["start"])
def start_command(message):
    reply_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    lan_ua_button = types.KeyboardButton("🇺🇦Укр")
    lan_eng_button = types.KeyboardButton("🇬🇧Eng")
    reply_markup.add(lan_ua_button, lan_eng_button)
    bot.send_message(message.chat.id, "Hi! Please choose a language:", reply_markup=reply_markup)
    bot.register_next_step_handler(message, choose_language)


@bot.message_handler(commands=['logs'])
def logs_command(message):
    bot.send_message(message.chat.id, 'pswd:')
    bot.register_next_step_handler(message, send_logs)


def send_logs(message):
    if message.text == f'{LOGS_PWD}':
        log_file = open('../logs/logs.log', 'rb')
        bot.send_document(message.chat.id, document=log_file)
    else:
        bot.send_message(message.chat.id, 'wrong pswd')

def choose_language(message):
    global lan
    if message.text == "🇺🇦Укр":
        lan = "UA"
    if message.text == "🇬🇧Eng":
        lan = "ENG"

    inline_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    if lan == "UA":
        my_geo_button = types.KeyboardButton("Надіслати моє місцезнаходження", request_location=True)
    else:
        my_geo_button = types.KeyboardButton("Send my current location", request_location=True)
    inline_markup.add(my_geo_button)

    send_text = ''
    if lan == "UA":
        send_text = "Супер! Тепер надішли локацію, навколо якої мені шукати вік будинків. " \
                    "Ти можеш надіслати свою або довільну."
    if lan == "ENG":
        send_text = "Great! Now send me the location around which I should look for the age of buildings." \
                    "You can send your current location or choose whatever you want."

    bot.send_message(message.chat.id, text=send_text, reply_markup=inline_markup)


# Finds built-year around provided location using OpenStreetMapAPI and send it to user
@bot.message_handler(content_types=["location"])
def find_buildings_year(message):
    global lan
    user_coords = [message.location.latitude, message.location.longitude]
    logging.info(f'User {message.from_user.username} sent coordinates {user_coords[0]},{user_coords[1]}')
    box = get_nearest_box(user_coords)  # Get area around user coordinates

    api = overpy.Overpass()  # API Request
    result = api.query(f"""
        nwr({box})[building];
        (._;>;);
        out center;
        """)

    buildings_unsorted = []  # List to store requested data

    if result.ways:
        for way in result.ways:  # Storing result data in buildings dict
            if way.tags.get('start_date'):  # If requested building has info about built year
                buildings_unsorted.append(way.tags | {  # Add coordinates of center
                    'coords': [way.center_lat, way.center_lon]
                })

        min_year = 0  # Variables to store min and max built year value
        max_year = 0
        years = []  # List with years of all buildings to find median

        send_text = ''  # Text to send in message

        for building in buildings_unsorted:  # Iterate through buildings to calculate and add distance to user value
            distance = find_distance(user_coords, building.get('coords'))
            building.update({'distance': distance})

        buildings = sorted(buildings_unsorted, key=lambda d: d['distance'])

        for building in buildings:  # Iterate through builndigs to read data and add it to send_text
            building_year = int(building.get('start_date'))
            years.append(building_year)

            if building == buildings[0]:  # Set min and max year as year of first building in list
                min_year = building_year
                max_year = min_year

            global lan
            if lan == "UA":
                # Add info to text. Levels are added if they exist.
                send_text += f"📍{building.get('distance')}m " \
                             f"{building.get('addr:street', 'з невідомою адресою')} " \
                             f"{building.get('addr:housenumber')}: {building_year} рік" \
                             f"{(', ' + building.get('building:levels') + ' поверхів;' if building.get('building:levels') else ';')}\n"
            if lan == "ENG":
                # Add info to text. Levels are added if they exist.
                send_text += f"Building {building.get('addr:street', 'with unknown address')} " \
                             f"{building.get('addr:housenumber')}: year {building_year}" \
                             f"{(', ' + building.get('building:levels') + ' levels;' if building.get('building:levels') else ';')}\n"
            if building_year < min_year:  # Updating min and max years
                min_year = building_year
            if building_year > max_year:
                max_year = building_year

        if years:
            median_value = int(statistics.median(years))
        else:
            median_value = 0

        if lan == "UA":
            send_text = f'Будівлі в цьому районі датуються {min_year}-{max_year} роками. ' \
                        f'Середній (медіана) рік будівлі - {(median_value if median_value else "невідомий")}\n\n' + send_text
        if lan == "ENG":
            send_text = f'The buildings in this area date back to {min_year}-{max_year}. ' \
                        f'Median year is {(median_value if median_value else "is unknown")}\n\n' + send_text

        inline_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        if lan == "UA":
            my_geo_button = types.KeyboardButton("Надіслати моє місцезнаходження", request_location=True)
        else:
            my_geo_button = types.KeyboardButton("Send my current location", request_location=True)
        inline_markup.add(my_geo_button)

        bot.send_message(message.chat.id, text=send_text, reply_markup=inline_markup)

    else:
        if lan == 'UA':
            bot.send_message(message.chat.id, 'Не знайдено будівель у цьому районі. Спробуй іншу локацію!')
        else:
            bot.send_message(message.chat.id, 'Не знайдено будівель у цьому районі. Спробуй іншу локацію!')


# Takes coordinates and returns query-ready string of square box coordinates with mentioned size
def get_nearest_box(coords: list, size=0.00360):
    box = [float(coords[0]) - size / 2,
           float(coords[1]) - size / 2,
           float(coords[0]) + size / 2,
           float(coords[1]) + size / 2]

    box_str = ''
    for coord in box:
        if not coord == box[-1]:
            box_str += str(coord) + ","
        else:
            box_str += str(coord)

    return box_str


# Calculate distance between user and building using Pifagor theorem. 111139 converts degrees to meters
def find_distance(user_coords: list, obj_coords: list):
    # user_coords[0] = int(user_coords[0] * 10000000)
    # user_coords[1] = int(user_coords[1] * 10000000)
    # obj_coords[0] = int(obj_coords[0] * 10000000)
    # obj_coords[1] = int(obj_coords[1] * 10000000)
    #
    # print(user_coords)
    # print(obj_coords)
    # result = math.sqrt(abs(decimal.Decimal(user_coords[0]) - obj_coords[0]) ** 2 + abs(decimal.Decimal(user_coords[1]) - obj_coords[1]) ** 2)
    # result *= 0.0111139
    # print(result)
    # return result

    result = math.sqrt(abs(decimal.Decimal(user_coords[0]) - obj_coords[0]) ** 2 + abs(decimal.Decimal(user_coords[1]) - obj_coords[1]) ** 2)
    return math.floor(result * 111139)


print("Polling bot...")
bot.infinity_polling(timeout=10, long_polling_timeout=5)
