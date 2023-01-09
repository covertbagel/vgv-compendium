from collections import namedtuple
from csv import writer
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from json import dumps, loads
import re
from time import sleep

from flask import abort, Flask, redirect, render_template, request, send_file, url_for
from google.appengine.api import memcache, users, wrap_wsgi_app
from google.cloud import datastore
from requests import Session
import yt_dlp

from secrets import YT_DATA_API_KEY

app = Flask(__name__)
app.wsgi_app = wrap_wsgi_app(app.wsgi_app)
db = datastore.Client()

_CACHE_SECS_LONG = 86400  # 1 day.
_CACHE_SECS_SHORT = 1800  # 30 minutes.
_DATE_CORRECTION = timedelta(hours=4, minutes=10)
_DERIVED_NOTES_KEY = 'derived_notes'
_PARAMS = {
    'key': YT_DATA_API_KEY,
    'maxResults': '50',
    'part': 'contentDetails,snippet',
    'playlistId': 'PLI6HmVcz0NXquDc4QenBMxidVeFue6E08',
}
_PATTERN_ANCHOR = re.compile('(egg|event) (\d+)ʹ?')
_PATTERN_MACRO = re.compile('!(egg|event)')
_URL = 'https://www.googleapis.com/youtube/v3/playlistItems'
_WRITE_LOCK_KEY = 'write_lock'


Entry = namedtuple('Entry', 'author notes timestamp')
Item = namedtuple('Item', 'title video_id video_published_at')


@app.template_filter('to_date')
def to_date(d):
    d = datetime.fromisoformat(d[:-1]) - _DATE_CORRECTION
    return f'{d:%Y-%m-%d}'


@app.route('/')
def root():
    user = users.get_current_user()
    return render_template('index.html',
                           admin=users.is_current_user_admin(),
                           email=user.email() if user else '',
                           items=playlist_items(),
                           login='' if user else users.create_login_url('/'),
                           logout=users.create_logout_url('/') if user else '',
                           notes=get_derived_notes())


@app.route('/csv')
def csv():
    d = datetime.now()
    out = StringIO()
    w = writer(out)
    w.writerow(['~aired', 'title', 'video id', 'video published at', 'notes'])
    notes = get_derived_notes()
    for item in playlist_items():
        row = [to_date(item.video_published_at), *item]
        if item.video_id in notes:
            row.append(notes[item.video_id])
        w.writerow(row)
    out.seek(0)
    return send_file(
            BytesIO(out.read().encode('utf-8')),
            as_attachment=True,
            download_name=f'vgv_compendium.{d:%Y%m%d%H%M}.csv',
            max_age=_CACHE_SECS_SHORT,
            mimetype='Content-Type: text/csv; charset=utf-8')


@app.route('/detail/<video_id>')
def detail(video_id):
    item = get_item(video_id)
    if not item:
        abort(404)
    detail = get_detail(video_id)
    return render_template('detail.html',
                           admin=users.is_current_user_admin(),
                           detail=detail,
                           item=item,
                           msg=request.args.get('msg'))


@app.route('/raw-info/<video_id>')
def raw_info(video_id):
    item = get_item(video_id)
    if not item or not users.is_current_user_admin():
        abort(404)
    return render_template('pprint.html', value=get_info(item))


@app.route('/save-detail/<video_id>', methods=['POST'])
def save_detail(video_id):
    item = get_item(video_id)
    if not item or not users.is_current_user_admin():
        abort(404)
    notes = request.form.get('notes', '').strip()
    if len(notes) > 100:
        return redirect(url_for('detail',
                msg=('Notes must be ≤100 characters.'
                     ' Can bump limit if needed, lmk'),
                video_id=video_id))
    if 'ʹ' in notes:
        return redirect(url_for('detail',
                msg='Notes may not contain reserved ʹ character',
                video_id=video_id))
    while not acquire_write_lock():
        sleep(1)
    detail = get_detail(video_id)
    if (not detail.entries and not notes) or (
            detail.entries and detail.entries[-1].notes == notes):
        release_write_lock()
        return redirect(url_for('detail',
                msg='Nothing new to save',
                video_id=video_id))
    if detail.etag != request.form.get('etag', ''):
        release_write_lock()
        return redirect(url_for('detail',
                msg='Note has already been modified. Update failed',
                video_id=video_id))
    entry = Entry(author=users.get_current_user().email(),
                  notes=notes,
                  timestamp=datetime.utcnow().isoformat()[:19]+'Z')
    with db.transaction():
        detail.insert(entry)
        get_summary()[video_id] = entry
    release_write_lock()
    memcache.delete(_DERIVED_NOTES_KEY)
    return redirect(url_for('detail',
                            msg='Update successful!',
                            video_id=video_id))


