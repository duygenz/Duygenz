import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import feedparser
import httpx

# List of RSS feeds
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

app = FastAPI(
    title="Vietnam News API",
    description="An API to fetch the latest news from various Vietnamese sources.",
    version="1.0.0",
)
origins = [
    "*",  # Cho phép tất cả các nguồn. Để an toàn hơn, bạn có thể thay bằng tên miền cụ thể.
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Cho phép tất cả các phương thức (GET, POST, etc.)
    allow_headers=["*"], # Cho phép tất cả các header
)
async def fetch_feed(client, url):
    """Asynchronously fetches and parses a single RSS feed."""
    try:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        return [
            {
                "title": entry.get("title", "No Title"),
                "link": entry.get("link", "No Link"),
                "published": entry.get("published", "No Date"),
                "source": feed.feed.get("title", url),
            }
            for entry in feed.entries
        ]
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        print(f"Error fetching {url}: {e}")
        return []

@app.get(
    "/news",
    summary="Fetch News from All Sources",
    description="Retrieves a consolidated list of the latest news articles from all configured RSS feeds.",
)
async def get_news():
    """
    This endpoint fetches news from all RSS feeds concurrently and returns them
    as a single JSON response.
    """
    async with httpx.AsyncClient() as client:
        tasks = [fetch_feed(client, url) for url in RSS_FEEDS]
        results = await asyncio.gather(*tasks)
        
        # Flatten the list of lists into a single list
        all_news = [item for sublist in results for item in sublist]
        
        # Optional: Sort all news by published date (best-effort)
        # Note: Date parsing can be complex; this is a simple sort
        try:
            all_news.sort(key=lambda x: feedparser._parse_date(x['published']), reverse=True)
        except Exception:
            # If dates are inconsistent, just return as is
            pass

    return JSONResponse(content={"news": all_news})

# Health check endpoint
@app.get("/", summary="Health Check")
async def root():
    """A simple health check endpoint to confirm the API is running."""
    return {"status": "ok", "message": "Welcome to the News API!"}

