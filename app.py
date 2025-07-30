import feedparser
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify
from flask_cors import CORS
from sentence_transformers import SentenceTransformer
from threading import Thread, Lock
import time

# Khởi tạo Flask App và CORS
app = Flask(__name__)
CORS(app) # Cho phép Cross-Origin Resource Sharing

# Danh sách các nguồn RSS
RSS_FEEDS = [
    'https://cafef.vn/thi-truong-chung-khoan.rss',
    'https://vneconomy.vn/chung-khoan.rss',
    'https://vneconomy.vn/tai-chinh.rss',
    'https://vneconomy.vn/thi-truong.rss',
    'https://vneconomy.vn/nhip-cau-doanh-nghiep.rss',
    'https://vneconomy.vn/tin-moi.rss',
    'https://cafebiz.vn/rss/cau-chuyen-kinh-doanh.rss'
]

# Tải mô hình sentence-transformer (nhẹ, phù hợp với Render free tier)
# Mô hình này sẽ được tải một lần khi ứng dụng khởi động
model = SentenceTransformer('all-MiniLM-L6-v2')

# Biến toàn cục để lưu trữ tin tức và vector
# Sử dụng lock để đảm bảo an toàn khi cập nhật từ background thread
news_data_store = []
data_lock = Lock()

def get_full_content(url):
    """
    Hàm lấy nội dung đầy đủ của bài viết từ URL.
    Sử dụng BeautifulSoup để phân tích HTML.
    Lưu ý: Cấu trúc HTML của mỗi trang có thể khác nhau, cần tùy chỉnh selector.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Thử các selectors phổ biến cho nội dung bài viết
        # Đây là phần cần tùy chỉnh nhất cho từng trang báo
        content_selectors = [
            'div.detail-content',    # VnEconomy
            'div.content-detail',    # CafeF / CafeBiz
            'article',
            'div.post-content'
        ]
        
        content_div = None
        for selector in content_selectors:
            content_div = soup.select_one(selector)
            if content_div:
                break
        
        if content_div:
            # Loại bỏ các thẻ không cần thiết như script, style
            for tag in content_div(['script', 'style']):
                tag.decompose()
            return content_div.get_text(separator=' ', strip=True)
        return None
    except requests.RequestException as e:
        print(f"Lỗi khi lấy nội dung từ {url}: {e}")
        return None

def fetch_and_process_feeds():
    """
    Lấy tin từ RSS, xử lý và tạo vector.
    """
    global news_data_store
    temp_news_list = []
    
    print("Bắt đầu quá trình lấy và xử lý tin tức...")

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                # Lấy nội dung đầy đủ
                full_context = get_full_content(entry.link)
                
                # Nếu không lấy được full_context, dùng summary từ RSS
                if not full_context:
                    full_context = BeautifulSoup(entry.summary, 'html.parser').get_text(strip=True)

                # Chỉ xử lý nếu có nội dung
                if full_context:
                    news_item = {
                        'title': entry.title,
                        'link': entry.link,
                        'summary': BeautifulSoup(entry.summary, 'html.parser').get_text(strip=True),
                        'published': entry.get('published', 'N/A'),
                        'source': feed.feed.title
                    }
                    
                    # Tạo vector từ nội dung đầy đủ
                    vector = model.encode(full_context, convert_to_tensor=False).tolist()
                    news_item['vector'] = vector
                    
                    temp_news_list.append(news_item)
            
            print(f"Đã xử lý xong: {feed_url}")

        except Exception as e:
            print(f"Lỗi khi xử lý feed {feed_url}: {e}")

    # Cập nhật data store một cách an toàn
    with data_lock:
        news_data_store = temp_news_list
    
    print(f"Hoàn tất! Đã cập nhật {len(temp_news_list)} tin tức.")


def background_task():
    """
    Chạy fetch_and_process_feeds trong nền và lặp lại sau một khoảng thời gian.
    """
    while True:
        fetch_and_process_feeds()
        # Chờ 30 phút (1800 giây) trước khi cập nhật lại
        time.sleep(1800)

@app.route('/api/news', methods=['GET'])
def get_news():
    """
    Endpoint chính để trả về danh sách tin tức đã được xử lý.
    """
    with data_lock:
        # Trả về một bản sao của dữ liệu để tránh race condition
        response_data = list(news_data_store)
    
    return jsonify(response_data)

if __name__ == '__main__':
    # Chạy tác vụ nền để cập nhật tin tức
    # Sử dụng daemon=True để thread tự động kết thúc khi main app tắt
    update_thread = Thread(target=background_task, daemon=True)
    update_thread.start()
    
    # Chạy ứng dụng Flask
    # Render sẽ sử dụng một Gunicorn server, nên phần này chủ yếu cho local testing
    app.run(host='0.0.0.0', port=5000)
