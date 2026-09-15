from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from .schemas import OptimizeRequest, OptimizeResponse, OptimizationRules
from core.ai.token_utils import TokenOptimizer, OpenAITokenizer
from apps.lean.config_settings import settings

PRESETS = {
    "low": OptimizationRules(remove_thoughts=False, shorten_urls=False),
    "medium": OptimizationRules(),
    "high": OptimizationRules(shorten_urls=True, compress_whitespace=True),
}

router = APIRouter()

def get_optimizer(strategy: str = None, rules: OptimizationRules = None):
    # 실제 rules 적용은 TokenOptimizer 내부에서 구현 필요
    # 여기서는 예시로 OpenAITokenizer만 사용
    return TokenOptimizer(OpenAITokenizer())

@router.post("/v1/optimize", response_model=OptimizeResponse)
async def optimize(req: OptimizeRequest):
    optimizer = get_optimizer(req.strategy, req.rules)
    # CPU 연산은 스레드풀에서 실행
    optimized = await run_in_threadpool(optimizer.optimize, req.messages)
    original_tokens = await run_in_threadpool(optimizer.count_tokens, req.messages)
    new_tokens = await run_in_threadpool(optimizer.count_tokens, optimized)
    return OptimizeResponse(
        optimized=optimized,
        token_saved=original_tokens - new_tokens,
        original_tokens=original_tokens,
        new_tokens=new_tokens,
    )

@router.get("/health")
def health():
    return {"status": "ok"}
