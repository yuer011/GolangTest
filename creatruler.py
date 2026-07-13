
import random
import string
import time

# 配置
url = "https://feilian-qa11.local.ifeilian.cn:8443/api/admin/v2/dynamic_security/dlp/sensitive_pattern/create?os=web"
headers = {
    "accept": "*/*",
    "accept-language": "zh-CN",
    "admin-csrf-token": "",
    "cache-control": "no-cache",
    "content-type": "application/json",
    "csrf-token": "BnZEStSUoelZAOziwfSWlkvzxcasNCvktdUOOBFC",
    "origin": "https://feilian-qa11.local.ifeilian.cn:8443",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://feilian-qa11.local.ifeilian.cn:8443/admin/security_edlp/data_recognition?tab=edlp%2Fdata_identify%2Fsensitive_lib",
    "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "x-fe-version": "3.2.6.15024",
    "x-tenant-timezone": "Asia/Shanghai",
    "x-version-check": "0"
}
cookies = {
    "unit-open-id": "un_QOB0XzbXpE5x",
    "refer_next": "%2Fadmin%2Fsecurity_edlp%2Fstrategy_center%3Ftab%3Dedlp%252Fpolicy%252Finternal_addr",
    "csrf-token": "BnZEStSUoelZAOziwfSWlkvzxcasNCvktdUOOBFC",
    "session": "MTc4MzMzMDI0N3xOd3dBTkRjeU5FaFJVVXRQVEZkUFRsRkNTMVZXU1ZneU5WaEJTMEZXTkZSSVVVWlZTa2hFU2s0ME0wSkdUVFJHVlRJMVNGTlFORkU9fOsw7c5qslBQNseTimH98qNb9qa7CWNXuUpTKv69ZTIL"
}

# 生成 5 位随机字符串（字母+数字）
def random_5_str():
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(5))

# 循环 100 次请求
for i in range(1, 101):
    name = random_5_str()
    value = random_5_str()
    payload = {
        "class": 3,
        "name": name,
        "value": value,
        "min_match_times": 1
    }
    print(f"===== 第 {i} 次请求 =====")
    print(f"name: {name}, value: {value}")

    time.sleep(0.2)