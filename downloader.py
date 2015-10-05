import os
from time import sleep, time
from threading import Thread
from http.client import HTTPException
import logging
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

    def new_download(self, gallery_info, page_info):
        '''Add a new download'''
        self.tasks.append((gallery_info, page_info))

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
                    logging.debug('Thread exited: {0}'.format(thread.ident))
                    break
            # Create a new thread if possible
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
        '''Will be True if all the downloads are completed'''
        return len(self.tasks) == 0 and len(self.threads) == 0

class DownloadThread(Thread):
    '''Worker.'''
    translate_map = str.maketrans('/', '／')

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

        # Make a directory named as the Japanese name of the gallery.
        dir_path = self.gallery_info.name_jp
        dir_path = dir_path.translate(self.translate_map)
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
        # Save the file to the disk.
        buf.seek(0)
        copyfileobj(buf, open(file_path, 'wb'))
        logging.info('Finish: {0}'.format(self.page_info.imgname))

    def stop(self):
        self.working = False

    @property
    def second_lapsed(self):
        return time() - self.begin