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
def create_chunks(text, chunk_size=1500):
    """Chia một đoạn text dài thành các chunks có kích thước xác định."""
    if not isinstance(text, str):
        return []
    chunks = []
    current_pos = 0
    while current_pos < len(text):
        chunks.append(text[current_pos:current_pos + chunk_size])
        current_pos += chunk_size
    return chunks

# Hàm lấy nội dung đầy đủ của bài báo từ URL (đã tối ưu)
def get_full_article_content(url):
    """Lấy và làm sạch nội dung text từ URL bài báo."""
    try:
        # Thêm headers để giả lập trình duyệt, tránh bị chặn
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # Thêm headers và đặt timeout cho request
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()  # Ném lỗi nếu request không thành công (vd: 404, 500)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Xóa các thẻ không cần thiết (script, style, nav, footer)
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()

        # Lấy text và làm sạch
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        return text
    except requests.RequestException as e:
        print(f"Lỗi khi lấy nội dung từ {url}: {e}")
        return f"Không thể lấy nội dung từ {url}. Lỗi: {e}"

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
            'full_content_chunks': create_chunks(full_content)
        }
        articles.append(article_data)
    return articles

# Route cho trang chủ, giúp kiểm tra API có "sống" hay không
@app.route('/')
def home():
    """Route trang chủ để kiểm tra tình trạng API."""
    return "<h1>API Tin tức đang hoạt động!</h1><p>Truy cập <b>/news</b> để lấy dữ liệu.</p>"

# Định nghĩa API endpoint chính
@app.route('/news', methods=['GET'])
def get_news():
    """Endpoint chính để lấy tin tức từ tất cả các nguồn RSS."""
    all_articles = []
    # Giảm số worker để tránh lỗi hết RAM trên Render Free
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_url = {executor.submit(parse_feed, url): url for url in RSS_FEEDS}
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                articles_from_feed = future.result()
                all_articles.extend(articles_from_feed)
            except Exception as exc:
                url = future_to_url[future]
                print(f'{url} đã tạo ra một exception: {exc}')

    return jsonify(all_articles)

# Chạy app
if __name__ == '__main__':
    # Port 10000 thường được Render khuyến khích
    app.run(host='0.0.0.0', port=10000)

