# 去中心化AI Agent运行环境设计文档

## 构建一个去中心化的AI Agent运行环境，支持异构Agent（Codex、Claude Code、GPT-4等）的注册、发现、协作与通信，实现真正意义上的多Agent协同工作流

---

## 1. 系统概述

### 1.1 设计目标

构建一个去中心化的多Agent协作平台，实现以下核心能力：

- **异构Agent支持**：无缝集成Codex、Claude Code、GPT-4、本地LLM等不同类型Agent
- **去中心化架构**：无单点故障，Agent可动态加入/离开网络
- **自主协作**：Agent之间可自主发现、协商任务、分工合作
- **安全通信**：端到端加密，身份验证，权限控制
- **可扩展性**：支持新类型Agent快速接入

### 1.2 核心特性

| 特性 | 描述 |
|------|------|
| 去中心化 | 基于 gossip 协议的 P2P 网络，无中心化协调器 |
| 异构兼容 | 统一Agent抽象接口，屏蔽底层差异 |
| 动态发现 | mDNS + DHT 混合服务发现机制 |
| 智能路由 | 基于能力描述的任务自动分派 |
| 容错机制 | 心跳检测、自动故障转移、状态快照 |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Network Layer                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐            │
│  │  Codex  │  │ Claude  │  │  GPT-4  │  │ Local   │            │
│  │  Agent  │  │  Code   │  │  Agent  │  │  LLM    │            │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘            │
│       │            │            │            │                  │
│       └────────────┴────────────┴────────────┘                  │
│                    │                                             │
│              ┌─────┴─────┐                                       │
│              │  P2P Mesh  │  ← Gossip Protocol                   │
│              │  Network   │                                       │
│              └─────┬─────┘                                       │
│                    │                                             │
│  ┌─────────────────┼─────────────────┐                          │
│  │                 │                 │                          │
│  ▼                 ▼                 ▼                          │
│ ┌────────┐    ┌────────┐    ┌────────┐                         │
│ │Service │    │ Task   │    │Message │                         │
│ │Discovery│   │Router  │    │Queue   │                         │
│ └────────┘    └────────┘    └────────┘                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Orchestration Layer                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Workflow  │  │   Consensus │  │   State     │             │
│  │   Engine    │  │   Manager   │  │   Manager   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

#### 2.2.1 Agent抽象层

```python
# agent/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Any, AsyncIterator
import uuid

@dataclass
class AgentCapability:
    """Agent能力描述"""
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema
    output_schema: Dict[str, Any]
    cost_per_token: float
    max_context_length: int
    supported_languages: List[str]

@dataclass
class AgentIdentity:
    """Agent身份标识"""
    id: str
    name: str
    type: str  # "codex", "claude", "gpt4", "custom"
    version: str
    public_key: str
    endpoint: str  # 通信地址
    capabilities: List[AgentCapability]
    metadata: Dict[str, Any]

class BaseAgent(ABC):
    """Agent抽象基类"""
    
    def __init__(self, identity: AgentIdentity):
        self.identity = identity
        self.peers: Dict[str, AgentIdentity] = {}  # 已发现的 peers
        self.message_handlers: Dict[str, callable] = {}
        
    @abstractmethod
    async def execute(self, task: Dict[str, Any], context: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        """执行具体任务，返回流式结果"""
        pass
    
    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """对话接口"""
        pass
    
    async def send_message(self, target_id: str, message_type: str, payload: Dict[str, Any]):
        """向指定Agent发送消息"""
        # 通过P2P网络发送
        pass
    
    async def broadcast(self, message_type: str, payload: Dict[str, Any]):
        """广播消息到网络"""
        pass
    
    def register_handler(self, message_type: str, handler: callable):
        """注册消息处理器"""
        self.message_handlers[message_type] = handler
```

#### 2.2.2 P2P网络层

