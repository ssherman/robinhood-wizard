from rh_wizard.broker.client import BrokerClient


class FakeTool:
    def __init__(self, name):
        self.tool_name = name


class FakeMCPClient:
    """Stand-in for strands MCPClient with the context-manager + sync call surface."""

    def __init__(self, tools, call_result):
        self._tools = tools
        self._call_result = call_result
        self.entered = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *exc):
        return False

    def list_tools_sync(self):
        return self._tools

    def call_tool_sync(self, *, tool_use_id, name, arguments=None):
        assert self.entered, "must be used inside the client context"
        assert tool_use_id, "Strands requires a non-empty tool_use_id"
        assert name == "get_accounts"
        return self._call_result


def test_list_tool_names():
    fake = FakeMCPClient([FakeTool("get_accounts"), FakeTool("get_portfolio")], None)
    with BrokerClient(fake) as broker:
        assert broker.list_tool_names() == ["get_accounts", "get_portfolio"]


def test_get_accounts_parses_results():
    payload = {"results": [{"account_number": "X1", "type": "agentic"}]}
    fake = FakeMCPClient([FakeTool("get_accounts")], {"data": payload})
    with BrokerClient(fake) as broker:
        accounts = broker.get_accounts()
    assert accounts == [{"account_number": "X1", "type": "agentic"}]


def test_get_accounts_parses_strands_text_toolresult():
    # Real Strands shape: content is a list of {"text": <json string>} items.
    tool_result = {
        "status": "success",
        "toolUseId": "rhw-1",
        "content": [{"text": '{"data": {"results": [{"account_number": "AG-9"}]}}'}],
    }
    fake = FakeMCPClient([FakeTool("get_accounts")], tool_result)
    with BrokerClient(fake) as broker:
        accounts = broker.get_accounts()
    assert accounts == [{"account_number": "AG-9"}]


def test_get_accounts_prefers_structured_content():
    tool_result = {
        "status": "success",
        "toolUseId": "rhw-2",
        "content": [{"text": "ignored"}],
        "structuredContent": {"data": {"results": [{"account_number": "AG-7"}]}},
    }
    fake = FakeMCPClient([FakeTool("get_accounts")], tool_result)
    with BrokerClient(fake) as broker:
        accounts = broker.get_accounts()
    assert accounts == [{"account_number": "AG-7"}]
