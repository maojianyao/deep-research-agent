"""不调用模型的最小运行检查：验证证据 ID 引用校验逻辑。"""
import asyncio
import os

from backend.src.research.schemas import ReportBlock, ReportDraft, ResearchRun
from backend.src.services.llm import get_llm
from backend.src.services.search import duckduckgo_search, tavily_search, parallel_search, youcom_search, \
    exa_search
from backend.src.research.agents import PlannerAgent, ResearcherAgent, EvidenceReviewerAgent, CriticAgent, WriterAgent, \
    SynthesizerAgent
from backend.src.research.orchestrator import ResearchOrchestrator

def self_check() -> None:
    draft = ReportDraft(title="demo", blocks=[ReportBlock(heading="摘要", text="x", evidence_ids=["evidence_1"])])
    assert not WriterAgent.citations_are_valid(draft, [])


async def get_research_result(research_topic: str):
    import dotenv
    dotenv.load_dotenv()
    llm_model = get_llm()

    # 默认duckduckgo
    searches = [duckduckgo_search,]
    if "TAVILY_API_KEY" in os.environ:
        searches.append(tavily_search)
    if "PARALLEL_API_KEY" in os.environ:
        searches.append(parallel_search)
    if "YDC_API_KEY" in os.environ:
        searches.append(youcom_search)
    if "EXA_API_KEY" in os.environ:
        searches.append(exa_search)

    planner_agent = PlannerAgent(llm_model)
    researcher_agent = ResearcherAgent(llm_model, searches)
    reviewer_agent = EvidenceReviewerAgent(llm_model)
    synthesizer_agent = SynthesizerAgent(llm_model)
    critic_agent = CriticAgent(llm_model)
    writer_agent = WriterAgent(llm_model)

    orchestrator_agent = ResearchOrchestrator(planner_agent,
                                              researcher_agent,
                                              reviewer_agent,
                                              synthesizer_agent,
                                              critic_agent,
                                              writer_agent)

    # 传入运行数据
    state_data = ResearchRun(
        user_request=research_topic,
    )
    result = await orchestrator_agent.run(state_data)

    return result
if __name__ == "__main__":
    from datetime import datetime
    date = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    topic = "大模型agent开发范式"
    result = asyncio.run(get_research_result(topic))
    base_path = "../resources/"
    with open(f"{base_path}result_{date}.txt", "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))

    md = result.to_markdown()
    if md is None:
        print(f"报告尚未生成，当前状态：{result.status}")

    # 保存为 .md 文件
    with open(f"{base_path}report_{date}.md", "w", encoding="utf-8") as f:
        f.write(md)
