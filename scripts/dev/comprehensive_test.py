#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全面测试写作Agent系统"""
import requests
import json
import time
import sys
import io

# 设置标准输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://127.0.0.1:8002"

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.issues = []

    def add_pass(self, test_name):
        self.passed.append(test_name)
        print(f"✓ {test_name}")

    def add_fail(self, test_name, error):
        self.failed.append((test_name, error))
        print(f"✗ {test_name}: {error}")

    def add_issue(self, issue):
        self.issues.append(issue)
        print(f"⚠ 发现问题: {issue}")

    def summary(self):
        print("\n" + "="*60)
        print("测试总结")
        print("="*60)
        print(f"通过: {len(self.passed)}")
        print(f"失败: {len(self.failed)}")
        print(f"问题: {len(self.issues)}")

        if self.failed:
            print("\n失败的测试:")
            for name, error in self.failed:
                print(f"  - {name}: {error}")

        if self.issues:
            print("\n发现的问题:")
            for i, issue in enumerate(self.issues, 1):
                print(f"  {i}. {issue}")

results = TestResults()

def test_server_health():
    """测试服务器健康状态"""
    print("\n[测试1] 服务器健康检查")
    try:
        response = requests.get(f"{BASE_URL}/", allow_redirects=False, timeout=5)
        if response.status_code == 303:
            results.add_pass("服务器响应正常")
            return True
        else:
            results.add_fail("服务器响应", f"状态码 {response.status_code}")
            return False
    except Exception as e:
        results.add_fail("服务器连接", str(e))
        return False

def test_document_creation():
    """测试文档创建"""
    print("\n[测试2] 文档创建")
    try:
        response = requests.get(f"{BASE_URL}/", allow_redirects=False)
        if response.status_code == 303:
            doc_url = response.headers.get("location")
            doc_id = doc_url.split("/")[-1]
            results.add_pass("文档创建成功")
            return doc_id
        else:
            results.add_fail("文档创建", f"状态码 {response.status_code}")
            return None
    except Exception as e:
        results.add_fail("文档创建", str(e))
        return None

def test_document_api(doc_id):
    """测试文档API"""
    print("\n[测试3] 文档API")
    try:
        response = requests.get(f"{BASE_URL}/api/doc/{doc_id}")
        if response.status_code == 200:
            data = response.json()
            if 'id' in data and data['id'] == doc_id:
                results.add_pass("文档API正常")
                return True
            else:
                results.add_fail("文档API", "返回数据格式错误")
                return False
        else:
            results.add_fail("文档API", f"状态码 {response.status_code}")
            return False
    except Exception as e:
        results.add_fail("文档API", str(e))
        return False

def test_short_generation(doc_id):
    """测试短文档生成"""
    print("\n[测试4] 短文档生成 (约500字)")
    try:
        instruction = "写一篇关于Python编程语言的简短介绍，约500字。"

        response = requests.post(
            f"{BASE_URL}/api/doc/{doc_id}/generate/stream",
            json={"instruction": instruction},
            stream=True,
            timeout=120
        )

        if response.status_code == 200:
            events = []
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        try:
                            data = json.loads(line_str[6:])
                            events.append(data)
                            if data.get('type') == 'done':
                                break
                            elif data.get('type') == 'error':
                                results.add_fail("短文档生成", data.get('error', '未知错误'))
                                return False
                        except:
                            pass

            # 检查生成的内容
            doc_response = requests.get(f"{BASE_URL}/api/doc/{doc_id}")
            if doc_response.status_code == 200:
                doc_data = doc_response.json()
                text = doc_data.get('text', '')
                char_count = len(text)

                if char_count > 100:
                    results.add_pass(f"短文档生成成功 ({char_count}字符)")
                    if char_count < 300:
                        results.add_issue(f"生成内容偏短: {char_count}字符 (期望约500字)")
                    return True
                else:
                    results.add_fail("短文档生成", f"内容太短: {char_count}字符")
                    return False
        else:
            results.add_fail("短文档生成", f"状态码 {response.status_code}")
            return False
    except Exception as e:
        results.add_fail("短文档生成", str(e))
        return False

def test_medium_generation():
    """测试中等长度文档生成"""
    print("\n[测试5] 中等长度文档生成 (约2000字)")

    # 创建新文档
    doc_id = test_document_creation()
    if not doc_id:
        return False

    try:
        instruction = """写一篇关于"机器学习在医疗诊断中的应用"的研究报告，要求：
1. 包含背景介绍
2. 技术原理说明
3. 应用案例分析
4. 挑战与展望
5. 总字数约2000字"""

        response = requests.post(
            f"{BASE_URL}/api/doc/{doc_id}/generate/stream",
            json={"instruction": instruction},
            stream=True,
            timeout=300  # 增加到300秒
        )

        if response.status_code == 200:
            start_time = time.time()
            events = []
            last_event_time = start_time

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        try:
                            data = json.loads(line_str[6:])
                            events.append(data)
                            last_event_time = time.time()

                            if data.get('type') == 'done':
                                break
                            elif data.get('type') == 'error':
                                results.add_fail("中等文档生成", data.get('error', '未知错误'))
                                return False
                        except:
                            pass

                # 检查是否超时
                if time.time() - last_event_time > 60:
                    results.add_fail("中等文档生成", "生成超时(60秒无响应)")
                    return False

            generation_time = time.time() - start_time

            # 检查生成的内容
            doc_response = requests.get(f"{BASE_URL}/api/doc/{doc_id}")
            if doc_response.status_code == 200:
                doc_data = doc_response.json()
                text = doc_data.get('text', '')
                char_count = len(text)

                if char_count > 500:
                    results.add_pass(f"中等文档生成成功 ({char_count}字符, 耗时{generation_time:.1f}秒)")

                    if char_count < 1000:
                        results.add_issue(f"生成内容偏短: {char_count}字符 (期望约2000字)")
                    if generation_time > 120:
                        results.add_issue(f"生成时间较长: {generation_time:.1f}秒")

                    return True
                else:
                    results.add_fail("中等文档生成", f"内容太短: {char_count}字符")
                    return False
        else:
            results.add_fail("中等文档生成", f"状态码 {response.status_code}")
            return False
    except Exception as e:
        results.add_fail("中等文档生成", str(e))
        return False

