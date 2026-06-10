import http.client
import json
import time
import logging
import uuid

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 请求配置
HOST = "test.ifeilian.cn"
PORT = 8443
URL = "/api/admin/v2/dynamic_security/dlp/sensitive_pattern/create?os=web"
METHOD = "POST"
EXECUTE_TIMES = 2000
INTERVAL = 0.2

# 生成 10 字符唯一名称
def generate_name():
    return str(uuid.uuid4()).replace('-', '')[:10]

# 请求头（完全按照你的 curl）
headers = {
    'accept': '*/*',
    'accept-language': 'zh-CN',
    'admin-csrf-token': 'AssSDlPYaEPxqJybDsORNxpnGwYbbakaYOJlvgRK',
    'cache-control': 'no-cache',
    'content-type': 'application/json',
    'csrf-token': 'hpIwNnQUMGVlEWBjSIdcMdftCgIrFbZdPsxGBTDw',
    'origin': 'https://test.ifeilian.cn:8443',
    'pragma': 'no-cache',
    'priority': 'u=1, i',
    'referer': 'https://test.ifeilian.cn:8443/admin/security_edlp/data_recognition?tab=edlp%2Fdata_identify%2Fsensitive_lib',
    'sec-ch-ua': '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
    'x-fe-version': '3.3.1.12780',
    'x-tenant-timezone': 'Asia/Shanghai',
    'x-version-check': '0',
    'Cookie': 'unit-open-id=un_Y3bErj7gjLOk; admin-csrf-token=AssSDlPYaEPxqJybDsORNxpnGwYbbakaYOJlvgRK; admin-session=MTc3MzExMDkzMHxOd3dBTkZnMlJreExRa0pHV0ZaQlQwWXlSbGN5V1RRME1razNWRVJTV2sxV1ZqTlJOVlpFTkVOTFZFZFdSRFpEVmsxTFVWcENRMUU9fMdCwesYm1HRULa8aN6tnGYQ2iHneYLEdlOjxBgTTaMW; ops-csrf-token=uRgnmUSZKqmIQXTuKdihBCingxvWNglStuuPqaCt; ops_session=MTc3MzI5ODMzNHxOd3dBTkROTFJqZEZUVmxIV0U5UVRqTlNNbGRYVlVsSlJGTlFNa1pOVXpkTlIweExVRk5DVkVWV05VZEpTRlV6TnpOV1FWUkZWMEU9fFz55ysv_2SXn-QXFd13ku4ndupx-v01F5F2NFfwu9VY; plugin-token=eyJhbGciOiJIUzINiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIxNjU0MyIsImV4cCI6MTc3NDUxNDQ0MiwidmFsIjoie1wib3Blbl9pZFwiOlwib3VfMmpyeU40RGdPblwiLFwic2Vzc2lvbl9pZFwiOlwiRkZQQlNFVTNIWTdUWUxBWkFKNjI2REE3QjVBTEhZV1FWRzRNUU1BTkJMUFNUWE5HQ0tRQVwifSJ9.FWpz00n_9he5xueIgoS3It73lS0baWLsoQoBZ7aTk1w; csrf-token=hpIwNnQUMGVlEWBjSIdcMdftCgIrFbZdPsxGBTDw; refer_next=%2Fadmin%2Fsecurity_edlp%2Finvestigation%3Fend%3D1773417599%26start%3D1772121600%26sub_tab%3Dfile%26tab%3Dedlp%252Fevent%252Falarm%26user_ids%3D17065; session=MTc3MzQwMjgzMnxOd3dBTkU4elRVMVlXbEpGVmswM1F6UktTalZaU3pKWFVrWkdRa3haTmtZM1ZsZENXVTlKUmpKTFFWUkVSVU5OV1VwUlJqTTBTMUU9fIkqxEnSJWPj5zvqLmt5hywtQxqqx0l6VcA_X-AiCTuf'
}

def send_request():
    try:
        # 每次生成唯一 name
        payload = json.dumps({
            "class": 3,
            "name": generate_name(),
            "value": "1",
            "min_match_times": 1
        })

        conn = http.client.HTTPSConnection(HOST, PORT, timeout=10)
        conn.request(METHOD, URL, payload, headers)
        res = conn.getresponse()
        data = res.read().decode("utf-8")
        conn.close()

        return {
            "success": True,
            "code": res.status,
            "resp": data
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == '__main__':
    success = 0
    fail = 0
    logging.info(f"开始循环执行 {EXECUTE_TIMES} 次请求")

    for i in range(1, EXECUTE_TIMES + 1):
        logging.info(f"第 {i} 次请求中...")
        res = send_request()

        if res["success"]:
            success += 1
            logging.info(f"第 {i} 次成功 | 状态码：{res['code']}")
        else:
            fail += 1
            logging.error(f"第 {i} 次失败：{res['error']}")

        if i < EXECUTE_TIMES:
            time.sleep(INTERVAL)

    logging.info("=" * 50)
    logging.info(f"执行完毕 | 总计：{EXECUTE_TIMES} 次")
    logging.info(f"成功：{success} 次 | 失败：{fail} 次")