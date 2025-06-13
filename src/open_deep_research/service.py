from fastapi import FastAPI
from pydantic import BaseModel
import uuid
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