```python
# network/p2p.py
import asyncio
from typing import Set, Dict
import hashlib

class P2PNetwork:
    """去中心化P2P网络管理"""
    
    def __init__(self, node_id: str, listen_addr: str):
        self.node_id = node_id
        self.listen_addr = listen_addr
        self.peers: Dict[str, PeerConnection] = {}
        self.message_router = MessageRouter()
        self.gossip_protocol = GossipProtocol()
        
    async def start(self):
        """启动P2P节点"""
        # 1. 启动监听
        await self._start_listener()
        # 2. 启动 gossip 协议
        await self.gossip_protocol.start()
        # 3. 启动服务发现
        await self._start_service_discovery()
        
    async def join_network(self, bootstrap_nodes: List[str]):
        """通过引导节点加入网络"""
        for addr in bootstrap_nodes:
            try:
                peer = await self._connect_peer(addr)
                await self._perform_handshake(peer)
            except Exception as e:
                logger.warning(f"Failed to connect bootstrap node {addr}: {e}")
                
    async def send_to_peer(self, peer_id: str, message: Message):
        """向指定peer发送消息"""
        if peer_id not in self.peers:
            # 通过DHT查找路由
            route = await self._find_route(peer_id)
            if not route:
                raise PeerNotFoundError(peer_id)
            # 通过中间节点转发
            await self._forward_message(route, message)
        else:
            await self.peers[peer_id].send(message)
            
    async def broadcast(self, message: Message, ttl: int = 3):
        """Gossip广播消息"""
        await self.gossip_protocol.broadcast(message, ttl)

class GossipProtocol:
    """Gossip协议实现 - 用于消息传播和成员发现"""
    
    def __init__(self):
        self.seen_messages: Set[str] = set()  # 防重复
        self.fanout = 3  # 每次随机选择3个peer转发
        
    async def broadcast(self, message: Message, ttl: int):
        """传播消息"""
        msg_hash = self._hash_message(message)
        if msg_hash in self.seen_messages:
            return
        self.seen_messages.add(msg_hash)
        
        if ttl <= 0:
            return
            
        # 随机选择 fanout 个 peer
        peers = self._random_peers(self.fanout)
        for peer in peers:
            asyncio.create_task(peer.send(message.with_ttl(ttl - 1)))
```

#### 2.2.3 服务发现模块

```python
# discovery/service_discovery.py
import zeroconf
import asyncio
from typing import Callable

class HybridServiceDiscovery:
    """混合服务发现：mDNS局域网 + DHT广域网"""
    
    def __init__(self, node_id: str, on_peer_discovered: Callable):
        self.node_id = node_id
        self.on_peer_discovered = on_peer_discovered
        self.mdns = MDNSDiscovery()
        self.dht = DHTDiscovery()
        self.local_peers: Set[str] = set()
        self.global_peers: Set[str] = set()
        
    async def start(self):
        """启动服务发现"""
        # 启动mDNS（局域网）
        await self.mdns.start(
            service_type="_agent._tcp.local.",
            on_discovered=self._handle_local_peer
        )
        # 启动DHT（广域网）
        await self.dht.start(
            bootstrap_nodes=BOOTSTRAP_NODES,
            on_discovered=self._handle_global_peer
        )
        
    async def announce(self, agent_info: AgentIdentity):
        """宣布自身服务"""
        # mDNS广播
        await self.mdns.register_service(
            name=f"{agent_info.name}.{agent_info.id[:8]}",
            port=extract_port(agent_info.endpoint),
            properties={
                "id": agent_info.id,
                "type": agent_info.type,
                "capabilities": json.dumps([c.name for c in agent_info.capabilities])
            }
        )
        # DHT存储
        key = f"agent:{agent_info.id}"
        await self.dht.put(key, agent_info.to_json())
        
    async def find_agents_by_capability(self, capability: str) -> List[AgentIdentity]:
        """按能力搜索Agent"""
        results = []
        # 本地搜索
        results.extend(await self.mdns.find_by_capability(capability))
        # DHT搜索
        results.extend(await self.dht.find_by_capability(capability))
        return results
```

#### 2.2.4 任务路由与编排

