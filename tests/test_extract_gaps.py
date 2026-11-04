"""Regressions for extractor gaps found on outside repos.

CrewAI decorator crews (crewAIInc/crewAI-examples stock_analysis and
surprise_trip), LangGraph Command routing and multiple StateGraphs
(langchain-ai/open_deep_research deep_researcher.py), Terraform resources
that share a name (terraform-aws-modules vpc/eks), and from_directory
include/exclude.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from semanticembed import extract

FIX = Path(__file__).parent / "fixtures"


def test_crewai_decorator_sequential_crew():
    edges = set(extract.from_crewai(str(FIX / "crew_decorator" / "crew.py")))
    assert {("planner", "plan_task"), ("scout", "scout_task"), ("compiler", "compile_task")} <= edges
    assert {("plan_task", "scout_task"), ("scout_task", "compile_task")} <= edges
    assert ("plan_task", "compile_task") in edges  # tasks.yaml context


def test_crewai_redefined_task_keeps_last_body_and_source_order(tmp_path):
    # stock_analysis defines financial_analysis twice. Python's class dict
    # keeps the first slot and the last body, and CrewBase iterates that dict.
    f = tmp_path / "crew.py"
    f.write_text(textwrap.dedent("""
        from crewai import Agent, Crew, Process, Task
        from crewai.project import CrewBase, agent, crew, task

        @CrewBase
        class StockAnalysisCrew:
            @agent
            def financial_agent(self):
                return Agent()
            @task
            def financial_analysis(self):
                return Task(agent=self.financial_agent())
            @agent
            def research_analyst_agent(self):
                return Agent()
            @task
            def research(self):
                return Task(agent=self.research_analyst_agent())
            @agent
            def financial_analyst_agent(self):
                return Agent()
            @task
            def financial_analysis(self):
                return Task(agent=self.financial_analyst_agent())
            @task
            def filings_analysis(self):
                return Task(agent=self.financial_analyst_agent())
            @agent
            def investment_advisor_agent(self):
                return Agent()
            @task
            def recommend(self):
                return Task(agent=self.investment_advisor_agent())
            @crew
            def crew(self):
                return Crew(process=Process.sequential)
    """))
    edges = set(extract.from_crewai(str(f)))
    assert edges == {
        ("financial_analyst_agent", "financial_analysis"),
        ("research_analyst_agent", "research"),
        ("financial_analyst_agent", "filings_analysis"),
        ("investment_advisor_agent", "recommend"),
        ("financial_analysis", "research"),
        ("research", "filings_analysis"),
        ("filings_analysis", "recommend"),
    }


def test_crewai_hierarchical_manager(tmp_path):
    f = tmp_path / "crew.py"
    f.write_text(textwrap.dedent("""
        @CrewBase
        class C:
            @agent
            def mgr(self):
                return Agent()
            @agent
            def worker(self):
                return Agent()
            @task
            def t1(self):
                return Task(agent=self.worker())
            @task
            def t2(self):
                return Task(agent=self.worker())
            @crew
            def crew(self):
                return Crew(process=Process.hierarchical, manager_agent=self.mgr())
    """))
    edges = set(extract.from_crewai(str(f)))
    assert ("mgr", "worker") in edges
    assert ("t1", "t2") not in edges


def test_crewai_yaml_agent_used_when_task_has_no_inline_agent(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "tasks.yaml").write_text(
        "draft:\n  description: draft\n  agent: writer\n"
        "edit:\n  description: edit\n  agent: scout\n  context: [draft]\n",
        encoding="utf-8",
    )
    f = tmp_path / "crew.py"
    f.write_text(textwrap.dedent("""
        from crewai.project import CrewBase, agent, task

        @CrewBase
        class C:
            tasks_config = "config/tasks.yaml"
            @agent
            def writer(self):
                return Agent()
            @agent
            def scout(self):
                return Agent()
            @task
            def draft(self):
                return Task(config=self.tasks_config["draft"])
            @task
            def edit(self):
                return Task(config=self.tasks_config["edit"], agent=self.writer())
    """))
    edges = set(extract.from_crewai(str(f)))
    assert ("writer", "draft") in edges  # yaml agent, no inline agent
    assert ("writer", "edit") in edges   # inline agent overrides yaml agent: scout
    assert ("scout", "edit") not in edges
    assert ("draft", "edit") in edges     # yaml context, and the sequential chain


def test_celery_task_decorator_is_not_a_crew(tmp_path):
    f = tmp_path / "jobs.py"
    f.write_text(textwrap.dedent("""
        class Jobs:
            @task
            def job(self):
                return Task(agent=self.worker())
            @agent
            def worker(self):
                return Agent()
    """))
    assert extract.from_crewai(str(f)) == []


def test_langgraph_command_goto_and_annotations():
    edges = set(extract.from_langgraph(str(FIX / "langgraph_command.py")))
    assert ("clarify", "write_brief") in edges
    assert ("clarify", "END") in edges
    assert ("write_brief", "research") in edges
    assert ("supervisor", "supervisor_tools") in edges
    assert ("supervisor_tools", "supervisor") in edges


def test_langgraph_multiple_builders_keep_separate_start_end():
    edges = set(extract.from_langgraph(str(FIX / "langgraph_command.py")))
    assert ("START", "clarify") in edges and ("report", "END") in edges
    # Mounted subgraph: entry and exit go through the parent node.
    assert ("research", "supervisor") in edges
    assert ("supervisor_tools", "research") in edges
    assert ("START", "supervisor") not in edges
    # Unmounted extra builder does not share the top graph's sentinels.
    assert ("START[worker]", "worker") in edges and ("worker", "END[worker]") in edges
    assert ("START", "worker") not in edges


def test_langgraph_single_graph_command_keeps_bare_sentinels(tmp_path):
    f = tmp_path / "g.py"
    f.write_text(textwrap.dedent("""
        from typing import Literal
        from langgraph.graph import StateGraph, START, END
        from langgraph.types import Command

        def unused(state):
            return Command(goto="nope")

        def a(state) -> Command[Literal["b", "__end__"]]:
            return Command(goto=END)

        g = StateGraph(dict)
        g.add_node("a", a)
        g.add_node("b", lambda s: s)
        g.set_entry_point("a")
        g.add_edge("b", END)
    """))
    edges = set(extract.from_langgraph(str(f)))
    assert ("START", "a") in edges
    assert ("a", "b") in edges
    assert ("a", "END") in edges
    assert ("b", "END") in edges
    assert not any(node.startswith("START[") or node.startswith("END[") for edge in edges for node in edge)
    assert ("unused", "nope") not in edges
    assert ("a", "nope") not in edges


def test_langgraph_send_and_later_invoked_subgraph(tmp_path):
    # The invoked subgraph is defined AFTER the parent. It must not take
    # the bare START/END, and the call site links to the subgraph entry.
    f = tmp_path / "g.py"
    f.write_text(textwrap.dedent("""
        from langgraph.graph import StateGraph, START, END
        from langgraph.types import Command, Send

        def tools(state):
            compiled.ainvoke({})
            return Command(goto=[Send("done"), Send("tools")])

        parent = StateGraph(dict)
        parent.add_node("tools", tools)
        parent.add_node("done", lambda s: s)
        parent.add_edge(START, "tools")
        parent.add_edge("done", END)

        sub = StateGraph(dict)
        sub.add_node("worker", lambda s: s)
        sub.add_edge(START, "worker")
        sub.add_edge("worker", END)
        compiled = sub.compile()
    """))
    edges = set(extract.from_langgraph(str(f)))
    assert ("START", "tools") in edges
    assert ("tools", "done") in edges
    assert ("done", "END") in edges
    assert ("tools", "worker") in edges
    assert ("START[sub]", "worker") in edges
    assert ("worker", "END[sub]") in edges
    assert ("START", "worker") not in edges
    assert ("worker", "END") not in edges


def test_langgraph_self_invoke_does_not_demote_the_parent(tmp_path):
    f = tmp_path / "g.py"
    f.write_text(textwrap.dedent("""
        from langgraph.graph import StateGraph, START, END

        def loop(state):
            app.ainvoke({})
            return state

        helper = StateGraph(dict)
        helper.add_node("h", lambda s: s)
        helper.add_edge(START, "h")
        helper.add_edge("h", END)

        g = StateGraph(dict)
        g.add_node("loop", loop)
        g.add_edge(START, "loop")
        g.add_edge("loop", END)
        app = g.compile()
    """))
    edges = set(extract.from_langgraph(str(f)))
    assert ("START", "loop") in edges
    assert ("loop", "END") in edges
    assert ("START[helper]", "h") in edges
    assert ("h", "END[helper]") in edges
    assert ("loop", "loop") not in edges



def test_terraform_same_name_resources_do_not_collapse(tmp_path):
    (tmp_path / "main.tf").write_text(
        'resource "aws_vpc" "this" {\n  cidr_block = "10.0.0.0/16"\n}\n'
        'resource "aws_internet_gateway" "this" {\n  vpc_id = aws_vpc.this.id\n}\n'
        'resource "aws_subnet" "public" {\n  vpc_id = aws_vpc.this.id\n}\n'
        'resource "aws_route_table" "public" {\n  vpc_id = aws_vpc.this.id\n'
        '  gateway_id = aws_internet_gateway.this.id\n}\n'
        'resource "aws_instance" "web" {\n  subnet_id = aws_subnet.public.id\n}\n',
        encoding="utf-8",
    )
    edges = set(extract.from_terraform(str(tmp_path)))
    assert ("aws_internet_gateway.this", "aws_vpc.this") in edges
    assert ("aws_route_table.public", "aws_internet_gateway.this") in edges
    assert ("aws_subnet.public", "aws_vpc.this") in edges
    # "web" is the only resource with that name, so it stays short.
    assert ("web", "aws_subnet.public") in edges
    assert not any(node in {"this", "public"} for edge in edges for node in edge)


def test_from_directory_exclude_and_include(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  web:\n    depends_on: [db]\n  db:\n    image: postgres\n",
        encoding="utf-8",
    )
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(
        "on: push\njobs:\n  build:\n    runs-on: x\n    steps: []\n"
        "  deploy:\n    needs: build\n    runs-on: x\n    steps: []\n",
        encoding="utf-8",
    )
    _edges, sources = extract.from_directory(str(tmp_path))
    assert "github-actions" in sources
    assert "docker-compose" in sources

    edges, sources = extract.from_directory(str(tmp_path), exclude={"github-actions"})
    assert sources == {"docker-compose": 1}
    assert edges == [("web", "db")]

    _edges, sources = extract.from_directory(str(tmp_path), include={"github-actions"})
    assert set(sources) == {"github-actions"}

    # A string is one label. exclude wins when a label is in both sets.
    _edges, sources = extract.from_directory(str(tmp_path), include="github-actions")
    assert set(sources) == {"github-actions"}
    _edges, sources = extract.from_directory(
        str(tmp_path),
        include=["docker-compose", "github-actions"],
        exclude="docker-compose",
    )
    assert set(sources) == {"github-actions"}
