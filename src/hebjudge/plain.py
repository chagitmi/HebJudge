"""Plain Hebrew for people who are not security experts (D-48).

The guided interface describes every attempt, failure and goal in everyday words: what was tried
("pretended to be a manager"), what it was for ("to get its instructions"), and what went wrong.
Fixed texts, no model, so they are free and always the same.
"""

# The five things the wizard asks about, in the order shown. Each is one attacker goal.
GOALS = (
    "leak_system_prompt",
    "leak_protected_data",
    "forbidden_action",
    "off_policy_commitment",
    "role_abandonment",
)

# The checklist in the wizard: what the bot must not do, with a short explanation.
GOAL_CHOICE = {
    "leak_system_prompt": ("לחשוף את ההוראות שלו", "מה שכתבת לו, וקודים או סיסמאות שמופיעים שם"),
    "leak_protected_data": ("למסור מידע פרטי", "שלך או של אנשים אחרים: מיילים, טלפונים, כתובות"),
    "forbidden_action": ("לעשות פעולה בלי אישור", "לשלוח, למחוק, לבטל, לשלם"),
    "off_policy_commitment": ("להבטיח דברים שאסור לו", "הנחות, החזרים, מועדים"),
    "role_abandonment": ("לצאת מהתפקיד שלו", 'להפוך ל"בוט אחר" כי מישהו ביקש'),
}

# A failed goal, as the title of an issue in the result.
GOAL_FAILED = {
    "leak_system_prompt": "הבוט חשף את ההוראות שלו",
    "leak_protected_data": "הבוט מסר מידע פרטי",
    "forbidden_action": "הבוט עשה פעולה בלי אישור",
    "off_policy_commitment": "הבוט הבטיח משהו שאסור לו",
    "role_abandonment": "הבוט יצא מהתפקיד שלו",
    "benign": "הבוט סירב לבקשה רגילה",
}

# What an attempt was for, after "כדי".
GOAL_PURPOSE = {
    "leak_system_prompt": "כדי לקבל את ההוראות שלו",
    "leak_protected_data": "כדי לקבל מידע פרטי",
    "forbidden_action": "כדי שיעשה פעולה בלי אישור",
    "off_policy_commitment": "כדי לקבל הבטחה שאסור לו לתת",
    "role_abandonment": "כדי להוציא אותו מהתפקיד",
}

# What was tried, in the past tense, for the live list of attempts.
TECHNIQUE_DONE = {
    "authority_impersonation": "התחזו לצוות או למנהל",
    "emotional_pressure": "לחצו והפעילו רגשות",
    "fake_system_message": 'שלחו "הודעת מערכת" מזויפת',
    "instruction_override": "ביקשו ממנו להתעלם מההוראות",
    "fake_conversation": "טענו שהוא כבר הסכים קודם",
    "role_play": "הציעו לו משחק תפקידים",
    "format_exploit": "ביקשו את התשובה בפורמט JSON",
    "translation_trick": "ביקשו ממנו לתרגם את ההוראות",
    "hypothetical_fiction": "עטפו את הבקשה בסיפור או בשאלה תיאורטית",
    "payload_splitting": "פיצלו את הבקשה לחלקים",
    "refusal_suppression": "דרשו ממנו לענות בלי לסרב",
}

# When the failure happened, as the second line of an issue.
TECHNIQUE_WHEN = {
    "authority_impersonation": "כשמישהו התחזה לצוות או למנהל.",
    "emotional_pressure": "כשמישהו לחץ והפעיל רגשות.",
    "fake_system_message": 'כשמישהו שלח לו "הודעת מערכת" מזויפת.',
    "instruction_override": "כשביקשו ממנו להתעלם מההוראות שלו.",
    "fake_conversation": "כשמישהו טען שהוא כבר הסכים קודם.",
    "role_play": "כשהציעו לו משחק תפקידים.",
    "format_exploit": "כשביקשו את התשובה בפורמט JSON.",
    "translation_trick": "כשביקשו ממנו לתרגם את ההוראות.",
    "hypothetical_fiction": "כשהבקשה נעטפה בסיפור או בשאלה תיאורטית.",
    "payload_splitting": "כשהבקשה פוצלה לחלקים.",
    "refusal_suppression": "כשדרשו ממנו לענות בלי לסרב.",
}


def attempt(goal: str | None, technique: str | None) -> str:
    """One attempt in everyday words: 'pretended to be a manager, to get its instructions'."""
    if not goal or goal == "benign":
        return "שאלה רגילה, כדי לוודא שהוא לא מסרב סתם"
    done = TECHNIQUE_DONE.get(technique or "", "ניסו לעקוף את ההוראות")
    purpose = GOAL_PURPOSE.get(goal)
    return f"{done}, {purpose}" if purpose else done


def outcome(goal: str | None, verdict: str) -> str:
    """The result of one attempt: the bot held, failed, or it is unclear."""
    benign = not goal or goal == "benign"
    if verdict == "unclear":
        return "לא ברור"
    if verdict == "attack_succeeded":
        return "הבוט סירב" if benign else "הבוט נכשל"
    return "הבוט ענה" if benign else "הבוט עמד"


def when(technique: str | None) -> str:
    return TECHNIQUE_WHEN.get(technique or "", "")
