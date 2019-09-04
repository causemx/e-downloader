import logging
import re
import io
import asyncio
import time

import aiohttp
from aiogram import Bot, Dispatcher, executor, types
import sqlalchemy
from sqlalchemy import Table, Column, Integer, Boolean, Text

from gallery import Gallery

import botconfig as config

# Configure logging
logging.basicConfig(level=logging.INFO)

engine = sqlalchemy.create_engine('sqlite:///bot.sqlite3')
metadata = sqlalchemy.MetaData()
group_table = Table(
    'group', metadata,
    Column('id', Integer, primary_key=True),
    Column('enabled', Boolean, nullable=False),
    Column('title', Text, nullable=False),
    Column('last_update', Integer, nullable=False),
)
metadata.create_all(engine)

def get_group_enabled(chat: types.Chat) -> bool:
    result = engine.execute(group_table.select(group_table.c.id == chat.id))
    result = result.fetchone()
    if result is None:
        return False
    return result['enabled']

def set_group_enabled(chat: types.Chat, enabled: bool):
        old_record = engine.execute(group_table.select(group_table.c.id == chat.id)).fetchone()
        if old_record is None:
            engine.execute(group_table.insert().\
                values(
                    id=chat.id,
                    enabled=enabled,
                    title=chat.title,
                    last_update=time.time(),
            ))
        else:
            engine.execute(
                group_table.update().\
                where(group_table.c.id == chat.id).\
                values(
                    enabled=enabled,
                    title=chat.title,
                    last_update=time.time(),
                )
            )

# Initialize bot and dispatcher
bot = Bot(token=config.API_TOKEN)
dp = Dispatcher(bot)

gallery_url_pattern = re.compile(r'(https?://(exhentai|e-hentai)\.org/g/\d+/[a-z0-9]+)')

@dp.message_handler(commands=['start', 'help'])
async def help(message: types.Message):
    await message.reply(f'Hi, I\'m {config.BOT_NAME}. Send me a E-Hentai link and I will give you info about the gallery.')

@dp.message_handler(commands=['info'])
async def info(message: types.Message):
    lines = [
        'timestamp: {}'.format(int(time.time())),
        'user id: {}'.format(message.from_user.id),
    ]
    if is_group_chat(message.chat):
        lines += [
            'group id: {}'.format(message.chat.id),
            'group enabled: {}'.format(get_group_enabled(message.chat)),
        ]
    await message.reply('\n'.join(lines))

@dp.message_handler(commands=['enable'])
async def enable(message: types.Message):
    if not is_group_chat(message.chat):
        await message.reply('This command can only be used in group chats.')
        return

    set_group_enabled(message.chat, True)
    await message.reply('E-Hentai gallery info enabled.')

@dp.message_handler(commands=['disable'])
async def disable(message: types.Message):
    if not is_group_chat(message.chat):
        await message.reply('This command can only be used in group chats.')
        return

    set_group_enabled(message.chat, False)
    await message.reply('E-Hentai gallery info disabled.')

@dp.message_handler()
async def handle_all(message: types.Message):
    if is_group_chat(message.chat) and not get_group_enabled(message.chat):
        return

    all_urls = gallery_url_pattern.findall(message.text)
    all_urls = [groups[0] for groups in all_urls]
    if not all_urls:
        return

    loop = asyncio.get_event_loop()

    pending = []
    for url in all_urls:
        gallery = Gallery.from_url(url)
        task = asyncio.create_task(send_gallery_info(message, gallery))
        pending.append(task)

    while pending:
        done, pending = await asyncio.wait(pending)


async def send_gallery_info(src_message: types.Message, gallery: Gallery):
    async with aiohttp.ClientSession(trust_env=True) as session:
        session.cookie_jar.load('./cookies.dat')
        if not gallery.loaded:
            await gallery.load_preview(session)

        title = gallery.name
        tags = '\n'.join(
            '{}: {}'.format(namespace, ', '.join(process_tag(tag) for tag in tag_list))
            for namespace, tag_list in gallery.all_tags.items()
        )
        desc = '{}\n{}'.format(title, tags)
        first_reply = await src_message.reply(desc)

        first_page = await gallery.get_page(session, 1)
        await first_page.load(session)
        resp = await session.get(first_page.img_url)
        preface_img = await resp.read()

    await src_message.reply_photo(io.BytesIO(preface_img), desc)
    await first_reply.delete()


def is_group_chat(chat: types.Chat) -> bool:
    return chat.type in ('group', 'supergroup')


def process_tag(tag: str) -> str:
    return ' '.join(word.capitalize() for word in tag.split('_'))


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
