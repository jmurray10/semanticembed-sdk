"""Every question sent to Jev, in one place.

Jev answers yes/no judgments (a "Noul": the probability that a statement is
true). The scripts turn the probabilities into decisions with the
thresholds below. Wording, context and thresholds were fixed before the
held-out measurements in docs/jev.md; change them only together with a new
measurement.
"""

from __future__ import annotations

# Noul thresholds. Above YES reads as yes, below NO as no, between is unsettled.
YES = 0.7
NO = 0.3

# --------------------------------------------------------------------------
# Leak guard: does an added hunk explain how the hosted service works inside?
# --------------------------------------------------------------------------

# Public facts only. It names the kind of private material, never the material.
LEAK_CONTEXT = (
    "SemanticEmbed computes six numbers per graph node (depth, independence, hierarchy, "
    "throughput, criticality, fanout) on a hosted server and returns risk flags such as "
    "CONVERGENCE_SINK. This repository is the public client: it parses config files into "
    "edges, sends them to the server, and shows the results. The server's code is not in "
    "this repository."
)

LEAK_QUESTIONS: dict[str, dict] = {
    "threshold": {
        "type": "noul",
        "instructions": "Does `added_lines` state a numeric cutoff that decides when a risk flag fires?",
    },
    "procedure": {
        "type": "noul",
        "instructions": "Does `added_lines` describe the processing steps used to compute an embedding value?",
    },
    "preprocess": {
        "type": "noul",
        "instructions": (
            "Does `added_lines` describe how the hosted scorer changes the input graph before "
            "scoring, such as removing edges or cycles?"
        ),
    },
    "tiebreak": {
        "type": "noul",
        "instructions": "Does `added_lines` describe how ties between nodes are broken when a value is computed?",
    },
}

# Subject check, asked alongside the four above. "How ties are broken" is
# literally true of client code that sorts results for display, so a hunk
# only counts as a leak when it is about what the hosted server does, or is
# client code that reproduces it. Code that consumes returned values is not.
SCOPE_QUESTION: dict[str, dict] = {
    "about_scoring": {
        "type": "noul",
        "instructions": (
            "Does `added_lines` describe what the hosted server does, or add code that does "
            "the server's work in this repository?"
        ),
        "criteria": {
            "true": (
                "Says what the server does internally to produce the six numbers or decide risk "
                "flags, or adds code in this repository that computes one of the six numbers or "
                "decides a risk flag."
            ),
            "false": (
                "Describes what this client or a user's own code does: parsing files into edges, "
                "sending requests, explaining what a number means, or ranking, filtering, "
                "printing, or alerting on numbers the server returned."
            ),
        },
    },
}

LEAK_REASONS = {
    "threshold": "states a cutoff that decides when a risk flag fires",
    "procedure": "describes processing steps used to compute an embedding value",
    "preprocess": "describes how the hosted scorer changes the input graph",
    "tiebreak": "describes how ties between nodes are broken",
}

# --------------------------------------------------------------------------
# Edge audit: is an extracted edge real, or a parsing artifact?
# --------------------------------------------------------------------------

EDGE_QUESTIONS: dict[str, dict] = {
    "target_is_component": {
        "type": "noul",
        "instructions": "Is `edge.target` the name of a software component?",
        "criteria": {
            "true": (
                "`edge.target` names a package, module, service, job, agent, task, workflow node, "
                "or infrastructure resource that appears in `snippet`."
            ),
            "false": (
                "`edge.target` is only a fragment of the text, such as a URL scheme, a "
                "version-control prefix, a file name, or a command-line option."
            ),
        },
    },
    "target_is_group": {
        "type": "noul",
        "instructions": (
            "Is `edge.target` the name of a dependency group defined in `snippet`, meaning a named "
            "list of other dependencies?"
        ),
    },
    "claim_shown": {
        "type": "noul",
        "instructions": "Does `snippet` show that `claim` is true?",
    },
}

# What one edge from each parser asserts, as a sentence about the two names.
EDGE_MEANING = {
    "requirements": "The Python project `{s}` installs the package named `{t}`.",
    "pyproject": "The Python project `{s}` depends on the package named `{t}`.",
    "package-json": "The npm package `{s}` depends on the package named `{t}`.",
    "docker-compose": "The service `{s}` depends on or connects to the service `{t}`.",
    "kubernetes": "The Kubernetes object `{s}` routes traffic to or calls `{t}`.",
    "terraform": "The Terraform resource `{s}` references the resource `{t}`.",
    "cloudformation": "The CloudFormation resource `{s}` references the resource `{t}`.",
    "pulumi": "The Pulumi resource `{s}` references the resource `{t}`.",
    "aws-cdk": "The CDK construct `{s}` references the construct `{t}`.",
    "github-actions": "In this workflow, `{t}` runs after `{s}` (or `{t}` is a job of the workflow `{s}`).",
    "langgraph": "In this LangGraph graph, control can pass from node `{s}` to node `{t}`.",
    "crewai": "In this CrewAI crew, agent `{s}` performs task `{t}`, or task `{s}` feeds task `{t}`.",
    "autogen": "In this AutoGen app, agent `{s}` sends messages to agent `{t}`.",
    "otel-traces": "In these traces, service `{s}` calls service `{t}`.",
}

# Everything the leak guard asks about one hunk, in one request.
LEAK_ALL_QUESTIONS: dict[str, dict] = {**LEAK_QUESTIONS, **SCOPE_QUESTION}
