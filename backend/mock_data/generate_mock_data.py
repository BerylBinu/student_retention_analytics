"""
Generates realistic, messy, FICTIONAL student messages in four different formats,
the way they would really arrive from campus systems:

    Zendesk support tickets   -> JSON, nested "ticket" object
    Moodle forum posts        -> JSON, HTML message, unix timestamp
    Student emails            -> plain .txt with email headers
    Campus chatbot logs       -> JSON with a list of chat turns

Every format is different on purpose: the pipeline must cope with unstructured data,
and Gemini does the work of pulling out the student ID, date and risk signals.

Run from the backend folder:
    python mock_data/generate_mock_data.py

Output:
    mock_data/samples/historical/   -> upload first (builds up the dashboard)
    mock_data/samples/live_demo/    -> upload one at a time during the demo video

All names, IDs and stories are made up.
"""

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "samples"
MYT = timezone(timedelta(hours=8))  # Malaysia time

STUDENTS = {
    "TP071234": "Aisyah Rahman",
    "TP068812": "Jason Lim Wei Han",
    "TP070455": "Priya Nair",
    "TP072210": "Chen Wei",
    "TP066540": "Nurul Izzah Kamal",
    "TP071877": "Arjun Menon",
    "TP073014": "Sarah Tan Mei Ling",
    "TP067321": "Daniel Wong",
    "TP070002": "Farah Aziz",
    "TP072876": "Kevin Raj",
}


def email_address(student_id):
    return f"{student_id.lower()}@student.uni.example"


def when(month, day, hour, minute=0):
    return datetime(2026, month, day, hour, minute, tzinfo=MYT)


# ---------------------------------------------------------------------------
# Format builders
# ---------------------------------------------------------------------------
def zendesk(ticket_id, student_id, dt, subject, description, tags, channel="web"):
    return "json", {
        "ticket": {
            "id": ticket_id,
            "created_at": dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "subject": subject,
            "description": description,
            "status": "new",
            "priority": None,
            "tags": tags,
            "via": {"channel": channel},
            "requester": {"name": STUDENTS[student_id], "external_id": student_id, "email": email_address(student_id)},
            "group": "Student Services Helpdesk",
        }
    }


