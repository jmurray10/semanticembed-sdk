# Deploying the HF Space

This folder is the source for the SemanticEmbed Hugging Face Space.
**Nothing autonomous here pushes to HF** — deployment requires
interactive auth on your machine.

## One-time prereqs

```bash
pip install -U huggingface_hub gradio
hf auth login            # opens a browser; paste a write token from huggingface.co/settings/tokens
```

A "write" token is required (the default "read" token won't push code).

## Path A — Python (recommended; programmatic, idempotent)

From the SDK repo root, after `hf auth login`:

```python
from huggingface_hub import HfApi

api = HfApi()
api.create_repo(
    repo_id="jmurray10/semanticembed-agent-risk",
    repo_type="space",
    space_sdk="gradio",
    exist_ok=True,
)
api.upload_folder(
    folder_path="huggingface",
    repo_id="jmurray10/semanticembed-agent-risk",
    repo_type="space",
    commit_message="Update Space",
)
```

Re-running the snippet pushes any local changes — same shape as
`git push`.

## Path B — git remote (what HF actually does under the hood)

```bash
# 1. Create the Space in the HF UI: huggingface.co/new-space
#    name: semanticembed-agent-risk
#    SDK: Gradio
#    visibility: Public
#    license: other (matches our LICENSE)

# 2. Clone the empty Space
cd /tmp
git clone https://huggingface.co/spaces/jmurray10/semanticembed-agent-risk hf-space
cd hf-space

# 3. Copy the contents of this folder in
rsync -a --delete --exclude='.git' /path/to/semanticembed-sdk/huggingface/ ./

# 4. Push
git add .
git commit -m "Update Space"
git push
```

You'll be prompted for a password — paste a write token (not your
account password).

## Path C — `gradio deploy` (one-shot, slightly opinionated)

```bash
cd huggingface
gradio deploy
```

This guides you through space creation + first push. Subsequent updates
still need either Path A or B.

## Refreshing examples from the SDK repo

The four files in `huggingface/examples/` are copies of canonical
fixtures in the parent `examples/` directory. To resync before a deploy:

```bash
bash huggingface/build.sh
```

(Just runs the four `cp` commands; idempotent.)

## Verifying the deploy

After the first successful push, the Space builds for ~2 minutes. Check:

- https://huggingface.co/spaces/jmurray10/semanticembed-agent-risk
- The "Logs" tab on that page shows the build + Gradio startup output.
- Hit **Analyze** with each example to confirm the live API path works
  (the cold-start can take 1-2 seconds).

## Updating the Space

Any change to `app.py`, `requirements.txt`, or examples should be
committed to the SDK repo first, then re-pushed via Path A. HF
auto-rebuilds on git push.

## What if you change the public API?

If `semanticembed` ships a breaking change (e.g. a function rename) and
the Space breaks, either:

- Pin a known-good version in `requirements.txt`
  (`semanticembed[extract]==0.7.2`), or
- Update `app.py` to match the new API and re-push.

The `>=` pin in the current `requirements.txt` accepts patch and minor
upgrades, which is fine within the v0.7.x line.
