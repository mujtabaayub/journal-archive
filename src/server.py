"""
Phase 4b: Browser-based chat interface.

Usage (from project root):
    python -m src.server
Then open http://localhost:5000 in your browser.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import anthropic
from flask import Flask, jsonify, request, Response
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "journal.db"

SYSTEM = """You are a thoughtful assistant with access to excerpts from the user's personal journal.
The entries span many years and cover a wide range of experiences, emotions, and reflections.
Answer questions grounded in the entries provided. If the entries don't contain enough to answer well, say so.
Be direct and personal — you're helping someone understand their own life and writing."""

app = Flask(__name__)
app.config["PROPAGATE_EXCEPTIONS"] = True
client = anthropic.Anthropic()
conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
sessions: dict[str, list[dict]] = {}

print("Loading embedding model...", flush=True)
_model = SentenceTransformer("all-MiniLM-L6-v2")

print("Loading embeddings index...", flush=True)
_rows = conn.execute(
    "SELECT e.draft_id, e.vec, d.gmail_date, d.body_text, t.mood, t.entry_type, t.summary "
    "FROM embeddings e "
    "JOIN drafts d ON e.draft_id = d.draft_id "
    "JOIN tags t ON e.draft_id = t.draft_id"
).fetchall()
_ids      = [r[0] for r in _rows]
_matrix   = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in _rows])
_meta     = [{"date": r[2][:10] if r[2] else "", "body": (r[3] or "")[:1500],
              "mood": r[4] or "", "type": (r[5] or "").replace("_"," "), "summary": r[6] or ""}
             for r in _rows]
print(f"Index ready — {len(_ids)} entries.", flush=True)


def search(query: str, limit: int = 15) -> list[dict]:
    q_vec = _model.encode(query, normalize_embeddings=True)
    scores = _matrix @ q_vec
    top_idx = np.argsort(scores)[::-1][:limit]
    return [_meta[i] for i in top_idx]


def format_entries(entries: list[dict]) -> str:
    parts = []
    for e in entries:
        parts.append(
            f"[{e['date']} · {e['mood']} · {e['type']}]\n"
            f"Summary: {e['summary']}\n"
            f"{e['body']}"
        )
    return "\n\n---\n\n".join(parts)


@app.route("/")
def index() -> Response:
    return Response(HTML, mimetype="text/html")


