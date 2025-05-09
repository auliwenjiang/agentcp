import zipfile
import os
import requests
from tqdm import tqdm  # 进度条

# 创建 ZIP 包
def create_zip(output_filename, source_dir):
    with zipfile.ZipFile(output_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=source_dir)
                zipf.write(file_path, arcname)


# 解压 ZIP 包
def extract_zip(zip_file, extract_dir):
    with zipfile.ZipFile(zip_file, "r") as zipf:
        zipf.extractall(extract_dir)


def download_file(url, filename):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        total_size = int(r.headers.get("content-length", 0))

        with open(filename, "wb") as f, tqdm(
            desc=filename,
            total=total_size,
            unit="iB",
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))
