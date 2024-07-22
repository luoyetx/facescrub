import os
from os.path import join, exists
import hashlib
import cv2
import aiohttp
import asyncio
import async_timeout
import ssl
import logging
from tqdm.asyncio import tqdm_asyncio
import time

# 设置日志配置 Set up logging configuration
logging.basicConfig(
    level=logging.INFO
)  # 修改为INFO以减少日志输出 Change to INFO to reduce logging output
logger = logging.getLogger(__name__)

# 本地代理地址（Clash 或 V2Ray 本地代理地址）Local proxy address (Clash or V2Ray local proxy address)
LOCAL_PROXY = "http://127.0.0.1:7890"  # 请根据你的实际端口号调整 Please adjust according to your actual port number
TEST_URL = "https://www.google.com"

files = ["facescrub_actors.txt", "facescrub_actresses.txt"]
RESULT_ROOT = "./download"
if not exists(RESULT_ROOT):
    os.mkdir(RESULT_ROOT)

# 创建一个不验证SSL证书的SSL上下文 Create an SSL context that does not verify SSL certificates
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


async def check_proxy(session):
    try:
        async with session.get(
            TEST_URL, proxy=LOCAL_PROXY, ssl=ssl_context
        ) as response:
            if response.status == 200:
                logger.info(f"Proxy is working: {response.status}")
                return True
            else:
                logger.error(f"Proxy test failed with status code: {response.status}")
                return False
    except Exception as e:
        logger.error(f"Proxy test failed: {e}")
        return False


async def download_image(session, url, dst, timeout=30):
    try:
        # 创建目标目录
        os.makedirs(os.path.dirname(dst), exist_ok=True)

        logger.debug(f"Attempting to download {url}")
        async with async_timeout.timeout(timeout):
            async with session.get(url, proxy=LOCAL_PROXY, ssl=ssl_context) as response:
                logger.debug(f"Received response {response.status} for {url}")

                if response.status in [502, 403, 404]:
                    error_msgs = {
                        502: "502 Bad Gateway",
                        403: "403 Forbidden",
                        404: "404 Not Found",
                    }
                    error_msg = error_msgs.get(
                        response.status, f"HTTP {response.status}"
                    )
                    logger.warning(f"Failed to download {url}: {error_msg}")
                    return False

                response.raise_for_status()
                content = await response.read()
                with open(dst, "wb") as f:
                    f.write(content)
                logger.info(f"Successfully downloaded {url}")
                return True
    except (
        aiohttp.ClientError,
        aiohttp.ClientConnectorError,
        asyncio.TimeoutError,
    ) as e:
        logger.error(f"Failed to download {url}: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error while attempting to download {url}: {e}")
        return False


async def process_task(session, names, urls, bboxes, progress_bar):
    total_success = 0
    total_failures = 0
    failed_downloads = (
        []
    )  # 用于记录下载失败的URL Used to log URLs that failed to download
    for i in range(len(names)):
        directory = join(RESULT_ROOT, names[i])
        if not exists(directory):
            os.mkdir(directory)
        fname = hashlib.sha1(urls[i].encode("utf-8")).hexdigest() + ".jpg"
        dst = join(directory, fname)
        logger.debug(f"Checking existence of {dst}")
        if exists(dst):
            logger.info(f"{dst} already downloaded, skipping...")
            total_success += 1
            progress_bar.update(1)
            continue

        success = await download_image(session, urls[i], dst)
        if not success:
            failed_downloads.append(urls[i])
            total_failures += 1
            progress_bar.update(1)
            continue

        total_success += 1
        progress_bar.update(1)

        # Get face
        face_directory = join(directory, "face")
        if not exists(face_directory):
            os.mkdir(face_directory)
        img = cv2.imread(dst)
        if img is None or img.size == 0:
            # No image data
            os.remove(dst)
            continue
        else:
            face_path = join(face_directory, fname)
            face = img[bboxes[i][1] : bboxes[i][3], bboxes[i][0] : bboxes[i][2]]
            if face.size == 0:
                logger.warning(f"Invalid face data for {dst}")
                os.remove(dst)
                continue
            cv2.imwrite(face_path, face)
            # Write bbox to file
            with open(join(directory, "_bboxes.txt"), "a") as fd:
                bbox_str = ",".join([str(_) for _ in bboxes[i]])
                fd.write(f"{fname} {bbox_str}\n")

    # 记录下载失败的 URL Log the URLs that failed to download
    if failed_downloads:
        with open("failed_downloads.txt", "w") as f:
            for url in failed_downloads:
                f.write(f"{url}\n")
        logger.info(f"Failed downloads have been recorded in failed_downloads.txt")

    return total_success, total_failures


