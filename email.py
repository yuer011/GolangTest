import requests
import random
import string

# 接口地址
url = "https://feilian-qa15.local.ifeilian.cn:8443/api/admin/v2/dynamic_security/edlp/email_addr_whitelist/add?os=web"

# 请求头（直接沿用你提供的，已修复 admin-csrf-token 错误）
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

# Cookie（直接复制你的）
cookies = {
    "unit-open-id": "un_kyYO08D0r3Xw",
    "csrf-token": "BozGSLQmRvVoTmGypsetPwxOCgAcIHfsWuSeKCDT",
    "refer_next": "%2Fadmin",
    "session": "MTc3NDQyMzE5MHxOd3dBTkZsSk4wUmFXbGRTU1VGUFFrczJTemRPU0V4WVJrMVBOMEpWTlZoU1ZWaFJTbFZVTkROQlZFZE1URWN5VWxSV00weE9WVUU9fFi_wjHyGpnYJvJNE7Jst1WWlaCVXpuYElwOjoKiZNBZ",
    "plugin-token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIzIiwiZXhwIjoxNzc1ODAzNzAxLCJ2YWwiOiJ7XCJvcGVuX2lkXCI6XCJvdV8zQm85NXowWE5iXCIsXCJzZXNzaW9uX2lkXCI6XCJZSTdEWlpXUklBT0JLNks3TkhMWEZNTzdCVTVYUlVYUUpVVDQzQVRHTExHMlJUVjNMTlVBXCJ9In0.cyAhZU--VJYcuOwwiRD4K8JgAHWN0EY2IXDd3p4jUgg"
}


# 生成 5 位随机字母数字字符串
def generate_random_str(length=5):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


# 循环执行 5 次
for i in range(1, 6):
    print(f"\n===== 第 {i} 次请求 =====")

    # 生成随机参数
    domain = generate_random_str(5)
    name = f"升级后-{generate_random_str(8)}"  # 升级后+8位随机串

    # 打印本次使用的值
    print(f"本次 email_domain_content: {domain}")

    # 请求体
    data = {
        "email_name": name,
        "email_domain_content": domain
    }

    # 发送请求（关闭SSL验证，因为是内网域名）
    try:
        response = requests.post(
            url=url,
            headers=headers,
            cookies=cookies,
            json=data,
            verify=False  # 关键：内网自签名证书必须关闭
        )

        print(f"状态码: {response.status_code}")
        print(f"响应内容: {response.text[:200]}...")  # 只打印前200字符

    except Exception as e:
        print(f"请求异常: {str(e)}")