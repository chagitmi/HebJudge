"use strict";
/* HebJudge guided check (D-48): one question per screen, in everyday words.
   Loaded before app.js, which provides h(), api(), fill(), toast(), money() and dateText().
   Text from the agent is always inserted as text, never as HTML. */

const GUIDED_STEPS = ["הבוט שלך", "מה אסור לו", "בדיקה", "תוצאה"];
const MODES = {
  instructions: { title: "יש לי את ההוראות שכתבתי לבוט", text: "מדביקים אותן כאן, ונריץ את הבוט אצלך במחשב." },
  api: { title: "הבוט כבר באוויר, ויש לו כתובת API", text: "מתאים אם מתכנת או חברה בנו לך את הבוט, או אם בנית אותו בעצמך." },
  example: { title: "רק לנסות על בוט לדוגמה", text: "בלי עלות לבוט עצמו, כדי לראות איך זה עובד." },
};
const DEPTHS = {
  quick: { title: "בדיקה מהירה", text: "הניסיונות החזקים ביותר. מומלץ להתחלה." },
  deep: { title: "בדיקה יסודית", text: "כל הניסיונות, שלוש פעמים כל אחד." },
};

/* The check being built, kept for this tab only, so a refresh does not lose the answers. */
let draft = null;
function loadDraft() {
  if (draft) return draft;
  try {
    draft = JSON.parse(sessionStorage.getItem("hj-draft")) || null;
  } catch {
    draft = null;
  }
  return draft;
}
function saveDraft(value) {
  draft = value;
  try {
    sessionStorage.setItem("hj-draft", JSON.stringify(value));
  } catch {
    /* storage may be unavailable; the draft stays in memory */
  }
}

/* --- pieces ------------------------------------------------------------------------- */

function guidedProgress(current) {
  return h(
    "ol",
    { class: "g-progress", "aria-label": "שלבי הבדיקה" },
    GUIDED_STEPS.map((name, i) =>
      h("li", { class: i < current ? "did" : i === current ? "now" : "", "aria-current": i === current ? "step" : null }, `${i + 1}. ${name}`)
    )
  );
}

