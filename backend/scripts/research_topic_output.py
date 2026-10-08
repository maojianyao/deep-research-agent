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
from backend.src.storage import ResearchRunRepository, create_db_engine, init_db

def self_check() -> None:
    draft = ReportDraft(title="demo", blocks=[ReportBlock(heading="摘要", text="x", evidence_ids=["evidence_1"])])
    assert not WriterAgent.citations_are_valid(draft, [])


async def get_research_result(research_topic: str, max_iterations: int):
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
        max_iterations=max_iterations,
    )
    engine = create_db_engine()
    init_db(engine)
    repository = ResearchRunRepository(engine)
    repository.save_run(state_data)

    async def persist(run: ResearchRun) -> None:
        await asyncio.to_thread(repository.save_run, run)

    orchestrator_agent.on_update = persist
    result = await orchestrator_agent.run(state_data)
    print(f"研究记录已保存：run_id={result.id}")

    return result
if __name__ == "__main__":
    import sys
    self_check()
    from datetime import datetime
    date = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    topic = sys.argv[1] if len(sys.argv) > 1 else "RAG技术演变"
    max_iter = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    print(f"开始深度研究任务：主题 = 【{topic}】，最大迭代 = {max_iter}")
    result = asyncio.run(get_research_result(topic, max_iterations=max_iter))
    base_path = os.path.join(os.path.dirname(__file__), "../resources")
    os.makedirs(base_path, exist_ok=True)
    result_file = os.path.join(base_path, f"result_{date}.txt")
    report_file = os.path.join(base_path, f"report_{date}.md")
    with open(result_file, "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))

    md = result.to_markdown()
    if md is None:
        print(f"报告尚未生成，当前状态：{result.status}")
    else:
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"研究报告已成功生成并导出：{report_file}")
