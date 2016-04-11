import asyncio
import aiohttp
import ehentai
import gallery
import os
import copy
import json


def main():
    cookie_file_path = './cookie.txt'
    # load cookies
    if os.path.exists(cookie_file_path):
        cookies = open(cookie_file_path).read()
        cookiejar = ehentai.GreatCookieJar.from_string(cookies)
    else:
        cookiejar = ehentai.GreatCookieJar()
        cookies = input('document.cookie: ')
        if cookies.startswith('\"') and cookies.endswith('\"'):
            cookies = json.loads(cookies)
        cookies = ehentai.convert_cookies(cookies)
        cookiejar.update(cookies)
        open(cookie_file_path, 'w').write(repr(cookiejar))

    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    conn = aiohttp.TCPConnector(limit=20)
    with aiohttp.ClientSession(loop=loop, connector=conn, cookies=cookiejar.get_dict()) as session:
        loop.run_until_complete(gallery.fetch_gallery(session, 'http://exhentai.org/g/901496/9503a75fe5/', gallery.download))

    # save cookies
    cookiejar.update(session.cookies)
    open(cookie_file_path, 'w').write(repr(cookiejar))

if __name__ == '__main__':
    main()