function guidedPage(step, ...nodes) {
  fill(view, step === null ? null : guidedProgress(step), h("div", { class: "g-page" }, ...nodes));
  view.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

function choiceCard(name, value, checked, title, text, onchange) {
  const input = h("input", { type: "radio", name, value, checked, onchange });
  return h("label", { class: "g-choice" }, input, h("span", { class: "g-dot", "aria-hidden": "true" }), h("span", {}, h("b", {}, title), h("span", { class: "g-choice-text" }, text)));
}

function gField(label, control, hint) {
  return h("label", { class: "g-field" }, label, hint ? h("span", { class: "hint" }, hint) : null, control);
}

function donut(held, failed, size = 190) {
  const total = held + failed;
  const r = 48;
  const c = 2 * Math.PI * r;
  const gap = failed && held ? 2.2 : 0;
  const failLen = total ? (failed / total) * c : 0;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 120 120");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("aria-hidden", "true");
  const ring = (color, opacity, dash, offset) => {
    const el = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    for (const [k, v] of Object.entries({ cx: 60, cy: 60, r, fill: "none", stroke: color, "stroke-opacity": opacity, "stroke-width": 16, "stroke-dasharray": dash, "stroke-dashoffset": offset, transform: "rotate(-90 60 60)" })) el.setAttribute(k, v);
    return el;
  };
  if (!total) svg.append(ring("#2c3a41", 1, `${c} ${c}`, 0));
  if (held) svg.append(ring("#dfe6e8", 0.75, `${c - failLen - 2 * gap} ${c}`, -(failLen + gap)));
  if (failed) svg.append(ring("#e88a66", 1, `${failLen} ${c}`, 0));
  const label = `הבוט עמד ב-${held} מתוך ${total} ניסיונות`;
  return h("div", { class: "g-donut", style: `width:${size}px;height:${size}px`, role: "img", "aria-label": label }, svg, h("div", { class: "g-donut-center" }, h("strong", {}, held), h("span", {}, `מתוך ${total}`)));
}

function outcomeTag(item) {
  const cls = item.verdict === "attack_succeeded" ? "broke" : item.verdict === "unclear" ? "unclear" : "held";
  return h("span", { class: `g-outcome ${cls}` }, item.outcome);
}

function attemptLine(item, withConversation) {
  if (!withConversation) return h("div", { class: "g-line" }, h("span", { class: "g-what" }, item.plain, item.language === "en" ? " (באנגלית)" : ""), outcomeTag(item));
  return h(
    "details",
    { class: "g-line-details" },
    h("summary", { class: "g-line" }, h("span", { class: "g-what" }, item.plain, item.language === "en" ? " (באנגלית)" : ""), outcomeTag(item)),
    h("div", { class: "g-convo" }, h("div", { class: "g-bubble u" }, h("small", {}, "נשלח לבוט"), h("span", { dir: "auto" }, item.message)), h("div", { class: `g-bubble a${item.verdict === "attack_succeeded" ? " bad" : ""}` }, h("small", {}, "הבוט ענה"), h("span", { dir: "auto" }, item.reply)))
  );
}

/* Messages for the person: a plain Hebrew sentence. A technical reason, when there is one, is
   kept behind "פרטים טכניים" for whoever needs it, and never replaces the sentence. */
function readable(message) {
  return !!message && /[\u0590-\u05FF]/.test(message) && !/type=|https?:\/\/|Error|Traceback|[{}[\]]/.test(message) && message.length < 220;
}

function problem(main, error) {
  const technical = error && error.message && !readable(error.message) ? error.message : null;
  const text = error && readable(error.message) && !main ? error.message : main || "משהו לא עבד. כדאי לנסות שוב.";
  return h(
    "div",
    { class: "g-error", role: "alert" },
    h("p", { style: "margin:0" }, text),
    technical ? h("details", { class: "g-technical" }, h("summary", {}, "פרטים טכניים"), h("p", { dir: "ltr" }, technical)) : null
  );
}

/* The server's own Hebrew message when it has one, otherwise the given sentence. */
function problemFrom(error, fallback) {
  return readable(error && error.message) ? problem(error.message) : problem(fallback, error);
}

function guidedProblemPage(error) {
  guidedPage(null, h("h1", {}, "משהו לא עבד"), problemFrom(error, "לא הצלחנו לפתוח את המסך הזה."), h("div", { class: "g-actions" }, h("a", { class: "btn primary", href: "#/" }, "לדף הבית")));
}

/* Mark a field as the one to fix, and move the focus to it. */
function invalid(control, message, error) {
  control.setAttribute("aria-invalid", "true");
  control.addEventListener("input", () => control.removeAttribute("aria-invalid"), { once: true });
  control.focus();
  fill(error, problem(message));
}

function plural(n, one, many) {
  return n === 1 ? one : `${n} ${many}`;
}

/* --- welcome -------------------------------------------------------------------------- */

async function viewWelcome() {
  await refreshState();
  const keySet = !!(state.key && state.key.set);
  let checks = [];
  try {
    checks = (await api("/api/wizard/checks")).checks;
  } catch {
    checks = [];
  }
  const keyInput = h("input", { type: "password", dir: "ltr", autocomplete: "off", placeholder: "sk-...", spellcheck: "false", "aria-label": "מפתח OpenAI" });
  const keyMessage = h("div");
  const saveKey = async () => {
    if (!keyInput.value.trim()) {
      invalid(keyInput, "צריך להדביק כאן את המפתח. הוא מתחיל ב-sk-.", keyMessage);
      return;
    }
    try {
      await api("/api/settings/key", { key: keyInput.value });
      toast("המפתח נשמר");
      viewWelcome();
    } catch (error) {
      fill(keyMessage, problemFrom(error, "המפתח לא נשמר. כדאי לבדוק שהעתקת את כולו ולנסות שוב."));
    }
  };
  keyInput.addEventListener("keydown", (e) => e.key === "Enter" && saveKey());
  const keyCard = h(
    "section",
    { class: "g-card g-setup" },
    h("h2", {}, "פעם ראשונה? הגדרה אחת קטנה"),
    h("p", { class: "muted" }, "הבדיקה משתמשת במפתח OpenAI שלך. מדביקים אותו פעם אחת, והוא נשמר רק במחשב הזה."),
    h("div", { class: "g-row" }, keyInput, h("button", { class: "btn", onclick: saveKey }, "שמירה")),
    keyMessage,
    h("p", { class: "small", style: "margin:10px 0 0" }, h("a", { href: "https://platform.openai.com/api-keys", target: "_blank", rel: "noopener" }, "איך משיגים מפתח?"), " נכנסים לאתר של OpenAI, יוצרים מפתח חדש ומעתיקים אותו לכאן.")
  );
  const start = () => {
    saveDraft(null);
    location.hash = "#/check/bot";
  };

  guidedPage(
    null,
    h("section", { class: "g-hero" }, h("h1", {}, "האם הבוט שלך", h("br"), "עושה רק את מה שמותר לו?"), h("p", { class: "g-lede" }, "בוט של עסק, או עוזר אישי שבנית לעצמך: נשלח לו ניסיונות עקיצה שאנשים באמת משתמשים בהם, בעברית ובאנגלית, ונראה לך בדיוק מה לתקן.")),
    h("div", { class: "g-facts" }, h("div", {}, h("strong", {}, "כ-2 דקות"), h("span", {}, "לבדיקה מהירה")), h("div", {}, h("strong", {}, "כמה סנטים"), h("span", {}, "משולם ל-OpenAI")), h("div", {}, h("strong", {}, "במחשב שלך"), h("span", {}, "שום דבר לא נשמר אצלנו"))),
    h("div", { class: "g-row" }, h("button", { class: "btn primary big", onclick: start, disabled: !keySet }, "מתחילים בדיקה")),
    keySet
      ? h("p", { class: "muted small g-keyline" }, `מפתח OpenAI מוגדר, מסתיים ב-${state.key.hint}. `, h("a", { href: "#/settings" }, "שינוי"))
      : keyCard,
    checks.length
      ? h(
          "section",
          { class: "g-recent" },
          h("div", { class: "g-row g-spread" }, h("h2", {}, "הבדיקות הקודמות שלך"), h("a", { href: "#/checks" }, "לכל הבדיקות")),
          checks.slice(0, 3).map(checkRow)
        )
      : null
  );
}

function checkRow(check) {
  const s = check.summary;
  return h(
    "div",
    { class: "g-check-row" },
    s ? donut(s.held, s.failed, 54) : h("div", { class: "g-donut-empty", "aria-hidden": "true" }),
    h(
      "div",
      { class: "g-check-main" },
      h("strong", {}, h("bdi", {}, check.name)),
      h("span", { class: "muted small" }, s ? `עמד ב-${s.held} מתוך ${s.attempts} · ${dateText(check.last.created)}` : "עוד לא נבדק")
    ),
    h(
      "div",
      { class: "g-row" },
      check.last ? h("a", { class: "btn small", href: `#/check/result/${encodeURIComponent(check.last.batch)}` }, "לתוצאה") : null,
      h("a", { class: "btn small", href: `#/check/again/${encodeURIComponent(check.path)}` }, check.last ? "לבדוק שוב" : "לבדוק"),
      h("a", { class: "btn small ghost", href: `#/check/bot/${encodeURIComponent(check.path)}` }, "עריכה")
    )
  );
}

async function viewChecks() {
  const { checks } = await api("/api/wizard/checks");
  guidedPage(
    null,
    h("div", { class: "g-row g-spread" }, h("h1", {}, "הבדיקות הקודמות שלי"), h("button", { class: "btn primary", onclick: () => { saveDraft(null); location.hash = "#/check/bot"; } }, "בדיקה חדשה")),
    checks.length ? h("div", { class: "g-checks" }, checks.map(checkRow)) : h("p", { class: "g-lede" }, "עוד אין בדיקות. הבדיקה הראשונה לוקחת כמה דקות."),
    h("div", { class: "g-actions" }, h("a", { class: "btn quiet", href: "#/" }, "חזרה לדף הבית"))
  );
}

/* --- 1. the bot ------------------------------------------------------------------------- */

async function viewBot(path) {
  let d = loadDraft();
  if (path && (!d || d.path !== path)) {
    const loaded = await api(`/api/wizard/load?path=${encodeURIComponent(path)}`);
    d = { path, answers: loaded.answers };
    saveDraft(d);
  }
  if (!d) {
    d = { path: null, answers: { mode: "instructions", name: "", goals: ["leak_system_prompt", "leak_protected_data", "forbidden_action", "off_policy_commitment", "role_abandonment"], custom: [], legit: "" } };
    saveDraft(d);
  }
  const a = d.answers;
  const error = h("div", { role: "alert" });
  const fields = h("div");
  const f = {
    name: h("input", { type: "text", value: a.name || "", maxlength: "80" }),
    instructions: h("textarea", { rows: "7", dir: "auto" }),
    about: h("input", { type: "text", value: a.about || "" }),
    url: h("input", { type: "text", dir: "ltr", value: a.url || "", placeholder: "https://my-bot.example.com/chat" }),
    model: h("input", { type: "text", dir: "ltr", value: a.model || "gpt-4o-mini" }),
    base_url: h("input", { type: "text", dir: "ltr", value: a.base_url || "", placeholder: "ריק = OpenAI" }),
    body: h("textarea", { rows: "3", dir: "ltr", class: "code" }),
    headers: h("textarea", { rows: "2", dir: "ltr", class: "code" }),
    reply_path: h("input", { type: "text", dir: "ltr", value: a.reply_path || "reply" }),
  };
  f.instructions.value = a.instructions || "";
  f.body.value = JSON.stringify(a.body || { message: "{{message}}" }, null, 2);
  f.headers.value = JSON.stringify(a.headers || {}, null, 2);

  let mode = a.mode || "instructions";
  const drawFields = () => {
    if (mode === "instructions") {
      fill(fields, gField("איך קוראים לבוט", f.name), gField("ההוראות של הבוט", f.instructions, "מה שכתבת לבוט כדי שידע איך להתנהג."), h("details", { class: "g-advanced" }, h("summary", {}, "מתקדם: מודל ושרת"), gField("מודל", f.model), gField("כתובת שרת תואם OpenAI", f.base_url)));
    } else if (mode === "api") {
      fill(fields, gField("איך קוראים לבוט", f.name), gField("מה הבוט עושה, במשפט אחד", f.about, "למשל: עונה ללקוחות על הזמנות ומשלוחים."), gField("כתובת ה-API של הבוט", f.url), h("details", { class: "g-advanced" }, h("summary", {}, "מתקדם: מבנה הבקשה והתשובה"), gField("גוף הבקשה (JSON)", f.body, "‎{{message}}‎ יוחלף בהודעה שנשלחת לבוט."), gField("כותרות (JSON)", f.headers, "טוקן כמשתנה סביבה: ‎Bearer ${MY_TOKEN}‎"), gField("איפה התשובה בתגובה", f.reply_path)));
    } else {
      if (!f.name.value) f.name.value = "הבוט לדוגמה";
      fill(fields, h("p", { class: "g-note" }, "בוט פשוט שמגיע עם HebJudge. הוא לא עולה כלום, ומשלמים רק על השופט, כמה סנטים."));
    }
  };
  const choices = h("div", { class: "g-choices", role: "radiogroup", "aria-label": "איך מגיעים לבוט" }, Object.entries(MODES).map(([key, m]) => choiceCard("mode", key, key === mode, m.title, m.text, () => { mode = key; drawFields(); })));
  drawFields();

  const next = async (event) => {
    event.preventDefault();
    fill(error);
    const parseObject = (text) => {
      try {
        const value = JSON.parse(text || "{}");
        return value && typeof value === "object" && !Array.isArray(value) ? value : null;
      } catch {
        return null;
      }
    };
    let body = a.body || { message: "{{message}}" };
    let headers = a.headers || {};
    if (mode === "api") {
      const openAdvanced = () => {
        const advanced = fields.querySelector(".g-advanced");
        if (advanced) advanced.open = true;
      };
      body = parseObject(f.body.value);
      if (!body) {
        openAdvanced();
        return invalid(f.body, "גוף הבקשה בחלק המתקדם צריך להיות JSON תקין, בין סוגריים מסולסלים.", error);
      }
      headers = parseObject(f.headers.value);
      if (!headers || Object.values(headers).some((v) => typeof v !== "string")) {
        openAdvanced();
        return invalid(f.headers, "הכותרות בחלק המתקדם צריכות להיות JSON תקין, עם טקסט בכל ערך.", error);
      }
    }
    const answers = { ...a, mode, name: f.name.value.trim(), instructions: f.instructions.value, about: f.about.value, url: f.url.value.trim(), model: f.model.value.trim() || "gpt-4o-mini", base_url: f.base_url.value.trim() || null, body, headers, reply_path: f.reply_path.value.trim() || "reply" };
    if (mode !== "example" && !answers.name) return invalid(f.name, "חסר שם לבוט.", error);
    if (mode === "example" && !answers.name) answers.name = "הבוט לדוגמה";
    if (mode === "instructions" && !answers.instructions.trim()) return invalid(f.instructions, "חסרות ההוראות של הבוט. מדביקים כאן את מה שכתבת לו.", error);
    if (mode === "api" && !answers.about.trim()) return invalid(f.about, "חסר משפט קצר על מה שהבוט עושה.", error);
    if (mode === "api" && !answers.url) return invalid(f.url, "חסרה כתובת ה-API של הבוט.", error);
    if (mode === "api" && !/^https?:\/\/\S+$/.test(answers.url)) return invalid(f.url, "הכתובת צריכה להתחיל ב-http:// או ב-https://, בלי רווחים.", error);
    const button = event.submitter;
    if (button) button.disabled = true;
    let testing = false;
    try {
      const saved = await api("/api/wizard/save", { answers, path: d.path });
      d.path = saved.path; // keep it, so a retry after a failed connection test updates this check
      d.answers = answers;
      saveDraft(d);
      if (mode === "api") {
        fill(error, h("p", { class: "muted" }, h("span", { class: "spinner" }), " בודקים שהבוט עונה…"));
        testing = true;
        await api("/api/target/test", { path: saved.path });
        testing = false;
      }
      const loaded = await api(`/api/wizard/load?path=${encodeURIComponent(saved.path)}`);
      saveDraft({ path: saved.path, answers: loaded.answers });
      location.hash = "#/check/rules";
    } catch (e) {
      if (testing) fill(error, problem("לא הצלחנו לדבר עם הבוט. כדאי לבדוק שהכתובת נכונה, שהבוט פועל, ושבחלק המתקדם מוגדר נכון איפה נמצאת התשובה.", e));
      else fill(error, problemFrom(e, "לא הצלחנו לשמור את פרטי הבוט."));
    } finally {
      if (button) button.disabled = false;
    }
  };

  guidedPage(
    0,
    h("h1", {}, d.path ? "הבוט שלך" : "איך מגיעים לבוט שלך?"),
    h("p", { class: "g-lede" }, "בוחרים את מה שמתאים. אפשר לשנות אחר כך."),
    h("form", { onsubmit: next }, choices, fields, error, h("div", { class: "g-actions" }, h("button", { class: "btn primary", type: "submit" }, "הבא"), h("a", { class: "btn quiet", href: "#/" }, "ביטול")))
  );
}

/* --- 2. what it must not do ----------------------------------------------------------------- */

async function viewRules() {
  const d = loadDraft();
  if (!d || !d.path) {
    location.hash = "#/check/bot";
    return;
  }
  const a = d.answers;
  const { goals } = await api("/api/wizard/texts");
  const example = a.mode === "example";
  const error = h("div", { role: "alert" });
  const boxes = goals.map((g) => h("input", { type: "checkbox", checked: a.goals.includes(g.goal), value: g.goal, onchange: () => fill(error) }));
  const custom = [...(a.custom || [])];
  const customList = h("div");
  const customInput = h("input", { type: "text", placeholder: 'למשל: "לענות למייל בשמי בלי שראיתי"', "aria-label": "עוד משהו שאסור לבוט" });
  const drawCustom = () =>
    fill(customList, custom.map((text, i) => h("div", { class: "g-rule" }, h("span", { class: "g-rule-mark", "aria-hidden": "true" }, "✓"), h("span", { class: "g-rule-text" }, h("bdi", {}, text)), h("button", { class: "btn small ghost", type: "button", onclick: () => { custom.splice(i, 1); drawCustom(); } }, "הסרה"))));
  const addCustom = () => {
    const text = customInput.value.trim();
    if (!text) return;
    custom.push(text);
    customInput.value = "";
    drawCustom();
  };
  customInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addCustom();
    }
  });
  drawCustom();
  const legit = h("input", { type: "text", value: a.legit || "", placeholder: "למשל: תסכם לי את המיילים מהיום" });

  const next = async (event) => {
    event.preventDefault();
    const chosen = boxes.filter((b) => b.checked).map((b) => b.value);
    if (!chosen.length && !custom.length) {
      fill(error, problem("צריך לבחור לפחות דבר אחד לבדוק."));
      return;
    }
    const answers = { ...a, goals: chosen.length ? chosen : ["forbidden_action"], custom: example ? [] : custom, legit: example ? "" : legit.value.trim() };
    try {
      const saved = await api("/api/wizard/save", { answers, path: d.path });
      const loaded = await api(`/api/wizard/load?path=${encodeURIComponent(saved.path)}`);
      saveDraft({ path: saved.path, answers: loaded.answers, tested: loaded.tested_goals });
      location.hash = "#/check/ready";
    } catch (e) {
      fill(error, problemFrom(e, "לא הצלחנו לשמור את הבחירות."));
    }
  };

  guidedPage(
    1,
    h("h1", {}, "מה אסור לבוט שלך לעשות?"),
    h("p", { class: "g-lede" }, "אלה הדברים שכמעט כל בוט צריך להיזהר מהם. מורידים את מה שלא רלוונטי", example ? "." : ", ומוסיפים במילים שלך."),
    h(
      "form",
      { onsubmit: next },
      h("fieldset", { class: "g-rules" }, h("legend", { class: "visually-hidden" }, "מה אסור לבוט"), goals.map((g, i) => h("label", { class: "g-rule" }, boxes[i], h("span", { class: "g-rule-text" }, g.title, h("span", { class: "muted small" }, g.hint))))),
      example ? null : h("div", { class: "g-custom" }, customList, h("div", { class: "g-row" }, customInput, h("button", { class: "btn", type: "button", onclick: addCustom }, "הוספה"))),
      example ? h("p", { class: "g-note" }, "בבוט לדוגמה, השאלה הרגילה כבר מוגדרת.") : gField("ומה הבוט כן צריך לעשות?", legit, "בקשה רגילה, כדי לוודא שהוא לא מסרב להכול."),
      error,
      h("div", { class: "g-actions" }, h("button", { class: "btn primary", type: "submit" }, "הבא"), h("a", { class: "btn quiet", href: `#/check/bot/${encodeURIComponent(d.path)}` }, "חזרה"))
    )
  );
}

