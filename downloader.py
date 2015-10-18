import os
from time import sleep, time
from threading import Thread
from http.client import HTTPException
import logging
logger = logging.getLogger('e-spider.downloader')
import traceback
from io import BytesIO
from shutil import copyfileobj
import socket
import urllib
# for type hint
from gallery import GalleryInfo, PageInfo

class DownloadManager(Thread):
    '''A thread that automatically control number of running DownloadThread.'''
    def __init__(self, opener=None, timeout=10.0, max_thread=5) -> None:
        Thread.__init__(self)

        self.opener = opener
        self.timeout = timeout
        self.max_thread = max_thread
        self.tasks = []
        self.failures = []
        self.oks = []
        self.threads = []
        self.working = False

    def new_download(self, task: (GalleryInfo, PageInfo)) -> None:
        '''Add a new download task.'''
        self.tasks.append(task)

    def run(self) -> None:
        self.working = True
        while self.working:
            sleep(0.05)
            # Remove a dead thread.
            for i in range(len(self.threads)):
                thread = self.threads[i]
                if not thread.isAlive():
                    del self.threads[i]
                    if thread.ok:
                        self.oks.append((thread.gallery_info, thread.page_info))
                    else:
                        self.failures.append((thread.gallery_info, thread.page_info))
                    logger.debug('Thread exited: {0}'.format(thread.ident))
                    break
            # Create a new thread if possible
            if len(self.threads) < self.max_thread and self.tasks:
                task = self.tasks[0]
                del self.tasks[0]
                thread = DownloadThread(task, self.opener, self.timeout)
                thread.start()
                self.threads.append(thread)
                logger.debug('Starting new thread: {0}'.format(thread.ident))

    def resume(self) -> None:
        self.working = True

    def stop(self) -> None:
        self.working = False

    @property
    def finished(self) -> bool:
        '''Will be True if all the downloads are completed'''
        return len(self.tasks) == 0 and len(self.threads) == 0

class DownloadThread(Thread):
    '''A thread that downloads a single image.'''
    translate_map = str.maketrans('/', '／')

    def __init__(self, task: (GalleryInfo, PageInfo), opener=None, timeout=10.0) -> None:
        Thread.__init__(self)

        self.gallery_info, self.page_info = task
        self.open = opener.open if opener else urllib.request.urlopen
        self.timeout = timeout
        self.begin = time()
        self.ok = None
        self.working = False
        self.bytesread = 0
        self.length = -1

    def run(self) -> None:
        self.working = True

        # make a directory named as the Japanese name of the gallery
        dir_path = self.gallery_info.name_jp
        dir_path = dir_path.translate(self.translate_map)
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)
        file_path = dir_path + os.sep + self.page_info.img_name
        if os.path.exists(file_path):
            logger.info('Skip: {0}'.format(self.page_info.img_name))
            self.ok = True
            return
        # start downloading
        self.ok = False
        logger.info('Start: {0}'.format(self.page_info.img_name))
        buf = BytesIO()
        try:
            response = self.open(self.page_info.img_url, timeout=self.timeout)
            self.length = response.getheader('Content-Length','-1')
            self.length = int(self.length)
            while self.working:
                # read data and update information
                data = response.read(512)
                if not data:
                    self.ok = True
                    break
                buf.write(data)
                self.bytesread += len(data)
        except OSError:
            logger.debug(traceback.format_exc())
        except HTTPException:
            logger.debug(traceback.format_exc())
        except socket.timeout:
            logger.debug(traceback.format_exc())
        if not self.ok:
            logger.info('Failed: {0}'.format(self.page_info.img_name))
            return
        # save the image
        buf.seek(0)
        copyfileobj(buf, open(file_path, 'wb'))
        logger.info('Finish: {0}'.format(self.page_info.img_name))

    def resume(self) -> None:
        self.working = True

    def stop(self) -> None:
        self.working = False

    @property
    def second_lapsed(self) -> float:
        return time() - self.begin

