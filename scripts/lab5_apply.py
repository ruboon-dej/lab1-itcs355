#!/usr/bin/env python3
"""Apply the Lab 5 edits to existing repo files. Idempotent: safe to run twice.

    python scripts/lab5_apply.py

Every patch asserts that the text it expects is really there. If a patch cannot find its
anchor it says so and changes NOTHING in that file, so a repo that differs from the one this
was written against is never silently half-edited.
"""
from __future__ import annotations

import py_compile
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
failures: list[str] = []


def patch(rel: str, label: str, fn) -> None:
    path = ROOT / rel
    if not path.exists():
        failures.append(f"{rel}: file not found")
        print(f"MISSING  {label}  ({rel})")
        return
    old = path.read_text()
    try:
        new = fn(old)
    except AssertionError as exc:
        failures.append(f"{rel}: {exc}")
        print(f"FAILED   {label}: {exc}")
        return
    if new == old:
        print(f"already  {label}")
        return
    path.write_text(new)
    print(f"patched  {label}")


def sub_once(text: str, old: str, new: str, what: str) -> str:
    assert old in text, f"anchor not found for {what}"
    return text.replace(old, new, 1)


# --- 1. prices: the table was wrong (DS3_v2 cheaper than DS2_v2). Retail API, 2026-10-16.
def costs(s: str) -> str:
    if "6.8306" in s:
        return s
    s = sub_once(s, '"Standard_DS2_v2": 11.1955,', '"Standard_DS2_v2": 6.8306,', "DS2_v2 rate")
    s = sub_once(s, '"Standard_DS3_v2": 8.1,', '"Standard_DS3_v2": 13.628,', "DS3_v2 rate")
    s = sub_once(s, "# Standard_DS2_v2 Japan East: $0.336/hour.",
                 "# Linux pay-as-you-go, Japan East, Azure Retail Prices API 2026-10-16:\n"
                 "        # DS2_v2 $0.205/h, DS3_v2 $0.409/h (earlier values here were wrong).",
                 "price comment")
    s = sub_once(s, "SPOT_FACTOR = 0.30", "SPOT_FACTOR = 0.20", "spot factor")
    s = s.replace("roughly 30% of on-demand", "roughly 20% of on-demand")
    return s


# --- 2. Dockerfile: the pipeline's validate step runs tests/ inside the image.
def dockerfile(s: str) -> str:
    line = "COPY --chown=runner:runner tests/ ./tests/"
    if line in s:
        return s
    anchor = "COPY --chown=runner:runner scripts/ ./scripts/"
    return sub_once(s, anchor, anchor + "\n" + line, "scripts COPY line")


# --- 3. Makefile: teardown must target lab 5; add ops image and submit targets.
def makefile(s: str) -> str:
    if "scripts/teardown_lab5.py" not in s:
        pattern = re.compile(
            r"teardown:[^\n]*\n\tpython -c \"from src import config; from cloudlayer.factory import "
            r"get_adapter; \\\n\tcfg=config.load\(\); print\(get_adapter\(cfg\)\.teardown\(cfg\.tags\(3\)\)\)\"")
        assert pattern.search(s), "teardown recipe not in the expected form"
        s = pattern.sub("teardown: ## Delete everything tagged lab=5 and what tags cannot reach\n"
                        "\tpython scripts/teardown_lab5.py", s, count=1)
    if "image-ops-push" not in s:
        s = s.rstrip("\n") + (
            "\n\n# --- Lab 5 additions (scripts/lab5_apply.py) ---\n"
            ".PHONY: image-ops image-ops-push pipeline-submit\n"
            "image-ops: ## Build the ops image (gate, register) for linux/amd64\n"
            "\tdocker buildx build --platform $(PLATFORM) -f Dockerfile.ops -t itcs355-ops:$(TAG) --load .\n\n"
            "image-ops-push: image-ops ## Push the ops image and record its digest in .image_ops_uri\n"
            "\t@python -c \"from cloudlayer.factory import get_adapter; from src import config; \\\n"
            "\turi = get_adapter(config.load()).push_image('itcs355-ops:$(TAG)'); \\\n"
            "\topen('.image_ops_uri', 'w').write(uri); \\\n"
            "\tprint(uri)\"\n\n"
            "pipeline-submit: ## Submit the Lab 5 pipeline, e.g. make pipeline-submit ARGS=\"--wait\"\n"
            "\tpython scripts/submit_pipeline.py $(ARGS)\n")
    return s


# --- 4. AzureAdapter.generate: delegate to cloudlayer/azure_llm.py
def azure_adapter(s: str) -> str:
    if "def generate(" in s:
        return s
    anchor = "    def teardown("
    method = ('    def generate(self, prompt: str, params: dict[str, Any]) -> dict[str, Any]:\n'
              '        """Azure OpenAI chat completion; tokens come from the provider usage block."""\n'
              '        from cloudlayer.azure_llm import generate as _generate\n\n'
              '        return _generate(self.cfg, prompt, params)\n\n')
    return sub_once(s, anchor, method + anchor, "AzureAdapter.teardown")


