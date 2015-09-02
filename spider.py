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
import os
from io import BytesIO
from shutil import copyfileobj
import traceback
import logging

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

def findElements(root, tag_name, pattern):
    elements = root.getElementsByTagName(tag_name)
    return [element for element in elements if pattern(element)]

def del_between(s, start_text, end_text):
    if start_text not in s or end_text not in s:
        return s
    start = s.find(start_text)
    end = s.find(end_text) + len(end_text)
    return s[:start] + s[end:]

class Spider(object):
    '''https://en.wikipedia.org/wiki/Spider'''
    def __init__(self, opener=None, timeout=10.0):
        self.open = opener.open if opener else urllib.request.urlopen
        self.timeout=timeout

    def login(self, username, password):
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

    def open_parse(self, url):
        '''return value: DOM'''
        while True:
            sleep(0.2)
            try:
                data = self.open(url, timeout=self.timeout).read()
                html = data.decode()
                if html.startswith('Your IP address'):
                    logging.debug('IP address baned.')
                    continue
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

    def get_gallery_info(self, gallery_url):
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

    def parse_tag(self, dom):
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



    def get_page_urls(self, gallery_url):
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

    def get_page_info(self, page_url):
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

class Downloader(Thread):
    '''Commander.'''
    def __init__(self, opener=None, timeout=10.0, max_thread=5):
        Thread.__init__(self)

        self.opener = opener
        self.timeout = timeout
        self.max_thread = max_thread
        self.tasks = []
        self.failures = []
        self.threads = []
        self.working = False

    def new_download(self, gallery_info, page_info):
        self.tasks.append((gallery_info, page_info))

    def run(self):
        self.working = True
        while self.working:
            sleep(0.05)
            for i in range(len(self.threads)):
                thread = self.threads[i]
                if not thread.isAlive():
                    del self.threads[i]
                    if not thread.ok:
                        self.failures.append((thread.gallery_info, thread.page_info))
                    logging.debug('Thread exited: {0}'.format(thread.ident))
                    break
            if len(self.threads) < self.max_thread and self.tasks:
                gallery_info, page_info = self.tasks[0]
                del self.tasks[0]
                thread = DownloadThread(gallery_info, page_info, self.opener, self.timeout)
                thread.start()
                self.threads.append(thread)
                logging.debug('Starting new thread: {0}'.format(thread.ident))

    def stop(self):
        self.working = False

    @property
    def finished(self):
        return len(self.tasks) == 0 and len(self.threads) == 0

class DownloadThread(Thread):
    '''Worker.'''
    def __init__(self, gallery_info, page_info, opener=None, timeout=10.0):
        Thread.__init__(self)

        self.gallery_info = gallery_info
        self.page_info = page_info
        self.open = opener.open if opener else urllib.request.urlopen
        self.timeout = timeout
        self.begin = time()
        self.ok = None
        self.working = False
        self.bytesread = 0
        self.length = -1

    def run(self):
        self.working = True

        dir_path = self.gallery_info.name_jp
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)
        file_path = dir_path + os.sep + self.page_info.imgname
        if os.path.exists(file_path):
            logging.info('Skip: {0}'.format(self.page_info.imgname))
            self.ok = True
            return
        
        self.ok = False
        logging.info('Start: {0}'.format(self.page_info.imgname))
        buf = BytesIO()
        try:
            response = self.open(self.page_info.imgurl, timeout=self.timeout)
            self.length = response.getheader('Content-Length','-1')
            self.length = int(self.length)
            while self.working:
                data = response.read(512)
                if not data:
                    self.ok = True
                    break
                buf.write(data)
                self.bytesread += len(data)
        except OSError:
            logging.debug(traceback.format_exc())
        except HTTPException:
            logging.debug(traceback.format_exc())
        except socket.timeout:
            logging.debug(traceback.format_exc())
        if not self.ok:
            logging.info('Failed: {0}'.format(self.page_info.imgname))
            return
        buf.seek(0)
        copyfileobj(buf, open(file_path, 'wb'))
        logging.info('Finish: {0}'.format(self.page_info.imgname))

    def stop(self):
        self.working = False

    @property
    def second_lapsed(self):
        return time() - self.begin

PageInfo = namedtuple('PageInfo', ['imgname', 'imgurl', 'originimg', 'reloadurl'])
GalleryInfo = namedtuple('GalleryInfo', ['gid', 'token', 'name_en', 'name_jp', 'category', 'uploader', 'infos', 'rating', 'rating_count', 'translated', 'resized', 'tags'])

def main(args):
    # See our GreatCookieJar and Spider.
    cj = GreatCookieJar()
    if os.path.exists('cookie.txt'):
        cj.restore(open('cookie.txt', 'r'))
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    spider = Spider(opener, timeout=4.0)
    # Ask user to enter arguments if it is not given by command line.
    if not args:
        args = input('Arguments: ').split(' ')
    
    if args[0] == 'login':
        print('Logging in ... ', end='', flush=True)
        result = spider.login(args[1], args[2])
        cj.store(open('cookie.txt', 'w'))
        if not result:
            print('done.')
        else:
            print('failed.')
            print(result)
        if len(args) > 3:
            gallery_urls = args[3:]
        else:
            gallery_urls = []
    else:
        gallery_urls = args[:]
    # Now we are good to deal with given URLs.
    for gallery_url in gallery_urls:
        # Get GalleryInfo object and URLs needed for getting PageInfo objects.
        page_urls = spider.get_page_urls(gallery_url)
        gallery_info =spider.get_gallery_info(gallery_url)
        downloader = Downloader(timeout=5.0, max_thread=10)
        downloader.start()
        logging.info('Gallery: {0}'.format(gallery_info.name_jp))
        
        for _ in range(3):# We will keep trying for 3 times.
            for page_url in page_urls:
                page_info = spider.get_page_info(page_url)
                if page_info.imgurl == 'http://ehgt.org/g/509.gif':
                    logging.error('You have temporarily reached the limit for how many images you can browse.')
                    continue
                logging.debug('Get picture: {0}'.format(page_info.imgname))
                downloader.new_download(gallery_info, page_info)
            logging.debug('Waiting for DownloadThread ...')
            while not downloader.finished:
                 sleep(0.1)
            if not downloader.failures:
                break
            # Some pictures failed downloading, so we will try again using new URLs.
            page_urls = [page_info.reloadurl for gallery_info, page_info in downloader.failures]
            downloader.failures.clear()

        logging.debug('Waiting for DownloadThread ...')
        while not downloader.finished:
            sleep(0.1)
        downloader.stop()
        if downloader.failures:
            logging.warn('Downloading gallery failed: {0}'.format(gallery_info.name_jp))
        else:
            logging.warn('Gallery downloaded: {0}'.format(gallery_info.name_jp))

    cj.store(open('cookie.txt','w'))

if __name__ == '__main__':
    from sys import argv
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)-15s %(threadName)s %(message)s')
    main(argv[1:])
