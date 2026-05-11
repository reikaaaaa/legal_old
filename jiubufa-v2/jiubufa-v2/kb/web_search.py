"""
联网搜索法条工具。

使用 DeepSeek V4 Flash 联网搜索最新的中国法律法规，
补充本地知识库的不足。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from llm import LLMClient
from config import WEB_SEARCH_MODEL, WEB_SEARCH_TOP_K

logger = logging.getLogger("jiubufa.kb.web_search")


SYSTEM_PROMPT = """你是一位专业的法律检索专家，负责搜索中国最新的法律法规。

请根据查询条件搜索相关法律法规，包括：
- 法律（全国人大及其常委会制定）
- 行政法规（国务院制定）
- 司法解释（最高人民法院、最高人民检察院制定）
- 部门规章（国务院各部委制定）
- 地方性法规（如适用）

搜索要求：
1. 优先返回现行有效的法律法规
2. 包含最新的司法解释和修正案
3. 注明法条的效力状态
4. 说明与查询案件的关联性

请严格按照以下JSON格式输出：
{
  "laws": [
    {
      "law_name": "法律名称",
      "article_no": "条文号（如：第一千零七十九条）",
      "article_text": "法条原文",
      "effective_status": "现行有效/已废止/尚未生效",
      "relevance_reason": "与本案的关联性说明",
      "source_url": "来源URL（如有）"
    }
  ]
}"""


def build_search_query(
    query_text: str,
    case_cause: Optional[str] = None,
    legal_domain: Optional[str] = None,
    claim_type: Optional[str] = None,
    defense_type: Optional[str] = None,
) -> str:
    """构建联网搜索查询语句"""
    parts = [query_text]
    if case_cause:
        parts.append(f"案由：{case_cause}")
    if legal_domain:
        parts.append(f"法律领域：{legal_domain}")
    if claim_type:
        parts.append(f"请求类型：{claim_type}")
    if defense_type:
        parts.append(f"抗辩类型：{defense_type}")
    return " | ".join(parts)


def search_laws_online(
    query_text: str,
    case_cause: Optional[str] = None,
    legal_domain: Optional[str] = None,
    claim_type: Optional[str] = None,
    defense_type: Optional[str] = None,
    top_k: int = 2,
    model_id: str = WEB_SEARCH_MODEL,
    llm: Optional[LLMClient] = None,
) -> List[Dict[str, Any]]:
    """
    使用 DeepSeek V4 Flash 联网搜索相关法条。
    
    参数：
        query_text: 搜索查询文本
        case_cause: 案由
        legal_domain: 法律领域
        claim_type: 请求类型
        defense_type: 抗辩类型
        top_k: 返回前K个最相关的法条（默认2个）
        model_id: 使用的模型ID
        llm: LLM客户端实例（可选，默认创建新实例）
    
    返回：
        法条列表，每个法条包含 law_name, article_no, article_text 等字段
    """
    if llm is None:
        llm = LLMClient()
    
    search_query = build_search_query(
        query_text=query_text,
        case_cause=case_cause,
        legal_domain=legal_domain,
        claim_type=claim_type,
        defense_type=defense_type,
    )
    
    user_prompt = f"""请搜索与以下条件相关的中国法律法规，返回最相关的 {top_k} 个法条：

查询内容：{search_query}

要求：
1. 优先返回现行有效的法律法规
2. 包含司法解释和最新修正案
3. 每个法条注明效力状态
4. 说明与本案的关联性
5. 只返回最相关的 {top_k} 个法条"""

    try:
        logger.info(f"开始联网搜索法条：{search_query}")
        result = llm.chat_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model_id=model_id,
            step_key="web_law_search",
            temperature=0.1,
            max_tokens=8192,
        )
        
        laws = result.get("laws", [])
        logger.info(f"联网搜索完成，返回 {len(laws)} 个法条")
        
        # 限制返回数量
        return laws[:top_k]
        
    except Exception as e:
        logger.error(f"联网搜索法条失败：{e}")
        return []


def search_request_basis_online(
    claim_text: str,
    claim_types: List[str],
    case_causes: List[str],
    legal_domains: List[str],
    top_k: int = 2,
    llm: Optional[LLMClient] = None,
) -> List[Dict[str, Any]]:
    """
    联网搜索请求权基础法条。
    
    参数：
        claim_text: 诉讼请求文本
        claim_types: 请求类型列表
        case_causes: 案由列表
        legal_domains: 法律领域列表
        top_k: 返回前K个法条
        llm: LLM客户端实例
    
    返回：
        法条列表
    """
    claim_type_str = "、".join(claim_types) if claim_types else None
    case_cause_str = "、".join(case_causes) if case_causes else None
    legal_domain_str = "、".join(legal_domains) if legal_domains else None
    
    return search_laws_online(
        query_text=claim_text,
        case_cause=case_cause_str,
        legal_domain=legal_domain_str,
        claim_type=claim_type_str,
        top_k=top_k,
        llm=llm,
    )


def search_defense_basis_online(
    defense_text: str,
    defense_types: List[str],
    case_causes: List[str],
    legal_domains: List[str],
    top_k: int = 2,
    llm: Optional[LLMClient] = None,
) -> List[Dict[str, Any]]:
    """
    联网搜索抗辩权基础法条。
    
    参数：
        defense_text: 答辩/抗辩文本
        defense_types: 抗辩类型列表
        case_causes: 案由列表
        legal_domains: 法律领域列表
        top_k: 返回前K个法条
        llm: LLM客户端实例
    
    返回：
        法条列表
    """
    defense_type_str = "、".join(defense_types) if defense_types else None
    case_cause_str = "、".join(case_causes) if case_causes else None
    legal_domain_str = "、".join(legal_domains) if legal_domains else None
    
    return search_laws_online(
        query_text=defense_text,
        case_cause=case_cause_str,
        legal_domain=legal_domain_str,
        defense_type=defense_type_str,
        top_k=top_k,
        llm=llm,
    )


def format_web_laws_for_prompt(laws: List[Dict[str, Any]]) -> str:
    """
    将联网搜索的法条格式化为 prompt 文本。
    
    参数：
        laws: 法条列表
    
    返回：
        格式化的文本
    """
    if not laws:
        return "（无联网搜索结果）"
    
    lines = ["【联网搜索补充法条】"]
    for i, law in enumerate(laws, 1):
        law_name = law.get("law_name", "未知法律")
        article_no = law.get("article_no", "未知条文号")
        article_text = law.get("article_text", "（无原文）")
        effective_status = law.get("effective_status", "未知")
        relevance = law.get("relevance_reason", "")
        
        lines.append(f"\n法条 {i}：")
        lines.append(f"  法律名称：{law_name}")
        lines.append(f"  条文号：{article_no}")
        lines.append(f"  效力状态：{effective_status}")
        lines.append(f"  法条原文：{article_text}")
        if relevance:
            lines.append(f"  关联性：{relevance}")
    
    return "\n".join(lines)
