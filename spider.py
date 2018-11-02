# -*- coding:utf-8 -*-


'__author__' == 'weiss'


import pymongo
from urllib.parse import urlencode
import requests
from lxml.etree import XMLSyntaxError
from requests.exceptions import ConnectionError
from pyquery import PyQuery as pq
from config import *

headers = {
        'Cookie': 'ABTEST=0|1541077442|v1; IPLOC=CN2201; SUID=4FC31A6F2028940A000000005BDAF9C2; PHPSESSID=ottcmthkj7r6gvpvfjfvdeenp4; SUIR=1541077442; SUID=4FC31A6F2E08990A000000005BDAF9C2; weixinIndexVisited=1; SNUID=820FD7A3CDC8B556DE3B12D4CD53AC94; JSESSIONID=aaaafjHt_FIbHbPMgk-Aw; ppinf=5|1541077561|1542287161|dHJ1c3Q6MToxfGNsaWVudGlkOjQ6MjAxN3x1bmlxbmFtZTo1OndlaXNzfGNydDoxMDoxNTQxMDc3NTYxfHJlZm5pY2s6NTp3ZWlzc3x1c2VyaWQ6NDQ6bzl0Mmx1SXliSUZYYk9tV1NjS1p2djRLbG9IRUB3ZWl4aW4uc29odS5jb218; pprdig=YEzu0D1M_oVNq3ycMo9ImtnIewc4sTPSKyv7XBGR6dt9YipW68Gsvdk_ISz0T5XMeB-uPm2LHfrrah9XzXOYQpATelf7799t_K__syqaj_mpGEJpJIqtu5p19Yec3hYH3gX-_qkQDkaw14XsV4QFr6_AbYSaRWrx8yGnVu5aSSA; sgid=31-37717255-AVvaibjk4RsduNj3HW4IDXws; ppmdig=1541077561000000c1fe20b7e575015a28d5438687496cbb; sct=3',
        'Host': 'weixin.sogou.com',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36'
    }

proxy = None
max_count = 5

client = pymongo.MongoClient(MONGO_URL, MONGO_PORT)
db = client[MONGO_DB]


# 获取代理方法
def get_proxy():
    try:
        # 利用我们维护好的代理池，从中获取代理
        response = requests.get(PROXY_POOL_URL)
        if response.status_code == 200:
            return response.text
        return None
    except ConnectionError:
        return None


# 获取索引页面信息
def get_html(url, count=1):
    print('Crawling', url)
    print('Trying Count', count)
    global proxy
    # 给一个最大请求次数，如果超过最大值，则返回None
    if count >= max_count:
        print('Tried Too Many Counts')
        return None
    try:
        # 第一次不需要代理，所以需要加一个if判断
        if proxy:
            # 代理配置方法
            proxies = {
                'http': 'http://' + proxy
            }
            response = requests.get(url, allow_redirects=False, headers=headers, proxies=proxies)
        else:
            response = requests.get(url, allow_redirects=False, headers=headers)
        # 判断状态码
        if response.status_code == 200:
            return response.text
        # 如果状态码为302，则需要代理ip
        if response.status_code == 302:
            # Need Proxy
            print('302')
            # 从get_proxy()方法中取出代理，并判断是否可用
            proxy = get_proxy()
            # print('?????????')
            if proxy:
                print('Using Proxy', proxy)
                return get_html(url)
            else:
                print('Get Proxy Failed')
                return None
    except ConnectionError as e:
        print('Error Occurred', e.args)
        proxy = get_proxy()
        count += 1
        return get_html(url)


base_url = 'https://weixin.sogou.com/weixin?'


# 获取索引页
def get_index(key_word, page):
    data = {
        'query': key_word,
        'type': 2,
        'page': page
    }
    queryies = urlencode(data)
    # 拼接为完整的url
    url = base_url + queryies
    html = get_html(url)
    # 返回完整页面
    return html


# 解析页面，利用pyquery获取每个文章的url
def parse_index(html):
    doc = pq(html)
    items = doc('.news-box .news-list li .txt-box h3 a').items()
    for item in items:
        yield item.attr('href')


# 获取每个文章的详情，微信的这个请求没有什么反爬虫措施，所以不需要别的措施
def get_detail(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        return None
    except ConnectionError:
        return None


# 解析每个文章详情页中我们所需要的消息，利用pyquery方法
def parse_detail(html):
    try:
        doc = pq(html)
        title = doc('.rich_media_title').text()
        content = doc('.rich_media_content ').text()
        date = doc('#publish_time').text()
        nickname = doc('.profile_nickname').text()
        wechat = doc('#js_profile_qrcode > div > p:nth-child(3) > span').text()
        return {
            'title': title,
            'content': content,
            'date': date,
            'nickname': nickname,
            'wechat': wechat
        }
    except XMLSyntaxError:
        return None


# 保存到mongodb中
def save_to_mongo(data):
    # 这个方法是保证存入数据库中的数据不是重复的
    if db[MONGO_TABLE].update({'title': data['title']}, {'$set': data}, True):
        print('Saved to Mongo', data)
    else:
        print('Saved to Mongo Faild', data['title'])


def main():
    # 使其翻页
    for page in range(1, 101):
        html = get_index(KEY_WORD, page)
        # 判断获取到的页面是否可用
        if html:
            # 可用则调用解析页面的方法
            article_urls = parse_index(html)
            # 返回的文章url使用生成器，所以遍历一下取出每个url
            for article_url in article_urls:
                print(article_url)
                # 并用解析出的每个文章url，传入获取文章详情页面方法中
                article_html = get_detail(article_url)
                # 判断获取到的文章详情页面是否有效
                if article_html:
                    # 有效则传入解析文章详情页面方法中进行解析，并提取出我们想要的数据
                    artcle_data = parse_detail(article_html)
                    if artcle_data:
                        # 如果提取出的数据有效，则保存到数据库中
                        save_to_mongo(artcle_data)


if __name__ == '__main__':
    main()