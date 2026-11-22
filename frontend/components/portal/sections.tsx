"use client";

import "leaflet/dist/leaflet.css";

import { DownloadOutlined, LeftOutlined, LinkOutlined, PaperClipOutlined, PhoneOutlined, RightOutlined } from "@ant-design/icons";
import {
  Alert, App, Badge, Button, Card, DatePicker, Empty, Form, Input, List, Modal, Progress, Radio, Select, Space, Spin, Statistic, Tag, TimePicker, Typography,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import type * as Leaflet from "leaflet";
import { useCallback, useEffect, useRef, useState } from "react";

import type { Tab } from "@/components/portal/PortalApp";
import { usePortalLang } from "@/components/portal/PortalShell";
import { type Child, money, portal, PortalError, t, tr } from "@/lib/portal";

type P = { child: Child };

const L = {
  none: t("Nothing here yet.", "अभी कुछ नहीं।"), download: t("Download", "डाउनलोड"), send: t("Send", "भेजें"), sent: t("Sent", "भेजा गया"),
  present: t("Present", "उपस्थित"), absent: t("Absent", "अनुपस्थित"), leave: t("Leave", "अवकाश"), late: t("Late", "विलंब"),
  half_day: t("Half-day", "आधा दिन"), notMarked: t("Not marked yet", "अभी दर्ज नहीं"), holiday: t("Holiday", "अवकाश दिवस"),
  partly: t("Absent for some periods", "कुछ कालांशों में अनुपस्थित"),
  today: t("Attendance today", "आज की उपस्थिति"), dues: t("Fee due", "देय शुल्क"), overdue: t("Overdue", "बकाया"),
  paid: t("Paid", "भुगतान"), latest: t("Latest result", "नवीनतम परिणाम"), hwDue: t("Homework due", "देय गृहकार्य"),
  newNotices: t("New notices", "नई सूचनाएँ"), all: t("See all", "सभी देखें"), due: t("Due", "अंतिम तिथि"),
  submitted: t("Submitted", "जमा"), checked: t("Checked", "जाँचा गया"), notSubmitted: t("Not submitted", "जमा नहीं"),
  submit: t("Submit work", "कार्य जमा करें"), answer: t("Answer (optional if you attach a photo)", "उत्तर (फ़ोटो लगाने पर वैकल्पिक)"),
  photos: t("Photos or files (up to 5)", "फ़ोटो या फ़ाइलें (5 तक)"), onlyStudent: t("The student submits from their own login.", "छात्र अपने लॉगिन से जमा करता है।"),
  grade: t("Grade", "ग्रेड"), remarks: t("Teacher's remarks", "शिक्षक की टिप्पणी"), material: t("Study material", "अध्ययन सामग्री"),
  classes: t("Online classes", "ऑनलाइन कक्षाएँ"), tests: t("Online tests", "ऑनलाइन परीक्षाएँ"), join: t("Join class", "कक्षा से जुड़ें"),
  opens: t("Opens 15 minutes before the start", "आरंभ से 15 मिनट पहले खुलेगी"), ended: t("Ended", "समाप्त"), joined: t("Joined", "जुड़े"),
  start: t("Start test", "परीक्षा शुरू करें"), resume: t("Continue", "जारी रखें"), finish: t("Submit answers", "उत्तर जमा करें"),
  timeLeft: t("Time left", "शेष समय"), score: t("Score", "अंक"), receipts: t("Receipts", "रसीदें"), charges: t("Fee details", "शुल्क विवरण"),
  reportCard: t("Report card", "रिपोर्ट कार्ड"), pass: t("Pass", "उत्तीर्ण"), fail: t("Needs improvement", "सुधार आवश्यक"),
  outpass: t("Ask for an outpass", "आउटपास का अनुरोध"), from: t("Leaving on", "जाने की तिथि"), to: t("Returning on", "लौटने की तिथि"),
  returnBy: t("Return by (time)", "लौटने का समय"), where: t("Going to", "कहाँ"), reason: t("Reason", "कारण"),
  menu: t("This week's mess menu", "इस सप्ताह का मेस मेन्यू"), noHostel: t("Not staying in the hostel.", "छात्रावास में नहीं रहते।"),
  noBus: t("Not using school transport.", "विद्यालय परिवहन का उपयोग नहीं।"), seen: t("Bus location", "बस की स्थिति"),
  ago: t("ago", "पहले"), noGps: t("No location received yet today.", "आज अभी कोई स्थान नहीं मिला।"), driver: t("Driver", "चालक"),
  stop: t("Stop", "पड़ाव"), pickup: t("Pick-up", "पिक-अप"), drop: t("Drop", "ड्रॉप"),
  leaveAsk: t("Apply for leave (day scholar)", "अवकाश आवेदन (दिवा छात्र)"), leaveFrom: t("First day of leave", "अवकाश का पहला दिन"),
  leaveTo: t("Last day (empty = one day)", "अंतिम दिन (खाली = एक दिन)"),
  changeAsk: t("Ask the office to change", "कार्यालय से परिवर्तन का अनुरोध"), what: t("What", "क्या"), newValue: t("New value", "नया"),
  address: t("Address", "पता"), phone: t("Parent's mobile", "अभिभावक मोबाइल"), email: t("Parent's email", "अभिभावक ईमेल"),
  waiting: t("Waiting", "प्रतीक्षारत"), approved: t("Approved", "स्वीकृत"), rejected: t("Rejected", "अस्वीकृत"),
  noTimetable: t("No timetable yet.", "अभी समय-सारणी नहीं।"), online: t("Online", "ऑनलाइन"), sub: t("Substitute", "प्रतिस्थापक"),
  boarderOnly: t("Hostel students ask for an outpass on the Hostel page.", "छात्रावास के छात्र छात्रावास पृष्ठ पर आउटपास माँगें।"),
};

const STATUS_COLOR: Record<string, string> = { present: "green", absent: "red", leave: "blue", late: "gold", half_day: "orange" };
const REQ_COLOR: Record<string, string> = { requested: "orange", approved: "green", rejected: "red", out: "blue", returned: "default", cancelled: "default" };

function useLoad<R>(child: Child, path: string | null) {
  const [data, setData] = useState<R | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    if (path === null) return;
    try { setData(await portal.get<R>(child, path)); setError(null); } catch (e) { setError((e as Error).message); }
  }, [child, path]);
  useEffect(() => { void reload(); }, [reload]);
  return { data, error, reload };
}

