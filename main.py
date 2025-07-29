import asyncio
import re
from typing import List, Dict, Any
from urllib.parse import urljoin

import aiohttp
import feedparser
from bs4 import BeautifulSoup
from cachetools import TTLCache, cached
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# --- Cấu hình ---
# Danh sách các RSS feed đầu vào
RSS_FEEDS = [
    "https://cafef.vn/thi-truong-chung-khoan.rss",
    "https://vneconomy.vn/chung-khoan.rss",
    "https://vneconomy.vn/tai-chinh.rss",
    "https://vneconomy.vn/thi-truong.rss",
    "https://vneconomy.vn/nhip-cau-doanh-nghiep.rss",
    "https://vneconomy.vn/tin-moi.rss",
    "https://vietstock.vn/830/chung-khoan/co-phieu.rss",
    "https://vietstock.vn/145/chung-khoan/y-kien-chuyen-gia.rss",
    "https://vietstock.vn/737/doanh-nghiep/hoat-dong-kinh-doanh.rss",
    "https://vietstock.vn/582/nhan-dinh-phan-tich/phan-tich-co-ban.rss",
    "https://vietstock.vn/585/nhan-dinh-phan-tich/phan-tich-ky-thuat.rss",
    "https://vietstock.vn/1636/nhan-dinh-phan-tich/nhan-dinh-thi-truong.rss",
    "https://cafebiz.vn/rss/cau-chuyen-kinh-doanh.rss",
]

# Cấu hình cache: cache tồn tại trong 300 giây (5 phút)
cache = TTLCache(maxsize=100, ttl=300)

# User-Agent để giả lập trình duyệt
REQUEST_HEADER = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36'
}

# --- Khởi tạo FastAPI App ---
app = FastAPI(
    title="Vietnam Stock News API",
    description="API tổng hợp và bóc tách tin tức tài chính - chứng khoán từ các nguồn RSS uy tín của Việt Nam.",
    version="1.0.0",
)

# --- Định nghĩa Model dữ liệu trả về ---
class NewsChunk(BaseModel):
    chunk_id: int
    text: str

class NewsArticle(BaseModel):
    source: str
    title: str
    link: str
    published: str
    summary: str
    full_text_chunks: List[NewsChunk]

# --- Lõi xử lý ---

async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """Hàm bất đồng bộ để tải nội dung HTML của một URL."""
    try:
        async with session.get(url, headers=REQUEST_HEADER, timeout=15) as response:
            response.raise_for_status()
            return await response.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(f"Error fetching {url}: {e}")
        return ""

def clean_text(text: str) -> str:
    """Dọn dẹp văn bản, loại bỏ khoảng trắng thừa."""
    text = re.sub(r'\s*\n\s*', '\n', text)  # Thay thế nhiều newline bằng một
    text = re.sub(r'[ \t]+', ' ', text)     # Thay thế nhiều khoảng trắng bằng một
    return text.strip()

def extract_content_from_html(html: str, url: str) -> str:
    """
    Bóc tách nội dung chính của bài báo từ HTML.
    Hàm này thử các selector phổ biến của các trang báo.
    """
    soup = BeautifulSoup(html, 'html.parser')
    content = None

    # Các quy tắc bóc tách cho từng trang
    if 'vneconomy.vn' in url:
        content = soup.find('div', class_='detail__content')
    elif 'cafef.vn' in url or 'cafebiz.vn' in url:
        content = soup.find('div', id='mainContent')
    elif 'vietstock.vn' in url:
        content = soup.find('div', id='content')

    # Quy tắc chung nếu không khớp
    if not content:
        content = soup.find('article') or soup.find('main')

    if not content:
        return ""

    # Loại bỏ các thẻ không cần thiết
    for tag in content.find_all(['script', 'style', 'nav', 'footer', 'aside', 'form']):
        tag.decompose()

    return clean_text(content.get_text(separator='\n', strip=True))

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> List[Dict[str, Any]]:
    """
    Chia văn bản thành các chunks nhỏ hơn.
    Phương pháp: chia theo đoạn văn trước, sau đó chia nhỏ hơn nếu cần.
    """
    if not text:
        return []

    # Tách theo các đoạn văn trước
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = ""

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue

        if len(current_chunk) + len(p) + 1 <= chunk_size:
            current_chunk += p + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = p + " "

    if current_chunk:
        chunks.append(current_chunk.strip())

    # Định dạng lại output
    return [{"chunk_id": i, "text": chunk} for i, chunk in enumerate(chunks)]

async def process_rss_entry(session: aiohttp.ClientSession, entry: Dict, source_title: str) -> Dict:
    """Xử lý một tin bài: lấy full text và chunking."""
    article_url = urljoin(entry.get("link", ""), entry.get("link", ""))
    html = await fetch_html(session, article_url)

    if not html:
        return {}

    full_text = extract_content_from_html(html, article_url)
    chunks = chunk_text(full_text)

    # Nếu không thể bóc tách nội dung, vẫn trả về thông tin cơ bản
    return {
        "source": source_title,
        "title": entry.get("title", "N/A"),
        "link": article_url,
        "published": entry.get("published", "N/A"),
        "summary": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(),
        "full_text_chunks": chunks,
    }


# --- API Endpoint ---

@app.get("/v1/news", response_model=List[NewsArticle])
@cached(cache)
async def get_all_news():
    """
    Endpoint chính để lấy và xử lý tin tức.
    Kết quả được cache trong 5 phút.
    """
    all_articles = []
    async with aiohttp.ClientSession() as session:
        # Lấy danh sách các tin bài từ tất cả các RSS feed
        feed_parsing_tasks = []
        for url in RSS_FEEDS:
             # feedparser không phải là async, chạy trong executor để không block event loop
            feed_parsing_tasks.append(
                asyncio.to_thread(feedparser.parse, url)
            )
        
        parsed_feeds = await asyncio.gather(*feed_parsing_tasks)

        # Tạo các task để xử lý từng bài báo một cách đồng thời
        processing_tasks = []
        for feed in parsed_feeds:
            source_title = feed.feed.get("title", "Unknown Source")
            for entry in feed.entries[:5]:  # Giới hạn 5 tin mới nhất mỗi nguồn
                processing_tasks.append(
                    process_rss_entry(session, entry, source_title)
                )

        # Chờ tất cả các task xử lý hoàn thành
        processed_articles = await asyncio.gather(*processing_tasks)
        
        # Lọc bỏ các kết quả rỗng (do lỗi fetch hoặc parse)
        all_articles = [article for article in processed_articles if article]

    if not all_articles:
        raise HTTPException(status_code=503, detail="Could not fetch news from sources.")
    
    # Sắp xếp tin tức theo thời gian (giả định, vì format thời gian có thể khác nhau)
    # Một giải pháp thực tế hơn cần chuẩn hóa `published_date`
    return sorted(all_articles, key=lambda x: x.get('published', ''), reverse=True)

@app.get("/", include_in_schema=False)
def root():
    return {"message": "Welcome to the Vietnam Stock News API. Go to /docs for documentation."}

