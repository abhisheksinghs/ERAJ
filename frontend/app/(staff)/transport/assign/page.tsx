"use client";

import { Alert, App, Button, Card, DatePicker, Descriptions, Form, Radio, Result, Space, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Assign a student or staff member to a route, stop and vehicle — or change an existing rider from a date. */
interface Assignment { id: number; rider_name: string; route: number; route_code: string; stop: number; stop_name: string; vehicle: number; vehicle_no: string; start_date: string; monthly_fare: string }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  assign: t("Assign a rider", "यात्री जोड़ें"), change: t("Change stop or vehicle", "पड़ाव या वाहन बदलें"),
  student: t("Student", "छात्र"), staff: t("Staff", "कर्मचारी"), route: t("Route", "मार्ग"), stop: t("Stop", "पड़ाव"),
  vehicle: t("Vehicle", "वाहन"), from: t("From", "से"), save: t("Save", "सहेजें"),
  current: t("Rides now", "वर्तमान"), feeNote: t("Students' monthly fare is added to their Fees account from this month to the end of the session.",
    "छात्रों का मासिक किराया इस माह से सत्र के अंत तक शुल्क खाते में जुड़ेगा।"),
  changeNote: t("The old stop's fees stop from this date's month (or the next, mid-month); the new fare starts.",
    "पुराने पड़ाव का शुल्क इस तिथि के माह (मध्य-माह हो तो अगले) से बंद; नया किराया आरंभ।"),
};

function AssignForm() {
  const { lang, can, allBranches } = useSession();
  const { message } = App.useApp();
  const router = useRouter();
  const params = useSearchParams();
  const changeId = params.get("change");
  const [current, setCurrent] = useState<Assignment | null>(null);
  const [kind, setKind] = useState<"student" | "staff">("student");
  const [rider, setRider] = useState<number | null>(null);
  const [route, setRoute] = useState<number | null>(null);
  const [stop, setStop] = useState<number | null>(null);
  const [vehicle, setVehicle] = useState<number | null>(null);
  const [from, setFrom] = useState<Dayjs>(dayjs());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!changeId) return;
    void api.get<Assignment>(`transport/assignments/${changeId}`).then((a) => {
      setCurrent(a);
      setRoute(a.route);
      setFrom(dayjs().add(1, "month").startOf("month"));
    });
  }, [changeId]);

  if (!can("transport.assignment.manage")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;

  async function save() {
    setBusy(true);
    try {
      if (current) {
        await api.post(`transport/assignments/${current.id}/change`, { stop, vehicle, from_date: from.format("YYYY-MM-DD") });
      } else {
        await api.post("transport/assignments", { [kind]: rider, stop, vehicle, start_date: from.format("YYYY-MM-DD") });
      }
      message.success(tr(UI.done, lang));
      router.push("/transport/assignments");
    } catch (e) {
      const err = e as { message?: string; errors?: Record<string, string[]> };
      message.error(err.errors ? Object.values(err.errors).flat()[0] : err.message ?? "Error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8, maxWidth: 640 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(current ? L.change : L.assign, lang)}</Typography.Title>
      {current && (
        <Descriptions size="small" bordered column={1} title={tr(L.current, lang)}>
          <Descriptions.Item label={current.rider_name}>{`${current.route_code} · ${current.stop_name} · ${current.vehicle_no} · ₹${Number(current.monthly_fare)}`}</Descriptions.Item>
        </Descriptions>
      )}
      <Card size="small">
        <Form layout="vertical" onFinish={save}>
          {!current && (
            <>
              <Form.Item><Radio.Group value={kind} onChange={(e) => { setKind(e.target.value); setRider(null); }}
                options={[{ value: "student", label: tr(L.student, lang) }, { value: "staff", label: tr(L.staff, lang) }]} /></Form.Item>
              <Form.Item label={tr(kind === "student" ? L.student : L.staff, lang)} required>
                <RelationSelect key={kind} resource={kind === "student" ? "people/students" : "people/staff"} label="full_name" search
                  value={rider} onChange={(v) => setRider(v as number)} placeholder={tr(kind === "student" ? L.student : L.staff, lang)} />
              </Form.Item>
            </>
          )}
          <Form.Item label={tr(L.route, lang)} required>
            <RelationSelect resource="transport/routes" label="code" value={route} placeholder={tr(L.route, lang)}
              onChange={(v) => { setRoute(v as number); setStop(null); setVehicle(null); }} />
          </Form.Item>
          <Form.Item label={tr(L.stop, lang)} required>
            <RelationSelect key={`s${route}`} resource="transport/stops" label="label" value={stop} enabled={!!route} placeholder={tr(L.stop, lang)}
              filters={[{ field: "route", value: route }]} onChange={(v) => setStop(v as number)} />
          </Form.Item>
          <Form.Item label={tr(L.vehicle, lang)} required>
            <RelationSelect key={`v${route}`} resource="transport/vehicles" label="registration_no" value={vehicle} enabled={!!route} placeholder={tr(L.vehicle, lang)}
              filters={[{ field: "route", value: route }]} onChange={(v) => setVehicle(v as number)} />
          </Form.Item>
          <Form.Item label={tr(L.from, lang)} required>
            <DatePicker value={from} onChange={(d) => d && setFrom(d)} format="DD-MM-YYYY" allowClear={false} aria-label="from" />
          </Form.Item>
          <Alert type="info" showIcon style={{ marginBottom: 12 }} message={tr(current ? L.changeNote : L.feeNote, lang)} />
          <Button type="primary" htmlType="submit" loading={busy} disabled={!stop || !vehicle || (!current && !rider)}>{tr(L.save, lang)}</Button>
        </Form>
      </Card>
    </Space>
  );
}

export default function AssignPage() {
  return <Suspense><AssignForm /></Suspense>;
}
