import asyncio
import os
from pathlib import Path

from cursor_sdk import (
    AgentOptions,
    AsyncAgent,
    AsyncClient,
    LocalAgentOptions,
    ModelParameterValue,
    ModelSelection,
)
from dotenv import load_dotenv

root = Path(__file__).resolve().parent
workspace = root / "workspace"
load_dotenv(root / ".env")


async def main() -> None:
    async with await AsyncClient.launch_bridge(workspace=workspace) as client:
        result = await AsyncAgent.prompt(
            "Notion MCP로 최근에 수정한 페이지 제목 하나를 찾아서 알려 줘. "
            "Notion 도구가 없거나 첫 호출이 실패하면, "
            "재시도나 다른 방법(웹 검색, 파일 탐색, 우회)을 하지 말고 "
            "실패 사유, 시도했던 방식 한 줄만 말하고 즉시 종료해 줘.",
            AgentOptions(
                api_key=os.environ["CURSOR_API_KEY"],
                model=ModelSelection(
                    id="grok-4.7",
                    params=[ModelParameterValue(id="fast", value="true")],
                ),
                local=LocalAgentOptions(
                    cwd=str(workspace),
                    setting_sources=["all"],
                ),
            ),
            client=client,
        )
        print(result.status)
        print(result.result)


asyncio.run(main())
