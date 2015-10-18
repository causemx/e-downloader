from collections import namedtuple
from time import sleep, time
import traceback
import logging
logger = logging.getLogger('e-spider.gallery')

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
        self.cookies = cookies if cookies is not None else GreatCookieJar()
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
    '''Get infomation from e-hentai gallery.'''
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
        return 'You are now logged in as:' in html

    def check_login(self) -> bool:
        html = self.get('http://forums.e-hentai.org/').text
        return 'Welcome guest' not in html

    def get_query(self, url: str) -> PyQuery:
        while True:
            sleep(0.25)
            try:
                response = self.get(url)
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
        try:
            name_jp = query('h1#gj')[0].text
        except IndexError:
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

    def get_page_urls(self, gallery_url: str) -> list:
        '''Get the list of page urls of the given gallery.'''
        # process the URL
        if '?' in gallery_url:
            gallery_url = gallery_url.split('?')[0]
        if not gallery_url.endswith('/'):
            gallery_url += '/'
        pages = []
        p = 0
        while True:
            url = gallery_url + '?p=' + str(p)
            query=self.get_query(url)
            
            gpc = query('.gpc')[0].text.split(' ')
            current_page = gpc[3]
            all_pages = gpc[5]
            logger.debug('Gallery page get: ' + url)

            for page_link in query('div.gdtm > div:nth-child(1) > a:nth-child(1)'):
                pages.append(page_link.attrib['href'])

            if current_page == all_pages:
                break
            p += 1
        return pages

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

