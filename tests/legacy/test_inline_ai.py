#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试内联AI操作功能"""
import requests
import json
import sys
import io

# 设置标准输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"

def test_inline_ai():
    """测试内联AI操作"""
    print("="*60)
    print("测试内联AI操作功能")
    print("="*60)

    # 创建文档
    print("\n1. 创建测试文档...")
    response = requests.get(f"{BASE_URL}/", allow_redirects=False)
    doc_id = response.headers.get("location").split("/")[-1]
    print(f"   文档ID: {doc_id}")

    # 测试用例
    test_cases = [
        {
            "name": "继续写作",
            "operation": "continue",
            "selected_text": "",
            "before_text": "人工智能（AI）正在改变我们的生活方式。从智能手机到自动驾驶汽车，AI技术无处不在。",
            "after_text": "",
            "params": {"target_words": 100}
        },
        {
            "name": "改进文本",
            "operation": "improve",
            "selected_text": "这个系统很好用，功能也很多，我觉得挺不错的。",
            "before_text": "",
            "after_text": "",
            "params": {"focus": "style"}
        },
        {
            "name": "总结段落",
            "operation": "summarize",
            "selected_text": """机器学习是人工智能的一个分支，它使计算机能够从数据中学习并做出决策，而无需明确编程。
机器学习算法通过分析大量数据来识别模式和规律，然后使用这些模式来预测未来的结果或做出决策。
常见的机器学习类型包括监督学习、无监督学习和强化学习。监督学习使用标记的数据进行训练，
无监督学习从未标记的数据中发现模式，而强化学习通过试错来学习最佳行为。""",
            "before_text": "",
            "after_text": "",
            "params": {"max_sentences": 2}
        },
        {
            "name": "扩展内容",
            "operation": "expand",
            "selected_text": "深度学习是机器学习的一个子集，使用神经网络进行学习。",
            "before_text": "",
            "after_text": "",
            "params": {"expansion_ratio": 3.0}
        },
        {
            "name": "改变语气",
            "operation": "change_tone",
            "selected_text": "这个方法挺好的，大家可以试试看。",
            "before_text": "",
            "after_text": "",
            "params": {"target_tone": "academic"}
        },
        {
            "name": "简化文本",
            "operation": "simplify",
            "selected_text": "该算法采用了基于梯度下降的优化方法，通过反向传播机制来调整神经网络中的权重参数，从而最小化损失函数。",
            "before_text": "",
            "after_text": "",
            "params": {}
        }
    ]

    # 执行测试
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. 测试: {test_case['name']}")
        print(f"   操作: {test_case['operation']}")

        if test_case['selected_text']:
            print(f"   原文: {test_case['selected_text'][:80]}...")

        # 构建请求
        request_data = {
            "operation": test_case['operation'],
            "selected_text": test_case['selected_text'],
            "before_text": test_case['before_text'],
            "after_text": test_case['after_text'],
            "document_title": "AI技术研究报告"
        }
        request_data.update(test_case['params'])

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
                print(f"   生成内容: {generated[:200]}...")
                if len(generated) > 200:
                    print(f"   (共{len(generated)}字符)")
            else:
                print(f"   ✗ 失败: {response.status_code}")
                print(f"   错误: {response.text}")

        except Exception as e:
            print(f"   ✗ 异常: {e}")

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)

if __name__ == "__main__":
    try:
        test_inline_ai()
    except KeyboardInterrupt:
        print("\n\n测试被中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
