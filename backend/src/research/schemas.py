"""研究工作流的持久化契约；所有 Agent 只通过这些对象协作。"""

from __future__ import annotations

from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl

from backend.src.research.context_budget import truncate_text, DIGEST_STATEMENT_CHARS, DIGEST_CAVEAT_CHARS, \
    DIGEST_MAX_CAVEATS, DIGEST_CLAIM_CHARS, DIGEST_EXCERPT_CHARS, DIGEST_LIMITATION_CHARS, DIGEST_MAX_LIMITATIONS
from backend.src.utils.documents import document_keys


def new_id(prefix: str) -> str:
    """生成便于日志和跨 Agent 引用的短标识符。"""
    return f"{prefix}_{uuid4().hex[:12]}"

class RoleAgent(str, Enum):
    """Agent 角色标识符"""
    PLANNER = "planner"
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    SYNTHESIZER = "synthesizer"
    CRITIC = "critic"
    WRITER = "writer"


class RunStatus(str, Enum):
    """编排器允许的运行状态；终态不会再触发 Agent 调用。"""
    PLANNING = "planning"       # 计划制定中
    RESEARCHING = "researching"       # 研究执行中
    REVIEWING_EVIDENCE = "reviewing_evidence"       # 证据审查中
    SYNTHESIZING = "synthesizing"       # 综合合成中
    CRITIC_REVIEW = "critic_review"       # 反方审查中
    WRITING = "writing"       # 报告写作中
    COMPLETED = "completed"       # 研究完成
    NEEDS_HUMAN_REVIEW = "needs_human_review"       # 需人工复核
    FAILED = "failed"       # 研究失败
    CANCELLED = "cancelled"   # 用户主动取消


class ResearchTask(BaseModel):
    """可独立执行的研究子问题及其验收条件。"""

    id: str = Field(default_factory=lambda: new_id("task"), description="任务的稳定标识符。")
    question: str = Field(description="需要以证据回答的具体问题。")
    task_type: Literal["fact", "causal", "comparison", "prediction", "value"] =  Field(
        default="fact", description="问题类型：fact事实、causal因果、comparison比较、prediction预测、value价值判断。")
    priority: Literal["high", "medium", "low"] = Field(default="medium", description="决定检索和审稿的优先级。")
    required_source_types: list[str] = Field(default_factory=lambda: ["official", "primary"], description="可接受的来源类型。")
    acceptance_criteria: list[str] = Field(default_factory=list, description="任务完成前必须满足的证据条件。")
    queries: list[str] = Field(default_factory=list, description="检索 Agent 使用的查询词；为空时使用 question。")
    attempts: int = Field(default=0, ge=0, description="已尝试检索的次数，不允许为负数。")
    completed: bool = Field(default=False, description="是否已形成至少一条可审查的发现。")


class ResearchPlan(BaseModel):
    """Planner 输出的研究蓝图，不包含事实性结论。"""

    research_question: str = Field(description="归一化后的总研究问题。")
    scope: str = Field(description="时间、地域、对象和不包含内容的边界。")
    tasks: list[ResearchTask] = Field(min_length=1, description="至少一个可执行子任务。")
    completion_rules: list[str] = Field(default_factory=list, description="整项研究进入写作前的验收规则。")


class ResearchTaskDraft(BaseModel):
    """Planner 模型可见的任务草稿；id、attempts、completed 由应用层管理，不进入模型 schema。"""

    question: str = Field(description="需要以证据回答的具体问题。")
    task_type: Literal["fact", "causal", "comparison", "prediction", "value"] =  Field(
        default="fact", description="问题类型：fact事实、causal因果、comparison比较、prediction预测、value价值判断。")
    priority: Literal["high", "medium", "low"] = Field(default="medium", description="决定检索和审稿的优先级。")
    required_source_types: list[str] = Field(
        default_factory=lambda: ["official", "primary"],
        description="来源类型短标签，如 official、primary、academic、news、report。",
    )
    acceptance_criteria: list[str] = Field(default_factory=list, description="任务完成前必须满足的证据条件。")
    queries: list[str] = Field(default_factory=list, description="检索 Agent 使用的查询词；为空时使用 question。")

    def to_task(self) -> ResearchTask:
        """由应用层生成 id，映射为完整任务对象。"""
        return ResearchTask(id=new_id("task"), **self.model_dump())


