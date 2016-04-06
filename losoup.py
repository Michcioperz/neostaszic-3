import datetime
import urllib.parse

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, url_for, Response
from werkzeug.contrib.atom import AtomFeed

app = Flask(__name__)


def image_if_any(x) -> str:
    try:
        return x.find("a", "highslide").extract()["href"]
    except AttributeError:
        return None


def get_news(page: int = 1) -> list:
    r = requests.get("http://lo01.pl/staszic/index.php", params=dict(page=page))
    r.encoding = "UTF-8"
    return [dict(img=image_if_any(x), title=x.find("div", "news_title").get_text(),
                 id=urllib.parse.parse_qs(urllib.parse.urlparse(x.find("div", "news_title").a["href"]).query)["id"][0],
                 content=x.find("div", "news_content"),
                 author=x.find("div", "news_author").get_text().split("dodany przez: ", 1)[1],
                 time=datetime.datetime.strptime(x.find("div", "news_time").get_text(), "%H:%M %d.%m.%Y")) for x in
            BeautifulSoup(r.text).find_all("div",
                                           "news")]


def get_article(item: int) -> dict:
    r = requests.get("http://lo01.pl/staszic/index.php", params=dict(subpage="news", id=item))
    r.encoding = "UTF-8"
    x = BeautifulSoup(r.text).find("div", "news")
    print(x)
    return dict(img=image_if_any(x), title=x.find("div", "news_title").get_text(), id=item,
                content=x.find("div", "news_content"),
                author=x.find("div", "news_author").get_text().split("dodany przez: ", 1)[1],
                time=datetime.datetime.strptime(x.find("div", "news_time").get_text(), "%H:%M %d.%m.%Y"),
                cleantext=BeautifulSoup(x.find("div", "news_content").get_text()))


@app.route('/', defaults={"page": 1})
@app.route('/p/<int:page>')
def news_page(page: int) -> Response:
    return render_template("news_list.html", news=get_news(page), max=max)


@app.route('/n/<int:item>')
def news_item(item: int) -> Response:
    return render_template("news_item.html", article=get_article(item))


@app.route("/feed.atom")
def feed_atom() -> Response:
    feed = AtomFeed("NeoStaszic-3", feed_url=request.url, url=request.url_root)
    for article in get_news():
        feed.add(article["title"], article["content"], content_type="html", author=article["author"],
                 url=url_for("news_item", item=article["id"]), published=article["time"], updated=article["time"])
    return feed.get_response()


if __name__ == '__main__':
    app.run(debug=True)
