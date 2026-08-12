import os
import requests

VIDEO_URL = "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "sample.mp4")


def download_sample_video():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Baixando vídeo de teste para: {OUTPUT_FILE}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    with requests.get(VIDEO_URL, stream=True, timeout=30, headers=headers) as response:
        response.raise_for_status()
        with open(OUTPUT_FILE, "wb") as out_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    out_file.write(chunk)

    print("Download concluído.")
    print(f"Use o arquivo local como source em: {OUTPUT_FILE}")


if __name__ == "__main__":
    download_sample_video()
