#!/usr/bin/env python3
"""
B站UP主直播预约时间获取脚本
自动获取UP主的直播预约信息并保存到文件
添加buvid3支持以避免风控
"""

from functools import reduce
from hashlib import md5
import urllib.parse
import time
import requests
import os
import sys
import re
import random
import string

# WBI签名相关
mixinKeyEncTab = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]


def getMixinKey(orig: str):
    """对 imgKey 和 subKey 进行字符顺序打乱编码"""
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, "")[:32]


def encWbi(params: dict, img_key: str, sub_key: str):
    """为请求参数进行 wbi 签名"""
    mixin_key = getMixinKey(img_key + sub_key)
    curr_time = round(time.time())
    params["wts"] = curr_time  # 添加 wts 字段
    params = dict(sorted(params.items()))  # 按照 key 重排参数
    # 过滤 value 中的 "!'()*" 字符
    params = {
        k: "".join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)  # 序列化参数
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()  # 计算 w_rid
    params["w_rid"] = wbi_sign
    return params


def getWbiKeys(buvid3: str = "") -> tuple[str, str]:
    """获取最新的 img_key 和 sub_key"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    }

    # 添加buvid3到Cookie中
    cookies = {}
    if buvid3:
        cookies["buvid3"] = buvid3

    resp = requests.get(
        "https://api.bilibili.com/x/web-interface/nav", headers=headers, cookies=cookies
    )
    resp.raise_for_status()
    json_content = resp.json()
    img_url: str = json_content["data"]["wbi_img"]["img_url"]
    sub_url: str = json_content["data"]["wbi_img"]["sub_url"]
    img_key = img_url.rsplit("/", 1)[1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]
    return img_key, sub_key


def get_buvid3() -> str:
    """获取buvid3标识"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        # 尝试从获取buvid3的API获取
        resp = requests.get(
            "https://api.bilibili.com/x/web-frontend/getbuvid", headers=headers
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                buvid3 = data["data"]["buvid"]
                print(f"成功获取buvid3: {buvid3}")
                return buvid3

        # 如果API获取失败，使用一个随机生成的buvid3作为备选
        # 生成符合buvid3格式的随机字符串 (通常以XY开头)
        random_part = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=32)
        )
        buvid3 = f"XY{random_part}"
        print(f"生成随机buvid3: {buvid3}")
        return buvid3

    except Exception as e:
        print(f"获取buvid3失败: {e}")
        # 返回一个固定的备选buvid3
        return "XY5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A"


def parse_reservation_time(time_text: str, uncheck_text: str = "") -> float | None:
    """解析预约时间文本，返回时间戳"""
    now = time.localtime()
    year = now.tm_year

    # 尝试匹配"今天 时:分"格式（可能带有"直播"等后缀）
    today_match = re.search(r"今天\s*(\d{1,2}):(\d{1,2})", time_text)
    if today_match:
        hour = int(today_match.group(1))
        minute = int(today_match.group(2))

        # 获取今天日期
        month = now.tm_mon
        day = now.tm_mday

        # 创建时间对象
        reservation_time = time.mktime((year, month, day, hour, minute, 0, 0, 0, -1))

        # 根据按钮状态决定是否设置为明天
        if uncheck_text != "已结束" and reservation_time < time.time():
            tomorrow = time.localtime(time.time() + 86400)
            reservation_time = time.mktime(
                (
                    tomorrow.tm_year,
                    tomorrow.tm_mon,
                    tomorrow.tm_mday,
                    hour,
                    minute,
                    0,
                    0,
                    0,
                    -1,
                )
            )
        return reservation_time

    # 尝试匹配"明天 时:分"格式（可能带有"直播"等后缀）
    tomorrow_match = re.search(r"明天\s*(\d{1,2}):(\d{1,2})", time_text)
    if tomorrow_match:
        hour = int(tomorrow_match.group(1))
        minute = int(tomorrow_match.group(2))

        # 获取明天日期
        tomorrow = time.localtime(time.time() + 86400)

        # 创建时间对象
        reservation_time = time.mktime(
            (
                tomorrow.tm_year,
                tomorrow.tm_mon,
                tomorrow.tm_mday,
                hour,
                minute,
                0,
                0,
                0,
                -1,
            )
        )
        return reservation_time

    # 尝试匹配"后天 时:分"格式
    day_after_tomorrow_match = re.search(r"后天\s*(\d{1,2}):(\d{1,2})", time_text)
    if day_after_tomorrow_match:
        hour = int(day_after_tomorrow_match.group(1))
        minute = int(day_after_tomorrow_match.group(2))

        # 获取后天日期
        day_after = time.localtime(time.time() + 86400 * 2)

        # 创建时间对象
        reservation_time = time.mktime(
            (
                day_after.tm_year,
                day_after.tm_mon,
                day_after.tm_mday,
                hour,
                minute,
                0,
                0,
                0,
                -1,
            )
        )
        return reservation_time

    # 尝试匹配"月-日 时:分"格式
    date_match = re.search(r"(\d{1,2})-(\d{1,2})\s*(\d{1,2}):(\d{1,2})", time_text)
    if date_match:
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        hour = int(date_match.group(3))
        minute = int(date_match.group(4))

        # 创建时间对象
        reservation_time = time.mktime((year, month, day, hour, minute, 0, 0, 0, -1))

        # 根据按钮状态决定是否设置为明年
        if uncheck_text != "已结束" and reservation_time < time.time():
            reservation_time = time.mktime(
                (year + 1, month, day, hour, minute, 0, 0, 0, -1)
            )
        return reservation_time

    # 尝试匹配"年-月-日 时:分"格式
    full_date_match = re.search(
        r"(\d{4})-(\d{1,2})-(\d{1,2})\s*(\d{1,2}):(\d{1,2})", time_text
    )
    if full_date_match:
        year = int(full_date_match.group(1))
        month = int(full_date_match.group(2))
        day = int(full_date_match.group(3))
        hour = int(full_date_match.group(4))
        minute = int(full_date_match.group(5))

        reservation_time = time.mktime((year, month, day, hour, minute, 0, 0, 0, -1))
        return reservation_time

    # 尝试匹配"月/日 时:分"格式
    slash_date_match = re.search(
        r"(\d{1,2})/(\d{1,2})\s*(\d{1,2}):(\d{1,2})", time_text
    )
    if slash_date_match:
        month = int(slash_date_match.group(1))
        day = int(slash_date_match.group(2))
        hour = int(slash_date_match.group(3))
        minute = int(slash_date_match.group(4))

        reservation_time = time.mktime((year, month, day, hour, minute, 0, 0, 0, -1))

        if uncheck_text != "已结束" and reservation_time < time.time():
            reservation_time = time.mktime(
                (year + 1, month, day, hour, minute, 0, 0, 0, -1)
            )
        return reservation_time

    return None