function Loading({ error }: { error: string | null }) {
  return error ? <Alert type="error" showIcon message={error} /> : <div style={{ padding: 32, textAlign: "center" }}><Spin /></div>;
}

function statusLabel(st: string | null, lang: "en" | "hi") {
  if (!st) return tr(L.notMarked, lang);
  if (st === "partly absent") return tr(L.partly, lang);
  return tr((L as Record<string, ReturnType<typeof t>>)[st] ?? t(st, st), lang);
}

const fmt = (d: string | null | undefined, f = "DD-MM-YYYY") => (d ? dayjs(d).format(f) : "—");

// ------------------------------------------------------------------ home
interface Home {
  attendance_today: string | null; fees: { outstanding: string; overdue: string; paid: string };
  latest_result: { exam: number; name: string; percentage: string; grade: string | null } | null;
  homework_due: { id: number; subject: string; title: string; due_date: string }[]; homework_due_count: number;
  notices_unread: number; notices: { id: number; title: string; sent_at: string; read: boolean }[];
}

export function HomeTab({ child, go }: P & { go: (t: Tab) => void }) {
  const { lang } = usePortalLang();
  const { data, error } = useLoad<Home>(child, "");
  if (!data) return <Loading error={error} />;
  const st = data.attendance_today;
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card size="small" onClick={() => go("attendance")} hoverable>
        <Space style={{ width: "100%", justifyContent: "space-between" }}>
          <span>{tr(L.today, lang)}</span>
          <Tag data-testid="today-status" color={st ? STATUS_COLOR[st] ?? "red" : "default"}>{statusLabel(st, lang)}</Tag>
        </Space>
      </Card>
      <Card size="small" onClick={() => go("fees")} hoverable>
        <Space size="large" wrap>
          <Statistic title={tr(L.dues, lang)} value={money(data.fees.outstanding)} />
          {Number(data.fees.overdue) > 0 && <Statistic title={tr(L.overdue, lang)} value={money(data.fees.overdue)} valueStyle={{ color: "#c92a2a" }} />}
        </Space>
      </Card>
      {data.latest_result && (
        <Card size="small" onClick={() => go("results")} hoverable>
          <Space style={{ width: "100%", justifyContent: "space-between" }}>
            <span>{tr(L.latest, lang)}: {data.latest_result.name}</span>
            <b>{data.latest_result.percentage}% {data.latest_result.grade && <Tag color="blue">{data.latest_result.grade}</Tag>}</b>
          </Space>
        </Card>
      )}
      <Card size="small" title={<Badge count={data.homework_due_count} offset={[12, 0]}>{tr(L.hwDue, lang)}</Badge>}
        extra={<Button type="link" onClick={() => go("homework")}>{tr(L.all, lang)}</Button>}>
        {data.homework_due.length ? data.homework_due.map((h) => (
          <div key={h.id} className="portal-row"><span>{h.subject}: {h.title}</span><Typography.Text type="secondary">{fmt(h.due_date, "DD-MM")}</Typography.Text></div>
        )) : <Typography.Text type="secondary">{tr(L.none, lang)}</Typography.Text>}
      </Card>
      <Card size="small" title={<Badge count={data.notices_unread} offset={[12, 0]}>{tr(L.newNotices, lang)}</Badge>}
        extra={<Button type="link" onClick={() => go("notices")}>{tr(L.all, lang)}</Button>}>
        {data.notices.length ? data.notices.map((n) => (
          <div key={n.id} className="portal-row"><span style={{ fontWeight: n.read ? 400 : 600 }}>{n.title}</span><Typography.Text type="secondary">{fmt(n.sent_at, "DD-MM")}</Typography.Text></div>
        )) : <Typography.Text type="secondary">{tr(L.none, lang)}</Typography.Text>}
      </Card>
    </Space>
  );
}

// ------------------------------------------------------------------ attendance
interface Cal { days: { date: string; holiday: string | null; statuses: string[] }[]; attended: number; marked: number; percentage: number }

