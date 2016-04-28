import datetime
import pickle
import urllib.parse
from operator import itemgetter

import bleach
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, url_for, Response, jsonify, abort
from redis import Redis
from werkzeug.contrib.atom import AtomFeed

app = Flask(__name__)
cache = Redis()

page_ttl = 180
article_ttl = 1800


def image_if_any(x: BeautifulSoup) -> str:
    try:
        return x.find("a", "highslide").extract()["href"]
    except AttributeError:
        return None


def _get_news(page: int = 1) -> list:
    r = requests.get("http://lo01.pl/staszic/index.php", params=dict(page=page))
    r.encoding = "UTF-8"
    n = [dict(img=image_if_any(x), title=x.find("div", "news_title").get_text(),
              id=urllib.parse.parse_qs(urllib.parse.urlparse(x.find("div", "news_title").a["href"]).query)["id"][0],
              content=str(x.find("div", "news_content")),
              author=x.find("div", "news_author").get_text().split("dodany przez: ", 1)[1],
              time=datetime.datetime.strptime(x.find("div", "news_time").get_text(), "%H:%M %d.%m.%Y"),
              cleantext=str(x.find("div", "news_content").get_text()).strip(), pinned=False)
         for x in BeautifulSoup(r.text).find_all("div", "news")]
    if page == 1:
        i = 0
        while sorted(n[i:], key=itemgetter("time"), reverse=True) != n[i:]:
            print(i)
            n[i]["pinned"] = True
            i += 1
    for news in n:
        news["content"] = bleach.clean(news["content"], strip=True, tags=["p", "strong", "em", "ul", "ol", "li", "img"])
    with cache.pipeline() as pipe:
        pipe.set('p:%i' % page, pickle.dumps(n))
        pipe.expire('p:%i' % page, page_ttl)
        pipe.execute()
    return n


def get_news(page: int = 1) -> dict:
    loaded = cache.get("p:%i" % page)
    if loaded:
        return pickle.loads(loaded)
    return _get_news(page)


def get_fresh_news() -> dict:
    return sorted(get_news(1)+get_news(2), key=itemgetter("time"), reverse=True)


def _get_article(item: int) -> dict:
    r = requests.get("http://lo01.pl/staszic/index.php", params=dict(subpage="news", id=item))
    r.encoding = "UTF-8"
    x = BeautifulSoup(r.text).find("div", "news")
    a = dict(img=image_if_any(x), title=str(x.find("div", "news_title").get_text()), id=item,
             content=str(x.find("div", "news_content")),
             author=str(x.find("div", "news_author").get_text()).split("dodany przez: ", 1)[1],
             time=datetime.datetime.strptime(x.find("div", "news_time").get_text(), "%H:%M %d.%m.%Y"),
             cleantext=str(x.find("div", "news_content").get_text()).strip())
    a["content"] = bleach.clean(a["content"], strip=True, tags=["p", "strong", "em", "ul", "ol", "li", "img"])
    with cache.pipeline() as pipe:
        pipe.set('n:%i' % item, pickle.dumps(a))
        pipe.expire('n:%i' % item, article_ttl)
        pipe.execute()
    return a


def get_article(item: int) -> dict:
    loaded = cache.get("n:%i" % item)
    if loaded:
        return pickle.loads(loaded)
    return _get_article(item)


@app.route('/', defaults={"page": 1})
@app.route('/p/<int:page>')
def news_page(page: int) -> Response:
    return render_template("news_list.html", news=get_news(page), max=max, len=len)


@app.route('/p/<int:page>.json')
def news_page_json(page: int) -> Response:
    return jsonify(data=get_news(page))


@app.route('/p/f')
def news_page_fresh() -> Response:
    return render_template("news_list.html", news=get_fresh_news(), max=max, len=len, page=1)


@app.route('/p/f.json')
def news_page_fresh_json() -> Response:
    return jsonify(data=get_fresh_news())


@app.route('/n/<int:item>')
def news_item(item: int) -> Response:
    if item < 73: abort(404)
    return render_template("news_item.html", article=get_article(item))


@app.route('/n/<int:item>.json')
def news_item_json(item: int) -> Response:
    if item < 73: abort(404)
    return jsonify(data=get_article(item))


@app.route("/feed.atom")
def feed_atom() -> Response:
    feed = AtomFeed("NeoStaszic-3", feed_url=request.url, url=request.url_root)
    for article in sorted(get_news(), key=itemgetter("time"), reverse=True):
        feed.add(article["title"], article["content"], content_type="html", author=article["author"],
                 url=url_for("news_item", item=article["id"]), published=article["time"], updated=article["time"])
    return feed.get_response()


if __name__ == '__main__':
    app.run(debug=True)
