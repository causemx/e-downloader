import asyncio
import aiohttp
import ehentai
from gallery import Gallery
import os
import copy
import json


async def download(session, gallery_url):
    gallery = Gallery.from_url(gallery_url)
    await gallery.load_preview(session)

    planned_pages = asyncio.queues.Queue()
    unloaded_pages = asyncio.queues.Queue()
    loaded_pages = asyncio.queues.Queue()

    async def get_page():
        page_id = await planned_pages.get()
        page = await gallery.get_page(session, page_id)
        await unloaded_pages.put(page)
        planned_pages.task_done()

    async def load_page():
        page = await unloaded_pages.get()
        await page.load(session)
        await loaded_pages.put(page)
        unloaded_pages.task_done()

    async def download_image():
        page = await loaded_pages.get()
        #print(page.get_url())
        try:
            data = await ehentai.fetch_data(session, page.img_url, timeout=60)
        except asyncio.TimeoutError:
            await unloaded_pages.put(page)
        except aiohttp.BadStatusLine:
            await unloaded_pages.put(page)
        except aiohttp.DisconnectedError:
            await unloaded_pages.put(page)
        except aiohttp.ClientResponseError:
            await unloaded_pages.put(page)
        except:
            raise
        else:
            open(target_dir + page.img_url.split('/')[-1], 'wb').write(data)
        loaded_pages.task_done()

    async def do_forever(job):
        try:
            while True:
                await job()
        except asyncio.CancelledError:
            pass
        except:
            import traceback
            traceback.print_exc()

    target_dir = './Images/' + gallery.name + '/'
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    for i in range(gallery.page_count):
        await planned_pages.put(i+1)

    workers = [asyncio.ensure_future(do_forever(get_page)) for __ in range(1)]
    workers += [asyncio.ensure_future(do_forever(load_page)) for __ in range(3)]
    workers += [asyncio.ensure_future(do_forever(download_image)) for __ in range(20)]

    await planned_pages.join()
    while unloaded_pages.qsize() != 0 or unloaded_pages._unfinished_tasks != 0 or loaded_pages.qsize() != 0 or loaded_pages._unfinished_tasks != 0:
        await unloaded_pages.join()
        await loaded_pages.join()

    for worker in workers:
        worker.cancel()


def main(args):
    cookie_file_path = './cookie.txt'
    # load cookies
    if os.path.exists(cookie_file_path):
        cookies = open(cookie_file_path).read()
        cookiejar = ehentai.GreatCookieJar.from_string(cookies)
    else:
        cookiejar = ehentai.GreatCookieJar()
        cookies = input('document.cookie: ')
        if cookies.startswith('\"') and cookies.endswith('\"'):
            cookies = json.loads(cookies)
        cookies = ehentai.convert_cookies(cookies)
        cookiejar.update(cookies)
        open(cookie_file_path, 'w').write(repr(cookiejar))

    loop = asyncio.get_event_loop()
    #loop.set_debug(True)

    conn = aiohttp.TCPConnector(limit=20)
    with aiohttp.ClientSession(loop=loop, connector=conn, cookies=cookiejar.get_dict()) as session:
        loop.run_until_complete(download(session, 'https://exhentai.org/g/961036/1ee98dcd48/'))

    # save cookies
    cookiejar.update(session.cookies)
    open(cookie_file_path, 'w').write(repr(cookiejar))


if __name__ == '__main__':
    import sys
    main(sys.argv[1:])