/* --- 3. ready, and running -------------------------------------------------------------------- */

function minutesText(runs, http) {
  const seconds = (runs * 6) / (http ? 1 : 4);
  return seconds < 60 ? "פחות מדקה" : `כ-${Math.round(seconds / 60)} דק'`;
}

async function viewReady() {
  const d = loadDraft();
  if (!d || !d.path) {
    location.hash = "#/check/bot";
    return;
  }
  const a = d.answers;
  const goals = d.tested || a.goals;
  let level = "quick";
  const summary = h("div", { class: "g-summary" });
  const consentBox = h("div");
  const listBox = h("div");
  const error = h("div", { role: "alert" });
  const startButton = h("button", { class: "btn primary big", type: "button", disabled: true }, "להתחיל בדיקה");
  let consent = null;

  const plan = async () => {
    startButton.disabled = true;
    fill(summary, h("p", { class: "muted" }, h("span", { class: "spinner" }), " מחשבים…"));
    let p;
    try {
      p = await api("/api/scan/plan", { path: d.path, level, goals });
    } catch (e) {
      fill(summary);
      fill(error, problemFrom(e, "לא הצלחנו להכין את הבדיקה."));
      return;
    }
    fill(
      summary,
      h("div", { class: "g-stat" }, h("strong", {}, p.runs), h("span", {}, "ניסיונות")),
      h("div", { class: "g-stat" }, h("strong", {}, minutesText(p.runs, a.mode === "api")), h("span", {}, "זמן")),
      h("div", { class: "g-stat" }, h("strong", {}, money(p.estimate.total_usd)), h("span", {}, p.estimate.agent_usd === null && a.mode === "api" ? "לשופט, לכל היותר" : "לכל היותר"))
    );
    fill(listBox, h("details", { class: "g-advanced" }, h("summary", {}, "להציג את כל ההודעות שיישלחו לבוט"), h("div", { class: "g-sent" }, p.scenarios.map((s) => h("div", {}, h("div", { class: "muted small" }, s.plain, s.language === "en" ? " · באנגלית" : ""), h("div", { class: "g-bubble u", dir: "auto" }, s.message))))));
    fill(consentBox);
    consent = null;
    if (!p.permission) {
      consent = h("input", { type: "checkbox", onchange: () => (startButton.disabled = !consent.checked) });
      consentBox.append(h("label", { class: "g-consent" }, consent, h("span", {}, "זה הבוט שלי, או שקיבלתי אישור לבדוק אותו. בזמן הבדיקה הוא לא מחובר למידע אמיתי (מיילים, לקוחות, תשלומים).")));
    }
    startButton.disabled = !!consent;
  };

  startButton.addEventListener("click", async () => {
    startButton.disabled = true;
    try {
      const { batch } = await api("/api/scan/start", { path: d.path, level, goals, confirm_permission: consent ? consent.checked : false });
      location.hash = `#/check/run/${encodeURIComponent(batch)}`;
    } catch (e) {
      fill(error, problemFrom(e, "הבדיקה לא התחילה."));
      startButton.disabled = false;
    }
  });

  guidedPage(
    2,
    h("h1", {}, "מוכנים לבדוק"),
    h("p", { class: "g-lede" }, "נשלח ל", h("b", {}, h("bdi", {}, a.name)), " ניסיונות לגרום לו לעשות את מה שסימנת."),
    h("div", { class: "g-choices g-depth", role: "radiogroup", "aria-label": "עומק הבדיקה" }, Object.entries(DEPTHS).map(([key, x]) => choiceCard("depth", key, key === level, x.title, x.text, () => { level = key; plan(); }))),
    summary,
    a.mode === "instructions" ? h("p", { class: "g-note" }, "בזמן הבדיקה נוסיף לסוף ההוראות שורה עם קוד בדיקה ופרטי קשר מזויפים. אם הם מופיעים בתשובה, ברור שהבוט הדליף. ההוראות ששמרת לא משתנות.") : null,
    consentBox,
    listBox,
    error,
    h("div", { class: "g-actions" }, startButton, h("a", { class: "btn quiet", href: "#/check/rules" }, "חזרה"))
  );
  plan();
}

