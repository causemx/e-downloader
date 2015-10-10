#!/usr/bin/env python3

from spider import GreatCookieJar
from spider import Spider
from downloader import Downloader
from time import sleep
from sys import argv
import logging
import os

logger = logging.getLogger('e-spider.main')

def main(args):
    # See our GreatCookieJar and Spider.
    cj = GreatCookieJar()
    if os.path.exists('cookie.txt'):
        cj.restore(open('cookie.txt', 'r'))
        logger.info('Cookie loaded.')
    spider = Spider(timeout=4.0,
                    cookies=cj,
                    headers={'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:41.0) Gecko/20100101 Firefox/41.0'},
                    proxies=None)
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
        logger.info('Gallery: {0}'.format(gallery_info.name_jp))
        # Keep trying until all the pictures are downloaded.
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
            # Some pictures failed downloading, so we will try again using new URLs.
            page_urls = [page_info.reload_url for gallery_info, page_info in downloader.failures]
            # downloader.failures.clear()
            del downloader.failures[:]

        logger.debug('Waiting for DownloadThread ...')
        while not downloader.finished:
            sleep(0.1)
        downloader.stop()
        logger.info('Gallery downloaded: {0}'.format(gallery_info.name_jp))
    # Save cookies.
    cj.store(open('cookie.txt','w'))

if __name__ == '__main__':
    root_logger = logging.getLogger('e-spider')
    root_logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)-15s %(threadName)s %(message)s')
    ch.setFormatter(formatter)
    root_logger.addHandler(ch)
    main(argv[1:])
