#!/usr/bin/env python3

from http.cookiejar import Cookie, CookieJar
import urllib.request
import urllib.parse
from http.client import HTTPException
from xml.dom.minidom import parseString
from collections import namedtuple
from xml.parsers import expat
from time import sleep, time
from threading import Thread
import traceback
import logging

from downloader import Downloader

class GreatCookieJar(CookieJar):
    '''Used to save cookies to a file; FileCookieJar is too high-end.'''
    def store(self, f):
        for cookie in self:
            f.write(repr(cookie))
            f.write('\n')
        logging.debug('Cookie saved.')

    def restore(self, f):
        for line in f.readlines():
            self.set_cookie(eval(line))
        logging.debug('Cookie loaded.')

def findElements(root, tag_name: str, pattern: str):
    '''
    Find elements whose tag name is tag_name and pattern(element) is True.
    '''
    elements = root.getElementsByTagName(tag_name)
    return [element for element in elements if pattern(element)]

def del_between(s: str, start_text: str, end_text: str) -> str:
    '''
    Delete the substring starting with start_text and ending with end_text.
    '''
    if start_text not in s or end_text not in s:
        return s
    start = s.find(start_text)
    end = s.find(end_text) + len(end_text)
    return s[:start] + s[end:]

# Information of a gallery page.
PageInfo = namedtuple('PageInfo', ['imgname', 'imgurl', 'originimg', 'reloadurl'])
# Information of a gallery
GalleryInfo = namedtuple('GalleryInfo',
                         [
                             'gid',
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
                             'tags'
                         ])