def test_docx_export(doc_id):
    """测试DOCX导出"""
    print("\n[测试6] DOCX导出")
    try:
        response = requests.get(f"{BASE_URL}/download/{doc_id}.docx", timeout=30)

        if response.status_code == 200:
            content = response.content
            file_size = len(content)

            # 检查文件大小
            if file_size < 1000:
                results.add_fail("DOCX导出", f"文件太小: {file_size}字节")
                return False

            # 检查DOCX文件头
            if content[:4] == b'PK\x03\x04':
                results.add_pass(f"DOCX导出成功 ({file_size}字节)")

                # 保存文件用于手动检查
                filename = f"test_export_{doc_id}.docx"
                with open(filename, 'wb') as f:
                    f.write(content)
                print(f"   已保存到: {filename}")

                return True
            else:
                results.add_fail("DOCX导出", "文件格式不正确")
                return False
        else:
            results.add_fail("DOCX导出", f"状态码 {response.status_code}")
            return False
    except Exception as e:
        results.add_fail("DOCX导出", str(e))
        return False

def test_document_settings(doc_id):
    """测试文档设置"""
    print("\n[测试7] 文档设置")
    try:
        settings_data = {
            "generation_prefs": {
                "purpose": "测试报告",
                "target_length_mode": "word_count",
                "target_word_count": 1000,
                "extra_requirements": "使用简洁的语言"
            }
        }

        response = requests.post(
            f"{BASE_URL}/api/doc/{doc_id}/settings",
            json=settings_data
        )

        if response.status_code == 200:
            # 验证设置是否保存
            doc_response = requests.get(f"{BASE_URL}/api/doc/{doc_id}")
            if doc_response.status_code == 200:
                doc_data = doc_response.json()
                prefs = doc_data.get('generation_prefs', {})

                if prefs.get('target_word_count') == 1000:
                    results.add_pass("文档设置保存成功")
                    return True
                else:
                    results.add_fail("文档设置", "设置未正确保存")
                    return False
        else:
            results.add_fail("文档设置", f"状态码 {response.status_code}")
            return False
    except Exception as e:
        results.add_fail("文档设置", str(e))
        return False

def test_error_handling():
    """测试错误处理"""
    print("\n[测试8] 错误处理")
    passed = 0
    total = 3

    # 测试不存在的文档
    try:
        response = requests.get(f"{BASE_URL}/api/doc/nonexistent")
        if response.status_code == 404:
            passed += 1
            print("  ✓ 不存在的文档返回404")
        else:
            print(f"  ✗ 不存在的文档应返回404，实际: {response.status_code}")
    except Exception as e:
        print(f"  ✗ 测试失败: {e}")

    # 测试空指令
    try:
        doc_id = test_document_creation()
        if doc_id:
            response = requests.post(
                f"{BASE_URL}/api/doc/{doc_id}/generate/stream",
                json={"instruction": ""},
                stream=True
            )
            if response.status_code == 400:
                passed += 1
                print("  ✓ 空指令返回400")
            else:
                print(f"  ✗ 空指令应返回400，实际: {response.status_code}")
    except Exception as e:
        print(f"  ✗ 测试失败: {e}")

    # 测试无效的导出
    try:
        response = requests.get(f"{BASE_URL}/download/invalid.docx")
        if response.status_code in [404, 500]:
            passed += 1
            print("  ✓ 无效导出返回错误")
        else:
            print(f"  ✗ 无效导出应返回错误，实际: {response.status_code}")
    except Exception as e:
        print(f"  ✗ 测试失败: {e}")

    if passed == total:
        results.add_pass(f"错误处理测试 ({passed}/{total})")
        return True
    else:
        results.add_fail("错误处理测试", f"只通过 {passed}/{total}")
        return False

def run_all_tests():
    """运行所有测试"""
    print("="*60)
    print("开始全面测试写作Agent系统")
    print("="*60)

    # 测试1: 服务器健康
    if not test_server_health():
        print("\n❌ 服务器未运行，终止测试")
        return

    # 测试2-3: 文档创建和API
    doc_id = test_document_creation()
    if doc_id:
        test_document_api(doc_id)
        test_document_settings(doc_id)
        test_short_generation(doc_id)
        test_docx_export(doc_id)

    # 测试5: 中等长度文档
    test_medium_generation()

    # 测试8: 错误处理
    test_error_handling()

    # 显示总结
    results.summary()

if __name__ == "__main__":
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        results.summary()
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        results.summary()