def get_live_reservation(mid: str, buvid3: str):
    """获取UP主的直播预约信息"""
    try:
        # 获取WBI密钥
        img_key, sub_key = getWbiKeys(buvid3)
        print(f"获取到WBI密钥: img_key={img_key}, sub_key={sub_key}")

        # 准备参数
        params = {
            "host_mid": mid,
            "offset": "",
            "features": "itemOpusStyle,listOnlyfans,opusBigCover,onlyfansVote,forwardListHidden,decorationCard,commentsNewVersion,onlyfansAssetsV2,ugcDelete,onlyfansQaCard",
        }

        # 生成签名
        signed_params = encWbi(params, img_key, sub_key)

        # 发送请求，带上buvid3
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": f"https://space.bilibili.com/{mid}",
        }

        cookies = {"buvid3": buvid3}

        url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
        response = requests.get(
            url, params=signed_params, headers=headers, cookies=cookies
        )
        response.raise_for_status()
        data = response.json()

        if data["code"] != 0:
            print(f"API返回错误: {data['message']}")
            return None

        # 查找最新的直播预约动态
        items = data.get("data", {}).get("items", [])

        # 如果没有找到动态，尝试翻页
        offset = data.get("data", {}).get("offset", "")
        max_pages = 100  # 最多翻100页

        for page in range(max_pages):
            # 在当前页的items中查找预约
            for item in items:
                # 检查是否是直播预约动态
                additional = (
                    item.get("modules", {})
                    .get("module_dynamic", {})
                    .get("additional", {})
                )
                if additional:
                    if additional.get("type") == "ADDITIONAL_TYPE_RESERVE":
                        reserve = additional.get("reserve", {})
                        if (
                            reserve
                            and reserve.get("desc1")
                            and reserve.get("desc1", {}).get("text")
                        ):
                            # 解析时间
                            time_text = reserve["desc1"]["text"]
                            title = reserve.get("title", "")

                            # 检查按钮状态
                            button = reserve.get("button", {})
                            uncheck_text = (
                                button.get("uncheck", {}).get("text", "")
                                if button
                                else ""
                            )

                            # 使用新的解析函数
                            reservation_time = parse_reservation_time(
                                time_text, uncheck_text
                            )

                            if reservation_time is not None:
                                return {
                                    "timestamp": int(reservation_time),
                                    "title": title,
                                    "time_text": time_text,
                                }
                            else:
                                print(f"无法解析时间格式: {time_text}")
                                continue

            # 如果当前页没有找到预约但有更多页面，继续翻页
            if offset and data.get("data", {}).get("has_more", False):
                print(f"第{page + 1}页未找到预约，继续翻页，offset: {offset}")
                # 更新offset参数
                params["offset"] = offset
                signed_params = encWbi(params, img_key, sub_key)

                # 发送翻页请求
                response = requests.get(
                    url, params=signed_params, headers=headers, cookies=cookies
                )
                response.raise_for_status()
                data = response.json()

                if data["code"] != 0:
                    break

                items = data.get("data", {}).get("items", [])
                offset = data.get("data", {}).get("offset", "")
            else:
                # 如果没有更多页面，跳出循环
                break

        print("未找到近期的直播预约信息")
        return None

    except Exception as e:
        print(f"获取直播预约信息时出错: {e}")
        return None


def main():
    """主函数"""
    # UP主的MID
    mid = "414149787"

    print("开始获取B站UP主直播预约信息...")

    # 获取buvid3
    buvid3 = get_buvid3()

    # 获取直播预约信息
    reservation = get_live_reservation(mid, buvid3)

    if reservation:
        # 写入自动获取的时间文件
        with open("auto-get-time.txt", "w", encoding="utf-8") as f:
            f.write(f"{reservation['timestamp']}\n")
            f.write(f"{reservation['title']}\n")
        print(f"成功写入auto-get-time.txt: {reservation}")
    else:
        print("未获取到直播预约信息，保持现有文件不变")


if __name__ == "__main__":
    main()
