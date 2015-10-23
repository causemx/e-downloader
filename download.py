#!/usr/bin/env python3

from spider import GreatCookieJar, GallerySpider
from downloader import DownloadManager
from time import sleep
from sys import argv
import logging
import os
import copy

logger = logging.getLogger('e-spider.main')

def main(args):
    # see our GreatCookieJar and Spider
    cj = GreatCookieJar()
    if os.path.exists('cookie.txt'):
        cj.restore(open('cookie.txt', 'r'))
        logger.info('Cookie loaded.')
    spider = GallerySpider(timeout=4.0,
                    cookies=cj,
                    headers={'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:41.0) Gecko/20100101 Firefox/41.0'},
                    proxies=None)
    # ask user to enter arguments if it is not given by command line
    if not args:
        print_usage()
        return
    if args[0] == 'login':
        if len(args) != 3:
            print_usage()
            return
        print('Logging in ... ', end='', flush=True)
        result = spider.login(args[1], args[2])
        # copy cookies from .e-hentai.org to .exhentai.org
        for cookie in cj:
            if cookie.domain == '.e-hentai.org':
                cookie = copy.copy(cookie)
                cookie.domain = '.exhentai.org'
                cj.set_cookie(cookie)
        cj.store(open('cookie.txt', 'w'))
        print('done.' if result else 'failed.')
        return
    else:
        gallery_urls = args[:]
    # now we are good to deal with given URLs
    for gallery_url in gallery_urls:
        # get GalleryInfo object and URLs needed for getting PageInfo objects
        gallery_info =spider.get_gallery_info(gallery_url)
        logger.info('Get gallery: {0}'.format(gallery_info.name_jp))
        page_urls = spider.get_page_urls(gallery_url)
        downloader = DownloadManager(timeout=5.0, max_thread=10)
        downloader.start()
        logger.info('Start gallery: {0}'.format(gallery_info.name_jp))
        # keep trying until all the pictures are downloaded
        while page_urls:
            for page_url in page_urls:
                page_info = spider.get_page_info(page_url)
                if page_info.img_url == 'http://ehgt.org/g/509.gif':
                    logger.error('You have temporarily reached the limit for how many images you can browse.')
                    continue
                logger.debug('Get picture: {0}'.format(page_info.img_name))
                downloader.new_download((gallery_info, page_info))
            logger.debug('Waiting for DownloadThread ...')
            while not downloader.finished:
                 sleep(0.1)
            if not downloader.failures:
                break
            # some pictures failed downloading, so we will try again using new URLs
            page_urls = [page_info.reload_url for gallery_info, page_info in downloader.failures]
            downloader.failures.clear()

        logger.debug('Waiting for DownloadThread ...')
        while not downloader.finished:
            sleep(0.1)
        downloader.stop()
        logger.info('Gallery downloaded: {0}'.format(gallery_info.name_jp))

    # save cookies
    cj.store(open('cookie.txt','w'))
    logger.info('Cookie saved.')

def print_usage():
    pass

if __name__ == '__main__':
    # setup logger
    module_logger = logging.getLogger('e-spider')
    module_logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)-15s %(threadName)s %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    module_logger.addHandler(ch)

    main(argv[1:])

