from writing_agent.llm.model_router import ModelRouter


def test_model_router_choose_model() -> None:
    router = ModelRouter()
    model = router.choose_model(task='long review', prompt_len=220, candidates=['m-large', 'm-small'])
    assert model == 'm-large'


def test_model_router_fallback_chain() -> None:
    router = ModelRouter()
    chain = router.fallback_chain(preferred='m2', candidates=['m1', 'm2', 'm3'])
    assert chain == ['m2', 'm1', 'm3']
