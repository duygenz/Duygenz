import feedparser
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sentence_transformers import SentenceTransformer
import torch

# ==============================================================================
# KHỞI TẠO VÀ CẤU HÌNH
# ==============================================================================

# Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="News API with Vector Embeddings",
    description="API để lấy tin tức từ nhiều nguồn RSS và tạo vector embedding cho nội dung.",
    version="1.0.0",
)

# Cấu hình CORS: Cho phép tất cả các nguồn gốc (origins) truy cập API.
# Trong môi trường production thực tế, bạn nên giới hạn lại chỉ những domain cần thiết.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Danh sách các RSS feed cần lấy tin
RSS_FEEDS = [
    "https://cafef.vn/thi-truong-chung-khoan.rss",
    "https://vneconomy.vn/chung-khoan.rss",
    "https://vneconomy.vn/tai-chinh.rss",
    "https://vneconomy.vn/thi-truong.rss",
    "https://vneconomy.vn/nhip-cau-doanh-nghiep.rss",
    "https://vneconomy.vn/tin-moi.rss",
    "https://cafebiz.vn/rss/cau-chuyen-kinh-doanh.rss",
]

# Biến toàn cục để lưu trữ dữ liệu tin tức và mô hình
# Cách này giúp mô hình chỉ cần tải 1 lần khi server khởi động, tiết kiệm bộ nhớ và thời gian.
news_cache = []
try:
    # Tải mô hình sentence-transformer. 'all-MiniLM-L6-v2' nhỏ gọn và hiệu quả.
    # Chiếm khoảng 90MB RAM.
    print("Initializing model... This may take a moment.")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    print("Model loaded successfully.")
except Exception as e:
    print(f"Error loading model: {e}")
    model = None

# ==============================================================================
# CÁC HÀM XỬ LÝ LOGIC
# ==============================================================================

def get_full_content(url: str) -> str:
    """
    Truy cập URL của bài báo và trích xuất nội dung văn bản chính.
    """
    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Xóa các thẻ không cần thiết
        for tag in soup(['script', 'style', 'header', 'footer', 'nav', 'aside']):
            tag.decompose()

        # Lấy văn bản từ thẻ body và làm sạch
        body_text = soup.body.get_text(separator=' ', strip=True)
        return ' '.join(body_text.split()) # Chuẩn hóa khoảng trắng
    except Exception as e:
        print(f"Could not fetch or parse content from {url}. Error: {e}")
        return "" # Trả về chuỗi rỗng nếu có lỗi

def process_feeds():
    """
    Xử lý tất cả các RSS feed: lấy tin, trích xuất nội dung và tạo vector.
    """
    global news_cache
    processed_articles = []

    if not model:
        print("Model is not available. Skipping feed processing.")
        return

    print(f"Processing {len(RSS_FEEDS)} RSS feeds...")
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                # Lấy nội dung đầy đủ từ link bài viết
                full_content = get_full_content(entry.link)
                
                # Chỉ xử lý nếu có nội dung
                if full_content:
                    article = {
                        "title": entry.title,
                        "link": entry.link,
                        "published": entry.get("published", "N/A"),
                        "summary": entry.summary,
                        "full_content": full_content,
                    }
                    processed_articles.append(article)
        except Exception as e:
            print(f"Error processing feed {feed_url}: {e}")
            continue

    print(f"Found {len(processed_articles)} articles. Generating vectors...")
    
    # Tạo vector hàng loạt (bulk embedding) - hiệu quả hơn tạo từng cái một
    all_contents = [article['full_content'] for article in processed_articles]
    if all_contents:
        vectors = model.encode(all_contents, convert_to_tensor=False, show_progress_bar=True)
        # Gán vector vào từng bài viết
        for i, article in enumerate(processed_articles):
            article['vector'] = vectors[i].tolist() # Chuyển numpy array thành list để dễ serialize JSON
            del article['full_content'] # Xóa nội dung đầy đủ để giảm dung lượng response

    news_cache = processed_articles
    print("Feed processing and vector generation complete.")
    print(f"Total articles in cache: {len(news_cache)}")

# ==============================================================================
# SỰ KIỆN KHỞI ĐỘNG VÀ ENDPOINTS
# ==============================================================================

@app.on_event("startup")
def startup_event():
    """
    Hàm này được gọi một lần khi ứng dụng FastAPI khởi động.
    Chúng ta sẽ xử lý tin tức ở đây.
    """
    print("Application startup: Processing initial feeds.")
    process_feeds()

@app.get("/", summary="Root Endpoint", description="Hiển thị thông báo chào mừng.")
def read_root():
    return {"message": "Welcome to the News API. Access /news to get articles."}

@app.get("/news", summary="Get All News", description="Lấy tất cả tin tức đã được xử lý cùng với vector.")
def get_news():
    """
    Trả về danh sách tất cả các bài báo đã được xử lý từ cache.
    Dữ liệu được làm mới khi server khởi động.
    """
    if not news_cache:
        # Nếu cache rỗng, có thể do lỗi lúc khởi động. Thử xử lý lại.
        print("News cache is empty. Attempting to re-process feeds.")
        process_feeds()
        if not news_cache:
             raise HTTPException(status_code=503, detail="News service is temporarily unavailable. Please try again later.")
    
    return {"count": len(news_cache), "articles": news_cache}

@app.post("/refresh", summary="Refresh News Feeds", description="Kích hoạt việc làm mới dữ liệu từ các RSS feed.")
def refresh_news():
    """
    Endpoint này cho phép bạn kích hoạt việc làm mới dữ liệu một cách thủ công.
    """
    print("Manual refresh triggered.")
    process_feeds()
    return {"message": "News feed refresh initiated.", "articles_found": len(news_cache)}

