export interface DataSource {
  id: string;
  name: string;
  description: string;
  icon: string;
  enabled: boolean;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  responseTime?: number; // Time in milliseconds
  sources?: SourceReference[]; // Perplexity-like source citations
  followUpQuestions?: string[]; // Suggested follow-up questions
  thinkingContent?: string; // AI's thinking process (collapsible)
}

export interface SourceReference {
  type: 'tool' | 'datasource' | 'cache';
  name: string;
  description?: string;
  recordCount?: number;
}

export interface ChatRequest {
  message: string;
  datasource: string;
  session_id?: string;
}

export interface ChatResponse {
  message: string;
  session_id: string;
  datasource: string;
  tool_calls?: Array<{
    name: string;
    arguments: Record<string, unknown>;
    result: string;
  }>;
}

export interface User {
  id: string;
  email: string;
  name: string;
  profilePicture?: string;
  createdAt: string;
}

export interface AgentStep {
  id: string;
  type: 'thinking' | 'planning' | 'tool_call' | 'analyzing' | 'synthesizing' | 'complete' | 'error';
  title: string;
  description?: string;
  status: 'pending' | 'active' | 'complete' | 'error';
  timestamp: number;
  duration?: number;
  details?: {
    tool?: string;
    datasource?: string;
    result?: string;
  };
}
