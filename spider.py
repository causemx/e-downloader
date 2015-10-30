from collections import namedtuple
from time import sleep, time
import traceback
import logging
logger = logging.getLogger('e-spider.spider')
import math

import requests
from requests.cookies import RequestsCookieJar
from pyquery import PyQuery

# for type hint ...
from io import FileIO
import lxml
HtmlElement = lxml.html.HtmlElement

class GreatCookieJar(RequestsCookieJar):
    '''Used to save cookies to a file; FileCookieJar is too high-end.'''
    def store(self, f: FileIO) -> None:
        for cookie in self:
            f.write(repr(cookie))
            f.write('\n')

    def restore(self, f: FileIO) -> None:
        from http.cookiejar import Cookie
        for line in f.readlines():
            self.set_cookie(eval(line))


# namedtuple is a metaclass, see module collections.
# information of a gallery page
PageInfo = namedtuple('PageInfo', ['img_name', 'img_url', 'origin_img', 'reload_url'])
# information of a gallery
GalleryInfo = namedtuple('GalleryInfo',
                         ['gid',
                          'token',
                          'name_en',
                          'name_jp',
                          'category',
                          'uploader',
                          'infos',
                          'rating',
                          'rating_count',
                          'translated',
                          'resized',
                          'tags'])


class Requester(object):
    '''A class that makes HTTP requests'''
    def __init__(self, timeout=10, proxies=None, cookies=None, headers=None) -> None:
        self.timeout = timeout
        self.proxies = proxies
        self.cookies = cookies if not cookies is None else GreatCookieJar()
        self.headers = headers

    def get(self, url: str, **kwargs) -> requests.Response:
        response = requests.get(url,
                                timeout=self.timeout,
                                proxies=self.proxies,
                                cookies=self.cookies,
                                headers=self.headers,
                                **kwargs)
        self.cookies.update(response.cookies)
        return response

    def post(self, url: str, **kwargs) -> requests.Response:
        response = requests.post(url,
                                 timeout=self.timeout,
                                 proxies=self.proxies,
                                 cookies=self.cookies,
                                 headers=self.headers,
                                 **kwargs)
        self.cookies.update(response.cookies)
        return response


class Spider(Requester):
    '''Requester for e-hentai.org.'''
    def login(self, username: str, password: str) -> bool:
        '''Login to get the cookies we need to access exhentai.org.'''
        base_url = 'https://forums.e-hentai.org/index.php'
        params = {'act': 'Login', 'CODE': '01'}
        data = {'CookieDate' : 1,
                'b' : 'd',
                'bt' : '',
                'UserName' : username,
                'PassWord' : password,
                'ipb_login_submit' : 'Login!'}
        response = self.post(base_url, params=params, data=data)
        html = response.text
        open('error.html', 'w').write(html)
        self.logged_in = 'You are now logged in as:' in html
        return self.logged_in

    def check_login(self) -> bool:
        if hasattr(self, 'logged_in'):
            return self.logged_in
        html = self.get_query('http://forums.e-hentai.org/').html()
        self.logged_in = 'Welcome guest' not in html
        return self.logged_in

    def get_query(self, url: str, **kwargs) -> PyQuery:
        '''Get the page and try to parse it.'''
        while True:
            sleep(0.25)
            try:
                response = self.get(url, **kwargs)
                html = response.text
                if html.startswith('Your IP address'):
                    logger.error('IP address baned.')
                    continue
                break
            except requests.RequestException:
                logger.debug(traceback.format_exc())
                continue
        query = PyQuery(html)
        return query

