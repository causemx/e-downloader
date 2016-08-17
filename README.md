# e-downloader
An E-Hentai image downloader in python.

Supports both ```g.e-hentai.org``` and ```exhentai.org```.
If you want to download something from ```exhentai.org```,cookie from your browser is needed because ```exhentai.org``` can only be accessed by some specific users.

To get your cookie:

0. turn to ```g.e-hentai.org``` (or ```exhentai.org```)
0. press ```F12``` and find the console
0. enter ```document.cookie``` and press ```Enter```
0. the cookie will appear under what you had entered

```e-downloader``` is now a command-line tool.
```download.py``` is the file that shoud to be executed.
Type ```python3 download.py --help``` for detail.

## Dependency:
* python3.5+
* requests
* html5lib
* asyncio