class ResearchPlanDraft(BaseModel):
    """Planner 模型可见的研究蓝图；转换为 ResearchPlan 时补齐应用层字段。"""

    research_question: str = Field(description="归一化后的总研究问题。")
    scope: str = Field(description="时间、地域、对象和不包含内容的边界。")
    tasks: list[ResearchTaskDraft] = Field(min_length=1, description="至少一个可执行子任务。")
    completion_rules: list[str] = Field(default_factory=list, description="整项研究进入写作前的验收规则。")

    def to_plan(self) -> ResearchPlan:
        """把模型输出转换为带应用层生成 id 的正式计划。"""
        return ResearchPlan(
            research_question=self.research_question,
            scope=self.scope,
            tasks=[item.to_task() for item in self.tasks],
            completion_rules=self.completion_rules,
        )


class SourceDocument(BaseModel):
    """搜索适配器返回的原始材料，不应直接用于最终报告。"""

    url: HttpUrl = Field(description="来源的规范 HTTP(S) 地址，由 HttpUrl 校验格式。")
    title: str = Field(min_length=1, description="页面或文档标题，不能为空。")
    publisher: str | None = Field(default=None, description="发布机构或作者；缺失时保留 null。")
    published_at: str | None = Field(default=None, description="来源声明的发布日期，暂以原字符串保留。")
    source_type: str = Field(default="unknown", description="official、primary、academic 等来源分类。")
    content: str = Field(min_length=1, description="已获取的原始正文；为空的材料不可作为证据。")


class SourceRef(BaseModel):
    """模型可见的来源引用：只含元数据，不含正文 content，防止全文进入上下文。"""

    url: str = Field(description="来源 URL。")
    title: str = Field(description="来源标题。")
    publisher: str | None = Field(default=None, description="发布机构或作者。")
    published_at: str | None = Field(default=None, description="发布日期。")
    source_type: str = Field(default="unknown", description="来源分类。")

    @classmethod
    def from_document(cls, doc: "SourceDocument") -> "SourceRef":
        return cls(url=str(doc.url), title=doc.title, publisher=doc.publisher,
                   published_at=doc.published_at, source_type=doc.source_type)


class CandidateEvidence(BaseModel):
    """Researcher 从原始资料中提取、尚未经审查的候选证据。"""

    task_id: str | None = Field(default=None, description="候选证据所属任务 ID；由应用层回填。")
    iteration: int = Field(default=0, ge=0, description="产生该候选证据的检索轮次。")
    source: SourceDocument = Field(description="候选证据所属的原始来源。")
    claim: str = Field(min_length=1, description="候选证据拟支持或反驳的主张。")
    excerpt: str = Field(min_length=1, description="直接相关的原文摘录，不能为空。")
    locator: str | None = Field(default=None, description="页码、章节或段落等可复核定位信息。")


class CandidateEvidenceBatch(BaseModel):
    """结构化输出包装器，避免让模型直接返回顶层 JSON 数组。"""

    items: list[CandidateEvidence] = Field(default_factory=list, description="本轮提取的候选证据列表。")


class CandidateEvidenceDraft(BaseModel):
    """模型可见的证据草稿：仅回报来源 URL，原始文档由应用层回绑，避免模型回传全文。"""

    source_url: str = Field(description="候选证据所属来源的 URL，必须逐字取自输入文档的 url 字段。")
    claim: str = Field(min_length=1, description="候选证据拟支持或反驳的主张。")
    excerpt: str = Field(min_length=1, description="直接相关的原文摘录，不能为空。")
    locator: str | None = Field(default=None, description="页码、章节或段落等可复核定位信息。")


class CandidateEvidenceBatchDraft(BaseModel):
    """结构化输出包装器，避免让模型直接返回顶层 JSON 数组。"""

    items: list[CandidateEvidenceDraft] = Field(default_factory=list, description="本轮提取的候选证据列表。")

    def to_candidates(self, documents: dict[str, SourceDocument]) -> tuple[list[CandidateEvidence], list[str]]:
        """按 URL 回绑真实来源；返回（候选证据列表, 模型编造的未知 URL 列表）。"""
        candidates, unknown = [], []
        documents_by_url = {document_keys(url, doc.title)[0]: doc for url, doc in documents.items()}
        for draft in self.items:
            source = (documents.get(draft.source_url)
                      or documents.get(draft.source_url.rstrip("/"))
                      or documents_by_url.get(document_keys(draft.source_url, "")[0]))
            if source is None:
                unknown.append(draft.source_url)
                continue
            candidates.append(CandidateEvidence(
                source=source, claim=draft.claim, excerpt=draft.excerpt, locator=draft.locator,
            ))
        return candidates, unknown