@app.route("/chat", methods=["POST"])
def chat() -> Response:
    print(">>> /chat called", flush=True)
    try:
        data = request.json
        session_id = data.get("session", "default")
        question = data.get("question", "").strip()
        print(f">>> question: {question}", flush=True)

        if not question:
            return jsonify({"error": "Empty question"}), 400

        history = sessions.setdefault(session_id, [])

        entries = search(question)
        print(f">>> {len(entries)} entries found", flush=True)
        context = format_entries(entries) if entries else "No relevant entries found."

        history.append({
            "role": "user",
            "content": f"Journal entries relevant to my question:\n\n{context}\n\n---\n\nMy question: {question}",
        })

        print(">>> calling Claude...", flush=True)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM,
            messages=history,
        )
        answer = resp.content[0].text
        history.append({"role": "assistant", "content": answer})
        print(">>> done", flush=True)
        return jsonify({"answer": answer, "sources": len(entries)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/reset", methods=["POST"])
def reset() -> Response:
    session_id = request.json.get("session", "default")
    sessions.pop(session_id, None)
    return jsonify({"ok": True})


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Journal Chat</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:#f2f2f0;color:#1a1a1a;display:flex;flex-direction:column;
  height:100vh;font-size:15px}
header{background:#fff;border-bottom:1px solid #e0e0dc;padding:14px 24px;
  display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
header h1{font-size:1.05em;font-weight:700}
header span{font-size:0.78em;color:#aaa}
#new-btn{font-size:0.78em;padding:5px 12px;border:1px solid #ddd;border-radius:6px;
  background:#fafaf8;cursor:pointer;color:#666}
#new-btn:hover{background:#eee}
#messages{flex:1;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:14px}
.msg{max-width:720px;line-height:1.7}
.msg.user{align-self:flex-end;background:#1a5a8a;color:#fff;
  padding:10px 16px;border-radius:14px 14px 3px 14px;font-size:0.9em}
.msg.assistant{align-self:flex-start;background:#fff;
  padding:14px 18px;border-radius:3px 14px 14px 14px;
  box-shadow:0 1px 3px rgba(0,0,0,.07);font-size:0.9em;white-space:pre-wrap}
.msg.assistant .src{font-size:0.72em;color:#bbb;margin-top:8px}
.typing{align-self:flex-start;background:#fff;padding:12px 16px;
  border-radius:3px 14px 14px 14px;box-shadow:0 1px 3px rgba(0,0,0,.07);
  color:#aaa;font-size:0.85em;font-style:italic}
#bottom{background:#fff;border-top:1px solid #e0e0dc;padding:16px 24px;flex-shrink:0}
#form{display:flex;gap:10px;max-width:760px;margin:0 auto}
#input{flex:1;padding:10px 14px;border:1px solid #ddd;border-radius:8px;
  font-size:0.9em;outline:none;resize:none;font-family:inherit;max-height:120px}
#input:focus{border-color:#6aaed6}
#send{padding:10px 20px;background:#1a5a8a;color:#fff;border:none;
  border-radius:8px;cursor:pointer;font-size:0.9em;font-weight:600;white-space:nowrap}
#send:hover{background:#154d78}
#send:disabled{background:#aaa;cursor:default}
</style>
</head>
<body>
<header>
  <h1>&#128211; Journal Chat</h1>
  <div style="display:flex;align-items:center;gap:12px">
    <span id="src-hint"></span>
    <button id="new-btn" onclick="newChat()">New conversation</button>
  </div>
</header>
<div id="messages">
  <div class="msg assistant">Ask me anything about your journal — themes, periods of time, recurring feelings, specific memories, or patterns across the years.</div>
</div>
<div id="bottom">
  <div id="form">
    <textarea id="input" rows="1" placeholder="Ask something..." oninput="resize(this)" onkeydown="onKey(event)"></textarea>
    <button id="send" onclick="send()">Send</button>
  </div>
</div>
<script>
const SESSION = Math.random().toString(36).slice(2);
const msgs = document.getElementById("messages");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");

function resize(el){el.style.height="auto";el.style.height=Math.min(el.scrollHeight,120)+"px"}
function onKey(e){if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}}

function addMsg(role, text, sources){
  const d=document.createElement("div");
  d.className="msg "+role;
  if(role==="assistant"){
    d.textContent=text;
    if(sources!=null){
      const s=document.createElement("div");
      s.className="src";
      s.textContent=sources+" entries retrieved";
      d.appendChild(s);
    }
  } else {
    d.textContent=text;
  }
  msgs.appendChild(d);
  msgs.scrollTop=msgs.scrollHeight;
  return d;
}

async function send(){
  const q=input.value.trim();
  if(!q||sendBtn.disabled) return;
  input.value=""; resize(input);
  addMsg("user",q);
  sendBtn.disabled=true;
  const typing=document.createElement("div");
  typing.className="typing"; typing.textContent="Thinking...";
  msgs.appendChild(typing); msgs.scrollTop=msgs.scrollHeight;

  try{
    const r=await fetch("/chat",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({session:SESSION,question:q})});
    const data=await r.json();
    typing.remove();
    addMsg("assistant",data.answer,data.sources);
    document.getElementById("src-hint").textContent="";
  } catch(e){
    typing.remove();
    addMsg("assistant","Something went wrong. Please try again.");
  }
  sendBtn.disabled=false;
  input.focus();
}

async function newChat(){
  await fetch("/reset",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({session:SESSION})});
  msgs.innerHTML="";
  addMsg("assistant","Ask me anything about your journal — themes, periods of time, recurring feelings, specific memories, or patterns across the years.");
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    app.run(port=5000, debug=False, use_reloader=False, threaded=False)
