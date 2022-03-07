"""import and install modules"""

import argparse
import json
import logging
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    from dateutil.parser import parse
except ModuleNotFoundError as error:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'dateutil.parser'])
    from dateutil.parser import parse
try:
    import requests
except ModuleNotFoundError as error:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests'])
    import requests
try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError as error:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'bs4'])
    from bs4 import BeautifulSoup

try:
    import lxml
except ModuleNotFoundError as error:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'lxml'])
    import lxml
try:
    from json2html import *
except ModuleNotFoundError as error:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'json2html'])
    from json2html import *
try:
    from reportlab.lib import utils
except ModuleNotFoundError as error:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'reportlab'])
    from reportlab.lib import utils

try:
    import pymongo
except ModuleNotFoundError as error:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pymongo'])
    import pymongo

from pymongo import MongoClient

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image


def exception_wrapper(exit_mode=True):
    """Wraps the function in oreder to catch an exception, if exit_mode - exits the app and writes an exit message"""

    def inner_wrapper(func):
        def wrapper(*args, **kwargs):
            try:
                res = func(*args, **kwargs)
                return res
            except Exception as error:
                logging.exception(error)
                if exit_mode:
                    exit(f'An error occured: {error} \nExit to prevent further errors')

        return wrapper

    return inner_wrapper


@exception_wrapper()
def get_args():
    """ Unpacks arguments from command line and returns them as "args" object."""
    parser = argparse.ArgumentParser(description='Parses an RSS feed')
    parser.add_argument('--source', type=str, help='a source for parsing')
    parser.add_argument('--version', action='version', version='%(prog)s 5.0')
    parser.add_argument('--json', action='store_true', help='write collected feed into json file')
    parser.add_argument('--verbose', action='store_true', help='verbose status message')
    parser.add_argument('--limit', type=int, help='Limit of news in feed. In case of None Limit all feed is provided')
    parser.add_argument('--date', type=str, help='Provide news for this date in YYYYMMDD format')
    parser.add_argument('--tohtml', action='store_true', help='Convert feed to html format')
    parser.add_argument('--topdf', action='store_true', help='Convert feed to pdf format')
    parser.add_argument('--mongo', action='store_true', help='Cache news into MongoDB')
    args = parser.parse_args()
    if args.limit and args.limit <= 0:
        exit("Error: wrong --limit argument, limit value should be positive number")
    return args


@exception_wrapper()
def parse_news(source):
    """Requests the source page content and parses it with BeautifulSoup module"""
    url = requests.get(source)
    if url.status_code != 200:
        exit('Error opening RSS-feed')
    all_news = BeautifulSoup(url.content.decode('utf-8'), 'xml')
    return all_news


@exception_wrapper()
def cache_feed(allnews, source):
    """Creates list of dictionaries containing fields RSS-feed"""
    cache_list = []
    channel = allnews.channel
    entries = allnews.find_all('item')
    for entry in entries:
        cache_dict = {
            'RSS': channel.title.text,
            'RSS link': source,
        }
        cache_dict.update({
            'Title': entry.title.text,
            'News link': entry.link.text,
            'Published': str(parse(entry.pubDate.text).date()),
            'Image source': []
        })
        if entry.description:
            cache_dict.update({'Description': BeautifulSoup(entry.description.text, 'html.parser').text})
            if BeautifulSoup(entry.description.text, 'html.parser').img:
                URL = BeautifulSoup(entry.description.text, "html.parser").img["src"]
                img_file = f'images/{URL.strip("https://").replace("/", "").replace(":", "")}'
                if not os.path.isfile(img_file):
                    urllib.request.urlretrieve(URL, img_file)
                cache_dict['Image source'].append((URL, img_file))

        if entry.find('media:content'):
            for item in str(entry.find('media:content')).split():
                if 'url' in item:
                    URL = item.strip('url="').strip('"')
            img_file = f'images/{URL.strip("https://").replace("/", "").replace(":", "")}'
            if not os.path.isfile(img_file):
                urllib.request.urlretrieve(URL, img_file)
            cache_dict['Image source'].append((URL, img_file))

        cache_list.append(cache_dict)
    return cache_list


@exception_wrapper()
def cache_update(allnews, source):
    """Updates news in MongoDB"""
    news = db.news
    if bool(news.find_one()):
        for item in cache_feed(allnews, source):
            news.update_one({'_id': '_id'}, {"$set": item})
    else:
        for item in cache_feed(allnews, source):
            news.insert_one(item)


@exception_wrapper()
def read_cache(source=None, date=None, limit=None):
    """Downloads cached feed from MongoDB"""
    news_list = []
    news = db.news
    if not bool(news.find_one()):
        print("Unfortunately, there's no cached news yet")
    else:
        for record in news.find():
            if source:
                if record['Published'].replace('-', '') == date and record['RSS link'] == source:
                    news_list.append(record)
            elif record['Published'].replace('-', '') == date:
                news_list.append(record)
    return news_list[:limit]


