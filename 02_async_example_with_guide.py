"""비동기 Cursor SDK로 로컬 에이전트에 프롬프트를 한 번 보내는 예제.

하는 일은 한 가지다. 이 저장소를 한 문장으로 요약하라고 시키고, 끝난 뒤
상태와 답변을 출력한다.

async를 처음 본다면 아래 네 가지만 알면 이 파일을 읽을 수 있다.

1. `async def`로 만든 함수는 호출해도 바로 실행되지 않는다.
   `main()`은 "나중에 실행할 작업 설명서"(코루틴)만 만든다.
2. `asyncio.run(main())`이 그 설명서를 실제로 돌리는 이벤트 루프를 켠다.
   루프는 `main()`이 끝나거나 예외가 날 때까지 이 프로세스를 붙잡는다.
3. `await`는 "이 작업이 끝날 때까지 이 함수를 잠시 멈춘다"는 뜻이다.
   멈춘 동안 루프는 다른 작업을 할 수 있다. 이 예제에는 다른 작업이 없어서,
   보이는 효과는 "이 줄에서 기다렸다가 다음 줄로 간다"와 같다.
4. 비동기 SDK에는 자동으로 만들어 주는 기본 클라이언트가 없다.
   `AsyncClient.launch_bridge()`로 브릿지를 직접 띄우고, 그 클라이언트를
   `client=`로 넘겨야 한다. 동기 `Agent.prompt()`는 이 과정을 숨기지만,
   Windows에서는 그 숨은 시작 코드가 파이프에 select()를 써서
   WinError 10038로 실패한다. 비동기 시작 코드는 그 경로를 타지 않는다.

동기 클래스와의 대응은 이름만 다르다.

    CursorClient -> AsyncClient
    Agent        -> AsyncAgent

실행: python 02_async_example_with_guide.py
`.env`에는 `CURSOR_API_KEY=...` 한 줄이 있어야 한다.
"""

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

# 이 줄들은 async가 아니다. 파일을 실행하면 이벤트 루프보다 먼저 그대로 실행된다.
root = Path(__file__).resolve().parent
workspace = root / "workspace"
load_dotenv(root / ".env")


async def main() -> None:
    # 이 함수 본문은 asyncio.run(main())이 호출된 뒤에야 실행된다.
    print("1. main()이 시작됐다. 여기까지는 브릿지도 에이전트도 없다.")
    print(f"   작업 폴더: {workspace}")
    print("   API 키는 .env의 CURSOR_API_KEY에서 읽는다. 값은 출력하지 않는다.")

    # launch_bridge()도 async def다. await 없이 호출하면 브릿지가 뜨지 않고,
    # 코루틴 객체만 생긴 채 다음 줄로 넘어간다.
    #
    # await가 끝나는 시점은 브릿지 프로세스가 뜨고, 주소와 인증 토큰을 담은
    # 클라이언트가 반환된 때다. 한 줄로 쓰면 아래와 같다.
    #
    #     async with await AsyncClient.launch_bridge(workspace=workspace) as client:
    #
    # `await ...`가 클라이언트를 만들고, `async with`가 블록을 벗어날 때
    # client.aclose()로 브릿지 프로세스를 끈다. 아래는 그 두 단계를 나눠
    # 어디서 기다리는지 보이게 한 것이다. 동작은 같다.
    print("2. 브릿지를 띄우는 중. 이 줄의 await가 끝나기 전에는 3으로 가지 않는다.")
    client = await AsyncClient.launch_bridge(workspace=workspace)
    print("3. 브릿지가 준비됐다. 이후 SDK 호출은 이 client를 통해 나간다.")

    try:
        # AsyncAgent.prompt()는 일회용 호출이다. 내부에서 에이전트를 만들고,
        # 메시지 하나를 보내고, 실행이 끝날 때까지 기다린 다음, 에이전트를 닫는다.
        # 브릿지(client)는 닫지 않는다. 그건 아래 finally가 담당한다.
        #
        # local을 비우면 로컬 실행이 기본값이 된다. 클라우드로 돌리려다 빼먹으면
        # 조용히 로컬 에이전트가 되므로, 어느 쪽인지 코드에 드러나게 항상 넘긴다.
        # model은 로컬 실행에서 필수다.
        #
        # Grok 4.7의 Fast는 별도 모델 ID가 아니다. 같은 id "grok-4.7"에
        # 파라미터 fast=true를 붙인 프리셋이다. 문자열만 넘기면 Fast가 꺼진
        # 기본 선택이다.
        print("4. 프롬프트를 보냈다. 에이전트가 끝날 때까지 이 await에서 기다린다.")
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

        # 여기까지 왔다면 예외 없이 실행이 끝난 것이다.
        # status는 그 실행의 결과다. "finished"면 정상 종료, "error"면
        # 실행은 시작됐지만 도중에 실패, "cancelled"면 취소다.
        # 키 오류나 브릿지 연결 실패처럼 실행 자체가 시작되지 않은 경우는
        # status가 아니라 CursorAgentError 예외로 이 줄 이전에 빠진다.
        print("5. 대기 끝. 에이전트 실행이 종료됐다.")
        print(f"   status: {result.status}")
        print(f"   run id: {result.id}")
        print(result.result)
    finally:
        # 성공이든 예외든 브릿지 자식 프로세스를 끈다. await인 이유는
        # 종료 요청을 브릿지에 보내고 프로세스가 끝날 때까지 기다리기 때문이다.
        print("6. 브릿지를 종료한다.")
        await client.aclose()
        print("7. 브릿지가 종료됐다. main()이 끝나면 이벤트 루프도 끝난다.")


print("0. 이벤트 루프를 켠다. main()이 반환할 때까지 이 줄에서 기다린다.")
asyncio.run(main())
print("8. asyncio.run()이 반환했다. 프로세스는 여기서 끝난다.")
