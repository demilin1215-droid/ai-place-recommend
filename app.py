# 匯入所需模組
import os              # 作業系統模組，用於讀取環境變數
import sqlite3         # SQLite 資料庫模組，用於本地資料儲存
import tempfile         # 取得部署環境可寫入的暫存目錄
from functools import wraps
from flask import Flask, render_template, request, redirect, session, url_for  # 從 Flask 套件中匯入會用到的功能
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv  # 載入 .env 環境變數檔案
from recommend_service import get_recommended_place  # 用於計算地理距離
import requests        # 用於發送 HTTP 請求（如呼叫 Google Maps API）

# 載入 .env 檔案中的環境變數（如 GOOGLE_MAPS_API_KEY、GOOGLE_GEOCODING_API_KEY）
load_dotenv()

# 建立 Flask 應用程式
# __name__ 會被設為 "__main__"，表示直接執行此檔案
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")

oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)
DB_INITIALIZED = False

# 資料庫檔案名稱；Vercel 的專案目錄不可持久寫入，所以 SQLite 只適合本機備用
DB_NAME = os.path.join(tempfile.gettempdir(), "places.db") if os.getenv("VERCEL") else "places.db"

# 初始分類資料
# 只有在 place_categories 是空表時，才會自動匯入這些預設分類
DEFAULT_CATEGORIES = [
    ("cafe", "咖啡廳", 1),
    ("brunch", "早午餐", 2),
    ("dessert", "甜點店", 3),
    ("bistro", "餐酒館", 4),
    ("snack", "小吃店", 5),
    ("restaurant", "餐廳", 6),
    ("bar", "酒吧", 7),
    ("attraction", "景點", 8),
    ("exhibition", "展覽", 9),
    ("shop", "選物店", 10),
    ("stationery", "文具店", 11),
    ("toy", "玩具店", 12),
    ("flower", "花店", 13),
]

#建立資料庫連線
#回傳一個連線物件，後續可用於執行 SQL 語句
def get_db_connection():
    if USE_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            connect_timeout=10,
            prepare_threshold=None,
        )

    conn = sqlite3.connect(DB_NAME)
    #設定 row_factory 為 sqlite3.Row，讓查詢結果可以用欄位名稱存取（如 row['place_name']）
    conn.row_factory = sqlite3.Row
    return conn


def db_param():
    return "%s" if USE_POSTGRES else "?"


def category_labels_sql():
    if USE_POSTGRES:
        return "STRING_AGG(pc.category_label, '、' ORDER BY pc.sort_order) AS category"
    return "GROUP_CONCAT(pc.category_label, '、') AS category"


def should_auto_init_db():
    return not USE_POSTGRES


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.url))
        return view_func(*args, **kwargs)

    return wrapped_view


def safe_next_url(next_url):
    if not next_url:
        return url_for("index")

    if next_url.startswith("/") or next_url.startswith(request.host_url):
        return next_url

    return url_for("index")


@app.before_request
def ensure_db_initialized():
    global DB_INITIALIZED

    if request.endpoint in ("health", "static"):
        return

    if should_auto_init_db() and not DB_INITIALIZED:
        init_db()
        DB_INITIALIZED = True

