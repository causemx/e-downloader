import download
import asyncio
import aiohttp
import ehentai
import os
import json
import argparse


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('--cookie_file', type=str, default='./cookie.txt', dest='cookie_file_path',
                        help='location of the file to store cookies')
    parser.add_argument('--cookie_str', type=str, dest='cookie_str',
                        help='document.cookie string from the browser')
    parser.add_argument('--proxy', type=str, dest='proxy',
                        help='http proxy through which data is downloaded')
    parser.add_argument('gallery_url', type=str,
                        help='url of the gallery to download')
    args = parser.parse_args(args)

    # load cookies
    cookiejar = prepare_cookies(args)

    loop = asyncio.get_event_loop()
    #loop.set_debug(True)

    if args.proxy:
        connector = aiohttp.ProxyConnector(args.proxy)
    else:
        connector = None
    with aiohttp.ClientSession(loop=loop, connector=connector, cookies=cookiejar.get_dict()) as session:
        loop.run_until_complete(download.download(session, args.gallery_url))

    # save cookies
    cookiejar.update(session.cookie_jar._cookies)
    open(args.cookie_file_path, 'w').write(repr(cookiejar))


def prepare_cookies(args):
    path = args.cookie_file_path
    if os.path.exists(path):
        cookies = open(path).read()
        cookiejar = ehentai.GreatCookieJar.from_string(cookies)
    else:
        cookiejar = ehentai.GreatCookieJar()
        if args.cookie_str:
            cookies = args.cookie_str
        else:
            cookies = input('document.cookie: ')
        if cookies.startswith('\"') and cookies.endswith('\"'):
            cookies = json.loads(cookies)
        cookies = ehentai.convert_cookies(cookies)
        cookiejar.update(cookies)
        open(args.cookie_file_path, 'w').write(repr(cookiejar))
    return cookiejar


if __name__ == '__main__':
    from sys import argv
    main(argv[1:])