```python
# orchestration/task_router.py
from typing import List, Optional
import numpy as np

class TaskRouter:
    """智能任务路由 - 基于能力和负载选择最优Agent"""
    
    def __init__(self):
        self.agents: Dict[str, AgentStatus] = {}
        self.capability_index: Dict[str, Set[str]] = {}  # capability -> agent_ids
        
    async def route_task(self, task: Task) -> Optional[str]:
        """为任务选择最优Agent"""
        required_caps = task.required_capabilities
        
        # 1. 筛选有能力的Agent
        candidates = self._find_capable_agents(required_caps)
        if not candidates:
            return None
            
        # 2. 评分排序
        scored = []
        for agent_id in candidates:
            score = self._score_agent(agent_id, task)
            scored.append((agent_id, score))
            
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0] if scored else None
        
    def _score_agent(self, agent_id: str, task: Task) -> float:
        """综合评分Agent"""
        agent = self.agents[agent_id]
        
        # 负载评分（越低越好）
        load_score = 1.0 - min(agent.current_load / agent.max_capacity, 1.0)
        
        # 延迟评分（基于网络RTT）
        latency_score = 1.0 / (1.0 + agent.avg_latency_ms / 100)
        
        # 成本评分
        cost_score = 1.0 / (1.0 + agent.estimated_cost(task))
        
        # 历史成功率
        success_score = agent.success_rate
        
        # 加权综合
        return (
            0.3 * load_score +
            0.25 * latency_score +
            0.2 * cost_score +
            0.25 * success_score
        )

class WorkflowEngine:
    """工作流编排引擎 - 支持复杂多Agent协作流程"""
    
    def __init__(self, router: TaskRouter):
        self.router = router
        self.workflows: Dict[str, Workflow] = {}
        
    async def execute_workflow(self, workflow_def: WorkflowDefinition, inputs: Dict) -> WorkflowResult:
        """执行工作流"""
        workflow = Workflow(workflow_def)
        context = ExecutionContext(inputs)
        
        for step in workflow.steps:
            # 为当前步骤选择Agent
            agent_id = await self.router.route_task(step.task)
            if not agent_id:
                raise NoAgentAvailableError(step.task)
                
            # 执行步骤
            result = await self._execute_step(agent_id, step, context)
            context.set_step_result(step.id, result)
            
            # 处理分支
            next_steps = workflow.get_next_steps(step.id, result)
            
        return WorkflowResult(context.outputs)
        
    async def _execute_step(self, agent_id: str, step: Step, context: ExecutionContext) -> StepResult:
        """执行单个步骤"""
        agent = await self._get_agent(agent_id)
        
        # 构建任务消息
        task_msg = {
            "type": "EXECUTE_TASK",
            "task_id": step.id,
            "task_def": step.task.to_dict(),
            "context": context.to_dict(),
            "dependencies": [context.get_step_result(dep) for dep in step.dependencies]
        }
        
        # 发送并等待结果
        result = await agent.execute_task(task_msg)
        return StepResult(result)
```

#### 2.2.5 安全与通信

```python
# security/secure_channel.py
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import hashlib

class SecureChannel:
    """端到端加密通信通道"""
    
    def __init__(self, local_identity: AgentIdentity):
        self.local_id = local_identity.id
        self.private_key = load_private_key(local_identity.id)
        self.public_key = self.private_key.public_key()
        self.session_keys: Dict[str, bytes] = {}  # peer_id -> session_key
        
    async def establish_channel(self, peer_id: str, peer_public_key: bytes) -> bool:
        """与peer建立安全通道（ECDH密钥交换）"""
        try:
            # 生成临时密钥对
            ephemeral_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            
            # 交换公钥并派生共享密钥
            shared_secret = await self._perform_key_exchange(peer_id, ephemeral_key)
            
            # 使用HKDF派生会话密钥
            session_key = HKDF.derive_key(shared_secret, salt=None, info=b"agent-session")
            self.session_keys[peer_id] = session_key
            
            return True
        except Exception as e:
            logger.error(f"Failed to establish secure channel with {peer_id}: {e}")
            return False
            
    async def send_encrypted(self, peer_id: str, message: bytes) -> bytes:
        """发送加密消息"""
        session_key = self.session_keys.get(peer_id)
        if not session_key:
            raise ChannelNotEstablishedError(peer_id)
            
        # AES-GCM加密
        nonce = os.urandom(12)
        aesgcm = AESGCM(session_key)
        ciphertext = aesgcm.encrypt(nonce, message, None)
        
        # 签名
        signature = self._sign(ciphertext)
        
        return pack_message(nonce, ciphertext, signature)
        
    async def receive_encrypted(self, peer_id: str, packet: bytes) -> bytes:
        """接收并解密消息"""
        nonce, ciphertext, signature = unpack_message(packet)
        
        # 验证签名
        if not self._verify_signature(peer_id, ciphertext, signature):
            raise SignatureVerificationError()
            
        # 解密
        session_key = self.session_keys[peer_id]
        aesgcm = AESGCM(session_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        
        return plaintext

class PermissionManager:
    """权限管理 - 基于Capability的访问控制"""
    
    def __init__(self):
        self.acl: Dict[str, Set[str]] = {}  # resource -> allowed_agents
        self.capabilities: Dict[str, Set[str]] = {}  # agent -> capabilities
        
    def check_permission(self, agent_id: str, resource: str, action: str) -> bool:
        """检查Agent是否有权限执行操作"""
        # 检查资源ACL
        allowed = self.acl.get(resource, set())
        if agent_id not in allowed:
            return False
            
        # 检查能力要求
        required_cap = f"{resource}:{action}"
        agent_caps = self.capabilities.get(agent_id, set())
        
        return required_cap in agent_caps or "admin" in agent_caps
```

