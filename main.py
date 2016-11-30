import download
import asyncio
import aiohttp
import ehentai
import os
import argparse
import getpass


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('--cookie-storage', type=str, default='./cookies.txt', dest='cookie_file_path',
                        help='path of the text file that stores cookies')
    parser.add_argument('--proxy', type=str, dest='proxy',
                        help='http proxy to use')

    subparsers = parser.add_subparsers(title='command', dest='command_name')
    parser_login = subparsers.add_parser('login', help='login and save cookies')
    parser_login.add_argument('--username', type=str, dest='username', default=None)
    parser_login.add_argument('--password', type=str, dest='password', default=None)
    parser_login.set_defaults(func=do_login)
    parser_download = subparsers.add_parser('download', help='download images from a gallery')
    parser_download.add_argument('gallery_url', metavar='gallery-url', type=str,
                                 help='url of the gallery that you want to download')
    parser_download.add_argument('--download-timeout', type=float, dest='download_timeout', default=5.0,
                                 help='timeout of download connections')
    parser_download.set_defaults(func=do_download)

    args = parser.parse_args(args)
    if not args.command_name:
        parser.print_help()
        exit(1)

    # load cookies
    cookiejar = prepare_cookies(args)
    args.cookiejar = cookiejar

    args.func(args)

    # save cookies
    open(args.cookie_file_path, 'w').write(repr(cookiejar))


def prepare_cookies(args):
    path = args.cookie_file_path
    if os.path.exists(path):
        cookies = open(path).read()
        cookiejar = ehentai.GreatCookieJar.from_string(cookies)
    else:
        cookiejar = ehentai.GreatCookieJar()
        open(path, 'w').write('GreatCookieJar()')
    return cookiejar


def do_login(args):
    if args.username is None:
        username = input('Username for e-hentai: ')
    if args.password is None:
        password = getpass.getpass()
    cookies, error = ehentai.login(username, password)
    args.cookiejar.update(cookies)
    if error:
        print(error)
    else:
        print('Logged in successfully.')


def do_download(args):
    loop = asyncio.get_event_loop()
    # loop.set_debug(True)

    if args.proxy:
        connector = aiohttp.ProxyConnector(args.proxy)
    else:
        connector = None
    with aiohttp.ClientSession(loop=loop, connector=connector, cookies=args.cookiejar.get_dict()) as session:
        loop.run_until_complete(download.download(session, args.gallery_url, download_timeout=args.download_timeout))

    #args.cookiejar.update(session.cookie_jar._cookies)


if __name__ == '__main__':
    from sys import argv
    main(argv[1:])
