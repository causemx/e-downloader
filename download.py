from gallery import Gallery
import ehentai
import aiohttp
import os
import asyncio
import re
import traceback
import math


def patch_yarl_quote():
    import yarl
    old_quote = yarl.quote
    def quote(s, safe='', **kwargs):
        return old_quote(s, safe=safe+'=', **kwargs)
    yarl.quote = quote

patch_yarl_quote()


def path_escape(path):
    escape_charset = ['/', ':', '*', '\\', '&', '?']
    escape_pattern = re.compile('|'.join((re.escape(x) for x in escape_charset)))
    return escape_pattern.sub('_', path)


async def do_forever(job):
    while True:
        try:
            await job()
        except asyncio.CancelledError:
            break
        except:
            traceback.print_exc()


class Downloader:
    def __init__(self, session, gallery_url, force_origin=False, page_fetcher_num=1,
                 page_loader_num=2, image_downloader_num=10, download_timeout=7.0):
        self.session = session
        self.download_timeout = download_timeout
        self.force_origin = force_origin
        self.page_fetcher_num = page_fetcher_num
        self.page_loader_num = page_loader_num
        self.image_downloader_num = image_downloader_num
        self.gallery = Gallery.from_url(gallery_url)

        self.planned_pages = asyncio.queues.Queue()
        self.unloaded_pages = asyncio.queues.Queue()
        self.loaded_pages = asyncio.queues.Queue()

    async def get_page(self):
        page_id = await self.planned_pages.get()
        page = await self.gallery.get_page(self.session, page_id)
        await self.unloaded_pages.put(page)
        self.planned_pages.task_done()

    async def load_page(self):
        page = await self.unloaded_pages.get()
        await page.load(self.session)
        await self.loaded_pages.put(page)
        self.unloaded_pages.task_done()

    async def download_image(self):
        page = await self.loaded_pages.get()
        image_url = page.origin_url if self.force_origin else page.img_url
        print('downloading:', page.page)

        async def failed():
            print('failed:', page.page)
            await self.unloaded_pages.put(page)

        try:
            data = await ehentai.fetch_data(self.session, image_url, timeout=self.download_timeout)
        except asyncio.TimeoutError:
            await failed()
        except aiohttp.ClientError:
            await failed()
        except aiohttp.ServerDisconnectedError:
            await failed()
        except aiohttp.ServerConnectionError:
            await failed()
        else:
            print('done:', page.page)
            with self.open_output_file(page) as f:
                f.write(data)
        self.loaded_pages.task_done()

    async def start(self):
        if not self.gallery.loaded:
            await self.gallery.load_preview(self.session)

        for i in range(self.gallery.page_count):
            await self.planned_pages.put(i+1)

        self.workers = workers = [asyncio.ensure_future(do_forever(self.get_page)) for __ in range(self.page_fetcher_num)]
        workers += [asyncio.ensure_future(do_forever(self.load_page)) for __ in range(self.page_loader_num)]
        workers += [asyncio.ensure_future(do_forever(self.download_image)) for __ in range(self.image_downloader_num)]

    async def join(self):
        await self.planned_pages.join()
        # await unloaded_pages and loaded_pages
        while self.unloaded_pages.qsize() != 0 or self.unloaded_pages._unfinished_tasks != 0 or self.loaded_pages.qsize() != 0 or self.loaded_pages._unfinished_tasks != 0:
            await self.unloaded_pages.join()
            await self.loaded_pages.join()

        for worker in self.workers:
            worker.cancel()

    def open_output_file(self, page):
        filled_num = str(page.page).zfill(int(math.log10(self.gallery.page_count)) + 1)
        path = './Images/{}/{}-{}'.format(path_escape(self.gallery.name), filled_num, path_escape(page.file_name))
        return open(path, 'wb')


async def download(*args, **kwargs):
    downloader = Downloader(*args, **kwargs)
    await downloader.gallery.load_preview(downloader.session)
    output_dir = './Images/' + path_escape(downloader.gallery.name)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    await downloader.start()
    await downloader.join()