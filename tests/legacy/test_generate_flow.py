#!/usr/bin/env python3
"""端到端生成流程测试，诊断超时问题"""
import json
import time
import urllib.request
import urllib.parse
from urllib.error import URLError, HTTPError

BASE_URL = "http://127.0.0.1:8000"

def test_generate():
    """测试完整生成流程"""
    print("=== 开始生成流程测试 ===\n")
    
    # 1. 创建新文档
    print("[1/5] 创建新文档...")
    try:
        req = urllib.request.Request(f"{BASE_URL}/workbench2?new=1", method="GET")
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode('utf-8')
        # 从HTML中提取doc_id
        import re
        match = re.search(r'data-doc-id="([^"]+)"', html)
        if not match:
            print("✗ 无法从HTML中提取doc_id")
            return False
        doc_id = match.group(1)
        print(f"✓ 文档创建成功: {doc_id}\n")
    except Exception as e:
        print(f"✗ 创建文档失败: {e}")
        return False
    
    # 2. 提交生成指令
    print("[2/5] 提交生成指令...")
    instruction = "生成一个关于人工智能的技术报告"
    payload = json.dumps({
        "instruction": instruction,
        "title": "",
        "total_chars": 2000
    }).encode('utf-8')
    
    try:
        req = urllib.request.Request(
            f"{BASE_URL}/api/doc/{doc_id}/generate",
            data=payload,
            headers={'Content-Type': 'application/json'},
            method="POST"
        )
        
        print(f"  指令: {instruction}")
        print(f"  目标字数: 2000")
        print("  等待SSE流响应...\n")
        
        start_time = time.time()
        resp = urllib.request.urlopen(req, timeout=180)  # 3分钟超时
        
        event_count = 0
        last_event = None
        
        # 读取SSE流
        buffer = b''
        while True:
            chunk = resp.read(1024)
            if not chunk:
                break
            
            buffer += chunk
            lines = buffer.split(b'\n')
            buffer = lines[-1]  # 保留未完成的行
            
            for line in lines[:-1]:
                line = line.decode('utf-8', errors='ignore').strip()
                if not line or line.startswith(':'):
                    continue
                
                if line.startswith('event:'):
                    last_event = line[6:].strip()
                elif line.startswith('data:'):
                    data_str = line[5:].strip()
                    event_count += 1
                    
                    try:
                        data = json.loads(data_str)
                        elapsed = time.time() - start_time
                        
                        if last_event == 'plan':
                            print(f"[{elapsed:.1f}s] 事件#{event_count}: plan")
                            print(f"  标题: {data.get('title', 'N/A')}")
                            print(f"  章节数: {len(data.get('sections', []))}")
                        
                        elif last_event == 'analysis':
                            print(f"[{elapsed:.1f}s] 事件#{event_count}: analysis")
                            print(f"  主题: {data.get('topic', 'N/A')}")
                        
                        elif last_event == 'section_start':
                            title = data.get('title', 'N/A')
                            print(f"[{elapsed:.1f}s] 事件#{event_count}: section_start - {title}")
                        
                        elif last_event == 'section_done':
                            title = data.get('title', 'N/A')
                            chars = data.get('chars', 0)
                            print(f"[{elapsed:.1f}s] 事件#{event_count}: section_done - {title} ({chars}字)")
                        
                        elif last_event == 'done':
                            total_chars = data.get('total_chars', 0)
                            print(f"\n[{elapsed:.1f}s] ✓ 生成完成！总字数: {total_chars}")
                            return True
                        
                        elif last_event == 'error':
                            error_msg = data.get('error', 'Unknown error')
                            print(f"\n[{elapsed:.1f}s] ✗ 生成失败: {error_msg}")
                            return False
                        
                        elif last_event == 'progress':
                            pct = data.get('percent', 0)
                            print(f"[{elapsed:.1f}s] 进度: {pct}%", end='\r')
                        
                    except json.JSONDecodeError:
                        pass
        
        elapsed = time.time() - start_time
        print(f"\n[{elapsed:.1f}s] ✗ SSE流意外结束（共{event_count}个事件）")
        return False
        
    except URLError as e:
        elapsed = time.time() - start_time
        print(f"\n[{elapsed:.1f}s] ✗ 网络错误: {e}")
        return False
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n[{elapsed:.1f}s] ✗ 未知错误: {e}")
        return False

if __name__ == "__main__":
    success = test_generate()
    print(f"\n{'='*50}")
    print(f"测试结果: {'成功' if success else '失败'}")
    print(f"{'='*50}")