export function AttendanceTab({ child }: P) {
  const { lang } = usePortalLang();
  const [month, setMonth] = useState(dayjs().startOf("month"));
  const { data, error } = useLoad<Cal>(child, `attendance?month=${month.format("YYYY-MM")}`);
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Space style={{ width: "100%", justifyContent: "space-between" }}>
        <Button icon={<LeftOutlined />} onClick={() => setMonth(month.subtract(1, "month"))} aria-label="previous month" />
        <b>{month.format("MMMM YYYY")}</b>
        <Button icon={<RightOutlined />} disabled={!month.isBefore(dayjs().startOf("month"))} onClick={() => setMonth(month.add(1, "month"))} aria-label="next month" />
      </Space>
      {!data ? <Loading error={error} /> : (
        <>
          <Card size="small"><Progress type="circle" size={72} percent={Math.round(data.percentage)} /> <span style={{ marginLeft: 12 }}>{data.attended} / {data.marked}</span></Card>
          <div className="portal-cal">
            {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => <div key={`h${i}`} className="h">{d}</div>)}
            {Array.from({ length: (dayjs(data.days[0]?.date).day() + 6) % 7 }).map((_, i) => <div key={`e${i}`} />)}
            {data.days.map((d) => {
              const st = d.holiday ? "holiday" : d.statuses.includes("absent") ? "absent" : d.statuses[0] ?? "";
              return <div key={d.date} className={`d ${st}`} title={d.holiday ?? statusLabel(st || null, lang)}>{dayjs(d.date).date()}</div>;
            })}
          </div>
          <Space wrap size={4}>
            {["present", "absent", "leave", "late", "holiday"].map((k) => <span key={k} className={`portal-key ${k}`}>{statusLabel(k, lang)}</span>)}
          </Space>
        </>
      )}
    </Space>
  );
}

// ------------------------------------------------------------------ fees
interface Fees {
  charged: string; paid: string; outstanding: string; overdue: string;
  charges: { id: number; head: string; description: string; due_date: string; amount: string; paid: string; outstanding: string; overdue: boolean }[];
  receipts: { id: number; number: string; date: string; amount: string; mode: string }[];
}

export function FeesTab({ child }: P) {
  const { lang } = usePortalLang();
  const { data, error } = useLoad<Fees>(child, "fees");
  if (!data) return <Loading error={error} />;
  const open = data.charges.filter((c) => Number(c.outstanding) > 0);
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card size="small"><Space size="large" wrap>
        <Statistic title={tr(L.dues, lang)} value={money(data.outstanding)} />
        <Statistic title={tr(L.overdue, lang)} value={money(data.overdue)} valueStyle={{ color: Number(data.overdue) > 0 ? "#c92a2a" : undefined }} />
        <Statistic title={tr(L.paid, lang)} value={money(data.paid)} />
      </Space></Card>
      <Card size="small" title={tr(L.charges, lang)}>
        {open.length ? open.map((c) => (
          <div key={c.id} className="portal-row">
            <span>{c.description} <Typography.Text type="secondary">· {tr(L.due, lang)} {fmt(c.due_date, "DD-MM")}</Typography.Text> {c.overdue && <Tag color="red">{tr(L.overdue, lang)}</Tag>}</span>
            <b>{money(c.outstanding)}</b>
          </div>
        )) : <Typography.Text type="secondary">{tr(L.none, lang)}</Typography.Text>}
      </Card>
      <Card size="small" title={tr(L.receipts, lang)}>
        {data.receipts.length ? data.receipts.map((r) => (
          <div key={r.id} className="portal-row">
            <span>{r.number} <Typography.Text type="secondary">· {fmt(r.date)} · {r.mode}</Typography.Text></span>
            <Space><b>{money(r.amount)}</b><Button size="small" icon={<DownloadOutlined />} href={portal.href(child, `receipt?receipt=${r.id}`)} aria-label={`receipt ${r.number}`} /></Space>
          </div>
        )) : <Typography.Text type="secondary">{tr(L.none, lang)}</Typography.Text>}
      </Card>
    </Space>
  );
}

// ------------------------------------------------------------------ results
interface ResultRow { exam: number; name: string; year: string; percentage: string; grade: string | null; result: string; rank_section: number | null;
  subjects: { name: string; marks: string; max: string; grade: string | null }[] }

export function ResultsTab({ child }: P) {
  const { lang } = usePortalLang();
  const { data, error } = useLoad<ResultRow[]>(child, "results");
  if (!data) return <Loading error={error} />;
  if (!data.length) return <Empty description={tr(L.none, lang)} />;
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      {data.map((r) => (
        <Card key={r.exam} size="small" title={`${r.name} · ${r.year}`}
          extra={<Button size="small" icon={<DownloadOutlined />} href={portal.href(child, `report-card?exam=${r.exam}`)}>{tr(L.reportCard, lang)}</Button>}>
          <Space style={{ marginBottom: 8 }}>
            <b>{r.percentage}%</b>{r.grade && <Tag color="blue">{r.grade}</Tag>}
            {r.result !== "pending" && <Tag color={r.result === "pass" ? "green" : "orange"}>{tr(r.result === "pass" ? L.pass : L.fail, lang)}</Tag>}
          </Space>
          {r.subjects.map((s) => <div key={s.name} className="portal-row"><span>{s.name}</span><span>{s.marks} / {s.max} {s.grade && <Tag>{s.grade}</Tag>}</span></div>)}
        </Card>
      ))}
    </Space>
  );
}

// ------------------------------------------------------------------ homework + material
interface Hw { id: number; subject: string; title: string; description: string; due_date: string; files: { id: number; name: string }[];
  status: string; submitted_at: string | null; late: boolean; grade: string; remarks: string; my_files: { id: number; name: string }[]; text: string }
interface Material { id: number; subject: string; chapter: string; title: string; description: string; kind: string; link: string; file: string | null }