---

## 3. 具体Agent实现

### 3.1 Codex Agent

```python
# agents/codex_agent.py
import openai
from typing import AsyncIterator

class CodexAgent(BaseAgent):
    """OpenAI Codex Agent实现"""
    
    def __init__(self, api_key: str, model: str = "codex-latest"):
        identity = AgentIdentity(
            id=f"codex-{uuid.uuid4().hex[:8]}",
            name="Codex",
            type="codex",
            version="1.0",
            public_key="",  # 生成RSA密钥对
            endpoint="",  # 动态分配
            capabilities=[
                AgentCapability(
                    name="code_generation",
                    description="Generate code from natural language descriptions",
                    input_schema={"type": "object", "properties": {"prompt": {"type": "string"}}},
                    output_schema={"type": "object", "properties": {"code": {"type": "string"}}},
                    cost_per_token=0.002,
                    max_context_length=128000,
                    supported_languages=["python", "javascript", "typescript", "go", "rust", "java"]
                ),
                AgentCapability(
                    name="code_review",
                    description="Review and suggest improvements for code",
                    input_schema={"type": "object", "properties": {"code": {"type": "string"}}},
                    output_schema={"type": "object", "properties": {"review": {"type": "string"}}},
                    cost_per_token=0.002,
                    max_context_length=128000,
                    supported_languages=["*"]
                )
            ],
            metadata={"provider": "openai", "model": model}
        )
        super().__init__(identity)
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model
        
    async def execute(self, task: Dict[str, Any], context: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        """执行代码生成任务"""
        task_type = task.get("type")
        
        if task_type == "code_generation":
            async for chunk in self._generate_code(task["prompt"], context):
                yield chunk
        elif task_type == "code_review":
            async for chunk in self._review_code(task["code"], context):
                yield chunk
        else:
            raise UnsupportedTaskError(task_type)
            
    async def _generate_code(self, prompt: str, context: Dict) -> AsyncIterator[Dict[str, Any]]:
        """流式生成代码"""
        messages = [
            {"role": "system", "content": "You are a helpful coding assistant."},
            {"role": "user", "content": prompt}
        ]
        
        # 添加上下文
        if "conversation_history" in context:
            messages = context["conversation_history"] + messages
            
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=0.2
        )
        
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield {"type": "delta", "content": content}
                
    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """对话接口"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content
```

### 3.2 Claude Code Agent

```python
# agents/claude_agent.py
import anthropic

class ClaudeCodeAgent(BaseAgent):
    """Anthropic Claude Code Agent实现"""
    
    def __init__(self, api_key: str, model: str = "claude-3-opus-20240229"):
        identity = AgentIdentity(
            id=f"claude-{uuid.uuid4().hex[:8]}",
            name="Claude Code",
            type="claude",
            version="3",
            public_key="",
            endpoint="",
            capabilities=[
                AgentCapability(
                    name="complex_reasoning",
                    description="Handle complex multi-step reasoning tasks",
                    input_schema={"type": "object", "properties": {"problem": {"type": "string"}}},
                    output_schema={"type": "object", "properties": {"solution": {"type": "string"}}},
                    cost_per_token=0.015,
                    max_context_length=200000,
                    supported_languages=["*"]
                ),
                AgentCapability(
                    name="architecture_design",
                    description="Design system architecture and patterns",
                    input_schema={"type": "object", "properties": {"requirements": {"type": "string"}}},
                    output_schema={"type": "object", "properties": {"design": {"type": "string"}}},
                    cost_per_token=0.015,
                    max_context_length=200000,
                    supported_languages=["*"]
                )
            ],
            metadata={"provider": "anthropic", "model": model}
        )
        super().__init__(identity)
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        
    async def execute(self, task: Dict[str, Any], context: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        """执行任务"""
        # 类似Codex的实现...
        pass
```

