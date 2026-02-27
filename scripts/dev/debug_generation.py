#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调试长文档生成问题"""
import requests
import json
import time
import sys
import io

# 设置标准输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://127.0.0.1:8001"

def debug_long_generation():
    """调试长文档生成"""
    print("="*60)
    print("调试长文档生成")
    print("="*60)

    # 创建新文档
    print("\n1. 创建文档...")
    response = requests.get(f"{BASE_URL}/", allow_redirects=False)
    if response.status_code == 303:
        doc_url = response.headers.get("location")
        doc_id = doc_url.split("/")[-1]
        print(f"   文档ID: {doc_id}")
    else:
        print(f"   失败: {response.status_code}")
        return

    # 使用更简单的指令
    print("\n2. 开始生成 (使用简单指令)...")
    instruction = "写一篇关于Python编程语言的文章，包括历史、特点、应用领域和未来发展，约1500字。"

    print(f"   指令: {instruction}")
    print(f"   开始时间: {time.strftime('%H:%M:%S')}")

    response = requests.post(
        f"{BASE_URL}/api/doc/{doc_id}/generate/stream",
        json={"instruction": instruction},
        stream=True,
        timeout=300
    )

    if response.status_code != 200:
        print(f"   失败: {response.status_code}")
        print(f"   响应: {response.text}")
        return

    print("   生成开始，监控事件流...")
    start_time = time.time()
    last_event_time = start_time
    event_count = 0
    last_event_type = None
    current_event_name = None

    try:
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')

                # 解析event行
                if line_str.startswith('event: '):
                    current_event_name = line_str[7:].strip()
                    continue

                # 解析data行
                if line_str.startswith('data: '):
                    event_count += 1
                    current_time = time.time()
                    gap = current_time - last_event_time
                    last_event_time = current_time

                    try:
                        data = json.loads(line_str[6:])
                        event_type = current_event_name or data.get('type', 'unknown')
                        last_event_type = event_type

                        elapsed = current_time - start_time
                        print(f"   [{elapsed:6.1f}s] (+{gap:4.1f}s) {event_type}", end="")

                        if event_type == 'delta':
                            delta = data.get('delta', '')
                            print(f": {delta[:50]}...")
                        elif event_type == 'phase':
                            phase = data.get('phase', '')
                            print(f": {phase}")
                        elif event_type == 'state':
                            name = data.get('name', '')
                            phase = data.get('phase', '')
                            print(f": {name} - {phase}")
                        elif event_type == 'section':
                            section = data.get('section', '')
                            phase = data.get('phase', '')
                            print(f": {section} - {phase}")
                        elif event_type == 'section_start':
                            title = data.get('title', '')
                            print(f": {title}")
                        elif event_type == 'section_done':
                            title = data.get('title', '')
                            print(f": {title}")
                        elif event_type == 'final':
                            text = data.get('text', '')
                            print(f" - 完成! ({len(text)}字符)")
                            break
                        elif event_type == 'error':
                            error = data.get('error', '')
                            print(f": {error}")
                            break
                        else:
                            print()

                        # 重置event名称
                        current_event_name = None

                    except json.JSONDecodeError as e:
                        print(f"   JSON解析错误: {e}")

            # 检查是否长时间无响应
            if time.time() - last_event_time > 90:
                print(f"\n   ⚠ 警告: 已经{time.time() - last_event_time:.0f}秒没有收到事件")
                print(f"   最后事件类型: {last_event_type}")
                print(f"   总事件数: {event_count}")
                break

    except Exception as e:
        print(f"\n   异常: {e}")
        import traceback
        traceback.print_exc()

    total_time = time.time() - start_time
    print(f"\n3. 生成结束")
    print(f"   总耗时: {total_time:.1f}秒")
    print(f"   总事件数: {event_count}")

    # 获取最终文档
    print("\n4. 获取文档内容...")
    response = requests.get(f"{BASE_URL}/api/doc/{doc_id}")
    if response.status_code == 200:
        doc_data = response.json()
        text = doc_data.get('text', '')
        print(f"   文档长度: {len(text)} 字符")
        if text:
            print(f"   前200字符:\n   {text[:200]}...")
        else:
            print("   ⚠ 文档为空!")
    else:
        print(f"   获取失败: {response.status_code}")

    print(f"\n文档地址: {BASE_URL}/workbench/{doc_id}")

if __name__ == "__main__":
    try:
        debug_long_generation()
    except KeyboardInterrupt:
        print("\n\n被用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
