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
learn_workspace = root / "learn-workspace"
load_dotenv(root / ".env")


async def main() -> None:
    # project 설정은 cwd를 감싸는 가장 가까운 git 루트의 .cursor/mcp.json을 읽는다.
    async with await AsyncClient.launch_bridge(workspace=learn_workspace) as client:
        result = await AsyncAgent.prompt(
            "Microsoft Learn MCP의 검색 도구로 'Azure Functions MCP 트리거'를 검색해 줘. "
            "사전 지식은 쓰지 말고 도구 응답에 있는 내용만 사용해서 다음을 출력해 줘: "
            "1) 호출한 MCP 도구 이름, "
            "2) 상위 3개 결과의 제목과 전체 URL(응답에 있는 그대로), "
            "3) 첫 번째 결과 본문에서 가져온 문장 하나를 원문 그대로 인용. "
            "Learn MCP 도구가 없거나 첫 호출이 실패하면, "
            "재시도나 다른 방법을 쓰지 말고 실패 사유만 한 줄로 말하고 종료해 줘.",
            AgentOptions(
                api_key=os.environ["CURSOR_API_KEY"],
                model=ModelSelection(
                    id="grok-4.7",
                    params=[ModelParameterValue(id="fast", value="true")],
                ),
                local=LocalAgentOptions(
                    cwd=str(learn_workspace),
                    setting_sources=["project"],
                ),
            ),
            client=client,
        )
        print(result.status)
        print(result.result)


asyncio.run(main())