### 3.3 本地LLM Agent

```python
# agents/local_agent.py
import ollama

class LocalLLMAgent(BaseAgent):
    """本地Ollama Agent实现"""
    
    def __init__(self, model: str = "qwen2.5:7b", host: str = "http://localhost:11434"):
        identity = AgentIdentity(
            id=f"local-{uuid.uuid4().hex[:8]}",
            name=f"Local {model}",
            type="local",
            version="1.0",
            public_key="",
            endpoint=host,
            capabilities=[
                AgentCapability(
                    name="local_inference",
                    description="Run inference locally without external API",
                    input_schema={"type": "object", "properties": {"prompt": {"type": "string"}}},
                    output_schema={"type": "object", "properties": {"response": {"type": "string"}}},
                    cost_per_token=0,  # 本地运行免费
                    max_context_length=32768,
                    supported_languages=["zh", "en"]
                )
            ],
            metadata={"provider": "ollama", "model": model, "privacy": "local"}
        )
        super().__init__(identity)
        self.model = model
        self.host = host
        
    async def execute(self, task: Dict[str, Any], context: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        """本地执行"""
        prompt = task.get("prompt", "")
        
        response = await ollama.AsyncClient(host=self.host).chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            stream=True
        )
        
        async for chunk in response:
            yield {"type": "delta", "content": chunk.message.content}
```

---

## 4. 协作模式

### 4.1 协作协议

```python
# collaboration/protocol.py
from enum import Enum

class CollaborationMode(Enum):
    """协作模式"""
    SEQUENTIAL = "sequential"      # 顺序执行
    PARALLEL = "parallel"          # 并行执行
    MAP_REDUCE = "map_reduce"      # 分片处理+聚合
    DEBATE = "debate"              # 多Agent辩论
    VOTING = "voting"              # 投票决策

class CollaborationProtocol:
    """多Agent协作协议"""
    
    async def coordinate(self, task: ComplexTask, agents: List[str]) -> CollaborationResult:
        """协调多Agent完成任务"""
        
        if task.mode == CollaborationMode.SEQUENTIAL:
            return await self._sequential_execute(task, agents)
        elif task.mode == CollaborationMode.PARALLEL:
            return await self._parallel_execute(task, agents)
        elif task.mode == CollaborationMode.MAP_REDUCE:
            return await self._map_reduce_execute(task, agents)
        elif task.mode == CollaborationMode.DEBATE:
            return await self._debate_execute(task, agents)
        elif task.mode == CollaborationMode.VOTING:
            return await self._voting_execute(task, agents)
            
    async def _sequential_execute(self, task: ComplexTask, agents: List[str]) -> CollaborationResult:
        """顺序执行：Agent1 -> Agent2 -> Agent3"""
        context = {}
        results = []
        
        for i, agent_id in enumerate(agents):
            subtask = task.subtasks[i]
            subtask.context.update(context)
            
            agent = await self._get_agent(agent_id)
            result = await agent.execute(subtask.to_dict(), context)
            
            context[f"agent_{i}_result"] = result
            results.append(result)
            
        return CollaborationResult(results=results, final_result=results[-1])
        
    async def _parallel_execute(self, task: ComplexTask, agents: List[str]) -> CollaborationResult:
        """并行执行：所有Agent同时工作"""
        tasks = []
        for agent_id, subtask in zip(agents, task.subtasks):
            agent = await self._get_agent(agent_id)
            tasks.append(agent.execute(subtask.to_dict(), {}))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 合并结果
        merged = self._merge_results(results)
        return CollaborationResult(results=results, final_result=merged)
        
    async def _debate_execute(self, task: ComplexTask, agents: List[str]) -> CollaborationResult:
        """辩论模式：多Agent讨论达成共识"""
        topic = task.topic
        rounds = task.rounds or 3
        
        debate_history = []
        
        for round_num in range(rounds):
            round_responses = []
            
            for agent_id in agents:
                agent = await self._get_agent(agent_id)
                
                # 构建辩论提示
                prompt = self._build_debate_prompt(topic, debate_history, agent_id)
                
                response = await agent.chat([
                    {"role": "system", "content": "You are participating in a debate."},
                    {"role": "user", "content": prompt}
                ])
                
                round_responses.append({"agent": agent_id, "response": response})
                
            debate_history.append({"round": round_num, "responses": round_responses})
            
        # 最终共识
        consensus = await self._reach_consensus(debate_history, agents)
        return CollaborationResult(
            results=debate_history,
            final_result=consensus
        )
```