#初始化資料庫，建立表格
#此函式會在程式啟動時執行，確保資料表存在
def init_db():
    conn = get_db_connection()

    # 建立使用者資料表
    if USE_POSTGRES:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                google_sub TEXT NOT NULL UNIQUE,
                email TEXT,
                name TEXT,
                picture TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                google_sub TEXT NOT NULL UNIQUE,
                email TEXT,
                name TEXT,
                picture TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # 建立收藏地點資料表
    if USE_POSTGRES:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS favorite_places (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                place_name TEXT NOT NULL,
                address TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                google_place_id TEXT NOT NULL,
                category TEXT,
                note TEXT,
                visited INTEGER DEFAULT 0,
                revisit_rating INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS favorite_places (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 主鍵，自動遞增
                user_id INTEGER,                       -- 所屬使用者 ID
                place_name TEXT NOT NULL,            -- 地點名稱（必填）
                address TEXT,                         -- 地址
                latitude REAL,                        -- 緯度
                longitude REAL,                       -- 經度
                google_place_id TEXT NOT NULL,        -- Google Places API 的地點 ID
                category TEXT,                         -- 分類（如餐廳、景點、住宿）
                note TEXT,                             -- 備註
                visited INTEGER DEFAULT 0,            -- 是否已訪問（0=否，1=是）
                revisit_rating INTEGER DEFAULT 0,  -- 再訪意願評分（0-5）
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 建立時間
            )
        """)

    if USE_POSTGRES:
        conn.execute("ALTER TABLE favorite_places ADD COLUMN IF NOT EXISTS user_id INTEGER")
    else:
        favorite_columns = conn.execute("PRAGMA table_info(favorite_places)").fetchall()
        if "user_id" not in [column["name"] for column in favorite_columns]:
            conn.execute("ALTER TABLE favorite_places ADD COLUMN user_id INTEGER")

    # 建立分類對照表
    if USE_POSTGRES:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS place_categories (
                id SERIAL PRIMARY KEY,
                category_value TEXT NOT NULL UNIQUE,
                category_label TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        """)
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS place_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_value TEXT NOT NULL UNIQUE,
                category_label TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )        
        """)

    # 將預設分類寫入分類對照表
    if USE_POSTGRES:
        for category in DEFAULT_CATEGORIES:
            conn.execute("""
                INSERT INTO place_categories (
                    category_value,
                    category_label,
                    sort_order
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (category_value) DO NOTHING
            """, category)
    else:
        conn.executemany("""
            INSERT OR IGNORE INTO place_categories (
                category_value,
                category_label,
                sort_order
            )
            VALUES (?, ?, ?)
        """, DEFAULT_CATEGORIES)

    conn.commit()   # 提交交易，確保 SQL 語句執行
    conn.close()    # 關閉連線，釋放資源

def get_active_categories():
    conn = get_db_connection()
    categories = conn.execute("""
        SELECT category_value, category_label
        FROM place_categories
        WHERE is_active = 1
        ORDER BY sort_order
    """).fetchall()
    conn.close()
    return categories


def get_category_label(category_value):
    if not category_value:
        return None

    conn = get_db_connection()
    category = conn.execute(
        f"""
        SELECT category_label
        FROM place_categories
        WHERE category_value = {db_param()}
        """,
        (category_value,)
    ).fetchone()
    conn.close()

    return category["category_label"] if category else None


def get_or_create_user(user_info):
    google_sub = user_info.get("sub")
    email = user_info.get("email")
    name = user_info.get("name")
    picture = user_info.get("picture")

    conn = get_db_connection()
    user = conn.execute(
        f"""
        SELECT id, google_sub, email, name, picture
        FROM users
        WHERE google_sub = {db_param()}
        """,
        (google_sub,)
    ).fetchone()

    if user:
        conn.execute(
            f"""
            UPDATE users
            SET email = {db_param()},
                name = {db_param()},
                picture = {db_param()}
            WHERE id = {db_param()}
            """,
            (email, name, picture, user["id"])
        )
        conn.commit()
        user_id = user["id"]
    else:
        cursor = conn.execute(
            f"""
            INSERT INTO users (
                google_sub,
                email,
                name,
                picture
            )
            VALUES ({", ".join([db_param()] * 4)})
            RETURNING id
            """,
            (google_sub, email, name, picture)
        ) if USE_POSTGRES else conn.execute(
            f"""
            INSERT INTO users (
                google_sub,
                email,
                name,
                picture
            )
            VALUES ({", ".join([db_param()] * 4)})
            """,
            (google_sub, email, name, picture)
        )
        user_id = cursor.fetchone()["id"] if USE_POSTGRES else cursor.lastrowid
        conn.commit()

    conn.close()

    return {
        "id": user_id,
        "name": name,
        "email": email,
        "picture": picture,
    }


#根路由：當使用者訪問 http://127.0.0.1:5000/ 時觸發
#render_template用來顯示 HTML 頁面
#redirect直接重新導向到另一個網址或頁面
#url_for用來根據「函式名稱」產生網址
##首頁，顯示最近收藏的 3 個地點
@app.route("/health")
def health():
    return {"status": "ok", "database": "postgres" if USE_POSTGRES else "sqlite"}


@app.route("/login")
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
        return "Google OAuth 尚未設定，請先設定 GOOGLE_CLIENT_ID 與 GOOGLE_CLIENT_SECRET。", 500

    session["next_url"] = safe_next_url(request.args.get("next"))
    redirect_uri = url_for("auth_google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route("/auth/google/callback")
def auth_google_callback():
    token = google.authorize_access_token()
    user_info = token.get("userinfo")

    if not user_info:
        user_info = google.userinfo(token=token)

    if not user_info or not user_info.get("sub"):
        return redirect(url_for("index"))

    user = get_or_create_user(user_info)
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]

    return redirect(session.pop("next_url", url_for("index")))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/")
def index():
    recent_favorites = []

    if session.get("user_id"):
        conn = get_db_connection()

        recent_favorites = conn.execute(f"""
            SELECT
                place_name,
                address,
                latitude,
                longitude,
                google_place_id,
                note,
                visited,
                {category_labels_sql()},
                MAX(fp.created_at) AS created_at
            FROM favorite_places fp
            LEFT JOIN place_categories pc ON fp.category = pc.category_value
            WHERE fp.user_id = {db_param()}
            GROUP BY
                fp.google_place_id,
                fp.place_name,
                fp.address,
                fp.latitude,
                fp.longitude,
                fp.note,
                fp.visited
            ORDER BY created_at DESC
            LIMIT 3
        """, (session["user_id"],)).fetchall()

        conn.close()
    
    categories = get_active_categories()

    return render_template(
        "index.html",
        recent_favorites=recent_favorites,
        categories=categories
    )

#使用 Google Maps Geocoding API 將地址轉換成經緯度
def geocode_location(location):
    api_key = os.getenv("GOOGLE_GEOCODING_API_KEY")

    location = (location or "").strip()

    if not api_key or not location:
        return None, None

    url = "https://maps.googleapis.com/maps/api/geocode/json"

    params = {
        "address": location,
        "key": api_key,
        "language": "zh-TW",
        "region": "tw" #限定搜尋結果在台灣，提升地址解析的準確度
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return None, None

    if data.get("status") != "OK" or not data.get("results"):
        return None, None

    geometry = data["results"][0]["geometry"]["location"]

    return geometry["lat"], geometry["lng"]

#推薦頁
@app.route("/recommend")
@login_required
def recommend():
    location = (request.args.get("location") or "").strip()
    user_lat = (request.args.get("lat") or "").strip()
    user_lng = (request.args.get("lng") or "").strip()
    category = request.args.get("category")
    category_label = get_category_label(category)

    # 如果使用者是手動輸入所在地，就用 Google Geocoding API 轉成經緯度
    if location and (not user_lat or not user_lng):
        user_lat, user_lng = geocode_location(location)

        if not user_lat or not user_lng:
            return render_template(
                "recommend.html",
                recommended_place=None,
                location=location,
                lat=user_lat,
                lng=user_lng,
                category=category,
                category_label=category_label,
                message="無法解析輸入的所在地，請確認地址是否正確，或改用目前位置定位。"
            )

    # 檢查必要資料
    if not category:
        return render_template(
            "recommend.html",
            recommended_place=None,
            location=location,
            lat=user_lat,
            lng=user_lng,
            category=category,
            category_label=category_label,
            message="請先選擇想去的地點分類。"
        )

    if not user_lat or not user_lng:
        
        return render_template(
            "recommend.html",
            recommended_place=None,
            location=location,
            lat=user_lat,
            lng=user_lng,
            category=category,
            category_label=category_label,
            message="無法取得目前位置，請重新定位或輸入所在地。"
        )

    conn = get_db_connection()

	# 依照使用者指定的分類篩選收藏地點
    places = conn.execute(
        f"""
        SELECT fp.*, pc.category_label
        FROM favorite_places fp
        LEFT JOIN place_categories pc ON fp.category = pc.category_value
        WHERE fp.category = {db_param()}
          AND fp.user_id = {db_param()}
        """,
        (category, session["user_id"])
    ).fetchall()

    conn.close()

	# 如果沒有符合分類的收藏地點
    if not places:
        return render_template(
            "recommend.html",
            recommended_place=None,
            location=location,
            lat=user_lat,
            lng=user_lng,
            category=category,
            category_label=category_label,
            message=f"目前沒有收藏「{category_label or '這個分類'}」類型的地點。"
        )

	# 呼叫 recommend_service.py 裡面的推薦邏
    recommended_place = get_recommended_place(
        places,
        user_lat,
        user_lng
    )

	# 如果所有地點都沒有經緯度
    if recommended_place is None:
        return render_template(
            "recommend.html",
            recommended_place=None,
            location=location,
            lat=user_lat,
            lng=user_lng,
            category=category,
            category_label=category_label,
            message="目前沒有可用的地點經緯度資料。"
        )

    return render_template(
        "recommend.html",
        recommended_place=recommended_place,
        location=location,
        lat=user_lat,
        lng=user_lng,
        category=category,
        category_label=category_label,
        message=None
    )

#收藏頁
#request取得使用者送出的資料，例如表單輸入、GET/POST 參數
#- GET: 顯示所有已收藏的地點列表
#- POST: 接收表單資料，新增地點到資料庫
@app.route("/favorites", methods=["GET", "POST"])
@login_required
def favorites():
    #檢查請求方法，若為 POST 表示要新增地點  
    if request.method == "POST":
        #從表單取得各欄位資料
        place_name = request.form.get("place_name")
        address = request.form.get("address")
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        google_place_id = request.form.get("google_place_id")
        #category = request.form.get("category")
        categories = request.form.getlist("category")  #取得多選的分類，會回傳一個列表
        note = request.form.get("note")
        visited = int(request.form.get("visited", 0))
        revisit_rating = int(request.form.get("revisit_rating", 0)) if visited else 0

        #連線資料庫並執行 INSERT 語句
        conn = get_db_connection()
        for category in categories:
            conn.execute(f"""
                INSERT INTO favorite_places (
                    place_name,
                    address,
                    latitude,
                    longitude,
                    google_place_id,
                    user_id,
                    category,
                    note,
                    visited,
                    revisit_rating
                )
                VALUES ({", ".join([db_param()] * 10)})
            """, (
                place_name,
                address,
                latitude,
                longitude,
                google_place_id,
                session["user_id"],
                category,
                note,
                visited,
                revisit_rating
            ))
        conn.commit()   # 提交交易
        conn.close()    # 關閉連線

        #新增完成後，重新導向回收藏頁面（防止重複提交）
        return redirect(url_for("favorites"))

    #若為 GET 請求，則查詢所有收藏地點
    conn = get_db_connection()
    places = conn.execute(f"""
        SELECT
            place_name,
            address,
            latitude,
            longitude,
            google_place_id,
            note,
            visited,
            {category_labels_sql()},
            MAX(fp.created_at) AS created_at
        FROM favorite_places fp
        LEFT JOIN place_categories pc ON fp.category = pc.category_value
        WHERE fp.user_id = {db_param()}
        GROUP BY
            google_place_id,
            place_name,
            address,
            latitude,
            longitude,
            note,
            visited
        ORDER BY created_at DESC   -- 最新新增的排在前面
    """, (session["user_id"],)).fetchall()
    conn.close()

    categories = get_active_categories()

    #從環境變數取得 Google Maps API Key（用於地圖顯示）
    google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")

    #渲染 HTML 模板並傳遞資料給前端
    return render_template(
        "favorites.html",
        places=places,
        categories=categories,
        google_maps_api_key=google_maps_api_key
    )


@app.route("/favorites/<path:google_place_id>/edit", methods=["GET", "POST"])
@login_required
def edit_favorite(google_place_id):
    conn = get_db_connection()

    if request.method == "POST":
        place_name = request.form.get("place_name")
        address = request.form.get("address")
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        categories = request.form.getlist("category")
        note = request.form.get("note")
        visited = int(request.form.get("visited", 0))
        revisit_rating = int(request.form.get("revisit_rating", 0)) if visited else 0

        existing_place = conn.execute(
            f"""
            SELECT created_at
            FROM favorite_places
            WHERE google_place_id = {db_param()}
              AND user_id = {db_param()}
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (google_place_id, session["user_id"])
        ).fetchone()

        if not existing_place:
            conn.close()
            return redirect(url_for("favorites"))

        created_at = existing_place["created_at"]

        conn.execute(
            f"""
            DELETE FROM favorite_places
            WHERE google_place_id = {db_param()}
              AND user_id = {db_param()}
            """,
            (google_place_id, session["user_id"])
        )

        for category in categories:
            conn.execute(f"""
                INSERT INTO favorite_places (
                    place_name,
                    address,
                    latitude,
                    longitude,
                    google_place_id,
                    user_id,
                    category,
                    note,
                    visited,
                    revisit_rating,
                    created_at
                )
                VALUES ({", ".join([db_param()] * 11)})
            """, (
                place_name,
                address,
                latitude,
                longitude,
                google_place_id,
                session["user_id"],
                category,
                note,
                visited,
                revisit_rating,
                created_at
            ))

        conn.commit()
        conn.close()
        return redirect(url_for("favorites"))

    place = conn.execute(
        f"""
        SELECT
            place_name,
            address,
            latitude,
            longitude,
            google_place_id,
            note,
            visited,
            revisit_rating,
            MAX(created_at) AS created_at
        FROM favorite_places
        WHERE google_place_id = {db_param()}
          AND user_id = {db_param()}
        GROUP BY
            google_place_id,
            place_name,
            address,
            latitude,
            longitude,
            note,
            visited,
            revisit_rating
        """,
        (google_place_id, session["user_id"])
    ).fetchone()

    if not place:
        conn.close()
        return redirect(url_for("favorites"))

    selected_rows = conn.execute(
        f"""
        SELECT category
        FROM favorite_places
        WHERE google_place_id = {db_param()}
          AND user_id = {db_param()}
        """,
        (google_place_id, session["user_id"])
    ).fetchall()

    conn.close()

    selected_categories = [row["category"] for row in selected_rows]
    categories = get_active_categories()

    return render_template(
        "edit_favorite.html",
        place=place,
        categories=categories,
        selected_categories=selected_categories
    )


@app.route("/favorites/<path:google_place_id>/delete", methods=["POST"])
@login_required
def delete_favorite(google_place_id):
    conn = get_db_connection()
    conn.execute(
        f"""
        DELETE FROM favorite_places
        WHERE google_place_id = {db_param()}
          AND user_id = {db_param()}
        """,
        (google_place_id, session["user_id"])
    )
    conn.commit()
    conn.close()
    return redirect(url_for("favorites"))

#程式入口點
#當直接執行此檔案（而非匯入模組）時才會執行
if __name__ == "__main__":
    #app.run(debug=True)   # 啟動 Flask 伺服器（debug=True 開啟除錯模式）
    app.run(debug=False)
