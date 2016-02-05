import asyncio
import os
from ehentai import fetch_text_ensure
from ehentai import parse_html
from ehentai import fetch_data_ensure


def get_between(s, beg, end):
    '''Get a substring of s starts with beg and ends with end.'''
    return s.split(beg)[-1].split(end)[0]

def parse_int(s):
    '''Remove comma in the number and convert it to int.'''
    return int(s.replace(',', ''))


class Gallery:
    def __init__(self, gallery_id, gallery_token):
        self.gallery_id = gallery_id
        self.token = gallery_token
        self.content_map = None
        self.loaded = False

    async def load_preview(self, session, preview_page=0, domain='exhentai.org'):
        url = self.get_url(preview_page, domain)
        html = await fetch_text_ensure(session, url)
        doc = parse_html(html)

        name_en = doc.find('.//h1[@id="gn"]')
        if name_en is not None:
            self.name_en = name_en.text
        name_jp = doc.find('.//h1[@id="gj"]')
        if name_jp is not None:
            self.name_jp = name_jp.text
        
        parts = doc.find('.//div[@class="gtb"]/p[@class="gpc"]').text.split(' ')
        self.img_count = parse_int(parts[5])
        preview_beg = parse_int(parts[1])
        preview_end = parse_int(parts[3])
        if preview_end != self.img_count:
            self.preview_range = preview_end - preview_beg + 1

        imgs = doc.findall('.//div[@id="gdt"]/div/div/a')
        page_urls = [img.attrib['href'] for img in imgs]
        pages = [GalleryPage.from_url(url) for url in page_urls]

        if self.content_map is None:
            self.content_map = {}

        self.content_map.update({page.page: page for page in pages})
        self.loaded = True

    def get_url(self, preview_page=0, domain='exhentai.org'):
        if preview_page == 0:
            url = 'http://{}/g/{}/{}/'.format(
                domain,
                self.gallery_id,
                self.token)
        else:
            url = 'http://{}/g/{}/{}/?p={}'.format(
                domain,
                self.gallery_id,
                self.token, 
                preview_page)
        return url

    async def get_page(self, session, page, domain='exhentai.org'):
        if not self.loaded:
            raise NotLoadedError()
        if page in self.content_map:
            return self.content_map[page]
        if (page - 1) in self.content_map:
            p = self.content_map[page - 1]
            if p.loaded:
                self.content_map[page] = p.next
                return p.next
        if (page + 1) in self.content_map:
            p = self.content_map[page + 1]
            if p.loaded:
                self.content_map[page] = p.prev
                return p.prev
        preview_page = (page - 1) // self.preview_range
        await self.load_preview(session, preview_page=preview_page, domain=domain)
        return self.content_map[page]

    @property
    def name(self):
        if not self.loaded:
            raise NotLoadedError()
        if hasattr(self, 'name_jp'):
            return self.name_jp
        if hasattr(self, 'name_en'):
            return self.name_en
        return None

    @staticmethod
    def parse_url(url):
        if '?p=' in url:
            url, page = url.split('?p=')
            page = int(page)
        else:
            page = 0
        part = url.split('/')
        assert(part[3] == 'g')
        token = part[-2]
        gallery_id = int(part[-3])
        domain = part[2]
        return {'domain': domain, 'galleryid': gallery_id, 'token': token, 'page': page}

    @staticmethod
    def from_url(url):
        result = Gallery.parse_url(url)
        return Gallery(result['galleryid'], result['token'])


class GalleryPage:
    def __init__(self, gallery_id, page_token, page, reload_info=''):
        self.gallery_id = gallery_id
        self.token = page_token
        self.page = page
        self.loaded = False
        self.reload_info = reload_info

    async def load(self, session, domain='exhentai.org'):
        url = self.get_url()
        html = await fetch_text_ensure(session, url)
        doc = parse_html(html)

        self.img_url = doc.find('.//img[@id="img"]').attrib['src']
        
        prev_url = doc.find('.//a[@id="prev"]').attrib['onclick']
        prev_page = int(get_between(prev_url, '(', ','))
        prev_token = get_between(prev_url, ',', ')')[1:-1]
        self.prev = GalleryPage(self.gallery_id, prev_token, prev_page)

        next_url = doc.find('.//a[@id="next"]').attrib['onclick']
        next_page = int(get_between(next_url, '(', ','))
        next_token = get_between(next_url, ',', ')')[1:-1]
        self.next = GalleryPage(self.gallery_id, next_token, next_page)

        preview_url = doc.find('.//div[@id="i5"]/div/a').attrib['href']
        self.preview_page = int(preview_url.split('?p=')[-1]) if '?p=' in preview_url else 0

        self.file_name, self.img_size, self.file_length = doc.find('.//div[@id="i4"]/div[1]').text.split(' :: ')
        self.img_size = [int(n) for n in self.img_size.split(' x ')]

        reload_info = doc.find('.//a[@id="loadfail"]').attrib['onclick']
        reload_info = get_between(reload_info, "('", "')")[1:-1]
        self.append_reload_info(reload_info)

        if doc.find('.//div[@id="i7"]'):
            self.origin_url = doc.find('.//div[@id="i7"]/a').attrib['href']
        else:
            self.origin_url = self.img_url

        self.gallery_name = doc.find('.//h1').text

        self.loaded = True

    def append_reload_info(self, reload_info):
        if self.reload_info:
            self.reload_info += '&nl=' + reload_info
        else:
            self.reload_info = '?nl=' + reload_info

    def get_url(self, domain='exhentai.org'):
        url = 'http://{}/s/{}/{}-{}'.format(
            domain,
            self.token,
            self.gallery_id,
            self.page)
        if self.reload_info:
            url += self.reload_info
        return url

    @staticmethod
    def parse_url(url):
        result = {}
        if '?' in url:
            url, reload_info = url.split('?')
            result['reload_info'] = reload_info
        part = url.split('/')
        assert(part[3] == 's')
        domain = part[2]
        gallery_id, page = part[-1].split('-')
        gallery_id = int(gallery_id)
        page = int(page)
        page_token = part[-2]
        result.update({'domain': domain,
                       'galleryid': gallery_id,
                       'token': page_token,
                       'page': page})
        return result

    @staticmethod
    def from_url(url):
        result = GalleryPage.parse_url(url)
        return GalleryPage(result['galleryid'], result['token'], result['page'], result.get('reload_info', ''))


async def fetch_gallery(session, url, download_method):
    gallery = Gallery.from_url(url)
    await gallery.load_preview(session)

    loop = asyncio.get_event_loop()
    tasks = []

    for i in range(1, gallery.img_count + 1):
        page = await gallery.get_page(session, i)
        task = loop.create_task(download_method(session, page))
        tasks.append(task)
        await asyncio.sleep(0.3)
    await asyncio.wait(tasks)

async def download(session, page, output_method=None):
    if output_method is None:
        def output_method(p):
            return '{curdir}{sep}images{sep}{galleryname}{sep}{filename}'.format(
                curdir=os.curdir,
                sep=os.sep,
                filename=p.file_name,
                galleryname=p.gallery_name)

    if not page.loaded:
        await page.load(session)
    data = await fetch_data_ensure(session, page.img_url)

    filename = output_method(page)
    dirname = os.path.dirname(filename)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    print(filename)

    try:
        f = None
        f = open(filename, 'wb')
        f.write(data)
    except:
        raise
    finally:
        if f:
            f.close()


class NotLoadedError(BaseException):
    pass
