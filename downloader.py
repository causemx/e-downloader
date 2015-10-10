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


class Downloader(Thread):
    '''Commander.'''
    def __init__(self, opener=None, timeout=10.0, max_thread=5):
        Thread.__init__(self)

        self.opener = opener
        self.timeout = timeout
        self.max_thread = max_thread
        self.tasks = []
        self.failures = []# failed tasks
        self.threads = []
        self.working = False

    def new_download(self, task):
        '''Add a new download'''
        self.tasks.append(task)

    def run(self):
        self.working = True
        while self.working:
            sleep(0.05)
            # Remove a dead thread.
            for i in range(len(self.threads)):
                thread = self.threads[i]
                if not thread.isAlive():
                    del self.threads[i]
                    if not thread.ok:
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

    def stop(self):
        self.working = False

    @property
    def finished(self):
        '''Will be True if all the downloads are completed'''
        return len(self.tasks) == 0 and len(self.threads) == 0

class DownloadThread(Thread):
    '''Worker.'''
    translate_map = str.maketrans('/', '／')

    def __init__(self, task, opener=None, timeout=10.0):
        Thread.__init__(self)

        self.gallery_info, self.page_info = task
        self.open = opener.open if opener else urllib.request.urlopen
        self.timeout = timeout
        self.begin = time()
        self.ok = None
        self.working = False
        self.bytesread = 0
        self.length = -1

    def run(self):
        self.working = True

        # Make a directory named as the Japanese name of the gallery.
        dir_path = self.gallery_info.name_jp
        dir_path = dir_path.translate(self.translate_map)
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)
        file_path = dir_path + os.sep + self.page_info.img_name
        if os.path.exists(file_path):
            logger.info('Skip: {0}'.format(self.page_info.img_name))
            self.ok = True
            return
        
        self.ok = False
        logger.info('Start: {0}'.format(self.page_info.img_name))
        buf = BytesIO()
        try:
            response = self.open(self.page_info.img_url, timeout=self.timeout)
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
            logger.debug(traceback.format_exc())
        except HTTPException:
            logger.debug(traceback.format_exc())
        except socket.timeout:
            logger.debug(traceback.format_exc())
        if not self.ok:
            logger.info('Failed: {0}'.format(self.page_info.img_name))
            return
        # Save the file to the disk.
        buf.seek(0)
        copyfileobj(buf, open(file_path, 'wb'))
        logger.info('Finish: {0}'.format(self.page_info.img_name))

    def stop(self):
        self.working = False

    @property
    def second_lapsed(self):
        return time() - self.begin
