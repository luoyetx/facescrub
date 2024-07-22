facescrub
=========

Download dataset from http://vintage.winklerbros.net/facescrub.html

simply rum `python download.py`, all images are downloaded under `download`.

### Notice

Since I want to vertify the image and extract face region from the images, opencv-python package needed. If you are on Windows, this [url](http://www.lfd.uci.edu/~gohlke/pythonlibs/) can be very helpful to install packages.

### Upgrade

24/07/22

新增python3下使用本地代理地址（Clash 或 V2Ray 本地代理地址）的下载脚本，且加入异步并发、代理地址测试、下载进度条显示、失败日志记录、下载失败后再次下载、可反复运行脚本重复下载（相同URL的图片会跳过）等机制

Add a Python 3 script that uses a local proxy address (Clash or V2Ray local proxy address) for downloading, and incorporate the following features: asynchronous concurrency, proxy address testing, download progress bar display, failure log recording, retry downloads on failure, ability to rerun the script to download repeatedly (skip images with the same URL)
