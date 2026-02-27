#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试文档生成功能"""
import requests
import json
import time
import sys
import io

# 设置标准输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://127.0.0.1:8002"

def test_document_generation():
    """测试完整的文档生成流程"""

    # 1. 创建新文档（访问首页会自动创建）
    print("1. 创建新文档...")
    response = requests.get(f"{BASE_URL}/", allow_redirects=False)
    if response.status_code == 303:
        doc_url = response.headers.get("location")
        doc_id = doc_url.split("/")[-1]
        print(f"   ✓ 文档ID: {doc_id}")
    else:
        print(f"   ✗ 创建失败: {response.status_code}")
        return

    # 2. 设置生成偏好
    print("\n2. 设置生成偏好...")
    settings_data = {
        "generation_prefs": {
            "purpose": "研究报告",
            "target_length_mode": "word_count",
            "target_word_count": 2000,
            "extra_requirements": "使用学术化的语言，包含具体案例"
        }
    }

    response = requests.post(
        f"{BASE_URL}/api/doc/{doc_id}/settings",
        json=settings_data
    )

    if response.status_code == 200:
        print(f"   ✓ 设置成功")
    else:
        print(f"   ✗ 设置失败: {response.status_code}")

    # 3. 开始生成文档（使用流式API）
    print("\n3. 开始生成文档...")
    print("   (这可能需要几分钟时间...)")

    # 生成指令
    instruction = """请生成一篇关于"人工智能在教育领域的应用研究"的报告，要求：
1. 包含研究背景和意义
2. 分析当前AI在教育中的应用现状
3. 介绍具体的技术方案和案例
4. 展望未来发展趋势
5. 字数约2000字
6. 使用学术化的语言风格"""

    response = requests.post(
        f"{BASE_URL}/api/doc/{doc_id}/generate/stream",
        json={"instruction": instruction},
        stream=True
    )

    if response.status_code == 200:
        print("   ✓ 生成开始")
        event_count = 0
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    event_count += 1
                    try:
                        data = json.loads(line_str[6:])
                        event_type = data.get('type', 'unknown')

                        if event_type == 'phase':
                            phase = data.get('phase', '')
                            print(f"   → 阶段: {phase}")
                        elif event_type == 'section_start':
                            title = data.get('title', '')
                            print(f"   → 开始生成: {title}")
                        elif event_type == 'section_done':
                            title = data.get('title', '')
                            print(f"   ✓ 完成: {title}")
                        elif event_type == 'done':
                            print(f"   ✓ 文档生成完成！")
                            break
                        elif event_type == 'error':
                            error = data.get('error', '')
                            print(f"   ✗ 错误: {error}")
                            break
                    except json.JSONDecodeError:
                        pass

        print(f"   总共接收 {event_count} 个事件")
    else:
        print(f"   ✗ 生成失败: {response.status_code}")
        print(f"   响应: {response.text}")
        return

    # 4. 获取生成的文档内容
    print("\n4. 获取文档内容...")
    response = requests.get(f"{BASE_URL}/api/doc/{doc_id}")

    if response.status_code == 200:
        doc_data = response.json()
        text = doc_data.get('text', '')
        word_count = len(text)
        print(f"   ✓ 文档长度: {word_count} 字符")
        print(f"   前100字符: {text[:100]}...")
    else:
        print(f"   ✗ 获取失败: {response.status_code}")

    # 5. 导出为DOCX
    print("\n5. 导出DOCX文档...")
    response = requests.get(f"{BASE_URL}/download/{doc_id}.docx")

    if response.status_code == 200:
        filename = f"test_output_{doc_id}.docx"
        with open(filename, 'wb') as f:
            f.write(response.content)
        print(f"   ✓ 导出成功: {filename}")
        print(f"   文件大小: {len(response.content)} 字节")
    else:
        print(f"   ✗ 导出失败: {response.status_code}")
        print(f"   响应: {response.text}")

    print(f"\n✅ 测试完成！文档ID: {doc_id}")
    print(f"   访问地址: {BASE_URL}/workbench/{doc_id}")

if __name__ == "__main__":
    try:
        test_document_generation()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