function SubmitForm({ child, hw, onDone }: P & { hw: Hw; onDone: () => void }) {
  const { lang } = usePortalLang();
  const { message } = App.useApp();
  const [text, setText] = useState(hw.text);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  async function send() {
    const fd = new FormData();
    fd.append("homework", String(hw.id));
    fd.append("text", text);
    files.forEach((f) => fd.append("files", f));
    setBusy(true);
    try { await portal.post(child, "submit", fd); message.success(tr(L.sent, lang)); onDone(); }
    catch (e) { message.error((e as Error).message); }
    finally { setBusy(false); }
  }
  return (
    <Space direction="vertical" style={{ width: "100%", marginTop: 8 }}>
      <Input.TextArea aria-label={`answer-${hw.id}`} placeholder={tr(L.answer, lang)} value={text} autoSize={{ minRows: 2 }} onChange={(e) => setText(e.target.value)} />
      <label className="portal-file">
        <PaperClipOutlined /> {tr(L.photos, lang)}{files.length ? ` · ${files.length}` : ""}
        <input data-testid={`files-${hw.id}`} type="file" multiple accept="image/*,.pdf,.docx,.pptx" capture="environment" hidden
          onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 5))} />
      </label>
      <Button type="primary" block loading={busy} disabled={!text.trim() && !files.length && !hw.my_files.length} onClick={() => void send()}>{tr(L.submit, lang)}</Button>
    </Space>
  );
}

export function HomeworkTab({ child }: P) {
  const { lang } = usePortalLang();
  const { data, error, reload } = useLoad<Hw[]>(child, "homework");
  const mats = useLoad<Material[]>(child, "materials");
  if (!data) return <Loading error={error} />;
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      {!data.length && <Empty description={tr(L.none, lang)} />}
      {data.map((h) => (
        <Card key={h.id} size="small" data-testid={`hw-${h.id}`}
          title={<span>{h.subject}: {h.title}</span>}
          extra={<Tag color={h.status === "checked" ? "green" : h.status === "submitted" ? "blue" : dayjs(h.due_date).isBefore(dayjs(), "day") ? "red" : "orange"}>
            {tr(h.status === "checked" ? L.checked : h.status === "submitted" ? L.submitted : L.notSubmitted, lang)}</Tag>}>
          <Typography.Text type="secondary">{tr(L.due, lang)} {fmt(h.due_date)}</Typography.Text>
          {h.description && <Typography.Paragraph style={{ margin: "6px 0" }}>{h.description}</Typography.Paragraph>}
          {h.files.map((f) => <div key={f.id}><a href={portal.href(child, `homework-file?homework=${h.id}&file=${f.id}`)}><PaperClipOutlined /> {f.name}</a></div>)}
          {h.submitted_at && <div style={{ marginTop: 6 }}>
            <Typography.Text type="secondary">{tr(L.submitted, lang)} {fmt(h.submitted_at, "DD-MM HH:mm")}</Typography.Text> {h.late && <Tag color="orange">{tr(L.late, lang)}</Tag>}
            {h.my_files.map((f) => <div key={f.id}><a href={portal.href(child, `homework-file?homework=${h.id}&file=${f.id}`)}><PaperClipOutlined /> {f.name}</a></div>)}
          </div>}
          {h.status === "checked" && <Alert style={{ marginTop: 8 }} type="success" data-testid={`grade-${h.id}`}
            message={<span>{tr(L.grade, lang)}: <b>{h.grade || "—"}</b></span>} description={h.remarks ? `${tr(L.remarks, lang)}: ${h.remarks}` : undefined} />}
          {h.status !== "checked" && (child.is_self ? <SubmitForm child={child} hw={h} onDone={() => void reload()} />
            : h.status === "not submitted" && <Typography.Text type="secondary" style={{ display: "block", marginTop: 6 }}>{tr(L.onlyStudent, lang)}</Typography.Text>)}
        </Card>
      ))}
      <Typography.Title level={5}>{tr(L.material, lang)}</Typography.Title>
      {(mats.data ?? []).length ? (
        <List size="small" bordered dataSource={mats.data ?? []} renderItem={(m) => (
          <List.Item actions={[m.file ? <a key="f" href={portal.href(child, `material-file?material=${m.id}`)}><DownloadOutlined /></a>
            : m.link ? <a key="l" href={m.link} target="_blank" rel="noopener noreferrer"><LinkOutlined /></a> : null]}>
            <List.Item.Meta title={m.title} description={`${m.subject}${m.chapter ? ` · ${m.chapter}` : ""}${m.description ? ` — ${m.description}` : ""}`} />
          </List.Item>
        )} />
      ) : <Typography.Text type="secondary">{tr(L.none, lang)}</Typography.Text>}
    </Space>
  );
}

// ------------------------------------------------------------------ online classes + tests
interface OClass { id: number; title: string; subject: string; starts_at: string; ends_at: string; state: string; joined: boolean }
interface OTest { id: number; title: string; subject: string; opens_at: string; closes_at: string; time_limit_minutes: number; questions: number;
  state: string; attempt: number | null; score: string | null; max_score: string | null }
interface Attempt { attempt: number; title: string; instructions: string; deadline: string; submitted_at: string | null; score: string | null; max_score: string | null;
  answers: Record<string, number>; questions: { id: number; sequence: number; text: string; options: string[]; marks: string; correct?: number }[] }

