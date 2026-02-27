#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试选中段落AI询问和流式输出功能"""
import requests
import json
import sys
import io
import time

# 设置标准输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"

def test_ask_ai():
    """测试Ask AI功能"""
    print("="*60)
    print("测试Ask AI功能")
    print("="*60)

    # 创建文档
    print("\n1. 创建测试文档...")
    response = requests.get(f"{BASE_URL}/", allow_redirects=False)
    doc_id = response.headers.get("location").split("/")[-1]
    print(f"   文档ID: {doc_id}")

    # 测试用例
    test_cases = [
        {
            "name": "询问文本主题",
            "operation": "ask_ai",
            "selected_text": """人工智能（AI）正在改变我们的生活方式。从智能手机到自动驾驶汽车，
AI技术无处不在。机器学习算法使计算机能够从数据中学习，深度学习则通过神经网络
模拟人脑的工作方式。""",
            "question": "这段文本的主要主题是什么？"
        },
        {
            "name": "询问技术细节",
            "operation": "ask_ai",
            "selected_text": """深度学习使用多层神经网络来处理数据。每一层都会提取不同级别的特征，
从简单的边缘和纹理到复杂的对象和概念。通过反向传播算法，网络可以自动调整权重
以最小化预测误差。""",
            "question": "深度学习是如何工作的？"
        },
        {
            "name": "解释文本",
            "operation": "explain",
            "selected_text": "梯度下降是一种优化算法，通过迭代地调整参数来最小化损失函数。",
            "detail_level": "detailed"
        },
        {
            "name": "翻译文本",
            "operation": "translate",
            "selected_text": "人工智能正在改变世界。",
            "target_language": "en"
        }
    ]

    # 执行测试
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. 测试: {test_case['name']}")
        print(f"   操作: {test_case['operation']}")
        print(f"   文本: {test_case['selected_text'][:50]}...")

        # 构建请求
        request_data = {
            "operation": test_case['operation'],
            "selected_text": test_case['selected_text'],
            "before_text": "",
            "after_text": "",
            "document_title": "AI技术研究"
        }

        # 添加操作特定参数
        if 'question' in test_case:
            request_data['question'] = test_case['question']
            print(f"   问题: {test_case['question']}")
        if 'detail_level' in test_case:
            request_data['detail_level'] = test_case['detail_level']
        if 'target_language' in test_case:
            request_data['target_language'] = test_case['target_language']

        try:
            response = requests.post(
                f"{BASE_URL}/api/doc/{doc_id}/inline-ai",
                json=request_data,
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                generated = result.get('generated_text', '')
                print(f"   ✓ 成功")
                print(f"   回答: {generated[:300]}...")
                if len(generated) > 300:
                    print(f"   (共{len(generated)}字符)")
            else:
                print(f"   ✗ 失败: {response.status_code}")
                print(f"   错误: {response.text}")

        except Exception as e:
            print(f"   ✗ 异常: {e}")

    print("\n" + "="*60)


def test_streaming():
    """测试流式输出功能"""
    print("\n" + "="*60)
    print("测试流式输出功能")
    print("="*60)

    # 创建文档
    print("\n1. 创建测试文档...")
    response = requests.get(f"{BASE_URL}/", allow_redirects=False)
    doc_id = response.headers.get("location").split("/")[-1]
    print(f"   文档ID: {doc_id}")

    # 测试用例
    test_cases = [
        {
            "name": "流式询问",
            "operation": "ask_ai",
            "selected_text": "机器学习是人工智能的一个分支，它使计算机能够从数据中学习。",
            "question": "机器学习有哪些主要类型？"
        },
        {
            "name": "流式解释",
            "operation": "explain",
            "selected_text": "神经网络是一种模仿人脑结构的计算模型。",
            "detail_level": "medium"
        },
        {
            "name": "流式改进",
            "operation": "improve",
            "selected_text": "这个方法很好，大家可以试试。",
            "focus": "style"
        }
    ]

    # 执行测试
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. 测试: {test_case['name']}")
        print(f"   操作: {test_case['operation']}")
        print(f"   文本: {test_case['selected_text'][:50]}...")

        # 构建请求
        request_data = {
            "operation": test_case['operation'],
            "selected_text": test_case['selected_text'],
            "before_text": "",
            "after_text": "",
            "document_title": "AI技术研究"
        }

        # 添加操作特定参数
        if 'question' in test_case:
            request_data['question'] = test_case['question']
            print(f"   问题: {test_case['question']}")
        if 'detail_level' in test_case:
            request_data['detail_level'] = test_case['detail_level']
        if 'focus' in test_case:
            request_data['focus'] = test_case['focus']

        try:
            print(f"   开始流式输出...")
            start_time = time.time()

            response = requests.post(
                f"{BASE_URL}/api/doc/{doc_id}/inline-ai/stream",
                json=request_data,
                stream=True,
                timeout=60
            )

            if response.status_code == 200:
                print(f"   ✓ 连接成功")
                event_count = 0
                current_event_name = None
                accumulated_text = ""

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
                            try:
                                data = json.loads(line_str[6:])
                                event_type = current_event_name or data.get('type', 'unknown')

                                if event_type == 'start':
                                    print(f"   [开始] 操作: {data.get('operation')}")
                                elif event_type == 'delta':
                                    content = data.get('content', '')
                                    accumulated_text = data.get('accumulated', accumulated_text)
                                    print(f"   [增量] {content}")
                                elif event_type == 'done':
                                    elapsed = time.time() - start_time
                                    print(f"   [完成] 耗时: {elapsed:.1f}秒")
                                    print(f"   完整内容: {data.get('content', '')[:200]}...")
                                    break
                                elif event_type == 'error':
                                    print(f"   [错误] {data.get('error')}")
                                    break

                                current_event_name = None

                            except json.JSONDecodeError as e:
                                print(f"   JSON解析错误: {e}")

                print(f"   总事件数: {event_count}")
            else:
                print(f"   ✗ 失败: {response.status_code}")
                print(f"   错误: {response.text}")

        except Exception as e:
            print(f"   ✗ 异常: {e}")

    print("\n" + "="*60)


if __name__ == "__main__":
    try:
        # 测试Ask AI功能
        test_ask_ai()

        # 测试流式输出
        test_streaming()

        print("\n" + "="*60)
        print("所有测试完成")
        print("="*60)

    except KeyboardInterrupt:
        print("\n\n测试被中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
