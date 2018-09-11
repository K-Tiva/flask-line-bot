# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import os
import sys
import json
from datetime import datetime
from jinja2 import  Environment, FileSystemLoader, select_autoescape
from flask import (
    Flask, render_template, g,
    request, redirect, url_for, abort
)
from flask_sqlalchemy import SQLAlchemy
from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    LineBotApiError, InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    FlexSendMessage, BubbleContainer, CarouselContainer,
    TemplateSendMessage, ConfirmTemplate, MessageAction
)


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.root_path, 'db.sqlite3')
#app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL') or 'postgresql://localhost/entries.db'
db = SQLAlchemy(app)


class Entry(db.Model):
    __tablename__ = 'entries'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(), nullable=False)
    deadline = db.Column(db.String(), nullable=False)
    body = db.Column(db.String(), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now(), nullable=False)


channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable')
    sys.exit(1)

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)


template_env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=select_autoescape(['json'])
)


@app.route('/')
def index():
    entries = Entry.query.order_by(Entry.deadline).all()
    return render_template('index.html', entries=entries)


@app.route('/post', methods=['POST'])
def add_entry():
    entry = Entry()
    entry.title = request.form['title']
    dt = datetime.strptime(request.form['deadline'], '%Y-%m-%d')
    entry.deadline = dt.strftime('%Y年%m月%d日')
    entry.body = request.form['body']
    entry.timestamp = datetime.now()
    db.session.add(entry)
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/delete', methods=['POST'])
def del_entry():
    entry = Entry()
    db.session.query(Entry).filter(Entry.id==int(request.form['id'])).delete()
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/callback', methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    print("Request body: " + body)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except LineBotApiError as e:
        print("Got exception from LINE Messaging API: %s\n" % e.message)
        for m in e.error.details:
            print(" %s: %s" % (m.property, m.message))
        print("\n")
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def message_text(event):
    global entry
    text = event.message.text

    if text == '周知事項を教えて':
        entries = Entry.query.order_by(Entry.deadline).all()
        template  = template_env.get_template('entries.json')
        data = template.render(dict(entries=entries))
        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(
                alt_text="Don't show contents...",
                contents=CarouselContainer.new_from_json_dict(json.loads(data))
            )
        )
    elif text == 'ただいま工事中です':
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="その命令は工事中です。しばらくお待ちください。")
        )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="その命令には対応していません。")
        )


if __name__ == '__main__':
    # heroku workaround: https://qiita.com/akabei/items/38f974716f194afea4a5
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
