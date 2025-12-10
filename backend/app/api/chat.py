"""Chat API routes."""

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.models.chat import ChatRequest, ChatResponse, SessionCreate, Session
from app.services.chat_service import chat_service
from app.middleware.auth import get_current_user_optional as get_current_user
from app.core.database import get_db
from app.core.security import generate_session_id
from app.models.database import User

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/message", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    req: Request,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a chat message and get a response.

    Supports both authenticated and anonymous users.
    """
    try:
        # Generate session ID if not provided
        session_id = request.session_id or generate_session_id()

        # Get credential session ID from cookies (for anonymous users)
        credential_session_id = req.cookies.get("session_id")

        # Use user_id for credentials if authenticated
        if user:
            credential_session_id = user.id

        # Process message
        response_text, tool_calls = await chat_service.process_message(
            message=request.message,
            datasource=request.datasource,
            session_id=session_id,
            credential_session_id=credential_session_id,
            user_id=user.id if user else None,
            db=db if user else None,
        )

        return ChatResponse(
            message=response_text,
            session_id=session_id,
            datasource=request.datasource,
            tool_calls=tool_calls if tool_calls else None,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/message/stream")
async def send_message_stream(
    request: ChatRequest,
    req: Request,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a chat message and get a streaming response.

    Supports both authenticated and anonymous users.
    """
    try:
        # Generate session ID if not provided
        session_id = request.session_id or generate_session_id()

        # Get credential session ID from cookies (for anonymous users)
        credential_session_id = req.cookies.get("session_id")

        # Use user_id for credentials if authenticated
        if user:
            credential_session_id = user.id

        async def event_generator():
            """Generate Server-Sent Events with structured agent steps."""
            import time
            step_counter = 0
            start_time = time.time()
            sources_used = []  # Track sources/tools used
            accumulated_content = ""  # For generating follow-ups

            def make_sse(data: dict) -> str:
                """Helper to format SSE data."""
                return f"data: {json.dumps(data)}\n\n"

            def make_step(step_id: str, step_type: str, title: str, status: str, description: str = "", duration: int = None) -> dict:
                """Helper to create agent step events."""
                step = {
                    "id": step_id,
                    "type": step_type,
                    "title": title,
                    "status": status,
                    "timestamp": int(time.time() * 1000)
                }
                if description:
                    step["description"] = description
                if duration is not None:
                    step["duration"] = duration
                return {"type": "agent_step", "step": step}

            def generate_follow_up_questions(query: str, datasource: str) -> List[str]:
                """Generate contextual follow-up questions based on datasource."""
                follow_ups = {
                    "mysql": [
                        "Show me the table structure",
                        "How many total records are there?",
                        "What are the most recent entries?",
                        "Can you summarize the data distribution?",
                    ],
                    "s3": [
                        "What other files are in this bucket?",
                        "Show me the file contents",
                        "How large are these files?",
                        "What's the folder structure?",
                    ],
                    "jira": [
                        "Show me high priority issues",
                        "What issues are assigned to me?",
                        "Show issues updated this week",
                        "What's the status breakdown?",
                    ],
                    "google_workspace": [
                        "Show me recent documents",
                        "What events are coming up?",
                        "Search for specific content",
                        "Show shared documents",
                    ],
                }
                return follow_ups.get(datasource, [
                    "Tell me more about this",
                    "Can you provide more details?",
                    "What else can you show me?",
                ])[:3]

            try:
                # Send session ID first
                yield make_sse({"type": "session", "session_id": session_id})

                # Send initial thinking step
                step_counter += 1
                yield make_sse(make_step(
                    f"step-{step_counter}", "thinking", "Analyzing query", "active",
                    "Understanding your request..."
                ))

                # Stream the response
                async for chunk in chat_service.process_message_stream(
                    message=request.message,
                    datasource=request.datasource,
                    session_id=session_id,
                    credential_session_id=credential_session_id,
                    user_id=user.id if user else None,
                    db=db if user else None,
                ):
                    # Check if this is a structured event (dict) or plain text
                    if isinstance(chunk, dict):
                        # Structured event from backend
                        event_type = chunk.get("type")
                        if event_type == "thinking":
                            step_counter += 1
                            yield make_sse(make_step(
                                f"step-{step_counter}", "thinking", "Thinking", "active",
                                chunk.get("content", "")
                            ))
                        elif event_type == "tool_start":
                            step_counter += 1
                            tool_name = chunk.get("tool", "tool")
                            # Track source used
                            sources_used.append({
                                "type": "tool",
                                "name": tool_name,
                                "description": chunk.get("description", "")
                            })
                            yield make_sse(make_step(
                                f"step-{step_counter}", "tool_call", f"Using {tool_name}", "active",
                                chunk.get("description", "Executing tool...")
                            ))
                        elif event_type == "tool_end":
                            tool_name = chunk.get("tool", "tool")
                            yield make_sse(make_step(
                                f"step-{step_counter}", "tool_call", f"Completed {tool_name}", "complete"
                            ))
                        elif event_type == "text":
                            content = chunk.get("content", "")
                            accumulated_content += content
                            yield make_sse({"type": "content", "content": content})
                    else:
                        # Plain text chunk
                        accumulated_content += chunk
                        yield make_sse({"type": "content", "content": chunk})

                # Send completion step
                elapsed = time.time() - start_time
                step_counter += 1
                yield make_sse(make_step(
                    f"step-{step_counter}", "complete", "Response ready", "complete",
                    f"Completed in {elapsed:.1f}s", int(elapsed * 1000)
                ))

                # Generate follow-up questions
                follow_ups = generate_follow_up_questions(request.message, request.datasource)

                # Add datasource as a source if no tools were called
                if not sources_used:
                    sources_used.append({
                        "type": "datasource",
                        "name": request.datasource,
                        "description": f"Connected to {request.datasource}"
                    })

                # Send done signal with metadata (Perplexity-style)
                yield make_sse({
                    "type": "done",
                    "sources": sources_used,
                    "follow_up_questions": follow_ups,
                    "response_time_ms": int(elapsed * 1000)
                })

            except Exception as e:
                yield make_sse({"type": "error", "error": str(e)})

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=List[str])
async def list_sessions():
    """List all active chat sessions."""
    return list(chat_service.sessions.keys())