class EvidenceCard(BaseModel):
    """审查通过或保留的证据卡，是报告唯一可引用的事实来源。"""

    id: str = Field(default_factory=lambda: new_id("evidence"), description="证据的稳定标识符。")
    task_id: str = Field(description="证据所属研究任务 ID。")
    iteration: int = Field(default=0, ge=0, description="产生该证据卡的检索轮次。")
    claim: str = Field(min_length=1, description="该证据所对应的主张。")
    excerpt: str = Field(min_length=1, description="用于复核的直接原文。")
    source: SourceDocument = Field(description="原始来源及其元数据。")
    locator: str | None = Field(default=None, description="原文在来源中的定位信息。")
    verdict: Literal["supported", "partially_supported", "contradicted", "insufficient"] = Field(description="审查结论。")
    confidence: float = Field(ge=0, le=1, description="审查置信度，限制在 0 到 1。")
    limitations: list[str] = Field(default_factory=list, description="口径、时效性或方法等限制。")

    def to_digest(self, *, excerpt_chars: int = DIGEST_EXCERPT_CHARS) -> "EvidenceDigest":
        """生成进模型的紧凑视图：不含来源正文，摘录与主张限长。"""
        return EvidenceDigest(
            id=self.id,
            task_id=self.task_id,
            claim=truncate_text(self.claim, DIGEST_CLAIM_CHARS),
            excerpt=truncate_text(self.excerpt, excerpt_chars),
            verdict=self.verdict,
            confidence=self.confidence,
            limitations=[truncate_text(item, DIGEST_LIMITATION_CHARS)
                         for item in self.limitations[:DIGEST_MAX_LIMITATIONS]],
            source=SourceRef.from_document(self.source),
        )


class EvidenceAssessment(BaseModel):
    """审查模型的输出；由应用层补回不可伪造的任务和来源字段。"""

    verdict: Literal["supported", "partially_supported", "contradicted", "insufficient"] = Field(description="候选证据的审查结论。必须是supported、partially_supported、contradicted、insufficient其中之一。")
    confidence: float = Field(ge=0, le=1, description="结论置信度，必须位于闭区间 [0, 1]。")
    limitations: list[str] = Field(default_factory=list, description="影响使用该证据的局限。")


class EvidenceAssessmentBatch(BaseModel):
    """批量审查输出：items 与输入候选列表按索引一一对应。"""

    items: list[EvidenceAssessment] = Field(default_factory=list, description="审查结论列表，顺序必须与输入候选一致。")


class EvidenceDigest(BaseModel):
    """证据卡的紧凑视图：无来源正文、摘录限长，供 Critic / Writer / 补证规划消费。"""

    id: str = Field(description="证据稳定标识符，用于跨 Agent 引用。")
    task_id: str = Field(description="证据所属研究任务 ID。")
    claim: str = Field(description="限长后的主张表述。")
    excerpt: str = Field(description="限长后的原文摘录。")
    verdict: str = Field(description="审查结论。")
    confidence: float = Field(description="审查置信度。")
    limitations: list[str] = Field(default_factory=list, description="限长后的局限说明。")
    source: SourceRef = Field(description="来源元数据引用，不含正文。")


class Finding(BaseModel):
    """由已审查证据综合出的可供审稿和写作使用的结论。"""

    id: str = Field(default_factory=lambda: new_id("finding"), description="结论的稳定标识符。")
    task_id: str = Field(description="该结论回答的任务 ID。")
    iteration: int = Field(default=0, ge=0, description="产生该结论的检索轮次。")
    statement: str = Field(min_length=1, description="带限定条件的结论表述。")
    classification: Literal["fact", "inference", "contested"] = Field(description="事实、推断或存在争议的判断。")
    evidence_ids: list[str] = Field(min_length=1, description="支撑此结论的已审查证据 ID，至少一条。")
    confidence: float = Field(ge=0, le=1, description="综合置信度，限制在 0 到 1。")
    caveats: list[str] = Field(default_factory=list, description="写作时必须保留的不确定性。")

    def to_digest(self, *, statement_chars: int = DIGEST_STATEMENT_CHARS) -> "FindingDigest":
        """生成进模型的紧凑视图：陈述与警示限长，完整字段留在应用层。"""
        return FindingDigest(
            id=self.id,
            task_id=self.task_id,
            statement=truncate_text(self.statement, statement_chars),
            classification=self.classification,
            confidence=self.confidence,
            caveats=[truncate_text(item, DIGEST_CAVEAT_CHARS) for item in self.caveats[:DIGEST_MAX_CAVEATS]],
            evidence_ids=list(self.evidence_ids),
        )