class GallerySpider(Spider):
    '''Get information from e-hentai gallery.'''
    def get_gallery_info(self, gallery_url: str) -> GalleryInfo:
        '''Get the GalleryInfo object from by given url.'''
        # gallery url: http://g.e-hentai.org/g/gid/token/[?p=xxx]
        gallery_url = gallery_url.split('?')[0]
        gid = gallery_url.split('/')[-3]
        token = gallery_url.split('/')[-2]

        query = self.get_query(gallery_url)
        html = query.outer_html()

        if 'This gallery has been removed, and is unavailable.' in html:
            return None
        if 'Content Warning' in html:
            return None

        name_en = query('h1#gn')[0].text
        name_jp = query('h1#gj')
        name_jp = name_jp[0].text if name_jp else name_en
        if name_jp is None:
            name_jp = name_en

        category = query('img.ic')[0].attrib['src'].split('/')[-1]
        uploader = query('#gdn > a:nth-child(1)')[0].text
        infos = None # not supported yet
        translated = 'This gallery has been translated from the original language text.' in html
        resized = 'This gallery has been resized for online viewing.' in html

        rating = query('#rating_label')[0].text
        rating = rating.split(': ')[-1]
        rating = float(rating)
        rating_count = query('#rating_count')[0].text
        rating_count = int(rating_count)

        tags = None # not supported yet

        return GalleryInfo(gid=gid,
                           token=token,
                           name_en=name_en,
                           name_jp=name_jp,
                           category=category,
                           uploader=uploader,
                           infos=infos,
                           translated=translated,
                           resized=resized,
                           rating=rating,
                           rating_count=rating_count,
                           tags=tags)

    def fetch_page_urls(self, gallery_url: str, page: int) -> list:
        '''Get the list of page urls in given page of thumbnails.'''
        # process the url
        gallery_url = gallery_url.split('?')[0]
        if not gallery_url.endswith('/'):
            gallery_url += '/'    
        url = gallery_url + '?p=' +str(page)
        query = self.get_query(url)
        logger.debug('Gallery thumbnail page get: ' + url)

        gpc = query('.gpc')[0].text.split(' ')
        range_start = int(gpc[1])
        range_end = int(gpc[3])
        all_pages = int(gpc[5])
        if (range_end - range_start + 1) * (page + 1) > all_pages:
            return []

        page_urls = query('div.gdtm > div:nth-child(1) > a:nth-child(1)')
        page_urls = [page_url.attrib['href'] for page_url in page_urls]
        return page_urls

    def get_page_urls(self, gallery_url: str) -> list:
        '''Get the list of page urls of the given gallery.'''
        page = 0
        while True:
            page_urls = self.fetch_page_urls(gallery_url, page)
            if page_urls:
                for page_url in page_urls:
                    yield page_url
            else:
                break
            page += 1

    def get_page_info(self, page_url: str) -> PageInfo:
        '''Get the PageInfo object by the given url.'''
        # page url: http://g.e-hentai.org/s/imgkey/gid-page/[?nl=xxx[&nl=xxx[...]]]
        query = self.get_query(page_url)
        
        img_url = query('img#img')[0].attrib['src']

        i4 = query('#i4 > div:nth-child(1)')[0]
        img_name, img_size, img_len = i4.text.split(' :: ')

        reload_url = query('a[href="#"]')[0].attrib['onclick']
        reload_url = reload_url.split("('")[-1].split("')")[0]
        if '?' in page_url:
            reload_url = page_url + '&nl=' + reload_url
        else:
            reload_url = page_url + '?nl=' + reload_url

        try:
            origin_url = query('#i7 > a:nth-child(2)')[0].attrib['href']
        except IndexError:
            origin_url = None

        return PageInfo(img_name=img_name,
                        img_url=img_url,
                        origin_img=origin_url,
                        reload_url=reload_url)


class Searcher(Spider):
    '''Search galleries in e-hentai gallery.'''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.keyword = ''
        self.doujinshi = True
        self.manga = True
        self.artistcg = True
        self.gamecg = True
        self.western = True
        self.non_h = True
        self.imageset = True
        self.cosplay = True
        self.asianporn = True
        self.misc = True
        self.advanced_search = False
        self.search_name = True
        self.search_tags = True
        self.min_rating = None

    def make_params(self, page: int) -> None:
        params = {'f_doujinshi': self.doujinshi,
                  'f_manga': self.manga,
                  'f_artistcg': self.artistcg,
                  'f_gamecg': self.gamecg,
                  'f_western': self.western,
                  'f_non-h': self.non_h,
                  'f_imageset': self.imageset,
                  'f_cosplay': self.cosplay,
                  'f_asianporn': self.asianporn,
                  'f_misc': self.misc}
        params = {key: '1' if value else '0' for key,value in params.items()}
        params['f_search'] = self.keyword
        params['f_apply'] = 'Apply Filter'
        params['page'] = str(page)
        if self.advanced_search:
            params['advsearch'] = '1'
            params['f_sname'] = 'on' if self.search_name else 'off'
            params['f_stags'] = 'on' if self.search_tags else 'off'
            if self.min_rating:
                params['f_sr'] = 'on'
                params['f_srdd'] = str(self.min_rating)
        return params

    def fetch_results(self, page: int) -> list:
        params = self.make_params(page)
        if self.check_login():
            base_url = 'http://exhentai.org/'
        else:
            base_url = 'http://g.e-hentai.org/'
        query = self.get_query(base_url, params=params)

        process_number = lambda s: int(s.replace(',', ''))
        ip = query('p.ip')[0]
        ip = ip.text.split(' ')
        range_start = process_number(ip[1].split('-')[0])
        range_end = process_number(ip[1].split('-')[1])
        range_all = process_number(ip[-1])
        range_length = range_end - range_start + 1
        page_count = math.ceil(range_all / range_length)
        if range_end == range_all:
            return []

        results = query('tr[class^="gtr"] > td:nth-child(3) > div:nth-child(1) > div:nth-child(3) > a:nth-child(1)')
        results = [result.attrib['href'] for result in results]
        return results

    def __iter__(self):
        page = 0
        while True:
            results = self.fetch_results(page)
            page += 1
            if not results:
                break
            for result in results:
                yield result

