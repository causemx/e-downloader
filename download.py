import asyncio
import aiohttp
import ehentai
from gallery import Gallery
import os
import json
import argparse


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
        print('downloading:', page.get_url().split('?')[0])
        try:
            data = await ehentai.fetch_data(session, page.img_url, timeout=2.0)
        except asyncio.TimeoutError:
            await unloaded_pages.put(page)
        except aiohttp.BadStatusLine:
            await unloaded_pages.put(page)
        except aiohttp.DisconnectedError:
            await unloaded_pages.put(page)
        except aiohttp.ClientResponseError:
            await unloaded_pages.put(page)
        except aiohttp.ClientOSError:
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
    workers += [asyncio.ensure_future(do_forever(load_page)) for __ in range(2)]
    workers += [asyncio.ensure_future(do_forever(download_image)) for __ in range(20)]

    await planned_pages.join()
    # await unloaded_pages and loaded_pages
    while unloaded_pages.qsize() != 0 or unloaded_pages._unfinished_tasks != 0 or loaded_pages.qsize() != 0 or loaded_pages._unfinished_tasks != 0:
        await unloaded_pages.join()
        await loaded_pages.join()

    for worker in workers:
        worker.cancel()


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('--cookie_file', type=str, default='./cookie.txt', dest='cookie_file_path',
                        help='location of the file to store cookies')
    parser.add_argument('--cookie_str', type=str, dest='cookie_str',
                        help='document.cookie string from the browser')
    parser.add_argument('--proxy', type=str, dest='proxy',
                        help='http proxy through which data is downloaded')
    parser.add_argument('gallery_url', type=str,
                        help='url of the gallery to download')
    args = parser.parse_args(args)

    # load cookies
    cookiejar = prepare_cookies(args)

    loop = asyncio.get_event_loop()
    #loop.set_debug(True)

    if args.proxy:
        connector = aiohttp.ProxyConnector(args.proxy)
    else:
        connector = None
    with aiohttp.ClientSession(loop=loop, connector=connector, cookies=cookiejar.get_dict()) as session:
        loop.run_until_complete(download(session, args.gallery_url))

    # save cookies
    cookiejar.update(session.cookies)
    open(args.cookie_file_path, 'w').write(repr(cookiejar))


def prepare_cookies(args):
    path = args.cookie_file_path
    if os.path.exists(path):
        cookies = open(path).read()
        cookiejar = ehentai.GreatCookieJar.from_string(cookies)
    else:
        cookiejar = ehentai.GreatCookieJar()
        if args.cookie_str:
            cookies = args.cookie_str
        else:
            cookies = input('document.cookie: ')
        if cookies.startswith('\"') and cookies.endswith('\"'):
            cookies = json.loads(cookies)
        cookies = ehentai.convert_cookies(cookies)
        cookiejar.update(cookies)
        open(cookie_file_path, 'w').write(repr(cookiejar))
    return cookiejar


if __name__ == '__main__':
    from sys import argv
    main(argv[1:])
