#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查SSE事件流格式"""
import requests
import time
import sys
import io

# 设置标准输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://127.0.0.1:8002"

def check_sse_format():
    """检查SSE事件流格式"""
    print("检查SSE事件流格式\n")

    # 创建文档
    response = requests.get(f"{BASE_URL}/", allow_redirects=False)
    doc_id = response.headers.get("location").split("/")[-1]
    print(f"文档ID: {doc_id}\n")

    # 开始生成
    instruction = "写一段关于人工智能的简短介绍，约200字。"

    response = requests.post(
        f"{BASE_URL}/api/doc/{doc_id}/generate/stream",
        json={"instruction": instruction},
        stream=True,
        timeout=120
    )

    print("原始事件流:\n" + "="*60)
    line_count = 0
    for line in response.iter_lines():
        line_count += 1
        if line:
            line_str = line.decode('utf-8')
            print(f"[{line_count:3d}] {repr(line_str)}")

            if line_count > 50:  # 只显示前50行
                print("... (省略更多行)")
                break
        else:
            print(f"[{line_count:3d}] (空行)")

if __name__ == "__main__":
    try:
        check_sse_format()
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
