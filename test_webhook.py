import time
import hmac
import hashlib
import base64
import requests
import json

WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/9c7500f1-ebec-4ee1-b1a8-9e2dde340c2c"
SECRET = "pciLVTwg1bZzvNtIGtwAAg"

def gen_sign(secret, timestamp):
    # 拼接 timestamp + "\n" + secret
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    # 对 cipher 做 Base64 编码
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return sign

def send_message():
    timestamp = str(int(time.time()))
    sign = gen_sign(SECRET, timestamp)

    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "timestamp": timestamp,
        "sign": sign,
        "msg_type": "text",
        "content": {
            "text": "开启签名校验后的机器人测试成功！"
        }
    }

    response = requests.post(WEBHOOK_URL, headers=headers, data=json.dumps(payload))
    print("响应状态码:", response.status_code)
    print("响应内容:", response.text)

if __name__ == "__main__":
    send_message()