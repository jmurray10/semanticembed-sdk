"""CrewAI content-creation pipeline — parsable example.

Try::

    import semanticembed as se
    edges = se.extract.from_crewai("examples/crewai_content_pipeline.py")

Topology (extracted by from_crewai):

    researcher  -> research_task
    writer      -> draft_task
    editor      -> edit_task
    seo         -> seo_task

    research_task -> draft_task     (Task context dependency)
    draft_task    -> edit_task
    edit_task     -> seo_task

    manager -> researcher           (Crew(manager_agent=...) fan-out)
    manager -> writer
    manager -> editor
    manager -> seo
"""

from crewai import Agent, Task, Crew


researcher = Agent(role="Senior Researcher", goal="Find facts and citations", backstory="...")
writer     = Agent(role="Writer",            goal="Draft an article",         backstory="...")
editor     = Agent(role="Editor",            goal="Polish and tighten",       backstory="...")
seo        = Agent(role="SEO Specialist",    goal="Optimize for search",      backstory="...")
manager    = Agent(role="Content Manager",   goal="Coordinate the team",      backstory="...")


research_task = Task(
    description="Research the topic and produce an outline with sources.",
    agent=researcher,
)

draft_task = Task(
    description="Write a 1500-word draft from the research outline.",
    agent=writer,
    context=[research_task],
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
    agents=[researcher, writer, editor, seo],
    tasks=[research_task, draft_task, edit_task, seo_task],
    manager_agent=manager,
)