@router.post("/sessions", response_model=dict)
async def create_session(request: SessionCreate):
    """Create a new chat session."""
    session_id = generate_session_id()
    chat_service.sessions[session_id] = []

    return {
        "session_id": session_id,
        "datasource": request.datasource,
        "name": request.name,
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    if session_id in chat_service.sessions:
        del chat_service.sessions[session_id]
        return {"message": "Session deleted"}

    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions/{session_id}/info")
async def get_session_info(
    session_id: str,
    datasource: str,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get information about a chat session including message count.

    Useful for debugging and verifying session persistence.
    """
    try:
        if user and db:
            # Authenticated user - check database
            messages = await chat_service.get_chat_history(
                user_id=user.id,
                datasource=datasource,
                session_id=session_id,
                db=db,
            )
            return {
                "session_id": session_id,
                "datasource": datasource,
                "user_id": user.id,
                "message_count": len(messages),
                "storage": "database",
                "messages": messages if len(messages) <= 5 else messages[-5:],  # Last 5 messages
            }
        else:
            # Anonymous user - check in-memory
            if session_id in chat_service.sessions:
                messages = chat_service.sessions[session_id]
                return {
                    "session_id": session_id,
                    "message_count": len(messages),
                    "storage": "in-memory",
                    "messages": messages if len(messages) <= 5 else messages[-5:],
                }
            else:
                return {
                    "session_id": session_id,
                    "message_count": 0,
                    "storage": "in-memory",
                    "messages": [],
                }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
