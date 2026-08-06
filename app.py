from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from urllib.parse import urlparse, urljoin
from functools import wraps
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

# app.py はプロジェクト直下に置く。
# 実体（templates / static / data）は bousai_app/ 配下にあるので、そこを参照する。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, 'bousai_app')

app = Flask(
    __name__,
    template_folder=os.path.join(APP_DIR, 'templates'),
    static_folder=os.path.join(APP_DIR, 'static'),
)
app.secret_key = 'your-secret-key-here'

# 管理者認証情報
ADMIN_CREDENTIALS = {
    'admin': '123'
}

# ────────────────────────────────
# 気象警報・注意報設定
PREFECTURE_CODE = "020000"  # 青森県
AREA_NAME = "青森市"

# ワークショップ課題：青森市の市区町村コードに変更する
AREA_CODE = "0220100"

WARNING_URL = (
    f"https://www.jma.go.jp/bosai/warning/data/r8/{PREFECTURE_CODE}.json"
)

JST = timezone(timedelta(hours=9))

# 警報・注意報のコード一覧
WARNING_CODES = {
    "00": "解除",
    "02": "暴風雪警報",
    "03": "レベル3大雨警報",
    "04": "洪水警報",
    "05": "暴風警報",
    "06": "大雪警報",
    "07": "波浪警報",
    "08": "レベル3高潮警報",
    "09": "レベル3土砂災害警報",
    "10": "レベル2大雨注意報",
    "12": "大雪注意報",
    "13": "風雪注意報",
    "14": "雷注意報",
    "15": "強風注意報",
    "16": "波浪注意報",
    "17": "融雪注意報",
    "18": "洪水注意報",
    "19": "レベル2高潮注意報",
    "20": "濃霧注意報",
    "21": "乾燥注意報",
    "22": "なだれ注意報",
    "23": "低温注意報",
    "24": "霜注意報",
    "25": "着氷注意報",
    "26": "着雪注意報",
    "27": "その他の注意報",
    "29": "レベル2土砂災害注意報",
    "32": "暴風雪特別警報",
    "33": "レベル5大雨特別警報",
    "35": "暴風特別警報",
    "36": "大雪特別警報",
    "37": "波浪特別警報",
    "38": "レベル5高潮特別警報",
    "39": "レベル5土砂災害特別警報",
    "43": "レベル4大雨危険警報",
    "48": "レベル4高潮危険警報",
    "49": "レベル4土砂災害危険警報"
}

# ────────────────────────────────
# サンプルデータの読み込み
DATA_FILE = os.path.join(APP_DIR, 'data', 'shelters.json')
INSTRUCTIONS_FILE = os.path.join(APP_DIR, 'data', 'instructions.json')

def load_json(path, default):
    """JSONファイルを読み込む（存在しない・壊れている場合は default を返す）"""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def normalize_shelters(data):
    """既存の避難所データに id と管理用フィールドを補完する"""
    if not isinstance(data, list):
        return []

    normalized = []
    for index, shelter in enumerate(data):
        if not isinstance(shelter, dict):
            continue
        normalized_shelter = dict(shelter)
        if not normalized_shelter.get('id'):
            normalized_shelter['id'] = f"shelter-{index + 1}"
        normalized_shelter.setdefault('postal_code', '')
        normalized_shelter.setdefault('address', '青森県青森市')
        normalized_shelter.setdefault('lat', '')
        normalized_shelter.setdefault('lng', '')
        normalized_shelter.setdefault('capacity', [])
        normalized_shelter.setdefault('pet', '可')
        normalized_shelter.setdefault('barrier_free', '有')
        normalized_shelter.setdefault('opening_status', '開設〇')
        normalized_shelter.setdefault('comment', '')
        normalized.append(normalized_shelter)
    return normalized


shelters = normalize_shelters(load_json(DATA_FILE, []))
instructions = load_json(INSTRUCTIONS_FILE, [])


