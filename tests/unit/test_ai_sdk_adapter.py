from writing_agent.llm.ai_sdk_adapter import AISDKAdapter, StreamChunk


class _FakeProvider:
    def chat_stream(self, *, system, user, temperature=0.2, options=None):
        yield 'a'
        yield 'b'

    def chat(self, *, system, user, temperature=0.2, options=None):
        return '{"ok":1,"value":2}'


class _FakeGatewayProvider(_FakeProvider):
    def generate_object(self, *, system, user, schema, temperature=0.1, options=None):
        return {"ok": 1, "gateway": True}

    def tool_call(self, *, tool_name, arguments, options=None):
        return {"ok": 1, "tool": tool_name, "arguments": arguments}


def test_ai_sdk_stream_text() -> None:
    sdk = AISDKAdapter(provider=_FakeProvider())
    chunks = list(sdk.stream_text(system='s', user='u'))
    assert any(isinstance(x, StreamChunk) for x in chunks)
    assert ''.join(x.delta for x in chunks if x.delta) == 'ab'


def test_ai_sdk_generate_object() -> None:
    sdk = AISDKAdapter(provider=_FakeProvider())
    obj = sdk.generate_object(system='s', user='u')
    assert obj.get('ok') == 1


def test_ai_sdk_generate_object_uses_provider_override() -> None:
    sdk = AISDKAdapter(provider=_FakeGatewayProvider())
    obj = sdk.generate_object(
        system='s',
        user='u',
        schema={'type': 'object', 'properties': {'ok': {'type': 'number'}}},
    )
    assert obj.get('gateway') is True


def test_ai_sdk_tool_call_uses_provider_override() -> None:
    sdk = AISDKAdapter(provider=_FakeGatewayProvider())
    out = sdk.tool_call(tool_name='echo', arguments={'k': 1}, registry={})
    assert out.get('tool') == 'echo'
