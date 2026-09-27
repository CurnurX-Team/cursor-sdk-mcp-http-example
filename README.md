# Cursor SDK로 MCP를 붙일 때

`01`, `02`는 비동기 `AsyncAgent.prompt`를 처음 호출해 본 예제다. MCP가 주제가 아니라서 여기서는 다루지 않는다.

| 발표 | 파일 | 붙인 방법 | 결과 | 팀에 공유할 점 |
| --- | --- | --- | --- | --- |
| 03 | `03_learn_mcp_http_example.py` | `AgentOptions.mcp_servers`에 Microsoft Learn HTTP 주소를 직접 넣음 | 동작함. `microsoft_docs_search`가 호출되고 문서 제목, URL, 본문 인용이 돌아옴 | 인증이 없는 HTTP MCP는 이 방식이 가장 짧고 결과가 분명하다 |
| 04 | `04_learn_mcp_json_example.py` | `setting_sources=["project"]`로 `.cursor/mcp.json`을 읽게 함 | 동작함. `mcp.json`을 이 저장소의 git 루트 `.cursor/mcp.json`으로 옮긴 뒤 Microsoft Learn 검색이 된다 | project MCP는 `LocalAgentOptions.cwd` 바로 아래가 아니라, 그 cwd를 감싸는 **가장 가까운 git 루트**의 `.cursor/mcp.json`을 읽는다. `learn-workspace/.cursor/mcp.json`에 두면 이 저장소 루트의 `.git`이 먼저 잡혀서 그 파일은 읽히지 않는다 |
| 05 | `05_notion_mcp_example.py` | 자체 OAuth 클라이언트로 로그인한 뒤 OAuth access token을 `HttpMcpServerConfig.headers`에 전달 | 동작함. 최초 브라우저 승인과 재실행 모두에서 최근 Notion 페이지를 조회함 | Cursor IDE의 플러그인 OAuth는 로컬 SDK의 `inline:notion`에서 재사용되지 않았다. DCR·PKCE·refresh token 처리를 별도로 구현하면 STDIO 없이 HTTP MCP를 사용할 수 있다 |

## 05: Notion MCP OAuth 흐름

한 줄로 요약하면 **사용자가 브라우저에서 한 번 권한을 허용하고, 프로그램은
그 결과로 받은 token을 사용해 Notion MCP에 접속하는 과정**이다.

역할은 두 파일로 나뉜다.

| 파일 | 역할 |
| --- | --- |
| `notion_mcp_oauth.py` | 로그인, 브라우저 callback, token 발급·저장·갱신 담당 |
| `05_notion_mcp_example.py` | 발급된 access token으로 Notion HTTP MCP를 호출 |

### 최초 실행 순서

| 순서 | 누가 | 하는 일 | 결과 |
| --- | --- | --- | --- |
| 1 | 프로그램 | Notion의 OAuth 설정 주소를 조회한다 | 등록·로그인·token 발급 주소를 알게 된다 |
| 2 | 프로그램 | Notion에 이 예제를 OAuth 클라이언트로 등록한다(DCR) | 이 프로그램을 식별하는 `client_id`를 받는다 |
| 3 | 프로그램 | 일회용 PKCE `verifier`와 `challenge`를 만든다 | 로그인 도중 authorization code가 탈취되는 것을 막는다 |
| 4 | 프로그램 | `localhost:8787`에 임시 callback 서버를 열고 브라우저를 실행한다 | Notion 권한 승인 화면이 열린다 |
| 5 | 사용자 | 연결할 워크스페이스와 권한을 확인하고 승인한다 | Notion이 일회용 authorization code를 callback으로 보낸다 |
| 6 | 프로그램 | code와 PKCE verifier를 Notion에 제출한다 | `access token`과 `refresh token`을 받는다 |
| 7 | 프로그램 | access token을 HTTP `Authorization: Bearer ...` 헤더에 넣는다 | `https://mcp.notion.com/mcp`의 도구를 호출할 수 있다 |
| 8 | 프로그램 | token을 `.notion-mcp-oauth.json`에 저장한다 | 다음 실행부터 브라우저 로그인을 생략할 수 있다 |

```text
사용자 승인
   ↓
localhost:8787/callback
   ↓ authorization code
token 교환
   ↓ access token
HttpMcpServerConfig
   ↓ Authorization 헤더
Notion MCP
```

### 두 번째 실행부터

| token 상태 | 프로그램의 동작 | 사용자 로그인 |
| --- | --- | --- |
| access token이 아직 유효함 | 저장된 access token을 바로 사용 | 필요 없음 |
| access token이 곧 만료됨 | refresh token으로 새 access token을 발급 | 필요 없음 |
| refresh token도 사용할 수 없음 | OAuth를 처음부터 다시 시작 | 다시 승인 필요 |

### 용어 정리

| 용어 | 쉽게 말하면 | 수명/용도 |
| --- | --- | --- |
| `client_id` | Notion이 이 프로그램을 구분하는 이름표 | 등록 후 계속 재사용 |
| PKCE `verifier` | 현재 로그인 요청을 시작한 프로그램임을 증명하는 임시 비밀값 | 로그인 한 번에만 사용 |
| authorization code | 사용자 승인이 끝났다는 일회용 교환권 | token으로 바꾸고 폐기 |
| access token | Notion MCP를 실제로 호출할 때 보여 주는 출입증 | 짧게 사용 |
| refresh token | 만료된 access token을 새로 받기 위한 갱신권 | 재로그인 없이 갱신할 때 사용 |

OAuth 정보는 저장소 루트의 `.notion-mcp-oauth.json`에 저장되며 Git에서
제외된다. 이 파일에는 실제 사용자 권한을 가진 token이 평문으로 들어 있으므로
공유하거나 커밋하면 안 된다. 이 예제는 로컬 학습용이며, 운영 환경에서는 OS
자격 증명 저장소나 비밀 관리 서비스를 사용해야 한다.

```powershell
python 05_notion_mcp_example.py
```
