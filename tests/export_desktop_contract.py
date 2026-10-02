"""Produce representative real plugin schemas for validation by OpenAI's SDK."""
import json
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import remctl_mcp as m
from test_mcp_server import FakeExecutor, request
with tempfile.TemporaryDirectory() as state:
    os.environ.update(REMCTL_PLUGIN="1", REMCTL_CONFIG_DIR=state)
    executor=FakeExecutor(stdout=json.dumps({"lists":[{"id":9,"title":"Demo","badge":{"emoji":"🌈"}}],"sharees":[{"objectUUID":"member","name":"Member"}],"items":[{"name":"demo"}]}))
    server=m.MCPServer(m.ServerConfig(version="test",executor=executor))
    meta={m.META_PROTOCOL_VERSION:m.MODERN_PROTOCOL_VERSIONS[0],m.META_CLIENT_CAPABILITIES:{"extensions":{"openai/elicitation":{"form":{}}}}}
    form=request(server,"tools/call",{"name":"choose_reminder_details","arguments":{"listId":9,"reminderId":42},"_meta":meta})['result']['inputRequests']['details']['params']['requestedSchema']
    print(json.dumps({"form":form,"settings":server.plugin.settings(),"tools":server.plugin.descriptors()}))
