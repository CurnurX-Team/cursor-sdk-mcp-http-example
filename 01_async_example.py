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
            "이 저장소가 무엇을 하는지 한 문장으로 요약해 줘.",
            AgentOptions(
                api_key=os.environ["CURSOR_API_KEY"],
                model=ModelSelection(
                    id="grok-4.7",
                    params=[ModelParameterValue(id="fast", value="true")],
                ),
                local=LocalAgentOptions(cwd=str(workspace)),
            ),
            client=client,
        )
        print(result.status)
        print(result.result)


asyncio.run(main())
