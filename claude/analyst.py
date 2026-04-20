import anthropic
import json
import re
from pathlib import Path
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL


def load_system_context():
    """Load all 4 MD files as the system prompt."""
    md_dir = Path(__file__).parent.parent / "md_files"
    files = [
        "qoyod-manager-os.md",
        "qoyod-paid-media-agent.md",
        "qoyod-hubspot-cro-agent.md",
        "qoyod-task-flow.md",
    ]
    context = ""
    for f in files:
        path = md_dir / f
        if path.exists():
            context += f"\n\n---\n\n{path.read_text()}"
    return context.strip()


def analyze(data: dict) -> dict:
    """
    Send performance data to Claude. Returns structured decision JSON.
    data should contain: google_ads, meta, hubspot, date
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system_prompt = load_system_context()

    user_message = f"""
Daily performance check — {data.get('date')}

Run the full daily decision framework against this data.
Output your response in the exact format specified in your operating system:
1. Summary
2. Slack Draft
3. Asana Task Draft (if needed)
4. JSON

Performance data:
{json.dumps(data, indent=2)}
"""

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = message.content[0].text

    # Extract JSON block from Claude's response
    json_block = extract_json(raw)

    return {
        "raw_response": raw,
        "decision": json_block,
    }


def extract_json(text: str) -> dict:
    """Pull the JSON object out of Claude's response."""
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Fallback: find first { ... } block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}