### 4.2 消息格式

```python
# collaboration/messages.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class AgentMessage:
    """Agent间通信消息格式"""
    msg_id: str
    msg_type: str  # TASK_REQUEST, TASK_RESPONSE, HEARTBEAT, DISCOVERY, etc.
    from_agent: str
    to_agent: Optional[str]  # None表示广播
    timestamp: datetime
    payload: Dict[str, Any]
    signature: str  # 消息签名
    ttl: int = 3  # 生存时间
    
@dataclass
class TaskRequest:
    """任务请求"""
    task_id: str
    task_type: str
    parameters: Dict[str, Any]
    priority: int  # 0-10
    deadline: Optional[datetime]
    callback_endpoint: Optional[str]
    
@dataclass
class TaskResponse:
    """任务响应"""
    task_id: str
    status: str  # PENDING, RUNNING, COMPLETED, FAILED
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    execution_time_ms: int
    tokens_used: int
```

---

## 5. 部署与运行

### 5.1 启动脚本

```python
# main.py
import asyncio
import argparse
from typing import List

async def main():
    parser = argparse.ArgumentParser(description="Decentralized AI Agent Platform")
    parser.add_argument("--type", choices=["codex", "claude", "local", "custom"], required=True)
    parser.add_argument("--name", default="agent")
    parser.add_argument("--port", type=int, default=0)  # 0表示自动分配
    parser.add_argument("--bootstrap", nargs="+", default=[], help="引导节点地址")
    parser.add_argument("--api-key", help="API密钥（用于云端Agent）")
    parser.add_argument("--model", help="模型名称（用于本地Agent）")
    
    args = parser.parse_args()
    
    # 创建Agent
    if args.type == "codex":
        agent = CodexAgent(api_key=args.api_key)
    elif args.type == "claude":
        agent = ClaudeCodeAgent(api_key=args.api_key)
    elif args.type == "local":
        agent = LocalLLMAgent(model=args.model or "qwen2.5:7b")
    else:
        raise ValueError(f"Unknown agent type: {args.type}")
        
    # 启动P2P网络
    network = P2PNetwork(
        node_id=agent.identity.id,
        listen_addr=f"0.0.0.0:{args.port}"
    )
    await network.start()
    
    # 加入网络
    if args.bootstrap:
        await network.join_network(args.bootstrap)
        
    # 启动服务发现
    discovery = HybridServiceDiscovery(
        node_id=agent.identity.id,
        on_peer_discovered=lambda peer: print(f"Discovered peer: {peer.name}")
    )
    await discovery.start()
    await discovery.announce(agent.identity)
    
    # 注册消息处理器
    agent.register_handler("TASK_REQUEST", handle_task_request)
    agent.register_handler("HEARTBEAT", handle_heartbeat)
    
    print(f"Agent {agent.identity.name} ({agent.identity.id}) started")
    print(f"Listening on {network.listen_addr}")
    print(f"Capabilities: {[c.name for c in agent.identity.capabilities]}")
    
    # 保持运行
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        await network.stop()
        
async def handle_task_request(agent: BaseAgent, message: AgentMessage):
    """处理任务请求"""
    request = TaskRequest(**message.payload)
    
    # 执行任务
    result_chunks = []
    async for chunk in agent.execute(request.parameters, {}):
        result_chunks.append(chunk)
        
    # 发送响应
    response = TaskResponse(
        task_id=request.task_id,
        status="COMPLETED",
        result={"chunks": result_chunks},
        error=None,
        execution_time_ms=0,
        tokens_used=0
    )
    
    await agent.send_message(
        message.from_agent,
        "TASK_RESPONSE",
        response.__dict__
    )
    
async def handle_heartbeat(agent: BaseAgent, message: AgentMessage):
    """处理心跳"""
    # 更新peer状态
    pass

if __name__ == "__main__":
    asyncio.run(main())
```

### 5.2 Docker部署

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000-9000

