<div dir="rtl" align="right">

<h1 dir="rtl">התקנת HebJudge</h1>

<p dir="rtl">HebJudge רץ במחשב שלכם. הממשק נפתח בדפדפן, והסוכנים, הסריקות והתוצאות נשמרים בתיקייה שממנה מפעילים אותו. רק שני דברים יוצאים מהמחשב: הודעות התקיפה, שנשלחות לסוכן שבודקים, וכל שיחה, שנשלחת ל-OpenAI לשיפוט עם מפתח ה-API שלכם.</p>

<p dir="rtl"><a href="INSTALL.md">English</a></p>

<h2 dir="rtl">מה צריך</h2>

<ul dir="rtl">
<li><b>פייתון 3.11 ומעלה.</b></li>
<li><b>מפתח API של OpenAI</b>, בשביל השופט. הסריקות מחויבות בחשבון OpenAI שלכם. סריקה מהירה עולה בערך 5 סנט, והעלות מוצגת לפני שנשלח משהו.</li>
<li><b>סוכן שלכם, או סוכן שיש לכם הרשאה לבדוק</b>, בסביבת בדיקה. כדי לנסות קודם, יש סוכן דוגמה שלא עולה כלום.</li>
</ul>

<h2 dir="rtl">1. התקנת פייתון (אם עוד אין)</h2>

<p dir="rtl">בודקים בטרמינל (ב-Windows: PowerShell):</p>

<div dir="ltr" align="left">

```bash
python --version
```

</div>

<p dir="rtl">אם מופיע 3.11 ומעלה, ממשיכים לשלב 2. אחרת:</p>

<ul dir="rtl">
<li><b>Windows:</b> מורידים את פייתון מ-<a href="https://www.python.org/downloads/">python.org/downloads</a>. במסך הראשון של ההתקנה מסמנים <b>Add python.exe to PATH</b>, ולוחצים <b>Install Now</b>. אחרי ההתקנה סוגרים ופותחים מחדש את PowerShell.</li>
<li><b>Mac:</b> מורידים מ-<a href="https://www.python.org/downloads/">python.org/downloads</a>, או <code>brew install python</code>.</li>
</ul>

<h2 dir="rtl">2. התקנת HebJudge</h2>

<p dir="rtl">בוחרים תיקייה לעבודה, למשל <code>Documents\HebJudge</code>, פותחים בה טרמינל ומריצים:</p>

<div dir="ltr" align="left">

```bash
python -m venv .venv
```

</div>

<p dir="rtl">מפעילים את הסביבה:</p>

<ul dir="rtl">
<li>Windows (PowerShell): <code>.\.venv\Scripts\Activate.ps1</code></li>
<li>Mac / Linux: <code>source .venv/bin/activate</code></li>
</ul>

<p dir="rtl">אם PowerShell מסרב להריץ את הסקריפט, מריצים פעם אחת <code>Set-ExecutionPolicy -Scope CurrentUser RemoteSigned</code>, ואז מפעילים שוב.</p>

<p dir="rtl">ואז:</p>

<div dir="ltr" align="left">

```bash
pip install hebjudge
hebjudge init
```

</div>

<p dir="rtl">הפקודה <code>hebjudge init</code> מעתיקה את סוכני הדוגמה לתיקייה <code>examples</code>.</p>

<h2 dir="rtl">3. הוספת מפתח ה-API</h2>

<p dir="rtl">יוצרים מפתח בכתובת <a href="https://platform.openai.com/api-keys">platform.openai.com/api-keys</a>, ואז אחת משתי הדרכים:</p>

<ul dir="rtl">
<li>פותחים את הממשק (שלב 4) ומדביקים אותו במסך הפתיחה, או</li>
<li>מריצים <code>hebjudge key set</code> ומדביקים. המפתח לא מוצג בזמן ההקלדה.</li>
</ul>

<p dir="rtl">המפתח נשמר בקובץ <code>~/.hebjudge/config.env</code>, שרק המשתמש שלכם יכול לקרוא, ולעולם לא בתיקיית הפרויקט. הפקודה <code>hebjudge key test</code> בודקת אותו, בלי עלות.</p>

<h2 dir="rtl">4. פתיחת הממשק</h2>

<div dir="ltr" align="left">

```bash
hebjudge ui
```

</div>

<p dir="rtl">הדפדפן נפתח בכתובת <code>http://127.0.0.1:8770</code>. אם הוא לא נפתח, מעתיקים את הכתובת לדפדפן. כדי לסגור את הממשק לוחצים <b>Ctrl+C</b> בטרמינל.</p>

<p dir="rtl">בפעם הבאה: פותחים טרמינל באותה תיקייה, מפעילים את הסביבה (שלב 2), ומריצים <code>hebjudge ui</code>.</p>

<h2 dir="rtl">5. צעדים ראשונים בממשק</h2>

<p dir="rtl">הממשק נפתח בבדיקה מודרכת. לוחצים <b>מתחילים בדיקה</b> ועונים על שלוש שאלות:</p>

<ol dir="rtl">
<li><b>הבוט שלך:</b> מדביקים את ההוראות שכתבתם לבוט, או את כתובת ה-API שלו. כדי לנסות קודם בלי לחבר בוט, בוחרים <b>רק לנסות על בוט לדוגמה</b>.</li>
<li><b>מה אסור לו:</b> חמישה דברים שכמעט כל בוט צריך להיזהר מהם כבר מסומנים. מורידים את מה שלא רלוונטי, ומוסיפים במילים שלכם.</li>
<li><b>בדיקה:</b> רואים כמה ניסיונות יישלחו, כמה זמן זה ייקח וכמה זה יעלה לכל היותר, ומתחילים. בדיקה מהירה עולה בדרך כלל כמה סנטים.</li>
</ol>

<p dir="rtl">בתוצאה מופיע משפט מוכן לכל בעיה. מוסיפים אותו להוראות של הבוט, ולוחצים <b>תיקנתי, לבדוק שוב</b>. הבדיקה חוזרת על אותם ניסיונות בדיוק ומראה מה השתפר. כל השאר (קובצי סוכן, כל התבניות, השוואות) נמצא תחת <b>מצב מתקדם</b>.</p>

<h2 dir="rtl">עדכון לגרסה חדשה</h2>

<div dir="ltr" align="left">

```bash
pip install --upgrade hebjudge
```

</div>

<h2 dir="rtl">בעיות נפוצות</h2>

<table dir="rtl">
<tr><th>הבעיה</th><th>הפתרון</th></tr>
<tr><td><code>hebjudge</code> לא מזוהה</td><td>הסביבה לא פעילה: מריצים את פקודת ההפעלה משלב 2</td></tr>
<tr><td><code>python</code> לא מזוהה (Windows)</td><td>מתקינים שוב את פייתון עם <b>Add python.exe to PATH</b>, או כותבים <code>py</code> במקום <code>python</code></td></tr>
<tr><td>נפתח Edge במקום כרום</td><td>הממשק נפתח בדפדפן ברירת המחדל. מעתיקים את הכתובת לכרום, או משנים את ברירת המחדל בהגדרות של Windows</td></tr>
<tr><td>הפורט 8770 תפוס</td><td><code>hebjudge ui --port 8771</code></td></tr>
<tr><td>"חסר מפתח API"</td><td>מוסיפים אותו במסך הגדרות, או <code>hebjudge key set</code></td></tr>
<tr><td>המפתח לא עובד</td><td>בודקים שהועתק במלואו, ושיש יתרה בחשבון OpenAI</td></tr>
</table>

</div>