class Spider(object):
    '''Get information from e-hentai.'''
    def __init__(self, opener=None, timeout=10.0):
        self.open = opener.open if opener else urllib.request.urlopen
        self.timeout=timeout

    def login(self, username: str, password: str) -> None:
        '''
        Login to get the cookie we need to access exhentai.org.
        Warning: HTTPS is not used.
        '''
        base_url = 'http://forums.e-hentai.org/index.php?act=Login&CODE=01'
        post_data = {'CookieDate' : 1,
                     'b' : 'd',
                     'bt' : '',
                     'UserName' : username,
                     'PassWord' : password,
                     'ipb_login_submit' : 'Login!'}
        post_data = urllib.parse.urlencode(post_data).encode()
        html = self.open(base_url, data=post_data , timeout=self.timeout).read().decode()
        if 'You are now logged in as:' in html:
            return None
        else:
            try:
                document = parseString(html)
                root = document.root
                span = findElements(root, 'span', lambda span: span.getAttribute('class') == 'postcolor')[0]
                reason = span.childNodes[0].data
            except:
                reason = 'Login failed.'
                logging.debug(traceback.format_exc())
            return reason

    def check_login(self):
        html = self.open('http://forums.e-hentai.org/', timeout=self.timeout).read().decode()
        if 'Welcome Guest' in html:
            return False
        else:
            return True

    def open_parse(self, url: str):
        '''return value: DOM'''
        while True:
            sleep(0.2)
            try:
                data = self.open(url, timeout=self.timeout).read()
                html = data.decode()
                if html.startswith('Your IP address'):
                    logging.debug('IP address baned.')
                    continue
                # We need to remove useless part of the html
                while '<iframe' in html:
                    html = del_between(html, '<iframe', '</iframe>')
                while '<script' in html:
                    html = del_between(html, '<script', '</script>')
                while '<form' in html:
                    html = del_between(html, '<form', '</form>')
                html = del_between(html, '<div id="cdiv" class="gm">', '</div><!-- /cdiv -->')
                document = parseString(html)
                return document
            except OSError:
                logging.debug(traceback.format_exc())
            except UnicodeDecodeError:
                logging.debug(traceback.format_exc())
            except HTTPException:
                logging.debug(traceback.format_exc())
            except expat.ExpatError:
                logging.debug(traceback.format_exc())

    def get_gallery_info(self, gallery_url: str) -> GalleryInfo:
        '''Get the GalleryInfo object from by given url.'''
        # gallery url: http://g.e-hentai.org/g/gid/token/[?p=xxx]
        gallery_url = gallery_url.split('?')[0]
        gid = gallery_url.split('/')[-3]
        token = gallery_url.split('/')[-2]

        document = self.open_parse(gallery_url)
        root = document.documentElement
        html = document.toxml()

        if 'This gallery has been removed, and is unavailable.' in html:
            return None
        if 'Content Warning' in html:
            return None

        name_en = findElements(root, 'h1', lambda h1: h1.getAttribute('id') == 'gn')[0]
        name_en = name_en.childNodes[0].data
        name_jp = findElements(root, 'h1', lambda h1: h1.getAttribute('id') == 'gj')[0]
        if name_jp.childNodes:
            name_jp = name_jp.childNodes[0].data
        else:
            name_jp = name_en

        category = findElements(root, 'img', lambda img: img.getAttribute('class') == 'ic')[0]
        category = category.getAttribute('src').split('/')[-1]

        uploader = findElements(root, 'div', lambda a: a.getAttribute('id') == 'gdn')[0]
        uploader = uploader.childNodes[0].childNodes[0].data

        gdt1s = findElements(root, 'td', lambda td: td.getAttribute('class') == 'gdt1')
        gdt1s = [gdt1.childNodes[0].data for gdt1 in gdt1s]
        gdt1s = [gdt1.lower().split(':')[0] for gdt1 in gdt1s]
        gdt2s = findElements(root, 'td', lambda td: td.getAttribute('class') == 'gdt2')
        gdt2s = [gdt2.childNodes[0] for gdt2 in gdt2s]
        infos = dict(zip(gdt1s, gdt2s))
        info_parent = infos['parent']
        if info_parent.childNodes:
            info_parent = info_parent.getAttribute('href')
        else:
            info_parent = info_parent.data
        infos['parent'] = info_parent
        infos['posted'] = infos['posted'].data
        infos['visible'] = infos['visible'].data == 'Yes'
        infos['language'] = infos['language'].data
        infos['size'] = infos['file size'].data
        del infos['file size']
        infos['length'] = int(infos['length'].data.split(' ')[0])
        infos['favorited'] = int(infos['favorited'].data.split(' ')[0])

        translated = 'This gallery has been translated from the original language text.' in html
        resized = 'This gallery has been resized for online viewing.' in html

        rating = findElements(root, 'td', lambda td: td.getAttribute('id') == 'rating_label')[0]
        rating = rating.childNodes[0].data.split(': ')[-1]
        rating = float(rating)
        rating_count = findElements(root, 'span', lambda span: span.getAttribute('id') == 'rating_count')[0]
        rating_count = rating_count.childNodes[0].data

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
                           tags=self.parse_tag(document))

    def parse_tag(self, dom) -> dict:
        root = dom.documentElement
        tag_map = {}
        tags = findElements(root, 'div', lambda div: div.getAttribute('class') == 'gt')
        for tag in tags:
            tag = tag.getAttribute('id')[3:]
            if ':' in tag:
                category, name = tag.split(':')
            else:
                category = 'misc'
                name = tag
            if category in tag_map:
                tag_map[category].append(name)
            else:
                tag_map[category] = [name]
        return tag_map

    def get_page_urls(self, gallery_url:str) -> list:
        '''Get the list of page urls of the given gallery.'''
        pages = []
        p = 0
        gallery_url += '/' if not gallery_url.endswith('/') else ''
        while True:
            url = gallery_url + '?p=' + str(p)
            document = self.open_parse(url)
            root = document.documentElement

            gpc = findElements(root, 'p', lambda p: p.getAttribute('class') == 'gpc')[0]
            gpc = gpc.childNodes[0].data.split(' ')
            current_page = gpc[3]
            all_pages = gpc[5]

            def f(a):
                href = a.getAttribute('href')
                s = href.split('/')
                if len(s) == 6:
                    return s[-3] == 's'
                else:
                    return False
            page_urls = findElements(root, 'a', f)
            page_urls = [a.getAttribute('href') for a in page_urls]
            pages += page_urls
            
            if current_page == all_pages:
                break
            p += 1
        return pages

    def get_page_info(self, page_url: str) -> PageInfo:
        '''Get the PageInfo object by the given url.'''
        # page url: http://g.e-hentai.org/s/imgkey/gid-page/[?nl=xxx[&nl=xxx[...]]]

        document = self.open_parse(page_url)
        root = document.documentElement
        
        img = findElements(root, 'img', lambda img: img.getAttribute('id') == 'img')[0]
        img_url = img.getAttribute('src')

        i4 = findElements(root, 'div', lambda div: div.getAttribute('id') == 'i4')[0]
        img_info = i4.childNodes[0].childNodes[0].data
        img_name, img_size, img_len = img_info.split(' :: ')

        i6 = findElements(root, 'div', lambda div: div.getAttribute('id') == 'i6')[0]
        reload_url = i6.getElementsByTagName('a')[-1].getAttribute('onclick')
        reload_url = reload_url.split("('")[-1].split("')")[0]
        if '?' in page_url:
            reload_url = page_url + '&nl=' + reload_url
        else:
            reload_url = page_url + '?nl=' + reload_url

        i7 = findElements(root, 'div', lambda div: div.getAttribute('id') == 'i7')[0]
        if i7.childNodes:
            origin_url = i7.getElementsByTagName('a')[-1].getAttribute('href')
        else:
            origin_url = None

        return PageInfo(imgname=img_name,
                        imgurl=img_url,
                        originimg=origin_url,
                        reloadurl=reload_url)