function TestRunner({ child, attemptStart, onClose }: P & { attemptStart: Attempt; onClose: () => void }) {
  const { lang } = usePortalLang();
  const { message } = App.useApp();
  const [a, setA] = useState(attemptStart);
  const [answers, setAnswers] = useState<Record<string, number>>(attemptStart.answers ?? {});
  const [now, setNow] = useState(dayjs());
  useEffect(() => { const id = window.setInterval(() => setNow(dayjs()), 1000); return () => window.clearInterval(id); }, []);
  const left = Math.max(0, dayjs(a.deadline).diff(now, "second"));
  const done = a.submitted_at !== null;
  const finish = useCallback(async () => {
    try { setA(await portal.post<Attempt>(child, "finish-test", { attempt: a.attempt, answers })); }
    catch (e) { message.error((e as Error).message); }
  }, [a.attempt, answers, child, message]);
  useEffect(() => { if (!done && left === 0) void finish(); }, [done, left, finish]);
  const pick = (qid: number, v: number) => {
    const next = { ...answers, [String(qid)]: v };
    setAnswers(next);
    void portal.post(child, "save-answers", { attempt: a.attempt, answers: next }).catch(() => undefined);
  };
  return (
    <Modal open title={a.title} onCancel={onClose} footer={done ? <Button onClick={onClose}>OK</Button>
      : <Button type="primary" onClick={() => void finish()}>{tr(L.finish, lang)}</Button>} width={640}>
      {done ? <Alert type="success" showIcon data-testid="test-score" message={`${tr(L.score, lang)}: ${a.score} / ${a.max_score}`} />
        : <Alert type={left < 60 ? "warning" : "info"} message={`${tr(L.timeLeft, lang)}: ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`} />}
      {a.instructions && <Typography.Paragraph style={{ marginTop: 8 }}>{a.instructions}</Typography.Paragraph>}
      {a.questions.map((q) => (
        <Card key={q.id} size="small" style={{ marginTop: 8 }} title={`${q.sequence}. ${q.text}`}>
          <Radio.Group disabled={done} value={answers[String(q.id)]} onChange={(e) => pick(q.id, e.target.value)}>
            <Space direction="vertical">
              {q.options.map((o, i) => <Radio key={i} value={i} aria-label={`q${q.sequence}-${i}`}>
                {o} {done && q.correct === i && <Tag color="green">✓</Tag>}</Radio>)}
            </Space>
          </Radio.Group>
        </Card>
      ))}
    </Modal>
  );
}

export function ClassesTab({ child }: P) {
  const { lang } = usePortalLang();
  const { message } = App.useApp();
  const classes = useLoad<OClass[]>(child, "classes");
  const tests = useLoad<OTest[]>(child, "tests");
  const [running, setRunning] = useState<Attempt | null>(null);
  async function join(c: OClass) {
    try {
      const r = await portal.post<{ link: string }>(child, "join", { online_class: c.id });
      window.open(r.link, "_blank", "noopener");
      void classes.reload();
    } catch (e) { message.error((e as Error).message); }
  }
  async function start(tst: OTest) {
    try { setRunning(await portal.post<Attempt>(child, "start-test", { test: tst.id })); }
    catch (e) { message.error((e as Error).message); }
  }
  async function view(tst: OTest) {
    try { setRunning(await portal.get<Attempt>(child, `attempt?attempt=${tst.attempt}`)); } catch (e) { message.error((e as Error).message); }
  }
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Typography.Title level={5} style={{ margin: 0 }}>{tr(L.classes, lang)}</Typography.Title>
      {!classes.data ? <Loading error={classes.error} /> : classes.data.length ? classes.data.map((c) => (
        <Card key={c.id} size="small" title={`${c.subject}: ${c.title}`} extra={c.joined && <Tag color="green">{tr(L.joined, lang)}</Tag>}>
          <div>{fmt(c.starts_at, "ddd DD-MM HH:mm")} – {fmt(c.ends_at, "HH:mm")}</div>
          {c.state === "ended" ? <Tag>{tr(L.ended, lang)}</Tag> : child.is_self ? (
            <Button style={{ marginTop: 8 }} type="primary" disabled={c.state !== "open"} onClick={() => void join(c)}>{tr(L.join, lang)}</Button>
          ) : null}
          {c.state === "later" && <Typography.Text type="secondary" style={{ display: "block" }}>{tr(L.opens, lang)}</Typography.Text>}
        </Card>
      )) : <Typography.Text type="secondary">{tr(L.none, lang)}</Typography.Text>}
      <Typography.Title level={5} style={{ margin: 0 }}>{tr(L.tests, lang)}</Typography.Title>
      {!tests.data ? <Loading error={tests.error} /> : tests.data.length ? tests.data.map((x) => (
        <Card key={x.id} size="small" title={`${x.subject}: ${x.title}`}
          extra={x.score !== null ? <Tag color="blue">{x.score} / {x.max_score}</Tag> : <Tag>{x.state}</Tag>}>
          <div>{fmt(x.opens_at, "DD-MM HH:mm")} – {fmt(x.closes_at, "DD-MM HH:mm")} · {x.questions} Q · {x.time_limit_minutes} min</div>
          {child.is_self && (x.state === "open" || x.state === "in progress") && (
            <Button style={{ marginTop: 8 }} type="primary" onClick={() => void start(x)}>{tr(x.state === "open" ? L.start : L.resume, lang)}</Button>)}
          {x.state === "submitted" && x.attempt && <Button style={{ marginTop: 8 }} onClick={() => void view(x)}>{tr(L.score, lang)}</Button>}
        </Card>
      )) : <Typography.Text type="secondary">{tr(L.none, lang)}</Typography.Text>}
      {running && <TestRunner child={child} attemptStart={running} onClose={() => { setRunning(null); void tests.reload(); }} />}
    </Space>
  );
}

