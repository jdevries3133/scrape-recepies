from abc import ABC, abstractmethod
from io import BytesIO
import logging
import os
import shelve
from concurrent.futures import ThreadPoolExecutor, as_completed

import certifi
import pycurl

logging.basicConfig(
    filename='abc_crawlers.log',
    level='DEBUG',
    filemode='w',
    format='%(asctime)s %(levelname)-8s %(message)s'
)

class Crawler(ABC):
    def __init__(self, sitemap_url, context):
        """
        Things to put in context:
            Site name (string)
            Cache key
        """
        self.sitemap = sitemap_url
        self.context = context

        # there should be a separate cache created for every new child
        self.cache_dir = (
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'cache'
            )
        )

        # all instances will use the same database
        self.cache_path = os.path.join(
            self.cache_dir,
            'crawler_cache'
        )

        if self.context['read cache']:
            self.url_dict = self.read_cache_func()
        else:
            self.url_dict = {}

        if self.context['debug mode']:
            self.html_dir = os.path.join(self.cache_dir, 'html_pages')

    def write_cache_func(self):
        with shelve.open(self.cache_path) as db:
            db[self.context['cache key']] = self.url_dict

    def read_cache_func(self):
        with shelve.open(self.cache_path) as db:
            cached_url_dict = db[self.context['cache key']]
        return cached_url_dict

    def cache_recipe_page_responses(self):
        """
        Make a request to all the recipe pages, and save them in the
        database.

        Make a locally stored html page for each response, which we can
        use for development.

        '2014_3_week_4.html'

        dict = {
            'url groups': {
                'recipe pages': {
                    'parent url': [child urls],
                    'parent url2': [child urls2],
                }
                'other urls': {
                    'parent url': [other urls],
                    (etc)
                }
            }
        }
        """
        # dict data => [(url, (context))] --- that'll be var "input_list"
        tuples_for_func = []
        # context = {'supercat': 'super', 'subcat': 'sub'}
        for sg_name, sg_content in self.url_dict['url groups'].items():
            # sg_content will be a dict {'parent': [children]}
            for parent, children in sg_content.items():
                context = {'supercat': sg_name, 'subcat': parent}
                for child in children:
                    tuples_for_func.append(
                        (child, context)
                    )

        # results are going to be (response, url, context)
        results = self.multithread_requests(tuples_for_func[:100])

        # all works up to this point

    def cache_urls(self):
        # reference 'read debug cache' attribute
        write_cache = not self.context['read debug cache']

        # read cache
        if not write_cache:
            with shelve.open(self.cache_path) as db:
                self.all_urls = db[self.context['url cache key']]

        # write cache
        if write_cache:

            # check for self.all_urls attribute
            if not hasattr(self, 'all_urls'):
                raise Exception(
                    'Cannot cache urls, because self.get_urls() has '
                    'not yet been called, and self.all_urls is not defined.'
                )

            # write
            with shelve.open(self.cache_path) as db:
                db[self.context['url cache key']] = self.all_urls

        logging.debug(f'lpc: {self.all_urls}')

        return self.all_urls

    def multithread_requests(self, urls):

        if isinstance(urls[0], tuple):
            mode = 'tuples'

        if isinstance(urls[0], str):
            mode = 'regular'

        response_and_url = []
        with ThreadPoolExecutor(max_workers=200) as executor:
            if mode == 'regular':
                threads = [
                    executor.submit(
                        self.make_pycurl_request, url
                    )
                    for url
                    in urls
                ]

            if mode == 'tuples':
                threads = [
                    executor.submit(
                        self.make_pycurl_request, url, context
                    )
                    for url, context
                    in urls
                ]


            for r in as_completed(threads):
                try:
                    response_and_url.append(r.result())

                except Exception as e:
                    logging.warning(e)

        return response_and_url

    def make_pycurl_request(self, url, context=None):
        try:
            buffer = BytesIO()
            crl = pycurl.Curl()
            crl.setopt(crl.URL, url)
            crl.setopt(crl.WRITEDATA, buffer)
            crl.setopt(crl.CAINFO, certifi.where())
            crl.perform()

            crl.close()

            logging.debug(f'response recieved from {url}')

        except Exception as e:
            raise Exception(f'{url} failed because of {e}.')

        if context:
            return buffer.getvalue().decode(), url, context

        return buffer.getvalue().decode(), url

    @abstractmethod
    def parse_parent(self):
        """
        Parse the parent urls from the standard dict above, so that they
        can be used for folder or file names in the above method.
        """
        pass

    @abstractmethod
    def get_urls(self):
        """
        Recursively crawl through the site map, and get all
        urls for recipe pages.
        """
        pass

    @abstractmethod
    def recursive(self, links_to_do, cache=False):
        """
        Crawl through the sitemap, and get urls
        """
        pass

    @abstractmethod
    def make_url_dict(self):
        """
        Go through the recursively discovered list of urls, and filter them
        down to what we actually want; urls which are pages of recipes.
        """
        pass
