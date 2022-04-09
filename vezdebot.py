import sqlite3
import os
import vk_api
import urllib.request
import random
import string
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.upload import VkUpload

db_path = "./users.sqlite"
memes_path = "./memes/"
group_link = "vezdemem"
group_id = "212547232"
album_id = "283603783"
app_id = 8131807

# Возможные состояния пользователя:
# "" - Новый пользователь
# default - Главное меню
# rating - Ожидается оценка мема current_meme
# upload - Ожидается фотокарточка во вложении
# showcase_* - Показываем красивые кнопочки

class Bot:
    def __init__(self, token_bot, token_upload):
        self.api = vk_api.VkApi(token=token_bot)
        self.longpoll = VkBotLongPoll(self.api, group_id)
        self.upload_api = vk_api.VkApi(token=token_upload)
        self.upload = VkUpload(self.upload_api)
        self.db = sqlite3.connect(db_path)

        self.sync_memes()
    def __del__(self):
        self.db.close()
    def loop(self):
        for event in self.longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                peer_id = event.obj.peer_id or event.message.peer_id
                user_id = event.obj.message['from_id']
                user_state = self.get_user_state(user_id)
                response = str(event.obj.text or event.message.text).casefold()
                if response.startswith(f"[club{group_id}|@{group_link}] "):
                    response = response.split(' ', 1)[1]
                print(user_id)
                print(user_state)
                print(response)
                print('*'* 30)
                if response == "привет":
                    self.send_message(peer_id, "Привет Вездекодерам!")
                elif response == "статистика":
                    likes, dislikes = self.get_user_stats(user_id)
                    user_stats = f'''Ваша статистика:\nЛайков: {likes}\nДизлайков: {dislikes}\n\n'''
                    likes, dislikes = self.get_summary_stats()
                    summary_stats = f'''Общая статистика:\nЛайков: {likes}\nДизлайков: {dislikes}\n\n'''
                    top_memes = self.get_top_memes()
                    top_memes_stats = "\n".join(f"{n}. {i[1]} лайков [https://vk.com/photo-{group_id}_{i[0]}]" for n, i in enumerate(top_memes, start=1)) # бубылда
                    attachments = ",".join(f"photo-{group_id}_{i[0]}" for i in top_memes)
                    self.send_message(peer_id, user_stats + summary_stats + top_memes_stats, attachments=attachments)
                elif user_state == "default":
                    if response == "мем":
                        meme_id = self.get_meme(user_id)
                        if meme_id == "":
                            keyboard = self.get_keyboard("default")
                            self.send_message(peer_id, "Мемы закончились, приходи позже. Так же ты всегда можешь добавить новые мемы командой \"Добавить мем\".", keyboard=keyboard)
                        else:
                            self.set_user_state(user_id, "rating", meme_id)
                            keyboard = self.get_keyboard("rating")
                            photo_url = f"photo-{group_id}_{meme_id}"
                            self.send_message(peer_id, attachments=[photo_url], keyboard=keyboard)
                    elif response == "добавить мем":
                        self.set_user_state(user_id, "upload")
                        keyboard = self.get_keyboard("upload")
                        self.send_message(peer_id, "Пришли мем картинкой и я его добавлю.", keyboard=keyboard)
                elif user_state == "upload":
                    if response == "отмена":
                        self.set_user_state(user_id, "default")
                        keyboard = self.get_keyboard("default")
                        self.send_message(peer_id, "На случай если передумаешь ты можешь загрузить мем в любой момент!", keyboard=keyboard)
                    else:
                        memes_found = False
                        for attach in event.obj.message['attachments']:
                            if attach['type'] == "photo":
                                memes_found = True
                                meme_id = self.reupload_photo(attach['photo'])
                                self.add_meme(meme_id)
                        if memes_found:
                            self.set_user_state(user_id, "default")
                            keyboard = self.get_keyboard("default")
                            self.send_message(peer_id, "Мемы успешно загружены.", keyboard=keyboard)
                        else:
                            self.send_message(peer_id, "Для добавления мема отправь его как картинку.")
                elif user_state == "rating":
                    meme_id = self.get_user_current_meme(user_id)
                    if response == "👍":
                        self.set_user_state(user_id, "default")
                        self.set_user_reaction(user_id, meme_id, 1)
                        keyboard = self.get_keyboard("default")
                        self.send_message(peer_id, "Голос учтён!", keyboard=keyboard)
                    elif response == "👎":
                        self.set_user_state(user_id, "default")
                        self.set_user_reaction(user_id, meme_id, -1)
                        keyboard = self.get_keyboard("default")
                        self.send_message(peer_id, "Голос учтён!", keyboard=keyboard)
                    else:
                        keyboard = self.get_keyboard("rating")
                        self.send_message(peer_id, "Чтобы продолжить оцените мем.", keyboard=keyboard)
                elif user_state == "":
                    self.create_user(user_id)
                    self.set_user_state(user_id, "showcase_1")
                    self.send_message(peer_id, "Привет, по ТЗ тут надо показать мега-крутую клавиатуру, помоги мне с этим и ответь на пару вопросов!")
                    keyboard = self.get_keyboard("showcase_1")
                    self.send_message(peer_id, "Любишь мемы?", keyboard=keyboard)
                elif user_state.startswith("showcase") and response == "пропустить вопросы":
                    self.set_user_state(user_id, "default")
                    keyboard = self.get_keyboard("default")
                    self.send_message(peer_id, "Тогда приступим к самому интересному!\nМем можно получить. Командой \"Мем\". Её я дам. Оценить его нужно по своему мнению. Мнение я не дам.",
                                      keyboard=keyboard)
                elif user_state == "showcase_1":
                    self.set_user_state(user_id, "showcase_2")
                    if response == "да":
                        self.send_message(peer_id, "Отлично!")
                    elif response == "нет":
                        self.send_message(peer_id, "Надеюсь, наши мемы тебе всё-таки понравятся!")
                    keyboard = self.get_keyboard("showcase_2")
                    self.send_message(peer_id, "Какое твоё любимое время года?", keyboard=keyboard)
                elif user_state == "showcase_2":
                    self.set_user_state(user_id, "showcase_3")
                    self.send_message(peer_id, "Хороший выбор!")
                    keyboard = self.get_keyboard("showcase_3")
                    self.send_message(peer_id, "А теперь выбери цифру от 1 до 9!", keyboard=keyboard)
                elif user_state == "showcase_3":
                    self.set_user_state(user_id, "showcase_4")
                    keyboard = self.get_keyboard("showcase_4")
                    self.send_message(peer_id, "Какую кнопку нажмёшь?", keyboard=keyboard)
                elif user_state == "showcase_4":
                    self.set_user_state(user_id, "showcase_5")
                    keyboard = self.get_keyboard("showcase_5")
                    self.send_message(peer_id, "Любишь кошечек или собачек?", keyboard=keyboard)
                elif user_state == "showcase_5":
                    self.set_user_state(user_id, "showcase_6")
                    keyboard = self.get_keyboard("showcase_6")
                    self.send_message(peer_id, "Какая профессия у повара?", keyboard=keyboard)
                elif user_state == "showcase_6":
                    self.set_user_state(user_id, "showcase_7")
                    self.send_message(peer_id, "Хаааа, а твояяя??")
                    keyboard = self.get_keyboard("showcase_7")
                    self.send_message(peer_id, "Какие фильмы любишь смотреть?", keyboard=keyboard)
                elif user_state == "showcase_7":
                    self.set_user_state(user_id, "showcase_8")
                    keyboard = self.get_keyboard("showcase_8")
                    self.send_message(peer_id, "Понравился опрос? Только честно!", keyboard=keyboard)
                elif user_state == "showcase_8":
                    self.set_user_state(user_id, "default")
                    keyboard = self.get_keyboard("default")
                    self.send_message(peer_id, "Спасибо! Теперь ты можешь получать мемы с помощью команды \"Мем\", а так же оценивать их!",
                                        keyboard=keyboard)

    def get_keyboard(self, state, one_time=False):
        keyboard = VkKeyboard(one_time=one_time)
        if state == "default":
            keyboard.add_button("Мем", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("Добавить мем", color=VkKeyboardColor.POSITIVE)
            keyboard.add_line()
            keyboard.add_button("Статистика", color=VkKeyboardColor.SECONDARY)
        elif state == "rating":
            keyboard.add_button("👍", color=VkKeyboardColor.POSITIVE)
            keyboard.add_button("👎", color=VkKeyboardColor.NEGATIVE)
        elif state == "upload":
            keyboard.add_button("Отмена", color=VkKeyboardColor.NEGATIVE)
        elif state == "showcase_1":
            keyboard.add_button("Да", color=VkKeyboardColor.POSITIVE)
            keyboard.add_button("Нет", color=VkKeyboardColor.NEGATIVE)
            keyboard.add_line()
            keyboard.add_button("Пропустить вопросы", color=VkKeyboardColor.SECONDARY)
        elif state == "showcase_2":
            keyboard.add_button("🌸 Весна", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("☀️ Лето", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("❄️ Зима", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("🍁 Осень", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("Пропустить вопросы", color=VkKeyboardColor.SECONDARY)
        elif state == "showcase_3":
            keyboard.add_button("1️⃣", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("2️⃣", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("3️⃣", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("4️⃣", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("5️⃣", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("6️⃣", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("7️⃣", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("8️⃣", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("9️⃣", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("Пропустить вопросы", color=VkKeyboardColor.SECONDARY)
        elif state == "showcase_4":
            keyboard.add_button("Эту!", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("Или эту?", color=VkKeyboardColor.NEGATIVE)
            keyboard.add_line()
            keyboard.add_button("Нет, эту!", color=VkKeyboardColor.POSITIVE)
            keyboard.add_line()
            keyboard.add_button("Пропустить вопросы", color=VkKeyboardColor.SECONDARY)
        elif state == "showcase_5":
            keyboard.add_button("🐈 Кошечек", color=VkKeyboardColor.POSITIVE)
            keyboard.add_button("🐕 Собачек", color=VkKeyboardColor.POSITIVE)
            keyboard.add_line()
            keyboard.add_button("🍽️ И те, и другие очень вкусные!", color=VkKeyboardColor.NEGATIVE)
            keyboard.add_line()
            keyboard.add_button("Пропустить вопросы", color=VkKeyboardColor.SECONDARY)
        elif state == "showcase_6":
            keyboard.add_button("👨‍🍳 ПОВАР!!!", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("Пропустить вопросы", color=VkKeyboardColor.SECONDARY)
        elif state == "showcase_7":
            keyboard.add_button("Комедии", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("Ужасы", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("Триллеры", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("Драмы", color=VkKeyboardColor.PRIMARY)
            keyboard.add_button("Мюзиклы", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("Пропустить вопросы", color=VkKeyboardColor.SECONDARY)
        elif state == "showcase_8":
            keyboard.add_button("Да", color=VkKeyboardColor.POSITIVE)
            keyboard.add_line()
            keyboard.add_button("Да", color=VkKeyboardColor.POSITIVE)
            keyboard.add_button("Да", color=VkKeyboardColor.POSITIVE)
            keyboard.add_line()
            keyboard.add_button("Да", color=VkKeyboardColor.POSITIVE)
            keyboard.add_line()
            keyboard.add_button("This poll sucks", color=VkKeyboardColor.NEGATIVE)
            keyboard.add_line()
            keyboard.add_button("Пропустить вопросы", color=VkKeyboardColor.SECONDARY)
        return keyboard
    def send_message(self, peer_id, msg="", attachments=None, keyboard=None):
        self.api.method('messages.send', {'peer_id': peer_id,
                                          'random_id': get_random_id(),
                                          'message': msg,
                                          'attachment': attachments,
                                          'keyboard': keyboard.get_keyboard() if keyboard is not None else None})
    def sync_memes(self, offset=0, count=50):
        response = self.upload_api.method('photos.get', {'owner_id': "-" + group_id,
                                                         'album_id': album_id})
        ids = []
        for item in response['items']:
            ids.append((item['id'], 0))
        cur = self.db.cursor()
        cur.executemany('''INSERT OR IGNORE INTO memes (meme_id, rating) 
                           VALUES (?, ?)''', ids)
        self.db.commit()
        if offset + count < response['count']:
            self.sync_memes(offset + count)
    def add_meme(self, meme_id):
        cur = self.db.cursor()
        cur.execute(f'''INSERT INTO memes (meme_id, rating) 
                        VALUES ({meme_id}, 0)''')
        self.db.commit()
    def reupload_photo(self, photo):
        # Ищем максимальное разрешение картинки
        # Приоритет: w > z > y > x > m > s
        max_priority = ""
        photo_url = ""
        for size in photo['sizes']:
            if size['type'] == "w":
                photo_url = size['url']
                break
            elif size['type'] == "z" and max_priority not in ["w"]:
                max_priority = "z"
                photo_url = size['url']
            elif size['type'] == "y" and max_priority not in ["w", "z"]:
                max_priority = "y"
                photo_url = size['url']
            elif size['type'] == "x" and max_priority not in ["w", "z", "y"]:
                max_priority = "x"
                photo_url = size['url']
            elif size['type'] == "m" and max_priority not in ["w", "z", "y", "x"]:
                max_priority = "m"
                photo_url = size['url']
            elif size['type'] == "s" and max_priority not in ["w", "z", "y", "x", "m"]:
                max_priority = "s"
                photo_url = size['url']
        letters = string.ascii_letters + string.digits
        filename = f"{os.path.abspath(os.path.dirname(__file__))}/{''.join(random.choice(letters) for i in range(32))}.jpg" # бубылда №2
        urllib.request.urlretrieve(photo_url, filename)
        photo = self.upload.photo(filename,
                                    album_id=album_id,
                                    group_id=group_id)
        os.remove(filename)
        return photo[0]['id']
    def get_meme(self, user_id):
        cur = self.db.cursor()
        cur.execute(f'''SELECT meme_id FROM memes WHERE meme_id NOT IN ( 
            SELECT meme_id FROM users_reactions WHERE user_id={user_id} 
            ) ORDER BY RANDOM() LIMIT 1''')
        item = cur.fetchone()
        return "" if item is None else item[0]
    def get_user_state(self, user_id):
        cur = self.db.cursor()
        cur.execute(f'''SELECT state FROM users WHERE user_id={user_id}''')
        item = cur.fetchone()
        return "" if item is None else item[0]
    def get_user_current_meme(self, user_id):
        cur = self.db.cursor()
        cur.execute(f'''SELECT current_meme FROM users WHERE user_id={user_id}''')
        item = cur.fetchone()
        return "" if item is None else item[0]
    def get_user_stats(self, user_id):
        cur = self.db.cursor()
        cur.execute(f'''SELECT likes, dislikes FROM users WHERE user_id={user_id}''')
        item = cur.fetchone()
        return (0, 0) if item is None else (item[0], item[1])
    def get_summary_stats(self):
        cur = self.db.cursor()
        cur.execute(f'''SELECT likes, dislikes FROM stats WHERE id=0''')
        item = cur.fetchone()
        return (0, 0) if item is None else (item[0], item[1])
    def get_top_memes(self):
        cur = self.db.cursor()
        cur.execute(f'''SELECT meme_id, rating FROM memes ORDER BY rating DESC LIMIT 9''')
        items = []
        for item in cur.fetchall():
            items.append((item[0], item[1]))
        return items
    def set_user_state(self, user_id, state, current_meme=None):
        cur = self.db.cursor()
        cur.execute(f'''UPDATE users SET state = "{state}", current_meme = "{current_meme}"
                        WHERE user_id={user_id}''')
        self.db.commit()
    def set_user_reaction(self, user_id, meme_id, reaction):
        cur = self.db.cursor()
        cur.execute(f'''INSERT INTO users_reactions (user_id, meme_id, reaction) 
                    VALUES ("{user_id}", "{meme_id}", {reaction})''')
        cur.execute(f'''UPDATE memes SET rating = rating + {reaction} WHERE meme_id={meme_id}''')
        cur.execute(f'''UPDATE users SET {"likes" if reaction > 0 else "dislikes"} = {"likes" if reaction > 0 else "dislikes"} + 1 WHERE user_id={user_id}''')
        cur.execute(f'''UPDATE stats SET {"likes" if reaction > 0 else "dislikes"} = {"likes" if reaction > 0 else "dislikes"} + 1 WHERE id=0''')
        self.db.commit()
    def create_user(self, user_id):
        cur = self.db.cursor()
        cur.execute(f'''INSERT INTO users (user_id, likes, dislikes) 
                        VALUES ({user_id}, 0, 0)''')
        self.db.commit()

def __init_db():
    db = sqlite3.connect(db_path)
    cur = db.cursor()
    cur.execute('''CREATE TABLE stats (
        id INTEGER PRIMARY KEY CHECK (id = 0),
        likes INTEGER NOT NULL DEFAULT 0,
        dislikes INTEGER NOT NULL DEFAULT 0
        )''')
    cur.execute('''INSERT OR REPLACE INTO stats (id, likes, dislikes) VALUES (0, 0, 0)''')
    cur.execute('''CREATE TABLE users (
        user_id INTEGER PRIMARY KEY,
        state TEXT,
        current_meme TEXT,
        likes INTEGER,
        dislikes INTEGER
        )''')
    cur.execute('''CREATE TABLE users_reactions (
        user_id INTEGER,
        meme_id INTEGER,
        reaction INTEGER,
        UNIQUE(user_id, meme_id)
        )''')
    cur.execute('''CREATE TABLE memes (
        meme_id INTEGER PRIMARY KEY,
        rating INTEGER NOT NULL DEFAULT 0
        )''')
    db.commit()
    db.close()

if __name__ == "__main__":
    if not os.path.isfile(db_path):
        __init_db()
    token_bot = ""
    with open("./token_bot.txt", "r") as token:
        token_bot = token.read()
    token_upload = ""
    with open("./token_upload.txt", "r") as token:
        token_upload = token.read()
    bot = Bot(token_bot, token_upload)
    bot.loop()