class FindingDigest(BaseModel):
    """结论的紧凑视图：陈述与警示限长，供 Critic / Writer / 补证规划消费。"""

    id: str = Field(description="结论稳定标识符。")
    task_id: str = Field(description="结论所属任务 ID。")
    statement: str = Field(description="限长后的结论表述。")
    classification: str = Field(description="fact、inference 或 contested。")
    confidence: float = Field(description="综合置信度。")
    caveats: list[str] = Field(default_factory=list, description="限长后的不确定性说明。")
    evidence_ids: list[str] = Field(default_factory=list, description="支撑证据 ID，供应用层回绑。")


class CriticIssue(BaseModel):
    """Critic 发现的可行动问题；严重问题可触发新的研究任务。"""

    severity: Literal["high", "medium", "low"] = Field(description="问题对报告可信度的影响级别。")
    finding_id: str | None = Field(default=None, description="受影响的结论 ID；全局问题时为 null。")
    problem: str = Field(min_length=1, description="可复核的问题说明。")
    follow_up_question: str | None = Field(default=None, description="需要补证时创建的新研究问题。")
    follow_up_queries: list[str] = Field(
            default_factory=list,
            description="follow_up_question 对应的 2-4 条关键词检索查询；应为具体名词+时间范围，禁止整句指令。",
        )

class CriticReview(BaseModel):
    """Critic 对当前证据集的闸门决策。"""

    decision: Literal["approve", "research_more", "needs_human_review"] = Field(description="批准写作、继续研究或交由人工决定。")
    iteration: int = Field(default=0, ge=0, description="该审稿意见对应的检索轮次。")
    issues: list[CriticIssue] = Field(default_factory=list, description="需修复、降级或补证的问题。")
    approved_finding_ids: list[str] = Field(default_factory=list, description="获准进入报告的结论 ID。")


class FindingDraft(BaseModel):
    """Synthesizer 的综合结论草稿；evidence_ids 由应用层校验后回绑。"""

    statement: str = Field(min_length=1, description="叙述性综合结论（200-500字）：主结论+支撑细节+限定条件，禁止罗列拼接。")
    classification: Literal["fact", "inference", "contested"] = Field(default="fact", description="事实、推断或存在争议的判断。")
    confidence: float = Field(ge=0, le=1, description="综合置信度。")
    caveats: list[str] = Field(default_factory=list, description="写作时必须保留的不确定性。")
    evidence_ids: list[str] = Field(min_length=1, description="引用的证据 ID，必须逐字取自输入 evidence 的 id 字段。")


class OutlineSection(BaseModel):
    """大纲中的单章规划。"""

    heading: str = Field(min_length=1, description="章节标题。")
    role: str = Field(default="", description="本章在全文主线中的作用（铺垫/论证/检验/收束），一句话。")
    key_points: list[str] = Field(default_factory=list, description="本章要论证的 2-4 个要点。")
    transition_to_next: str | None = Field(default=None, description="本章结尾抛给下一章的具体问题或悬念；末章为 null。")
    finding_ids: list[str] = Field(default_factory=list, description="分配到本章的结论 ID；范围/方法类章节可为空。")


class ReportOutline(BaseModel):
    """Writer 大纲阶段的输出：按研究维度组织的章节结构。"""

    narrative: str = Field(default="", description="全文主线：核心论点与论证路径，1-2 句话。")
    title: str = Field(min_length=1, description="报告标题。")
    sections: list[OutlineSection] = Field(min_length=1, description="章节规划，顺序即报告顺序。")

class SectionDraft(BaseModel):
    """Writer 分章阶段的单章输出。"""

    heading: str = Field(min_length=1, description="章节标题，与大纲一致。")
    text: str = Field(min_length=1, description="本章叙述性正文，多段落，段落间有逻辑衔接。")
    finding_ids: list[str] = Field(default_factory=list, description="本章采用的结论 ID。")
    evidence_ids: list[str] = Field(default_factory=list, description="本章引用的证据 ID，用于引用核验。")
    key_points: list[str] = Field(default_factory=list, description="本章要点，由应用层从大纲回填，模型无需重复生成。")