def save_shelters():
    """避難所データをJSONファイルに保存する"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(shelters, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def save_instructions():
    """指示ボードのデータをファイルに保存する"""
    try:
        with open(INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(instructions, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_next_instruction_id():
    ids = []
    for item in instructions:
        try:
            ids.append(int(item.get('id', 0)))
        except (TypeError, ValueError):
            continue
    return max(ids, default=0) + 1


def get_instruction_by_id(instruction_id):
    for item in instructions:
        if str(item.get('id', '')) == str(instruction_id):
            return item
    return None


def get_shelter_by_id(shelter_id):
    """IDから避難所を取得する"""
    for shelter in shelters:
        if str(shelter.get('id', '')) == str(shelter_id):
            return shelter
    return None
# ────────────────────────────────

# ────────────────────────────────
# 認証関連の設定とヘルパー関数
def is_safe_url(target):
    """リダイレクト先URLが安全かどうかチェック"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def login_required(f):
    """認証が必要なページに付けるデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in') and not app.config.get('TESTING'):
            # 現在のURLをnextパラメータとしてログイン画面にリダイレクト
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_japan_time():
    """日本時間（JST）の現在時刻を取得する"""
    return datetime.now(JST).strftime("%Y年%m月%d日 %H:%M")


def format_report_time(iso_str):
    """気象庁の発表時刻（ISO形式）をJSTの表示用文字列に変換する"""
    if not iso_str:
        return "不明"
    try:
        parsed = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        if parsed.tzinfo:
            parsed = parsed.astimezone(JST)
        return parsed.strftime("%Y年%m月%d日 %H:%M")
    except ValueError:
        return iso_str


def _to_text(value):
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        return '・'.join(str(item) for item in value if str(item).strip())
    return str(value).strip()


def _parse_numeric(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        digits = ''.join(ch for ch in value if ch.isdigit() or ch in '.-')
        if digits:
            try:
                return float(digits)
            except ValueError:
                return None
    return None


def _build_shelter_display(shelter, index=0):
    if not isinstance(shelter, dict):
        return {}

    def pick(*keys):
        for key in keys:
            if shelter.get(key) not in (None, ''):
                return shelter.get(key)
        return None

    opening_status = pick('open_status', 'status', 'open', 'opening_status') or '開設〇'
    travel_time = pick('travelTime', 'time', 'duration', '所要時間')
    distance = pick('distance', '距離')
    congestion = pick('congestion', '混雑度', 'crowd')
    hazards = pick('hazards', 'disasterTypes', '対応災害', 'hazard')

    if travel_time is None:
        travel_time = f"{5 + (index % 4) * 3}分"
    if distance is None:
        distance = f"{(index % 5 + 1) * 0.7:.1f}km"
    if hazards is None:
        hazards = ['地震']

    congestion_text = _to_text(congestion)
    if congestion_text in {'low', '空いている', '空き', '空きあり'}:
        congestion_label = '空いている'
        congestion_rank = 0
        congestion_class = 'low'
    elif congestion_text in {'medium', 'やや混雑'}:
        congestion_label = 'やや混雑'
        congestion_rank = 1
        congestion_class = 'medium'
    elif congestion_text in {'high', '混雑'}:
        congestion_label = '混雑'
        congestion_rank = 2
        congestion_class = 'high'
    else:
        congestion_label = '空いている'
        congestion_rank = 0
        congestion_class = 'low'

    opening_status_text = _to_text(opening_status)
    is_closed = '閉鎖' in opening_status_text or '閉鎖中' in opening_status_text
    if is_closed:
        congestion_label = '－'
        congestion_rank = 3
        congestion_class = 'closed'
        hazards_text = '－'
    else:
        hazards_text = _to_text(hazards)

    distance_num = _parse_numeric(distance) if distance is not None else None
    travel_time_num = _parse_numeric(travel_time) if travel_time is not None else None
    if travel_time_num is None:
        travel_time_num = 5 + (index % 4) * 3

    return {
        'id': shelter.get('id') or f"shelter-{index + 1}",
        'name': shelter.get('name') or '避難所',
        'address': shelter.get('address') or '青森県青森市',
        'opening_status': opening_status_text,
        'travel_time': travel_time,
        'travel_time_num': travel_time_num,
        'distance': distance,
        'distance_num': distance_num if distance_num is not None else (index % 5 + 1) * 0.7,
        'congestion': congestion_label,
        'congestion_rank': congestion_rank,
        'congestion_class': congestion_class,
        'hazards': hazards_text,
        'comment': _to_text(shelter.get('comment') or shelter.get('remark') or shelter.get('remarks')),
        'capacity': _to_text(shelter.get('capacity') or shelter.get('収容人数')) or '未設定',
        'current_users': _to_text(shelter.get('current_users') or shelter.get('現在の避難者数')) or '未設定',
        'pet': _to_text(shelter.get('pet') or '不明') or '不明',
        'toilet': _to_text(shelter.get('toilet') or '不明') or '不明',
        'stock': _to_text(shelter.get('stock') or shelter.get('備蓄')) or '未設定',
        'barrier_free': _to_text(shelter.get('barrier_free') or '不明') or '不明',
        'is_closed': is_closed,
    }


def _sort_display_results(items, sort_key):
    sort_key = sort_key or 'distance_asc'
    def sort_key_fn(item):
        if sort_key == 'distance_desc':
            return (-item.get('distance_num', 0), item.get('travel_time_num', 0), item.get('name', ''))
        if sort_key == 'time_asc':
            return (item.get('travel_time_num', 0), item.get('distance_num', 0), item.get('name', ''))
        if sort_key == 'time_desc':
            return (-item.get('travel_time_num', 0), item.get('distance_num', 0), item.get('name', ''))
        if sort_key == 'congestion_asc':
            return (item.get('congestion_rank', 0), item.get('distance_num', 0), item.get('name', ''))
        if sort_key == 'congestion_desc':
            return (-item.get('congestion_rank', 0), item.get('distance_num', 0), item.get('name', ''))
        if sort_key == 'name_desc':
            return (item.get('name', ''), item.get('distance_num', 0))
        if sort_key == 'name_asc':
            return (item.get('name', ''), item.get('distance_num', 0))
        return (item.get('distance_num', 0), item.get('travel_time_num', 0), item.get('name', ''))

    if sort_key in {'name_asc', 'name_desc'}:
        items = sorted(items, key=lambda item: item.get('name', ''), reverse=sort_key == 'name_desc')
        return items

    return sorted(items, key=sort_key_fn)


def filter_shelters(district=None):
    """district 指定があれば一致する避難所のみ、なければ全件を返す"""
    return [s for s in shelters if not district or s.get('district') == district]


def get_search_results_items(shelter_data, query='', sort_key='distance_asc', crowd=None, distance=None, support=None):
    q = (query or '').strip()
    crowd_value = (crowd or '').strip().lower()
    distance_value = (distance or '').strip()
    support_value = (support or '').strip().lower()

    filtered = []
    for index, shelter in enumerate(shelter_data):
        if not isinstance(shelter, dict):
            continue

        display = _build_shelter_display(shelter, index)
        if q:
            haystack = ' '.join([
                shelter.get('name', ''),
                shelter.get('address', ''),
                shelter.get('comment', ''),
                shelter.get('opening_status', ''),
            ]).lower()
            if q.lower() not in haystack:
                continue

        if crowd_value:
            crowd_map = {
                'low': '空いている',
                'medium': 'やや混雑',
                'high': '混雑',
            }
            expected_label = crowd_map.get(crowd_value)
            if expected_label and display.get('congestion') != expected_label:
                continue

        if distance_value:
            try:
                max_distance = float(distance_value)
            except ValueError:
                max_distance = None
            if max_distance is not None and display.get('distance_num', 0) > max_distance:
                continue

        if support_value in {'wheelchair', 'medical', 'both'}:
            barrier_free = str(shelter.get('barrier_free', '')).lower()
            pet = str(shelter.get('pet', '')).lower()
            if support_value == 'wheelchair' and '有' not in barrier_free and '可' not in barrier_free:
                continue
            if support_value == 'medical' and '可' not in pet and '対応' not in pet:
                continue
            if support_value == 'both' and ('有' not in barrier_free and '可' not in barrier_free) and ('可' not in pet and '対応' not in pet):
                continue

        filtered.append(display)
    return _sort_display_results(filtered, sort_key)


def parse_area_warnings(warning_data):
    """気象庁の新形式JSONから対象市区町村の発表・継続中の情報を抽出する"""
    if not isinstance(warning_data, list):
        raise ValueError("気象庁の警報・注意報データが新形式の配列ではありません")

    warnings = []
    seen_codes = set()
    report_datetimes = []

    for report in warning_data:
        if not isinstance(report, dict):
            continue

        report_datetime = report.get("reportDatetime")
        if isinstance(report_datetime, str) and report_datetime:
            report_datetimes.append(report_datetime)

        warning = report.get("warning")
        if not isinstance(warning, dict):
            continue

        class20_items = warning.get("class20Items", [])
        if not isinstance(class20_items, list):
            continue

        area = next(
            (
                item for item in class20_items
                if isinstance(item, dict)
                and item.get("areaCode") == AREA_CODE
            ),
            None
        )
        if not area:
            continue

        kinds = area.get("kinds", [])
        if not isinstance(kinds, list):
            continue

        for kind in kinds:
            if not isinstance(kind, dict):
                continue

            status = kind.get("status", "")
            code = kind.get("code", "")
            if status not in ("発表", "継続") or not code or code in seen_codes:
                continue

            warnings.append({
                "name": WARNING_CODES.get(
                    code,
                    f"不明な警報・注意報 (コード: {code})"
                ),
                "code": code,
                "status": status
            })
            seen_codes.add(code)

    latest_report_datetime = max(report_datetimes, default="")
    return warnings, latest_report_datetime


def get_map_shelters():
    """地図表示用に避難所データを整形する"""
    base_lat = 40.8244
    base_lng = 140.7400
    crowd_levels = [
        {"value": "low", "label": "空き", "color": "#16a34a"},
        {"value": "medium", "label": "やや混雑", "color": "#f59e0b"},
        {"value": "high", "label": "混雑", "color": "#dc2626"},
        {"value": "unknown", "label": "未設定", "color": "#6b7280"},
    ]

    map_shelters = []
    for index, shelter in enumerate(shelters):
        if not isinstance(shelter, dict):
            continue

        crowd = shelter.get('crowd') or 'unknown'
        crowd_info = next(
            (item for item in crowd_levels if item['value'] == crowd),
            crowd_levels[-1]
        )

        lat_offset = ((index % 5) - 2) * 0.008
        lng_offset = ((index // 5) % 4 - 1.5) * 0.012

        map_shelters.append({
            'name': shelter.get('name') or '避難所',
            'lat': round(base_lat + lat_offset, 5),
            'lng': round(base_lng + lng_offset, 5),
            'crowd': crowd,
            'crowd_label': crowd_info['label'],
            'color': crowd_info['color'],
        })

    return map_shelters


def get_weather_warnings():
    """対象市区町村の警報・注意報を取得する"""
    try:
        with urllib.request.urlopen(url=WARNING_URL, timeout=10) as res:
            warning_data = json.loads(res.read())

        warnings, report_datetime = parse_area_warnings(warning_data)

        return {
            "area_name": AREA_NAME,
            "warnings": warnings,
            "report_time": format_report_time(report_datetime),
            "last_fetch_time": get_japan_time()
        }

    except Exception:
        return {
            "area_name": AREA_NAME,
            "warnings": [],
            "report_time": "取得失敗",
            "last_fetch_time": get_japan_time(),
            "error": True
        }


# トップページ：templates/index.html を返す（住民向け指示も表示する）
@app.route('/')
def index():
    resident_notices = [i for i in instructions if i.get('target') == '住民']
    highlight_name = request.args.get('highlight', '').strip()
    highlight_address = request.args.get('address', '').strip()
    shelters_for_map = get_map_shelters()
    if highlight_name:
        for shelter in shelters_for_map:
            if shelter['name'] == highlight_name:
                shelter['highlight'] = True
                shelter['popup_address'] = highlight_address or shelter.get('address', '')
                break
    return render_template(
        'index.html',
        resident_notices=resident_notices,
        shelters=shelters_for_map,
        weather_summary=get_weather_warnings(),
        highlight_name=highlight_name,
    )

# ログインページ
@app.route('/login', methods=['GET', 'POST'])
def login():
    # リダイレクト先を取得（デフォルトは避難所登録画面）
    next_url = request.args.get('next') or request.form.get('next')

    # 安全でないURLの場合はデフォルトページにリダイレクト
    if not next_url or not is_safe_url(next_url):
        next_url = url_for('shelter_register')

    if request.method == 'POST':
        password = request.form.get('password', '').strip()

        # 認証チェック
        username = next(
            (name for name, registered_password in ADMIN_CREDENTIALS.items()
             if registered_password == password),
            None
        )
        if username:
            session['logged_in'] = True
            session['username'] = username
            # ログイン成功後は指定されたページにリダイレクト
            return redirect(next_url)
        return render_template('login.html', error=True, message="パスワードが正しくありません。", next=next_url)

    # ログイン済みの場合は指定されたページにリダイレクト
    if session.get('logged_in'):
        return redirect(next_url)

    return render_template('login.html', next=next_url)

# ログアウト
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# 避難所登録ページ：GETはフォーム表示、POSTは登録処理を行う
@app.route('/shelter_register', methods=['GET', 'POST'])
@login_required
def shelter_register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            return render_template('shelter_register.html', error=True, message='避難所名は必須です。')

        # 新しい避難所オブジェクトを作成して保存
        new_shelter = {
            'name': name,
            'created_at': get_japan_time()
        }
        shelters.append(new_shelter)
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(shelters, f, ensure_ascii=False, indent=2)
        except Exception:
            # 保存に失敗しても処理は継続し、ユーザーにはエラーメッセージを表示
            return render_template('shelter_register.html', error=True, message='登録に失敗しました。')

        return render_template('shelter_register.html', success=True, message='避難所を登録しました。')

    return render_template('shelter_register.html')

# 避難所検索ページ
@app.route('/shelter_search')
def shelter_search():
    return render_template('shelter_search.html')


# 避難所管理ページ
@app.route('/shelter_manage', methods=['GET', 'POST'])
@login_required
def shelter_manage():
    message = None
    message_type = None
    selected_shelter = None
    selected_shelter_id = ''
    capacity_options = [
        {'value': '〜300', 'label': '〜300 /人'},
        {'value': '301〜600', 'label': '301〜600 /人'},
        {'value': '601〜900', 'label': '601〜900 /人'},
        {'value': '901〜1200', 'label': '901〜1200 /人'},
        {'value': '1201〜1500', 'label': '1201〜1500 /人'},
        {'value': '1501〜', 'label': '1501〜 /人'},
    ]

    if request.method == 'POST':
        action = request.form.get('action', 'create')
        selected_shelter_id = request.form.get('shelter_id', '').strip()

        if action == 'create':
            name = request.form.get('name', '').strip()
            if not name:
                message = '避難所名を入力してください。'
                message_type = 'error'
            else:
                postal_code = f"{request.form.get('postal_code_1', '').strip()}-{request.form.get('postal_code_2', '').strip()}".strip('-')
                address_detail = request.form.get('address_detail', '').strip()
                address = f"青森県青森市{address_detail}" if address_detail else '青森県青森市'
                lat = request.form.get('lat', '').strip()
                lng = request.form.get('lng', '').strip()
                capacity = request.form.getlist('capacity_option')
                pet = request.form.get('pet', '可')
                barrier_free = request.form.get('barrier_free', '有')
                opening_status = request.form.get('opening_status', '開設〇')
                comment = request.form.get('comment', '').strip()

                new_shelter = {
                    'id': f"shelter-{len(shelters) + 1}",
                    'name': name,
                    'postal_code': postal_code,
                    'address': address,
                    'lat': float(lat) if lat else '',
                    'lng': float(lng) if lng else '',
                    'capacity': capacity,
                    'pet': pet,
                    'barrier_free': barrier_free,
                    'opening_status': opening_status,
                    'comment': comment,
                    'created_at': get_japan_time(),
                    'updated_at': get_japan_time(),
                }
                shelters.append(new_shelter)
                save_shelters()
                message = '避難所を登録しました。'
                message_type = 'success'

        elif action == 'update':
            selected_shelter = get_shelter_by_id(selected_shelter_id)
            if not selected_shelter:
                message = '更新対象の避難所を選択してください。'
                message_type = 'error'
            else:
                name = request.form.get('name_update', '').strip()
                if not name:
                    message = '避難所名を入力してください。'
                    message_type = 'error'
                else:
                    comment = request.form.get('comment_update', '').strip()
                    selected_shelter['name'] = name
                    selected_shelter['comment'] = comment
                    selected_shelter['updated_at'] = get_japan_time()
                    save_shelters()
                    message = '避難所情報を更新しました。'
                    message_type = 'success'

        elif action == 'delete':
            selected_shelter = get_shelter_by_id(selected_shelter_id)
            if not selected_shelter:
                message = '削除対象の避難所を選択してください。'
                message_type = 'error'
            else:
                shelters[:] = [s for s in shelters if str(s.get('id', '')) != str(selected_shelter_id)]
                save_shelters()
                message = '避難所を削除しました。'
                message_type = 'success'

    if selected_shelter_id:
        selected_shelter = get_shelter_by_id(selected_shelter_id)

    return render_template(
        'shelter_manage.html',
        shelters=shelters,
        selected_shelter=selected_shelter,
        selected_shelter_id=selected_shelter_id,
        capacity_options=capacity_options,
        message=message,
        message_type=message_type,
    )


# 全施設一覧ページ
@app.route('/all_shelters')
def all_shelters():
    sort_key = request.args.get('sort', 'distance_asc')
    return render_template('search_results.html', results=get_search_results_items(shelters, sort_key=sort_key), sort_key=sort_key)


# 未開設の避難所一覧ページ
@app.route('/unopened_shelters')
def unopened_shelters():
    sort_key = request.args.get('sort', 'distance_asc')
    return render_template('search_results.html', results=[], sort_key=sort_key)


# 指示・発信ボード：一覧表示
@app.route('/board')
@login_required
def board():
    internal_instructions = [i for i in instructions if (i.get('kind') != 'resident' and str(i.get('target', '')) != '住民')]
    resident_instructions = [i for i in instructions if i.get('kind') == 'resident' or i.get('target') == '住民']
    return render_template(
        'board.html',
        internal_instructions=internal_instructions,
        resident_instructions=resident_instructions,
    )


@app.route('/board/internal/new', methods=['GET', 'POST'])
@login_required
def board_internal_new():
    form_values = {
        'title': '',
        'recipient_department': '',
        'recipient_person': '',
        'priority': '',
        'deadline': '',
        'content': '',
        'report_method': '',
        'completion_condition': '',
        'notes': '',
    }
    message = None
    message_type = None

    if request.method == 'POST':
        form_values.update({
            'title': request.form.get('title', '').strip(),
            'recipient_department': request.form.get('recipient_department', '').strip(),
            'recipient_person': request.form.get('recipient_person', '').strip(),
            'priority': request.form.get('priority', '').strip(),
            'deadline': request.form.get('deadline', '').strip(),
            'content': request.form.get('content', '').strip(),
            'report_method': request.form.get('report_method', '').strip(),
            'completion_condition': request.form.get('completion_condition', '').strip(),
            'notes': request.form.get('notes', '').strip(),
        })

        status = request.form.get('submit_action', 'draft').strip()
        if not form_values['title'] or not form_values['content']:
            message = '件名と指示内容は必須です。'
            message_type = 'error'
        else:
            new_item = {
                'id': get_next_instruction_id(),
                'kind': 'internal',
                'target': form_values['recipient_department'] or '防災課',
                'title': form_values['title'],
                'recipient_department': form_values['recipient_department'],
                'recipient_person': form_values['recipient_person'],
                'priority': form_values['priority'],
                'deadline': form_values['deadline'],
                'content': form_values['content'],
                'report_method': form_values['report_method'],
                'completion_condition': form_values['completion_condition'],
                'notes': form_values['notes'],
                'status': '下書き' if status == 'draft' else '送信済み',
                'created_at': get_japan_time(),
                'updated_at': get_japan_time(),
            }
            instructions.append(new_item)
            save_instructions()
            return redirect(url_for('board'))

    return render_template('board_form.html', form_values=form_values, mode='internal', message=message, message_type=message_type)


@app.route('/board/resident/new', methods=['GET', 'POST'])
@login_required
def board_resident_new():
    form_values = {
        'title': '',
        'area': '',
        'urgency': '',
        'content': '',
        'published_at': '',
        'notes': '',
    }
    message = None
    message_type = None

    if request.method == 'POST':
        form_values.update({
            'title': request.form.get('title', '').strip(),
            'area': request.form.get('area', '').strip(),
            'urgency': request.form.get('urgency', '').strip(),
            'content': request.form.get('content', '').strip(),
            'published_at': request.form.get('published_at', '').strip(),
            'notes': request.form.get('notes', '').strip(),
        })
        status = request.form.get('submit_action', 'draft').strip()
        if not form_values['title'] or not form_values['content']:
            message = 'タイトルと内容は必須です。'
            message_type = 'error'
        else:
            new_item = {
                'id': get_next_instruction_id(),
                'kind': 'resident',
                'target': '住民',
                'title': form_values['title'],
                'area': form_values['area'],
                'urgency': form_values['urgency'],
                'content': form_values['content'],
                'published_at': form_values['published_at'],
                'notes': form_values['notes'],
                'status': '下書き' if status == 'draft' else '公開中',
                'created_at': get_japan_time(),
                'updated_at': get_japan_time(),
            }
            instructions.append(new_item)
            save_instructions()
            return redirect(url_for('board'))

    return render_template('board_form.html', form_values=form_values, mode='resident', message=message, message_type=message_type)


@app.route('/board/edit/<int:instruction_id>', methods=['GET', 'POST'])
@login_required
def board_edit(instruction_id):
    instruction = get_instruction_by_id(instruction_id)
    if not instruction:
        return redirect(url_for('board'))

    if str(instruction.get('status', '')).strip() != '下書き':
        return redirect(url_for('board'))

    form_values = {
        'title': instruction.get('title', '') or instruction.get('content', ''),
        'recipient_department': instruction.get('recipient_department', ''),
        'recipient_person': instruction.get('recipient_person', ''),
        'priority': instruction.get('priority', ''),
        'deadline': instruction.get('deadline', ''),
        'content': instruction.get('content', ''),
        'report_method': instruction.get('report_method', ''),
        'completion_condition': instruction.get('completion_condition', ''),
        'notes': instruction.get('notes', ''),
        'area': instruction.get('area', ''),
        'urgency': instruction.get('urgency', ''),
        'published_at': instruction.get('published_at', ''),
    }
    message = None
    message_type = None

    if request.method == 'POST':
        form_values.update({
            'title': request.form.get('title', '').strip(),
            'recipient_department': request.form.get('recipient_department', '').strip(),
            'recipient_person': request.form.get('recipient_person', '').strip(),
            'priority': request.form.get('priority', '').strip(),
            'deadline': request.form.get('deadline', '').strip(),
            'content': request.form.get('content', '').strip(),
            'report_method': request.form.get('report_method', '').strip(),
            'completion_condition': request.form.get('completion_condition', '').strip(),
            'notes': request.form.get('notes', '').strip(),
            'area': request.form.get('area', '').strip(),
            'urgency': request.form.get('urgency', '').strip(),
            'published_at': request.form.get('published_at', '').strip(),
        })

        if not form_values['title'] or not form_values['content']:
            message = 'タイトル/件名と内容は必須です。'
            message_type = 'error'
        else:
            instruction.update({
                'title': form_values['title'],
                'recipient_department': form_values['recipient_department'],
                'recipient_person': form_values['recipient_person'],
                'priority': form_values['priority'],
                'deadline': form_values['deadline'],
                'content': form_values['content'],
                'report_method': form_values['report_method'],
                'completion_condition': form_values['completion_condition'],
                'notes': form_values['notes'],
                'area': form_values['area'],
                'urgency': form_values['urgency'],
                'published_at': form_values['published_at'],
                'updated_at': get_japan_time(),
            })
            if instruction.get('kind') == 'resident':
                instruction['target'] = '住民'
            else:
                instruction['target'] = form_values['recipient_department'] or '防災課'
            save_instructions()
            return redirect(url_for('board'))

    return render_template('board_form.html', form_values=form_values, mode='edit', instruction=instruction, message=message, message_type=message_type)

# 検索結果ページ：templates/search_results.html を返す
@app.route('/search_results')
def search_results():
    sort_key = request.args.get('sort', 'distance_asc')
    query = request.args.get('q', '')
    crowd = request.args.get('crowd', '')
    distance = request.args.get('distance', '')
    support = request.args.get('support', '')
    results = get_search_results_items(
        filter_shelters(request.args.get('district')),
        query=query,
        sort_key=sort_key,
        crowd=crowd,
        distance=distance,
        support=support,
    )
    return render_template(
        'search_results.html',
        results=results,
        sort_key=sort_key,
        query=query,
        crowd=crowd,
        distance=distance,
        support=support,
    )

# JSON API：/shelters?district=地区名
@app.route('/shelters', methods=['GET'])
def get_shelters():
    results = filter_shelters(request.args.get('district'))

    if not results:
        # 見つからなければエラー JSON を返す
        return jsonify({'error': 'No shelters found'}), 404

    # 見つかったらリストを JSON で返す
    return jsonify(results)

# 気象警報・注意報API
@app.route('/api/weather_warnings')
def api_weather_warnings():
    """気象警報・注意報をJSON形式で返すAPI"""
    return jsonify(get_weather_warnings())

if __name__ == '__main__':
    app.run(debug=True, port=5000)
