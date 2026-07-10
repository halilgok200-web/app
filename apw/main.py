from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
import yt_dlp
import requests

app = FastAPI(title="Universal Media Downloader")

# 1. ARAYÜZ (UI) KATMANI
@app.get("/", response_class=HTMLResponse)
async def read_item():
    return """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Media Downloader Hub</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 text-white min-h-screen flex flex-col items-center justify-center p-4">
        <div class="w-full max-w-2xl bg-slate-800 p-6 rounded-2xl shadow-xl border border-slate-700">
            <h1 class="text-3xl font-extrabold text-center mb-2 bg-gradient-to-r from-red-500 via-pink-500 to-purple-500 bg-clip-text text-transparent">
                Universal Downloader
            </h1>
            <p class="text-slate-400 text-center text-sm mb-6">YouTube, Instagram, TikTok ve daha fazlası...</p>
            
            <div class="flex flex-col sm:flex-row gap-2 mb-6">
                <input type="text" id="urlInput" placeholder="Medya veya Gönderi URL'sini yapıştırın..." 
                    class="flex-1 px-4 py-3 bg-slate-900 border border-slate-700 rounded-xl focus:outline-none focus:border-pink-500 text-white text-sm">
                <button onclick="fetchMedia()" id="btnFetch"
                    class="px-6 py-3 bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-500 hover:to-purple-500 font-semibold rounded-xl transition-all duration-200 shadow-lg active:scale-95 text-sm">
                    Sorgula
                </button>
            </div>

            <div id="loading" class="hidden text-center py-4">
                <div class="animate-spin inline-block w-8 h-8 border-4 border-pink-500 border-t-transparent rounded-full mb-2"></div>
                <p class="text-slate-400 text-xs">Medya detayları çözümleniyor, lütfen bekleyin...</p>
            </div>

            <div id="result" class="hidden space-y-4">
                <h3 id="mediaTitle" class="font-bold text-lg text-slate-200 line-clamp-2"></h3>
                <div id="mediaContainer" class="grid grid-cols-2 gap-4 max-h-[400px] overflow-y-auto p-2 border border-slate-700 rounded-xl bg-slate-900">
                    </div>
            </div>
        </div>

        <script>
            async function fetchMedia() {
                const urlInput = document.getElementById('urlInput').value.trim();
                const btnFetch = document.getElementById('btnFetch');
                const loading = document.getElementById('loading');
                const result = document.getElementById('result');
                const mediaContainer = document.getElementById('mediaContainer');
                const mediaTitle = document.getElementById('mediaTitle');

                if (!urlInput) {
                    alert('Lütfen geçerli bir URL girin!');
                    return;
                }

                loading.classList.remove('hidden');
                result.classList.add('hidden');
                mediaContainer.innerHTML = '';
                btnFetch.disabled = true;

                try {
                    const response = await fetch(`/api/download?url=${encodeURIComponent(urlInput)}`);
                    const data = await response.json();

                    if (!data.success) {
                        alert('Hata: ' + (data.detail || 'Medya çekilemedi.'));
                        return;
                    }

                    mediaTitle.innerText = data.title || 'Başlıksız Medya';
                    
                    if (data.type === 'carousel') {
                        data.media.forEach((item, index) => {
                            createMediaCard(item.url, item.is_video, `Medya ${index + 1}`);
                        });
                    } else {
                        createMediaCard(data.download_url, data.is_video, 'İndir');
                    }

                    result.classList.remove('hidden');
                } catch (error) {
                    alert('Bir sunucu hatası oluştu!');
                } finally {
                    loading.classList.add('hidden');
                    btnFetch.disabled = false;
                }
            }

            function createMediaCard(url, isVideo, label) {
                const container = document.getElementById('mediaContainer');
                const card = document.createElement('div');
                card.className = "bg-slate-800 p-3 rounded-lg border border-slate-700 flex flex-col justify-between items-center space-y-3 shadow";

                // DIKKAT: Yasaklı linki aşmak için indirme butonunu bizim proxy endpoint'imize yönlendiriyoruz
                const proxyUrl = `/api/proxy?stream_url=${encodeURIComponent(url)}`;

                let previewHtml = '';
                if (isVideo) {
                    previewHtml = `<video src="${proxyUrl}" class="w-full h-32 object-cover rounded" controls muted></video>`;
                } else {
                    previewHtml = `<img src="${proxyUrl}" class="w-full h-32 object-cover rounded" alt="Önizleme">`;
                }

                card.innerHTML = `
                    ${previewHtml}
                    <a href="${proxyUrl}" target="_blank" download="downloaded_media"
                        class="w-full text-center py-1.5 bg-emerald-600 hover:bg-emerald-500 text-xs font-medium rounded-md transition duration-200">
                        ${label}
                    </a>
                `;
                container.appendChild(card);
            }
        </script>
    </body>
    </html>
    """

# 2. PROXY KATMANI (TikTok/Instagram Engellerini Aşmak İçin)
@app.get("/api/proxy")
async def proxy_stream(stream_url: str = Query(..., description="Doğrudan medya url'si")):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.tiktok.com/'  # TikTok'u kandırmak için referans ekliyoruz
    }
    
    def iterfile():
        # Videoyu parça parça (chunk) indirip eşzamanlı olarak tarayıcıya yolluyoruz
        with requests.get(stream_url, headers=headers, stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=8192):
                yield chunk

    try:
        return StreamingResponse(iterfile(), media_type="video/mp4")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Proxy hatası: {str(e)}")

# 3. VERI AYIKLAMA (API) KATMANI
@app.get("/api/download")
async def get_download_url(url: str = Query(..., description="Medya URL'si")):
    ydl_opts = {
        'format': 'best',
        'noplaylist': False, 
        'playlist_items': '1-5',
        'ignoreerrors': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=400, detail="Medya bilgileri alınamadı.")

            if 'entries' in info:
                media_list = []
                for entry in info['entries']:
                    if entry:
                        direct_url = entry.get('url') or (entry.get('formats')[0]['url'] if entry.get('formats') else None)
                        if direct_url:
                            media_list.append({
                                "url": direct_url,
                                "is_video": entry.get('vcodec') != 'none' if entry.get('vcodec') else False
                            })
                if len(media_list) == 1:
                    return {"success": True, "type": "single", "title": info.get('title'), "download_url": media_list[0]['url'], "is_video": media_list[0]['is_video']}
                return {"success": True, "type": "carousel", "title": info.get('title'), "media": media_list}
            else:
                direct_url = info.get('url') or (info.get('formats')[0]['url'] if info.get('formats') else None)
                return {
                    "success": True, 
                    "type": "single", 
                    "title": info.get('title'), 
                    "download_url": direct_url, 
                    "is_video": info.get('vcodec') != 'none' if info.get('vcodec') else False
                }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
