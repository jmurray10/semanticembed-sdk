"""AutoGen code-review group chat — AFTER refactor.

Same as autogen_codereview.py, but with a `compliance` agent added to
the group chat (e.g. for license / data-handling review).

Drift you should see:

  + compliance              (added agent)
  + manager -> compliance   (added edge)

Common nodes' criticality may shift slightly because the manager's
fan-out grew from 4 to 5.
"""

import autogen


user_proxy = autogen.UserProxyAgent(
    name="user_proxy",
    human_input_mode="NEVER",
    code_execution_config={"work_dir": "/tmp/code", "use_docker": False},
)

reviewer = autogen.AssistantAgent(
    name="reviewer",
    llm_config={"model": "gpt-4o"},
    system_message="You review code for correctness, style, and idiom.",
)

tester = autogen.AssistantAgent(
    name="tester",
    llm_config={"model": "gpt-4o"},
    system_message="You write tests for the proposed changes.",
)

security = autogen.AssistantAgent(
    name="security",
    llm_config={"model": "gpt-4o"},
    system_message="You audit changes for security issues.",
)

compliance = autogen.AssistantAgent(
    name="compliance",
    llm_config={"model": "gpt-4o"},
    system_message="You check license, data-handling, and policy compliance.",
)

doc = autogen.AssistantAgent(
    name="doc",
    llm_config={"model": "gpt-4o-mini"},
    system_message="You suggest documentation updates.",
)


groupchat = autogen.GroupChat(
    agents=[reviewer, tester, security, compliance, doc],
    messages=[],
    max_round=15,
)

manager = autogen.GroupChatManager(groupchat=groupchat, llm_config={"model": "gpt-4o"})


user_proxy.initiate_chat(manager, message="Please review PR #4521 in the examples/ directory.")