// ------------------------------------------------------------------ timetable + diary
interface Grid { days: { day: number; name: string }[]; slots: { slot: number; number: number; label: string; start: string; end: string; is_break: boolean; days: number[] }[];
  cells: { day: number; slot: number; subject?: string; teacher?: string; substitute_name?: string | null }[];
  online: { id: number; title: string; subject: string; start: string; end: string }[] }

export function TimetableTab({ child }: P) {
  const { lang } = usePortalLang();
  const [day, setDay] = useState<Dayjs>(dayjs());
  const { data, error } = useLoad<Grid>(child, `timetable?date=${day.format("YYYY-MM-DD")}`);
  const wd = (day.day() + 6) % 7;
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <DatePicker value={day} allowClear={false} format="ddd DD-MM-YYYY" onChange={(d) => d && setDay(d)} style={{ width: "100%" }} />
      {!data ? <Loading error={error} /> : !data.slots.length && !data.online.length ? <Empty description={tr(L.noTimetable, lang)} /> : (
        <Card size="small">
          {data.slots.filter((s) => s.days.includes(wd)).map((s) => {
            const c = data.cells.find((x) => x.slot === s.slot && x.day === wd);
            return (
              <div key={s.slot} className="portal-row">
                <Typography.Text type="secondary">{String(s.start).slice(0, 5)}</Typography.Text>
                <span>{s.is_break ? s.label : c ? <>{c.subject} <Typography.Text type="secondary">{c.substitute_name ? `${tr(L.sub, lang)}: ${c.substitute_name}` : c.teacher}</Typography.Text></> : "—"}</span>
              </div>
            );
          })}
          {data.online.map((o) => (
            <div key={`o${o.id}`} className="portal-row"><Typography.Text type="secondary">{String(o.start).slice(0, 5)}</Typography.Text>
              <span>{o.subject}: {o.title} <Tag color="purple">{tr(L.online, lang)}</Tag></span></div>
          ))}
        </Card>
      )}
    </Space>
  );
}

interface Diary { id: number; date: string; period: number | null; subject: string; topic: string; notes: string; teacher: string }

export function DiaryTab({ child }: P) {
  const { lang } = usePortalLang();
  const { data, error } = useLoad<Diary[]>(child, "diary");
  if (!data) return <Loading error={error} />;
  if (!data.length) return <Empty description={tr(L.none, lang)} />;
  return (
    <List size="small" bordered dataSource={data} renderItem={(d) => (
      <List.Item><List.Item.Meta title={`${fmt(d.date, "ddd DD-MM")}${d.period ? ` · P${d.period}` : ""} · ${d.subject}`}
        description={<>{d.topic}{d.notes && <div>{d.notes}</div>}<Typography.Text type="secondary">{d.teacher}</Typography.Text></>} /></List.Item>
    )} />
  );
}

// ------------------------------------------------------------------ hostel
interface Outpasses { boarder: boolean; rows: { id: number; from_date: string; to_date: string; return_by: string; destination: string; reason: string; status: string; status_name: string; decision_note: string }[] }
interface Menu { mess: string; items: { day: number; day_name: string; meal: string; meal_name: string; items: string; items_hi: string; is_veg: boolean }[] }

export function HostelTab({ child }: P) {
  const { lang } = usePortalLang();
  const { message } = App.useApp();
  const { data, error, reload } = useLoad<Outpasses>(child, "outpasses");
  const menu = useLoad<Menu | null>(child, "menu");
  const [form] = Form.useForm<{ from: Dayjs; to: Dayjs; return_by?: Dayjs; destination?: string; reason: string }>();
  if (!data) return <Loading error={error} />;
  if (!data.boarder && !data.rows.length) return <Alert type="info" showIcon message={tr(L.noHostel, lang)} />;
  async function ask(v: { from: Dayjs; to: Dayjs; return_by?: Dayjs; destination?: string; reason: string }) {
    try {
      await portal.post(child, "outpass", { from_date: v.from.format("YYYY-MM-DD"), to_date: v.to.format("YYYY-MM-DD"),
        return_by: v.return_by?.format("HH:mm"), destination: v.destination ?? "", reason: v.reason });
      message.success(tr(L.sent, lang));
      form.resetFields();
      void reload();
    } catch (e) { message.error((e as Error).message); }
  }
  const today = (dayjs().day() + 6) % 7;
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      {data.boarder && (
        <Card size="small" title={tr(L.outpass, lang)}>
          <Form form={form} layout="vertical" onFinish={(v) => void ask(v)}>
            <Form.Item name="from" label={tr(L.from, lang)} rules={[{ required: true }]}>
              <DatePicker style={{ width: "100%" }} format="DD-MM-YYYY" disabledDate={(d) => d.isBefore(dayjs(), "day")} inputReadOnly />
            </Form.Item>
            <Form.Item name="to" label={tr(L.to, lang)} dependencies={["from"]} rules={[{ required: true }, ({ getFieldValue }) => ({
              validator: (_, v: Dayjs | undefined) => (!v || !getFieldValue("from") || !v.isBefore(getFieldValue("from"), "day") ? Promise.resolve()
                : Promise.reject(new Error(tr(t("Return date is before the leaving date.", "लौटने की तिथि जाने से पहले है।"), lang)))) })]}>
              <DatePicker style={{ width: "100%" }} format="DD-MM-YYYY" disabledDate={(d) => d.isBefore(dayjs(), "day")} inputReadOnly />
            </Form.Item>
            <Form.Item name="return_by" label={tr(L.returnBy, lang)}><TimePicker format="HH:mm" minuteStep={15} style={{ width: "100%" }} inputReadOnly /></Form.Item>
            <Form.Item name="destination" label={tr(L.where, lang)}><Input maxLength={200} /></Form.Item>
            <Form.Item name="reason" label={tr(L.reason, lang)} rules={[{ required: true }]}><Input maxLength={200} /></Form.Item>
            <Button type="primary" htmlType="submit" block>{tr(L.send, lang)}</Button>
          </Form>
        </Card>
      )}
      {data.rows.map((o) => (
        <Card key={o.id} size="small" data-testid={`outpass-${o.id}`}>
          <Space style={{ width: "100%", justifyContent: "space-between" }}>
            <span>{fmt(o.from_date, "DD-MM")} → {fmt(o.to_date, "DD-MM")} · {o.destination || o.reason}</span>
            <Tag color={REQ_COLOR[o.status]}>{o.status_name}</Tag>
          </Space>
          {o.decision_note && <Typography.Text type="secondary">{o.decision_note}</Typography.Text>}
        </Card>
      ))}
      {menu.data && (
        <Card size="small" title={`${tr(L.menu, lang)} · ${menu.data.mess}`}>
          {Array.from(new Set(menu.data.items.map((i) => i.day))).map((d) => (
            <div key={d} style={{ marginBottom: 6, fontWeight: d === today ? 600 : 400 }}>
              <div>{menu.data!.items.find((i) => i.day === d)?.day_name}</div>
              {menu.data!.items.filter((i) => i.day === d).map((i) => (
                <div key={i.meal} className="portal-row"><Typography.Text type="secondary">{i.meal_name}</Typography.Text><span>{lang === "hi" && i.items_hi ? i.items_hi : i.items}</span></div>
              ))}
            </div>
          ))}
        </Card>
      )}
    </Space>
  );
}

