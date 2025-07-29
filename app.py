import feedparser
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
CORS(app)

# Danh sách các nguồn cấp RSS
RSS_FEEDS = [
    'https://cafef.vn/thi-truong-chung-khoan.rss',
    'https://vneconomy.vn/chung-khoan.rss',
    'https://vneconomy.vn/tai-chinh.rss',
    'https://vneconomy.vn/thi-truong.rss',
    'https://vneconomy.vn/nhip-cau-doanh-nghiep.rss',
    'https://vneconomy.vn/tin-moi.rss',
    'https://cafebiz.vn/rss/cau-chuyen-kinh-doanh.rss'
]

def chunk_text(text, chunk_size=1000):
    """Chia một đoạn văn bản dài thành các đoạn nhỏ hơn."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            # Tìm dấu chấm câu gần nhất để ngắt câu tự nhiên hơn
            last_period = text.rfind('. ', start, end)
            if last_period != -1:
                end = last_period + 1
        chunks.append(text[start:end].strip())
        start = end
    return chunks

def get_full_article_content(url):
    """Lấy và phân tích nội dung đầy đủ của một bài báo từ URL."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Thử các bộ chọn CSS phổ biến cho nội dung bài báo
        # Điều này có thể cần tùy chỉnh cho từng trang web cụ thể
        selectors = [
            'div.main-content', 
            'article', 
            'div.entry-content', 
            'div.post-content',
            'div#main-content',
            'div.content'
        ]
        
        content = None
        for selector in selectors:
            content_element = soup.select_one(selector)
            if content_element:
                content = content_element.get_text(separator='\n', strip=True)
                break
        
        if not content:
            # Nếu không tìm thấy bằng các bộ chọn cụ thể, hãy thử một cách tiếp cận chung hơn
            content = soup.find('body').get_text(separator='\n', strip=True)

        return content if content else "Không thể trích xuất nội dung."

    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi lấy URL {url}: {e}")
        return None
    except Exception as e:
        print(f"Lỗi khi phân tích cú pháp URL {url}: {e}")
        return None

def process_feed(feed_url):
    """Xử lý một nguồn cấp RSS và trả về các mục tin tức."""
    news_feed = feedparser.parse(feed_url)
    news_items = []
    for entry in news_feed.entries:
        full_content = get_full_article_content(entry.link)
        if full_content:
            content_chunks = chunk_text(full_content)
            news_items.append({
                'title': entry.title,
                'link': entry.link,
                'published': entry.get('published', 'Không có ngày xuất bản'),
                'summary': entry.summary,
                'full_content_chunks': content_chunks
            })
    return news_items

@app.route('/news', methods=['GET'])
def get_news():
    """Điểm cuối API để lấy tin tức từ tất cả các nguồn cấp RSS."""
    all_news = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_feed = {executor.submit(process_feed, url): url for url in RSS_FEEDS}
        for future in as_completed(future_to_feed):
            try:
                all_news.extend(future.result())
            except Exception as e:
                print(f"Lỗi khi xử lý nguồn cấp: {e}")

    return jsonify(all_news)

if __name__ == '__main__':
    app.run(debug=True)