@app.route('/storyboard/<video_id>')
def storyboard(video_id):
    item = get_item(video_id)
    if not item:
        abort(404)
    result = []
    for f in get_info(item)['formats']:
        if f['format_id'] in ('sb2', 'sb1'):
            result.append({k: f[k] for k in (
                'columns', 'format_id', 'fragments', 'height', 'rows', 'width',
            )})
            if len(result) == 2:
                break
    return result


class Detail:
    def __init__(self, entity):
        self._entity = entity
        self._entries = None

    @property
    def entries(self):
        if self._entries is None:
            self._entries = []
            for e in self._entity.get('e', []):
                x = loads(e)
                self._entries.append(Entry(x['a'], x['n'], x['t']))
        return self._entries

    @property
    def etag(self):
        return str(hash(self.entries[-1])) if self.entries else ''

    def insert(self, entry):
        self._entity['e'] = self._entity.get('e', [])+[dumps({
            'a': entry.author, 'n': entry.notes, 't': entry.timestamp})]
        db.put(self._entity)
        self._entries = None


def clean_title(t):
    common_end = ' | The Video Game Valley'
    if t.endswith(common_end):
        return t[:-len(common_end)]
    return t


def item(i):
    return Item(
            title=clean_title(i['snippet']['title']),
            video_id=i['contentDetails']['videoId'],
            video_published_at=i['contentDetails']['videoPublishedAt'])


def get_info(item):
    key = f'info:{item.video_id}'
    if info := memcache.get(key):
        return info
    with yt_dlp.YoutubeDL(params={'format': 'sb0'}, auto_init=False) as ydl:
        ydl.get_info_extractor('Youtube')
        info = ydl.extract_info(f'http://youtube.com/watch?v={item.video_id}',
                                download=False)
    memcache.add(key, info, time=_CACHE_SECS_LONG)
    return info


def get_item(video_id):
    for i in playlist_items():
        if video_id == i.video_id:
            return i


class Summary:
    def __init__(self, entity):
        self._entity = entity

    def __setitem__(self, video_id, entry):
        self._entity[video_id] = dumps({
            'a': entry.author, 'n': entry.notes, 't': entry.timestamp})
        db.put(self._entity)

    def __getitem__(self, video_id):
        if e := self._entity.get(video_id, None):
            x = loads(e)
            return Entry(x['a'], x['n'], x['t'])


def get_summary():
    key = db.key('summary', 'main')
    if s := db.get(key=key):
        return Summary(s)
    return Summary(datastore.Entity(key=key))


def get_derived_notes():
    if notes := memcache.get(_DERIVED_NOTES_KEY):
        return notes
    items, summary = playlist_items(), get_summary()
    counts, notes, start_idx = {}, {}, 0
    # Derivation from most to least recent events.
    for item_idx, i in enumerate(items):
        if s := summary[i.video_id]:
            n = []
            for part in reversed(s.notes.split(',')):
                part, start_idx = process_part(
                    part, counts, -1, item_idx, start_idx)
                n.append(part)
            notes[i.video_id] = ','.join(reversed(n))
    # Derivation from least to most recent events.
    for i in reversed(items[:start_idx+1]):
        if i.video_id in notes:
            n = []
            for part in notes[i.video_id].split(','):
                part, _ = process_part(part, counts, 1, 0, 0)
                n.append(part)
            notes[i.video_id] = ','.join(n)
    # This cleared when details are saved, so can have long cache time.
    memcache.add(_DERIVED_NOTES_KEY, notes, time=_CACHE_SECS_LONG)
    return notes


def process_part(part, counts, increment, item_idx, start_idx):
    p = part.strip()
    m = _PATTERN_MACRO.match(p)
    if m and m.group(1) in counts:
        name = m.group(1)
        counts[name] += increment
        part = part.replace(p, f'{name} {counts[name]}ʹ', 1)
    if m := _PATTERN_ANCHOR.match(p):
        name, count = m.group(1), int(m.group(2))
        if name not in counts:
            start_idx = max(start_idx, item_idx)
        counts[name] = count
    return part, start_idx


def get_detail(video_id):
    key = db.key('detail', video_id)
    if d := db.get(key=key):
        return Detail(d)
    return Detail(datastore.Entity(key=key))


def acquire_write_lock():
    return memcache.add(_WRITE_LOCK_KEY, None, time=5)


def release_write_lock():
    memcache.delete(_WRITE_LOCK_KEY)


def playlist_items():
    key = 'playlist_items'
    if items := memcache.get(key):
        return items
    items = []
    page_token = ''
    session = Session()
    session.params.update(_PARAMS)
    while page_token is not None:
        i, page_token = playlist_items_page(session, page_token)
        items += i
    memcache.add(key, items, time=_CACHE_SECS_SHORT)
    return items


def playlist_items_page(session, page_token):
    params = {'page_token': page_token} if page_token else {}
    result = session.get(_URL, params=params).json()
    return ([item(i) for i in result['items']],
            result.get('nextPageToken', None))  # Missing in last page.

