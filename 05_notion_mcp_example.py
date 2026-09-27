import asyncio
import os
from pathlib import Path

from cursor_sdk import (
    AgentOptions,
    AsyncAgent,
    AsyncClient,
    HttpMcpServerConfig,
    LocalAgentOptions,
    ModelParameterValue,
    ModelSelection,
)
from dotenv import load_dotenv
from notion_mcp_oauth import get_notion_mcp_access_token

root = Path(__file__).resolve().parent
workspace = root / "workspace"
load_dotenv(root / ".env")


async def main() -> None:
    # OAuth는 HTTP MCP 연결 전에 끝나야 한다. 최초 실행에서는 브라우저에서
    # 워크스페이스를 승인하고, 이후에는 저장된 refresh token을 사용한다.
    access_token = await asyncio.to_thread(get_notion_mcp_access_token)

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
                local=LocalAgentOptions(cwd=str(workspace)),
                mcp_servers={
                    "notion": HttpMcpServerConfig(
                        url="https://mcp.notion.com/mcp",
                        headers={"Authorization": f"Bearer {access_token}"},
                    ),
                },
            ),
            client=client,
        )
        print(result.status)
        print(result.result)


asyncio.run(main())
