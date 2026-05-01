"""AutoGen code-review group chat — parsable example.

Try::

    import semanticembed as se
    edges = se.extract.from_autogen("examples/autogen_codereview.py")

Topology (extracted by from_autogen):

    user_proxy -> manager           (initiate_chat call)

    manager -> reviewer             (GroupChatManager fans out to chat agents)
    manager -> tester
    manager -> security
    manager -> doc
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

doc = autogen.AssistantAgent(
    name="doc",
    llm_config={"model": "gpt-4o-mini"},
    system_message="You suggest documentation updates.",
)


groupchat = autogen.GroupChat(
    agents=[reviewer, tester, security, doc],
    messages=[],
    max_round=15,
)

manager = autogen.GroupChatManager(groupchat=groupchat, llm_config={"model": "gpt-4o"})


user_proxy.initiate_chat(manager, message="Please review PR #4521 in the examples/ directory.")
