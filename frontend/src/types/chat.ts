import type { WorkflowEdge, WorkflowNode } from "@/types/workflow"

export interface WorkflowPreview {
  id: string
  name: string
  description: string | null
  url: string
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
}

export interface Conversation {
  id: string
  title: string
  is_pinned: boolean
  is_running: boolean
  has_unread: boolean
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  images?: string[]
  attachmentName?: string
  workflowPreview?: WorkflowPreview
  created_at: string
}

export interface ConversationDetail extends Conversation {
  last_credential_id: string | null
  last_model: string | null
  messages: Message[]
}

export interface ConversationCreate {
  title?: string
}

export interface ConversationUpdate {
  title?: string
  is_pinned?: boolean
}

export interface MessageCreate {
  content: string
  credential_id: string
  model: string
}

export type SSEChunk =
  | { type: 'content'; text: string }
  | { type: 'step'; label: string }
  | { type: 'tool_output'; images: string[] }
  | { type: 'workflow_created'; workflow: WorkflowPreview }
  | { type: 'title'; title: string }
  | { type: 'done' }
  | { type: 'error'; text: string }