// ------------------------------------------------------------------ bus
interface Bus { route: string; route_code: string; stop: string; stop_lat: string | null; stop_lng: string | null; pickup_time: string | null; drop_time: string | null;
  vehicle: string; driver: string; driver_phone: string; helper: string; helper_phone: string;
  bus: { lat: string | null; lng: string | null; speed: string | null; seen_at: string | null; age_seconds: number | null } }

export function BusTab({ child }: P) {
  const { lang } = usePortalLang();
  const { data, error, reload } = useLoad<Bus | null>(child, "transport");
  const box = useRef<HTMLDivElement | null>(null);
  const map = useRef<Leaflet.Map | null>(null);
  const layer = useRef<Leaflet.LayerGroup | null>(null);
  useEffect(() => { const id = window.setInterval(() => void reload(), 20000); return () => window.clearInterval(id); }, [reload]);
  useEffect(() => {
    if (!data || !box.current) return;
    void import("leaflet").then((mod) => {
      const Lf = mod.default ?? mod;
      if (!map.current && box.current) {
        map.current = Lf.map(box.current).setView([25.5941, 85.1376], 13);
        Lf.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap contributors" }).addTo(map.current);
        layer.current = Lf.layerGroup().addTo(map.current);
      }
      layer.current!.clearLayers();
      const pts: [number, number][] = [];
      if (data.stop_lat && data.stop_lng) {
        const p: [number, number] = [Number(data.stop_lat), Number(data.stop_lng)];
        Lf.circleMarker(p, { radius: 7, color: "#2b8a3e" }).bindTooltip(data.stop).addTo(layer.current!);
        pts.push(p);
      }
      if (data.bus.lat && data.bus.lng) {
        const p: [number, number] = [Number(data.bus.lat), Number(data.bus.lng)];
        Lf.circleMarker(p, { radius: 10, color: "#1e2761", fillColor: "#3b5bdb", fillOpacity: 0.9 }).bindTooltip(data.vehicle, { permanent: true }).addTo(layer.current!);
        pts.push(p);
      }
      if (pts.length) map.current!.fitBounds(Lf.latLngBounds(pts).pad(0.4), { maxZoom: 16 });
    });
  }, [data]);
  if (error) return <Loading error={error} />;
  if (data === null) return <Alert type="info" showIcon message={tr(L.noBus, lang)} />;
  const age = data.bus.age_seconds;
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card size="small">
        <div className="portal-row"><span>{data.route_code} · {data.route}</span><b>{data.vehicle}</b></div>
        <div className="portal-row"><span>{tr(L.stop, lang)}: {data.stop}</span>
          <span>{data.pickup_time && `${tr(L.pickup, lang)} ${data.pickup_time.slice(0, 5)}`} {data.drop_time && `· ${tr(L.drop, lang)} ${data.drop_time.slice(0, 5)}`}</span></div>
        {data.driver && <div className="portal-row"><span>{tr(L.driver, lang)}: {data.driver}</span>
          {data.driver_phone && <Button size="small" icon={<PhoneOutlined />} href={`tel:${data.driver_phone}`}>{data.driver_phone}</Button>}</div>}
      </Card>
      <Card size="small" title={tr(L.seen, lang)} extra={age !== null && <Tag color={age < 300 ? "green" : "default"}>{age < 60 ? `${age}s` : `${Math.floor(age / 60)}m`} {tr(L.ago, lang)}</Tag>}>
        {age === null && <Typography.Text type="secondary">{tr(L.noGps, lang)}</Typography.Text>}
        <div ref={box} style={{ height: 260, borderRadius: 8 }} data-testid="bus-map" />
      </Card>
    </Space>
  );
}

// ------------------------------------------------------------------ notices
interface Notice { id: number; title: string; body: string; sent_at: string; read: boolean }