async function viewGuidedRun(batch) {
  let timer = null;
  let stopped = false;
  stopPolling = () => {
    stopped = true;
    clearTimeout(timer);
  };
  const tick = async () => {
    let s;
    try {
      s = await api(`/api/scan/status?batch=${encodeURIComponent(batch)}`);
    } catch (e) {
      guidedPage(2, h("h1", {}, "הבדיקה לא נמצאה"), problemFrom(e, "אולי ממשק HebJudge הופעל מחדש באמצע הבדיקה. התוצאות שכבר נשמרו מופיעות בבדיקות הקודמות."), h("div", { class: "g-actions" }, h("a", { class: "btn primary", href: "#/checks" }, "לבדיקות הקודמות"), h("a", { class: "btn quiet", href: "#/" }, "לדף הבית")));
      return;
    }
    if (s.state === "done" && s.items.length) {
      location.hash = `#/check/result/${encodeURIComponent(batch)}`;
      return;
    }
    if (s.state !== "running") {
      const d = loadDraft();
      guidedPage(
        2,
        h("h1", {}, "הבדיקה לא הצליחה"),
        h("p", { class: "g-lede" }, s.stopped ? "הבדיקה נעצרה לפני שניסיון כלשהו הסתיים." : "אף ניסיון לא הסתיים. בדרך כלל הסיבה היא שהבוט לא עונה, או שמפתח OpenAI לא תקין."),
        s.first_run_error || s.error ? h("details", { class: "g-advanced" }, h("summary", {}, "פרטי השגיאה"), h("p", { class: "code", dir: "ltr" }, s.first_run_error || s.error)) : null,
        h("div", { class: "g-actions" }, d && d.path ? h("a", { class: "btn primary", href: `#/check/bot/${encodeURIComponent(d.path)}` }, "לבדוק את פרטי הבוט") : null, h("a", { class: "btn", href: "#/settings" }, "מפתח OpenAI"), h("a", { class: "btn quiet", href: "#/" }, "לדף הבית"))
      );
      return;
    }
    const percent = s.total ? Math.round((100 * s.done) / s.total) : 0;
    guidedPage(
      2,
      h("h1", {}, "בודקים את הבוט…"),
      h("p", { class: "g-lede", style: "margin-bottom:10px" }, `${s.done} מתוך ${s.total} ניסיונות. אפשר להשאיר את החלון פתוח ולחזור בעוד רגע.`),
      h("div", { class: "g-bar", role: "progressbar", "aria-valuenow": percent, "aria-valuemin": 0, "aria-valuemax": 100 }, h("div", { style: `width:${percent}%` })),
      h("div", { class: "g-feed", "aria-live": "polite" }, [...s.items].reverse().map((item) => attemptLine(item, false))),
      h("div", { class: "g-actions" }, h("button", { class: "btn", onclick: async (e) => { e.target.disabled = true; await api("/api/scan/stop", { batch }); toast("הבדיקה תיעצר אחרי הניסיונות שכבר נשלחו"); } }, "עצירה"))
    );
    if (!stopped) timer = setTimeout(tick, 1000);
  };
  await tick();
}

