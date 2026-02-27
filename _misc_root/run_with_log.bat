@echo off
chcp 65001 >nul
cd /d d:\codes\writing-agent
.\.venv\Scripts\python -m uvicorn writing_agent.web.app_v2:app --host 127.0.0.1 --port 8000
