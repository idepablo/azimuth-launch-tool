"""Ask AZIMUTH: questions in plain language, answered from the app's data."""
import html
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

import ask
import data
import ui

QUESTIONS_PER_SESSION = 20
AVATAR = str(Path(__file__).parent.parent / "assets" / "az_avatar.png")

# chat look: questions as bubbles on the right, AZIMUTH on the left with its own icon,
# and a large, clearly outlined question box
st.markdown(f"""
<style>
.az-user {{ display: flex; justify-content: flex-end; margin: 22px 0 8px; }}
.az-bubble {{ background: #263040; color: #E6EDF3; padding: 12px 18px; max-width: 75%;
             border-radius: 18px 18px 4px 18px; line-height: 1.55; white-space: pre-wrap; }}
[data-testid="stChatInput"] {{ border: 2px solid {ui.AMBER} !important; border-radius: 16px !important;
                              background: #151B23 !important; }}
[data-testid="stChatInput"] > div {{ border: none !important; background: transparent !important; }}
[data-testid="stChatInput"] textarea {{ min-height: 56px !important; font-size: 1.05rem !important; }}
</style>
""", unsafe_allow_html=True)
EXAMPLES = [
    "Which providers launched the most in 2025?",
    "How many failures has Electron had, and when?",
    "Most reliable active vehicles with 50+ flights?",
    "¿Cuántos lanzamientos hizo China cada año desde 2015?",
]
OUT_OF_SCOPE = ("Sorry, that is outside what AZIMUTH can answer. I can only answer questions "
                "about the launches, providers and vehicles in this app: counts, success rates, "
                "reliability, cadence and market share.")

ui.header("Ask AZIMUTH",
          "Questions in plain language, in English or Spanish, answered from the same data as the "
          "rest of the app. You can ask follow-ups, such as \"explain that\" or \"and in 2024?\".")

exam = data.ask_eval()
if exam:
    st.caption(
        f"In the latest test ({exam['run_at'][:10]}), it answered "
        f"{exam['in_scope_passed']} of {exam['in_scope_questions']} answerable questions "
        f"correctly and declined {exam['out_of_scope_declined']} of "
        f"{exam['out_of_scope_questions']} out-of-scope ones. The questions are in "
        "[analysis/ask_eval.py](https://github.com/idepablo/azimuth-launch-tool/blob/main/"
        "analysis/ask_eval.py).")

if not ask.api_key():
    st.info("Ask AZIMUTH is not switched on yet. The rest of the app works as usual.")
    ui.footer()
    st.stop()

as_of = data.manifest()["data_as_of"]
frames = ask.tables()
history = st.session_state.setdefault("ask_history", [])


def formspree_id():
    """The form's code; accepts the full https://formspree.io/f/... address too."""
    try:
        value = st.secrets.get("FORMSPREE_FORM_ID")
    except Exception:
        return None
    return value.strip().rstrip("/").split("/")[-1] if value else None


def send_report(entry, reason):
    """Email the question, query, answer and the user's reason, via Formspree."""
    payload = {
        "_subject": "AZIMUTH: Ask AZIMUTH report",
        "question": entry["question"],
        "in_scope": entry["result"]["in_scope"],
        "interpretation": entry["result"].get("note") or "",
        "sql": entry["result"].get("sql") or "",
        "answer": entry["result"].get("answer") or OUT_OF_SCOPE,
        "error": entry["result"].get("error") or "",
        "reason": reason,
        "data_as_of": as_of,
        "sent_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    request = urllib.request.Request(
        f"https://formspree.io/f/{formspree_id()}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 # the default Python identifier is often refused by bot protection
                 "User-Agent": "Mozilla/5.0 (AZIMUTH app; +https://azimuth-launch.streamlit.app)"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as error:
        # visible in the app's logs, so a failed report can be diagnosed
        print(f"Formspree report failed: HTTP {error.code}: {error.read()[:300]!r}")
        raise


def show(entry, index):
    st.markdown(f'<div class="az-user"><div class="az-bubble">{html.escape(entry["question"])}'
                '</div></div>', unsafe_allow_html=True)
    result = entry["result"]
    with st.chat_message("assistant", avatar=AVATAR):
        if not result["in_scope"]:
            st.write(OUT_OF_SCOPE)
        elif result["error"]:
            st.write("I couldn't get a working query for that one. Try rephrasing it, or report it "
                     "below so it can be fixed.")
        else:
            st.write(result["answer"])
            rows = result["rows"]
            # the answer stands on its own; the detail is there for anyone who wants it
            if result.get("note") or (rows is not None and len(rows) > 1):
                with st.expander("Details"):
                    if result.get("note"):
                        st.caption(f"How the question was read: {result['note']}")
                    if rows is not None and len(rows) > 1:
                        st.dataframe(rows, hide_index=True, width="stretch")

        if formspree_id():
            if entry.get("reported"):
                st.caption("Thanks, your report was sent.")
            else:
                label = ("Think this should be answerable? Tell me why" if not result["in_scope"]
                         else "Answer looks wrong? Report it")
                with st.expander(label):
                    with st.form(f"report_{index}", border=False):
                        reason = st.text_area("What's wrong, or why should this be answerable?",
                                              max_chars=500)
                        if st.form_submit_button("Send report"):
                            try:
                                entry["reported"] = send_report(entry, reason.strip())
                                st.rerun()
                            except Exception as error:
                                print(f"Report error: {error!r}")
                                st.error("The report could not be sent. Please try again later.")


# the conversation sits in a centred column, like a chat
_, chat, _ = st.columns([1, 6, 1])
with chat:
    for i, entry in enumerate(history):
        show(entry, i)

    # ---- new question -------------------------------------------------------------------
    if len(history) >= QUESTIONS_PER_SESSION:
        st.info(f"That's the limit of {QUESTIONS_PER_SESSION} questions per visit. Thanks for "
                "trying Ask AZIMUTH.")
    else:
        question = None
        st.markdown("**Ask a question**" if not history else "")
        # inside a container, the box sits right under the conversation instead of
        # at the bottom of the window
        with st.container():
            typed = st.chat_input("Ask about launches, providers, vehicles or reliability...",
                                  max_chars=300)
        if not history:
            picked = st.pills("Or try one of these:", EXAMPLES, selection_mode="single",
                              key="ask_example")
            question = picked
        question = typed or question
        if question:
            with st.spinner("Looking it up..."):
                try:
                    # the last few exchanges, so follow-up questions make sense
                    context = [(h["question"], h["result"].get("answer") or "")
                               for h in history[-3:] if h["result"].get("in_scope")]
                    result = ask.ask(question, frames, as_of, context)
                except Exception:
                    result = {"in_scope": True, "answer": None, "sql": None, "rows": None,
                              "note": None, "error": "service"}
            history.append({"question": question, "result": result})
            st.session_state.pop("ask_example", None)
            st.rerun()

st.caption("Answers are generated by an AI model from the data shown in this app and can be wrong. "
           "Questions and reports are not stored by the app; a report sends the question, answer "
           "and your note by email.")
ui.footer()