class SummaryDraft(BaseModel):
    """Writer 收束阶段的输出：执行摘要、结论与局限。"""

    executive_summary: str = Field(min_length=1, description="执行摘要：150-300字概括核心判断。")
    conclusion: str = Field(min_length=1, description="结论：回应研究问题，区分事实、推断与争议。")
    limitations: str | None = Field(default=None, description="全篇不确定性与审稿存疑点汇总；无则 null。")


class ReportBlock(BaseModel):
    """报告中的最小可追溯内容块。"""

    heading: str = Field(min_length=1, description="所属章节标题。")
    text: str = Field(min_length=1, description="面向读者的正文内容。")
    finding_ids: list[str] = Field(default_factory=list, description="正文采用的结论 ID。")
    evidence_ids: list[str] = Field(default_factory=list, description="正文直接引用的证据 ID，用于引用核验。")


class ReportDraft(BaseModel):
    """Writer 输出的报告草稿；发布前必须通过引用校验。"""

    title: str = Field(min_length=1, description="报告标题。")
    blocks: list[ReportBlock] = Field(min_length=1, description="至少一个可追溯的报告内容块。")

    def to_markdown(self, evidence: list[EvidenceCard] | None = None) -> str:
        """把报告渲染为 Markdown 文本；传入证据列表时在文末自动附参考文献。"""
        lines: list[str] = [f"# {self.title}", ""]
        for block in self.blocks:
            lines.append(f"## {block.heading}")
            lines.append("")
            lines.append(block.text)
            lines.append("")
        known = {item.id: item for item in evidence or []}
        cited = [eid for block in self.blocks for eid in block.evidence_ids if eid in known]
        if cited:
            seen_sources: set[str] = set()
            unique_sources = []
            for eid in dict.fromkeys(cited):
                source = known[eid].source
                keys = {key for key in document_keys(str(source.url), source.title) if key}
                if keys & seen_sources:
                    continue
                seen_sources.update(keys)
                unique_sources.append(source)
            lines.append("## 参考文献")
            lines.append("")
            for index, source in enumerate(unique_sources, start=1):
                meta = "，".join(part for part in (source.publisher, source.published_at) if part)
                lines.append(f"{index}. [{source.title}]({source.url})" + (f"（{meta}）" if meta else ""))
            lines.append("")
        return "\n".join(lines).strip() + "\n"

class SupplementPlanDraft(BaseModel):
    """Critic 判定需补证后，Planner 的增量规划输出：只包含新增任务。"""

    supplement_focus: str = Field(description="一句话说明本轮补证要填补的核心证据缺口。")
    tasks: list[ResearchTaskDraft] = Field(
        min_length=1, description="仅新增的补证任务，禁止重复已有结论已覆盖的子问题。")


class ResearchRun(BaseModel):
    """单次研究的持久化状态，供编排器在中断后恢复。"""

    id: str = Field(default_factory=lambda: new_id("run"), description="本次研究运行的稳定标识符。")
    user_request: str = Field(min_length=1, description="用户的原始研究请求，不能为空。")
    max_iterations: int = Field(default=3, ge=1, description="Critic 可要求补证的最大轮次，至少为 1。")
    iteration: int = Field(default=0, ge=0, description="已完成的检索轮次，不允许为负数。")
    status: RunStatus = Field(default=RunStatus.PLANNING, description="编排器当前所处的状态。")
    plan: ResearchPlan | None = Field(default=None, description="Planner 完成后生成的研究计划。")
    candidates: list[CandidateEvidence] = Field(default_factory=list, description="尚未或已经审查的候选证据记录。")
    evidence: list[EvidenceCard] = Field(default_factory=list, description="审查后可被结论和报告引用的证据。")
    findings: list[Finding] = Field(default_factory=list, description="基于已审查证据形成的结论。")
    critique: CriticReview | None = Field(default=None, description="最近一次反方审稿结果。")
    critiques: list[CriticReview] = Field(default_factory=list, description="历次反方审稿结果。")
    report: ReportDraft | None = Field(default=None, description="通过审稿后生成的报告草稿。")
    events: list[str] = Field(default_factory=list, description="状态转换和关键动作的审计事件。")

    def event(self, message: str) -> None:
        """追加可持久化的审计事件，避免 Agent 之间依赖聊天记录。"""
        self.events.append(message)

    def to_markdown(self) -> str | None:
        """把最终报告渲染为 Markdown 文本；报告尚未生成时返回 None。"""
        if self.report is None:
            return None
        return self.report.to_markdown(self.evidence)

if __name__ == '__main__':
    # data = ResearchRun(user_request="大模型使用教程")

    print(ResearchRun.model_dump())
