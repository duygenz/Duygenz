import feedparser
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify
from flask_cors import CORS
import concurrent.futures

# Khởi tạo Flask App
app = Flask(__name__)
# Cho phép CORS cho tất cả các domain
CORS(app)
# Thêm route cho trang chủ
@app.route('/')
def home():
    return "<h1>Chào mừng đến với API Tin tức Việt Nam!</h1><p>Vui lòng truy cập endpoint <b>/news</b> để lấy dữ liệu.</p>"

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

# Hàm để chia nội dung thành các chunks
def create_chunks(text, chunk_size=1000):
    """Chia một đoạn text dài thành các chunks có kích thước xác định."""
    chunks = []
    current_pos = 0
    while current_pos < len(text):
        chunks.append(text[current_pos:current_pos + chunk_size])
        current_pos += chunk_size
    return chunks

# Hàm lấy nội dung đầy đủ của bài báo từ URL
def get_full_article_content(url):
    """Lấy và làm sạch nội dung text từ URL bài báo."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Ném lỗi nếu request không thành công
        soup = BeautifulSoup(response.content, 'html.parser')

        # Xóa các thẻ không cần thiết (script, style)
        for script_or_style in soup(['script', 'style']):
            script_or_style.decompose()

        # Lấy text và làm sạch
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        return text
    except requests.RequestException as e:
        print(f"Lỗi khi lấy nội dung từ {url}: {e}")
        return "" # Trả về chuỗi rỗng nếu có lỗi

# Hàm xử lý một RSS feed
def parse_feed(feed_url):
    """Phân tích một RSS feed và trả về danh sách các bài báo đã được xử lý."""
    news_feed = feedparser.parse(feed_url)
    articles = []
    for entry in news_feed.entries:
        full_content = get_full_article_content(entry.link)
        article_data = {
            'title': entry.title,
            'link': entry.link,
            'published': entry.get('published', 'N/A'),
            'summary': entry.summary,
            'source': news_feed.feed.title,
            'full_content_chunks': create_chunks(full_content, chunk_size=1500) # Chia nội dung đầy đủ thành chunks
        }
        articles.append(article_data)
    return articles

# Định nghĩa API endpoint
@app.route('/news', methods=['GET'])
def get_news():
    """Endpoint chính để lấy tin tức từ tất cả các nguồn RSS."""
    all_articles = []
    # Sử dụng ThreadPoolExecutor để xử lý các request song song, tăng tốc độ
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        # Gửi các task parse_feed cho mỗi URL
        future_to_url = {executor.submit(parse_feed, url): url for url in RSS_FEEDS}
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                articles_from_feed = future.result()
                all_articles.extend(articles_from_feed)
            except Exception as exc:
                url = future_to_url[future]
                print(f'{url} đã tạo ra một exception: {exc}')

    # Sắp xếp bài báo theo ngày xuất bản (nếu có)
    # Lưu ý: Cần xử lý định dạng ngày tháng nếu muốn sắp xếp chính xác
    # all_articles.sort(key=lambda x: x['published'], reverse=True)

    return jsonify(all_articles)

# Chạy app (chỉ khi chạy trực tiếp file này)
if __name__ == '__main__':
    app.run(debug=True, port=5001)
