import asyncio
import os
import enum
import urllib.parse
import dateutil.parser
from ehentai import fetch_text_ensure
from ehentai import parse_html
from ehentai import fetch_data_ensure


def get_between(s, beg, end):
    '''Get a substring of s starts with beg and ends with end.'''
    return s.split(beg)[-1].split(end)[0]

def parse_int(s):
    '''Remove comma in the number and convert it to int.'''
    return int(s.replace(',', ''))


class NotLoadedError(BaseException):
    pass


class BadGalleryError(BaseException):
    pass


class GalleryCatalog(enum.IntEnum):
    doujinshi = 1
    manga = 2
    artistcg = 3
    gamecg = 4
    western = 5
    non_h = 6
    imageset = 7
    cosplay = 8
    asianporn = 9
    misc = 10


class Gallery:
    def __init__(self, gallery_id, gallery_token, base_url='https://g.e-hentai.org'):
        self.gallery_id = gallery_id
        self.token = gallery_token
        self.base_url = base_url
        self.content_map = None
        self.loaded = False
        self.raw_html = None
        self.parsed_document = None
        self.additional_info = None

    async def load_preview(self, session, preview_page=0):
        url = self.get_preview_page_url(preview_page)
        self.raw_html = html = await fetch_text_ensure(session, url)
        if '<title>Gallery Not Available - ' in html:
            raise BadGalleryError()

        self.parsed_document = doc = parse_html(html)

        name_en = doc.find('.//h1[@id="gn"]')
        if name_en is not None:
            self.name_en = name_en.text
        name_jp = doc.find('.//h1[@id="gj"]')
        if name_jp is not None:
            self.name_jp = name_jp.text
        
        parts = doc.find('.//div[@class="gtb"]/p[@class="gpc"]').text.split(' ')
        self.page_count = parse_int(parts[5])
        preview_beg = parse_int(parts[1])
        preview_end = parse_int(parts[3])
        if preview_end != self.page_count:
            self.preview_range = preview_end - preview_beg + 1

        imgs = doc.findall('.//div[@id="gdt"]/div/a')
        page_urls = [img.attrib['href'] for img in imgs]
        pages = [GalleryPage.from_url(url) for url in page_urls]

        if self.content_map is None:
            self.content_map = {}

        self.content_map.update({page.page: page for page in pages})
        self.loaded = True

    def get_preview_page_url(self, preview_page=0):
        if preview_page == 0:
            url = '{}/g/{}/{}/'.format(
                self.base_url,
                self.gallery_id,
                self.token)
        else:
            url = '{}/g/{}/{}/?p={}'.format(
                self.base_url,
                self.gallery_id,
                self.token, 
                preview_page)
        return url

    async def get_page(self, session, page):
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
        await self.load_preview(session, preview_page=preview_page)
        return self.content_map[page]

    @property
    def name(self):
        if not self.loaded:
            raise NotLoadedError()
        if self.name_jp is not None:
            return self.name_jp
        if self.name_en is not None:
            return self.name_en
        return None

    @staticmethod
    def parse_url(url):
        url = urllib.parse.urlparse(url)
        if url.query:
            query = urllib.parse.parse_qs(url.query)
            page = query.get('p', 0)
        else:
            page = 0
        part = url.path.split('/')
        assert(part[1] == 'g')
        gallery_id = int(part[2])
        token = part[3]
        base_url = url.scheme + '://' + url.netloc
        return {'base_url': base_url, 'gallery_id': gallery_id, 'token': token, 'page': page}

    @staticmethod
    def from_url(url):
        result = Gallery.parse_url(url)
        return Gallery(result['gallery_id'], result['token'], result['base_url'])

    @property
    def catalog(self):
        value = self.parsed_document.find('.//img[@class="ic"]').attrib['alt']
        return GalleryCatalog[value.replace('-', '_')]

    @property
    def uploader(self):
        return self.parsed_document.find('.//div[@id="gdn"]/a').text

    def get_tags(self, xpath):
        tag_lists = self.parsed_document.find('.//div[@id="taglist"]')
        tag_list = [i.attrib['id'] for i in tag_lists.findall(xpath)]
        tag_map = {}
        for tag in tag_list:
            if not tag.startswith('td_'):
                continue
            tag = tag[3:]
            if ':' in tag:
                namespace, name = tag.split(':')
                if namespace in tag_map:
                    tag_map[namespace].append(name)
                else:
                    tag_map[namespace] = [name]
            else:
                tag_map[tag] = tag
        return tag_map

    @property
    def tags(self):
        return self.get_tags('.//div[@class="gt"]')

    @property
    def downvoted_tags(self):
        return self.get_tags('.//div[@class="gtl"]')

    @property
    def average_rating(self):
        return self.parsed_document.find('.//td[@id="rating_label"]').text.split(' ')[-1]

    @property
    def upload_time(self):
        return dateutil.parser.parse(self.parsed_document.find('.//tr[td="Posted:"]/td[@class="gdt2"]').text)


class GalleryPage:
    def __init__(self, gallery_id, page_token, page, base_url='http://e-hentai.org', reload_info=''):
        self.gallery_id = gallery_id
        self.token = page_token
        self.page = page
        self.base_url = base_url
        self.reload_info = reload_info
        self.loaded = False
        self.raw_html = None
        self.parsed_document = None

    async def load(self, session):
        url = self.get_url()
        self.raw_html = html = await fetch_text_ensure(session, url)
        self.parsed_document = doc = parse_html(html)

        self.img_url = doc.find('.//img[@id="img"]').attrib['src']
        
        prev_url = doc.find('.//a[@id="prev"]').attrib['onclick']
        prev_page = int(get_between(prev_url, '(', ','))
        prev_token = get_between(prev_url, ',', ')')[1:-1]
        self.prev = GalleryPage(self.gallery_id, prev_token, prev_page, self.base_url)

        next_url = doc.find('.//a[@id="next"]').attrib['onclick']
        next_page = int(get_between(next_url, '(', ','))
        next_token = get_between(next_url, ',', ')')[1:-1]
        self.next = GalleryPage(self.gallery_id, next_token, next_page, self.base_url)

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

    def get_url(self):
        url = '{}/s/{}/{}-{}'.format(
            self.base_url,
            self.token,
            self.gallery_id,
            self.page)
        if self.reload_info:
            url += self.reload_info
        return url

    @property
    def load_counter(self):
        return len(self.reload_info.split('&'))

    @staticmethod
    def parse_url(url):
        url = urllib.parse.urlparse(url)
        if url.query:
            query = urllib.parse.parse_qs(url.query)
            reload_info = query.get('reload_info', '')
        else:
            reload_info = ''
        part = url.path.split('/')
        assert(part[1] == 's')
        gallery_id, page = part[3].split('-')
        gallery_id = int(gallery_id)
        page = int(page)
        page_token = part[2]
        base_url = url.scheme + '://' + url.netloc
        return {'base_url': base_url, 'gallery_id': gallery_id, 'token': page_token, 'page': page, 'reload_info': reload_info}

    @staticmethod
    def from_url(url):
        result = GalleryPage.parse_url(url)
        return GalleryPage(result['gallery_id'], result['token'], result['page'], result['base_url'], result['reload_info'])