# --- 5. llm_eval: live generation with system prompt, temperature, token cap, cached tokens.
def llm_eval(s: str) -> str:
    if "--system-prompt" in s:
        return s
    s = sub_once(s, '            "output_tokens": got.get("output_tokens", 0),\n',
                 '            "output_tokens": got.get("output_tokens", 0),\n'
                 '            "cached_input_tokens": got.get("cached_input_tokens", 0),\n', "score tokens")
    s = sub_once(s, '    out_tok = sum(r.get("output_tokens", 0) for r in results)\n',
                 '    out_tok = sum(r.get("output_tokens", 0) for r in results)\n'
                 '    cached_tok = sum(r.get("cached_input_tokens", 0) for r in results)\n', "summarise sums")
    s = sub_once(s, '        output_tokens=round(out_tok / total) if total else 0,\n    )',
                 '        output_tokens=round(out_tok / total) if total else 0,\n'
                 '        cached_input_tokens=min(round(cached_tok / total), round(in_tok / total)) if total else 0,\n    )',
                 "summarise usage")
    s = sub_once(s, '        "avg_output_tokens": avg.output_tokens,\n',
                 '        "avg_output_tokens": avg.output_tokens,\n'
                 '        "avg_cached_input_tokens": avg.cached_input_tokens,\n', "report fields")
    s = sub_once(s, "    args = ap.parse_args()\n",
                 '    ap.add_argument("--max-output-tokens", type=int, default=200)\n'
                 '    ap.add_argument("--temperature", type=float, default=0.0)\n'
                 '    ap.add_argument("--system-prompt", type=Path, default=None,\n'
                 '                    help="system prompt file sent with every live call")\n'
                 '    ap.add_argument("--record", type=Path, default=None,\n'
                 '                    help="with --live: save the raw responses as a replayable fixture")\n'
                 "    args = ap.parse_args()\n", "argparse")
    s = sub_once(s, "        responses = generate_live(golden)\n",
                 "        responses = generate_live(golden, args)\n"
                 "        if args.record:\n"
                 "            args.record.parent.mkdir(parents=True, exist_ok=True)\n"
                 '            args.record.write_text("".join(json.dumps(r) + "\\n" for r in responses))\n',
                 "generate_live call")
    start = s.index("def generate_live(golden: list[dict]) -> list[dict]:")
    end = s.index('if __name__ == "__main__":')
    new_fn = '''def generate_live(golden: list[dict], args=None) -> list[dict]:
    """Route each prompt through the adapter's `generate`.

    input_tokens, output_tokens, cached_input_tokens and latency_ms are copied from the
    provider's own usage block. They are never estimated from word counts.
    """
    from src import config
    from cloudlayer.factory import get_adapter

    adapter = get_adapter(config.load())
    params = {
        "max_output_tokens": getattr(args, "max_output_tokens", 200),
        "temperature": getattr(args, "temperature", 0.0),
    }
    system_path = getattr(args, "system_prompt", None)
    if system_path:
        params["system"] = Path(system_path).read_text()
    rows = []
    for case in golden:
        result = adapter.generate(case["prompt"], dict(params))
        rows.append({"id": case["id"], **result})
    return rows


'''
    return s[:start] + new_fn + s[end:]


# --- 6. token price for the model actually called (verify the figure, then record the date)
def llmcost(s: str) -> str:
    if '"gpt-4.1-mini"' in s:
        return s
    anchor = '    "azure": {\n        "small": (9.5, 38.0),'
    new = ('    "azure": {\n'
           '        # gpt-4.1-mini Global Standard: $0.40 in / $1.60 out per 1M tokens x 33.32 THB/USD.\n'
           '        # VERIFY on the Azure pricing page and write the date you checked in your cost report.\n'
           '        "gpt-4.1-mini": (13.33, 53.31),\n'
           '        "small": (9.5, 38.0),')
    return sub_once(s, anchor, new, "azure token table")


def gitignore(s: str) -> str:
    return s if ".image_ops_uri" in s else s.rstrip("\n") + "\n.image_ops_uri\n"


patch("src/costs.py", "corrected VM prices (DS2_v2, DS3_v2, spot factor)", costs)
patch("Dockerfile", "training image now includes tests/", dockerfile)
patch("Makefile", "teardown targets lab 5; ops image and submit targets", makefile)
patch("cloudlayer/azure.py", "AzureAdapter.generate", azure_adapter)
patch("scripts/llm_eval.py", "llm_eval live mode, system prompt, cached tokens", llm_eval)
patch("src/llmcost.py", "gpt-4.1-mini token rates (verify)", llmcost)
if (ROOT / ".gitignore").exists():
    patch(".gitignore", "ignore .image_ops_uri", gitignore)

dockerignore = ROOT / ".dockerignore"
if dockerignore.exists() and re.search(r"^/?tests/?$", dockerignore.read_text(), re.M):
    failures.append(".dockerignore excludes tests/: remove that line or validate will fail")
    print("WARNING  .dockerignore excludes tests/")

for rel in ("src/costs.py", "cloudlayer/azure.py", "cloudlayer/pipelines.py", "cloudlayer/azure_ops.py",
            "cloudlayer/azure_llm.py", "cloudlayer/aws.py", "cloudlayer/registry.py",
            "scripts/llm_eval.py", "scripts/evaluation_gate.py", "scripts/register_model.py",
            "scripts/submit_pipeline.py", "scripts/teardown_lab5.py", "scripts/schedule_pipeline.py"):
    try:
        py_compile.compile(str(ROOT / rel), doraise=True)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"{rel}: does not compile ({exc})")

print()
if failures:
    print("PROBLEMS:")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all patches applied and every touched file compiles")