export function NoticesTab({ child }: P) {
  const { lang } = usePortalLang();
  const { data, error, reload } = useLoad<Notice[]>(child, "notices");
  const [open, setOpen] = useState<number | null>(null);
  if (!data) return <Loading error={error} />;
  if (!data.length) return <Empty description={tr(L.none, lang)} />;
  return (
    <List bordered dataSource={data} renderItem={(n) => (
      <List.Item style={{ cursor: "pointer" }} onClick={() => {
        setOpen(open === n.id ? null : n.id);
        if (!n.read) void portal.post(child, "read-notice", { notice: n.id }).then(() => void reload());
      }}>
        <List.Item.Meta title={<span style={{ fontWeight: n.read ? 400 : 700 }}>{n.title}</span>} description={
          <>{fmt(n.sent_at, "DD-MM-YYYY HH:mm")}{open === n.id && <Typography.Paragraph style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{n.body}</Typography.Paragraph>}</>} />
      </List.Item>
    )} />
  );
}

// ------------------------------------------------------------------ leave + change requests
interface Leave { id: number; from_date: string; to_date: string; days: number; reason: string; status: string; decision_note: string }
interface Change { id: number; field: string; field_name: string; old_value: string; new_value: string; status: string; decision_note: string; created_at: string }

export function RequestsTab({ child }: P) {
  const { lang } = usePortalLang();
  const { message } = App.useApp();
  const leaves = useLoad<Leave[]>(child, "leaves");
  const changes = useLoad<Change[]>(child, "changes");
  const out = useLoad<Outpasses>(child, "outpasses");
  const [lf] = Form.useForm<{ from: Dayjs; to: Dayjs; reason: string }>();
  const [cf] = Form.useForm<{ field: string; new_value: string }>();
  const label: Record<string, ReturnType<typeof t>> = { requested: L.waiting, approved: L.approved, rejected: L.rejected };
  async function leave(v: { from: Dayjs; to?: Dayjs; reason: string }) {
    try {
      await portal.post(child, "leave", { from_date: v.from.format("YYYY-MM-DD"), to_date: (v.to ?? v.from).format("YYYY-MM-DD"), reason: v.reason });
      message.success(tr(L.sent, lang)); lf.resetFields(); void leaves.reload();
    } catch (e) { message.error((e as PortalError).message); }
  }
  async function change(v: { field: string; new_value: string }) {
    try { await portal.post(child, "change", v); message.success(tr(L.sent, lang)); cf.resetFields(); void changes.reload(); }
    catch (e) { message.error((e as PortalError).message); }
  }
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      {out.data?.boarder ? <Alert type="info" showIcon message={tr(L.boarderOnly, lang)} /> : (
        <Card size="small" title={tr(L.leaveAsk, lang)}>
          <Form form={lf} layout="vertical" onFinish={(v) => void leave(v)}>
            <Form.Item name="from" label={tr(L.leaveFrom, lang)} rules={[{ required: true }]}>
              <DatePicker style={{ width: "100%" }} format="DD-MM-YYYY" inputReadOnly disabledDate={(d) => d.isBefore(dayjs().subtract(7, "day"), "day")} />
            </Form.Item>
            <Form.Item name="to" label={tr(L.leaveTo, lang)}>
              <DatePicker style={{ width: "100%" }} format="DD-MM-YYYY" inputReadOnly disabledDate={(d) => d.isBefore(dayjs().subtract(7, "day"), "day")} />
            </Form.Item>
            <Form.Item name="reason" label={tr(L.reason, lang)} rules={[{ required: true }]}><Input maxLength={300} /></Form.Item>
            <Button type="primary" htmlType="submit" block>{tr(L.send, lang)}</Button>
          </Form>
        </Card>
      )}
      {(leaves.data ?? []).map((x) => (
        <Card key={x.id} size="small"><Space style={{ width: "100%", justifyContent: "space-between" }}>
          <span>{fmt(x.from_date, "DD-MM")} → {fmt(x.to_date, "DD-MM")} · {x.reason}</span>
          <Tag color={REQ_COLOR[x.status]}>{tr(label[x.status] ?? t(x.status, x.status), lang)}</Tag></Space>
          {x.decision_note && <Typography.Text type="secondary">{x.decision_note}</Typography.Text>}</Card>
      ))}
      {!child.is_self && (
        <Card size="small" title={tr(L.changeAsk, lang)}>
          <Form form={cf} layout="vertical" onFinish={(v) => void change(v)} initialValues={{ field: "address" }}>
            <Form.Item name="field" label={tr(L.what, lang)}>
              <Select options={[{ value: "address", label: tr(L.address, lang) }, { value: "phone", label: tr(L.phone, lang) }, { value: "email", label: tr(L.email, lang) }]} />
            </Form.Item>
            <Form.Item name="new_value" label={tr(L.newValue, lang)} rules={[{ required: true }]}><Input.TextArea autoSize maxLength={500} /></Form.Item>
            <Button type="primary" htmlType="submit" block>{tr(L.send, lang)}</Button>
          </Form>
        </Card>
      )}
      {(changes.data ?? []).map((x) => (
        <Card key={x.id} size="small"><Space style={{ width: "100%", justifyContent: "space-between" }}>
          <span>{x.field_name}: {x.new_value}</span><Tag color={REQ_COLOR[x.status]}>{tr(label[x.status] ?? t(x.status, x.status), lang)}</Tag></Space>
          {x.decision_note && <Typography.Text type="secondary">{x.decision_note}</Typography.Text>}</Card>
      ))}
    </Space>
  );
}
