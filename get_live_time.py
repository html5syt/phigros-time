#!/usr/bin/env python3
"""
B站UP主直播预约时间获取脚本
自动获取UP主的直播预约信息并保存到文件
"""

from functools import reduce
from hashlib import md5
import urllib.parse
import time
import requests
import os
import sys

# WBI签名相关
mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

def getMixinKey(orig: str):
    """对 imgKey 和 subKey 进行字符顺序打乱编码"""
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, '')[:32]

def encWbi(params: dict, img_key: str, sub_key: str):
    """为请求参数进行 wbi 签名"""
    mixin_key = getMixinKey(img_key + sub_key)
    curr_time = round(time.time())
    params['wts'] = curr_time                                   # 添加 wts 字段
    params = dict(sorted(params.items()))                       # 按照 key 重排参数
    # 过滤 value 中的 "!'()*" 字符
    params = {
        k : ''.join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v 
        in params.items()
    }
    query = urllib.parse.urlencode(params)                      # 序列化参数
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()    # 计算 w_rid
    params['w_rid'] = wbi_sign
    return params

def getWbiKeys() -> tuple[str, str]:
    """获取最新的 img_key 和 sub_key"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
        'Referer': 'https://www.bilibili.com/'
    }
    resp = requests.get('https://api.bilibili.com/x/web-interface/nav', headers=headers)
    resp.raise_for_status()
    json_content = resp.json()
    img_url: str = json_content['data']['wbi_img']['img_url']
    sub_url: str = json_content['data']['wbi_img']['sub_url']
    img_key = img_url.rsplit('/', 1)[1].split('.')[0]
    sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
    return img_key, sub_key

def get_live_reservation(mid: str):
    """获取UP主的直播预约信息"""
    try:
        # 获取WBI密钥
        img_key, sub_key = getWbiKeys()
        print(f"获取到WBI密钥: img_key={img_key}, sub_key={sub_key}")
        
        # 准备参数
        params = {
            'host_mid': mid,
            'offset': '',
            'features': 'itemOpusStyle,listOnlyfans,opusBigCover,onlyfansVote,forwardListHidden,decorationCard,commentsNewVersion,onlyfansAssetsV2,ugcDelete,onlyfansQaCard'
        }
        
        # 生成签名
        signed_params = encWbi(params, img_key, sub_key)
        
        # 发送请求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
            'Referer': 'https://www.bilibili.com/'
        }
        
        url = 'https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space'
        response = requests.get(url, params=signed_params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data['code'] != 0:
            print(f"API返回错误: {data['message']}")
            return None
        
        # 查找最新的直播预约动态
        items = data.get('data', {}).get('items', [])
        for item in items:
            # 检查动态发布时间（pub_ts）是否在近一个月内
            pub_ts = item.get('modules', {}).get('module_author', {}).get('pub_ts', 0)
            one_month_ago = int(time.time()) - 30 * 24 * 60 * 60
            
            if pub_ts and pub_ts < one_month_ago:
                continue
            
            # 检查是否是直播预约动态
            additional = item.get('modules', {}).get('module_dynamic', {}).get('additional', {})
            if additional.get('type') == 'ADDITIONAL_TYPE_RESERVE':
                reserve = additional.get('reserve', {})
                if reserve and reserve.get('desc1') and reserve.get('desc1', {}).get('text'):
                    # 解析时间
                    time_text = reserve['desc1']['text']
                    title = reserve.get('title', '')
                    
                    # 提取时间（示例："10-26 13:00 直播"）
                    import re
                    time_match = re.search(r'(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2})', time_text)
                    if time_match:
                        month = int(time_match.group(1))
                        day = int(time_match.group(2))
                        hour = int(time_match.group(3))
                        minute = int(time_match.group(4))
                        
                        # 构建日期（假设是当前年份）
                        now = time.localtime()
                        year = now.tm_year
                        
                        # 创建时间对象
                        reservation_time = time.mktime((year, month, day, hour, minute, 0, 0, 0, -1))
                        
                        # 如果日期已经过去，假设是明年
                        if reservation_time < time.time():
                            reservation_time = time.mktime((year + 1, month, day, hour, minute, 0, 0, 0, -1))
                        
                        # 移除"直播预约："前缀
                        clean_title = title.replace("直播预约：", "")
                        
                        print(f"找到直播预约: {clean_title}, 时间: {time.strftime('%Y-%m-%d %H:%M', time.localtime(reservation_time))}")
                        
                        return {
                            'timestamp': int(reservation_time),
                            'title': clean_title
                        }
        
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
    
    # 获取直播预约信息
    reservation = get_live_reservation(mid)
    
    if reservation:
        # 写入自动获取的时间文件
        with open('auto-get-time.txt', 'w', encoding='utf-8') as f:
            f.write(f"{reservation['timestamp']}\n")
            f.write(f"{reservation['title']}\n")
        print(f"成功写入auto-get-time.txt: {reservation}")
    else:
        print("未获取到直播预约信息，保持现有文件不变")

if __name__ == "__main__":
    main()
