from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uuid
import json
from langgraph.types import Command
from .graph import graph

app = FastAPI()

class TopicRequest(BaseModel):
    topic: str

class ResearchResponse(BaseModel):
    report: str

@app.post("/research", response_model=ResearchResponse)
async def run_research(req: TopicRequest) -> ResearchResponse:
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in graph.astream({"topic": req.topic}, thread):
        if "__interrupt__" in event:
            break

    async for _ in graph.astream(Command(resume=True), thread):
        pass

    state = graph.get_state(thread)
    report = state.values.get("final_report", "")
    return ResearchResponse(report=report)


@app.post("/research_stream")
async def run_research_stream(req: TopicRequest):
    """Run research and stream the plan and final report."""
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async def event_generator():
        async for event in graph.astream({"topic": req.topic}, thread, stream_mode="updates"):
            if "__interrupt__" in event:
                plan = event["__interrupt__"][0].value
                yield json.dumps({"plan": plan}) + "\n"
                break

        async for _ in graph.astream(Command(resume=True), thread, stream_mode="updates"):
            pass

        state = graph.get_state(thread)
        report = state.values.get("final_report", "")
        yield json.dumps({"final_report": report}) + "\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