async def retry_failed_downloads(session, progress_bar):
    if not exists("failed_downloads.txt"):
        logger.info("No failed downloads to retry.")
        return 0, 0

    with open("failed_downloads.txt", "r") as f:
        failed_urls = [line.strip() for line in f.readlines()]

    if not failed_urls:
        logger.info("No failed downloads to retry.")
        return 0, 0

    logger.info(f"Retrying {len(failed_urls)} failed downloads...")

    total_success = 0
    total_failures = 0

    async def retry_download(url):
        nonlocal total_success, total_failures
        directory = join(RESULT_ROOT, hashlib.sha1(url.encode("utf-8")).hexdigest())
        fname = hashlib.sha1(url.encode("utf-8")).hexdigest() + ".jpg"
        dst = join(directory, fname)
        progress_bar.update(1)

        logger.debug(f"Checking existence of {dst}")
        if exists(dst):
            logger.info(f"{dst} already downloaded, skipping...")
            total_success += 1
            return

        success = await download_image(session, url, dst)
        if not success:
            total_failures += 1
            return

        total_success += 1

    await tqdm_asyncio.gather(*[retry_download(url) for url in failed_urls])

    if total_failures == 0 and exists("failed_downloads.txt"):
        os.remove("failed_downloads.txt")

    return total_success, total_failures


async def main():
    start_time = time.time()  # 记录开始时间
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=ssl_context)
        ) as session:
            # 先测试代理和网络连接 First, test the proxy and network connection
            if not await check_proxy(session):
                logger.error(f"Proxy test failed. Exiting.")
                return

            tasks = []
            total_images = 0
            for f in files:
                with open(f, "r") as fd:
                    # Strip first line
                    fd.readline()
                    names = []
                    urls = []
                    bboxes = []
                    for line in fd.readlines():
                        components = line.split("\t")
                        if len(components) != 6:
                            continue  # Skip invalid lines
                        name = components[0].replace(" ", "_")
                        url = components[3]
                        bbox = [int(_) for _ in components[4].split(",")]
                        names.append(name)
                        urls.append(url)
                        bboxes.append(bbox)
                    total_images += len(names)

                    # Every name gets a task
                    last_name = names[0]
                    task_names = []
                    task_urls = []
                    task_bboxes = []
                    for i in range(len(names)):
                        if names[i] == last_name:
                            task_names.append(names[i])
                            task_urls.append(urls[i])
                            task_bboxes.append(bboxes[i])
                        else:
                            tasks.append((task_names, task_urls, task_bboxes))
                            task_names = [names[i]]
                            task_urls = [urls[i]]
                            task_bboxes = [bboxes[i]]
                            last_name = names[i]
                    tasks.append((task_names, task_urls, task_bboxes))

            # 创建一个进度条 Create a progress bar
            progress_bar = tqdm_asyncio(total=total_images, desc="Downloading images")
            results = await tqdm_asyncio.gather(
                *(
                    process_task(session, names, urls, bboxes, progress_bar)
                    for names, urls, bboxes in tasks
                )
            )

            total_success = sum(result[0] for result in results)
            total_failures = sum(result[1] for result in results)
            logger.info(f"Total successful downloads: {total_success}")
            logger.info(f"Total failed downloads: {total_failures}")

            # 重新尝试失败的下载 Retry failed downloads
            retry_success, retry_failures = await retry_failed_downloads(
                session, progress_bar
            )
            total_success += retry_success
            total_failures += retry_failures
            logger.info(f"Total successful downloads after retry: {total_success}")
            logger.info(f"Total failed downloads after retry: {total_failures}")

    except Exception as e:
        logger.error(f"Exception in main: {e}")
    finally:
        end_time = time.time()  # 记录结束时间
        total_time = end_time - start_time  # 计算总用时
        logger.info(f"Total time taken: {total_time:.2f} seconds")


if __name__ == "__main__":
    try:
        import asyncio
        import sys

        if sys.platform.startswith("win") and sys.version_info >= (3, 8):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        asyncio.run(main())
    except Exception as e:
        logger.error(f"Exception in main: {e}")
