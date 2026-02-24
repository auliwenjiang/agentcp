import os
import requests
import subprocess
import zipfile
from .tools import download_file

class SoftwareDeployer:
    def __init__(self, temp_dir="./temp"):
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)

    def deploy(self, package_url, install_args=None):
        # 下载软件包
        package_path = os.path.join(self.temp_dir, "package.zip")
        self._download(package_url, package_path)

        # 解压
        extract_dir = os.path.join(self.temp_dir, "extracted")
        self._extract(package_path, extract_dir)

        # 查找安装程序
        installer = self._find_installer(extract_dir)

        # 安装
        self._install(installer, install_args or [])

        # 清理
        self._cleanup()

    def _download(self, url, save_path):
        print(f"Downloading from {url}...")
        download_file(url, save_path)

    def _extract(self, package_path, extract_dir):
        print("Extracting package...")
        with zipfile.ZipFile(package_path, "r") as zipf:
            zipf.extractall(extract_dir)

    def _find_installer(self, directory):
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith((".exe", ".msi")):
                    return os.path.join(root, file)
        raise FileNotFoundError("No installer found in package")

    def _install(self, installer, args):
        print(f"Installing {installer}...")
        if installer.endswith(".msi"):
            subprocess.run(["msiexec", "/i", installer, "/qn"] + args, check=True)
        else:
            subprocess.run([installer, "/S"] + args, check=True)

    def _cleanup(self):
        print("Cleaning up...")
        # 安全删除临时文件
        import shutil

        shutil.rmtree(self.temp_dir)


# 使用示例
deployer = SoftwareDeployer()
deployer.deploy("https://example.com/software/latest.zip")
