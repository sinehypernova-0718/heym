"""Expression evaluation API."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.workflows import get_credentials_context, get_workflow_for_user
from app.db.models import CredentialType, User, Workflow
from app.db.session import get_db
from app.services.credential_access import get_accessible_credential
from app.services.encryption import decrypt_config
from app.services.expression_evaluator import (
    EXPRESSION_MAX_LENGTH,
    ExpressionEvaluateResponse,
    ExpressionEvaluatorService,
    build_eval_context,
    build_vars_context,
    get_selected_loop_total,
)
from app.services.global_variables_service import get_global_variables_context
from app.services.llm_service import execute_llm
from app.services.llm_trace import LLMTraceContext
from app.services.workflow_dsl_prompt import WORKFLOW_DSL_SYSTEM_PROMPT

router = APIRouter()


class NodeResultItem(BaseModel):
    """A node result supplied by the frontend canvas after a test run."""

    node_id: str
    label: str
    output: Any


class ExpressionEvaluateRequest(BaseModel):
    """Request payload for the unified expression evaluator endpoint."""

    expression: str = Field(..., max_length=EXPRESSION_MAX_LENGTH)
    workflow_id: UUID
    current_node_id: str
    field_name: str | None = None
    input_body: Any = None
    selected_loop_iteration_index: int | None = None
    node_results: list[NodeResultItem] = Field(default_factory=list)


class ExpressionGenerateRequest(BaseModel):
    """Request payload for AI-assisted expression generation."""

    description: str = Field(..., max_length=2000)
    workflow_id: UUID
    credential_id: UUID
    model: str
    current_node_id: str | None = None
    node_results: list[NodeResultItem] = Field(default_factory=list)


class ExpressionGenerateResponse(BaseModel):
    """Response containing the generated expression string."""

    expression: str


def _build_node_context_string(node_results: list[NodeResultItem]) -> str:
    """Format node results into a compact context block for the LLM."""
    if not node_results:
        return (
            "No prior run data available. Generate based on node labels and workflow conventions."
        )
    lines = ["Available node outputs from the last workflow run:"]
    for item in node_results:
        output_preview = json.dumps(item.output, default=str)
        if len(output_preview) > 500:
            output_preview = output_preview[:500] + "..."
        lines.append(f'\n- Node label: "{item.label}" (id: {item.node_id})')
        lines.append(f"  Output: {output_preview}")
    return "\n".join(lines)


async def _generate_expression(
    db: AsyncSession,
    request: ExpressionGenerateRequest,
    current_user: User,
) -> str:
    """Call the LLM to produce a single expression string from a plain-text description."""
    credential = await get_accessible_credential(
        db=db,
        credential_id=request.credential_id,
        user_id=current_user.id,
    )
    if not credential:
        raise ValueError("Credential not found")

    if credential.type not in (CredentialType.openai, CredentialType.google, CredentialType.custom):
        raise ValueError("Credential must be OpenAI, Google, or Custom type")

    config = decrypt_config(credential.encrypted_config)
    api_key = config.get("api_key", "")
    base_url = config.get("base_url") if credential.type == CredentialType.custom else None

    generate_suffix = (
        "\n\n---\n\n"
        "## Expression Generation Task\n\n"
        "Given the workflow context below, return ONLY a single bare expression that satisfies "
        "the user's description. No explanation, no JSON, no markdown – just the expression string.\n"
        "The expression must follow the Heym expression DSL described above.\n"
        "Start the expression with `$`."
    )
    system_prompt = WORKFLOW_DSL_SYSTEM_PROMPT + generate_suffix

    node_context = _build_node_context_string(request.node_results)
    user_message = f"Description: {request.description}\n\n{node_context}"

    trace_ctx = LLMTraceContext(
        user_id=current_user.id,
        credential_id=request.credential_id,
        workflow_id=request.workflow_id,
        source="expression_generate",
        node_label="expression_generate",
    )
    result = await execute_llm(
        credential_type=credential.type.value,
        api_key=api_key,
        base_url=base_url,
        model=request.model,
        system_instruction=system_prompt,
        user_message=user_message,
        temperature=0.2,
        max_tokens=200,
        trace_context=trace_ctx,
    )
    return result.get("text", "").strip()


async def get_workflow_by_id(
    workflow_id: UUID,
    db: AsyncSession,
    user: User,
) -> Workflow | None:
    """Load a workflow only when the caller has access to it."""
    return await get_workflow_for_user(db, workflow_id, user.id)


@router.post(
    "/evaluate",
    response_model=ExpressionEvaluateResponse,
    status_code=status.HTTP_200_OK,
)
async def evaluate_expression(
    request: ExpressionEvaluateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExpressionEvaluateResponse:
    """Evaluate an expression or template using pinned data and last-run node outputs."""
    workflow = await get_workflow_by_id(request.workflow_id, db, current_user)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    workflow_nodes = list(workflow.nodes or [])
    workflow_edges = list(workflow.edges or [])
    canvas_results = [
        {
            "node_id": item.node_id,
            "label": item.label,
            "output": item.output,
        }
        for item in request.node_results
    ]
    context = build_eval_context(
        workflow_nodes,
        canvas_results,
        workflow_edges=workflow_edges,
        current_node_id=request.current_node_id,
        initial_inputs=request.input_body,
        selected_loop_iteration_index=request.selected_loop_iteration_index,
    )
    vars_context = build_vars_context(
        workflow_nodes,
        canvas_results,
        workflow_edges=workflow_edges,
        current_node_id=request.current_node_id,
    )

    credentials_owner_id = current_user.id if current_user else workflow.owner_id
    credentials_context = await get_credentials_context(db, credentials_owner_id)
    global_variables_context = await get_global_variables_context(db, credentials_owner_id)

    service = ExpressionEvaluatorService(
        workflow_nodes=workflow_nodes,
        workflow_edges=workflow_edges,
        credentials_context=credentials_context,
        global_variables_context=global_variables_context,
        vars_context=vars_context,
    )
    response = service.evaluate(
        request.expression,
        context,
        current_node_id=request.current_node_id,
    )
    response.selected_loop_total = get_selected_loop_total(
        workflow_nodes,
        workflow_edges,
        request.current_node_id,
        context,
        service,
    )
    return response


@router.post(
    "/generate",
    response_model=ExpressionGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_expression(
    request: ExpressionGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExpressionGenerateResponse:
    """Generate a Heym expression from a plain-text description using an LLM."""
    try:
        expression = await _generate_expression(db=db, request=request, current_user=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ExpressionGenerateResponse(expression=expression)