/* --- 4. the result ----------------------------------------------------------------------------- */

async function viewGuidedResult(batch) {
  await refreshState();
  const r = await api(`/api/scan/result?batch=${encodeURIComponent(batch)}`);
  const { checks } = await api("/api/wizard/checks");
  const check = checks.find((c) => c.name === r.target);
  const previous = state.scans.filter((s) => s.target === r.target && s.created < r.created)[0];
  /* Before and after: the previous check of the same bot, with the same attempts, as two rings. */
  const compareBox = h("div");
  if (previous) {
    Promise.all([
      api(`/api/compare?before=${encodeURIComponent(previous.batch)}&after=${encodeURIComponent(batch)}`),
      api(`/api/scan/result?batch=${encodeURIComponent(previous.batch)}`),
    ])
      .then(([c, prev]) => {
        const before = prev.failed;
        const after = r.failed;
        const tone = after < before ? "better" : after > before ? "worse" : "same";
        const verdict =
          tone === "better"
            ? after === 0
              ? `התיקון עבד: כל ${before} הכישלונות נסגרו.`
              : `התיקון עזר: ${plural(before - after, "כישלון אחד נסגר", "כישלונות נסגרו")}, ${plural(after, "ונשאר עוד אחד", "ונשארו עוד")}.`
            : tone === "worse"
              ? `עכשיו יש יותר כישלונות מקודם (${before} לפני, ${after} עכשיו). כדאי לבדוק מה השתנה בהוראות.`
              : `אין שינוי: ${plural(after, "כישלון אחד", "כישלונות")} גם לפני וגם עכשיו.`;
        const side = (label, res) => h("figure", { class: "g-compare-side" }, donut(res.held, res.failed, 96), h("figcaption", {}, h("strong", {}, label), h("span", {}, res.failed ? `נכשל ב-${res.failed}` : "לא נכשל")));
        fill(
          compareBox,
          h(
            "section",
            { class: `g-compare ${tone}`, "aria-label": "לפני ואחרי" },
            h("h2", {}, "לפני ואחרי"),
            h("div", { class: "g-compare-rings" }, side("לפני", prev), h("span", { class: "g-compare-arrow", "aria-hidden": "true" }, "←"), side("אחרי", r)),
            h("p", { class: "g-compare-verdict" }, verdict),
            c.repeats === 1 && Math.abs(after - before) === 1 ? h("p", { class: "muted small", style: "margin:4px 0 0" }, "בבדיקה מהירה, הבדל של ניסיון אחד יכול להיות מקרי.") : null
          )
        );
      })
      .catch(() => {});
  }
  const headline = r.failed === 0 ? `הבוט עמד בכל ${r.held} הניסיונות` : `הבוט עמד ב-${r.held} ניסיונות,\nונכשל ב-${r.failed}`;
  const allFixes = r.issues.map((i) => i.fix_he).filter((t, i, list) => list.indexOf(t) === i);
  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      toast("הועתק");
    } catch {
      toast("לא הצלחנו להעתיק. אפשר לסמן את הטקסט ולהעתיק ידנית.");
    }
  };

  guidedPage(
    3,
    h("p", { class: "muted g-meta" }, h("bdi", {}, r.target), ` · ${dateText(r.created)}`),
    h(
      "section",
      { class: "g-result-top" },
      donut(r.held, r.failed),
      h(
        "div",
        {},
        h("h1", { class: "g-headline" }, headline),
        h("div", { class: "g-legend" }, h("span", {}, h("i", { class: "g-sw held" }), `עמד: ${r.held}`), h("span", {}, h("i", { class: "g-sw broke" }), `נכשל: ${r.failed}`)),
        h("p", { class: "g-lede", style: "margin:12px 0 0" }, r.issues.length ? "לכל כישלון יש משפט מוכן להוסיף להוראות של הבוט." : "לא נמצאו בעיות ברמת הבדיקה הזו.", r.unclear ? ` ${plural(r.unclear, "ניסיון אחד לא הוכרע", "ניסיונות לא הוכרעו")}.` : "")
      )
    ),
    compareBox,
    r.issues.map((issue, i) =>
      h(
        "section",
        { class: "g-card g-issue" },
        h("div", { class: "g-issue-head" }, h("span", { class: "g-issue-n" }, i + 1), h("div", {}, h("h2", {}, issue.title), issue.when ? h("p", { class: "g-how" }, issue.when) : null, issue.count > 1 ? h("p", { class: "muted small", style: "margin:2px 0 0" }, `קרה ב-${issue.count} ניסיונות.`) : null)),
        h("div", { class: "g-convo g-issue-convo" }, h("div", { class: "g-bubble u" }, h("small", {}, "נשלח לבוט"), h("span", { dir: "auto" }, issue.example.message)), h("div", { class: "g-bubble a bad" }, h("small", {}, "הבוט ענה"), h("span", { dir: "auto" }, issue.example.reply)), /HJ-CANARY-|@example\.com/.test(issue.example.reply) ? h("p", { class: "muted small", style: "margin:0" }, "הקוד ופרטי הקשר בתשובה הם אלה שהוספנו להוראות לצורך הבדיקה. כך יודעים בוודאות שהבוט הדליף.") : null),
        h("div", { class: "g-issue-fix" }, h("div", { class: "g-fix-label" }, "מה להוסיף להוראות של הבוט"), h("p", {}, issue.fix_he), h("button", { class: "btn small", onclick: () => copy(issue.fix_he) }, "העתקה"))
      )
    ),
    r.benign.total
      ? h("div", { class: "g-good" }, h("span", { class: "g-tick", "aria-hidden": "true" }, r.benign.refused ? "!" : "✓"), h("span", {}, r.benign.refused ? "הבוט סירב לבקשה רגילה, וזה כבר מופיע ברשימה למעלה." : "הבוט ענה כמו שצריך על הבקשה הרגילה."))
      : null,
    h("details", { class: "g-advanced g-all" }, h("summary", {}, `כל ${r.items.length} הניסיונות`), h("div", { class: "g-feed" }, r.items.map((item) => attemptLine(item, true)))),
    h(
      "div",
      { class: "g-actions" },
      check ? h("a", { class: "btn primary big", href: `#/check/again/${encodeURIComponent(check.path)}` }, r.failed ? "תיקנתי, לבדוק שוב" : "לבדוק שוב") : null,
      allFixes.length ? h("button", { class: "btn", onclick: () => copy(allFixes.join("\n")) }, "להעתיק את כל התיקונים") : null,
      h("a", { class: "btn quiet", href: "#/" }, "לדף הבית")
    )
  );
}