@exception_wrapper()
def write_feed(feed_list, writing_mode=None):
    """Prints parsed RSS-feed depending on writing mode:
    if writing_mode is not None - into <<news_feed + posfix depending on current date-time>>.json file
    in json_files folder
    and prints content of the file into stdout
    else - prints parsed RSS-feed into stdout"""

    if writing_mode:
        if not os.path.exists('json_files'):
            os.makedirs('json_files')
        file_name = "json_files/news_feed" + str(datetime.now())
        file_name = file_name.replace(':', '').replace('.', '') + '.json'

        with open(file_name, "w", encoding='utf8') as file:
            json.dump(feed_list, file, ensure_ascii=False, indent=4)
        print('[')
        for entry in feed_list:
            print(" {")
            for key, value in entry.items():
                print(f"  '{key}':'{value}'")
            print(' },')
        print(']')
    else:
        if feed_list != []:
            for news in feed_list:
                for key, value in news.items():
                    if key != 'Image source':
                        print(f'{key + ":":<15} {value}')
                    else:
                        print(f'{key + ":":<15} {value[0][0]}')
                    if key == 'RSS link':
                        print()
                print()
                print()
        else:
            print('Feed is empty')


@exception_wrapper()
def convert2html(feed_list):
    """Converts parsed RSS-feed into html format and saves the result in html_files folder.
    File name consists of <<news_feed + posfix depending on current date-time>>.html"""

    if not os.path.exists('html_files'):
        os.makedirs('html_files')
    file_name = "html_files/news_feed" + str(datetime.now())
    file_name = file_name.replace(':', '').replace('.', '') + '.html'

    for dictionary in feed_list:
        element = {}
        with open(file_name, 'a', encoding='utf-8') as file:
            for k, v in dictionary.items():
                if k != 'Image source' and k != 'News link':
                    element.update({k: v})
            file.write(json2html.convert(json=element, table_attributes=" border='1', width='100%' "))

            if 'Image source' in dictionary:
                for image in dictionary['Image source']:
                    try:
                        file.write(f'<img src="{Path.cwd()}/{image[1]}" width = "220"><br>')
                        file.write(f'<b>Image source:</b> <tr><td><a href="{image[0]}">{image[0]}</a></td></tr><br>')

                    except Exception:
                        try:
                            file.write(f'<img src="{image[0]}" width = "220"><br>')
                            file.write(f'<b>Image source:</b> <tr><td><a href="{image[0]}">{image[0]}</a></td></tr>')
                        except Exception:
                            pass
            if 'News link' in dictionary:
                file.write(
                    f'<b>News link     :</b> <tr><td><a href="{dictionary["News link"]}">{dictionary["News link"]}</a></td></tr><br>')
                file.write('<br>')


@exception_wrapper()
def convert2pdf(feed_list):
    """Converts parsed RSS-feed into html format and saves the result in html_files folder.
    File name consists of <<news_feed + posfix depending on current date-time>>.pdf"""
    if not os.path.exists('pdf_files'):
        os.makedirs('pdf_files')
    file_name = "pdf_files/news_feed" + str(datetime.now())
    file_name = file_name.replace(':', '').replace('.', '') + '.pdf'
    pdfmetrics.registerFont(TTFont('DejaVuSerif', 'DejaVuSerif.ttf', 'UTF-8'))
    doc = SimpleDocTemplate(file_name, pagesize=letter,
                            rightMargin=72, leftMargin=72,
                            topMargin=72, bottomMargin=18)
    Story = []
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Justify', alignment=TA_JUSTIFY))
    for dictionary in feed_list:
        for key, value in dictionary.items():
            if key != 'Image source':
                Story.append(Paragraph(f'<font name="DejaVuSerif">{key}: {value}</font>', styles["Normal"]))
                Story.append(Spacer(1, 12))
            elif key == 'Image source':

                for source in value:
                    img_source = f'{Path.cwd()}/{source[1]}'
                    img = utils.ImageReader(img_source)
                    iw, ih = img.getSize()
                    aspect = ih / float(iw)
                    img = Image(img_source, 1.5 * inch, 1.5 * aspect * inch)
                    Story.append(img)
                    Story.append(Spacer(1, 12))
                    Story.append(Paragraph(f'<font name="DejaVuSerif">{key}: {source[0]}</font>', styles["Normal"]))
                    Story.append(Spacer(1, 12))
        Story.append(Spacer(2, 12))
    doc.build(Story)


@exception_wrapper()
def main_block():
    """Declares global variables, sets modes of the App, calls inner functions of the program"""
    global args
    global logger
    global client
    global db
    client = MongoClient('52.16.25.193', 27017)
    db = client["news_database"]
    if not os.path.exists('images'):
        os.makedirs('images')
    args = get_args()
    if args.verbose:
        logging.basicConfig(level='NOTSET', stream=sys.stdout)
        logger = logging.getLogger()
    else:
        logging.basicConfig(level=80)

    if args.date:
        feed_list = read_cache(source=args.source, date=args.date, limit=args.limit)
    else:
        allnews = parse_news(args.source)
        feed_list = cache_feed(allnews, args.source)[:args.limit]
        cache_update(allnews, args.source)

    if args.tohtml:
        convert2html(feed_list)

    if args.topdf:
        convert2pdf(feed_list)

    write_feed(feed_list, args.json)


if __name__ == "__main__":
    main_block()