def moodle(post_id, student_id, dt, course, forum, subject, html_message):
    return "json", {
        "platform": "moodle",
        "course": course,
        "forum": forum,
        "discussion": {"id": post_id // 10, "name": subject},
        "post": {
            "id": post_id,
            "userid": student_id,
            "userfullname": STUDENTS[student_id],
            "created": int(dt.timestamp()),
            "subject": subject,
            "message": html_message,
            "messageformat": 1,
        },
    }


def email(student_id, dt, to, subject, body):
    header_date = dt.strftime("%a, %d %b %Y %H:%M:%S +0800")
    text = (
        f'From: "{STUDENTS[student_id]}" <{email_address(student_id)}>\n'
        f"To: {to}\n"
        f"Date: {header_date}\n"
        f"Subject: {subject}\n"
        f"X-Student-ID: {student_id}\n"
        "\n"
        f"{body.strip()}\n"
    )
    return "txt", text


def chatbot(session_id, student_id, dt, turns):
    messages = []
    for offset, (speaker, text) in enumerate(turns):
        messages.append(
            {
                "from": speaker,
                "ts": (dt + timedelta(seconds=40 * offset)).isoformat(),
                "text": text,
                **({"sid": student_id} if speaker == "student" else {}),
            }
        )
    return "json", {"source": "campus_assistant_bot", "session": session_id, "locale": "en-MY", "messages": messages}


# ---------------------------------------------------------------------------
# The stories (historical = loaded before the demo, live = shown during it)
# ---------------------------------------------------------------------------
HISTORICAL = [
    # Aisyah - financial stress that slowly gets worse
    zendesk(48211, "TP071234", when(10, 2, 10, 15), "PTPTN disbursement not received yet",
            "Hi, my PTPTN loan for this semester still hasn't come in. The fee deadline is next week. "
            "Is there any way to get an extension? I don't want my portal access blocked.",
            ["finance", "loan"]),
    email("TP071234", when(10, 13, 23, 41), "bursary@uni.example", "Instalment plan request",
          """Dear Bursary team,

I'm writing to ask if I can pay the remaining RM 4,850 in instalments. My loan was delayed
and my father's business has been slow so my family cannot cover the gap this month.
I have started working nights at a cafe (about 25 hours a week) to cover rent.

Please let me know the options, I really want to continue my degree.

Thank you,
Aisyah"""),
    moodle(77341, "TP071234", when(10, 24, 2, 5), "CT046-3-2 Cloud Infrastructure", "Lab Help",
           "Missed lab 6 again", "<p>Sorry I missed lab 6 and 7, work shifts clash with Tuesday labs. "
           "Can someone share the notes? Honestly I'm so tired I'm falling behind on everything.</p>"),

    # Jason - broken laptop, technology access
    zendesk(48290, "TP068812", when(10, 6, 14, 30), "Laptop died - need loaner",
            "my laptop motherboard is dead, repair shop says RM1200 and 2 weeks. "
            "do you guys have loaner laptops? I have a Java assignment due friday and can't install the IDE on the library PCs",
            ["it-support", "hardware"]),
    moodle(77102, "TP068812", when(10, 9, 22, 48), "AAPP Java Programming", "Assignment Q&A",
           "Late submission?", "<p>is there any penalty waiver if laptop broke? I've been doing code on my phone lol. "
           "submitting 2 days late probably</p>"),

    # Priya - burnout escalating to hopelessness
    moodle(76988, "TP070455", when(10, 4, 1, 12), "Research Methods for Computing", "General",
           "How do people manage 3 deadlines in one week?", "<p>I have FYP proposal, DSA assignment and the "
           "networking report all due the same week. I've been sleeping 3-4 hours. Any tips?</p>"),
    chatbot("cb-55120", "TP070455", when(10, 19, 3, 20), [
        ("student", "can i get an extension for all my assignments"),
        ("bot", "Extensions are handled by your module lecturer. Would you like the EC form link?"),
        ("student", "i guess. i can't focus anymore, i just stare at the screen for hours and nothing happens"),
        ("bot", "Here is the Extenuating Circumstances form: [link]. Is there anything else?"),
        ("student", "no"),
    ]),

    # Chen Wei - international student, isolation
    moodle(77015, "TP072210", when(10, 7, 20, 0), "Software Engineering", "Find a group",
           "Still looking for group members", "<p>Hi everyone, I am still looking for a group for the SE "
           "assignment. Groups were formed in week 1 but I joined late because of visa delay. Anyone?</p>"),
    email("TP072210", when(10, 21, 21, 30), "intl.office@uni.example", "Question about transfer",
          """Hello,

I would like to know the procedure to transfer my credits to another university or return home.
I have been here 2 months and I still don't know anyone. I eat alone every day and my English
makes it hard to join discussions. Maybe this place is not for me.

Regards
Chen Wei"""),

    # Nurul - family emergency
    email("TP066540", when(10, 11, 8, 5), "programme.leader@uni.example", "Urgent: family emergency",
          """Assalamualaikum Dr,

My father was admitted to Hospital Raja Perempuan Zainab II last night after a stroke.
I need to go back to Kota Bharu to help my mother, I am the eldest. I don't know how long.
May I know how to apply for deferment of my mid-term test?

Nurul Izzah"""),

    # Arjun - routine, low risk
    zendesk(48305, "TP071877", when(10, 8, 9, 0), "Password reset",
            "Can't log in to the student portal, password reset email not arriving. Please help.", ["account"]),
    chatbot("cb-55301", "TP071877", when(10, 22, 13, 10), [
        ("student", "where can i see the exam timetable for november"),
        ("bot", "The exam timetable is in the student portal under Examinations > Timetable."),
        ("student", "ok found it thanks!"),
    ]),

    # Sarah - positive, thriving
    moodle(77210, "TP073014", when(10, 15, 17, 45), "Data Analytics", "General",
           "Thank you for the Tableau workshop!", "<p>Just wanted to say the workshop on Saturday was amazing. "
           "Our club is going to use it for the hackathon. Loving this module :)</p>"),
    email("TP073014", when(10, 28, 10, 0), "career.centre@uni.example", "Internship fair registration",
          "Hi, I'd like to register for the internship fair on 20 November. Is there a dress code? Thanks, Sarah"),

    # Daniel - housing and transport
    zendesk(48377, "TP067321", when(10, 10, 7, 55), "Hostel water heater + noise",
            "Water heater in block B room 12-3 broken for 2 weeks and the unit next door has parties until 3am. "
            "I've moved out to my aunt's place in Klang, now it's 2 hours by train each way so I keep missing 8:30 classes.",
            ["hostel", "facilities"]),
    moodle(77420, "TP067321", when(10, 27, 8, 50), "Database Systems", "Attendance",
           "Attendance below 80%", "<p>Got the warning email that my attendance is 72%. "
           "The KTM delays are killing me. Is there any online option?</p>"),

    # Farah - academic pressure, thinking about withdrawing
    zendesk(48402, "TP070002", when(10, 16, 16, 20), "Midterm result query",
            "I got 31% for the Discrete Maths midterm. I studied but I just don't get it. "
            "What happens if I fail this module, do I have to repeat the whole semester?", ["academic"]),
    email("TP070002", when(10, 30, 22, 15), "registry@uni.example", "Withdrawal deadline",
          """Hi,

What is the last date to withdraw from the programme without paying next semester's fees?
I'm thinking maybe computing is not for me. My parents don't know yet.

Farah"""),

    # Kevin - connectivity + money for data
    chatbot("cb-55400", "TP072876", when(10, 18, 19, 5), [
        ("student", "my home wifi is super slow, can't join online classes"),
        ("bot", "You can use campus Wi-Fi or the library. Do you need the IT helpdesk contact?"),
        ("student", "i live in Semenyih, can't come to campus every day. mobile data finishes in 1 week, cannot afford to top up more"),
    ]),
    moodle(77455, "TP072876", when(10, 29, 21, 0), "Computer Networks", "Recordings",
           "Are lectures recorded?", "<p>Missed the last two online lectures due to connection issues. "
           "Are the recordings uploaded somewhere?</p>"),
]

LIVE_DEMO = [
    # Upload these during the demo video so judges see new signals appear.
    ("aisyah_escalation", email("TP071234", when(11, 6, 1, 30), "counselling@uni.example", "Considering deferring",
          """Hi,

I'm thinking of deferring next semester. I can't keep up with work and classes, the bursary
said instalments are not possible for my case. I failed the cloud quiz yesterday.
I don't know what else to do.

Aisyah""")),
    ("priya_crisis", chatbot("cb-56001", "TP070455", when(11, 7, 2, 40), [
        ("student", "is there a way to just stop everything"),
        ("bot", "I'm not sure I understand. Do you mean withdraw from your programme?"),
        ("student", "i dont know. i feel like nothing i do matters and i don't see the point of anything anymore"),
    ])),
    ("chen_positive", moodle(78010, "TP072210", when(11, 5, 18, 0), "Software Engineering", "Find a group",
          "Found a group, thank you!", "<p>Thank you to the peer mentor programme, I joined the Chinese "
          "students' society and found a group for SE. Feeling much better now.</p>")),
]


def write(folder, name, payload):
    kind, content = payload
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.{kind}"
    if kind == "json":
        path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")
    return path


def main():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    for number, payload in enumerate(HISTORICAL, start=1):
        kind = payload[0]
        data = payload[1]
        if kind == "json" and "ticket" in data:
            prefix = "zendesk"
        elif kind == "json" and data.get("platform") == "moodle":
            prefix = "moodle"
        elif kind == "json":
            prefix = "chatbot"
        else:
            prefix = "email"
        write(OUT_DIR / "historical", f"{number:02d}_{prefix}", payload)

    for name, payload in LIVE_DEMO:
        write(OUT_DIR / "live_demo", name, payload)

    print(f"Wrote {len(HISTORICAL)} historical files to {OUT_DIR / 'historical'}")
    print(f"Wrote {len(LIVE_DEMO)} live demo files to {OUT_DIR / 'live_demo'}")


if __name__ == "__main__":
    main()