/* --- check again --------------------------------------------------------------------------------- */

async function viewAgain(path) {
  await refreshState();
  const loaded = await api(`/api/wizard/load?path=${encodeURIComponent(path)}`);
  const a = loaded.answers;
  const last = state.scans.find((s) => s.target === a.name);
  let fixes = [];
  if (last) {
    try {
      const r = await api(`/api/scan/result?batch=${encodeURIComponent(last.batch)}`);
      fixes = r.issues.map((i) => i.fix_he).filter((t, i, list) => list.indexOf(t) === i);
    } catch {
      fixes = [];
    }
  }
  const settings = a.last_scan || { level: "quick", goals: loaded.tested_goals };
  const error = h("div", { role: "alert" });
  const instructions = h("textarea", { rows: "10", dir: "auto", "aria-label": "ההוראות של הבוט" });
  instructions.value = a.instructions || "";
  const add = (text) => {
    if (instructions.value.includes(text)) return;
    instructions.value = `${instructions.value.trimEnd()}\n${text}`;
  };
  const run = async (event) => {
    const button = event.target;
    button.disabled = true;
    try {
      if (a.mode === "instructions") {
        await api("/api/wizard/save", { answers: { ...a, instructions: instructions.value }, path });
      }
      const { batch } = await api("/api/scan/start", { path, level: settings.level, languages: settings.languages, goals: settings.goals || loaded.tested_goals, confirm_permission: true });
      saveDraft({ path, answers: a });
      location.hash = `#/check/run/${encodeURIComponent(batch)}`;
    } catch (e) {
      fill(error, problemFrom(e, "הבדיקה החוזרת לא התחילה."));
      button.disabled = false;
    }
  };

  guidedPage(
    null,
    h("h1", {}, "לבדוק שוב"),
    a.mode === "instructions"
      ? [
          h("p", { class: "g-lede" }, "מעדכנים את ההוראות של ", h("bdi", {}, a.name), ", ובודקים שוב עם אותם ניסיונות בדיוק, כדי לראות אם התיקון עזר."),
          fixes.length
            ? h("section", { class: "g-card g-fixlist" }, h("h2", {}, "התיקונים מהבדיקה הקודמת"), fixes.map((text) => h("div", { class: "g-fixrow" }, h("p", {}, text), h("button", { class: "btn small", type: "button", onclick: () => add(text) }, "הוספה להוראות"))), h("button", { class: "btn", type: "button", onclick: () => fixes.forEach(add) }, "להוסיף את כולם"))
            : null,
          gField("ההוראות של הבוט", instructions),
        ]
      : h("p", { class: "g-lede" }, "אחרי שעדכנת את ", h("bdi", {}, a.name), ", בודקים שוב עם אותם ניסיונות בדיוק, כדי לראות אם התיקון עזר.", fixes.length ? " התיקונים מהבדיקה הקודמת מופיעים במסך התוצאה." : ""),
    error,
    h("div", { class: "g-actions" }, h("button", { class: "btn primary big", type: "button", onclick: run }, "לבדוק שוב"), last ? h("a", { class: "btn quiet", href: `#/check/result/${encodeURIComponent(last.batch)}` }, "חזרה לתוצאה") : h("a", { class: "btn quiet", href: "#/" }, "חזרה"))
  );
}
