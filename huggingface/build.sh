#!/usr/bin/env bash
# Refresh huggingface/examples/ from the SDK repo's canonical examples.
# Run from the SDK repo root: bash huggingface/build.sh
set -euo pipefail

cd "$(dirname "$0")/.."

cp examples/langgraph_research_agent.py huggingface/examples/langgraph_research.py
cp examples/crewai_content_pipeline.py  huggingface/examples/crewai_content.py
cp examples/autogen_codereview.py       huggingface/examples/autogen_codereview.py
cp examples/google_online_boutique.json huggingface/examples/boutique.json

echo "Refreshed huggingface/examples/ from canonical fixtures."
