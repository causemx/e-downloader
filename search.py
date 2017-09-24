import math
from ehentai import fetch_text_ensure
from ehentai import parse_html


class Searcher:
    def __init__(self, session, base_url='https://e-hentai.org'):
        self.session = session
        self.base_url = base_url

        self.keyword = ''
        self.doujinshi = True
        self.manga = True
        self.artistcg = True
        self.gamecg = True
        self.western = True
        self.non_h = True
        self.imageset = True
        self.cosplay = True
        self.asianporn = True
        self.misc = True
        self.advanced_search = False
        self.search_name = True
        self.search_tags = True
        self.min_rating = None

    def _make_params(self, page=None):
        if not page:
            page = 0

        params = {'f_doujinshi': self.doujinshi,
                  'f_manga': self.manga,
                  'f_artistcg': self.artistcg,
                  'f_gamecg': self.gamecg,
                  'f_western': self.western,
                  'f_non-h': self.non_h,
                  'f_imageset': self.imageset,
                  'f_cosplay': self.cosplay,
                  'f_asianporn': self.asianporn,
                  'f_misc': self.misc}
        params = {key: '1' if value else '0' for key, value in params.items()}
        params['f_search'] = self.keyword
        params['f_apply'] = 'Apply Filter'
        if page != 0:
            params['page'] = str(page)
        if self.advanced_search:
            params['advsearch'] = '1'
            params['f_sname'] = 'on' if self.search_name else 'off'
            params['f_stags'] = 'on' if self.search_tags else 'off'
            if self.min_rating:
                params['f_sr'] = 'on'
                params['f_srdd'] = str(self.min_rating)
        return params

    async def fetch_results(self, page: int) -> list:
        params = self._make_params(page)
        html = await fetch_text_ensure(self.session, self.base_url + '/', params=params)
        doc = parse_html(html)
        results = [a.get('href') for a in doc.findall('.//a')]
        results = [url for url in results if url.startswith(self.base_url + '/g/')]
        return results

    async def __aiter__(self):
        return SearchCursor(self)


class SearchCursor:
    def __init__(self, searcher):
        self.searcher = searcher
        self.page = 0
        self.result_buffer = None

    async def __anext__(self):
        if self.result_buffer:
            result = self.result_buffer[0]
            del self.result_buffer[0]
            return result
        else:
            self.result_buffer = await self.searcher.fetch_results(self.page)
            self.page += 1
            if not self.result_buffer:
                raise StopAsyncIteration()
            return await self.__anext__()
