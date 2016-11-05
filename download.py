from gallery import Gallery
import ehentai
import aiohttp
import os
import asyncio


def patch_yarl_quote():
    import yarl
    old_quote = yarl.quote
    def quote(s, safe='', **kwargs):
        return old_quote(s, safe=safe+'=', **kwargs)
    yarl.quote = quote

patch_yarl_quote()


async def download(session, gallery_url, output_dir='./Images/', force_origin=False,
                   page_fetcher_num=1, page_loader_num=2, image_downloader_num=10,
                   download_timeout=7.0):
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
        image_url = page.origin_url if force_origin else page.img_url
        print('downloading:', page.page)

        async def failed():
            print('failed:', page.page)
            await unloaded_pages.put(page)

        try:
            data = await ehentai.fetch_data(session, image_url, timeout=download_timeout)
        except asyncio.TimeoutError:
            await failed()
        except aiohttp.BadStatusLine:
            await failed()
        except aiohttp.DisconnectedError:
            await failed()
        except aiohttp.ClientResponseError:
            await failed()
        except aiohttp.ClientOSError:
            await failed()
        else:
            print('done:', page.page)
            open(target_dir + page.img_url.split('/')[-1], 'wb').write(data)
        loaded_pages.task_done()

    async def do_forever(job):
        while True:
            try:
                await job()
            except asyncio.CancelledError:
                break
            except:
                import traceback
                traceback.print_exc()

    target_dir = output_dir + gallery.name + '/'
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    for i in range(gallery.page_count):
        await planned_pages.put(i+1)

    workers = [asyncio.ensure_future(do_forever(get_page)) for __ in range(page_fetcher_num)]
    workers += [asyncio.ensure_future(do_forever(load_page)) for __ in range(page_loader_num)]
    workers += [asyncio.ensure_future(do_forever(download_image)) for __ in range(image_downloader_num)]

    await planned_pages.join()
    # await unloaded_pages and loaded_pages
    while unloaded_pages.qsize() != 0 or unloaded_pages._unfinished_tasks != 0 or loaded_pages.qsize() != 0 or loaded_pages._unfinished_tasks != 0:
        await unloaded_pages.join()
        await loaded_pages.join()

    for worker in workers:
        worker.cancel()
