# 保存为 run.py ！！！ 绝对不要叫 requests.py
import requests
import random
import string
import warnings
warnings.filterwarnings("ignore") # 关闭SSL证书警告

# 接口地址
url = "https://feilian-qa15.local.ifeilian.cn:8443/api/admin/v2/dynamic_security/edlp/email_addr_whitelist/add?os=web"

# 请求头
headers = {
    "accept": "*/*",
    "accept-language": "zh-CN",
    "cache-control": "no-cache",
    "content-type": "application/json",
    "csrf-token": "BozGSLQmRvVoTmGypsetPwxOCgAcIHfsWuSeKCDT",
    "origin": "https://feilian-qa15.local.ifeilian.cn:8443",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://feilian-qa15.local.ifeilian.cn:8443/admin/security_edlp/strategy_center?addr_sub=email&tab=edlp%2Fpolicy%2Finternal_addr",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "x-fe-version": "2.1.0.13106",
    "x-tenant-timezone": "Asia/Shanghai",
    "x-version-check": "0"
}

# Cookie
cookies = {
    "unit-open-id": "un_kyYO08D0r3Xw",
    "csrf-token": "BozGSLQmRvVoTmGypsetPwxOCgAcIHfsWuSeKCDT",
    "refer_next": "%2Fadmin",
    "session": "MTc3NDQyMzE5MHxOd3dBTkZsSk4wUmFXbGRTU1VGUFFrczJTemRPU0V4WVJrMVBOMEpWTlZoU1ZWaFJTbFZVTkROQlZFZE1URWN5VWxSV00weE9WVUU9fFi_wjHyGpnYJvJNE7Jst1WWlaCVXpuYElwOjoKiZNBZ",
    "plugin-token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIzIiwiZXhwIjoxNzc1ODAzNzAxLCJ2YWwiOiJ7XCJvcGVuX2lkXCI6XCJvdV8zQm85NXowWE5iXCJ9In0.cyAhZU--VJYcuOwwiRD4K8JgAHWN0EY2IXDd3p4jUgg"
}

# 生成随机字符串
def random_str(n):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))

# 循环5次
for i in range(1, 6):
    print(f"\n===== 第 {i} 次请求 =====")
    domain = random_str(5)
    name = f"升级后-{random_str(6)}"
    print(f"email_domain_content = {domain}")

    data = {
        "email_name": name,
        "email_domain_content": domain
    }

    try:
        res = requests.post(url, headers=headers, cookies=cookies, json=data, verify=False)
        print(f"状态码: {res.status_code}")
        print(f"返回结果: {res.text}")
    except Exception as e:
        print(f"请求失败: {e}")