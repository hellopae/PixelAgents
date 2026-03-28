#!/usr/bin/env python3
"""
Pixel Agents — Claude Code Hook
─────────────────────────────────
วางไว้ใน .claude/settings.json ของโปรเจ็คที่ต้องการ monitor:

{
  "hooks": {
    "PreToolUse":  [{"hooks": [{"type": "command", "command": "python3 /FULL/PATH/TO/hook.py"}]}],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "python3 /FULL/PATH/TO/hook.py"}]}],
    "Stop":        [{"hooks": [{"type": "command", "command": "python3 /FULL/PATH/TO/hook.py"}]}],
    "Notification":[{"hooks": [{"type": "command", "command": "python3 /FULL/PATH/TO/hook.py"}]}]
  }
}

Claude Code ส่ง JSON มาทาง stdin — script นี้อ่านแล้ว POST ไป SSE server
ถ้า server ไม่ทำงาน script จะ silent fail (ไม่ block Claude)
"""

import sys, json, os, urllib.request, urllib.error

SSE_URL  = "http://localhost:3001/event"
TIMEOUT  = 1   # วินาที — ถ้า server ไม่ตอบก็ข้ามไป

# ── tool → agent state ───────────────────────────────────────────────────────

TOOL_STATE = {
    # กำลัง code / เขียน / รัน
    "Bash":          "CODING",
    "Write":         "CODING",
    "Edit":          "CODING",
    "MultiEdit":     "CODING",
    "NotebookEdit":  "CODING",
    # กำลังค้นหา / อ่าน
    "Read":          "SEARCHING",
    "Grep":          "SEARCHING",
    "Glob":          "SEARCHING",
    "LS":            "SEARCHING",
    "WebFetch":      "SEARCHING",
    "WebSearch":     "SEARCHING",
    "TodoRead":      "SEARCHING",
    # agent tools
    "Agent":         "CODING",
    "Task":          "CODING",
}

# ── task label ───────────────────────────────────────────────────────────────

def task_label(hook_name: str, tool: str, inp: dict, msg: str) -> str:
    if hook_name == "Stop":
        return "Waiting for your input"
    if hook_name == "Notification":
        return (msg or "Notification")[:65]

    basename = lambda p: os.path.basename(p) if p else ""

    label_map = {
        "Bash":       lambda i: f"$ {i.get('command','')[:60]}",
        "Write":      lambda i: f"Writing  {basename(i.get('file_path',''))}",
        "Edit":       lambda i: f"Editing  {basename(i.get('file_path',''))}",
        "MultiEdit":  lambda i: f"Editing  {basename(i.get('file_path',''))}",
        "Read":       lambda i: f"Reading  {basename(i.get('file_path',''))}",
        "Grep":       lambda i: f"Grep: {i.get('pattern','')[:45]}",
        "Glob":       lambda i: f"Glob: {i.get('pattern','')[:45]}",
        "LS":         lambda i: f"ls {i.get('path','')[:50]}",
        "WebFetch":   lambda i: f"Fetch: {i.get('url','')[:55]}",
        "WebSearch":  lambda i: f"Search: {i.get('query','')[:55]}",
        "Agent":      lambda i: f"Spawning agent: {str(i.get('prompt',''))[:45]}",
        "Task":       lambda i: f"Task: {str(i.get('description',''))[:50]}",
    }
    fn = label_map.get(tool)
    if fn:
        try:
            return fn(inp)
        except Exception:
            pass
    return f"Tool: {tool}" if tool else "Working..."

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        raw  = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)

    hook_name = data.get("hook_event_name", "")
    tool      = data.get("tool_name", "")
    inp       = data.get("tool_input", {}) or {}
    session   = data.get("session_id", "unknown")
    notif_msg = data.get("message", "")

    # derive state
    if hook_name in ("Stop", "Notification"):
        state = "WAITING"
    elif hook_name == "PostToolUse":
        # briefly show CODING after tool finishes (agent processing result)
        state = TOOL_STATE.get(tool, "CODING")
    else:
        state = TOOL_STATE.get(tool, "CODING")

    project = os.path.basename(os.getcwd())

    event = {
        "session_id": session,
        "hook":       hook_name,
        "tool_name":  tool,
        "state":      state,
        "task":       task_label(hook_name, tool, inp, notif_msg),
        "project":    project,
    }

    try:
        body = json.dumps(event).encode()
        req  = urllib.request.Request(
            SSE_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=TIMEOUT)
    except Exception:
        pass  # never block Claude Code

    sys.exit(0)


if __name__ == "__main__":
    main()
