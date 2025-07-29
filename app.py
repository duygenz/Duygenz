import feedparser
import nltk
from flask import Flask, jsonify
import re

# Initialize the Flask application
app = Flask(__name__)

# --- NLTK setup for sentence tokenization ---
# This ensures the 'punkt' tokenizer is available, downloading it if necessary.
# This is crucial for deployment environments like Render.
try:
    nltk.data.find('tokenizers/punkt')
except nltk.downloader.DownloadError:
    print("Downloading 'punkt' model for NLTK sentence tokenization...")
    nltk.download('punkt', quiet=True)
    print("'punkt' model downloaded.")

# --- List of RSS Feeds ---
RSS_FEEDS = [
    'https://cafef.vn/thi-truong-chung-khoan.rss',
    'https://vneconomy.vn/chung-khoan.rss',
    'https://vneconomy.vn/tai-chinh.rss',
    'https://vneconomy.vn/thi-truong.rss',
    'https://vneconomy.vn/nhip-cau-doanh-nghiep.rss',
    'https://vneconomy.vn/tin-moi.rss',
    'https://vietstock.vn/830/chung-khoan/co-phieu.rss',
    'https://vietstock.vn/145/chung-khoan/y-kien-chuyen-gia.rss',
    'https://vietstock.vn/737/doanh-nghiep/hoat-dong-kinh-doanh.rss',
    'https://vietstock.vn/582/nhan-dinh-phan-tich/phan-tich-co-ban.rss',
    'https://vietstock.vn/585/nhan-dinh-phan-tich/phan-tich-ky-thuat.rss',
    'https://vietstock.vn/1636/nhan-dinh-phan-tich/nhan-dinh-thi-truong.rss',
    'https://cafebiz.vn/rss/cau-chuyen-kinh-doanh.rss'
]

def clean_html(raw_html):
    """
    A simple function to remove HTML tags and extra whitespace.
    """
    clean_text = re.sub('<.*?>', '', raw_html)
    clean_text = ' '.join(clean_text.split())
    return clean_text

def chunk_content(text):
    """
    Splits a block of text into a list of sentences (chunks).
    This provides the small, precise chunks you requested.
    """
    if not text:
        return []
    return nltk.sent_tokenize(text)

@app.route('/news', methods=['GET'])
def get_bulk_news():
    """
    API endpoint to fetch, process, and return news from all RSS feeds.
    """
    all_news_items = []
    for feed_url in RSS_FEEDS:
        try:
            # Parse the feed content
            feed = feedparser.parse(feed_url)
            source_name = feed.feed.get('title', 'Unknown Source')

            for entry in feed.entries:
                # The main content is usually in 'summary' or 'description'
                full_content_html = entry.get('summary', entry.get('description', ''))
                
                # Clean the HTML to get plain text
                full_content_text = clean_html(full_content_html)

                # Create the small, precise chunks from the plain text
                content_chunks = chunk_content(full_content_text)

                news_item = {
                    'source': source_name,
                    'title': entry.get('title', 'No Title'),
                    'link': entry.get('link', ''),
                    'published': entry.get('published', 'No Date'),
                    'full_context': full_content_text,
                    'chunks': content_chunks
                }
                all_news_items.append(news_item)
        except Exception as e:
            # Log errors for individual feeds but don't stop the whole process
            print(f"Error processing feed {feed_url}: {e}")

    return jsonify(all_news_items)

# This allows running the app locally for testing
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

