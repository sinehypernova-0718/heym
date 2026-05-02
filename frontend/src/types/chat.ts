export interface Conversation {
  id: string
  title: string
  is_pinned: boolean
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  images?: string[]
  attachmentName?: string
  created_at: string
}

export interface ConversationDetail extends Conversation {
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
  | { type: 'title'; title: string }
  | { type: 'done' }
  | { type: 'error'; text: string }
