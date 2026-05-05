"""CrewAI content-creation pipeline — AFTER refactor.

Same as crewai_content.py, but with a `fact_checker` agent + `fact_check_task`
inserted between research and draft. Now the manager fans out to 5 agents
instead of 4, and the draft depends on fact-checked research.

Drift you should see:

  + fact_checker          (added agent)
  + fact_check_task       (added task)
  - research_task -> draft_task   (removed direct hand-off)
  + research_task -> fact_check_task
  + fact_check_task -> draft_task
  + manager -> fact_checker
  + fact_checker -> fact_check_task
"""

from crewai import Agent, Task, Crew


researcher   = Agent(role="Senior Researcher",  goal="Find facts and citations", backstory="...")
fact_checker = Agent(role="Fact Checker",       goal="Verify every claim",       backstory="...")
writer       = Agent(role="Writer",             goal="Draft an article",         backstory="...")
editor       = Agent(role="Editor",             goal="Polish and tighten",       backstory="...")
seo          = Agent(role="SEO Specialist",     goal="Optimize for search",      backstory="...")
manager      = Agent(role="Content Manager",    goal="Coordinate the team",      backstory="...")


research_task = Task(
    description="Research the topic and produce an outline with sources.",
    agent=researcher,
)

fact_check_task = Task(
    description="Verify each claim and citation in the research outline.",
    agent=fact_checker,
    context=[research_task],
)

draft_task = Task(
    description="Write a 1500-word draft from the verified research outline.",
    agent=writer,
    context=[fact_check_task],
)

edit_task = Task(
    description="Tighten prose, fix structure, verify all citations.",
    agent=editor,
    context=[draft_task],
)

seo_task = Task(
    description="Add meta description, headings, and target keywords.",
    agent=seo,
    context=[edit_task],
)


crew = Crew(
    agents=[researcher, fact_checker, writer, editor, seo],
    tasks=[research_task, fact_check_task, draft_task, edit_task, seo_task],
    manager_agent=manager,
)