CMD ["python", "main.py"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  codex-agent:
    build: .
    command: ["python", "main.py", "--type", "codex", "--name", "codex-1", "--api-key", "${OPENAI_API_KEY}"]
    ports:
      - "8001:8000"
    environment:
      - AGENT_BOOTSTRAP=claude-agent:8000
    networks:
      - agent-network

  claude-agent:
    build: .
    command: ["python", "main.py", "--type", "claude", "--name", "claude-1", "--api-key", "${ANTHROPIC_API_KEY}"]
    ports:
      - "8002:8000"
    networks:
      - agent-network

  local-agent:
    build: .
    command: ["python", "main.py", "--type", "local", "--name", "local-1", "--model", "qwen2.5:7b"]
    ports:
      - "8003:8000"
    networks:
      - agent-network

networks:
  agent-network:
    driver: bridge
```

---

## 6. 使用示例

### 6.1 启动多Agent网络

```bash
# 启动第一个Agent（作为引导节点）
python main.py --type local --name bootstrap --port 8000

# 启动其他Agent并加入网络
python main.py --type codex --name codex-1 --api-key $OPENAI_KEY --bootstrap localhost:8000
python main.py --type claude --name claude-1 --api-key $ANTHROPIC_KEY --bootstrap localhost:8000
python main.py --type local --name local-1 --model qwen2.5:7b --bootstrap localhost:8000
```

### 6.2 提交协作任务

```python
# client_example.py
import asyncio
import aiohttp

async def submit_collaborative_task():
    """提交一个需要多Agent协作的任务"""
    
    async with aiohttp.ClientSession() as session:
        # 定义复杂任务
        task = {
            "mode": "debate",  # 使用辩论模式
            "topic": "设计一个高性能分布式系统的架构",
            "agents": ["codex-1", "claude-1", "local-1"],
            "rounds": 3,
            "requirements": [
                "支持百万级并发",
                "保证数据一致性",
                "具备容错能力"
            ]
        }
        
        # 提交到任意Agent
        async with session.post(
            "http://localhost:8000/api/collaborate",
            json=task
        ) as resp:
            result = await resp.json()
            
        # 打印辩论结果
        for round_data in result["debate_history"]:
            print(f"\n=== Round {round_data['round'] + 1} ===")
            for response in round_data["responses"]:
                print(f"\n{response['agent']}:")
                print(response['response'][:500] + "...")
                
        print(f"\n=== 最终共识 ===")
        print(result["consensus"])

asyncio.run(submit_collaborative_task())
```

### 6.3 工作流编排

```python
# workflow_example.py
from orchestration.workflow_engine import WorkflowEngine, WorkflowDefinition

# 定义代码审查工作流
workflow = WorkflowDefinition()

# 步骤1: Codex生成代码
generate_step = workflow.add_step(
    name="generate",
    task_type="code_generation",
    agent_selector="capability:code_generation",
    parameters={"prompt": "实现一个线程安全的LRU缓存"}
)

# 步骤2: Claude审查架构
review_step = workflow.add_step(
    name="review_architecture",
    task_type="architecture_review",
    agent_selector="type:claude",
    depends_on=[generate_step],
    parameters={
        "code": "${steps.generate.output.code}"
    }
)

# 步骤3: 本地Agent优化性能
optimize_step = workflow.add_step(
    name="optimize",
    task_type="performance_optimization",
    agent_selector="type:local",
    depends_on=[review_step],
    parameters={
        "code": "${steps.generate.output.code}",
        "review_comments": "${steps.review_architecture.output.review}"
    }
)

# 执行工作流
engine = WorkflowEngine()
result = await engine.execute_workflow(workflow, {})

print("最终优化后的代码:")
print(result.steps["optimize"].output.code)
```

---

## 7. 总结

### 7.1 核心创新点

1. **真正去中心化**：基于gossip协议的P2P网络，无单点故障
2. **异构兼容**：统一抽象接口，支持任何类型的AI Agent
3. **智能协作**：多种协作模式（顺序、并行、辩论、投票）
4. **安全通信**：端到端加密，基于Capability的权限控制
5. **动态发现**：mDNS+DHT混合服务发现，支持局域网+广域网

### 7.2 应用场景

- **代码生成**：Codex生成 + Claude审查 + 本地优化
- **多语言翻译**：不同语言专家Agent协作
- **复杂问题求解**：多Agent辩论达成共识
- **分布式任务处理**：Map-Reduce模式处理大数据

### 7.3 未来扩展

- 支持更多Agent类型（Gemini、Llama等）
- 引入区块链实现去中心化信任
- 强化学习优化任务路由策略
- 联邦学习实现隐私保护协作

---

**文档版本**: 1.0  
**最后更新**: 2025年
